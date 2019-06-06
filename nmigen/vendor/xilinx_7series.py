from abc import abstractproperty

from ..hdl.ast import *
from ..hdl.dsl import *
from ..hdl.ir import *
from ..build import *


__all__ = ["Xilinx7SeriesPlatform"]


class Xilinx7SeriesPlatform(TemplatedPlatform):
    """
    Required tools:
        * ``vivado``

    Available overrides:
        * ``script_after_read``: inserts commands after ``read_xdc`` in Tcl script.
        * ``script_after_synth``: inserts commands after ``synth_design`` in Tcl script.
        * ``script_after_place``: inserts commands after ``place_design`` in Tcl script.
        * ``script_after_route``: inserts commands after ``route_design`` in Tcl script.
        * ``script_before_bitstream``: inserts commands before ``write_bitstream`` in Tcl script.
        * ``script_after_bitstream``: inserts commands after ``write_bitstream`` in Tcl script.
        * ``add_constraints``: inserts commands in XDC file.
        * ``vivado_opts``: adds extra options for Vivado.

    Build products:
        * ``{{name}}.log``: Vivado log.
        * ``{{name}}_timing_synth.rpt``: Vivado report.
        * ``{{name}}_utilization_hierarchical_synth.rpt``: Vivado report.
        * ``{{name}}_utilization_synth.rpt``: Vivado report.
        * ``{{name}}_utilization_hierarchical_place.rpt``: Vivado report.
        * ``{{name}}_utilization_place.rpt``: Vivado report.
        * ``{{name}}_io.rpt``: Vivado report.
        * ``{{name}}_control_sets.rpt``: Vivado report.
        * ``{{name}}_clock_utilization.rpt``:  Vivado report.
        * ``{{name}}_route_status.rpt``: Vivado report.
        * ``{{name}}_drc.rpt``: Vivado report.
        * ``{{name}}_timing.rpt``: Vivado report.
        * ``{{name}}_power.rpt``: Vivado report.
        * ``{{name}}_route.dcp``: Vivado design checkpoint.
        * ``{{name}}.bit``: binary bitstream.
    """

    device = abstractproperty()
    package = abstractproperty()
    speedgrade = abstractproperty()

    file_templates = {
        **TemplatedPlatform.build_script_templates,
        "{{name}}.v": r"""
            /* {{autogenerated}} */
            {{emit_design("verilog")}}
        """,
        "{{name}}.tcl": r"""
            # {{autogenerated}}
            create_project -force -name {{name}} -part {{platform.device}}{{platform.package}}-{{platform.speedgrade}}
            {% for file in platform.extra_files %}
                {% if file.endswith((".v", ".sv")) -%}
                    add_files {{file}}
                {% endif %}
            {% endfor %}
            add_files {{name}}.v
            read_xdc {{name}}.xdc
            {{get_override("script_after_read")|default("# (script_after_read placeholder)")}}
            synth_design -top {{name}} -part {{platform.device}}{{platform.package}}-{{platform.speedgrade}}
            {{get_override("script_after_synth")|default("# (script_after_synth placeholder)")}}
            report_timing_summary -file {{name}}_timing_synth.rpt
            report_utilization -hierarchical -file {{name}}_utilization_hierachical_synth.rpt
            report_utilization -file {{name}}_utilization_synth.rpt
            opt_design
            place_design
            {{get_override("script_after_place")|default("# (script_after_place placeholder)")}}
            report_utilization -hierarchical -file {{name}}_utilization_hierarchical_place.rpt
            report_utilization -file {{name}}_utilization_place.rpt
            report_io -file {{name}}_io.rpt
            report_control_sets -verbose -file {{name}}_control_sets.rpt
            report_clock_utilization -file {{name}}_clock_utilization.rpt
            route_design
            {{get_override("script_after_route")|default("# (script_after_route placeholder)")}}
            phys_opt_design
            report_timing_summary -no_header -no_detailed_paths
            write_checkpoint -force {{name}}_route.dcp
            report_route_status -file {{name}}_route_status.rpt
            report_drc -file {{name}}_drc.rpt
            report_timing_summary -datasheet -max_paths 10 -file {{name}}_timing.rpt
            report_power -file {{name}}_power.rpt
            {{get_override("script_before_bitstream")|default("# (script_before_bitstream placeholder)")}}
            write_bitstream -force {{name}}.bit
            {{get_override("script_after_bitstream")|default("# (script_after_bitstream placeholder)")}}
            quit
        """,
        "{{name}}.xdc": r"""
            # {{autogenerated}}
            {% for port_name, pin_name, attrs in platform.iter_port_constraints_bits() -%}
                set_property LOC {{pin_name}} [get_ports {{port_name}}]
                {% for attr_name, attr_value in attrs.items() -%}
                    set_property {{attr_name}} {{attr_value}} [get_ports {{port_name}}]
                {% endfor %}
            {% endfor %}
            {% for signal, frequency in platform.iter_clock_constraints() -%}
                create_clock -name {{signal.name}} -period {{1000000000/frequency}} [get_ports {{signal.name}}]
            {% endfor %}
            {{get_override("add_constraints")|default("# (add_constraints placeholder)")}}
        """
    }
    command_templates = [
        r"""
        {{get_tool("vivado")}}
            {{verbose("-verbose")}}
            {{get_override("vivado_opts")|join(" ")}}
            -mode batch
            -log {{name}}.log
            -source {{name}}.tcl
        """
    ]

    def _get_dff(self, m, clk, d, q):
        # SDR I/O is performed by packing a flip-flop into the pad IOB.
        for bit in range(len(q)):
            _q = Signal()
            _q.attrs["IOB"] = "TRUE"
            m.submodules += Instance("FDCE",
                i_C=clk,
                i_CE=Const(1),
                i_CLR=Const(0),
                i_D=d[bit],
                o_Q=_q,
            )
            m.d.comb += q[bit].eq(_q)

    def get_input(self, pin, port, attrs):
        self._check_feature("single-ended input", pin, attrs,
                            valid_xdrs=(0, 1), valid_attrs=True)
        m = Module()
        if pin.xdr == 1:
            self._get_dff(m, pin.i_clk, port, pin.i)
        else:
            m.d.comb += pin.i.eq(port)
        return m

    def get_output(self, pin, port, attrs):
        self._check_feature("single-ended output", pin, attrs,
                            valid_xdrs=(0, 1), valid_attrs=True)
        m = Module()
        if pin.xdr == 1:
            self._get_dff(m, pin.o_clk, pin.o, port)
        else:
            m.d.comb += port.eq(pin.o)
        return m

    def get_tristate(self, pin, port, attrs):
        self._check_feature("single-ended tristate", pin, attrs,
                            valid_xdrs=(0, 1), valid_attrs=True)
        m = Module()
        if pin.xdr == 1:
            o_ff = Signal.like(pin.o, name="{}_ff".format(pin.o.name))
            oe_ff = Signal.like(pin.oe, name="{}_ff".format(pin.oe.name))
            self._get_dff(m, pin.o_clk, pin.o, o_ff)
            self._get_dff(m, pin.o_clk, pin.oe, oe_ff)
        for bit in range(len(port)):
            m.submodules += Instance("OBUFT",
                i_T=~(oe_ff if pin.xdr == 1 else pin.oe),
                i_I=o_ff[bit] if pin.xdr == 1 else pin.o[bit],
                o_O=port[bit]
            )
        return m

    def get_input_output(self, pin, port, attrs):
        self._check_feature("single-ended input/output", pin, attrs,
                            valid_xdrs=(0, 1), valid_attrs=True)
        m = Module()
        if pin.xdr == 1:
            o_ff = Signal.like(pin.o, name="{}_ff".format(pin.o.name))
            oe_ff = Signal.like(pin.oe, name="{}_ff".format(pin.oe.name))
            i_ff = Signal.like(pin.i, name="{}_ff".format(pin.i.name))
            self._get_dff(m, pin.o_clk, pin.o, o_ff)
            self._get_dff(m, pin.o_clk, pin.oe, oe_ff)
            self._get_dff(m, pin.i_clk, i_ff, pin.i)
        for bit in range(len(port)):
            m.submodules += Instance("IOBUF",
                i_T=~(oe_ff if pin.xdr == 1 else pin.oe),
                i_I=o_ff[bit] if pin.xdr == 1 else pin.o[bit],
                o_O=i_ff[bit] if pin.xdr == 1 else pin.i[bit],
                io_IO=port[bit]
            )
        return m

    def get_diff_input(self, pin, p_port, n_port, attrs):
        self._check_feature("differential input", pin, attrs,
                            valid_xdrs=(0, 1), valid_attrs=True)
        m = Module()
        if pin.xdr == 1:
            i_ff = Signal.like(pin.i, name="{}_ff".format(pin.i.name))
            self._get_dff(m, pin.i_clk, i_ff, pin.i)
        for bit in range(len(p_port)):
            m.submodules += Instance("IBUFDS",
                i_I=p_port[bit],
                i_IB=n_port[bit],
                o_O=i_ff[bit] if pin.xdr == 1 else pin.i[bit]
            )
        return m

    def get_diff_output(self, pin, p_port, n_port, attrs):
        self._check_feature("differential output", pin, attrs,
                            valid_xdrs=(0, 1), valid_attrs=True)
        m = Module()
        if pin.xdr == 1:
            o_ff = Signal.like(pin.o, name="{}_ff".format(pin.o.name))
            self._get_dff(m, pin.o_clk, pin.o, o_ff)
        for bit in range(len(p_port)):
            m.submodules += Instance("OBUFDS",
                o_O=p_port[bit],
                o_OB=n_port[bit],
                i_I=o_ff[bit] if pin.xdr == 1 else pin.o[bit]
            )
        return m

    def get_diff_tristate(self, pin, p_port, n_port, attrs):
        self._check_feature("differential tristate", pin, attrs,
                            valid_xdrs=(0, 1), valid_attrs=True)
        m = Module()
        if pin.xdr == 1:
            o_ff = Signal.like(pin.o, name="{}_ff".format(pin.o.name))
            oe_ff = Signal.like(pin.oe, name="{}_ff".format(pin.oe.name))
            self._get_dff(m, pin.o_clk, pin.o, o_ff)
            self._get_dff(m, pin.o_clk, pin.oe, oe_ff)
        for bit in range(len(p_port)):
            m.submodules += Instance("OBUFTDS",
                i_T=~(oe_ff if pin.xdr == 1 else pin.oe),
                i_I=o_ff[bit] if pin.xdr == 1 else pin.o[bit],
                o_O=p_port[bit],
                o_OB=n_port[bit]
            )
        return m

    def get_diff_input_output(self, pin, p_port, n_port, attrs):
        self._check_feature("differential input/output", pin, attrs,
                            valid_xdrs=(0, 1), valid_attrs=True)
        m = Module()
        if pin.xdr == 1:
            o_ff = Signal.like(pin.o, name="{}_ff".format(pin.o.name))
            oe_ff = Signal.like(pin.oe, name="{}_ff".format(pin.oe.name))
            i_ff = Signal.like(pin.i, name="{}_ff".format(pin.i.name))
            self._get_dff(m, pin.o_clk, pin.o, o_ff)
            self._get_dff(m, pin.o_clk, pin.oe, oe_ff)
            self._get_dff(m, pin.i_clk, i_ff, pin.i)
        for bit in range(len(p_port)):
            m.submodules += Instance("IOBUFDS",
                i_T=~(oe_ff if pin.xdr == 1 else pin.oe),
                i_I=o_ff[bit] if pin.xdr == 1 else pin.o[bit],
                o_O=i_ff[bit] if pin.xdr == 1 else pin.i[bit],
                io_IO=p_port[bit],
                io_IOB=n_port[bit]
            )
        return m
