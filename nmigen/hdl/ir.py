from abc import ABCMeta, abstractmethod
from collections import defaultdict, OrderedDict
from functools import reduce
import warnings
import traceback
import sys

from ..tools import *
from .ast import *
from .cd import *


__all__ = ["UnusedElaboratable", "Elaboratable", "DriverConflict", "Fragment", "Instance"]


class UnusedElaboratable(Warning):
    pass


class Elaboratable(metaclass=ABCMeta):
    _Elaboratable__silence = False

    def __new__(cls, *args, src_loc_at=0, **kwargs):
        self = super().__new__(cls)
        self._Elaboratable__src_loc = traceback.extract_stack(limit=2 + src_loc_at)[0]
        self._Elaboratable__used    = False
        return self

    def __del__(self):
        if self._Elaboratable__silence:
            return
        if hasattr(self, "_Elaboratable__used") and not self._Elaboratable__used:
            warnings.warn_explicit("{!r} created but never used".format(self), UnusedElaboratable,
                                   filename=self._Elaboratable__src_loc.filename,
                                   lineno=self._Elaboratable__src_loc.lineno,
                                   source=self)


_old_excepthook = sys.excepthook
def _silence_elaboratable(type, value, traceback):
    # Don't show anything if the interpreter crashed; that'd just obscure the exception
    # traceback instead of helping.
    Elaboratable._Elaboratable__silence = True
    _old_excepthook(type, value, traceback)
sys.excepthook = _silence_elaboratable


class DriverConflict(UserWarning):
    pass


class Fragment:
    @staticmethod
    def get(obj, platform):
        while True:
            if isinstance(obj, Fragment):
                return obj
            elif isinstance(obj, Elaboratable):
                obj._Elaboratable__used = True
                obj = obj.elaborate(platform)
            elif hasattr(obj, "elaborate"):
                warnings.warn(
                    message="Class {!r} is an elaboratable that does not explicitly inherit from "
                            "Elaboratable; doing so would improve diagnostics"
                            .format(type(obj)),
                    category=RuntimeWarning,
                    stacklevel=2)
                obj = obj.elaborate(platform)
            else:
                if obj is not None:
                    raise AttributeError("Object '{!r}' cannot be elaborated".format(obj))
                else:
                    raise AttributeError("Object '{!r}' cannot be elaborated. Possible root cause: perhaps 'elaborate' doesn't return a module?".format(obj))

    def __init__(self):
        self.ports = SignalDict()
        self.drivers = OrderedDict()
        self.statements = []
        self.domains = OrderedDict()
        self.subfragments = []
        self.attrs = OrderedDict()
        self.generated = OrderedDict()
        self.flatten = False

    def add_ports(self, *ports, dir):
        assert dir in ("i", "o", "io")
        for port in flatten(ports):
            self.ports[port] = dir

    def iter_ports(self, dir=None):
        if dir is None:
            yield from self.ports
        else:
            for port, port_dir in self.ports.items():
                if port_dir == dir:
                    yield port

    def add_driver(self, signal, domain=None):
        if domain not in self.drivers:
            self.drivers[domain] = SignalSet()
        self.drivers[domain].add(signal)

    def iter_drivers(self):
        for domain, signals in self.drivers.items():
            for signal in signals:
                yield domain, signal

    def iter_comb(self):
        if None in self.drivers:
            yield from self.drivers[None]

    def iter_sync(self):
        for domain, signals in self.drivers.items():
            if domain is None:
                continue
            for signal in signals:
                yield domain, signal

    def iter_signals(self):
        signals = SignalSet()
        signals |= self.ports.keys()
        for domain, domain_signals in self.drivers.items():
            if domain is not None:
                cd = self.domains[domain]
                signals.add(cd.clk)
                if cd.rst is not None:
                    signals.add(cd.rst)
            signals |= domain_signals
        return signals

    def add_domains(self, *domains):
        for domain in flatten(domains):
            assert isinstance(domain, ClockDomain)
            assert domain.name not in self.domains
            self.domains[domain.name] = domain

    def iter_domains(self):
        yield from self.domains

    def add_statements(self, *stmts):
        self.statements += Statement.wrap(stmts)

    def add_subfragment(self, subfragment, name=None):
        assert isinstance(subfragment, Fragment)
        self.subfragments.append((subfragment, name))

    def find_subfragment(self, name_or_index):
        if isinstance(name_or_index, int):
            if name_or_index < len(self.subfragments):
                subfragment, name = self.subfragments[name_or_index]
                return subfragment
            raise NameError("No subfragment at index #{}".format(name_or_index))
        else:
            for subfragment, name in self.subfragments:
                if name == name_or_index:
                    return subfragment
            raise NameError("No subfragment with name '{}'".format(name_or_index))

    def find_generated(self, *path):
        if len(path) > 1:
            path_component, *path = path
            return self.find_subfragment(path_component).find_generated(*path)
        else:
            item, = path
            return self.generated[item]

    def elaborate(self, platform):
        return self

    def _merge_subfragment(self, subfragment):
        # Merge subfragment's everything except clock domains into this fragment.
        # Flattening is done after clock domain propagation, so we can assume the domains
        # are already the same in every involved fragment in the first place.
        self.ports.update(subfragment.ports)
        for domain, signal in subfragment.iter_drivers():
            self.add_driver(signal, domain)
        self.statements += subfragment.statements
        self.subfragments += subfragment.subfragments

        # Remove the merged subfragment.
        found = False
        for i, (check_subfrag, check_name) in enumerate(self.subfragments): # :nobr:
            if subfragment == check_subfrag:
                del self.subfragments[i]
                found = True
                break
        assert found

    def _resolve_hierarchy_conflicts(self, hierarchy=("top",), mode="warn"):
        assert mode in ("silent", "warn", "error")

        driver_subfrags = SignalDict()
        memory_subfrags = OrderedDict()
        def add_subfrag(registry, entity, entry):
            if entity not in registry:
                registry[entity] = set()
            registry[entity].add(entry)

        # For each signal driven by this fragment and/or its subfragments, determine which
        # subfragments also drive it.
        for domain, signal in self.iter_drivers():
            add_subfrag(driver_subfrags, signal, (None, hierarchy))

        flatten_subfrags = set()
        for i, (subfrag, name) in enumerate(self.subfragments):
            if name is None:
                name = "<unnamed #{}>".format(i)
            subfrag_hierarchy = hierarchy + (name,)

            if subfrag.flatten:
                # Always flatten subfragments that explicitly request it.
                flatten_subfrags.add((subfrag, subfrag_hierarchy))

            if isinstance(subfrag, Instance):
                # For memories (which are subfragments, but semantically a part of superfragment),
                # record that this fragment is driving it.
                if subfrag.type in ("$memrd", "$memwr"):
                    memory = subfrag.parameters["MEMID"]
                    add_subfrag(memory_subfrags, memory, (None, hierarchy))

                # Never flatten instances.
                continue

            # First, recurse into subfragments and let them detect driver conflicts as well.
            subfrag_drivers, subfrag_memories = \
                subfrag._resolve_hierarchy_conflicts(subfrag_hierarchy, mode)

            # Second, classify subfragments by signals they drive and memories they use.
            for signal in subfrag_drivers:
                add_subfrag(driver_subfrags, signal, (subfrag, subfrag_hierarchy))
            for memory in subfrag_memories:
                add_subfrag(memory_subfrags, memory, (subfrag, subfrag_hierarchy))

        # Find out the set of subfragments that needs to be flattened into this fragment
        # to resolve driver-driver conflicts.
        def flatten_subfrags_if_needed(subfrags):
            if len(subfrags) == 1:
                return []
            flatten_subfrags.update((f, h) for f, h in subfrags if f is not None)
            return list(sorted(".".join(h) for f, h in subfrags))

        for signal, subfrags in driver_subfrags.items():
            subfrag_names = flatten_subfrags_if_needed(subfrags)
            if not subfrag_names:
                continue

            # While we're at it, show a message.
            message = ("Signal '{}' is driven from multiple fragments: {}"
                       .format(signal, ", ".join(subfrag_names)))
            if mode == "error":
                raise DriverConflict(message)
            elif mode == "warn":
                message += "; hierarchy will be flattened"
                warnings.warn_explicit(message, DriverConflict, *signal.src_loc)

        for memory, subfrags in memory_subfrags.items():
            subfrag_names = flatten_subfrags_if_needed(subfrags)
            if not subfrag_names:
                continue

            # While we're at it, show a message.
            message = ("Memory '{}' is accessed from multiple fragments: {}"
                       .format(memory.name, ", ".join(subfrag_names)))
            if mode == "error":
                raise DriverConflict(message)
            elif mode == "warn":
                message += "; hierarchy will be flattened"
                warnings.warn_explicit(message, DriverConflict, *memory.src_loc)

        # Flatten hierarchy.
        for subfrag, subfrag_hierarchy in sorted(flatten_subfrags, key=lambda x: x[1]):
            self._merge_subfragment(subfrag)

        # If we flattened anything, we might be in a situation where we have a driver conflict
        # again, e.g. if we had a tree of fragments like A --- B --- C where only fragments
        # A and C were driving a signal S. In that case, since B is not driving S itself,
        # processing B will not result in any flattening, but since B is transitively driving S,
        # processing A will flatten B into it. Afterwards, we have a tree like AB --- C, which
        # has another conflict.
        if any(flatten_subfrags):
            # Try flattening again.
            return self._resolve_hierarchy_conflicts(hierarchy, mode)

        # Nothing was flattened, we're done!
        return (SignalSet(driver_subfrags.keys()),
                set(memory_subfrags.keys()))

    def _propagate_domains_up(self, hierarchy=("top",)):
        from .xfrm import DomainRenamer

        domain_subfrags = defaultdict(lambda: set())

        # For each domain defined by a subfragment, determine which subfragments define it.
        for i, (subfrag, name) in enumerate(self.subfragments):
            # First, recurse into subfragments and let them propagate domains up as well.
            hier_name = name
            if hier_name is None:
                hier_name = "<unnamed #{}>".format(i)
            subfrag._propagate_domains_up(hierarchy + (hier_name,))

            # Second, classify subfragments by domains they define.
            for domain in subfrag.iter_domains():
                domain_subfrags[domain].add((subfrag, name, i))

        # For each domain defined by more than one subfragment, rename the domain in each
        # of the subfragments such that they no longer conflict.
        for domain, subfrags in domain_subfrags.items():
            if len(subfrags) == 1:
                continue

            names = [n for f, n, i in subfrags]
            if not all(names):
                names = sorted("<unnamed #{}>".format(i) if n is None else "'{}'".format(n)
                               for f, n, i in subfrags)
                raise DomainError("Domain '{}' is defined by subfragments {} of fragment '{}'; "
                                  "it is necessary to either rename subfragment domains "
                                  "explicitly, or give names to subfragments"
                                  .format(domain, ", ".join(names), ".".join(hierarchy)))

            if len(names) != len(set(names)):
                names = sorted("#{}".format(i) for f, n, i in subfrags)
                raise DomainError("Domain '{}' is defined by subfragments {} of fragment '{}', "
                                  "some of which have identical names; it is necessary to either "
                                  "rename subfragment domains explicitly, or give distinct names "
                                  "to subfragments"
                                  .format(domain, ", ".join(names), ".".join(hierarchy)))

            for subfrag, name, i in subfrags:
                self.subfragments[i] = \
                    (DomainRenamer({domain: "{}_{}".format(name, domain)})(subfrag), name)

        # Finally, collect the (now unique) subfragment domains, and merge them into our domains.
        for subfrag, name in self.subfragments:
            for domain in subfrag.iter_domains():
                self.add_domains(subfrag.domains[domain])

    def _propagate_domains_down(self):
        # For each domain defined in this fragment, ensure it also exists in all subfragments.
        for subfrag, name in self.subfragments:
            for domain in self.iter_domains():
                if domain in subfrag.domains:
                    assert self.domains[domain] is subfrag.domains[domain]
                else:
                    subfrag.add_domains(self.domains[domain])

            subfrag._propagate_domains_down()

    def _propagate_domains(self, ensure_sync_exists):
        self._propagate_domains_up()
        if ensure_sync_exists and not self.domains:
            cd_sync = ClockDomain()
            self.add_domains(cd_sync)
            new_domains = (cd_sync,)
        else:
            new_domains = ()
        self._propagate_domains_down()
        return new_domains

    def _insert_domain_resets(self):
        from .xfrm import ResetInserter

        resets = {cd.name: cd.rst for cd in self.domains.values() if cd.rst is not None}
        return ResetInserter(resets)(self)

    def _lower_domain_signals(self):
        from .xfrm import DomainLowerer

        return DomainLowerer(self.domains)(self)

    def _prepare_use_def_graph(self, parent, level, uses, defs, ios, top):
        def add_uses(*sigs, self=self):
            for sig in flatten(sigs):
                if sig not in uses:
                    uses[sig] = set()
                uses[sig].add(self)

        def add_defs(*sigs):
            for sig in flatten(sigs):
                if sig not in defs:
                    defs[sig] = self
                else:
                    assert defs[sig] is self

        def add_io(*sigs):
            for sig in flatten(sigs):
                if sig not in ios:
                    ios[sig] = self
                else:
                    assert ios[sig] is self

        # Collect all signals we're driving (on LHS of statements), and signals we're using
        # (on RHS of statements, or in clock domains).
        for stmt in self.statements:
            add_uses(stmt._rhs_signals())
            add_defs(stmt._lhs_signals())

        for domain, _ in self.iter_sync():
            cd = self.domains[domain]
            add_uses(cd.clk)
            if cd.rst is not None:
                add_uses(cd.rst)

        # Repeat for subfragments.
        for subfrag, name in self.subfragments:
            if isinstance(subfrag, Instance):
                for port_name, (value, dir) in subfrag.named_ports.items():
                    if dir == "i":
                        subfrag.add_ports(value._rhs_signals(), dir=dir)
                        add_uses(value._rhs_signals())
                    if dir == "o":
                        subfrag.add_ports(value._lhs_signals(), dir=dir)
                        add_defs(value._lhs_signals())
                    if dir == "io":
                        subfrag.add_ports(value._lhs_signals(), dir=dir)
                        add_io(value._lhs_signals())
            else:
                parent[subfrag] = self
                level [subfrag] = level[self] + 1

                subfrag._prepare_use_def_graph(parent, level, uses, defs, ios, top)

    def _propagate_ports(self, ports, all_undef_as_ports):
        # Take this fragment graph:
        #
        #    __ B (def: q, use: p r)
        #   /
        #  A (def: p, use: q r)
        #   \
        #    \_ C (def: r, use: p q)
        #
        # We need to consider three cases.
        #   1. Signal p requires an input port in B;
        #   2. Signal r requires an output port in C;
        #   3. Signal r requires an output port in C and an input port in B.
        #
        # Adding these ports can be in general done in three steps for each signal:
        #   1. Find the least common ancestor of all uses and defs.
        #   2. Going upwards from the single def, add output ports.
        #   3. Going upwards from all uses, add input ports.

        parent = {self: None}
        level  = {self: 0}
        uses   = SignalDict()
        defs   = SignalDict()
        ios    = SignalDict()
        self._prepare_use_def_graph(parent, level, uses, defs, ios, self)

        ports = SignalSet(ports)
        if all_undef_as_ports:
            for sig in uses:
                if sig in defs:
                    continue
                ports.add(sig)
        for sig in ports:
            if sig not in uses:
                uses[sig] = set()
            uses[sig].add(self)

        @memoize
        def lca_of(fragu, fragv):
            # Normalize fragu to be deeper than fragv.
            if level[fragu] < level[fragv]:
                fragu, fragv = fragv, fragu
            # Find ancestor of fragu on the same level as fragv.
            for _ in range(level[fragu] - level[fragv]):
                fragu = parent[fragu]
            # If fragv was the ancestor of fragv, we're done.
            if fragu == fragv:
                return fragu
            # Otherwise, they are at the same level but in different branches. Step both fragu
            # and fragv until we find the common ancestor.
            while parent[fragu] != parent[fragv]:
                fragu = parent[fragu]
                fragv = parent[fragv]
            return parent[fragu]

        for sig in uses:
            if sig in defs:
                lca  = reduce(lca_of, uses[sig], defs[sig])
            else:
                lca  = reduce(lca_of, uses[sig])

            for frag in uses[sig]:
                if sig in defs and frag is defs[sig]:
                    continue
                while frag != lca:
                    frag.add_ports(sig, dir="i")
                    frag = parent[frag]

            if sig in defs:
                frag = defs[sig]
                while frag != lca:
                    frag.add_ports(sig, dir="o")
                    frag = parent[frag]

        for sig in ios:
            frag = ios[sig]
            while frag is not None:
                frag.add_ports(sig, dir="io")
                frag = parent[frag]

        for sig in ports:
            if sig in ios:
                continue
            if sig in defs:
                self.add_ports(sig, dir="o")
            else:
                self.add_ports(sig, dir="i")

    def prepare(self, ports=None, ensure_sync_exists=True):
        from .xfrm import SampleLowerer

        fragment = SampleLowerer()(self)
        new_domains = fragment._propagate_domains(ensure_sync_exists)
        fragment._resolve_hierarchy_conflicts()
        fragment = fragment._insert_domain_resets()
        fragment = fragment._lower_domain_signals()
        if ports is None:
            fragment._propagate_ports(ports=(), all_undef_as_ports=True)
        else:
            new_ports = []
            for cd in new_domains:
                new_ports.append(cd.clk)
                if cd.rst is not None:
                    new_ports.append(cd.rst)
            fragment._propagate_ports(ports=(*ports, *new_ports), all_undef_as_ports=False)
        return fragment


class Instance(Fragment):
    def __init__(self, type, *args, **kwargs):
        super().__init__()

        self.type        = type
        self.parameters  = OrderedDict()
        self.named_ports = OrderedDict()

        for (kind, name, value) in args:
            if kind == "a":
                self.attrs[name] = value
            elif kind == "p":
                self.parameters[name] = value
            elif kind in ("i", "o", "io"):
                self.named_ports[name] = (value, kind)
            else:
                raise NameError("Instance argument {!r} should be a tuple (kind, name, value) "
                                "where kind is one of \"p\", \"i\", \"o\", or \"io\""
                                .format((kind, name, value)))

        for kw, arg in kwargs.items():
            if kw.startswith("a_"):
                self.attrs[kw[2:]] = arg
            elif kw.startswith("p_"):
                self.parameters[kw[2:]] = arg
            elif kw.startswith("i_"):
                self.named_ports[kw[2:]] = (arg, "i")
            elif kw.startswith("o_"):
                self.named_ports[kw[2:]] = (arg, "o")
            elif kw.startswith("io_"):
                self.named_ports[kw[3:]] = (arg, "io")
            else:
                raise NameError("Instance keyword argument {}={!r} does not start with one of "
                                "\"p_\", \"i_\", \"o_\", or \"io_\""
                                .format(kw, arg))
