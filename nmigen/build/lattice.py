from functools import partial

from .generic_platform import *


__all__ = ["ECP5Platform"]


def _format_lpf(platform, name):
    text = ""
    text += "BLOCK RESETPATHS;\n"
    text += "BLOCK ASYNCPATHS;\n"

    for port_name, identifiers, extras in platform.get_port_constraints():
        if len(identifiers) == 1:
            text += "LOCATE COMP \"{}\" SITE \"{}\";\n".format(port_name, identifiers[0])
        else:
            for j, identifier in enumerate(identifiers):
                text += "LOCATE COMP \"{}[{}]\" SITE \"{}\";\n".format(port_name, j, identifier)
        for constraint in extras:
            text += "IOBUF PORT \"{}\" {};\n".format(port_name, constraint)
        text += "\n"

    text += "\n".join(platform.commands) + "\n"

    for clk_name, period in platform.get_period_constraints():
        freq = float(1/period) * 1000
        text += "FREQUENCY PORT \"{}\" {} MHz;\n".format(clk_name, freq)

    file_info = {"name": "{}.lpf".format(name), "file_type": "user"}
    return text, file_info


class ECP5Platform(GenericPlatform):
    def __init__(self, *args, toolchain="trellis", **kwargs):
        super().__init__(*args, **kwargs)

        if toolchain == "trellis":
            self.format_constraints = partial(_format_lpf, self)
            self.tool_options["trellis"] = {"nextpnr_options": ["--lpf $(TARGET).lpf"]} # FIXME
        else:
            raise ValueError("Unsupported toolchain: {}".format(toolchain))

        self.toolchain = toolchain
