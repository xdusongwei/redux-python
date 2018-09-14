from typing import *
import asyncio
from .base import MediumBase
from ..typing import *
from ..option import Option
from ..error import *
from ..action import Action
from ..listener import Listener
from ..store import Store


class LocalMediumListener(Listener):
    def __init__(self, reducer, listener_reducer, listener):
        super(LocalMediumListener, self).__init__()
        self.reducer = reducer
        self.listener_reducer = listener_reducer
        self.reducer_listener = listener
    
    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        if self.reducer_listener:
            await self.reducer_listener.on_changed(changed_key, state)


class LocalMedium(MediumBase):
    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    async def connect(store):
        return LocalMedium(store)

    async def send(self, current_key: KEY, key: KEY, action: Action) -> Option:
        if current_key == key:
            return Option(SameKeyError())
        message = LocalMedium.to_message(current_key, key, action).unwrap()
        source = LocalMedium(self.store)
        target_key, action = LocalMedium.from_message(source, message).unwrap()
        asyncio.ensure_future(self.store.dispatch(target_key, action))
        return Option.none()

    async def get_state(self, current_key: KEY, key: KEY, fields=None) -> Option:
        if current_key == key:
            return Option(SameKeyError())
        state = self.store[key]
        state = MediumBase.state_filter(state, fields)
        if state is None:
            return Option(NoneError())
        else:
            return Option(state)

    async def subscribe(self, current_key: KEY, key: KEY, listener: Listener) -> Option:
        subscribe_key = ("Local", current_key)
        listener_key = ("Local", key)
        reducer_opt = await self.store.get_or_create_cell(key, None)
        listener_reducer_opt = await self.store.get_or_create_cell(current_key, None)
        if listener_reducer_opt.is_none:
            return Option(KeyError())
        if reducer_opt.is_none:
            return Option(KeyError())
        reducer = reducer_opt.unwrap()
        listener_reducer = listener_reducer_opt.unwrap()
        if subscribe_key in reducer.subscribe_set:
            return Option(KeyError())
        listener_opt = await self.store.subscribe(key, LocalMediumListener(reducer, listener_reducer, listener))
        if listener_opt.is_none:
            return Option(KeyError())
        reducer.subscribe_set.add(subscribe_key)
        listener_reducer.listener_dict[listener_key] = listener_opt.unwrap()

    async def unsubscribe(self, current_key: KEY, key: KEY) -> Option:
        subscribe_key = ("Local", current_key)
        listener_key = ("Local", key)
        reducer_opt = await self.store.get_or_create_cell(key, None)
        listener_reducer_opt = await self.store.get_or_create_cell(current_key, None)
        if listener_reducer_opt.is_none:
            return Option(KeyError())
        if reducer_opt.is_none:
            return Option(KeyError())
        reducer = reducer_opt.unwrap()
        listener_reducer = listener_reducer_opt.unwrap()
        if subscribe_key not in reducer.subscribe_set:
            return Option(KeyError())
        del reducer.subscribe_set[subscribe_key]
        if listener_key in listener_reducer.listener_dict:
            listener = listener_reducer.listener_dict.pop(listener_key)
            listener()
