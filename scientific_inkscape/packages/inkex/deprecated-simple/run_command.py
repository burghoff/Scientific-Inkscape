# coding=utf-8
#
# Copyright (C) 2008 Stephen Silver
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA
#
"""
Deprecated module for running SVG-generating commands in Inkscape extensions
"""
import os
import sys
import tempfile
from subprocess import Popen, PIPE

from inkex.deprecated import deprecate


def run(command_format, prog_name):
    """inkex.commands.call(...)"""
    svgfile = tempfile.mktemp(".svg")
    command = command_format % svgfile
    msg = None
    # ps2pdf may attempt to write to the current directory, which may not
    # be writeable, so we switch to the temp directory first.
    try:
        os.chdir(tempfile.gettempdir())
    except IOError:
        pass

    try:
        proc = Popen(command, shell=True, stdout=PIPE, stderr=PIPE)
        return_code = proc.wait()
        out = proc.stdout.read()
        err = proc.stderr.read()

        if msg is None:
            if return_code:
                msg = "{} failed:\n{}\n{}\n".format(prog_name, out, err)
            elif err:
                sys.stderr.write(
                    "{} executed but logged the following error:\n{}\n{}\n".format(
                        prog_name, out, err
                    )
                )
    except Exception as inst:
        msg = "Error attempting to run {}: {}".format(prog_name, str(inst))

    # If successful, copy the output file to stdout.
    if msg is None:
        if os.name == "nt":  # make stdout work in binary on Windows
            import msvcrt

            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        try:
            with open(svgfile, "rb") as fhl:
                sys.stdout.write(fhl.read().decode(sys.stdout.encoding))
        except IOError as inst:
            msg = "Error reading temporary file: {}".format(str(inst))

    try:
        # Clean up.
        os.remove(svgfile)
    except (IOError, OSError):
        pass

    # Output error message (if any) and exit.
    return msg
