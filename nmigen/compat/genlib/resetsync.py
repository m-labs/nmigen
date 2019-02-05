from ...tools import deprecated
from ...lib.cdc import ResetSynchronizer as NativeResetSynchronizer


__all__ = ["AsyncResetSynchronizer"]


@deprecated("instead of `migen.genlib.resetsync.AsyncResetSynchronizer`, "
            "use `nmigen.lib.cdc.ResetSynchronizer`; note that ResetSynchronizer accepts "
            "a clock domain name as an argument, not a clock domain object")
class CompatResetSynchronizer(NativeResetSynchronizer):
    def __init__(self, cd, async_reset):
        super().__init__(async_reset, cd.name)


AsyncResetSynchronizer = CompatResetSynchronizer
