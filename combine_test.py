import asyncio
import pytest
import redux


timeout_future = asyncio.Future()
combine_future = asyncio.Future()


@redux.behavior("combine:", redux.IdleTimeoutRecycleOption(0.5))
class CombineReducer(redux.Reducer):
    async def action_received(self, action: redux.Action):
        if action == "START":
            self.combine_message(["A", "B"], redux.Action("COMBINE_FINISH"), redux.Action("COMBINE_ERROR"), 0.1)
        elif action == "COMBINE_ERROR":
            timeout_future.set_result(True)
        elif action == "COMBINE_FINISH":
            combine_future.set_result(True)
        else:
            print(action)


@pytest.fixture(scope="session", autouse=True)
def setup_environment():
    redux.RemoteManager().RECONNECT_TIMEOUT = 0.1


async def work():
    store = redux.Store([CombineReducer])
    await store.dispatch("combine:1", redux.Action("START"))
    await asyncio.sleep(0.2)
    assert timeout_future.done()
    await store.dispatch("combine:1", redux.Action("START"))
    await store.dispatch("combine:1", redux.Action("A"))
    await store.dispatch("combine:1", redux.Action("B"))
    await asyncio.sleep(0.2)
    assert combine_future.done()


def test_combine():
    asyncio.get_event_loop().run_until_complete(work())


if __name__ == '__main__':
    test_combine()
