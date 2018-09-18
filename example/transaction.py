from typing import *
import re
import json
import asyncio
import redux
import random
import websockets


'''
示例: 用户转账

这个示例通过 ExecutorReducer 节点这种无状态的结构处理 InternalEntryReducer 内部服务较复杂的逻辑, 以及使用弱 Action 避免创建 GeneralReducer.
为了避免内部节点关系太复杂, 通常工作内容相同的 GeneralReducer 之间是不能互相访问的,
对于一些场景, 相关联的 GeneralReducer 节点的状态需要同时被更新, 
此时需要将关联逻辑放在 ExecutorReducer 节点处理, 并通知各 GeneralReducer 完成状态更新.
这里特别注意的是, 在这个场景中, 
ExecutorReducer 不一定要激活 GeneralReducer 使其存在(例如被转账的 Bob, 如果 Bob 未登录, 没有必要激活 Bob 的 GeneralReducer 节点去处理 Action),
强制激活可能造成不期望的结果(如果此时强制让 Bob 用户的节点激活, 并在此时 initialize 方法加载了此时正确的 equity 数据, 
再去处理 INCREASE_EQUITY Action, 会重复计算他的 equity),
以及可能不必要的开销, 比如系统会对没有登录过的 Bob 创建了用户对应的 GeneralReducer 和 InternalEntryReducer 节点,
所以 ExecutorReducer 节点向 GeneralReducer 节点发送弱 Action, 不要求 GeneralReducer 节点存在并处理 Action,
同理 GeneralReducer 节点也向 InternalEntryReducer 节点发送弱 Action

这个示例的 Reducer 连接结构如下:

--------------------       ----------------------       ------------------------     -------------------
| websocket client | <---> | PublicEntryReducer | <---> | InternalEntryReducer | --> | ExecutorReducer |
--------------------       ----------------------       ------------------------     -------------------
                                                                    ↑                          │
                                                                    │                          │  
                                                                    │                          ↓
                                                                    │                 ------------------
                                                                    └──────────────── | GeneralReducer |
                                                                                      ------------------

'''

DATABASE = {
    "Alice": dict(equity=100),
    "Bob": dict(equity=10),
}


@redux.behavior("entry:public:", redux.SubscribeRecycleOption(), url_pattern=r"/events")
class PublicService(redux.PublicEntryReducer):
    @staticmethod
    async def find_node_id(key_prefix, path, query):
        return f"{str(int(random.uniform(0, 10000))).zfill(4)}"

    async def action_received(self, action: redux.Action):
        if action == "__NO_OP":
            return
        print("PublicService received", self.key, action)
        if isinstance(action.medium, redux.EntryMedium):
            if action == "SUBSCRIBE":
                user = action.arguments["user"]
                await self.send(action, redux.LocalMedium(self.store), UserService, user)
            if action == "TRANSFER":
                user = action.arguments["user"]
                await self.send(action, redux.LocalMedium(self.store), UserService, user)
        if isinstance(action.medium, redux.LocalMedium):
            await self.response(action, self.entry_medium)


@redux.behavior("entry:user:", redux.IdleTimeoutRecycleOption(3))
class UserService(redux.InternalEntryReducer):
    def __init__(self):
        super(UserService, self).__init__()
        self.login_list = []

    @property
    def login_list(self) -> List[redux.Action]:
        return self.get_state().get("_login_list", [])

    @login_list.setter
    def login_list(self, v):
        self.get_state()["_login_list"] = v

    async def action_received(self, action: redux.Action):
        if action == "SUBSCRIBE":
            login_list = self.login_list
            login_list.append(action)
            self.login_list = login_list
            user = action.arguments["user"]
        if action == "TRANSFER":
            await self.send(action, redux.LocalMedium(self.store), TransactionNode)
        if action in ["EQUITY_CHANGED", "NOT_ENOUGH_EQUITY"]:
            for session in self.login_list:
                await self.response(action, session.medium, session.source_key)


@redux.behavior("node:transfer", redux.NeverRecycleOption())
class TransactionNode(redux.ExecutorReducer):
    async def action_received(self, action: redux.Action):
        if action == "TRANSFER":
            from_user = action.arguments["from"]
            to_user = action.arguments["to"]
            change = action.arguments["change"]
            await self.send(redux.Action.no_op_command(), redux.LocalMedium(self.store), UserNode, from_user)
            result = await self.modify_database(from_user, to_user, change)
            medium = redux.LocalMedium(self.store)
            if result:
                await self.send(redux.Action("INCREASE_EQUITY", change=-change), medium, UserNode, from_user)
                await self.send(redux.Action("INCREASE_EQUITY", soft=True, change=change), medium, UserNode, to_user)
            else:
                await self.send(redux.Action("NOT_ENOUGH_EQUITY"), medium, UserNode, from_user)

    async def modify_database(self, from_user, to_user, change):
        global DATABASE
        if DATABASE[from_user]["equity"] >= change:
            DATABASE[from_user]["equity"] -= change
            DATABASE[to_user]["equity"] += change
            return True
        return False


@redux.behavior("node:user:", redux.IdleTimeoutRecycleOption(3))
class UserNode(redux.GeneralReducer):
    def __init__(self):
        mapping = {
            "equity": self.equity,
        }
        super(UserNode, self).__init__(mapping)

    async def initialize(self, key):
        print("create node", key)
        if not await super(UserNode, self).initialize(key):
            return False
        equity = await self.query_database()
        if equity is None:
            return False
        self.get_state()["equity"] = equity
        return True

    async def query_database(self):
        global DATABASE
        return DATABASE[self.node_id]["equity"]

    async def equity(self, action: redux.Action, state=0):
        if action == "INCREASE_EQUITY":
            state += action.arguments["change"]
        return state

    async def reduce_finish(self, action: redux.Action, changed_state: Dict[str, Any]):
        if action == "INCREASE_EQUITY":
            equity = self.get_state()["equity"]
            action = redux.Action("EQUITY_CHANGED", equity=equity)
            await self.send(action, redux.LocalMedium(self.store), UserService, self.node_id)
        if action == "NOT_ENOUGH_EQUITY":
            key = f"entry:user:{self.node_id}"
            action = redux.Action("NOT_ENOUGH_EQUITY")
            await self.send(action, redux.LocalMedium(self.store), UserService, self.node_id)


async def work():
    store = redux.Store([PublicService, UserService, TransactionNode, UserNode])
    server_opt = await redux.RemoteManager().serve_entry("127.0.0.1", 9966, store, [PublicService])
    server = server_opt.unwrap()

    alice_socket = await websockets.connect("ws://127.0.0.1:9966/events")
    subscribe_action = {
        "type": "SUBSCRIBE",
        "user": "Alice",
    }
    await alice_socket.send(json.dumps(subscribe_action))

    transfer_action = {
        "type": "TRANSFER",
        "user": "Alice",
        "from": "Alice",
        "to": "Bob",
        "change": 10
    }
    await alice_socket.send(json.dumps(transfer_action))
    await asyncio.sleep(0.1)

    transfer_action = {
        "type": "TRANSFER",
        "user": "Alice",
        "from": "Alice",
        "to": "Bob",
        "change": 1000
    }
    await alice_socket.send(json.dumps(transfer_action))
    await asyncio.sleep(0.1)


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(work())
