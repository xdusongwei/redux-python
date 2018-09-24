from typing import *
import asyncio
import pytest
import redux


class L(redux.Listener):
    test_sequence = [
        ({"name", "age"}, {'name': None, 'age': None}),
        ({"name"}, {'name': 'peter', 'age': None}),
        ({"name", "age"}, {'name': None, 'age': None}),
        ({"name"}, {'name': 'bob', 'age': None}),
        ({"name"}, {'name': 'jim', 'age': None}),
        ({"name"}, {'name': 'tony', 'age': None}),
    ]

    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        test_changed, test_state = self.test_sequence.pop(0)
        assert test_changed == set(changed_key)
        assert test_state == state


async def name(action: redux.Action, state=None):
    if action.type == "NAME":
        state = action.arguments["name"]
    return state


async def age(action: redux.Action, state=None):
    if action.type == "AGE":
        state = action.arguments["age"]
    return state


@redux.behavior("", redux.IdleTimeoutRecycleOption(0))
class ReducerBasic(redux.Reducer):
    def __init__(self):
        reducer = {
            "name": name,
            "age": age,
        }
        super(ReducerBasic, self).__init__(reducer)


async def basic_redux():
    store = redux.Store([ReducerBasic])
    await store.dispatch("1", redux.Action("todo"))
    handler = (await store.subscribe("1", L())).unwrap()
    await store.dispatch("1", redux.Action("NAME", name="peter"))
    handler()
    await store.dispatch("1", redux.Action("NAME", name="john"))
    handler = (await store.subscribe("1", L())).unwrap()
    await store.dispatch("1", redux.Action("NAME", name="bob"))
    await store.dispatch("1", redux.Action("NAME", name="jim"))
    await store.dispatch("1", redux.Action("NAME", name="tony"))


class ReducerWithSend(redux.Reducer):
    def __init__(self):
        reducer = {
            "name": name,
            "age": age,
        }
        super(ReducerWithSend, self).__init__(reducer)

    async def reduce_finish(self, action: redux.Action, changed_state: Dict[str, Any]):
        if self.key == "1":
            assert action.medium is None
            assert action.source_key is None
            opt = await self.send(action.medium, action.source_key, redux.Action("hello", time=1234))
            assert opt.is_error
            local_source = await redux.LocalMedium.connect(self.store)
            await self.send(local_source, "2", redux.Action("hello", time=4321))
        if self.key == "2":
            assert isinstance(action.medium, redux.LocalMedium)
            assert action.source_key == "1"
            assert action.arguments == dict(time=4321)


async def send_in_process():
    store = redux.Store([ReducerWithSend])
    await store.dispatch("1", redux.Action("todo"))


socket_sent_future = asyncio.Future()


@redux.behavior(None)
class ReducerWithSocketSend(redux.Reducer):
    def __init__(self):
        reducer = {
            "name": name,
            "age": age,
        }
        super(ReducerWithSocketSend, self).__init__(reducer)

    async def reduce_finish(self, action: redux.Action, changed_state: Dict[str, Any]):
        if self.key == "1" and action.type == "todo":
            target = await redux.RemoteMedium.connect(self.store, "ws://127.0.0.1:9906")
            target = target.unwrap()
            await self.send(target, "2", redux.Action("hello", time=4321))
        if self.key == "1" and action.type == "hello":
            assert action.arguments == dict(time=1)
            socket_sent_future.set_result(True)
        if self.key == "2":
            await self.send(action.medium, action.source_key, redux.Action("hello", time=1))


async def send_in_socket():
    redux.RemoteManager().client_url.add("ws://127.0.0.1:9906")
    store = redux.Store([ReducerWithSocketSend])
    server_opt = await redux.RemoteManager().serve("127.0.0.1", 9906, store)
    server = server_opt.unwrap()
    await store.dispatch("1", redux.Action("todo"))
    asyncio.wait_for(socket_sent_future, 1)
    await redux.RemoteManager().stop_serve(server)


refetch_future = asyncio.Future()


@redux.behavior("user")
class ReducerStateProvider(redux.Reducer):
    def __init__(self):
        reducer = {
            "name": name,
            "age": age,
        }
        super(ReducerStateProvider, self).__init__(reducer)

    async def initialize(self, key):
        await super(ReducerStateProvider, self).initialize(key)
        self._state = {
            "name": "provider",
            "age": 1,
        }
        return True

    async def action_received(self, action: redux.Action):
        if action.type == "CALL_ME":
            state = await self.get_remote_state(action.medium, "fetcher")
            assert state.unwrap() == dict(name=None, age=None)
            refetch_future.set_result(True)


@redux.behavior("fetcher")
class ReducerStateFetcher(redux.Reducer):
    def __init__(self):
        reducer = {
            "name": name,
            "age": age,
        }
        super(ReducerStateFetcher, self).__init__(reducer)

    async def action_received(self, action: redux.Action):
        target = await redux.RemoteMedium.connect(self.store, "ws://127.0.0.1:9906")
        state = await self.get_remote_state(target.unwrap(), "user")
        assert state.unwrap() == dict(name="provider", age=1)
        state = await self.get_remote_state(redux.LocalMedium(self.store), "user")
        assert state.unwrap() == dict(name="provider", age=1)

        state = await self.get_remote_state(target.unwrap(), "user", ["name"])
        assert state.unwrap() == dict(name="provider")
        state = await self.get_remote_state(redux.LocalMedium(self.store), "user", ["age"])
        assert state.unwrap() == dict(age=1)

        await self.send(target.unwrap(), "user", redux.Action("CALL_ME"))


async def fetch_state():
    redux.RemoteManager().client_url.add("ws://127.0.0.1:9906")
    store = redux.Store([ReducerStateProvider, ReducerStateFetcher])
    server_opt = await redux.RemoteManager().serve("127.0.0.1", 9906, store)
    await asyncio.sleep(0.11)
    server = server_opt.unwrap()
    await store.dispatch("user", redux.Action("todo"))
    await store.dispatch("fetcher", redux.Action("todo"))
    asyncio.wait_for(refetch_future, 1)
    await redux.RemoteManager().stop_serve(server)


class IdleListener(redux.Listener):
    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        pass


@redux.behavior(r"idle:", redux.IdleTimeoutRecycleOption(0.1))
class IdleReducer(redux.Reducer):
    def __init__(self):
        reducer = {
            "name": name,
            "age": age,
        }
        super(IdleReducer, self).__init__(reducer)


async def idle():
    store = redux.Store([IdleReducer, ], cleaner_period=0.05)
    await store.dispatch("idle:test", redux.Action.no_op_command())
    assert "idle:test" in store
    await asyncio.sleep(0.03)
    await store.dispatch("idle:test", redux.Action.no_op_command())
    await asyncio.sleep(0.22)
    assert "idle:test" not in store
    await store.dispatch("idle:test2", redux.Action.no_op_command())
    assert "idle:test2" in store
    await asyncio.sleep(0.11)
    assert "idle:test2" not in store

    handle = (await store.subscribe("idle:test3", IdleListener())).unwrap()
    await asyncio.sleep(0.11)
    assert "idle:test3" in store
    handle()
    await asyncio.sleep(0.11)
    assert "idle:test3" not in store

    handle = (await store.subscribe("idle:test4", IdleListener())).unwrap()
    await asyncio.sleep(0.11)
    assert "idle:test4" in store
    handle()
    handle = (await store.subscribe("idle:test4", IdleListener())).unwrap()
    await asyncio.sleep(0.11)
    assert "idle:test4" in store
    handle()
    await asyncio.sleep(0.11)


@pytest.fixture(scope="session", autouse=True)
def setup_environment():
    redux.RemoteManager().RECONNECT_TIMEOUT = 0.1


def test_basic():
    asyncio.get_event_loop().run_until_complete(basic_redux())


def test_send():
    asyncio.get_event_loop().run_until_complete(send_in_process())


def test_socket_send():
    asyncio.get_event_loop().run_until_complete(send_in_socket())


def test_fetch():
    asyncio.get_event_loop().run_until_complete(fetch_state())


def test_idle():
    asyncio.get_event_loop().run_until_complete(idle())


@redux.action_info("TYPE_ACTION")
class TypeAction(redux.Action):
    def __init__(self, **kwargs):
        super(TypeAction, self).__init__(self.TYPE, **kwargs)


def test_action():
    action = redux.Action("one")
    assert action == "one"
    assert action != "two"
    assert action.type == "one"
    assert action.type == action.type
    assert action in ["three", "two", "one"]
    assert action != TypeAction
    action = redux.Action("TYPE_ACTION")
    assert action == TypeAction

