from typing import *
import asyncio
import pytest
import redux


@pytest.fixture(scope="session", autouse=True)
def setup_environment():
    redux.RemoteManager().RECONNECT_TIMEOUT = 0.1


@redux.behavior("sub:local:", redux.SubscribeRecycleOption())
class LocalMediumSubscribeReducer(redux.Reducer):
    def __init__(self):
        mapping = {
            "name": self.name,
        }
        super(LocalMediumSubscribeReducer, self).__init__(mapping)

    async def name(self, action, state=None):
        if action == "setName":
            state = "Kenny"
        return state


class L(redux.Listener):
    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        print(changed_key)


@redux.behavior("listener:", redux.IdleTimeoutRecycleOption(5))
class LocalMediumListenerReducer(redux.Reducer):
    async def action_received(self, action: redux.Action):
        if action == "sub":
            await redux.LocalMedium(self.store).subscribe(self.key, "sub:local:1", L())


async def local_subscribe():
    store = redux.Store([LocalMediumSubscribeReducer, LocalMediumListenerReducer])
    await store.dispatch("listener:1", redux.Action("sub"))
    await store.dispatch("sub:local:1", redux.Action("setName"))
    await asyncio.sleep(5)



def test_idle():
    asyncio.get_event_loop().run_until_complete(local_subscribe())
