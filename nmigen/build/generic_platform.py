import edalize
import os
from collections import defaultdict, OrderedDict

from .. import *
from ..back import verilog
from ..hdl.rec import *
from ..lib.io import *


__all__ = [
    "Pins", "Subsignal", "DiffPairs", "Resource", "Connector",
    "ConstraintError", "GenericPlatform"
]


class Pins:
    def __init__(self, *identifiers, dir="io"):
        for i in identifiers:
            if not isinstance(i, str):
                raise TypeError("Identifier should be a string, not {!r}".format(i))
        self.identifiers = " ".join(identifiers).split(" ")

        if dir not in ("i", "o", "io"):
            raise TypeError("Direction should be either 'i', 'o' or 'io', not {!r}"
                            .format(dir))
        self.dir = dir

    def __len__(self):
        return len(self.identifiers)

    def __repr__(self):
        return "(pins {} '{}')".format(" ".join(self.identifiers), self.dir)


class DiffPairs:
    def __init__(self, *pairs, dir="io"):
        p, n = zip(*(pair.split(" ") for pair in pairs))
        self.p = Pins(*p, dir=dir)
        self.n = Pins(*n, dir=dir)

        self.dir = self.p.dir

    def __len__(self):
        return len(self.p)

    def __repr__(self):
        return "(diffpairs {} {})".format(self.p, self.n)


class Subsignal:
    def __init__(self, name, *io, extras=None):
        self.name = name

        self.has_pins       = len(io) == 1 and isinstance(io[0], Pins)
        self.has_diffpairs  = len(io) == 1 and isinstance(io[0], DiffPairs)
        self.has_subsignals = io and all(isinstance(c, Subsignal) for c in io)

        if not (self.has_pins or self.has_diffpairs or self.has_subsignals):
            raise TypeError("I/O constraints should be either Pins or DiffPairs or "
                            "multiple Subsignal, not {!r}"
                            .format(io))
        self.io = io

        extras = extras or []
        for c in extras:
            if not isinstance(c, str):
                raise TypeError("Extra contraint should be a string, not {!r}".format(c))
        self.extras = list(extras)

        if self.has_subsignals:
            for sub in self.io:
                sub.extras += self.extras

    def __repr__(self):
        return "(subsignal {} {} {})".format(self.name, " ".join(map(repr, self.io)), self.extras)


class Resource(Subsignal):
    def __init__(self, name, number, *io, extras=None):
        self.number = number
        super().__init__(name, *io, extras=extras)

    def __repr__(self):
        return "(resource {} {} {} {})".format(self.name, self.number, " ".join(map(repr, self.io)), self.extras)


class Connector:
    def __init__(self, name, description):
        self.name = name

        if isinstance(description, str):
            self.description = dict(enumerate(description.split(" ")))
        elif isinstance(description, list):
            self.description = dict(enumerate(description))
        elif isinstance(description, dict):
            self.description = description
        else:
            raise TypeError("Description should be either a whitespace-separated string, "
                            "a list or a dict, not {!r}"
                            .format(description))

        for alias, identifier in self.description.items():
            if not isinstance(identifier, str):
                raise TypeError("Identifier should be a string, not {!r}".format(identifier))
            elif identifier == "None":
                self.description[alias] = None

    def __getitem__(self, name):
        return self.description[name]

    def __repr__(self):
        return "(connector {} {})".format(self.name, self.description)


def _yosys_id_escape(s):
    if s[0] == "\\":
        s = s[1:]
    # TODO escape verilog keywords
    if s[0].isdigit() or not s.replace("_", "").isalnum():
        s = "\\{} ".format(s)
    return s


class ConstraintError(Exception):
    pass


class _ConstraintManager:
    def __init__(self, resources, connectors):
        self.available    = defaultdict(dict)
        self.matched      = OrderedDict()
        self.connectors   = dict()
        self.commands     = []
        self.clocks       = OrderedDict()
        self.constraints  = OrderedDict()
        self.tristates    = []
        self.diffpairs    = []
        self.ports        = []

        self.add_resources(resources)
        self.add_connectors(connectors)

    def add_resources(self, resources):
        for r in resources:
            if not isinstance(r, Resource):
                raise TypeError("Object {!r} is not a Resource".format(r))
            if r.number in self.available[r.name]:
                raise NameError("Resource {!r} has a (name, number) pair that is already taken"
                                .format(r))
            self.available[r.name][r.number] = r

    def add_connectors(self, connectors):
        for c in connectors:
            if not isinstance(c, Connector):
                raise TypeError("Object {!r} is not a Connector".format(c))
            if c.name in self.connectors:
                raise NameError("Connector {!r} has a name that is already taken".format(c))
            self.connectors[c.name] = c

    def add_command(self, command):
        if not isinstance(command, str):
            raise TypeError("Command must be a string, not {!r}".format(command))
        self.commands.append(command)

    def add_period_constraint(self, resource, period):
        if not isinstance(resource, Resource):
            raise TypeError("Object {!r} is not a Resource".format(resource))
        if (resource.name, resource.number) in self.clocks:
            raise ConstraintError("Resource {!r} is already constrained to a period"
                                  .format(resource))
        self.clocks[resource.name, resource.number] = period

    def lookup(self, name, number=None):
        if number is None and self.available[name]:
            number = sorted(self.available[name])[0]
        elif number not in self.available[name]:
            raise NameError("No available Resource with name '{}' and number '{}'"
                            .format(name, number))
        return self.available[name][number]

    def request_raw(self, name, number=None):
        resource = self.lookup(name, number=number)
        assert (resource.name, resource.number) not in self.matched

        def get_shape(subsignal):
            if subsignal.has_subsignals:
                return Layout([(s.name, get_shape(s)) for s in subsignal.io])
            elif subsignal.has_diffpairs:
                pair = subsignal.io[0]
                return Layout([("p", len(pair.p)), ("n", len(pair.n))])
            else:
                return len(subsignal.io[0])

        port_shape = get_shape(resource)
        port_name = "{}_{}".format(resource.name, resource.number)

        if isinstance(port_shape, Layout):
            port = Record(port_shape, name=port_name)
        else:
            port = Signal(port_shape, name=port_name)

        def add_constraints(port, subsignal):
            if subsignal.has_subsignals:
                for s in subsignal.io:
                    add_constraints(port[s.name], s)
            elif subsignal.has_diffpairs:
                self.constraints[_yosys_id_escape(port.p.name)] = subsignal.io[0].p, subsignal.extras
                self.constraints[_yosys_id_escape(port.n.name)] = subsignal.io[0].n, subsignal.extras
                self.ports += port.p, port.n
            else:
                self.constraints[_yosys_id_escape(port.name)] = subsignal.io[0], subsignal.extras
                self.ports.append(port)

        add_constraints(port, resource)

        del self.available[resource.name][resource.number]
        self.matched[resource.name, resource.number] = port
        return port

    def request(self, name, number=None, dir=None):
        resource = self.lookup(name, number=number)
        assert (resource.name, resource.number) not in self.matched

        def resolve_dir(subsignal, dir):
            if subsignal.has_subsignals:
                dir = dir or dict()
                if not isinstance(dir, dict):
                    raise TypeError("{} has subsignals. Directions should be a dict, not {!r}"
                                    .format(subsignal.name, dir))
                for s in subsignal.io:
                    dir[s.name] = resolve_dir(s, dir.get(s.name, None))
            else:
                dir = dir or subsignal.io[0].dir
                if dir not in ("i", "o", "io"):
                    raise TypeError("Direction should be either 'i', 'o' or 'io', not {!r}"
                                    .format(dir))
                if subsignal.io[0].dir != "io" and dir != subsignal.io[0].dir:
                    raise ValueError("Direction {} cannot be changed to {}. Valid changes are "
                                     "'io'->'i', 'io'->'o'."
                                     .format(subsignal.io[0].dir, dir))
            return dir

        dir = resolve_dir(resource, dir)

        def get_shape(subsignal, dir):
            if subsignal.has_subsignals:
                return Layout((s.name, get_shape(s, dir[s.name])) for s in subsignal.io)
            else:
                shape = len(subsignal.io[0])
                if dir == "io":
                    shape = Layout([("o", shape), ("oe", 1), ("i", shape)])
                return shape

        port_shape = get_shape(resource, dir)
        port_name = "{}_{}".format(resource.name, resource.number)

        if isinstance(port_shape, Layout):
            port = Record(port_shape, name=port_name)
        else:
            port = Signal(port_shape, name=port_name)

        def add_constraints(port, subsignal, dir):
            if subsignal.has_subsignals:
                for s in subsignal.io:
                    add_constraints(port[s.name], s, dir[s.name])
            elif subsignal.has_diffpairs:
                p = Signal.like(port, name=port.name + "_p")
                n = Signal.like(port, name=port.name + "_n")
                self.diffpairs.append((port, p, n, dir))
                self.constraints[_yosys_id_escape(p.name)] = subsignal.io[0].p, subsignal.extras
                self.constraints[_yosys_id_escape(n.name)] = subsignal.io[0].n, subsignal.extras
                self.ports += p, n
            elif dir == "io":
                inout = Signal.like(port.i, name=port.name + "_io")
                self.tristates.append((port, inout))
                self.constraints[_yosys_id_escape(inout.name)] = subsignal.io[0], subsignal.extras
            else:
                self.ports.append(port)
                self.constraints[_yosys_id_escape(port.name)] = subsignal.io[0], subsignal.extras

        add_constraints(port, resource, dir)

        del self.available[resource.name][resource.number]
        self.matched[resource.name, resource.number] = port
        return port

    def resolve_identifier(self, identifier):
        if ":" not in identifier:
            return identifier
        else:
            conn, pin = identifier.split(':')
            if pin.isdigit():
                pin = int(pin)
            return self.resolve_identifier(self.connectors[conn][pin])

    def get_port_constraints(self):
        constraints = []
        for port_name, (pins, extras) in self.constraints.items():
            identifiers = [self.resolve_identifier(i) for i in pins.identifiers]
            constraints.append((port_name, identifiers, extras))
        return constraints

    def get_period_constraints(self):
        constraints = []
        for k in self.matched.keys() & self.clocks.keys():
            port = self.matched[k]
            period = self.clocks[k]
            constraints.append((_yosys_id_escape(port.name), period))
        return constraints


class GenericPlatform(_ConstraintManager):
    def __init__(self, device, resources, connectors=[], name=None):
        super().__init__(resources, connectors)
        self.device       = device
        self.name         = name or self.__module__.split(".")[-1]
        self.files        = []
        self.tool_options = dict()

    def format_constraints(self):
        raise NotImplementedError # :nocov:

    def build(self, top, name="top", build_dir="build", **kwargs):
        assert hasattr(self, "default_clk_name")
        assert hasattr(self, "toolchain")

        if hasattr(self, "default_clk_period"):
            self.add_period_constraint(self.lookup(self.default_clk_name), self.default_clk_period)

        fragment = top.elaborate(self)
        fragment.submodules += CRG(self.request(self.default_clk_name))

        fragment = Fragment.get(fragment, self)
        inouts = []
        for port, inout in self.tristates:
            fragment.add_subfragment(Tristate(port, inout).elaborate(self))
            inouts.append(inout)
        for port, p, n, dir in self.diffpairs:
            if dir == "i":
                fragment.add_subfragment(self.get_diff_input(p, n, port))
            elif dir == "o":
                fragment.add_subfragment(self.get_diff_output(port, p, n))
            else:
                fragment.add_subfragment(self.get_diff_tristate(port, p, n))
                inouts += p, n
        fragment.add_ports(inouts, dir="io")

        os.makedirs(build_dir, exist_ok=True)
        cwd = os.getcwd()
        os.chdir(build_dir)

        verilog_text = verilog.convert(fragment, name, platform=self, **kwargs)
        with open("{}.v".format(name), "w") as f:
            f.write(verilog_text)
        self.files.append({"name": f.name, "file_type": "verilogSource"})

        constraints_text, constraints_info = self.format_constraints(name)
        with open(constraints_info["name"], "w") as f:
            f.write(constraints_text)
        self.files.append(constraints_info)

        os.chdir(cwd)

        edam = {
            "files":        self.files,
            "name":         name,
            "toplevel":     name,
            "tool_options": self.tool_options
        }

        backend = edalize.get_edatool(self.toolchain)(edam=edam, work_root=build_dir)
        backend.configure(None)
        backend.build()

    def get_diff_input(self, p, n, i):
        raise NotImplementedError # :nocov:

    def get_diff_output(self, o, p, n):
        raise NotImplementedError # :nocov:

    def get_diff_tristate(self, triple, p, n):
        raise NotImplementedError # :nocov:
