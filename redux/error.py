class ReduxError(Exception):
    def __init__(self, error: Exception, stack: str):
        self.error = error
        self.stack = stack

    def __repr__(self):
        return self.error.__repr__()


class NoneError(Exception):
    pass


class SameKeyError(Exception):
    pass


__all__ = ["ReduxError", "NoneError", "SameKeyError"]
