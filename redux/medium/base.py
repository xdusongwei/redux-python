from typing import *
from ..typing import *
from ..option import Option
from ..action import Action


class MediumBase:
    @staticmethod
    def to_message(source_key: KEY, key: KEY, action: 'Action') -> Option:
        message_type = "ACTION"
        message = dict(__t__=message_type, __k__=key, __r__=source_key, **action.to_dict())
        return Option(message)

    @staticmethod
    def from_message(source, message: Dict[str, Any]) -> Option:
        action = Action.from_dict(message)
        action.medium = source
        source_key = message.pop("__r__")
        action.source_key = source_key
        target_key = message.pop("__k__")
        return Option((target_key, action,))

    @staticmethod
    def to_pick_message(source_key: KEY, key: KEY, fields=None):
        message_type = "PICK"
        message = dict(__t__=message_type, __k__=key, __r__=source_key, __f__=fields)
        return Option(message)

    @staticmethod
    def from_pick_message(message: Dict[str, Any]) -> Option:
        fields = message.pop("__f__")
        target_key = message.pop("__k__")
        source_key = message.pop("__r__")
        return Option((source_key, target_key, fields))

    @staticmethod
    def to_pick_ack_message(key, state):
        message_type = "PICKACK"
        message = dict(__t__=message_type, __k__=key, __s__=state)
        return Option(message)

    @staticmethod
    def from_pick_ack_message(message: Dict[str, Any]) -> Option:
        target_key = message.pop("__k__")
        state = message.pop("__s__")
        return Option((target_key, state))

    async def send(self, current_key: KEY, key: KEY, action: Action):
        return Option(NotImplementedError())

    async def get_state(self, current_key: KEY, key: KEY, fields=None) -> Option:
        return Option(NotImplementedError())

    async def subscribe(self, current_key: KEY, key: KEY, listener) -> Option:
        return Option(NotImplementedError())

    @staticmethod
    def state_filter(state, fields):
        fields = set(fields or [])
        if state is not None:
            filtered_state = dict()
            for key in state.keys():
                if key.startswith("_"):
                    continue
                if not fields or key in fields:
                    filtered_state[key] = state[key]
            state = filtered_state
        return state
