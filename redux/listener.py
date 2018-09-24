from typing import *


class Listener:
    def __init__(self):
        self.key = None
        self.store = None
        self.is_binding = False
        self.unsubscribe = None

    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        raise NotImplementedError


class SilenceListener(Listener):
    async def on_changed(self, changed_key: List[str], state: Dict[str, Any]):
        return


class ListenerStateWrapper:
    def __init__(self, listener: Listener, initialize_full_state=True):
        self.is_synced = not initialize_full_state
        self.listener = listener

    async def call_state_changed(self, changed_state, state):
        if self.is_synced:
            await self.listener.on_changed(list(changed_state.keys()), state)
        else:
            self.is_synced = True
            await self.listener.on_changed([key for key in state.keys() if not key.startswith("__")], state)


__all__ = ["Listener", "SilenceListener", "ListenerStateWrapper", ]
