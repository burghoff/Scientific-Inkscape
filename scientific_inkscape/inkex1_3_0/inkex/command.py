# coding=utf-8
#
# Copyright (C) 2019 Martin Owens
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
This API provides methods for calling Inkscape to execute a given
Inkscape command. This may be needed for various compiling options
(e.g., png), running other extensions or performing other options only
available via the shell API.

Best practice is to avoid using this API except when absolutely necessary,
since it is resource-intensive to invoke a new Inkscape instance.

However, in any circumstance when it is necessary to call Inkscape, it
is strongly recommended that you do so through this API, rather than calling
it yourself, to take advantage of the security settings and testing functions.

"""

import os
import re
import sys
from shutil import which as warlock

from subprocess import Popen, PIPE
from tempfile import TemporaryDirectory
from typing import List
from lxml.etree import ElementTree

from .elements import SvgDocumentElement

INKSCAPE_EXECUTABLE_NAME = os.environ.get("INKSCAPE_COMMAND")
if INKSCAPE_EXECUTABLE_NAME is None:
    if sys.platform == "win32":
        # prefer inkscape.exe over inkscape.com which spawns a command window
        INKSCAPE_EXECUTABLE_NAME = "inkscape.exe"
    else:
        INKSCAPE_EXECUTABLE_NAME = "inkscape"


class CommandNotFound(IOError):
    """Command is not found"""


class ProgramRunError(ValueError):
    """A specialized ValueError that is raised when a call to an external command fails.
    It stores additional information about a failed call to an external program.

    If only the ``program`` parameter is given, it is interpreted as the error message.
    Otherwise, the error message is compiled from all constructor parameters."""

    program: str
    """The absolute path to the called executable"""

    returncode: int
    """Return code of the program call"""

    stderr: str
    """stderr stream output of the call"""

    stdout: str
    """stdout stream output of the call"""

    arguments: List
    """Arguments of the call"""

    def __init__(self, program, returncode=None, stderr=None, stdout=None, args=None):
        self.program = program
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        self.arguments = args
        super().__init__(str(self))

    def __str__(self):
        if self.returncode is None:
            return self.program
        return (
            f"Return Code: {self.returncode}: {self.stderr}\n{self.stdout}"
            f"\nargs: {self.args}"
        )


def which(program):
    """
    Attempt different methods of trying to find if the program exists.
    """
    if os.path.isabs(program) and os.path.isfile(program):
        return program
    # On Windows, shutil.which may give preference to .py files in the current directory
    # (such as pdflatex.py), e.g. if .PY is in pathext, because the current directory is
    # prepended to PATH. This can be suppressed by explicitly appending the current
    # directory.

    try:
        if sys.platform == "win32":
            prog = warlock(program, path=os.environ["PATH"] + ";" + os.curdir)
            if prog:
                return prog
    except ImportError:
        pass

    try:
        # Python3 only version of which
        prog = warlock(program)
        if prog:
            return prog
    except ImportError:
        pass  # python2

    # There may be other methods for doing a `which` command for other
    # operating systems; These should go here as they are discovered.

    raise CommandNotFound(f"Can not find the command: '{program}'")


def write_svg(svg, *filename):
    """Writes an svg to the given filename"""
    filename = os.path.join(*filename)
    if os.path.isfile(filename):
        return filename
    with open(filename, "wb") as fhl:
        if isinstance(svg, SvgDocumentElement):
            svg = ElementTree(svg)
        if hasattr(svg, "write"):
            # XML document
            svg.write(fhl)
        elif isinstance(svg, bytes):
            fhl.write(svg)
        else:
            raise ValueError("Not sure what type of SVG data this is.")
    return filename


def to_arg(arg, oldie=False):
    """Convert a python argument to a command line argument"""
    if isinstance(arg, (tuple, list)):
        (arg, val) = arg
        arg = "-" + arg
        if len(arg) > 2 and not oldie:
            arg = "-" + arg
        if val is True:
            return arg
        if val is False:
            return None
        return f"{arg}={str(val)}"
    return str(arg)


def to_args(prog, *positionals, **arguments):
    """Compile arguments and keyword arguments into a list of strings which Popen will
    understand.

    :param prog:
        Program executable prepended to the output.
    :type first: ``str``

    :Arguments:
        * (``str``) -- String added as given
        * (``tuple``) -- Ordered version of Keyword Arguments, see below

    :Keyword Arguments:
        * *name* (``str``) --
          Becomes ``--name="val"``
        * *name* (``bool``) --
          Becomes ``--name``
        * *name* (``list``) --
          Becomes ``--name="val1"`` ...
        * *n* (``str``) --
          Becomes ``-n=val``
        * *n* (``bool``) --
          Becomes ``-n``

    :return: Returns a list of compiled arguments ready for Popen.
    :rtype: ``list[str]``
    """
    args = [prog]
    oldie = arguments.pop("oldie", False)
    for arg, value in arguments.items():
        arg = arg.replace("_", "-").strip()

        if isinstance(value, tuple):
            value = list(value)
        elif not isinstance(value, list):
            value = [value]

        for val in value:
            args.append(to_arg((arg, val), oldie))

    args += [to_arg(pos, oldie) for pos in positionals if pos is not None]
    # Filter out empty non-arguments
    return [arg for arg in args if arg is not None]


def to_args_sorted(prog, *positionals, **arguments):
    """same as :func:`to_args`, but keyword arguments are sorted beforehand

    .. versionadded:: 1.2"""
    return to_args(prog, *positionals, **dict(sorted(arguments.items())))


def _call(program, *args, **kwargs):
    stdin = kwargs.pop("stdin", None)
    if isinstance(stdin, str):
        stdin = stdin.encode("utf-8")
    inpipe = PIPE if stdin else None

    args = to_args(which(program), *args, **kwargs)

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # create no console window

    with Popen(
        args,
        shell=False,  # Never have shell=True
        stdin=inpipe,  # StdIn not used (yet)
        stdout=PIPE,  # Grab any output (return it)
        stderr=PIPE,  # Take all errors, just incase
        **kwargs,
    ) as process:
        (stdout, stderr) = process.communicate(input=stdin)
        if process.returncode == 0:
            return stdout
        raise ProgramRunError(program, process.returncode, stderr, stdout, args)


def call(program, *args, **kwargs):
    """
    Generic caller to open any program and return its stdout::

        stdout = call('executable', arg1, arg2, dash_dash_arg='foo', d=True, ...)

    Will raise :class:`ProgramRunError` if return code is not 0.

    Keyword arguments:
        return_binary: Should stdout return raw bytes (default: False)

            .. versionadded:: 1.1
        stdin: The string or bytes containing the stdin (default: None)

    All other arguments converted using :func:`to_args` function.
    """
    # We use this long input because it's less likely to conflict with --binary=
    binary = kwargs.pop("return_binary", False)
    stdout = _call(program, *args, **kwargs)
    # Convert binary to string when we wish to have strings we do this here
    # so the mock tests will also run the conversion (always returns bytes)
    if not binary and isinstance(stdout, bytes):
        return stdout.decode(sys.stdout.encoding or "utf-8")
    return stdout


def inkscape(svg_file, *args, **kwargs):
    """
    Call Inkscape with the given svg_file and the given arguments, see call().

    Returns the stdout of the call.

    .. versionchanged:: 1.3
        If the "actions" kwargs parameter is passed, it is checked whether the length of
        the action string might lead to issues with the Windows CLI call character
        limit. In this case, Inkscape is called in `--shell`
        mode and the actions are fed in via stdin. This avoids violating the character
        limit for command line arguments on Windows, which results in errors like this:
        `[WinError 206] The filename or extension is too long`.
        This workaround is also possible when calling Inkscape with long arguments
        to `--export-id` and `--query-id`, by converting the call to the appropriate
        action sequence. The stdout is cleaned to resemble non-interactive mode.
    """
    os.environ["SELF_CALL"] = "true"
    actions = kwargs.get("actions", None)
    strip_stdout = False
    # Keep some safe margin to the 8191 character limit.
    if actions is not None and len(actions) > 7000:
        args = args + ("--shell",)
        kwargs["stdin"] = actions
        kwargs.pop("actions")
        strip_stdout = True
    stdout = call(INKSCAPE_EXECUTABLE_NAME, svg_file, *args, **kwargs)
    if strip_stdout:
        split = re.split(r"\n> ", stdout)
        if len(split) > 1:
            if "\n" in split[1]:
                stdout = "\n".join(split[1].split("\n")[1:])
            else:
                stdout = ""
    return stdout


def inkscape_command(svg, select=None, actions=None, *args, **kwargs):
    """
    Executes Inkscape batch actions with the given <svg> input and returns a new <svg>.

    inkscape_command('<svg...>', [select=...], [actions=...], [...])
    """
    with TemporaryDirectory(prefix="inkscape-command") as tmpdir:
        svg_file = write_svg(svg, tmpdir, "input.svg")
        select = ("select", select) if select else None
        inkscape(
            svg_file,
            select,
            batch_process=True,
            export_overwrite=True,
            actions=actions,
            *args,
            **kwargs,
        )
        with open(svg_file, "rb") as fhl:
            return fhl.read()


def take_snapshot(svg, dirname, name="snapshot", ext="png", dpi=96, **kwargs):
    """
    Take a snapshot of the given svg file.

    Resulting filename is yielded back, after generator finishes, the
    file is deleted so you must deal with the file inside the for loop.
    """
    svg_file = write_svg(svg, dirname, name + ".svg")
    ext_file = os.path.join(dirname, name + "." + str(ext).lower())
    inkscape(
        svg_file, export_dpi=dpi, export_filename=ext_file, export_type=ext, **kwargs
    )
    return ext_file


def is_inkscape_available():
    """Return true if the Inkscape executable is available."""
    try:
        return bool(which(INKSCAPE_EXECUTABLE_NAME))
    except CommandNotFound:
        return False
