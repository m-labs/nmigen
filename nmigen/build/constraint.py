from collections import OrderedDict

from .. import *
from ..hdl.rec import *
from ..lib.io import *

from .dsl import *
from .tools import *


__all__ = ["ConstraintError", "ConstraintManager"]


class ConstraintError(Exception):
    pass


class ConstraintManager:
    def __init__(self, resources):
        self.resources  = OrderedDict()
        self.requested  = OrderedDict()
        self.clocks     = OrderedDict()

        self._ports     = []
        self._tristates = []
        self._diffpairs = []

        self.add_resources(resources)

    def add_resources(self, resources):
        for r in resources:
            if not isinstance(r, Resource):
                raise TypeError("Object {!r} is not a Resource".format(r))
            if (r.name, r.number) in self.resources:
                raise NameError("Trying to add {!r}, but {!r} has the same name and number"
                                .format(r, self.resources[r.name, r.number]))
            self.resources[r.name, r.number] = r

    def add_period(self, name, number, period):
        resource = self.lookup(name, number)
        if isinstance(resource.io[0], Subsignal):
            raise ConstraintError("Cannot constrain period of resource (\"{}\", {}) because it has "
                                  "subsignals"
                                  .format(resource.name, resource.number, period))
        if (resource.name, resource.number) in self.clocks:
            other = self.clocks[resource.name, resource.number]
            raise ConstraintError("Resource (\"{}\", {}) is already constrained to a period of {} ns"
                                  .format(resource.name, resource.number, other))
        self.clocks[resource.name, resource.number] = period

    def lookup(self, name, number):
        if (name, number) not in self.resources:
            raise NameError("No available resource with name \"{}\" and number {}"
                            .format(name, number))
        return self.resources[name, number]

    def request(self, name, number, dir=None):
        # TODO: add xdr support
        resource = self.lookup(name, number)
        if (resource.name, resource.number) in self.requested:
            raise ConstraintError("Resource (\"{}\", {}) has already been requested"
                                  .format(name, number))

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

        def get_value(subsignal, dir, name):
            if isinstance(subsignal.io[0], Subsignal):
                # FIXME: temporary workaround to have Pin instances as Record fields
                fields = OrderedDict()
                for sub in subsignal.io:
                    fields[sub.name] = get_value(sub, dir[sub.name], "{}__{}".format(name, sub.name))
                rec = Record([(f_name, f.layout) for (f_name, f) in fields.items()], name=name)
                rec.fields.update(fields)
                return rec
            elif isinstance(subsignal.io[0], DiffPairs):
                pairs = subsignal.io[0]
                return Pin(len(pairs.p.names), dir, name=name)
            else:
                pins = subsignal.io[0]
                return Pin(len(pins.names), dir, name=name)

        value_name = "{}_{}".format(resource.name, resource.number)
        value = get_value(resource, dir, value_name)

        def match_constraints(value, subsignal):
            if isinstance(subsignal.io[0], Subsignal):
                for sub in subsignal.io:
                    yield from match_constraints(value[sub.name], sub)
            else:
                assert isinstance(value, Pin)
                yield (value, subsignal.io[0], subsignal.extras)

        for (pin, io, extras) in match_constraints(value, resource):
            if isinstance(io, DiffPairs):
                p = Signal(pin.width, name="{}_p".format(pin.name))
                n = Signal(pin.width, name="{}_n".format(pin.name))
                self._diffpairs.append((pin, p, n))
                self._ports += (
                    (p, io.p.names, extras),
                    (n, io.n.names, extras)
                )
            else:
                if pin.dir == "io":
                    port = Signal(pin.width, name="{}_io".format(pin.name))
                    self._tristates.append((pin, port))
                else:
                    port = getattr(pin, pin.dir)
                self._ports.append((port, io.names, extras))

        self.requested[resource.name, resource.number] = value
        return value

    def get_ports(self):
        ports = []
        for port, pins, extras in self._ports:
            ports.append(port)
        return ports

    def get_port_constraints(self):
        constraints = []
        for port, pins, extras in self._ports:
            constraints.append((yosys_id_escape(port.name), pins, extras))
        return constraints

    def get_period_constraints(self):
        constraints = []
        for name, number in self.clocks.keys() & self.requested.keys():
            resource = self.resources[name, number]
            pin = self.requested[name, number]
            period = self.clocks[name, number]
            if pin.dir == "io":
                raise ConstraintError("Cannot constrain period of resource (\"{}\", {}) because "
                                      "it has been requested as a tristate buffer"
                                      .format(name, number))
            if isinstance(resource.io[0], DiffPairs):
                port_name = "{}_p".format(pin.name)
            else:
                port_name = getattr(pin, pin.dir).name
            constraints.append((yosys_id_escape(port_name), period))
        return constraints
