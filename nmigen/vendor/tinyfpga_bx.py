from ..build import *
from .fpga.lattice_ice40 import LatticeICE40Platform, TinyProgrammerMixin


__all__ = ["TinyFPGABXPlatform"]

# Simon Kirkby
# 20190602
# obeygiantrobot@gmail.com

# board : https://tinyfpga.com/

class TinyFPGABXPlatform(TinyProgrammerMixin, LatticeICE40Platform):
    device    = "lp8k"
    package   = "cm81"
    clocks    = [
        ("clk16", 16e6),
    ]
    resources = [
        Resource("clk16", 0, Pins("B2", dir="i"), extras=["IO_STANDARD=LVCMOS33"]),

        Resource("user_led", 0, Pins("B3", dir="o"), extras=["IO_STANDARD=LVCMOS33"]),

        Resource("usb", 0,
            Subsignal("d_p", Pins("B4", dir="io")),
            Subsignal("d_n", Pins("A4", dir="io")),
            Subsignal("pull_up", Pins("A3", dir="o")),
            extras=["IO_STANDARD=SB_LVCMOS33"]
        ),

        Resource("spiflash", 0,
            Subsignal("cs_n", Pins("F7", dir="o")),
            Subsignal("clk",  Pins("G7", dir="o")),
            Subsignal("mosi", Pins("G6", dir="io")),
            Subsignal("miso", Pins("H7", dir="io")),
            extras=["IO_STANDARD=SB_LVCMOS33"]
        ),

        Resource("gpio", 0,
            # left hand side
            Subsignal("pin1", Pins("A2", dir="io")),
            Subsignal("pin2", Pins("A1", dir="io")),
            Subsignal("pin3", Pins("B1", dir="io")),
            Subsignal("pin4", Pins("C2", dir="io")),
            Subsignal("pin5", Pins("C1", dir="io")),
            Subsignal("pin6", Pins("D2", dir="io")),
            Subsignal("pin7", Pins("D1", dir="io")),
            Subsignal("pin8", Pins("E2", dir="io")),
            Subsignal("pin9", Pins("E1", dir="io")),
            Subsignal("pin10", Pins("G2", dir="io")),
            Subsignal("pin11", Pins("H1", dir="io")),
            Subsignal("pin12", Pins("J1", dir="io")),
            Subsignal("pin13", Pins("H2", dir="io")),
            # right hand side
            Subsignal("pin14", Pins("H9", dir="io")),
            Subsignal("pin15", Pins("D9", dir="io")),
            Subsignal("pin16", Pins("D8", dir="io")),
            Subsignal("pin17", Pins("B8", dir="io")),
            Subsignal("pin18", Pins("A9", dir="io")),
            Subsignal("pin19", Pins("B8", dir="io")),
            Subsignal("pin20", Pins("A8", dir="io")),
            Subsignal("pin21", Pins("B7", dir="io")),
            Subsignal("pin22", Pins("A7", dir="io")),
            Subsignal("pin23", Pins("B6", dir="io")),
            Subsignal("pin24", Pins("A6", dir="io")),
            # under side
            Subsignal("pin25", Pins("G1", dir="io")),
            Subsignal("pin26", Pins("J3", dir="io")),
            Subsignal("pin27", Pins("J4", dir="io")),
            Subsignal("pin28", Pins("G9", dir="io")),
            Subsignal("pin29", Pins("J9", dir="io")),
            Subsignal("pin30", Pins("E8", dir="io")),
            Subsignal("pin31", Pins("J2", dir="io")),
            extras=["IO_STANDARD=SB_LVCMOS33"]
        ),
    ]
