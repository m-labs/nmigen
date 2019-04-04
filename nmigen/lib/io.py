from .. import *
from ..hdl.rec import *


__all__ = ["triple_layout", "Tristate"]


def triple_layout(shape):
    return Layout([
        ("o",  shape, DIR_FANOUT),
        ("oe", 1,     DIR_FANOUT),
        ("i",  shape, DIR_FANIN)
    ])


class Tristate:
    def __init__(self, triple, io):
        self.triple = triple
        self.io     = io

    def elaborate(self, platform):
        if hasattr(platform, "get_tristate"):
            return platform.get_tristate(self.triple, self.io)

        m = Module()
        m.d.comb += self.triple.i.eq(self.io)
        m.submodules += Instance("$tribuf",
            p_WIDTH=len(self.io),
            i_EN=self.triple.oe,
            i_A=self.triple.o,
            o_Y=self.io,
        )

        f = m.elaborate(platform)
        f.flatten = True
        return f
