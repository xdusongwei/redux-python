from typing import *
import traceback
from collections import defaultdict
import asyncio


class Listener:
    def __init__(self, key, store: 'Store'):
        assert key
        assert store
        self.key = key
        self.store = store
        self.is_binding = False
        store.subscribe(key, self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.store:
            self.store.unsubscribe(self)
            self.store = None

    def unsubscribe(self):
        if self.store is not None:
            self.store.unsubscribe(self)
            self.store = None

    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        raise NotImplementedError


class ListenerState:
    def __init__(self, listener: Listener, initialize_full_state=True):
        self.is_synced = not initialize_full_state
        self.listener = listener

    async def call_state_changed(self, changed_state, state):
        if self.is_synced:
            await self.listener.on_changed(list(changed_state.keys()), state)
        else:
            self.is_synced = True
            await self.listener.on_changed(list(state.keys()), state)


class Action:
    def __init__(self, action_type: str, **kwargs):
        self.type = action_type
        self.arguments = kwargs or {}
        assert isinstance(self.type, str)
        assert isinstance(self.arguments, dict)

    def to_data(self, dumps):
        action_dict = dict(type=self.type, **self.arguments)
        return dumps(action_dict)

    @staticmethod
    def from_data(data, loads) -> 'Action':
        all_arguments = loads(data)
        action_type = all_arguments.get("type", None)
        assert isinstance(action_type, str)
        del all_arguments["type"]
        return Action(action_type, **all_arguments)

    def __repr__(self):
        return "<Action: {}>".format(self.type)


class Reducer:
    def __init__(self, mapping_dict: dict):
        mapping_dict = mapping_dict or {}
        self._mapping_dict = mapping_dict
        self._state = {}

    async def initialize_state(self, cell_key):
        self._state = {}
        return True

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


class Store:
    def __init__(self, reducer: Type, init_full_state=True):
        assert reducer
        self._reducer = reducer
        self._reducer_set = dict()
        self._observer_list = defaultdict(dict)
        self._initialize_full_state = init_full_state

    def __getitem__(self, item) -> Optional[Dict[str, Any]]:
        if type(item) is not str:
            raise TypeError
        reducer_cell = self._reducer_set.get(item, None)
        if reducer_cell is None:
            return None
        return reducer_cell.get_state()

    async def dispatch(self, key: str, action: Action) -> bool:
        try:
            if key is None:
                return False
            if key not in self._reducer_set:
                reducer = self._reducer()
                if not await reducer.initialize_state(key):
                    return False
                self._reducer_set[key] = reducer
            else:
                reducer = self._reducer_set[key]
            await self._dispatch_work(reducer, key, action)
        except Exception as e:
            traceback.print_exc()
            return False
        return True

    async def _dispatch_work(self, reducer: Reducer, key: str, action: Action):
        changed_state = await reducer.reduce(action)
        if changed_state:
            await self._call_listeners(key, changed_state, self[key])

    async def _call_listeners(self, key: str, changed_state: Dict[str, Any], state: Dict[str, Any]):
        listeners = self._observer_list.get(key, dict()).values()
        for listener in list(listeners):
            try:
                await listener.call_state_changed(changed_state, state)
            except Exception:
                self.unsubscribe(key, listener.listener)

    def subscribe(self, key: str, listener: Listener):
        listener_wrapper = ListenerState(listener, self._initialize_full_state)
        self._observer_list[key].setdefault(listener, listener_wrapper)
        listener.is_binding = True
        state = self[key]
        if state:
            asyncio.ensure_future(listener_wrapper.call_state_changed(state, state))

    def unsubscribe(self, key: str, listener: Listener):
        if listener not in self._observer_list[key]:
            return
        del self._observer_list[key][listener]
        listener.is_binding = False
        if not len(self._observer_list[key]):
            del self._observer_list[key]
            if key in self._reducer_set:
                del self._reducer_set[key]
