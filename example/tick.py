import asyncio
import re
import redux
from datetime import datetime


'''
示例: websocket 报时

这个示例只使用了 PublicEntryReducer 模式来和客户端进行通信, 
通过每两秒的周期使用 dispatch 方法触发 PublicEntryReducer 向客户端发送 TIME Action.
启动脚本之后, 需要使用浏览器打开 tick.html 文件接收 Action

这个示例的 Reducer 连接结构如下:

--------------------       ----------------------
| websocket client | <---> | PublicEntryReducer |
--------------------       ----------------------

'''


@redux.behavior("entry:session:", redux.SubscribeRecycleOption(), url_pattern="/tick/entry/(.+)")
class TickReducer(redux.PublicEntryReducer):
    @staticmethod
    async def find_node_id(key_prefix, path, query):
        groups = re.match(TickReducer.url_pattern, path).groups()
        if groups:
            return groups[0]
        return None

    async def initialize(self, key):
        result = await super(TickReducer, self).initialize(key)
        print(self.node_id, "join in")
        return result

    async def shutdown(self):
        print(self.node_id, "leave")

    async def action_received(self, action: redux.Action):
        medium = self.entry_medium
        time = str(datetime.now())
        await self.send(redux.Action("TIME", time=time, name=self.node_id), medium)


async def work():
    store = redux.Store()
    server_opt = await redux.RemoteManager().serve_entry("127.0.0.1", 9966, store, [TickReducer])
    server = server_opt.unwrap()
    while True:
        await asyncio.sleep(2)
        for reducer in store.find_reducer_list_by_type(TickReducer):
            await store.dispatch(reducer.key, redux.Action.no_op_command())

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(work())
