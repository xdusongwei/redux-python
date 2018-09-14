from typing import *
import time


class RecycleOption:
    def __init__(self):
        raise NotImplementedError


class IdleTimeoutRecycleOption:
    def __init__(self, timeout: Union[int, float]=30.0, soft_action=False, enable_subscribe=True):
        self.enable_subscribe = enable_subscribe
        self.timeout = float(timeout)
        self.soft_action = soft_action
        if self.timeout < 0:
            raise ValueError

    def create_key(self, reducer):
        return time.time() + self.timeout, reducer


class SubscribeRecycleOption(IdleTimeoutRecycleOption):
    def __init__(self, **kwargs):
        super(SubscribeRecycleOption, self).__init__(0, **kwargs)


class NeverRecycleOption:
    def __init__(self):
        pass


__all__ = ["RecycleOption", "IdleTimeoutRecycleOption", "SubscribeRecycleOption", "NeverRecycleOption"]

