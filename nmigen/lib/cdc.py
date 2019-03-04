from .. import *
from math import gcd


__all__ = ["MultiReg", "ResetSynchronizer", "PulseSynchronizer", "Gearbox"]


def _incr(signal, modulo):
    if modulo == 2 ** len(signal):
        return signal + 1
    else:
        return Mux(signal == modulo - 1, 0, signal + 1)


class MultiReg(Elaboratable):
    """Resynchronise a signal to a different clock domain.

    Consists of a chain of flip-flops. Eliminates metastabilities at the output, but provides
    no other guarantee as to the safe domain-crossing of a signal.

    Parameters
    ----------
    i : Signal(), in
        Signal to be resynchronised
    o : Signal(), out
        Signal connected to synchroniser output
    odomain : str
        Name of output clock domain
    n : int
        Number of flops between input and output.
    reset : int
        Reset value of the flip-flops. On FPGAs, even if ``reset_less`` is True, the MultiReg is
        still set to this value during initialization.
    reset_less : bool
        If True (the default), this MultiReg is unaffected by ``odomain`` reset.
        See "Note on Reset" below.

    Platform override
    -----------------
    Define the ``get_multi_reg`` platform method to override the implementation of MultiReg,
    e.g. to instantiate library cells directly.

    Note on Reset
    -------------
    MultiReg is non-resettable by default. Usually this is the safest option; on FPGAs
    the MultiReg will still be initialized to its ``reset`` value when the FPGA loads its
    configuration.

    However, in designs where the value of the MultiReg must be valid immediately after reset,
    consider setting ``reset_less`` to False if any of the following is true:

    - You are targeting an ASIC, or an FPGA that does not allow arbitrary initial flip-flop states;
    - Your design features warm (non-power-on) resets of ``odomain``, so the one-time
      initialization at power on is insufficient;
    - Your design features a sequenced reset, and the MultiReg must maintain its reset value until
      ``odomain`` reset specifically is deasserted.

    MultiReg is reset by the ``odomain`` reset only.
    """
    def __init__(self, i, o, odomain="sync", n=2, reset=0, reset_less=True):
        if not isinstance(n, int) or n < 1:
            raise TypeError("n must be a positive integer, not '{!r}'".format(n))
        self.i = i
        self.o = o
        self.odomain = odomain

        self._regs = [Signal(self.i.shape(), name="cdc{}".format(i),
                             reset=reset, reset_less=reset_less, attrs={"no_retiming": True})
                      for i in range(n)]

    def elaborate(self, platform):
        if hasattr(platform, "get_multi_reg"):
            return platform.get_multi_reg(self)

        m = Module()
        for i, o in zip((self.i, *self._regs), self._regs):
            m.d[self.odomain] += o.eq(i)
        m.d.comb += self.o.eq(self._regs[-1])
        return m


class ResetSynchronizer(Elaboratable):
    """Synchronize the deassertion of a reset to a local clock.

    Output `assertion` is asynchronous, so the local clock need not be free-running.

    Parameters
    ----------
    arst : Signal(1), out
        Asynchronous reset signal, to be synchronized.
    domain : str
        Name of domain to synchronize reset to.
    n : int, >=1
        Number of clock edges from input deassertion to output deassertion

    Override
    --------
    Define the ``get_reset_sync`` platform attribute to override the implementation of
    ResetSynchronizer, e.g. to instantiate library cells directly.
    """
    def __init__(self, arst, domain="sync", n=2):
        if not isinstance(n, int) or n < 1:
            raise TypeError("n must be a positive integer, not '{!r}'".format(n))
        self.arst = arst
        self.domain = domain

        self._regs = [Signal(name="arst{}".format(i), reset=1,
                             attrs={"no_retiming": True})
                      for i in range(n)]

    def elaborate(self, platform):
        if hasattr(platform, "get_reset_sync"):
            return platform.get_reset_sync(self)

        m = Module()
        m.domains += ClockDomain("_reset_sync", async_reset=True)
        for i, o in zip((0, *self._regs), self._regs):
            m.d._reset_sync += o.eq(i)
        m.d.comb += [
            ClockSignal("_reset_sync").eq(ClockSignal(self.domain)),
            ResetSignal("_reset_sync").eq(self.arst),
            ResetSignal(self.domain).eq(self._regs[-1])
        ]
        return m


class PulseSynchronizer(Elaboratable):
    """A one-clock pulse on the input produces a one-clock pulse on the output.

    If the output clock is faster than the input clock, then the input may be safely asserted at
    100% duty cycle. Otherwise, if the clock ratio is n : 1, the input may be asserted at most once
    in every n input clocks, else pulses may be dropped.

    Other than this there is no constraint on the ratio of input and output clock frequency.

    Parameters
    ----------

    idomain : str
        Name of input clock domain.
    odomain : str
        Name of output clock domain.
    sync_stages : int
        Number of synchronisation flops between the two clock domains. 2 is the default, and
        minimum safe value. High-frequency designs may choose to increase this.
    """
    def __init__(self, idomain, odomain, sync_stages=2):
        if not isinstance(sync_stages, int) or sync_stages < 1:
            raise TypeError("sync_stages must be a positive integer, not '{!r}'".format(sync_stages))

        self.i = Signal()
        self.o = Signal()
        self.idomain = idomain
        self.odomain = odomain
        self.sync_stages = sync_stages

    def elaborate(self, platform):
        m = Module()

        itoggle = Signal()
        otoggle = Signal()
        mreg = m.submodules.mreg = \
            MultiReg(itoggle, otoggle, odomain=self.odomain, n=self.sync_stages)
        otoggle_prev = Signal()

        m.d[self.idomain] += itoggle.eq(itoggle ^ self.i)
        m.d[self.odomain] += otoggle_prev.eq(otoggle)
        m.d.comb += self.o.eq(otoggle ^ otoggle_prev)

        return m


class Gearbox(Elaboratable):
    """Adapt the width of a continous datastream.

    Input:  m bits wide, clock frequency f MHz.
    Output: n bits wide, clock frequency m / n * f MHz.

    Used to adjust width of a datastream when interfacing system logic to a SerDes. The input and
    output clocks must be derived from the same reference clock, to maintain distance between
    read and write pointers.

    Parameters
    ----------
    iwidth : int
        Bit width of the input
    idomain : str
        Name of input clock domain
    owidth : int
        Bit width of the output
    odomain : str
        Name of output clock domain

    Attributes
    ----------
    i : Signal(iwidth), in
        Input datastream. Sampled on every input clock.
    o : Signal(owidth), out
        Output datastream. Transitions on every output clock.
    """
    def __init__(self, iwidth, idomain, owidth, odomain):
        if not isinstance(iwidth, int) or iwidth < 1:
            raise TypeError("iwidth must be a positive integer, not '{!r}'".format(iwidth))
        if not isinstance(owidth, int) or owidth < 1:
            raise TypeError("owidth must be a positive integer, not '{!r}'".format(owidth))

        self.i = Signal(iwidth)
        self.o = Signal(owidth)
        self.iwidth = iwidth
        self.idomain = idomain
        self.owidth = owidth
        self.odomain = odomain

        storagesize = iwidth * owidth // gcd(iwidth, owidth)
        while storagesize // iwidth < 4:
            storagesize *= 2
        while storagesize // owidth < 4:
            storagesize *= 2

        self._storagesize = storagesize
        self._ichunks = storagesize // self.iwidth
        self._ochunks = storagesize // self.owidth
        assert(self._ichunks * self.iwidth == storagesize)
        assert(self._ochunks * self.owidth == storagesize)

    def elaborate(self, platform):
        m = Module()

        storage = Signal(self._storagesize, attrs={"no_retiming": True})
        i_faster = self._ichunks > self._ochunks
        iptr = Signal(max=self._ichunks - 1, reset=(self._ichunks // 2 if i_faster else 0))
        optr = Signal(max=self._ochunks - 1, reset=(0 if i_faster else self._ochunks // 2))

        m.d[self.idomain] += iptr.eq(_incr(iptr, self._storagesize))
        m.d[self.odomain] += optr.eq(_incr(optr, self._storagesize))

        with m.Switch(iptr):
            for n in range(self._ichunks):
                s = slice(n * self.iwidth, (n + 1) * self.iwidth)
                with m.Case(n):
                    m.d[self.idomain] += storage[s].eq(self.i)

        with m.Switch(optr):
            for n in range(self._ochunks):
                s = slice(n * self.owidth, (n + 1) * self.owidth)
                with m.Case(n):
                    m.d[self.odomain] += self.o.eq(storage[s])

        return m
