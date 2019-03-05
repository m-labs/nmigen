from .tools import *
from ..hdl import *
from ..back.pysim import *
from ..lib.cdc import *


class MultiRegTestCase(FHDLTestCase):
    def test_paramcheck(self):
        i = Signal()
        o = Signal()
        with self.assertRaises(TypeError):
            m = MultiReg(i, o, n=0)
        with self.assertRaises(TypeError):
            m = MultiReg(i, o, n="x")
        with self.assertRaises(ValueError):
            m = MultiReg(i, o, n=2, reset="a")
        with self.assertRaises(TypeError):
            m = MultiReg(i, o, n=2, reset=i)
        m = MultiReg(i, o, n=1)
        m = MultiReg(i, o, reset=-1)

    def test_platform(self):
        platform = lambda: None
        platform.get_multi_reg = lambda m: "foobar{}".format(len(m._regs))
        i = Signal()
        o = Signal()
        m = MultiReg(i, o, n=5)
        self.assertEqual(m.elaborate(platform), "foobar5")

    def test_basic(self):
        i = Signal()
        o = Signal()
        frag = MultiReg(i, o)
        with Simulator(frag) as sim:
            sim.add_clock(1e-6)
            def process():
                self.assertEqual((yield o), 0)
                yield i.eq(1)
                yield Tick()
                self.assertEqual((yield o), 0)
                yield Tick()
                self.assertEqual((yield o), 0)
                yield Tick()
                self.assertEqual((yield o), 1)
            sim.add_process(process)
            sim.run()

    def test_reset_value(self):
        i = Signal(reset=1)
        o = Signal()
        frag = MultiReg(i, o, reset=1)
        with Simulator(frag) as sim:
            sim.add_clock(1e-6)
            def process():
                self.assertEqual((yield o), 1)
                yield i.eq(0)
                yield Tick()
                self.assertEqual((yield o), 1)
                yield Tick()
                self.assertEqual((yield o), 1)
                yield Tick()
                self.assertEqual((yield o), 0)
            sim.add_process(process)
            sim.run()


class ResetSynchronizerTestCase(FHDLTestCase):
    def test_paramcheck(self):
        arst = Signal()
        with self.assertRaises(TypeError):
            r = ResetSynchronizer(arst, n=0)
        with self.assertRaises(TypeError):
            r = ResetSynchronizer(arst, n="a")
        r = ResetSynchronizer(arst)

    def test_platform(self):
        platform = lambda: None
        platform.get_reset_sync = lambda m: "foobar{}".format(len(m._regs))
        arst = Signal()
        rs = ResetSynchronizer(arst, n=6)
        self.assertEqual(rs.elaborate(platform), "foobar6")

    def test_basic(self):
        arst = Signal()
        m = Module()
        m.domains += ClockDomain("sync")
        m.submodules += ResetSynchronizer(arst)
        s = Signal(reset=1)
        m.d.sync += s.eq(0)

        with Simulator(m, vcd_file=open("test.vcd", "w")) as sim:
            sim.add_clock(1e-6)
            def process():
                # initial reset
                self.assertEqual((yield s), 1)
                yield Tick(); yield Delay(1e-8)
                self.assertEqual((yield s), 1)
                yield Tick(); yield Delay(1e-8)
                self.assertEqual((yield s), 1)
                yield Tick(); yield Delay(1e-8)
                self.assertEqual((yield s), 0)
                yield Tick(); yield Delay(1e-8)

                yield arst.eq(1)
                yield Delay(1e-8)
                self.assertEqual((yield s), 1)
                yield Tick(); yield Delay(1e-8)
                self.assertEqual((yield s), 1)
                yield arst.eq(0)
                yield Tick(); yield Delay(1e-8)
                self.assertEqual((yield s), 1)
                yield Tick(); yield Delay(1e-8)
                self.assertEqual((yield s), 1)
                yield Tick(); yield Delay(1e-8)
                self.assertEqual((yield s), 0)
                yield Tick(); yield Delay(1e-8)
            sim.add_process(process)
            sim.run()


# TODO: test with distinct clocks
class PulseSynchronizerTestCase(FHDLTestCase):
    def test_paramcheck(self):
        with self.assertRaises(TypeError):
            ps = PulseSynchronizer("w", "r", sync_stages=0)
        with self.assertRaises(TypeError):
            ps = PulseSynchronizer("w", "r", sync_stages="abc")
        ps = PulseSynchronizer("w", "r", sync_stages = 1)

    def test_smoke(self):
        m = Module()
        m.domains += ClockDomain("sync")
        ps = m.submodules.dut = PulseSynchronizer("sync", "sync")

        with Simulator(m, vcd_file = open("test.vcd", "w")) as sim:
            sim.add_clock(1e-6)
            def process():
                yield ps.i.eq(0)
                # TODO: think about reset
                for n in range(5):
                    yield Tick()
                # Make sure no pulses are generated in quiescent state
                for n in range(3):
                    yield Tick()
                    self.assertEqual((yield ps.o), 0)
                # Check conservation of pulses
                accum = 0
                for n in range(10):
                    yield ps.i.eq(1 if n < 4 else 0)
                    yield Tick()
                    accum += yield ps.o
                self.assertEqual(accum, 4)
            sim.add_process(process)
            sim.run()

class BusSynchronizerTestCase(FHDLTestCase):
    def test_paramcheck(self):
        with self.assertRaises(TypeError):
            bs = BusSynchronizer(0, "i", "o")
        with self.assertRaises(TypeError):
            bs = BusSynchronizer("x", "i", "o")

        bs = BusSynchronizer(1, "i", "o")

        with self.assertRaises(TypeError):
            bs = BusSynchronizer(1, "i", "o", sync_stages = 1)
        with self.assertRaises(TypeError):
            bs = BusSynchronizer(1, "i", "o", sync_stages = "a")
        with self.assertRaises(TypeError):
            bs = BusSynchronizer(1, "i", "o", timeout=-1)
        with self.assertRaises(TypeError):
            bs = BusSynchronizer(1, "i", "o", timeout="a")

        bs = BusSynchronizer(1, "i", "o", timeout=0)

    def test_smoke_w1(self):
        self.check_smoke(width=1, timeout=127)

    def test_smoke_normalcase(self):
        self.check_smoke(width=8, timeout=127)

    def test_smoke_notimeout(self):
        self.check_smoke(width=8, timeout=0)

    def check_smoke(self, width, timeout):
        m = Module()
        m.domains += ClockDomain("sync")
        bs = m.submodules.dut = BusSynchronizer(width, "sync", "sync", timeout=timeout)

        with Simulator(m, vcd_file = open("test.vcd", "w")) as sim:
            sim.add_clock(1e-6)
            def process():
                for i in range(10):
                    testval = i % (2 ** width)
                    yield bs.i.eq(testval)
                    # 6-cycle round trip, and if one in progress, must complete first:
                    for j in range(11):
                        yield Tick()
                    self.assertEqual((yield bs.o), testval)
            sim.add_process(process)
            sim.run()

# TODO: test with distinct clocks
# (since we can currently only test symmetric aspect ratio)
class GearboxTestCase(FHDLTestCase):
    def test_paramcheck(self):
        with self.assertRaises(TypeError):
            g = Gearbox(0, "i", 1, "o")
        with self.assertRaises(TypeError):
            g = Gearbox(1, "i", 0, "o")
        with self.assertRaises(TypeError):
            g = Gearbox("x", "i", 1, "o")
        with self.assertRaises(TypeError):
            g = Gearbox(1, "i", "x", "o")
        g = Gearbox(1, "i", 1, "o")
        g = Gearbox(7, "i", 1, "o")
        g = Gearbox(7, "i", 3, "o")
        g = Gearbox(7, "i", 7, "o")
        g = Gearbox(3, "i", 7, "o")

    def test_smoke_symmetric(self):
        m = Module()
        m.domains += ClockDomain("sync")
        g = m.submodules.dut = Gearbox(8, "sync", 8, "sync")

        with Simulator(m, vcd_file = open("test.vcd", "w")) as sim:
            sim.add_clock(1e-6)
            def process():
                pipeline_filled = False
                expected_out = 1
                yield Tick()
                for i in range(g._ichunks * 4):
                    yield g.i.eq(i)
                    if (yield g.o):
                        pipeline_filled = True
                    if pipeline_filled:
                        self.assertEqual((yield g.o), expected_out)
                        expected_out += 1
                    yield Tick()
                self.assertEqual(pipeline_filled, True)
                self.assertEqual(expected_out > g._ichunks * 2, True)
            sim.add_process(process)
            sim.run()