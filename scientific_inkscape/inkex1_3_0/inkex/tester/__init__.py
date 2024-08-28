# coding=utf-8
#
# Copyright (C) 2018-2019 Martin Owens
#               2019 Thomas Holder
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110, USA.
#
"""
Testing module. See :ref:`unittests` for details.
"""

import os
import re
import sys
import shutil
import tempfile
import hashlib
import random
import uuid
import io
from typing import List, Union, Tuple, Type, TYPE_CHECKING

from io import BytesIO, StringIO
import xml.etree.ElementTree as xml

from unittest import TestCase as BaseCase
from inkex.base import InkscapeExtension

from .. import Transform, load_svg, SvgDocumentElement
from ..utils import to_bytes
from .xmldiff import xmldiff
from .mock import MockCommandMixin, Capture

if TYPE_CHECKING:
    from .filters import Compare

COMPARE_DELETE, COMPARE_CHECK, COMPARE_WRITE, COMPARE_OVERWRITE = range(4)


class NoExtension(InkscapeExtension):  # pylint: disable=too-few-public-methods
    """Test case must specify 'self.effect_class' to assertEffect."""

    def __init__(self, *args, **kwargs):  # pylint: disable=super-init-not-called
        raise NotImplementedError(self.__doc__)

    def run(self, args=None, output=None):
        """Fake run"""


class TestCase(MockCommandMixin, BaseCase):
    """
    Base class for all effects tests, provides access to data_files and
    test_without_parameters
    """

    effect_class = NoExtension  # type: Type[InkscapeExtension]
    effect_name = property(lambda self: self.effect_class.__module__)

    # If set to true, the output is not expected to be the stdout SVG document, but
    # rather text or a message sent to the stderr, this is highly weird. But sometimes
    # happens.
    stderr_output = False
    stdout_protect = True
    stderr_protect = True

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._temp_dir = None
        self._effect = None

    def setUp(self):  # pylint: disable=invalid-name
        """Make sure every test is seeded the same way"""
        self._effect = None
        super().setUp()
        random.seed(0x35F)

    def tearDown(self):
        super().tearDown()
        if self._temp_dir and os.path.isdir(self._temp_dir):
            shutil.rmtree(self._temp_dir)

    @classmethod
    def __file__(cls):
        """Create a __file__ property which acts much like the module version"""
        return os.path.abspath(sys.modules[cls.__module__].__file__)

    @classmethod
    def _testdir(cls):
        """Get's the folder where the test exists (so data can be found)"""
        return os.path.dirname(cls.__file__())

    @classmethod
    def rootdir(cls):
        """Return the full path to the extensions directory"""
        return os.path.dirname(cls._testdir())

    @classmethod
    def datadir(cls):
        """Get the data directory (can be over-ridden if needed)"""
        return os.path.join(cls._testdir(), "data")

    @property
    def tempdir(self):
        """Generate a temporary location to store files"""
        if self._temp_dir is None:
            self._temp_dir = os.path.realpath(tempfile.mkdtemp(prefix="inkex-tests-"))
        if not os.path.isdir(self._temp_dir):
            raise IOError("The temporary directory has disappeared!")
        return self._temp_dir

    def temp_file(
        self, prefix="file-", template="{prefix}{name}{suffix}", suffix=".tmp"
    ):
        """Generate the filename of a temporary file"""
        filename = template.format(prefix=prefix, suffix=suffix, name=uuid.uuid4().hex)
        return os.path.join(self.tempdir, filename)

    @classmethod
    def data_file(cls, filename, *parts, check_exists=True):
        """Provide a data file from a filename, can accept directories as arguments.

        .. versionchanged:: 1.2
            ``check_exists`` parameter added"""
        if os.path.isabs(filename):
            # Absolute root was passed in, so we trust that (it might be a tempdir)
            full_path = os.path.join(filename, *parts)
        else:
            # Otherwise we assume it's relative to the test data dir.
            full_path = os.path.join(cls.datadir(), filename, *parts)

        if not os.path.isfile(full_path) and check_exists:
            raise IOError(f"Can't find test data file: {full_path}")
        return full_path

    @property
    def empty_svg(self):
        """Returns a common minimal svg file"""
        return self.data_file("svg", "default-inkscape-SVG.svg")

    def assertAlmostTuple(
        self, found, expected, precision=8, msg=""
    ):  # pylint: disable=invalid-name
        """
        Floating point results may vary with computer architecture; use
        assertAlmostEqual to allow a tolerance in the result.
        """
        self.assertEqual(len(found), len(expected), msg)
        for fon, exp in zip(found, expected):
            self.assertAlmostEqual(fon, exp, precision, msg)

    def assertEffectEmpty(self, effect, **kwargs):  # pylint: disable=invalid-name
        """Assert calling effect without any arguments"""
        self.assertEffect(effect=effect, **kwargs)

    def assertEffect(self, *filename, **kwargs):  # pylint: disable=invalid-name
        """Assert an effect, capturing the output to stdout.

        filename should point to a starting svg document, default is empty_svg
        """
        if filename:
            data_file = self.data_file(*filename)
        else:
            data_file = self.empty_svg

        os.environ["DOCUMENT_PATH"] = data_file
        args = [data_file] + list(kwargs.pop("args", []))
        args += [f"--{kw[0]}={kw[1]}" for kw in kwargs.items()]

        effect = kwargs.pop("effect", self.effect_class)()

        # Output is redirected to this string io buffer
        if self.stderr_output:
            with Capture("stderr") as stderr:
                effect.run(args, output=BytesIO())
                effect.test_output = stderr
        else:
            output = BytesIO()
            with Capture(
                "stdout", kwargs.get("stdout_protect", self.stdout_protect)
            ) as stdout:
                with Capture(
                    "stderr", kwargs.get("stderr_protect", self.stderr_protect)
                ) as stderr:
                    effect.run(args, output=output)
                    self.assertEqual(
                        "", stdout.getvalue(), "Extra print statements detected"
                    )
                    self.assertEqual(
                        "", stderr.getvalue(), "Extra error or warnings detected"
                    )
            effect.test_output = output

        if os.environ.get("FAIL_ON_DEPRECATION", False):
            warnings = getattr(effect, "warned_about", set())
            effect.warned_about = set()  # reset for next test
            self.assertFalse(warnings, "Deprecated API is still being used!")

        return effect

    # pylint: disable=invalid-name
    def assertDeepAlmostEqual(self, first, second, places=None, msg=None, delta=None):
        """Asserts that two objects, possible nested lists, are almost equal."""
        if delta is None and places is None:
            places = 7
        if isinstance(first, (list, tuple)):
            assert len(first) == len(second)
            for f, s in zip(first, second):
                self.assertDeepAlmostEqual(f, s, places, msg, delta)
        else:
            self.assertAlmostEqual(first, second, places, msg, delta)

    def assertTransformEqual(self, lhs, rhs, places=7):
        """Assert that two transform expressions evaluate to the same
        transformation matrix.

        .. versionadded:: 1.1
        """
        self.assertAlmostTuple(
            tuple(Transform(lhs).to_hexad()), tuple(Transform(rhs).to_hexad()), places
        )

    # pylint: enable=invalid-name

    @property
    def effect(self):
        """Generate an effect object"""
        if self._effect is None:
            self._effect = self.effect_class()
        return self._effect

    def import_string(self, string, *args) -> SvgDocumentElement:
        """Runs a string through an import extension, with optional arguments
        provided as "--arg=value" arguments"""
        stream = io.BytesIO(string.encode())
        reader = self.effect_class()
        out = io.BytesIO()
        reader.parse_arguments([*args])
        reader.options.input_file = stream
        reader.options.output = out
        reader.load_raw()
        reader.save_raw(reader.effect())
        out.seek(0)
        decoded = out.read().decode("utf-8")
        document = load_svg(decoded)
        return document


class InkscapeExtensionTestMixin:
    """Automatically setup self.effect for each test and test with an empty svg"""

    def setUp(self):  # pylint: disable=invalid-name
        """Check if there is an effect_class set and create self.effect if it is"""
        super().setUp()
        if self.effect_class is None:
            self.skipTest("self.effect_class is not defined for this this test")

    def test_default_settings(self):
        """Extension works with empty svg file"""
        self.effect.run([self.empty_svg])


class ComparisonMixin:
    """
    Add comparison tests to any existing test suite.
    """

    compare_file: Union[List[str], Tuple[str], str] = "svg/shapes.svg"
    """This input svg file sent to the extension (if any)"""

    compare_filters = []  # type: List[Compare]
    """The ways in which the output is filtered for comparision (see filters.py)"""

    compare_filter_save = False
    """If true, the filtered output will be saved and only applied to the
    extension output (and not to the reference file)"""

    comparisons = [
        (),
        ("--id=p1", "--id=r3"),
    ]
    """A list of comparison runs, each entry will cause the extension to be run."""

    compare_file_extension = "svg"

    @property
    def _compare_file_extension(self):
        """The default extension to use when outputting check files in COMPARE_CHECK
        mode."""
        if self.stderr_output:
            return "txt"
        return self.compare_file_extension

    def test_all_comparisons(self):
        """Testing all comparisons"""
        if not isinstance(self.compare_file, (list, tuple)):
            self._test_comparisons(self.compare_file)
        else:
            for compare_file in self.compare_file:
                self._test_comparisons(
                    compare_file, addout=os.path.basename(compare_file)
                )

    def _test_comparisons(self, compare_file, addout=None):
        for args in self.comparisons:
            self.assertCompare(
                compare_file,
                self.get_compare_cmpfile(args, addout),
                args,
            )

    def assertCompare(
        self, infile, cmpfile, args, outfile=None
    ):  # pylint: disable=invalid-name
        """
        Compare the output of a previous run against this one.

        Args:
            infile: The filename of the pre-processed svg (or other type of file)
            cmpfile: The filename of the data we expect to get, if not set
                the filename will be generated from the effect name and kwargs.
            args: All the arguments to be passed to the effect run
            outfile: Optional, instead of returning a regular output, this extension
                dumps it's output to this filename instead.

        """
        compare_mode = int(os.environ.get("EXPORT_COMPARE", COMPARE_DELETE))

        effect = self.assertEffect(infile, args=args)

        if cmpfile is None:
            cmpfile = self.get_compare_cmpfile(args)

        if not os.path.isfile(cmpfile) and compare_mode == COMPARE_DELETE:
            raise IOError(
                f"Comparison file {cmpfile} not found, set EXPORT_COMPARE=1 to create "
                "it."
            )

        if outfile:
            if not os.path.isabs(outfile):
                outfile = os.path.join(self.tempdir, outfile)
            self.assertTrue(
                os.path.isfile(outfile), f"No output file created! {outfile}"
            )
            with open(outfile, "rb") as fhl:
                data_a = fhl.read()
        else:
            data_a = effect.test_output.getvalue()

        write_output = None
        if compare_mode == COMPARE_CHECK:
            _file = cmpfile[:-4] if cmpfile.endswith(".out") else cmpfile
            write_output = f"{_file}.{self._compare_file_extension}"
        elif (
            compare_mode == COMPARE_WRITE and not os.path.isfile(cmpfile)
        ) or compare_mode == COMPARE_OVERWRITE:
            write_output = cmpfile

        try:
            if write_output and not os.path.isfile(cmpfile):
                raise AssertionError(f"Check the output: {write_output}")
            with open(cmpfile, "rb") as fhl:
                data_b = self._apply_compare_filters(fhl.read(), False)
            self._base_compare(data_a, data_b, compare_mode)
        except AssertionError:
            if write_output:
                if isinstance(data_a, str):
                    data_a = data_a.encode("utf-8")
                with open(write_output, "wb") as fhl:
                    fhl.write(self._apply_compare_filters(data_a, True))
                    print(f"Written output: {write_output}")
                # This only reruns if the original test failed.
                # The idea here is to make sure the new output file is "stable"
                # Because some tests can produce random changes and we don't
                # want test authors to be too reassured by a simple write.
                if write_output == cmpfile:
                    effect = self.assertEffect(infile, args=args)
                    self._base_compare(data_a, cmpfile, COMPARE_CHECK)
            if not write_output == cmpfile:
                raise

    def _base_compare(self, data_a, data_b, compare_mode):
        data_a = self._apply_compare_filters(data_a)

        if (
            isinstance(data_a, bytes)
            and isinstance(data_b, bytes)
            and data_a.startswith(b"<")
            and data_b.startswith(b"<")
        ):
            # Late importing
            diff_xml, delta = xmldiff(data_a, data_b)
            if not delta and compare_mode == COMPARE_DELETE:
                print(
                    "The XML is different, you can save the output using the "
                    "EXPORT_COMPARE envionment variable. Set it to 1 to save a file "
                    "you can check, set it to 3 to overwrite this comparison, setting "
                    "the new data as the correct one.\n"
                )
            diff = "SVG Differences\n\n"
            if os.environ.get("XML_DIFF", False):
                diff = "<- " + diff_xml
            else:
                for x, (value_a, value_b) in enumerate(delta):
                    try:
                        # Take advantage of better text diff in testcase's own asserts.
                        self.assertEqual(value_a, value_b)
                    except AssertionError as err:
                        diff += f" {x}. {str(err)}\n"
            self.assertTrue(delta, diff)
        else:
            # compare any content (non svg)
            self.assertEqual(data_a, data_b)

    def _apply_compare_filters(self, data, is_saving=None):
        data = to_bytes(data)
        # Applying filters flips depending if we are saving the filtered content
        # to disk, or filtering during the test run. This is because some filters
        # are destructive others are useful for diagnostics.
        if is_saving is self.compare_filter_save or is_saving is None:
            for cfilter in self.compare_filters:
                data = cfilter(data)
        return data

    def get_compare_cmpfile(self, args, addout=None):
        """Generate an output file for the arguments given"""
        if addout is not None:
            args = list(args) + [str(addout)]
        opstr = (
            "__".join(args)
            .replace(self.tempdir, "TMP_DIR")
            .replace(self.datadir(), "DAT_DIR")
        )
        opstr = re.sub(r"[^\w-]", "__", opstr)
        if opstr:
            if len(opstr) > 127:
                # avoid filename-too-long error
                opstr = hashlib.md5(opstr.encode("latin1")).hexdigest()
            opstr = "__" + opstr
        return self.data_file(
            "refs", f"{self.effect_name}{opstr}.out", check_exists=False
        )
