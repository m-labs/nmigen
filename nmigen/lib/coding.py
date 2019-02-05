"""Encoders and decoders between binary and one-hot representation."""

from .. import *


__all__ = [
    "Encoder", "Decoder",
    "PriorityEncoder", "PriorityDecoder",
    "GrayEncoder", "GrayDecoder",
]


class Encoder:
    """Encode one-hot to binary.

    If one bit in ``i`` is asserted, ``n`` is low and ``o`` indicates the asserted bit.
    Otherwise, ``n`` is high and ``o`` is ``0``.

    Parameters
    ----------
    width : int
        Bit width of the input

    Attributes
    ----------
    i : Signal(width), in
        One-hot input.
    o : Signal(max=width), out
        Encoded binary.
    n : Signal, out
        Invalid: either none or multiple input bits are asserted.
    """
    def __init__(self, width):
        self.width = width

        self.i = Signal(width)
        self.o = Signal(max=max(2, width))
        self.n = Signal()

    def elaborate(self, platform):
        m = Module()
        with m.Switch(self.i):
            for j in range(self.width):
                with m.Case(1 << j):
                    m.d.comb += self.o.eq(j)
            with m.Case():
                m.d.comb += self.n.eq(1)
        return m


class PriorityEncoder:
    """Priority encode requests to binary.

    If any bit in ``i`` is asserted, ``n`` is low and ``o`` indicates the least significant
    asserted bit.
    Otherwise, ``n`` is high and ``o`` is ``0``.

    Parameters
    ----------
    width : int
        Bit width of the input.

    Attributes
    ----------
    i : Signal(width), in
        Input requests.
    o : Signal(max=width), out
        Encoded binary.
    n : Signal, out
        Invalid: no input bits are asserted.
    """
    def __init__(self, width):
        self.width = width

        self.i = Signal(width)
        self.o = Signal(max=max(2, width))
        self.n = Signal()

    def elaborate(self, platform):
        m = Module()
        for j in reversed(range(self.width)):
            with m.If(self.i[j]):
                m.d.comb += self.o.eq(j)
        m.d.comb += self.n.eq(self.i == 0)
        return m


class Decoder:
    """Decode binary to one-hot.

    If ``n`` is low, only the ``i``th bit in ``o`` is asserted.
    If ``n`` is high, ``o`` is ``0``.

    Parameters
    ----------
    width : int
        Bit width of the output.

    Attributes
    ----------
    i : Signal(max=width), in
        Input binary.
    o : Signal(width), out
        Decoded one-hot.
    n : Signal, in
        Invalid, no output bits are to be asserted.
    """
    def __init__(self, width):
        self.width = width

        self.i = Signal(max=max(2, width))
        self.n = Signal()
        self.o = Signal(width)

    def elaborate(self, platform):
        m = Module()
        with m.Switch(self.i):
            for j in range(len(self.o)):
                with m.Case(j):
                    m.d.comb += self.o.eq(1 << j)
        with m.If(self.n):
            m.d.comb += self.o.eq(0)
        return m


class PriorityDecoder(Decoder):
    """Decode binary to priority request.

    Identical to :class:`Decoder`.
    """


class GrayEncoder:
    """Encode binary to Gray code.

    Parameters
    ----------
    width : int
        Bit width.

    Attributes
    ----------
    i : Signal(width), in
        Input natural binary.
    o : Signal(width), out
        Encoded Gray code.
    """
    def __init__(self, width):
        self.width = width

        self.i = Signal(width)
        self.o = Signal(width)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o.eq(self.i ^ self.i[1:])
        return m


class GrayDecoder:
    """Decode Gray code to binary.

    Parameters
    ----------
    width : int
        Bit width.

    Attributes
    ----------
    i : Signal(width), in
        Input Gray code.
    o : Signal(width), out
        Decoded natural binary.
    """
    def __init__(self, width):
        self.width = width

        self.i = Signal(width)
        self.o = Signal(width)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o[-1].eq(self.i[-1])
        for i in reversed(range(self.width - 1)):
            m.d.comb += self.o[i].eq(self.o[i + 1] ^ self.i[i])
        return m
