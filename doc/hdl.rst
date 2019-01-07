The HDL domain-specific language
################################

The Fragmented Hardware Description Language (FHDL, or more simply, just HDL) is the basis of nMigen. It consists of a formal system to describe signals and the combinatorial and synchronous statements operating upon them. The formal system itself is low level and close to the synthesizable subset of Verilog, and we then rely on Python algorithms to build complex structures by combining HDL elements.

The nMigen HDL differs from MyHDL_ in fundamental ways. MyHDL follows the event-driven paradigm of traditional HDLs (see :ref:`background`) while nMigen's HDL separates the code into combinatorial statements, synchronous statements, and reset values. In MyHDL, the logic is described directly in the Python AST. The converter to Verilog or VHDL then examines the Python AST and recognizes a subset of Python that it translates into V*HDL statements. This seriously impedes the capability of MyHDL to generate logic procedurally. With nMigen, you manipulate a custom AST from Python, and you can more easily design algorithms that operate on it.

.. _MyHDL: http://www.myhdl.org

HDL consists of several elements, which are briefly explained below. They all can be imported directly from the ``nmigen`` module.

Expressions
***********

Constants
=========

The ``Constant`` object represents a constant, HDL-literal integer. It behaves like specifying integers and booleans but also supports slicing and can have a bit width or signedness different from what is implied by the value it represents.

``True`` and ``False`` are interpreted as 1 and 0, respectively.

Negative integers are explicitly supported. As with |MyHDL-countin|_, arithmetic operations return their natural results.

To lighten the syntax, assignments and operators automatically wrap Python integers and booleans into ``Constant``. Additionally, ``Constant`` is aliased to ``C``.

Examples
~~~~~~~~

In this example, we create a 4-bit constant (0) which is assigned to a signal ``a``.

    >>> from nmigen import *
    >>> a = Signal(4)
    >>> a.eq(0)
    (eq (sig a) (const 1'd0))

We can also use constants in arithmetic and logical operations.

    >>> from nmigen import *
    >>> a = Signal(4)
    >>> a.eq(a + 1)
    (eq (sig a) (+ (sig a) (const 1'd1))

You can make use of the ``Constant`` or ``C`` constructor to directly encode constants as well.

    >>> from nmigen import *
    >>> a = Signal()
    >>> a.eq(C(42)[0:1])
    (eq (sig a) (slice (const 6'd42) 0:1))

.. |MyHDL-countin| replace:: MyHDL
.. _MyHDL-countin: http://www.jandecaluwe.com/hdldesign/counting.html

Signal
======

The Signal object represents a value that is expected to change in the circuit. It does exactly what Verilog's *wire* and *reg* and VHDL's *signal* keywords do.

The main point of the Signal object is that it is identified by its Python ID (as returned by the :py:func:`id` function), and nothing else. It is the responsibility of the V*HDL back-end to establish an injective mapping between Python IDs and the V*HDL namespace. It should perform name mangling to ensure this. The consequence of this is that signal objects can safely become members of arbitrary Python classes, or be passed as parameters to functions or methods that generate logic involving them.

The properties of a Signal object are:

* An integer or a (integer, boolean) pair that defines the number of bits and whether the most significant bit of the signal is a sign bit (i.e. the signal is signed). The defaults are one bit and unsigned. Alternatively, the ``min`` and ``max`` parameters can be specified to define the range of the signal and determine its bit width and signedness. As with Python ranges, ``min`` is inclusive and defaults to 0, ``max`` is exclusive and defaults to 2.
* A name, used as a hint for the V*HDL back-end name mangler.
* The signal's reset value. It must be an integer, and defaults to 0. When the signal's value is modified with a synchronous statement, the reset value is the initialization value of the associated register. When the signal is assigned to in a conditional combinatorial statement (``If`` or ``Case``), the reset value is the value that the signal has when no condition that causes the signal to be driven is verified. This enforces the absence of latches in designs. If the signal is permanently driven using a combinatorial statement, the reset value has no effect.

.. note::
    The sole purpose of the name property is to make the generated V*HDL code easier to understand and debug. From a purely functional point of view, it is perfectly OK to have several signals with the same name property. The back-end will generate a unique name for each object. If no name property is specified, nMigen will analyze the code that created the signal object, and try to extract the variable or member name from there. For example, the following statements will create one or several signals named "bar": ::

      bar = Signal()
      self.bar = Signal()
      self.baz.bar = Signal()
      bar = [Signal() for x in range(42)]

    In case of conflicts, nMigen tries first to resolve the situation by prefixing the identifiers with names from the class and module hierarchy that created them. If the conflict persists (which can be the case if two signal objects are created with the same name in the same context), it will ultimately add number suffixes.

Examples
~~~~~~~~

This creates a single signal named ``a``, which defaults to 0 unless driven otherwise.

    >>> from nmigen import *
    >>> a = Signal()

In this example, we create an 24-bit wide signal named ``counter``.  Note that we don't explicitly specify that it is a 24-bit signal; rather, we specify the largest value it's expected to hold using the ``max`` keyword argument.

    >>> from nmigen import *
    >>> counter = Signal(max=12000000)
    >>> print(counter.nbits)
    24
    >>> print(counter.signed)
    False
    >>> print(counter.reset)
    0

This would be equivalent to the following:

    >>> from nmigen import *
    >>> counter = Signal(24)
    >>> print(counter.nbits)
    24
    >>> print(counter.signed)
    False
    >>> print(counter.reset)
    0

    If you wanted to default the counter to somewhere in the middle of its valid range, you could do the following:

    >>> from nmigen import *
    >>> counter = Signal(max=12000000, reset=6000000)
    >>> print(counter.nbits)
    24
    >>> print(counter.signed)
    False
    >>> print(counter.reset)
    6000000

Last, but not least, we show how to create a signal that is actually 5-bits wide, 4 of which are used to convey a magnitude, and the most-significant bit is used to convey sign.

    >>> from nmigen import *
    >>> index = Signal(min=-16, max=15)
    >>> print(index.nbits)
    5
    >>> print(index.signed)
    True

This is equivalent to the following:

    >>> from nmigen import *
    >>> index = Signal((5, True))
    >>> print(index.nbits)
    5
    >>> print(index.signed)
    True

Operators
=========

Operators are represented by the ``Operator`` class, which generally should not be used directly. Instead, most HDL objects overload the usual Python logic and arithmetic operators, which allows a much lighter syntax to be used.

Examples 
~~~~~~~~

The expression::

    a * b + c

is equivalent to::

    Operator("+", [Operator("*", [a, b]), c])

Slices
======

Slices are represented by the ``Slice`` class, which often should not be used in favor of the Python slice operation [x:y]. Implicit indices using the forms [x], [x:] and [:y] are supported.

.. note::
   Slices work like Python slices, **not** like VHDL or Verilog slices. The first bound is the index of the LSB and is inclusive. The second bound is the index of MSB and is exclusive. In V*HDL, bounds are MSB:LSB and both are inclusive.

Concatenations
==============

Concatenations are represented using the ``Cat`` class. To make the syntax lighter, its constructor takes a variable number of arguments, which are the signals to be concatenated together (you can use the Python "*" operator to pass a list instead).

.. note::
    To be consistent with slices, the first signal is connected to the bits with the lowest indices in the result. This is the opposite of the way the "{}" construct works in Verilog.

Examples
~~~~~~~~

Let's say you have the following flags defined in a UART, and you'd like to bundle them up into a single 8-bit quantity for convenient presentation to a host processor.  The ``Cat`` constructor would be ideal for this purpose:

    >>> from nmigen import *
    >>> z0 = Signal()   # hardwired to 0
    >>> z1 = Signal()
    >>> z2 = Signal()
    >>> txe = Signal()  # Transmit queue empty
    >>> txf = Signal()  # Transmit queue full
    >>> rxe = Signal()  # Receive queue empty
    >>> rxf = Signal()  # Receive queue full
    >>> rxo = Signal()  # Receive queue overrun
    >>> flags_byte = Cat(z0, z1, z2, txe, txf, rxe, rxf, rxo)
    >>> flags_byte.shape()
    (8, False)

As written above, the flags byte would conventionally be diagrammed as follows in a datasheet:

+-----+-----+-----+-----+-----+---+---+---+
|  7  |  6  |  5  |  4  |  3  | 2 | 1 | 0 |
+=====+=====+=====+=====+=====+===+===+===+
| RXO | RXF | RXE | TXF | TXE | 0 | 0 | 0 |
+-----+-----+-----+-----+-----+---+---+---+

Replications
============

``Repl`` objects represent the equivalent of ``{count{expression}}`` in Verilog.  It evaluates to a replicated pattern of bits, arranged adjacently.

Examples
~~~~~~~~

The expression::

    Replicate(0, 4)

is equivalent to::

    Cat(0, 0, 0, 0)

Knowing that, we can somewhat simplify the previous ``Cat`` example.
In the previous section, we illustrated how one might use the ``Cat`` constructor to bundle a set of related signals into a larger signal that was more convenient for an 8-bit processor to use.  You might notice that there are three unused flags, ``z0``, ``z1``, and ``z2``.  These can be replaced with a ``Repl`` instantiation as follows, with no change in circuit behavior and with an overall increase in code legibility:

    >>> from nmigen import *
    >>> txe = Signal()  # Transmit queue empty
    >>> txf = Signal()  # Transmit queue full
    >>> rxe = Signal()  # Receive queue empty
    >>> rxf = Signal()  # Receive queue full
    >>> rxo = Signal()  # Receive queue overrun
    >>> flags_byte = Cat(Repl(0, 3), txe, txf, rxe, rxf, rxo)
    >>> flags_byte.shape()
    (8, False)


Arrays
======

An ``Array`` object represents lists of other objects that can be indexed by HDL expressions. It is explicitly possible to:

* nest ``Array`` objects to create multidimensional tables.
* list any Python object in a ``Array`` as long as every expression appearing in a module ultimately evaluates to a ``Signal`` for all possible values of the indices. This allows the creation of lists of structured data.
* use expressions involving ``Array`` objects in both directions (assignment and reading).

Examples
~~~~~~~~

This creates a 4x4 matrix of 1-bit signals::

    >>> from nmigen import *
    >>> my_2d_array = Array(Array(Signal() for a in range(4)) for b in range(4))

You can then read the matrix with (``x`` and ``y`` being 2-bit signals)::

    >>> x = Signal(2)
    >>> y = Signal(2)
    >>> out = Signal()
    >>> out.eq(my_2d_array[x][y])

and write it with::

    >>> my_2d_array[x][y].eq(inp)

.. note::
   Since they have no direct equivalent in Verilog, ``Array`` objects are lowered into multiplexers and conditional statements before the actual conversion takes place. Such lowering happens automatically without any user intervention.

.. attention::
   Any out-of-bounds access performed on an ``Array`` object will refer to the *last element.*

Assignment
==========

Assignments are represented by the ``Assign`` class. Since using it directly would result in a cluttered syntax, the preferred technique for assignments is to use the ``eq()`` method provided by objects that can have a value assigned to them. They are signals, and their combinations with the slice and concatenation operators.

Examples
~~~~~~~~

The statement::

    >>> from nmigen import *
    >>> a = Signal(3)
    >>> b = Signal()
    >>> a[0].eq(b)
    (eq (slice (sig a) 0:1) (sig b))

is equivalent to::

    >>> from nmigen import *
    >>> from nmigen.hdl.dsl import Assign, Slice
    >>> a = Signal(3)
    >>> b = Signal()
    >>> Assign(Slice(a, 0, 1), b)
    (eq (slice (sig a) 0:1) (sig b))

Modules
*******

Before we can look at what kinds of statements the HDL supports, we need to first understand what ``Module`` objects are and how to build them.

Modules play the same role as Verilog modules and VHDL entities. Similarly, they are organized in a tree structure. However, they come into existence very differently than in V*HDL.  This may seem confusing at first; however, it's this difference which gives nMigen its power over V*HDL.

A HDL module is a Python object that derives from the ``Module`` class.  Module objects have a series of methods, described below, which describes the behavioral characteristics of the module.  In addition to these behavioral methods, the HDL module object also possesses attributes which are used to help construct combinatorial and synchronous logic as well.

In essence, a fresh ``Module`` object a blank slate which, by way of various HDL methods described below, is populated with a description of the hardware module you want to synthesize or simulate.

Structure of a Module Generator
===============================

Let's first look at the hello world of modules so that we can examine what's happening: wrapping a simple OR-gate into a reusable module.

Type the following program into a Python file called ``myor.py``::

    from nmigen import *
    from nmigen.cli import main

    class MyOR:
        def __init__(self, width=1):
            self.a = Signal(width)
            self.b = Signal(width)
            self.y = Signal(width)

        def get_fragment(self, platform):
            m = Module()
            m.d.comb += self.y.eq(self.a | self.b)

            return m.lower(platform)

    if __name__ == '__main__':
        orGate = MyOR()
        main(orGate, ports=[orGate.a, orGate.b, orGate.y])

This program works in two phases:

#. When the object is first instantiated, the interface to the module is declared in the ``__init__`` constructor.  Observe that we can parameterize this module via the keyword argument ``width``, which we'll illustrate later.

    .. note::
        After construction, the module does not yet properly exist!  The ``MyOR`` class is not the module, but rather the module's *generator*.

#. When it's time to reify the circuit into a Verilog module, the ``get_fragment`` method of the generator class is invoked by nMigen.  This is where we actually *generate* the module given what we already know about their configuration from the constructor above.

    .. note::
        You might be familiar with Migen, the predecessor to nMigen, where modules are typically subclassed from ``Module``.  This is not the case with nMigen!  ``Module`` objects are frequently instantiated as-is, without subclassing of any kind.

Notice that this Python file happens to be *executable* as well as importable.  You can enter the following at the command line to get help::

    $ python3 myor.py --help

As of this writing, the results should look something like::

   usage: myor.py [-h] {generate,simulate} ...

   positional arguments:
     {generate,simulate}
       generate           generate RTLIL or Verilog from the design
       simulate           simulate the design

   optional arguments:
     -h, --help           show this help message and exit

Simulation will be discussed in a later section.  For now, let's create the corresponding Verilog output from our module definition::

    $ python3 myor.py generate myor.v

If you examine the results, it should look something like this::

   /* Generated by Yosys 0.7+653 (git sha1 ddc1761f, clang 6.0.1 -fPIC -Os) */

   (* top =  1  *)
   (* generator = "nMigen" *)
   module top(b, y, a);
     wire \$1 ;
     (* src = "myor.py:6" *)
     input a;
     (* src = "myor.py:7" *)
     input b;
     (* src = "myor.py:8" *)
     output y;
     (* src = "myor.py:8" *)
     reg \y$next ;
     assign \$1  = a | (* src = "myor.py:12" *) b;
     always @* begin
       \y$next  = 1'h0;
       \y$next  = \$1 ;
     end
     assign y = \y$next ;
   endmodule

Some things to note:

#. nMigen introduces a lot of helpful back-references automatically for you, so that when you find yourself debugging a circuit, you can easily jump back to the corresponding Python sources.
#. nMigen *infers* whether a signal is an input or an output.
#. nMigen tailored the module to the needs of its invokation.

Remember that the *gen* in nMigen stands for *generator*.  You are not describing a circuit with nMigen; you are instead describing a *circuit generator.*  We can illustrate this by now generating an 8-input OR-gate Verilog module.  Make the following changes to the ``myor.py`` file::

    if __name__ == '__main__':
        orGate = MyOR(width=8)
        main(orGate, ports=[orGate.a, orGate.b, orGate.y])

Now, if you re-generate the Verilog module per the previous steps, you'll find the following changes in the output (metadata elided for clarity)::

   wire [7:0] \$1 ;
   input [7:0] a;
   input [7:0] b;
   output [7:0] y;

Notice that the signals now are properly sized.

.. note::
    That most circuits and their respective generators tends to closely relate to each other is merely a happy coincidence.  You'll see later that this doesn't need to always be the case.

Statements
**********

Now that we know how to construct a module, and even how to perform basic parameterization, we can explore various module statement methods to tailor generated modules to specific needs.

Combinatorial statements
========================

A combinatorial statement is a statement that is executed whenever one of its inputs changes.

Combinatorial statements are added to a module by using the ``d.comb`` special attribute. Like most module special attributes, it must be accessed using the ``+=`` increment operator, and either a single statement, a tuple of statements or a list of statements can appear on the right hand side.

We've seen an example in the previous program listing, so we'll elide any further illustration here.

Synchronous statements
======================

A synchronous statements is a statement that is executed at each edge of some clock signal.

They are added to a module by using the ``d.sync`` special attribute, which has the same properties as the ``d.comb`` attribute.

If, Else, Elif
==============

The ``If`` method is used to make a binary decision.  The parameter to ``If`` is the *predicate* to test.  The *consequent* of the statement appears inside the body of a ``with`` statement.  The *alternate* can optionally be specified in a separate ``with`` statement using the ``Else`` method.

For instance, we can express a simple two-input multiplexor like so::

    class Mux:
        def __init__(self):
            self.a = Signal()
            self.b = Signal()
            self.s = Signal()
            self.y = Signal()

        def get_fragment(self, platform):
            m = Module()

            with m.If(self.s):
                m.d.comb += self.y.eq(self.a)
            with m.Else():
                m.d.comb += self.y.eq(self.b)

            return m.lower(platform)

If you need to perform a multi-way decision, you can use the ``Elif`` method as a shortcut for an else-if construct::

   class Mux:
      def __init__(self):
            self.a = Signal()
            self.b = Signal()
            self.c = Signal()
            self.s = Signal(max=3)
            self.y = Signal()

        def get_fragment(self, platform):
            m = Module()

            with m.If(self.s == 0):
                m.d.comb += self.y.eq(self.a)
            with m.Elif(self.s == 1):
                m.d.comb += self.y.eq(self.b)
            with m.Else():
                m.d.comb += self.y.eq(self.c)

            return m.lower(platform)

``If``, ``Else``, and ``Elif`` bodies can nest as well::

    with m.If(self.tx_count16 == 0):
        self.tx_bitcount.eq(self.tx_bitcount + 1)
        with m.If(self.tx_bitcount == 8):
            self.tx.eq(1)
        with m.Elif(self.tx_bitcount == 9):
            self.tx.eq(1)
            self.tx_busy.eq(0)
        with m.Else():
            self.tx.eq(self.tx_reg[0])
            self.tx_reg.eq(Cat(self.tx_reg[1:], 0))


Switch, Case
============

If you find that you're writing the same basic form of predicate over and over again in a sequence of ``If`` and ``Elif`` statements, varying only by what a signal is compared against, then a ``Switch``/``Case`` construct might be a better solution.

The parameter to ``Switch`` specifies the signal which will be compared.  Each parameter to ``Case`` specifies the value against which it'll be compared.  The body of the successfully matching ``with`` predicate, its consequent, will take effect.

Consider this rewrite of the ``Mux`` class from the previous section::

   class Mux:
      def __init__(self):
            self.a = Signal()
            self.b = Signal()
            self.c = Signal()
            self.s = Signal(max=3)
            self.y = Signal()

        def get_fragment(self, platform):
            m = Module()

            with m.Switch(self.s):
                with m.Case(0):
                    m.d.comb += self.y.eq(self.a)
                with m.Case(1):
                    m.d.comb += self.y.eq(self.b)
                with m.Case():
                    m.d.comb += self.y.eq(self.c)

            return m.lower(platform)

.. note::
    A call to ``Case()``, with no parameter given, represents the *default* case.

What if a selector signal is already pre-decoded into one-hot signals?  We can use ``Case`` in that context as well::

   class Mux:
      def __init__(self):
            self.a = Signal()
            self.b = Signal()
            self.c = Signal()
            self.s = Signal(3)
            self.y = Signal()

        def get_fragment(self, platform):
            m = Module()

            with m.Switch(self.s):
                with m.Case("--1"):
                    m.d.comb += self.y.eq(self.a)
                with m.Case("-1-"):
                    m.d.comb += self.y.eq(self.b)
                with m.Case("1--"):
                    m.d.comb += self.y.eq(self.c)

            return m.lower(platform)

In this form, each parameter to ``Case`` must have a length which precisely matches the length of the variable you're switching against.

.. attention::
    In the section on Slices, we discussed how slice notation always goes from LSB (inclusive) to MSB (exclusive; e.g., ``LSB:MSB``).  This convention was held for the ``Cat`` and ``Repl`` functions as well, such that given any sequence of signals or constants, the left-most value corresponded to the least significant bit.
    
    However, if you look at the generated Verilog for the above definition of ``Mux``, you'll find that when using strings to specify don't care bits, the **right-most** digit corresponds to the least significant bit, not the left-most, exactly as you would expect when writing binary digits on paper!  Take care!


Miscellaneous
*************

Tri-state I/O
=============

As of this writing, tri-state I/O is not explicitly supported by nMigen.  (See `Github issue #6`_.)  For now, you'll need to manually elaborate tri-state I/O signals as distinct inputs, outputs, and output enables.

.. _`Github issue #6`: https://github.com/m-labs/nmigen/issues/6

Instances
=========

Instance objects represent the parametrized instantiation of a V*HDL module, and the connection of its ports to HDL signals. They are useful in a number of cases:

* Reusing legacy or third-party V*HDL code.
* Using special FPGA features (DCM, ICAP, ...).
* Implementing logic that cannot be expressed with nMigen HDL (e.g. latches).
* Breaking down a nMigen system into multiple sub-systems.

The instance object constructor takes the type (i.e. name of the instantiated module) of the instance, then multiple parameters describing how to connect and parametrize the instance.

Suppose we wish to instantiate some device which uses an SPI interface to provide random numbers.  We might have code such as the following::

    from nmigen import *
    from nmigen.cli import main

    class RNG:
        def __init__(self, speed=10000000, seed=1726412):
            self.miso = Signal()
            self.mosi = Signal()
            self.ss = Signal()
            self.clk = Signal()

            self.speed = speed
            self.default_seed = seed

        def get_fragment(self, platform):
            m = Module()
            m.submodules.rng = Instance("RandomNumberGen",
                p_DEFAULT_SEED = self.default_seed,
                p_SPI_SPEED = self.speed,

                i_mosi = self.mosi,
                o_miso = self.miso,
                i_ss = self.ss,
                i_clk = self.clk,
            )
            return m.lower(platform)

    if __name__ == '__main__':
        m = RNG()
        main(m, ports=[m.miso, m.mosi, m.ss, m.clk])

The first parameter to ``Instance`` is the name of the Verilog, VHDL, et. al. module to instantiate.

All subsequent keyword arguments are named according to a convention which nMigen uses to properly instantiate and infer signal directions:

* All parameters that start with ``p_`` are module instance parameters.  For example, if you example the Verilog output for the RNG module generator above, you'll see the ``.DEFAULT_SEED`` and ``.SPI_SPEED`` parameter provided.
* All parameters that start with ``i_`` are *inputs to the instantiated module.*  Therefore, they will also be inputs to the module thus generated above.
* All parameters that start with ``o_`` are *outputs from the instantiated module.*  Therefore, they're also outputs from the generated module as well.
* All parameters that start with ``io_`` are **bidirectional**.  For Verilog, this means that the signal is marked ``inout``.

.. note::
    Observe that no explicit support for clock or reset ports is provided at this time.  The best way to pass them along is to assign clock and reset explicitly as inputs to the instantiated module.

Memories
========

Memories (on-chip SRAM) are supported using a mechanism similar to instances.

A memory object has the following parameters:

* The width, which is the number of bits in each word.
* The depth, which represents the number of words in the memory.
* An optional list of integers used to initialize the memory.

To access the memory in hardware, ports can be obtained by calling the ``get_port`` method. A port always has an address signal ``a`` and a data read signal ``dat_r``. Other signals may be available depending on the port's configuration.

Options to ``get_port`` are:

* ``write_capable`` (default: ``False``): if the port can be used to write to the memory. This creates an additional ``we`` signal.
* ``async_read`` (default: ``False``): whether reads are asychronous (combinatorial) or synchronous (registered).
* ``has_re`` (default: ``False``): adds a read clock-enable signal ``re`` (ignored for asychronous ports).
* ``we_granularity`` (default: ``0``): if non-zero, writes of less than a memory word can occur. The width of the ``we`` signal is increased to act as a selection signal for the sub-words.
* ``mode`` (default: ``WRITE_FIRST``, ignored for aynchronous ports).  It can be:

  * ``READ_FIRST``: during a write, the previous value is read.
  * ``WRITE_FIRST``: the written value is returned.
  * ``NO_CHANGE``: the data read signal keeps its previous value on a write.

* ``clock_domain`` (default: ``"sys"``): the clock domain used for reading and writing from this port.

Migen generates behavioural V*HDL code that should be compatible with all simulators and, if the number of ports is <= 2, most FPGA synthesizers. If a specific code is needed, the memory handler can be overriden using the appropriate parameter of the V*HDL conversion function.

Submodules and specials
=======================

Submodules and specials can be added by using the ``submodules`` and ``specials`` attributes respectively. This can be done in two ways:

#. anonymously, by using the ``+=`` operator on the special attribute directly, e.g. ``self.submodules += some_other_module``. Like with the ``comb`` and ``sync`` attributes, a single module/special or a tuple or list can be specified.
#. by naming the submodule/special using a subattribute of the ``submodules`` or ``specials`` attribute, e.g. ``self.submodules.foo = module_foo``. The submodule/special is then accessible as an attribute of the object, e.g. ``self.foo`` (and not ``self.submodules.foo``). Only one submodule/special can be added at a time using this form.

Clock domains
=============

Specifying the implementation of a clock domain is done using the ``ClockDomain`` object. It contains the name of the clock domain, a clock signal that can be driven like any other signal in the design (for example, using a PLL instance), and optionally a reset signal. Clock domains without a reset signal are reset using e.g. ``initial`` statements in Verilog, which in many FPGA families initalize the registers during configuration.

The name can be omitted if it can be extracted from the variable name. When using this automatic naming feature, prefixes ``_``, ``cd_`` and ``_cd_`` are removed.

Clock domains are then added to a module using the ``clock_domains`` special attribute, which behaves exactly like ``submodules`` and ``specials``.

Summary of special attributes
=============================

.. table::

   +--------------------------------------------+--------------------------------------------------------------+
   | Syntax                                     | Action                                                       |
   +============================================+==============================================================+
   | self.comb += stmt                          | Add combinatorial statement to current module.               |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.comb += stmtA, stmtB                  | Add combinatorial statements A and B to current module.      |
   |                                            |                                                              |
   | self.comb += [stmtA, stmtB]                |                                                              |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.sync += stmt                          | Add synchronous statement to current module, in default      |
   |                                            | clock domain sys.                                            |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.sync.foo += stmt                      | Add synchronous statement to current module, in clock domain |
   |                                            | foo.                                                         |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.sync.foo += stmtA, stmtB              | Add synchronous statements A and B to current module, in     |
   |                                            | clock domain foo.                                            |
   | self.sync.foo += [stmtA, stmtB]            |                                                              |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.submodules += mod                     | Add anonymous submodule to current module.                   |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.submodules += modA, modB              | Add anonymous submodules A and B to current module.          |
   |                                            |                                                              |
   | self.submodules += [modA, modB]            |                                                              |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.submodules.bar = mod                  | Add submodule named bar to current module. The submodule can |
   |                                            | then be accessed using self.bar.                             |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.specials += spe                       | Add anonymous special to current module.                     |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.specials += speA, speB                | Add anonymous specials A and B to current module.            |
   |                                            |                                                              |
   | self.specials += [speA, speB]              |                                                              |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.specials.bar = spe                    | Add special named bar to current module. The special can     |
   |                                            | then be accessed using self.bar.                             |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.clock_domains += cd                   | Add clock domain to current module.                          |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.clock_domains += cdA, cdB             | Add clock domains A and B to current module.                 |
   |                                            |                                                              |
   | self.clock_domains += [cdA, cdB]           |                                                              |
   +--------------------------------------------+--------------------------------------------------------------+
   | self.clock_domains.pix = ClockDomain()     | Create and add clock domain pix to current module. The clock |
   |                                            | domain name is pix in all cases. It can be accessed using    |
   | self.clock_domains._pix = ClockDomain()    | self.pix, self._pix, self.cd_pix and self._cd_pix,           |
   |                                            | respectively.                                                |
   | self.clock_domains.cd_pix = ClockDomain()  |                                                              |
   |                                            |                                                              |
   | self.clock_domains._cd_pix = ClockDomain() |                                                              |
   +--------------------------------------------+--------------------------------------------------------------+

Clock domain management
=======================

When a module has named submodules that define one or several clock domains with the same name, those clock domain names are prefixed with the name of each submodule plus an underscore.

An example use case of this feature is a system with two independent video outputs. Each video output module is made of a clock generator module that defines a clock domain ``pix`` and drives the clock signal, plus a driver module that has synchronous statements and other elements in clock domain ``pix``. The designer of the video output module can simply use the clock domain name ``pix`` in that module. In the top-level system module, the video output submodules are named ``video0`` and ``video1``. Migen then automatically renames the ``pix`` clock domain of each module to ``video0_pix`` and ``video1_pix``. Note that happens only because the clock domain is defined (using ClockDomain objects), not simply referenced (using e.g. synchronous statements) in the video output modules.

Clock domain name overlap is an error condition when any of the submodules that defines the clock domains is anonymous.

Finalization mechanism
======================

Sometimes, it is desirable that some of a module logic be created only after the user has finished manipulating that module. For example, the FSM module supports that states be defined dynamically, and the width of the state signal can be known only after all states have been added. One solution is to declare the final number of states in the FSM constructor, but this is not user-friendly. A better solution is to automatically create the state signal just before the FSM module is converted to V*HDL. Migen supports this using the so-called finalization mechanism.

Modules can overload a ``do_finalize`` method that can create logic and is called using the algorithm below:

#. Finalization of the current module begins.
#. If the module has already been finalized (e.g. manually), the procedure stops here.
#. Submodules of the current module are recursively finalized.
#. ``do_finalize`` is called for the current module.
#. Any new submodules created by the current module's ``do_finalize`` are recursively finalized.

Finalization is automatically invoked at V*HDL conversion and at simulation. It can be manually invoked for any module by calling its ``finalize`` method.

The clock domain management mechanism explained above happens during finalization.

Conversion for synthesis
************************

Any FHDL module can be converted into synthesizable Verilog HDL. This is accomplished by using the ``convert`` function in the ``migen.fhdl.verilog`` module: ::

  # define FHDL module MyDesign here

  if __name__ == "__main__":
    from migen.fhdl.verilog import convert
    convert(MyDesign()).write("my_design.v")

The ``migen.build`` component provides scripts to interface third-party FPGA tools (from Xilinx, Altera and Lattice) to Migen, and a database of boards for the easy deployment of designs.
