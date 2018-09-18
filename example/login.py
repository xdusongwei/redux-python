from typing import *
import asyncio
import re
import redux
import json
import websockets


'''
示例: 用户登录

这个示例通过两种 Reducer 节点完成了一个复合的任务, 在 PublicEntryReducer 中完成 Action 的分发, 
主要的功能逻辑放在了 ExecutorReducer (一种自身没有状态的特殊 Reducer)进行处理.
ExecutorReducer 处理完 VERIFY_LOGIN Action 之后, 可以通过 Action 中的媒介(medium) 来回应处理结果给 PublicEntryReducer,
告知 PublicEntryReducer 节点 ACCESS_LOGIN 或者 DENIED_LOGIN 两种 Action 结果

这个示例的 Reducer 连接结构如下:

--------------------       ----------------------       -------------------
| websocket client | <---> | PublicEntryReducer | <---> | ExecutorReducer |
--------------------       ----------------------       -------------------

'''


@redux.behavior(r"entry:session:", redux.SubscribeRecycleOption(), url_pattern=r"/login/entry/(.+)")
class LoginReducer(redux.PublicEntryReducer):
    def __init__(self):
        mapping = {
            "is_login": self.is_login,
            "user_name": self.user_name,
        }
        super(LoginReducer, self).__init__(mapping)

    async def is_login(self, action: redux.Action, state=False):
        if isinstance(action.medium, redux.LocalMedium):
            if action == "ACCESS_LOGIN":
                state = True
            if action == "DENIED_LOGIN":
                state = False
        return state

    async def user_name(self, action: redux.Action, state=None):
        if isinstance(action.medium, redux.LocalMedium):
            if action == "ACCESS_LOGIN":
                state = action.arguments["user_name"]
            if action == "DENIED_LOGIN":
                state = None
        return state

    @staticmethod
    async def find_node_id(key_prefix, path, query):
        groups = re.match(LoginReducer.url_pattern, path).groups()
        if groups:
            return groups[0]
        return None

    async def action_received(self, action: redux.Action):
        if isinstance(action.medium, redux.EntryMedium):
            if action == "LOGIN":
                user_name = action.arguments["userName"]
                password = action.arguments["password"]
                action = redux.Action("VERIFY_LOGIN", user_name=user_name, password=password)
                await self.send(action, redux.LocalMedium(self.store), LoginVerify, user_name)
        if isinstance(action.medium, redux.LocalMedium):
            if action == "ACCESS_LOGIN":
                print(f"ACCESS_LOGIN {action.arguments['user_name']}")
            if action == "DENIED_LOGIN":
                print(f"DENIED_LOGIN {action.arguments['user_name']}")

    async def reduce_finish(self, action: redux.Action, changed_state: Dict[str, Any]):
        print(f"{action} state: {self.get_state()}")


@redux.behavior(r"service:login:", redux.NeverRecycleOption())
class LoginVerify(redux.ExecutorReducer):
    async def action_received(self, action: redux.Action):
        if action == "VERIFY_LOGIN":
            user_name = action.arguments["user_name"]
            password = action.arguments["password"]
            if user_name == "kenny" and password == "123456":
                if action.medium:
                    resp_action = redux.Action("ACCESS_LOGIN", user_name=user_name)
                    await self.response(resp_action, action.medium, action.source_key)
            else:
                if action.medium:
                    resp_action = redux.Action("DENIED_LOGIN", user_name=user_name)
                    await self.response(resp_action, action.medium, action.source_key, )


async def work():
    store = redux.Store()
    store.insert_reducer_type(LoginVerify)
    server_opt = await redux.RemoteManager().serve_entry("127.0.0.1", 9966, store, [LoginReducer])
    server = server_opt.unwrap()

    client_socket = await websockets.connect("ws://127.0.0.1:9966/login/entry/test")
    login_action = {
        "type": "LOGIN",
        "userName": "kenny",
        "password": "123456",
    }
    await client_socket.send(json.dumps(login_action))
    await asyncio.sleep(0.2)

    login_action = {
        "type": "LOGIN",
        "userName": "kenny",
        "password": "654321",
    }
    await client_socket.send(json.dumps(login_action))
    await asyncio.sleep(0.2)


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(work())
