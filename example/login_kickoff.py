from typing import *
import asyncio
import re
import redux
import json
import random
import websockets


'''
示例: 多终端登录

这个示例使用了3种 Reducer 节点实现了管理多种用户会话的方式, 
移动平台的登录会踢掉上一个移动设备的登录会话, 但是PC平台只能让当前设备下线才可以登录新的PC设备.
在这个示例中 InternalEntryReducer 节点是一个中介角色: 接受其他 Reducer 节点的服务请求, 并将内部 Reducer 节点的处理结果返回给提供服务的节点.
通过 InternalEntryReducer 节点包装了其中负责的具体业务逻辑节点, 将比较复杂的功能划分成中等粒度服务.
PublicEntryReducer 将只需要将登录相关的 Action 发送给 InternalEntryReducer, 
InternalEntryReducer 再去将 Action 交给 GeneralReducer 处理
注意 GeneralReducer 需要将结果传给 InternalEntryReducer 来不让自己暴露在外界

这个示例的 Reducer 连接结构如下:

--------------------       ----------------------       ------------------------       ------------------
| websocket client | <---> | PublicEntryReducer | <---> | InternalEntryReducer | <---> | GeneralReducer |
--------------------       ----------------------       ------------------------       ------------------


'''


@redux.behavior(r"entry:session:", redux.SubscribeRecycleOption(), r"/login/entry/(.+)")
class PublicService(redux.PublicEntryReducer):
    def __init__(self):
        super(PublicService, self).__init__()

    @staticmethod
    async def find_node_id(key_prefix, path, query):
        groups = re.match(PublicService.url_pattern, path).groups()
        if groups:
            return f"{groups[0]}{str(int(random.uniform(0, 10000))).zfill(4)}"
        return None

    async def action_received(self, action: redux.Action):
        if action == "__NO_OP":
            return
        print("PublicService received", self.key, action)
        if isinstance(action.medium, redux.EntryMedium):
            if action == "LOGIN":
                user_name = action.arguments["userName"]
                platform = action.arguments["platform"]
                action = redux.Action("LOGIN", user_name=user_name, platform=platform)
                await self.send(action, redux.LocalMedium(self.store), LoginService, user_name)
            if action == "SHOW_POINTS":
                token = action.arguments["token"]
                await self.send(action, redux.LocalMedium(self.store), LoginService, token)
        if isinstance(action.medium, redux.LocalMedium):
            await self.response(action, self.entry_medium, None)


@redux.behavior(r"entry:user:", redux.IdleTimeoutRecycleOption(3))
class LoginService(redux.InternalEntryReducer):
    PC_PLATFORM = {"Windows", "MacOS"}
    MOBILE_PLATFORM = {"Android", "iOS"}

    def __init__(self):
        super(LoginService, self).__init__()
        self.login_list = []

    @property
    def login_list(self) -> List[redux.Action]:
        return self.get_state().get("_login_list", [])

    @login_list.setter
    def login_list(self, v):
        self.get_state()["_login_list"] = v

    async def action_received(self, action: redux.Action):
        if action == "LOGIN" and action.medium and action.source_key:
            platform = action.arguments.get("platform")
            user = action.arguments.get("user_name")
            if platform in LoginService.PC_PLATFORM:
                if any([session for session in self.login_list if session.arguments["platform"] in LoginService.PC_PLATFORM]):
                    await self.response(redux.Action("DENIED_LOGIN"), action.medium, action.source_key)
                else:
                    login_list = self.login_list
                    login_list.append(action)
                    self.login_list = login_list
                    await self.response(redux.Action("ACCESS_LOGIN", token=user), action.medium, action.source_key)
            if platform in LoginService.MOBILE_PLATFORM:
                new_login_list = []
                for session in self.login_list.copy():
                    if session.arguments["platform"] in LoginService.MOBILE_PLATFORM:
                        await self.response(redux.Action("DENIED_LOGIN"), session.medium, session.source_key)
                    else:
                        new_login_list.append(session)
                new_login_list.append(action)
                self.login_list = new_login_list
                await self.response(redux.Action("ACCESS_LOGIN", token=user), action.medium, action.source_key)

        if action == "SHOW_POINTS":
            token = action.arguments.get("token", None)
            user = token
            await self.send(action, redux.LocalMedium(self.store), UserService, user)

        if action == "POINTS":
            for session in self.login_list:
                await self.response(action, session.medium, session.source_key)


@redux.behavior(r"node:user:", redux.IdleTimeoutRecycleOption(3))
class UserService(redux.GeneralReducer):
    def __init__(self):
        mapping = {
            "points": self.points,
        }
        super(UserService, self).__init__(mapping)

    async def action_received(self, action: redux.Action):
        if action == "SHOW_POINTS" and action.medium:
            points = self.get_state().get("points", None)
            await self.response(redux.Action("POINTS", points=points), action.medium, action.source_key)

    async def points(self, action: redux.Action, state=0):
        return state


async def work():
    store = redux.Store([PublicService, LoginService, UserService])
    server_opt = await redux.RemoteManager().serve_entry("127.0.0.1", 9966, store, [PublicService])
    server = server_opt.unwrap()

    client_socket = await websockets.connect("ws://127.0.0.1:9966/login/entry/test")
    login_action = {
        "type": "LOGIN",
        "userName": "kenny",
        "platform": "Windows",
    }
    await client_socket.send(json.dumps(login_action))

    client_socket = await websockets.connect("ws://127.0.0.1:9966/login/entry/test")
    login_action = {
        "type": "LOGIN",
        "userName": "kenny",
        "platform": "Android",
    }
    await client_socket.send(json.dumps(login_action))
    await asyncio.sleep(0.5)

    client_socket = await websockets.connect("ws://127.0.0.1:9966/login/entry/test")
    login_action = {
        "type": "LOGIN",
        "userName": "kenny",
        "platform": "MacOS",
    }
    await client_socket.send(json.dumps(login_action))
    await asyncio.sleep(0.5)

    client_socket = await websockets.connect("ws://127.0.0.1:9966/login/entry/test")
    login_action = {
        "type": "LOGIN",
        "userName": "kenny",
        "platform": "iOS",
    }
    await client_socket.send(json.dumps(login_action))
    await asyncio.sleep(0.5)

    point_action = {
        "type": "SHOW_POINTS",
        "token": "kenny",
    }
    await client_socket.send(json.dumps(point_action))
    await asyncio.sleep(0.5)


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(work())
