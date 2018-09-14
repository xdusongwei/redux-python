from typing import *
import json
import asyncio
import msgpack
import websockets
import urllib.parse
from collections import defaultdict
from .base import MediumBase
from ..typing import *
from ..error import *
from ..option import Option
from ..action import Action
from ..listener import Listener
from ..store import Store
from ..design import PublicEntryReducer


class EntryMedium(MediumBase):
    def __init__(self, manager, socket):
        self.manager = manager
        self.socket = socket

    async def send(self, current_key: KEY, key: KEY, action: Action):
        await self.manager.send_data(self.socket, action.to_data(json.dumps))


def singleton(cls, *args, **kw):
    instances = {}

    def _singleton():
        if cls not in instances:
            instances[cls] = cls(*args, **kw)
        return instances[cls]
    return _singleton


class ConnectionDetail:
    def __init__(self):
        self.is_connected = False
        self.socket = None
        self.dumps = msgpack.dumps
        self.loads = lambda binary: msgpack.loads(binary, encoding="utf8")
        # client side
        self.is_client = False
        self.url = None
        self.subscribe_keys = []
        self.state_pick_dict: Dict[KEY, asyncio.Future] = dict()
        self.state_sub_dict: Dict[KEY, Dict[KEY, asyncio.Future]] = defaultdict(dict)
        self.state_sub_set: Dict[KEY, Set[KEY]] = defaultdict(set)
        # server side
        self.is_server = False
        self.listeners = []

    def __repr__(self):
        if self.is_server:
            return f"<ConnectionDetail: Server({self.socket})>"
        elif self.is_client:
            return f"<ConnectionDetail: Client({self.url})>"
        else:
            return f"<ConnectionDetail: Unknown({self.socket})>"


class EntryListener(Listener):
    def __init__(self, manager: 'RemoteManager', socket):
        super(EntryListener, self).__init__()
        self.manager = manager
        self.socket = socket

    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        await self.manager.send_data(self.socket, json.dumps({}))


@singleton
class RemoteManager:
    RECONNECT_TIMEOUT = 1.0

    def __init__(self):
        self.client_connections: Dict[KEY, ConnectionDetail] = dict()
        self.server_connections: Dict[KEY, ConnectionDetail] = dict()
        self.client_url = set()
        self.entry_reducer = set()

    async def serve(self, host, port, store: Store, **kwargs) -> Option:
        try:
            coro = lambda websocket, path: self.on_new_connection(websocket, path, store)
            server = await websockets.serve(coro, host, port, **kwargs)
            return Option(server)
        except Exception as e:
            return Option(e)

    async def serve_entry(self, host, port, store: Store, reducer_list: List[Type], **kwargs):
        try:
            for reducer_type in reducer_list:
                store.insert_reducer_type(reducer_type)
            coro = lambda websocket, path: self.on_new_entry(websocket, path, store, reducer_list)
            server = await websockets.serve(coro, host, port, **kwargs)
            return Option(server)
        except Exception as e:
            return Option(e)

    async def stop_serve(self, server: websockets.server.WebSocketServer, clear_connections=True) -> Option:
        try:
            if clear_connections:
                server.close()
            else:
                server.server.close()
            return Option.none()
        except Exception as e:
            return Option(e)

    async def client(self, url, store) -> Option:
        if url not in self.client_url:
            return Option(KeyError())
        if url in self.client_connections:
            return Option(self.client_connections[url])
        socket_opt = await self.connect(url)
        if socket_opt.is_error:
            return socket_opt
        websocket = socket_opt.unwrap()
        detail = ConnectionDetail()
        detail.is_connected = True
        detail.socket = websocket
        detail.is_client = True
        detail.url = url
        self.client_url.add(url)
        self.client_connections[url] = detail
        asyncio.ensure_future(self.on_client_connected(detail, store))
        return Option(detail)

    async def on_new_entry(self, websocket, path, store: Store, reducer_list: List[Type]):
        unsubscribe = None
        medium = EntryMedium(self, websocket)
        try:
            url_info = urllib.parse.urlparse(path)
            arguments = dict(urllib.parse.parse_qsl(url_info.query))
            key = None
            for reducer in reducer_list:
                if not issubclass(reducer, PublicEntryReducer):
                    continue
                node_id = await reducer.find_node_id(reducer.key_prefix, url_info.path, arguments)
                if node_id is not None:
                    reducer_type = reducer
                    key = f"{reducer_type.key_prefix}{node_id}"
                    break
            if key is None:
                raise NoneError
            listener = EntryListener(self, websocket)
            unsubscribe_opt = await store.subscribe(key, listener)
            if unsubscribe_opt.is_none:
                raise KeyError
            unsubscribe = unsubscribe_opt.unwrap()
            reducer: PublicEntryReducer = (await store.get_or_create_cell(key)).unwrap()
            reducer.entry_medium = medium
        except Exception as e:
            if unsubscribe:
                unsubscribe()
            return
        while True:
            binary_opt = await self.read_data(websocket)
            if binary_opt.is_error:
                break
            action = Action.from_data(binary_opt.unwrap(), json.loads)
            action.medium = medium
            asyncio.ensure_future(store.dispatch(key, action))
        unsubscribe()

    async def on_new_connection(self, websocket, path, store: Store):
        detail = ConnectionDetail()
        detail.is_connected = True
        detail.socket = websocket
        detail.is_server = True
        connection_name = "@ws://{}:{}".format(*websocket.remote_address)
        self.server_connections[connection_name] = detail
        while True:
            read_data = self.read_data
            data_opt = await read_data(websocket)
            if data_opt.is_error:
                break
            binary = data_opt.unwrap()
            try:
                info = detail.loads(binary)
            except Exception as e:
                break
            if type(info) is not dict or "__t__" not in info:
                break
            message_type = info.pop("__t__")
            if "__k__" not in info:
                break
            if message_type == "ACTION":
                target_key, action = MediumBase.from_message(RemoteMedium(connection_name, websocket), info).unwrap()
                asyncio.ensure_future(store.dispatch(target_key, action))
            elif message_type == "SUBSCRIBE":
                pass
            elif message_type == "UNSUBSCRIBE":
                pass
            elif message_type == "STATE":
                pass
            elif message_type == "PICKACK":
                message_opt = MediumBase.from_pick_ack_message(info)
                target_key, state = message_opt.unwrap()
                if target_key in detail.state_pick_dict:
                    if state is None:
                        detail.state_pick_dict[target_key].set_result(NoneError())
                    else:
                        detail.state_pick_dict[target_key].set_result(state)
            elif message_type == "PICK":
                source_key, target_key, fields = MediumBase.from_pick_message(info).unwrap()
                state = store[target_key]
                state = MediumBase.state_filter(state, fields)
                message = MediumBase.to_pick_ack_message(source_key, state).unwrap()
                binary = detail.dumps(message)
                send_opt = await self.send_data(websocket, binary)
                if send_opt.is_error:
                    break
        detail.is_connected = False
        del self.server_connections[connection_name]
        try:
            await websocket.close()
        finally:
            pass

    async def on_client_connected(self, detail: ConnectionDetail, store: Store):
        while True:
            read_data = self.read_data
            data_opt = await read_data(detail.socket)
            if data_opt.is_error:
                if type(data_opt.error) is asyncio.CancelledError:
                    return
                else:
                    break
            binary = data_opt.unwrap()
            try:
                info = detail.loads(binary)
            except Exception as e:
                break
            if not isinstance(info, dict) or "__t__" not in info:
                break
            message_type = info.pop("__t__")
            if "__k__" not in info:
                break
            if message_type == "ACTION":
                message_opt = MediumBase.from_message(RemoteMedium(detail.url, detail.socket), info)
                target_key, action = message_opt.unwrap()
                asyncio.ensure_future(store.dispatch(target_key, action))
            elif message_type == "UNSUBSCRIBE":
                pass
            elif message_type == "STATE":
                pass
            elif message_type == "PICKACK":
                message_opt = MediumBase.from_pick_ack_message(info)
                target_key, state = message_opt.unwrap()
                if target_key in detail.state_pick_dict:
                    if state is None:
                        detail.state_pick_dict[target_key].set_result(NoneError())
                    else:
                        detail.state_pick_dict[target_key].set_result(state)
            elif message_type == "PICK":
                source_key, target_key, fields = MediumBase.from_pick_message(info).unwrap()
                state = store[target_key]
                state = MediumBase.state_filter(state, fields)
                message = MediumBase.to_pick_ack_message(source_key, state).unwrap()
                binary = detail.dumps(message)
                send_opt = await self.send_data(detail.socket, binary)
                if send_opt.is_error:
                    break
        detail.is_connected = False
        try:
            await detail.socket.close()
        finally:
            pass
        await self.client_to_offline(detail, store)

    async def client_to_offline(self, detail: ConnectionDetail, store: Store):
        detail.subscribe_keys.clear()
        asyncio.ensure_future(self.on_client_offline(detail, store))

    async def on_client_offline(self, detail: ConnectionDetail, store: Store):
        url = detail.url
        while True:
            if url not in self.client_url:
                break
            wait_coro = asyncio.sleep(self.RECONNECT_TIMEOUT, Option(TimeoutError()))
            work_coro = self.connect(url, self.RECONNECT_TIMEOUT)
            fs = [wait_coro, work_coro]
            done, pending = await asyncio.wait(fs, return_when=asyncio.FIRST_COMPLETED)
            socket_opt = done.pop().result()
            if not socket_opt.is_error:
                detail.is_connected = True
                websocket = socket_opt.unwrap()
                detail.socket = websocket
                asyncio.ensure_future(self.on_client_connected(detail, store))
                break
            await asyncio.wait(fs, return_when=asyncio.ALL_COMPLETED)

    async def connect(self, url, timeout=1.0):
        try:
            websocket = await websockets.connect(url, timeout=timeout)
            return Option(websocket)
        except Exception as e:
            return Option(e)

    async def read_data(self, websocket) -> Option:
        try:
            data = await websocket.recv()
            return Option(data)
        except Exception as e:
            return Option(e)

    async def send_data(self, websocket, data) -> Option:
        try:
            await websocket.send(data)
            return Option.none()
        except Exception as e:
            return Option(e)


class RemoteMedium(MediumBase):
    def __init__(self, url, websocket):
        self.url = url
        self.websocket = websocket

    @staticmethod
    async def connect(store, url: str):
        manager = RemoteManager()
        if type(url) is not KEY:
            return Option(TypeError())
        socket_opt = await manager.client(url, store)
        if socket_opt.is_error:
            return Option(socket_opt.error)
        elif socket_opt.is_none:
            return Option(NoneError())
        return Option(RemoteMedium(url, socket_opt.unwrap().socket))

    async def send(self, current_key: KEY, key: KEY, action: Action) -> Option:
        message = RemoteMedium.to_message(current_key, key, action).unwrap()
        binary = msgpack.dumps(message)
        return await RemoteManager().send_data(self.websocket, binary)

    async def get_state(self, current_key: KEY, key: KEY, fields=None):
        manager = RemoteManager()
        if self.url in manager.client_connections:
            detail = manager.client_connections[self.url]
        elif self.url in manager.server_connections:
            detail = manager.server_connections[self.url]
        else:
            return Option(NoneError())
        message = MediumBase.to_pick_message(current_key, key, fields).unwrap()
        try:
            future = asyncio.Future()
            detail.state_pick_dict[current_key] = future
            binary = msgpack.dumps(message)
            send_opt = await manager.send_data(self.websocket, binary)
            if send_opt.is_error:
                return send_opt
            await asyncio.wait_for(future, 0.1)
            result = future.result()
            return Option(result)
        except Exception as e:
            return Option(e)
        finally:
            if current_key in detail.state_pick_dict:
                del detail.state_pick_dict[current_key]
