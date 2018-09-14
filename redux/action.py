from typing import *


class Action:
    def __init__(self, type: str, **kwargs):
        self.type = type
        self.arguments = kwargs or {}
        self.medium = None
        self.source_key = None
        assert isinstance(self.type, str)
        assert isinstance(self.arguments, dict)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.type == other
        else:
            return super(Action, self).__eq__(other)

    def to_data(self, dumps):
        action_dict = dict(type=self.type, **{k: v for k, v in self.arguments.items() if not k.startswith("__")})
        return dumps(action_dict)

    def to_dict(self):
        return dict(type=self.type, **{k: v for k, v in self.arguments.items() if not k.startswith("__")})

    @property
    def soft(self):
        return self.arguments.get("soft")

    @staticmethod
    def from_data(data, loads) -> 'Action':
        all_arguments = loads(data)
        action_type = all_arguments.get("type", None)
        assert isinstance(action_type, str)
        del all_arguments["type"]
        return Action(action_type, **all_arguments)

    @staticmethod
    def from_dict(data: Dict) -> 'Action':
        action_type = data.get("type", None)
        assert isinstance(action_type, str)
        del data["type"]
        kwargs = {k: v for k, v in data.items() if not k.startswith("__")}
        return Action(action_type, **kwargs)

    @staticmethod
    def no_op_command() -> 'Action':
        return Action("__NO_OP")

    def __repr__(self):
        return "<Action: {}, {}>".format(self.type, self.arguments)


__all__ = ["Action", ]
