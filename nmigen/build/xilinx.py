from functools import partial

from .. import *
from .generic_platform import *


__all__ = ["XilinxPlatform"]


def _format_xdc(platform, name):
    text = ""

    for port_name, identifiers, extras in platform.get_port_constraints():
        if len(identifiers) == 1:
            text += "set_property LOC {} [get_ports {}]\n".format(identifiers[0], port_name)
        else:
            for j, identifier in enumerate(identifiers):
                text += "set_property LOC {} [get_ports {}[{}]]\n".format(identifier, port_name, j)
        for constraint in extras:
            constraint = constraint.replace("=", " ")
            text += "set_property {} [get_ports {}]\n".format(constraint, port_name)
        text += "\n"

    text += "\n".join(platform.commands) + "\n"

    for clk_name, period in platform.get_period_constraints():
        text += "create_clock -name {0} -period {1} [get_nets {0}]\n".format(clk_name, period)

    file_info = {"name": "{}.xdc".format(name), "file_type": "xdc"}
    return text, file_info


class XilinxPlatform(GenericPlatform):
    def __init__(self, *args, toolchain="vivado", **kwargs):
        super().__init__(*args, **kwargs)

        if toolchain == "vivado":
            self.format_constraints = partial(_format_xdc, self)
            self.tool_options["vivado"] = {"part": self.device}
        else:
            raise ValueError("Unsupported toolchain: {}".format(toolchain))
        self.toolchain = toolchain

    def get_diff_input(self, p, n, i):
        return Instance("IBUFDS", i_I=p, i_IB=n, o_O=i)

    def get_diff_output(self, o, p, n):
        return Instance("OBUFDS", i_I=o, o_O=p, o_OB=n)

    def get_diff_tristate(self, triple, p, n):
        return Instance("IOBUFDS", i_O=triple.o, i_T=triple.oe, o_I=triple.i, io_IO=p, io_IOB=n)
