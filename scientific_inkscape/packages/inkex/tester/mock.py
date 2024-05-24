# coding=utf-8
#
# Copyright (C) 2018 Martin Owens
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
# pylint: disable=protected-access,too-few-public-methods
"""
Any mocking utilities required by testing. Mocking is when you need the test
to exercise a piece of code, but that code may or does call on something
outside of the target code that either takes too long to run, isn't available
during the test running process or simply shouldn't be running at all.
"""

import io
import os
import sys
import logging
import hashlib
import tempfile
from typing import List, Tuple, Any

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.parser import Parser as EmailParser

import inkex.command


FIXED_BOUNDARY = "--CALLDATA--//--CALLDATA--"


class Capture:
    """Capture stdout or stderr. Used as `with Capture('stdout') as stream:`"""

    def __init__(self, io_name="stdout", swap=True):
        self.io_name = io_name
        self.original = getattr(sys, io_name)
        self.stream = io.StringIO()
        self.swap = swap

    def __enter__(self):
        if self.swap:
            setattr(sys, self.io_name, self.stream)
        return self.stream

    def __exit__(self, exc, value, traceback):
        if exc is not None and self.swap:
            # Dump content back to original if there was an error.
            self.original.write(self.stream.getvalue())
        setattr(sys, self.io_name, self.original)


class ManualVerbosity:
    """Change the verbosity of the test suite manually"""

    result = property(lambda self: self.test._current_result)

    def __init__(self, test, okay=True, dots=False):
        self.test = test
        self.okay = okay
        self.dots = dots

    def flip(
        self, exc_type=None, exc_val=None, exc_tb=None
    ):  # pylint: disable=unused-argument
        """Swap the stored verbosity with the original"""
        self.okay, self.result.showAll = self.result.showAll, self.okay
        self.dots, self.result.dots = self.result.dots, self.okay

    __enter__ = flip
    __exit__ = flip


class MockMixin:
    """
    Add mocking ability to any test base class, will set up mock on setUp
    and remove it on tearDown.

    Mocks are stored in an array attached to the test class (not instance!) which
    ensures that mocks can only ever be setUp once and can never be reset over
    themselves. (just in case this looks weird at first glance)

    class SomeTest(MockingMixin, TestBase):
        mocks = [(sys, 'exit', NoSystemExit("Nope!")]
    """

    mocks = []  # type: List[Tuple[Any, str, Any]]

    def setUpMock(self, owner, name, new):  # pylint: disable=invalid-name
        """Setup the mock here, taking name and function and returning (name, old)"""
        old = getattr(owner, name)
        if isinstance(new, str):
            if hasattr(self, new):
                new = getattr(self, new)
        if isinstance(new, Exception):

            def _error_function(*args2, **kw2):  # pylint: disable=unused-argument
                raise type(new)(str(new))

            setattr(owner, name, _error_function)
        elif new is None or isinstance(new, (str, int, float, list, tuple)):

            def _value_function(*args, **kw):  # pylint: disable=unused-argument
                return new

            setattr(owner, name, _value_function)
        else:
            setattr(owner, name, new)
        # When we start, mocks contains length 3 tuples, when we're finished, it
        # contains length 4, this stops remocking and reunmocking from taking place.
        return (owner, name, old, False)

    def setUp(self):  # pylint: disable=invalid-name
        """For each mock instruction, set it up and store the return"""
        super().setUp()
        for x, mock in enumerate(self.mocks):
            if len(mock) == 4:
                logging.error(
                    "Mock was already set up, so it wasn't cleared previously!"
                )
                continue
            self.mocks[x] = self.setUpMock(*mock)

    def tearDown(self):  # pylint: disable=invalid-name
        """For each returned stored, tear it down and restore mock instruction"""
        super().tearDown()
        try:
            for x, (owner, name, old, _) in enumerate(self.mocks):
                self.mocks[x] = (owner, name, getattr(owner, name))
                setattr(owner, name, old)
        except ValueError:
            logging.warning("Was never mocked, did something go wrong?")

    def old_call(self, name):
        """Get the original caller"""
        for arg in self.mocks:
            if arg[1] == name:
                return arg[2]
        return lambda: None


class MockCommandMixin(MockMixin):
    """
    Replace all the command functions with testable replacements.

    This stops the pipeline and people without the programs, running into problems.
    """

    mocks = [
        (inkex.command, "_call", "mock_call"),
        (tempfile, "mkdtemp", "record_tempdir"),
    ]
    recorded_tempdirs = []  # type:List[str]

    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()
        # This is a the daftest thing I've ever seen, when in the middle
        # of a mock, the 'self' variable magically turns from a FooTest
        # into a TestCase, this makes it impossible to find the datadir.
        from . import TestCase

        TestCase._mockdatadir = self.datadir()

    @classmethod
    def cmddir(cls):
        """Returns the location of all the mocked command results"""
        from . import TestCase

        return os.path.join(TestCase._mockdatadir, "cmd")

    def record_tempdir(self, *args, **kwargs):
        """Record any attempts to make tempdirs"""
        newdir = self.old_call("mkdtemp")(*args, **kwargs)
        self.recorded_tempdirs.append(os.path.realpath(newdir))
        return newdir

    def clean_paths(self, data, files):
        """Clean a string of any files or tempdirs"""

        def replace(indata, replaced, replacement):
            if isinstance(indata, str):
                indata = indata.replace(replaced, replacement)
            else:
                indata = [i.replace(replaced, replacement) for i in indata]
            return indata

        try:
            for fdir in self.recorded_tempdirs:
                data = replace(data, fdir + os.sep, "./")
                data = replace(data, fdir, ".")
                files = replace(files, fdir + os.sep, "./")
                files = replace(files, fdir, ".")
            for fname in files:
                data = replace(data, fname, os.path.basename(fname))
        except (UnicodeDecodeError, TypeError):
            pass
        return data

    def get_all_tempfiles(self):
        """Returns a set() of all files currently in any of the tempdirs"""
        ret = set([])
        for fdir in self.recorded_tempdirs:
            if not os.path.isdir(fdir):
                continue
            for fname in os.listdir(fdir):
                if fname in (".", ".."):
                    continue
                path = os.path.join(fdir, fname)
                # We store the modified time so if a program modifies
                # the input file in-place, it will look different.
                ret.add(path + f";{os.path.getmtime(path)}")

        return ret

    def ignore_command_mock(self, program, arglst, path):
        """Return true if the mock is ignored"""
        if self and program and arglst:
            env = os.environ.get("NO_MOCK_COMMANDS", 0)
            if (not os.path.exists(path) and int(env) == 1) or int(env) == 2:
                return True
        return False

    def mock_call(self, program, *args, **kwargs):
        """
        Replacement for the inkex.command.call() function, instead of calling
        an external program, will compile all arguments into a hash and use the
        hash to find a command result.
        """
        # Remove stdin first because it needs to NOT be in the Arguments list.
        stdin = kwargs.pop("stdin", None)
        args = list(args)

        # We use email
        msg = MIMEMultipart(boundary=FIXED_BOUNDARY)
        msg["Program"] = MockCommandMixin.get_program_name(program)

        # Gather any output files and add any input files to msg, args and kwargs
        # may be modified to strip out filename directories (which change)
        inputs, outputs = self.add_call_files(msg, args, kwargs)

        arglst = inkex.command.to_args_sorted(program, *args, **kwargs)[1:]
        arglst = self.clean_paths(arglst, inputs + outputs)
        argstr = " ".join(arglst)
        msg["Arguments"] = argstr.strip()

        if stdin is not None:
            # The stdin is counted as the msg body
            cleanin = (
                self.clean_paths(stdin, inputs + outputs)
                .replace("\r\n", "\n")
                .replace(".\\", "./")
            )
            msg.attach(MIMEText(cleanin, "plain", "utf-8"))

        keystr = msg.as_string()
        # On Windows, output is separated by CRLF
        keystr = keystr.replace("\r\n", "\n")
        # There is a difference between python2 and python3 output
        keystr = keystr.replace("\n\n", "\n")
        keystr = keystr.replace("\n ", " ")
        if "verb" in keystr:
            # Verbs seperated by colons cause diff in py2/3
            keystr = keystr.replace("; ", ";")
        # Generate a unique key for this call based on _all_ it's inputs
        key = hashlib.md5(keystr.encode("utf-8")).hexdigest()

        if self.ignore_command_mock(
            program, arglst, self.get_call_filename(program, key, create=True)
        ):
            # Call original code. This is so programmers can run the test suite
            # against the external programs too, to see how their fair.
            if stdin is not None:
                kwargs["stdin"] = stdin

            before = self.get_all_tempfiles()
            stdout = self.old_call("_call")(program, *args, **kwargs)
            outputs += list(self.get_all_tempfiles() - before)
            # Remove the modified time from the call
            outputs = [out.rsplit(";", 1)[0] for out in outputs]

            # After the program has run, we collect any file outputs and store
            # them, then store any stdout or stderr created during the run.
            # A developer can then use this to build new test cases.
            reply = MIMEMultipart(boundary=FIXED_BOUNDARY)
            reply["Program"] = MockCommandMixin.get_program_name(program)
            reply["Arguments"] = argstr
            self.save_call(program, key, stdout, outputs, reply)
            self.save_key(program, key, keystr, "key")
            return stdout

        try:
            return self.load_call(program, key, outputs)
        except IOError as err:
            self.save_key(program, key, keystr, "bad-key")
            raise IOError(
                f"Problem loading call: {program}/{key} use the environment variable "
                "NO_MOCK_COMMANDS=1 to call out to the external program and generate "
                f"the mock call file for call {program} {argstr}."
            ) from err

    def add_call_files(self, msg, args, kwargs):
        """
        Gather all files, adding input files to the msg (for hashing) and
        output files to the returned files list (for outputting in debug)
        """
        # Gather all possible string arguments together.
        loargs = sorted(kwargs.items(), key=lambda i: i[0])
        values = []
        for arg in args:
            if isinstance(arg, (tuple, list)):
                loargs.append(arg)
            else:
                values.append(str(arg))

        for _, value in loargs:
            if isinstance(value, (tuple, list)):
                for val in value:
                    if val is not True:
                        values.append(str(val))
            elif value is not True:
                values.append(str(value))

        # See if any of the strings could be filenames, either going to be
        # or are existing files on the disk.
        files = [[], []]
        for value in values:
            if os.path.isfile(value):  # Input file
                files[0].append(value)
                self.add_call_file(msg, value)
            elif os.path.isdir(os.path.dirname(value)):  # Output file
                files[1].append(value)
        return files

    def add_call_file(self, msg, filename):
        """Add a single file to the given mime message"""
        fname = os.path.basename(filename)
        with open(filename, "rb") as fhl:
            if filename.endswith(".svg"):
                value = self.clean_paths(fhl.read().decode("utf8"), [])
            else:
                value = fhl.read()
                try:
                    value = value.decode()
                except UnicodeDecodeError:
                    pass  # do not attempt to process binary files further
            if isinstance(value, str):
                value = value.replace("\r\n", "\n").replace(".\\", "./")
            part = MIMEApplication(value, Name=fname)
        # After the file is closed
        part["Content-Disposition"] = "attachment"
        part["Filename"] = fname
        msg.attach(part)

    def get_call_filename(self, program, key, create=False):
        """
        Get the filename for the call testing information.
        """
        path = self.get_call_path(program, create=create)
        fname = os.path.join(path, key + ".msg")
        if not create and not os.path.isfile(fname):
            raise IOError(f"Attempted to find call test data {key}")
        return fname

    @staticmethod
    def get_program_name(program):
        """Takes a program and returns a program name"""
        if program == inkex.command.INKSCAPE_EXECUTABLE_NAME:
            return "inkscape"
        return program

    def get_call_path(self, program, create=True):
        """Get where this program would store it's test data"""
        command_dir = os.path.join(
            self.cmddir(), MockCommandMixin.get_program_name(program)
        )
        if not os.path.isdir(command_dir):
            if create:
                os.makedirs(command_dir)
            else:
                raise IOError(
                    "A test is attempting to use an external program in a test:"
                    f" {program}; but there is not a command data directory which "
                    f"should contain the results of the command here: {command_dir}"
                )
        return command_dir

    def load_call(self, program, key, files):
        """
        Load the given call
        """
        fname = self.get_call_filename(program, key, create=False)
        with open(fname, "rb") as fhl:
            msg = EmailParser().parsestr(fhl.read().decode("utf-8"))

        stdout = None
        for part in msg.walk():
            if "attachment" in part.get("Content-Disposition", ""):
                base_name = part["Filename"]
                for out_file in files:
                    if out_file.endswith(base_name):
                        with open(out_file, "wb") as fhl:
                            fhl.write(part.get_payload(decode=True))
                            part = None
                if part is not None:
                    # Was not caught by any normal outputs, so we will
                    # save the file to EVERY tempdir in the hopes of
                    # hitting on of them.
                    for fdir in self.recorded_tempdirs:
                        if os.path.isdir(fdir):
                            with open(os.path.join(fdir, base_name), "wb") as fhl:
                                fhl.write(part.get_payload(decode=True))
            elif part.get_content_type() == "text/plain":
                stdout = part.get_payload(decode=True)

        return stdout

    def save_call(
        self, program, key, stdout, files, msg, ext="output"
    ):  # pylint: disable=too-many-arguments
        """
        Saves the results from the call into a debug output file, the resulting files
        should be a Mime msg file format with each attachment being one of the input
        files as well as any stdin and arguments used in the call.
        """
        if stdout is not None and stdout.strip():
            # The stdout is counted as the msg body here
            msg.attach(MIMEText(stdout.decode("utf-8"), "plain", "utf-8"))

        for fname in set(files):
            if os.path.isfile(fname):
                # print("SAVING FILE INTO MSG: {}".format(fname))
                self.add_call_file(msg, fname)
            else:
                part = MIMEText("Missing File", "plain", "utf-8")
                part.add_header("Filename", os.path.basename(fname))
                msg.attach(part)
        fname = self.get_call_filename(program, key, create=True) + "." + ext

        with open(fname, "wb") as fhl:
            fhl.write(msg.as_string().encode("utf-8"))
        if int(os.environ.get("NO_MOCK_COMMANDS", 0)) == 1:
            print(f"Saved mock call as {fname}, remove .{ext}")

    def save_key(self, program, key, keystr, ext="key"):
        """Save the key file if we are debugging the key data"""
        if os.environ.get("DEBUG_KEY"):
            fname = self.get_call_filename(program, key, create=True) + "." + ext
            with open(fname, "wb") as fhl:
                fhl.write(keystr.encode("utf-8"))
