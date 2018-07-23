from typing import *
import json
import asyncio
import websockets


class Action:
    def __init__(self, action_type: str, **kwargs):
        self.type = action_type
        self.arguments = kwargs or {}
        assert isinstance(self.type, str)
        assert isinstance(self.arguments, dict)

    def to_json(self) -> str:
        return json.dumps(dict(type=self.type).update(self.arguments))

    @staticmethod
    def from_json(json_data: str) -> 'Action':
        all_arguments = json.loads(json_data)
        action_type = all_arguments.get("type", None)
        assert isinstance(action_type, str)
        del all_arguments["type"]
        return Action(action_type, **all_arguments)


class Reducer:
    def __init__(self, mapping_dict: dict):
        mapping_dict = mapping_dict or {}
        self._mapping_dict = mapping_dict
        self._state = {}

    async def reduce(self, action: Action) -> Dict[str, Any]:
        changed_state = {}
        state = self._state
        for key, callback in self._mapping_dict.items():
            sub_state = state.get(key, None)
            new_sub_state = callback(sub_state, action)
            if id(sub_state) != id(new_sub_state):
                changed_state[key] = new_sub_state
            state[key] = new_sub_state
        self._state = state
        return changed_state


class StoreWrapper:
    def __init__(self, uri: str):
        pass

    async def hello(self, uri):
        async with websockets.connect(uri) as ws:
            pass
            #await ws.send("Hello world!")

    def dispatch(self, action: Union[Dict[str, Any], Action]):
        pass

    def get_state(self):
        pass

    def subscribe(self, listener):
        pass


class Store:
    def __init__(self, host: str, port: int, reducer: Reducer):
        assert reducer
        self._reducer = reducer
        asyncio.get_event_loop().run_until_complete(
            websockets.serve(self._pre_dispatch, host, port))
        asyncio.get_event_loop().run_forever()

    @no_type_check
    async def _pre_dispatch(self, ws, path):
        async for message in ws:
            action = Action.from_json(message)
            await self.dispatch(action)

    async def dispatch(self, action: Action):
        changed_state = await self._reducer.reduce(action)

