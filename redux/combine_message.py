from asyncio import Future, ensure_future, wait_for, TimeoutError


class CombineMessage:
    def __init__(self):
        self.message_type_list = list()
        self.combine_message = None
        self.timeout_message = None
        self.timeout = 1.0
        self.keep_origin = False
        self.future = Future()
        self.node_key = None
        self.store = None

    def active(self):
        ensure_future(self._active())

    async def _active(self):
        try:
            await wait_for(self.future, self.timeout)
            if self.combine_message:
                await self.store.dispatch(self.node_key, self.combine_message)
        except TimeoutError:
            if self.node_key in self.store:
                reducer_opt = await self.store.get_or_create_cell(self.node_key, None)
                if reducer_opt.is_some:
                    reducer = reducer_opt.unwrap()
                    if self in reducer.combine_message_list:
                        reducer.combine_message_list.remove(self)
                await self.store.dispatch(self.node_key, self.timeout_message)


class AnyMessage(CombineMessage):
    def __init__(self):
        super(AnyMessage, self).__init__()
        self.keep_origin = True


__all__ = ["CombineMessage", "AnyMessage"]
