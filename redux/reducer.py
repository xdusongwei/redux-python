from typing import *
from .typing import *
import asyncio
from .error import *
from .option import Option
from .recycle_option import *
from .medium import MediumBase
from .combine_message import CombineMessage, AnyMessage


'''class ReducerDetail:
    def __init__(self):
        self.locker = asyncio.Lock()
        self.last_idle_key = None
        self.is_new = True
        self.subscribe_set = set()
        self.listener_dict = set()'''


class Reducer:
    key_prefix = r"noname:"
    recycle_option = NeverRecycleOption()
    subscribe_action_set = set()

    def __repr__(self):
        return "<Reducer: {}>".format(self.key)

    def __hash__(self):
        return hash(self.key)

    def __init__(self, mapping_dict: dict=None):
        mapping_dict = mapping_dict or {}
        self.mapping_dict = mapping_dict
        self._state = {}
        self._store = None
        self.key = None
        self.node_id = None
        self.locker = asyncio.Lock()
        self.enable = False
        self.last_idle_key = None
        self.is_new = True
        if self.action_received.__code__ is Reducer.action_received.__code__:
            self.enable_call_action_received = False
        else:
            self.enable_call_action_received = True
        if self.reduce_finish.__code__ is Reducer.reduce_finish.__code__:
            self.enable_call_reduce_finish = False
        else:
            self.enable_call_reduce_finish = True
        if self.shutdown.__code__ is Reducer.shutdown.__code__:
            self.enable_call_shutdown = False
        else:
            self.enable_call_shutdown = True
        if self.enable_subscribe.__code__ is Reducer.enable_subscribe.__code__:
            self.enable_call_subscribe = False
        else:
            self.enable_call_subscribe = True
        if self.enable_unsubscribe.__code__ is Reducer.enable_unsubscribe.__code__:
            self.enable_call_unsubscribe = False
        else:
            self.enable_call_unsubscribe = True
        self.subscribe_set = set()
        self.unsubscribe_set = set()
        self.listener_dict = dict()
        self.combine_message_list = []

    async def initialize(self, key: KEY):
        self.key = key
        if key == self.key_prefix:
            self.node_id = None
        else:
            self.node_id = key.replace(self.key_prefix, "", 1)
        return True

    async def action_received(self, action):
        raise NotImplementedError

    async def reduce(self, action) -> Dict[KEY, Any]:
        if self.enable_call_action_received:
            await self.action_received(action)
        changed_state = {}
        state = self._state.copy()
        for key, callback in self.mapping_dict.items():
            if key.startswith("_"):
                continue
            sub_state = state.get(key, None)
            new_sub_state = await callback(state=sub_state, action=action)
            if id(sub_state) != id(new_sub_state):
                changed_state[key] = new_sub_state
            state[key] = new_sub_state
        self._state = state
        if self.enable_call_reduce_finish:
            await self.reduce_finish(action, changed_state)
        return changed_state

    async def reduce_finish(self, action, changed_state: Dict[KEY, Any]):
        raise NotImplementedError

    async def shutdown(self):
        return Option.none()

    def get_state(self):
        return self._state

    async def get_remote_state(self, source: MediumBase, key: KEY, fields=None) -> Option:
        if source is None:
            return Option.none()
        if not isinstance(source, MediumBase):
            return Option(TypeError())
        return await source.get_state(self.key, key, fields)

    async def send(self, medium: Optional[MediumBase], key, action) -> Option:
        if medium is None:
            return Option(NoneError())
        if not isinstance(medium, MediumBase):
            return Option(TypeError())
        return await medium.send(self.key, key, action)

    async def enable_subscribe(self, action) -> Option:
        raise NotImplementedError

    async def enable_unsubscribe(self, action) -> Option:
        raise NotImplementedError

    async def subscribe(self, medium: Optional[MediumBase], key: KEY) -> Option:
        pass

    async def unsubscribe(self, medium: Optional[MediumBase], key: KEY) -> Option:
        pass

    async def unsubscribe_all(self):
        pass

    @property
    def current(self) -> Dict[str, Callable]:
        return self.mapping_dict

    def replace_reducer(self, v: Dict[str, Callable]):
        self.mapping_dict = v

    @property
    def store(self):
        return self._store

    @store.setter
    def store(self, v):
        self._store = v

    def ensure_state(self):
        pass

    def combine_message(self, message_type_list: Union[KEY, List[KEY]], combine_message, timeout_message, timeout=1.0,
                        keep_origin=False):
        if not message_type_list:
            return
        cb = CombineMessage()
        cb.message_type_list = message_type_list if isinstance(message_type_list, list) else [message_type_list]
        cb.combine_message = combine_message
        cb.timeout_message = timeout_message
        cb.timeout = timeout
        cb.keep_origin = keep_origin
        cb.node_key = self.key
        cb.store = self.store
        self.combine_message_list.append(cb)
        cb.active()

    def any_message(self, message_type_list: Union[KEY, List[KEY]], timeout_message, timeout=1.0):
        if not message_type_list:
            return
        cb = AnyMessage()
        cb.message_type_list = message_type_list if isinstance(message_type_list, list) else [message_type_list]
        cb.timeout_message = timeout_message
        cb.timeout = timeout
        cb.node_key = self.key
        cb.store = self.store
        self.combine_message_list.append(cb)
        cb.active()


__all__ = ["Reducer", ]
