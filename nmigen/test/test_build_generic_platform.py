from .. import *
from ..build.dsl import *
from ..build.generic_platform import *
from ..hdl.rec import *
from ..lib.io import *
from .tools import *


class ConstraintsTestCase(FHDLTestCase):
    def setUp(self):
        self.resources = [
            Resource("clk100", 0, DiffPairs("H1", "H2", dir="i")),
            Resource("user_led", 0, Pins("A0", dir="o")),
            Resource("i2c", 0,
                Subsignal("scl", Pins("N10", dir="o")),
                Subsignal("sda", Pins("N11"))
            )
        ]
        self.platform = GenericPlatform("test", self.resources)

    def test_basic(self):
        self.assertEqual(self.platform.device, "test")
        self.assertEqual(self.platform.available, {
            "clk100":   {0: self.resources[0]},
            "user_led": {0: self.resources[1]},
            "i2c":      {0: self.resources[2]}
        })

    def test_add_resources(self):
        new_resources = [
            Resource("user_led", 1, Pins("A1", dir="o"))
        ]
        self.platform.add_resources(new_resources)
        self.assertEqual(self.platform.available, {
            "clk100":   {0: self.resources[0]},
            "user_led": {0: self.resources[1], 1: new_resources[0]},
            "i2c":      {0: self.resources[2]}
        })

    def test_lookup(self):
        r = self.platform.lookup("user_led")
        self.assertIs(r, self.platform.available["user_led"][0])

    def test_request_basic(self):
        user_led = self.platform.request("user_led")

        self.assertIsInstance(user_led, Pin)
        self.assertEqual(user_led.name, "user_led_0")
        self.assertEqual(user_led.width, 1)
        self.assertEqual(user_led.dir, "o")

        ports = self.platform.get_ports()
        self.assertEqual(len(ports), 1)
        self.assertIs(user_led.o, ports[0])

        self.assertEqual(self.platform.get_port_constraints(), [
            ("user_led_0__o", ["A0"], [])
        ])

    def test_request_with_dir(self):
        i2c = self.platform.request("i2c", dir={"sda": "o"})
        self.assertIsInstance(i2c, Record)
        self.assertIsInstance(i2c.sda, Pin)
        self.assertEqual(i2c.sda.dir, "o")

    def test_request_tristate(self):
        i2c = self.platform.request("i2c")
        self.assertEqual(i2c.sda.dir, "io")

        self.assertEqual(len(self.platform.inouts), 1)
        inout, _, _ = self.platform.inouts[0]
        self.assertEqual(inout.name, "i2c_0__sda_io")
        self.assertEqual(inout.nbits, 1)

        self.assertEqual(self.platform.tristates, [(i2c.sda, inout)])
        self.assertEqual(self.platform.get_port_constraints(), [
            ("i2c_0__scl__o", ["N10"], []),
            ("i2c_0__sda_io", ["N11"], [])
        ])

    def test_request_diffpairs(self):
        clk100 = self.platform.request("clk100")
        self.assertIsInstance(clk100, Pin)
        self.assertEqual(clk100.width, 1)

        ports = self.platform.get_ports()
        self.assertEqual(len(ports), 2)
        p, n = ports
        self.assertEqual(p.name, "clk100_0_p")
        self.assertEqual(p.nbits, clk100.width)
        self.assertEqual(n.name, "clk100_0_n")
        self.assertEqual(n.nbits, clk100.width)

        self.assertEqual(self.platform.diffpairs, [(clk100, p, n, "i")])
        self.assertEqual(self.platform.get_port_constraints(), [
            ("clk100_0_p", ["H1"], []),
            ("clk100_0_n", ["H2"], [])
        ])

    def test_add_period(self):
        r = self.platform.lookup("clk100")
        self.platform.add_period(r, 10.0)
        self.assertEqual(self.platform.clocks["clk100", 0], 10.0)

        clk100 = self.platform.request("clk100")
        self.assertEqual(self.platform.get_period_constraints(), [
            ("clk100_0__i", 10.0)
        ])

    def test_wrong_resources(self):
        with self.assertRaises(TypeError, msg="Object 'wrong' is not a Resource"):
            self.platform.add_resources(['wrong'])

    def test_wrong_resources_duplicate(self):
        with self.assertRaises(NameError,
                msg="Trying to add (resource user_led 0 (pins A1 o) ), but "
                    "(resource user_led 0 (pins A0 o) ) has the same name and number"):
            self.platform.add_resources([Resource("user_led", 0, Pins("A1", dir="o"))])

    def test_wrong_lookup(self):
        with self.assertRaises(NameError,
                msg="No available Resource with name 'user_led' and number 1"):
            r = self.platform.lookup("user_led", 1)

    def test_wrong_period(self):
        with self.assertRaises(TypeError, msg="Object 'wrong' is not a Resource"):
            self.platform.add_period('wrong', 10.0)

    def test_wrong_period_subsignals(self):
        with self.assertRaises(ConstraintError,
                msg="Cannot constrain Resource ('i2c', 0) to a period of 10.0 ns because "
                    "it has subsignals"):
            r = self.platform.lookup("i2c")
            self.platform.add_period(r, 10.0)

    def test_wrong_period_duplicate(self):
        with self.assertRaises(ConstraintError,
                msg="Resource ('clk100', 0) is already constrained to a period of 10.0 ns"):
            r = self.platform.lookup("clk100")
            self.platform.add_period(r, 10.0)
            self.platform.add_period(r, 5.0)

    def test_wrong_request_with_dir(self):
        with self.assertRaises(TypeError,
                msg="Direction must be one of \"i\", \"o\" or \"io\", not 'wrong'"):
            user_led = self.platform.request("user_led", dir="wrong")

    def test_wrong_request_with_dir_io(self):
        with self.assertRaises(ValueError,
                msg="Direction \"o\" cannot be changed to \"i\"; Valid changes are "
                    "\"io\"->\"i\", \"io\"->\"o\""):
            user_led = self.platform.request("user_led", dir="i")

    def test_wrong_request_with_dir_dict(self):
        with self.assertRaises(TypeError,
                msg="Directions must be a dict, not 'i', because (resource i2c 0 (subsignal scl "
                    "(pins N10 o) ) (subsignal sda (pins N11 io) ) ) has subsignals"):
            i2c = self.platform.request("i2c", dir="i")
