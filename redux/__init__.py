from typing import *
import json
import asyncio
import websockets

__all__ = ['Action', 'Reducer', 'StoreWrapper', 'Store', 'Listener']


class Listener:
    def __init__(self, wrapper: 'StoreWrapper'):
        assert wrapper
        self.store_wrapper = wrapper
        wrapper.subscribe(self)

    def unsubscribe(self):
        self.store_wrapper.unsubscribe(self)

    async def on_changed(self):
        raise NotImplementedError


class Action:
    def __init__(self, action_type: str, **kwargs):
        self.type = action_type
        self.arguments = kwargs or {}
        assert isinstance(self.type, str)
        assert isinstance(self.arguments, dict)

    def to_json(self) -> str:
        action_dict = dict(type=self.type, **self.arguments)
        return json.dumps(action_dict)

    @staticmethod
    def from_json(json_data: str) -> 'Action':
        all_arguments = json.loads(json_data)
        action_type = all_arguments.get("type", None)
        assert isinstance(action_type, str)
        del all_arguments["type"]
        return Action(action_type, **all_arguments)


class Reducer:
    def __init__(self, mapping_dict: dict):
        mapping_dict = mapping_dict or {}
        self._mapping_dict = mapping_dict
        self._state = {}

    async def reduce(self, action: Action) -> Dict[str, Any]:
        changed_state = {}
        state = self._state
        for key, callback in self._mapping_dict.items():
            sub_state = state.get(key, None)
            new_sub_state = await callback(state=sub_state, action=action)
            if id(sub_state) != id(new_sub_state):
                changed_state[key] = new_sub_state
            state[key] = new_sub_state
        self._state = state
        return changed_state

    def get_state(self):
        return self._state


class StoreWrapper:
    def __init__(self, uri: str, socket: websockets.WebSocketClientProtocol):
        self._get_state_queue = []
        self._uri = uri
        self._connection = socket
        self._state = {}
        self._observer_list = set([])
        asyncio.ensure_future(self._reader(), loop=asyncio.get_event_loop())

    @staticmethod
    async def create(uri: str):
        socket = await websockets.connect(uri)
        return StoreWrapper(uri, socket)

    async def close(self):
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _reader(self):
        async for message in self._connection:
            state = json.loads(message)
            self._state = state
            for listener in self._observer_list:
                asyncio.ensure_future(listener.on_changed(), loop=asyncio.get_event_loop())

    async def dispatch(self, action: Union[Dict[str, Any], Action]):
        action_json = action
        if isinstance(action, Action):
            action_json = action.to_json()
        else:
            action_json = json.dumps(action_json)
        assert isinstance(action_json, str)
        await self._connection.send(action_json)

    def get_state(self):
        return self._state

    def subscribe(self, listener: Listener):
        self._observer_list.add(listener)

    def unsubscribe(self, listener: Listener):
        if listener in self._observer_list:
            self._observer_list.remove(listener)


class Store:
    def __init__(self, host: str, port: int, reducer: Reducer):
        assert reducer
        self._reducer = reducer
        asyncio.get_event_loop().run_until_complete(websockets.serve(self._pre_dispatch, host, port))

    @no_type_check
    async def _pre_dispatch(self, ws, path):
        await ws.send(json.dumps(self.get_state()))
        async for message in ws:
            action = Action.from_json(message)
            await self.dispatch(ws, action)

    async def dispatch(self, ws: websockets.WebSocketServerProtocol, action: Action):
        changed_state = await self._reducer.reduce(action)
        if True:
            try:
                await ws.send(json.dumps(changed_state))
            except websockets.ConnectionClosed:
                pass

    def get_state(self):
        return self._reducer.get_state()
