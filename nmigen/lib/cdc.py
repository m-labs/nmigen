from ..tools import deprecated
from .. import *


__all__ = ["FFSynchronizer", "ResetSynchronizer"]
# TODO(nmigen-0.2): remove this
__all__ += ["MultiReg"]


class FFSynchronizer(Elaboratable):
    """Resynchronise a signal to a different clock domain.

    Consists of a chain of flip-flops. Eliminates metastabilities at the output, but provides
    no other guarantee as to the safe domain-crossing of a signal.

    Parameters
    ----------
    i : Signal, in
        Signal to be resynchronised.
    o : Signal, out
        Signal connected to synchroniser output.
    o_domain : str
        Name of output clock domain.
    stages : int
        Number of synchronization stages between input and output. The lowest safe number is 2,
        with higher numbers reducing MTBF further, at the cost of increased latency.
    reset : int
        Reset value of the flip-flops. On FPGAs, even if ``reset_less`` is True,
        the :class:`FFSynchronizer` is still set to this value during initialization.
    reset_less : bool
        If True (the default), this :class:`FFSynchronizer` is unaffected by ``o_domain`` reset.
        See "Note on Reset" below.

    Platform override
    -----------------
    Define the ``get_ff_sync`` platform method to override the implementation of :class:`FFSynchronizer`,
    e.g. to instantiate library cells directly.

    Note on Reset
    -------------
    :class:`FFSynchronizer` is non-resettable by default. Usually this is the safest option;
    on FPGAs the :class:`FFSynchronizer` will still be initialized to its ``reset`` value when
    the FPGA loads its configuration.

    However, in designs where the value of the :class:`FFSynchronizer` must be valid immediately
    after reset, consider setting ``reset_less`` to False if any of the following is true:

    - You are targeting an ASIC, or an FPGA that does not allow arbitrary initial flip-flop states;
    - Your design features warm (non-power-on) resets of ``o_domain``, so the one-time
      initialization at power on is insufficient;
    - Your design features a sequenced reset, and the :class:`FFSynchronizer` must maintain
      its reset value until ``o_domain`` reset specifically is deasserted.

    :class:`FFSynchronizer` is reset by the ``o_domain`` reset only.
    """
    def __init__(self, i, o, *, o_domain="sync", stages=2, reset=0, reset_less=True):
        self.i = i
        self.o = o

        self._reset      = reset
        self._reset_less = reset_less
        self._o_domain   = o_domain
        self._stages     = stages

    def elaborate(self, platform):
        if hasattr(platform, "get_ff_sync"):
            return platform.get_ff_sync(self)

        m = Module()
        flops = [Signal(self.i.shape(), name="stage{}".format(index),
                        reset=self._reset, reset_less=self._reset_less)
                 for index in range(self._stages)]
        for i, o in zip((self.i, *flops), flops):
            m.d[self._o_domain] += o.eq(i)
        m.d.comb += self.o.eq(flops[-1])
        return m


# TODO(nmigen-0.2): remove this
MultiReg = deprecated("instead of `MultiReg`, use `FFSynchronizer`")(FFSynchronizer)


class ResetSynchronizer(Elaboratable):
    def __init__(self, arst, *, domain="sync", stages=2):
        self.arst = arst

        self._domain = domain
        self._stages = stages

    def elaborate(self, platform):
        if hasattr(platform, "get_reset_sync"):
            return platform.get_reset_sync(self)

        m = Module()
        m.domains += ClockDomain("reset_sync", async_reset=True, local=True)
        flops = [Signal(1, name="stage{}".format(index), reset=1)
                 for index in range(self._stages)]
        for i, o in zip((0, *flops), flops):
            m.d.reset_sync += o.eq(i)
        m.d.comb += [
            ClockSignal("reset_sync").eq(ClockSignal(self._domain)),
            ResetSignal("reset_sync").eq(self.arst),
            ResetSignal(self._domain).eq(flops[-1])
        ]
        return m
