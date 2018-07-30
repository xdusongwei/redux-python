from typing import *
import re
import json
import asyncio
from urllib.parse import urljoin
import websockets
from .framework import Store, Listener, Action


class StateCellFilter:
    def create_cell_url(self, key: str) -> str:
        return "/redux/{}".format(key)

    def decode_cell_url(self, url: str) -> Optional[str]:
        re_match = re.match(r"/redux/(.+)", url)
        if re_match and re_match.lastindex == 1:
            return re_match.group(1)
        return None


class VirtualStore:
    def __init__(self, uri: str, socket: websockets.WebSocketClientProtocol,
                 loads=json.loads, dumps=json.dumps):
        self._get_state_queue = []
        self._uri = uri
        self._connection = socket
        self._state = {}
        self._observer_list = set([])
        self.loads = loads
        self.dumps = dumps
        asyncio.ensure_future(self._reader(), loop=asyncio.get_event_loop())

    @staticmethod
    async def create(host: str, key_uri):
        url = urljoin(host, key_uri)
        socket = await websockets.connect(url)
        return VirtualStore(url, socket)

    async def close(self):
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._observer_list.clear()

    async def _reader(self):
        async for message in self._connection:
            state = self.loads(message)
            if not state:
                continue
            self._state.update(state)
            for listener in list(self._observer_list):
                await listener.on_changed(list(state.keys()), state)

    async def dispatch(self, action: Union[Dict[str, Any], Action]):
        connection = self._connection
        assert connection
        action_data = action
        if isinstance(action, Action):
            action_data = action.to_data(self.dumps)
        else:
            action_data = self.dumps(action_data)
        assert isinstance(action_data, str) or isinstance(action_data, bytes)
        await connection.send(action_data)

    def get_state(self):
        return self._state

    def subscribe(self, key, listener: Listener):
        self._observer_list.add(listener)

    def unsubscribe(self, listener: Listener):
        if listener in self._observer_list:
            self._observer_list.remove(listener)


class _WebSocketListener(Listener):
    def __init__(self, key, store: 'WebSocketStoreServer', ws: websockets.WebSocketServerProtocol):
        self.ws = ws
        super(_WebSocketListener, self).__init__(key, store)

    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        response = {}
        for key in changed_key:
            if key in state:
                response[key] = state[key]
        await self.ws.send(self.store.dumps(response))


class WebSocketStoreServer(Store):
    def __init__(self, host: str, port: int, reducer: Type,
                 loads=json.loads, dumps=json.dumps,
                 cell_filter: StateCellFilter=StateCellFilter()):
        super(WebSocketStoreServer, self).__init__(reducer)
        assert reducer
        assert cell_filter
        assert loads
        assert dumps
        self._filter = cell_filter
        self.server = None
        self._host = host
        self._port = port
        self.loads = loads
        self.dumps = dumps

    async def start(self):
        host = self._host
        port = self._port
        server = await websockets.serve(self._pre_dispatch, host, port)
        self.server = server

    async def _pre_dispatch(self, ws: websockets.WebSocketServerProtocol, path):
        key = self._filter.decode_cell_url(path)
        try:
            if not key:
                return
            listener = _WebSocketListener(key, self, ws)
            async for message in ws:
                action = Action.from_data(message, self.loads)
                result = await self.dispatch(key, action)
                if not result:
                    raise IndexError
                if not listener.is_binding:
                    raise ConnectionError
        finally:
            await ws.close()
