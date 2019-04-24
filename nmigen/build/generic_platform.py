from collections import defaultdict, OrderedDict

from .. import *
from ..hdl.rec import *
from ..lib.io import *

from .dsl import *
from .tools import *


__all__ = ["ConstraintError", "GenericPlatform"]


class ConstraintError(Exception):
    pass


class _ConstraintManager:
    def __init__(self, resources):
        self.available    = defaultdict(dict)
        self.matched      = OrderedDict()
        self.clocks       = OrderedDict()
        self.tristates    = []
        self.diffpairs    = []
        self.ports        = []
        self.inouts       = []

        self.add_resources(resources)

    def add_resources(self, resources):
        for r in resources:
            if not isinstance(r, Resource):
                raise TypeError("Object {!r} is not a Resource".format(r))
            if r.number in self.available[r.name]:
                raise NameError("Trying to add {!r}, but {!r} has the same name and number"
                                .format(r, self.available[r.name][r.number]))
            self.available[r.name][r.number] = r

    def add_period(self, resource, period):
        if not isinstance(resource, Resource):
            raise TypeError("Object {!r} is not a Resource".format(resource))
        if isinstance(resource.io[0], Subsignal):
            raise ConstraintError("Cannot constrain Resource ('{}', {}) to a period of {} ns "
                                  "because it has subsignals"
                                  .format(resource.name, resource.number, period))
        if (resource.name, resource.number) in self.clocks:
            other = self.clocks[resource.name, resource.number]
            raise ConstraintError("Resource ('{}', {}) is already constrained to a period of {} ns"
                                  .format(resource.name, resource.number, other))
        self.clocks[resource.name, resource.number] = period

    def lookup(self, name, number=None):
        if number is None and self.available[name]:
            number = sorted(self.available[name])[0]
        elif number not in self.available[name]:
            raise NameError("No available Resource with name '{}' and number {}"
                            .format(name, number))
        return self.available[name][number]

    def request(self, name, number=None, dir=None):
        # TODO: add xdr support
        resource = self.lookup(name, number=number)
        assert (resource.name, resource.number) not in self.matched

        def resolve_dir(subsignal, dir):
            if isinstance(subsignal.io[0], Subsignal):
                if dir is None:
                    dir = dict()
                if not isinstance(dir, dict):
                    raise TypeError("Directions must be a dict, not {!r}, because {!r} "
                                    "has subsignals"
                                    .format(dir, subsignal))
                for sub in subsignal.io:
                    sub_dir = dir.get(sub.name, None)
                    dir[sub.name] = resolve_dir(sub, sub_dir)
            else:
                if dir is None:
                    dir = subsignal.io[0].dir
                if dir not in ("i", "o", "io"):
                    raise TypeError("Direction must be one of \"i\", \"o\" or \"io\", not {!r}"
                                    .format(dir))
                if subsignal.io[0].dir != "io" and dir != subsignal.io[0].dir:
                    raise ValueError("Direction \"{}\" cannot be changed to \"{}\"; Valid changes "
                                     "are \"io\"->\"i\", \"io\"->\"o\""
                                     .format(subsignal.io[0].dir, dir))
            return dir

        dir = resolve_dir(resource, dir)

        def get_port(subsignal, dir, name):
            if isinstance(subsignal.io[0], Subsignal):
                # FIXME: temporary workaround to have Pin instances as Record fields
                fields = []
                sub_ports = dict()
                for sub in subsignal.io:
                    sub_port = get_port(sub, dir[sub.name], "{}__{}".format(name, sub.name))
                    fields.append((sub.name, sub_port.layout))
                    sub_ports[sub.name] = sub_port
                port = Record(fields, name=name)
                port.fields.update(sub_ports)
                return port
            elif isinstance(subsignal.io[0], DiffPairs):
                pairs = subsignal.io[0]
                return Pin(len(pairs.p.names), dir, name=name)
            else:
                pins = subsignal.io[0]
                return Pin(len(pins.names), dir, name=name)

        port_name = "{}_{}".format(resource.name, resource.number)
        port = get_port(resource, dir, port_name)

        def match_port(port, subsignal, dir):
            if isinstance(subsignal.io[0], Subsignal):
                for sub in subsignal.io:
                    match_port(port[sub.name], sub, dir[sub.name])
            elif isinstance(subsignal.io[0], DiffPairs):
                pairs = subsignal.io[0]
                p = Signal.like(port, name=port.name + "_p")
                n = Signal.like(port, name=port.name + "_n")
                self.diffpairs.append((port, p, n, dir))
                if dir == "io":
                    self.inouts += (p, pairs.p, subsignal.extras), (n, pairs.n, subsignal.extras)
                else:
                    self.ports += (p, pairs.p, subsignal.extras), (n, pairs.n, subsignal.extras)
            else:
                pins = subsignal.io[0]
                if dir == "io":
                    inout = Signal(port.width, name=port.name + "_io")
                    self.tristates.append((port, inout))
                    self.inouts.append((inout, pins, subsignal.extras))
                else:
                    self.ports.append((getattr(port, dir), pins, subsignal.extras))

        match_port(port, resource, dir)

        del self.available[resource.name][resource.number]
        self.matched[resource.name, resource.number] = port, dir
        return port

    def get_ports(self):
        ports = []
        for port, pins, extras in self.ports:
            ports.append(port)
        return ports

    def get_port_constraints(self):
        constraints = []
        for port, pins, extras in self.ports:
            constraints.append((yosys_id_escape(port.name), pins.names, extras))
        for inout, pins, extras in self.inouts:
            constraints.append((yosys_id_escape(inout.name), pins.names, extras))
        return constraints

    def get_period_constraints(self):
        constraints = []
        for k in self.clocks.keys() & self.matched.keys():
            period = self.clocks[k]
            port, dir = self.matched[k]
            port_name = getattr(port, dir).name
            constraints.append((yosys_id_escape(port_name), period))
        return constraints


class GenericPlatform(_ConstraintManager):
    def __init__(self, device, resources):
        super().__init__(resources)

        self.device  = device

    def prepare(self, fragment):
        assert hasattr(self, "default_clk_name")

        if hasattr(self, "default_clk_period"):
            self.add_period(self.lookup(self.default_clk_name), self.default_clk_period)

        default_clk = self.request(self.default_clk_name)

        fragment = Fragment.get(fragment, self)
        fragment.add_subfragment(Fragment.get(CRG(default_clk), self))

        for port, p, n, dir in self.diffpairs:
            if dir == "i":
                fragment.add_subfragment(self.get_diff_input(p, n, port))
            elif dir == "o":
                fragment.add_subfragment(self.get_diff_output(port, p, n))
            else:
                fragment.add_subfragment(self.get_diff_tristate(port, p, n))
        for port, inout in self.tristates:
            fragment.add_subfragment(self.get_tristate(port, inout))

        fragment.add_ports([inout for inout, pins, extras in self.inouts], dir="io")

        return fragment

    def build(self, *args, **kwargs):
        assert hasattr(self, "toolchain")
        self.toolchain.build(self, *args, **kwargs)

    def get_tristate(self, triple, io):
        raise NotImplementedError # :nocov:

    def get_diff_input(self, p, n, i):
        raise NotImplementedError # :nocov:

    def get_diff_output(self, o, p, n):
        raise NotImplementedError # :nocov:

    def get_diff_tristate(self, triple, p, n):
        raise NotImplementedError # :nocov:
