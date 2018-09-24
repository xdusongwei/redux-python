from typing import *
import time
import traceback
from collections import defaultdict
from sortedcontainers import SortedSet
import asyncio
from .error import *
from .option import Option
from .action import Action
from .recycle_option import *
from .listener import Listener, ListenerStateWrapper
from .combine_message import CombineMessage, AnyMessage


class Store:
    def __repr__(self):
        return f"<Store Size: {len(self._reducer_set)}>"

    def __init__(self, reducer_list: List[Type]=None, init_full_state=True, cleaner_period=1.0):
        self._reducer_list = set(reducer_list or [])
        self._reducer_set = dict()
        self._observer_list = defaultdict(dict)
        self._initialize_full_state = init_full_state
        self._idle_set = SortedSet()
        self._idle_cleaner = False
        self.cleaner_period = float(cleaner_period)
        self._initialize_lock = asyncio.Lock()

    def __getitem__(self, item) -> Optional[Dict[str, Any]]:
        if type(item) is not str:
            raise TypeError
        reducer_cell = self._reducer_set.get(item, None)
        if reducer_cell is None:
            return None
        return reducer_cell.get_state()

    def __contains__(self, item):
        return item in self._reducer_set

    def insert_reducer_type(self, reducer: Type):
        self._reducer_list.add(reducer)

    def remove_reducer_type(self, reducer: Type):
        if reducer in self._reducer_list:
            self._reducer_list.remove(reducer)

    def find_reducer_type_by_prefix(self, key) -> Option:
        for reducer in self._reducer_list:
            if reducer.key_prefix is None:
                continue
            if isinstance(reducer.key_prefix, str):
                if key.startswith(reducer.key_prefix):
                    return Option(reducer)
        return Option.none()

    def find_reducer_list_by_type(self, reducer_type: Type) -> List:
        result = []
        for reducer in self._reducer_set.values():
            if type(reducer) == reducer_type:
                result.append(reducer)
        return result

    def set_idle_key(self, reducer):
        if isinstance(reducer.recycle_option, IdleTimeoutRecycleOption):
            key = reducer.recycle_option.create_key(reducer)
            reducer.last_idle_key = key
            self._idle_set.add(key)
            self.try_start_idle_cleaner()

    def remove_idle_key(self, reducer):
        if isinstance(reducer.recycle_option, IdleTimeoutRecycleOption):
            if reducer.last_idle_key in self._idle_set:
                self._idle_set.remove(reducer.last_idle_key)

    def try_start_idle_cleaner(self):
        if not self._idle_cleaner:
            self._idle_cleaner = True
            asyncio.ensure_future(self.idle_cleaner())

    async def get_or_create_cell(self, key, reducer_type: Optional[Type]=None) -> Option:
        if key not in self._reducer_set:
            if reducer_type is None:
                return Option.none()
            reducer = reducer_type()
            try:
                await self._initialize_lock.acquire()
                reducer.store = self
                if not await reducer.initialize(key):
                    return Option.none()
                reducer.enable = True
                self._reducer_set[key] = reducer
            except Exception as e:
                return Option(ReduxError(e, traceback.format_exc()))
            finally:
                self._initialize_lock.release()
        else:
            reducer = self._reducer_set[key]
        return Option(reducer)

    def pop_reducer_by_key(self, key):
        if key not in self._reducer_set:
            return
        reducer = self._reducer_set.pop(key)
        reducer.enable = False
        if reducer.listener_dict:
            for listener in reducer.listener_dict.values():
                listener()
            reducer.listener_dict.clear()
        if reducer.enable_call_shutdown:
            asyncio.ensure_future(reducer.shutdown())
        reducer.get_state().clear()

    def enable_create_reducer(self, reducer_type):
        return True #isinstance(reducer_type.recycle_option, UnsubscribeRecycleOption)

    def enable_set_up_idle_key(self, reducer_type: Type, action):
        option = reducer_type.recycle_option
        return isinstance(option, IdleTimeoutRecycleOption) and option.timeout and not action.soft

    async def dispatch(self, key: str, action: Action) -> bool:
        try:
            if key is None:
                return False
            if key in self:
                reducer = self._reducer_set[key]
            elif action.soft:
                return True
            else:
                reducer_type_opt = self.find_reducer_type_by_prefix(key)
                if reducer_type_opt.is_none:
                    return False
                reducer_type = reducer_type_opt.unwrap()
                if self.enable_create_reducer(reducer_type):
                    reducer_opt = await self.get_or_create_cell(key, reducer_type)
                    reducer = reducer_opt.unwrap() if reducer_opt.is_some else None
                else:
                    return False
            if not reducer:
                return False
            if self.enable_set_up_idle_key(type(reducer), action):
                self.remove_idle_key(reducer)
                self.set_idle_key(reducer)
            if await self._combine_block(reducer, action):
                if action.type in reducer.subscribe_action_set:
                    if not reducer.enable_call_subscribe:
                        pass # something wrong
                    else:
                        listener_opt = await reducer.enable_subscribe(action)
                        if listener_opt.is_some:
                            await self.subscribe(key, listener_opt.unwrap())
                elif action.type in reducer.unsubscribe_action_set:
                    if not reducer.enable_call_unsubscribe:
                        pass
                    else:
                        listener_opt = await reducer.enable_unsubscribe(action)
                        if listener_opt.is_some:
                            self.unsubscribe(key, listener_opt.unwrap())
                else:
                    await self._dispatch(reducer, action)
            if reducer.is_new and isinstance(reducer.recycle_option, IdleTimeoutRecycleOption) and not reducer.recycle_option.timeout:
                self.pop_reducer_by_key(key)
            reducer.is_new = False
        except Exception as e:
            traceback.print_exc()
            return False
        return True

    async def _combine_block(self, reducer, action):
        action_type = action.type
        for cb in list(reducer.combine_message_list):
            combine_message: CombineMessage = cb
            if action_type in combine_message.message_type_list:
                if isinstance(combine_message, AnyMessage):
                    reducer.combine_message_list.remove(combine_message)
                    combine_message.future.set_result(True)
                else:
                    combine_message.message_type_list.remove(action_type)
                    if not combine_message.message_type_list and not combine_message.future.done():
                        reducer.combine_message_list.remove(combine_message)
                        combine_message.future.set_result(True)
                return combine_message.keep_origin
        return True

    async def _dispatch(self, reducer, action: Action):
        try:
            key = reducer.key
            await reducer.locker.acquire()
            changed_state = await reducer.reduce(action)
        except Exception as e:
            raise e
        finally:
            reducer.locker.release()
        if changed_state:
            await self._call_listeners(key, changed_state, self[key])

    async def _call_listeners(self, key: str, changed_state: Dict[str, Any], state: Dict[str, Any]):
        listeners = self._observer_list.get(key, dict()).values()
        for listener in list(listeners):
            try:
                await listener.call_state_changed(changed_state, state)
            except Exception:
                self.unsubscribe(key, listener.listener)

    async def subscribe(self, key: str, listener: Listener) -> Option:
        reducer_type_opt = self.find_reducer_type_by_prefix(key)
        if reducer_type_opt.is_none:
            return Option.none()
        reducer_type = reducer_type_opt.unwrap()
        listener_wrapper = ListenerStateWrapper(listener, self._initialize_full_state)
        self._observer_list[key].setdefault(listener, listener_wrapper)
        listener.is_binding = True
        listener.store = self
        listener.key = key
        call_no_op = key not in self
        reducer_opt = await self.get_or_create_cell(key, reducer_type)
        if not reducer_opt.is_some:
            return Option.none()
        reducer = reducer_opt.unwrap()
        self.remove_idle_key(reducer)
        if call_no_op:
            await self._dispatch(reducer, Action.no_op_command())
            reducer.is_new = False
        state = self[key]
        if state:
            await listener_wrapper.call_state_changed(state, state)

        def unsubscribe():
            self.unsubscribe(key, listener)

        return Option(unsubscribe)

    def unsubscribe(self, key: str, listener: Listener):
        if listener not in self._observer_list[key]:
            return
        del self._observer_list[key][listener]
        listener.is_binding = False
        listener.store = None
        listener.key = None
        if not len(self._observer_list[key]):
            del self._observer_list[key]
            option = self._reducer_set[key].recycle_option
            if isinstance(option, IdleTimeoutRecycleOption) and option.timeout:
                self.set_idle_key(self._reducer_set[key])
            else:
                self.pop_reducer_by_key(key)

    async def idle_cleaner(self):
        period = self.cleaner_period
        if not self._idle_set:
            asyncio.get_event_loop().call_later(period, lambda: asyncio.ensure_future(self.idle_cleaner()))
            return
        timestamp, reducer = self._idle_set[0]
        now_timestamp = time.time()
        if now_timestamp < timestamp:
            sleep_time = max(period, timestamp - now_timestamp)
            asyncio.get_event_loop().call_later(sleep_time, lambda: asyncio.ensure_future(self.idle_cleaner()))
            return
        while self._idle_set:
            timestamp, reducer = self._idle_set.pop(0)
            now_timestamp = time.time()
            if now_timestamp >= timestamp:
                self.pop_reducer_by_key(reducer.key)
            else:
                break
        asyncio.get_event_loop().call_soon(lambda: asyncio.ensure_future(self.idle_cleaner()))
