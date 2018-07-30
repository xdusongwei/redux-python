import asyncio
import redux


SET_NAME = "SET_NAME"
SET_AGE = "SET_AGE"


async def name(action: redux.Action, state=None):
    action_type = action.type
    if action_type == SET_NAME:
        return action.arguments["name"]
    else:
        return state


async def age(action: redux.Action, state=None):
    action_type = action.type
    if action_type == SET_AGE:
        return action.arguments["age"]
    else:
        return state


class ClientListener(redux.Listener):
    KEYS_SEQ = [
        ['name'],
        ['age'],
        ['name'],
        ['name', 'age'],
        ['age'],
        ['age'],
    ]

    async def on_changed(self, changed_keys, state):
        state = self.store.get_state()
        print(changed_keys, state)
        #assert changed_keys == self.KEYS_SEQ.pop(0)


async def example_original():
    combine_channel = {
        "name": name,
        "age": age,
    }
    store = redux.Store(lambda: redux.Reducer(combine_channel))
    key = "1"
    kenny_listener = ClientListener(key, store)
    await store.dispatch(key, redux.Action("no-op"))
    print("sent", redux.Action("no-op"))
    await store.dispatch(key, redux.Action(SET_NAME, name="Kenny"))
    print("sent", redux.Action(SET_NAME, name="Kenny"))
    await store.dispatch(key, redux.Action(SET_AGE, age=20))
    print("sent", redux.Action(SET_AGE, age=20))
    await asyncio.sleep(1)


async def example():
    combine_channel = {
        "name": name,
        "age": age,
    }
    store = redux.Store("127.0.0.1", 8890, lambda: redux.Reducer(combine_channel))
    await store.start()

    key = redux.StateCellFilter().create_cell_url("12345")
    store_kenny = await redux.StoreWrapper.create("ws://127.0.0.1:8890/", key)
    kenny_listener = ClientListener(store_kenny)
    await store_kenny.dispatch(redux.Action("no-op"))
    await store_kenny.dispatch(redux.Action(SET_NAME, name="Kenny"))
    await store_kenny.dispatch(redux.Action(SET_AGE, age=20))

    key = redux.StateCellFilter().create_cell_url("54321")
    store_jimmy = await redux.StoreWrapper.create("ws://127.0.0.1:8890/", key)
    jimmy_listener = ClientListener(store_jimmy)
    await store_jimmy.dispatch(redux.Action(SET_NAME, name="Jimmy"))
    await store_jimmy.dispatch(redux.Action(SET_AGE, age=21))

    key = redux.StateCellFilter().create_cell_url("12345")
    store_new_kenny = await redux.StoreWrapper.create("ws://127.0.0.1:8890/", key)
    new_kenny_listener = ClientListener(store_new_kenny)
    await store_new_kenny.dispatch(redux.Action(SET_AGE, age=22))

    await asyncio.sleep(1)
    kenny_listener.unsubscribe()
    jimmy_listener.unsubscribe()
    new_kenny_listener.unsubscribe()
    await store_jimmy.close()
    await store_kenny.close()
    await store_new_kenny.close()


def test_async():
    asyncio.get_event_loop().run_until_complete(example_original())

