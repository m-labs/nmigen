from abc import abstractproperty

from ..hdl import *
from ..build import *


__all__ = ["LatticeECP5Platform"]


class LatticeECP5Platform(TemplatedPlatform):
    """
    Trellis toolchain
    -----------------

    Required tools:
        * ``yosys``
        * ``nextpnr-ecp5``
        * ``ecppack``

    The environment is populated by running the script specified in the environment variable
    ``NMIGEN_Trellis_env``, if present.

    Available overrides:
        * ``verbose``: enables logging of informational messages to standard error.
        * ``read_verilog_opts``: adds options for ``read_verilog`` Yosys command.
        * ``synth_opts``: adds options for ``synth_ecp5`` Yosys command.
        * ``script_after_read``: inserts commands after ``read_ilang`` in Yosys script.
        * ``script_after_synth``: inserts commands after ``synth_ecp5`` in Yosys script.
        * ``yosys_opts``: adds extra options for ``yosys``.
        * ``nextpnr_opts``: adds extra options for ``nextpnr-ecp5``.
        * ``ecppack_opts``: adds extra options for ``ecppack``.

    Build products:
        * ``{{name}}.rpt``: Yosys log.
        * ``{{name}}.json``: synthesized RTL.
        * ``{{name}}.tim``: nextpnr log.
        * ``{{name}}.config``: ASCII bitstream.
        * ``{{name}}.bit``: binary bitstream.
        * ``{{name}}.svf``: JTAG programming vector.

    Diamond toolchain
    -----------------

    Required tools:
        * ``pnmainc``
        * ``ddtcmd``

    The environment is populated by running the script specified in the environment variable
    ``NMIGEN_Diamond_env``, if present.

    Available overrides:
        * ``script_project``: inserts commands before ``prj_project save`` in Tcl script.
        * ``script_after_export``: inserts commands after ``prj_run Export`` in Tcl script.
        * ``add_preferences``: inserts commands in LPF file.
        * ``add_constraints``: inserts commands in XDC file.

    Build products:
        * ``{{name}}_impl/{{name}}_impl.htm``: consolidated log.
        * ``{{name}}.bit``: binary bitstream.
        * ``{{name}}.svf``: JTAG programming vector.
    """

    toolchain = None # selected when creating platform

    device  = abstractproperty()
    package = abstractproperty()
    speed   = abstractproperty()
    grade   = "C" # [C]ommercial, [I]ndustrial

    # Trellis templates

    _nextpnr_device_options = {
        "LFE5U-12F":    "--25k",
        "LFE5U-25F":    "--25k",
        "LFE5U-45F":    "--45k",
        "LFE5U-85F":    "--85k",
        "LFE5UM-12F":   "--um-25k",
        "LFE5UM-25F":   "--um-25k",
        "LFE5UM-45F":   "--um-45k",
        "LFE5UM-85F":   "--um-85k",
        "LFE5UM5G-12F": "--um5g-25k",
        "LFE5UM5G-25F": "--um5g-25k",
        "LFE5UM5G-45F": "--um5g-45k",
        "LFE5UM5G-85F": "--um5g-85k",
    }
    _nextpnr_package_options = {
        "BG256": "caBGA256",
        "MG285": "csfBGA285",
        "BG381": "caBGA381",
        "BG554": "caBGA554",
        "BG756": "caBGA756",
    }

    _trellis_file_templates = {
        **TemplatedPlatform.build_script_templates,
        "{{name}}.il": r"""
            # {{autogenerated}}
            {{emit_design("rtlil")}}
        """,
        "{{name}}.ys": r"""
            # {{autogenerated}}
            {% for file in platform.iter_extra_files(".v") -%}
                read_verilog {{get_override("read_opts")|options}} {{file}}
            {% endfor %}
            {% for file in platform.iter_extra_files(".sv") -%}
                read_verilog -sv {{get_override("read_opts")|options}} {{file}}
            {% endfor %}
            read_ilang {{name}}.il
            {{get_override("script_after_read")|default("# (script_after_read placeholder)")}}
            synth_ecp5 {{get_override("synth_opts")|options}} -top {{name}}
            {{get_override("script_after_synth")|default("# (script_after_synth placeholder)")}}
            write_json {{name}}.json
        """,
        "{{name}}.lpf": r"""
            # {{autogenerated}}
            BLOCK ASYNCPATHS;
            BLOCK RESETPATHS;
            {% for port_name, pin_name, extras in platform.iter_port_constraints_bits() -%}
                LOCATE COMP "{{port_name}}" SITE "{{pin_name}}";
                IOBUF PORT "{{port_name}}"
                    {%- for key, value in extras.items() %} {{key}}={{value}}{% endfor %};
            {% endfor %}
            {% for signal, frequency in platform.iter_clock_constraints() -%}
                FREQUENCY PORT "{{signal.name}}" {{frequency}} HZ;
            {% endfor %}
        """
    }
    _trellis_command_templates = [
        r"""
        {{get_tool("yosys")}}
            {{quiet("-q")}}
            {{get_override("yosys_opts")|options}}
            -l {{name}}.rpt
            {{name}}.ys
        """,
        r"""
        {{get_tool("nextpnr-ecp5")}}
            {{quiet("--quiet")}}
            {{get_override("nextpnr_opts")|options}}
            --log {{name}}.tim
            {{platform._nextpnr_device_options[platform.device]}}
            --package {{platform._nextpnr_package_options[platform.package]|upper}}
            --speed {{platform.speed}}
            --json {{name}}.json
            --lpf {{name}}.lpf
            --textcfg {{name}}.config
        """,
        r"""
        {{get_tool("ecppack")}}
            {{verbose("--verbose")}}
            {{get_override("ecppack_opts")|options}}
            --input {{name}}.config
            --bit {{name}}.bit
            --svf {{name}}.svf
        """
    ]

    # Diamond templates

    _diamond_file_templates = {
        **TemplatedPlatform.build_script_templates,
        "build_{{name}}.sh": r"""
            # {{autogenerated}}
            set -e{{verbose("x")}}
            if [ -z "$BASH" ] ; then exec /bin/bash "$0" "$@"; fi
            if [ -n "$NMIGEN_{{platform.toolchain}}_env" ]; then
                bindir=$(dirname "$NMIGEN_{{platform.toolchain}}_env")
                . "$NMIGEN_{{platform.toolchain}}_env"
            fi
            {{emit_commands("sh")}}
        """,
        "{{name}}.v": r"""
            /* {{autogenerated}} */
            {{emit_design("verilog")}}
        """,
        "{{name}}.tcl": r"""
            prj_project new -name "{{name}}" -impl "impl" -impl_dir "top_impl" \
                -dev {{platform.device}}-{{platform.speed}}{{platform.package}}{{platform.grade}} \
                -lpf "{{name}}.lpf" \
                -synthesis synplify
            {% for file in platform.iter_extra_files(".v", ".sv", ".vhd", ".vhdl") -%}
                prj_src add "{{file}}"
            {% endfor %}
            prj_src add "{{name}}.v"
            prj_impl option top "{{name}}"
            prj_src add "{{name}}.sdc"
            {{get_override("script_project")|default("# (script_project placeholder)")}}
            prj_project save
            prj_run Synthesis -impl "impl" -forceAll
            prj_run Translate -impl "impl" -forceAll
            prj_run Map -impl "impl" -forceAll
            prj_run PAR -impl "impl" -forceAll
            prj_run Export -impl "impl" -forceAll -task Bitgen
            {{get_override("script_after_export")|default("# (script_after_export placeholder)")}}
        """,
        "{{name}}.lpf": r"""
            # {{autogenerated}}
            BLOCK ASYNCPATHS;
            BLOCK RESETPATHS;
            {% for port_name, pin_name, extras in platform.iter_port_constraints_bits() -%}
                LOCATE COMP "{{port_name}}" SITE "{{pin_name}}";
                IOBUF PORT "{{port_name}}"
                    {%- for key, value in extras.items() %} {{key}}={{value}}{% endfor %};
            {% endfor %}
            {% for signal, frequency in platform.iter_clock_constraints() -%}
                FREQUENCY PORT "{{signal.name}}" {{frequency/1000000}} MHZ;
            {% endfor %}
            {{get_override("add_preferences")|default("# (add_preferences placeholder)")}}
        """,
        "{{name}}.sdc": r"""
            {% for signal, frequency in platform.iter_clock_constraints() -%}
                create_clock -period {{1000000000/frequency}} [get_ports {{signal.name}}]
            {% endfor %}
            {{get_override("add_constraints")|default("# (add_constraints placeholder)")}}
        """,
    }
    _diamond_command_templates = [
        # These don't have any usable command-line option overrides.
        r"""
        {{get_tool("pnmainc")}}
            {{name}}.tcl
        """,
        r"""
        {{get_tool("ddtcmd")}}
            -oft -bit
            -if {{name}}_impl/{{name}}_impl.bit -of {{name}}.bit
        """,
        r"""
        {{get_tool("ddtcmd")}}
            -oft -svfsingle -revd -op "Fast Program"
            -if {{name}}_impl/{{name}}_impl.bit -of {{name}}.svf
        """,
    ]

    # Common logic

    def __init__(self, *, toolchain="Trellis"):
        super().__init__()

        assert toolchain in ("Trellis", "Diamond")
        self.toolchain = toolchain

    @property
    def required_tools(self):
        if self.toolchain == "Trellis":
            return ["yosys", "nextpnr-ecp5", "ecppack"]
        if self.toolchain == "Diamond":
            return ["pnmainc", "ddtcmd"]
        assert False

    @property
    def file_templates(self):
        if self.toolchain == "Trellis":
            return self._trellis_file_templates
        if self.toolchain == "Diamond":
            return self._diamond_file_templates
        assert False

    @property
    def command_templates(self):
        if self.toolchain == "Trellis":
            return self._trellis_command_templates
        if self.toolchain == "Diamond":
            return self._diamond_command_templates
        assert False

    def create_missing_domain(self, name):
        # Lattice ECP devices have two global set/reset signals: PUR, which is driven at startup
        # by the configuration logic and unconditionally resets every storage element, and GSR,
        # which is driven by user logic and each storage element may be configured as affected or
        # unaffected by GSR. PUR is purely asynchronous, so even though it is a low-skew global
        # network, its deassertion may violate a setup/hold constraint with relation to a user
        # clock. To avoid this, a GSR/SGSR instance should be driven synchronized to user clock.
        if name == "sync" and self.default_clk is not None:
            clk_i = self.request(self.default_clk).i
            if self.default_rst is not None:
                rst_i = self.request(self.default_rst).i
            else:
                rst_i = Const(0)

            gsr0 = Signal()
            gsr1 = Signal()
            m = Module()
            # There is no end-of-startup signal on ECP5, but PUR is released after IOB enable, so
            # a simple reset synchronizer (with PUR as the asynchronous reset) does the job.
            m.submodules += [
                Instance("FD1S3AX", p_GSR="DISABLED", i_CK=clk_i, i_D=~rst_i, o_Q=gsr0),
                Instance("FD1S3AX", p_GSR="DISABLED", i_CK=clk_i, i_D=gsr0,   o_Q=gsr1),
                # Although we already synchronize the reset input to user clock, SGSR has dedicated
                # clock routing to the center of the FPGA; use that just in case it turns out to be
                # more reliable. (None of this is documented.)
                Instance("SGSR", i_CLK=clk_i, i_GSR=gsr1),
            ]
            # GSR implicitly connects to every appropriate storage element. As such, the sync
            # domain is reset-less; domains driven by other clocks would need to have dedicated
            # reset circuitry or otherwise meet setup/hold constraints on their own.
            m.domains += ClockDomain("sync", reset_less=True)
            m.d.comb += ClockSignal("sync").eq(clk_i)
            return m

    _single_ended_io_types = [
        "HSUL12", "LVCMOS12", "LVCMOS15", "LVCMOS18", "LVCMOS25", "LVCMOS33", "LVTTL33",
        "SSTL135_I", "SSTL135_II", "SSTL15_I", "SSTL15_II", "SSTL18_I", "SSTL18_II",
    ]
    _differential_io_types = [
        "BLVDS25", "BLVDS25E", "HSUL12D", "LVCMOS18D", "LVCMOS25D", "LVCMOS33D",
        "LVDS", "LVDS25E", "LVPECL33", "LVPECL33E", "LVTTL33D", "MLVDS", "MLVDS25E",
        "SLVS", "SSTL135D_II", "SSTL15D_II", "SSTL18D_II", "SUBLVDS",
    ]

    def should_skip_port_component(self, port, attrs, component):
        # On ECP5, a differential IO is placed by only instantiating an IO buffer primitive at
        # the PIOA or PIOC location, which is always the non-inverting pin.
        if attrs.get("IO_TYPE", "LVCMOS25") in self._differential_io_types and component == "n":
            return True
        return False

    def _get_xdr_buffer(self, m, pin, *, i_invert=False, o_invert=False):
        def get_ireg(clk, d, q):
            for bit in range(len(q)):
                m.submodules += Instance("IFS1P3DX",
                    i_SCLK=clk,
                    i_SP=Const(1),
                    i_CD=Const(0),
                    i_D=d[bit],
                    o_Q=q[bit]
                )

        def get_oreg(clk, d, q):
            for bit in range(len(q)):
                m.submodules += Instance("OFS1P3DX",
                    i_SCLK=clk,
                    i_SP=Const(1),
                    i_CD=Const(0),
                    i_D=d[bit],
                    o_Q=q[bit]
                )

        def get_iddr(sclk, d, q0, q1):
            for bit in range(len(d)):
                m.submodules += Instance("IDDRX1F",
                    i_SCLK=sclk,
                    i_RST=Const(0),
                    i_D=d[bit],
                    o_Q0=q0[bit], o_Q1=q1[bit]
                )

        def get_oddr(sclk, d0, d1, q):
            for bit in range(len(q)):
                m.submodules += Instance("ODDRX1F",
                    i_SCLK=sclk,
                    i_RST=Const(0),
                    i_D0=d0[bit], i_D1=d1[bit],
                    o_Q=q[bit]
                )

        def get_ineg(z, invert):
            if invert:
                a = Signal.like(z, name_suffix="_n")
                m.d.comb += z.eq(~a)
                return a
            else:
                return z

        def get_oneg(a, invert):
            if invert:
                z = Signal.like(a, name_suffix="_n")
                m.d.comb += z.eq(~a)
                return z
            else:
                return a

        if "i" in pin.dir:
            if pin.xdr < 2:
                pin_i  = get_ineg(pin.i,  i_invert)
            elif pin.xdr == 2:
                pin_i0 = get_ineg(pin.i0, i_invert)
                pin_i1 = get_ineg(pin.i1, i_invert)
        if "o" in pin.dir:
            if pin.xdr < 2:
                pin_o  = get_oneg(pin.o,  o_invert)
            elif pin.xdr == 2:
                pin_o0 = get_oneg(pin.o0, o_invert)
                pin_o1 = get_oneg(pin.o1, o_invert)

        i = o = t = None
        if "i" in pin.dir:
            i = Signal(pin.width, name="{}_xdr_i".format(pin.name))
        if "o" in pin.dir:
            o = Signal(pin.width, name="{}_xdr_o".format(pin.name))
        if pin.dir in ("oe", "io"):
            t = Signal(1,         name="{}_xdr_t".format(pin.name))

        if pin.xdr == 0:
            if "i" in pin.dir:
                i = pin_i
            if "o" in pin.dir:
                o = pin_o
            if pin.dir in ("oe", "io"):
                t = ~pin_oe
        elif pin.xdr == 1:
            # Note that currently nextpnr will not pack an FF (*FS1P3DX) into the PIO.
            if "i" in pin.dir:
                get_ireg(pin.i_clk, i, pin_i)
            if "o" in pin.dir:
                get_oreg(pin.o_clk, pin_o, o)
            if pin.dir in ("oe", "io"):
                get_oreg(pin.o_clk, ~pin.oe, t)
        elif pin.xdr == 2:
            if "i" in pin.dir:
                get_iddr(pin.i_clk, i, pin_i0, pin_i1)
            if "o" in pin.dir:
                get_oddr(pin.o_clk, pin_o0, pin_o1, o)
            if pin.dir in ("oe", "io"):
                # It looks like Diamond will not pack an OREG as a tristate register in a DDR PIO.
                # It is not clear what is the recommended set of primitives for this task.
                # Similarly, nextpnr will not pack anything as a tristate register in a DDR PIO.
                get_oreg(pin.o_clk, ~pin.oe, t)
        else:
            assert False

        return (i, o, t)

    def get_input(self, pin, port, attrs, invert):
        self._check_feature("single-ended input", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, i_invert=invert)
        for bit in range(len(port)):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("IB",
                i_I=port[bit],
                o_O=i[bit]
            )
        return m

    def get_output(self, pin, port, attrs, invert):
        self._check_feature("single-ended output", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, o_invert=invert)
        for bit in range(len(port)):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("OB",
                i_I=o[bit],
                o_O=port[bit]
            )
        return m

    def get_tristate(self, pin, port, attrs, invert):
        self._check_feature("single-ended tristate", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, o_invert=invert)
        for bit in range(len(port)):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("OBZ",
                i_T=t,
                i_I=o[bit],
                o_O=port[bit]
            )
        return m

    def get_input_output(self, pin, port, attrs, invert):
        self._check_feature("single-ended input/output", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, i_invert=invert, o_invert=invert)
        for bit in range(len(port)):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("BB",
                i_T=t,
                i_I=o[bit],
                o_O=i[bit],
                io_B=port[bit]
            )
        return m

    def get_diff_input(self, pin, p_port, n_port, attrs, invert):
        self._check_feature("differential input", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, i_invert=invert)
        for bit in range(len(p_port)):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("IB",
                i_I=p_port[bit],
                o_O=i[bit]
            )
        return m

    def get_diff_output(self, pin, p_port, n_port, attrs, invert):
        self._check_feature("differential output", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, o_invert=invert)
        for bit in range(len(p_port)):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("OB",
                i_I=o[bit],
                o_O=p_port[bit],
            )
        return m

    def get_diff_tristate(self, pin, p_port, n_port, attrs, invert):
        self._check_feature("differential tristate", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, o_invert=invert)
        for bit in range(len(p_port)):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("OBZ",
                i_T=t,
                i_I=o[bit],
                o_O=p_port[bit],
            )
        return m

    def get_diff_input_output(self, pin, p_port, n_port, attrs, invert):
        self._check_feature("differential input/output", pin, attrs,
                            valid_xdrs=(0, 1, 2), valid_attrs=True)
        m = Module()
        i, o, t = self._get_xdr_buffer(m, pin, i_invert=invert, o_invert=invert)
        for bit in range(len(p_port)):
            m.submodules["{}_{}".format(pin.name, bit)] = Instance("BB",
                i_T=t,
                i_I=o[bit],
                o_O=i[bit],
                io_B=p_port[bit],
            )
        return m
