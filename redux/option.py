from typing import *


_OT = TypeVar('_OT')


class Option:
    def __init__(self, v: _OT=None):
        self._v = v

    @property
    def is_error(self) -> bool:
        return isinstance(self._v, Exception)

    @property
    def is_none(self) -> bool:
        return self._v is None

    @property
    def is_some(self) -> bool:
        return not self.is_none and not self.is_error

    def unwrap(self) -> _OT:
        if self.is_error:
            raise ReferenceError
        return self._v

    @property
    def error(self) -> Optional[Exception]:
        if self.is_error:
            return self._v
        return None

    @staticmethod
    def none() -> 'Option':
        return Option()

    def __repr__(self):
        if self.is_error:
            return "<Option({}): {}>".format(type(self._v).__name__, self._v)
        return "<Option: {}>".format(self._v)


__all__ = ["Option"]
