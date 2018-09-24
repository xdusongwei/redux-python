'''
这里主要提供一些固定的reducer模式
entry模式(一个网络连接根据链接参数只会指定一种reducer的key会话提供服务，所以一个连接不会复用多个reducer)
internalentry模式(会复用物理连接，但是会话id冲突需要指定如何处理，比如踢掉旧的会话，或者禁止新的会话, 反向群推action，避免内部的复杂结构影响使用)
执行者模式(本身无状态)
工作者模式

以及提供一些action辅助
异步等待消息
多路等待消息合并
弱action(一般的Action会触发reducer的创建，弱Action不会要求reducer被创建，没有reducer时忽略消息的处理)
action签名，回溯，防止回环, ttl

以及一些reducer特性
ensure_state
比如持久化reducer
'''

from typing import *
import json
from .recycle_option import *
from .reducer import Reducer
from .action import Action
from .medium import MediumBase


class EntryMedium(MediumBase):
    def __init__(self, manager, socket):
        self.manager = manager
        self.socket = socket

    async def send(self, current_key, key, action: Action):
        await self.manager.send_data(self.socket, action.to_data(json.dumps))


class ReducerNode(Reducer):
    def __init__(self, mapping=None):
        super(ReducerNode, self).__init__(mapping)

    async def send(self, action, medium: Optional[MediumBase], reducer_type: Optional[Type[Reducer]]=None, node_id=None):
        if reducer_type:
            node_id = node_id or ""
            key = f"{reducer_type.key_prefix}{node_id}"
        else:
            key = None
        await super(ReducerNode, self).send(medium, key, action)

    async def response(self, action, medium: Optional[MediumBase], key: Optional[str]=None):
        await super(ReducerNode, self).send(medium, key, action)


class GeneralReducer(ReducerNode):
    def __init__(self, mapping_dict=None, entry_key: Optional[str]=None):
        assert mapping_dict is None or isinstance(mapping_dict, dict)
        mapping_dict = mapping_dict or {}
        super(GeneralReducer, self).__init__(mapping_dict)
        self.entry_key = entry_key


class PublicEntryReducer(ReducerNode):
    def __init__(self, mapping_dict=None, check_session=True):
        assert mapping_dict is None or isinstance(mapping_dict, dict)
        mapping_dict = mapping_dict or {}
        super(PublicEntryReducer, self).__init__(mapping_dict)
        self.check_session = check_session
        self.entry_medium = None

    @staticmethod
    async def find_node_id(key_prefix, path, query):
        raise NotImplementedError

    async def action_received(self, action):
        if isinstance(action.medium, EntryMedium):
            await self.entry_action_received(action)
        else:
            await self.internal_action_received(action)

    async def entry_action_received(self, action):
        return

    async def internal_action_received(self, action):
        return


class InternalEntryReducer(ReducerNode):
    def __init__(self, mapping_dict=None):
        assert mapping_dict is None or isinstance(mapping_dict, dict)
        mapping_dict = mapping_dict or {}
        super(InternalEntryReducer, self).__init__(mapping_dict)
        self.entry_mediums = set()


class ExecutorReducer(ReducerNode):
    def __init__(self, entry_key: Optional[str]=None, realm=None):
        super(ExecutorReducer, self).__init__(dict())
        self.entry_key = entry_key
        self.realm = realm or []


def reducer_behavior(
        key_prefix,
        recycle_option: RecycleOption=NeverRecycleOption(),
        subscribe_types=None,
        unsubscribe_types=None,
        url_pattern=None,
):
    def wrap(cls):
        if not issubclass(cls, Reducer):
            raise TypeError
        setattr(cls, "subscribe_action_set", subscribe_types or set())
        setattr(cls, "unsubscribe_action_set", unsubscribe_types or set())
        setattr(cls, "key_prefix", key_prefix)
        if recycle_option is not None:
            setattr(cls, "recycle_option", recycle_option)
        if issubclass(cls, PublicEntryReducer):
            setattr(cls, "url_pattern", url_pattern)
        return cls
    return wrap


def action_info(action_type):
    def wrap(cls):
        if not issubclass(cls, Action):
            raise TypeError
        if not isinstance(action_type, str):
            raise TypeError
        setattr(cls, "TYPE", action_type)
        return cls
    return wrap
