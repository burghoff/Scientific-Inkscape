#!/usr/bin/env python
# coding=utf-8
#
# Copyright (c) 2025 David Burghoff <burghoff@utexas.edu>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""
Machine-local temporary directory for Scientific Inkscape.

This is the single source of truth for where SI puts its scratch and log
files. It is deliberately dependency-free (only os/sys/tempfile) so it can be
imported very early -- in particular by the launcher scripts before they
redirect stdout/stderr to a log file, i.e. before dhelpers/inkex are loaded.

Because the location is derived purely from the local machine's temp folder,
callers must never pass an already-computed path between machines (a launcher
.bat that syncs across machines via a shared cloud drive would otherwise carry
the generating machine's path). Everyone -- dhelpers.shared_temp, and the AE
and GV launcher scripts -- computes it here instead.
"""

import os
import sys
import tempfile


def root():
    """Return the machine-local ``si_temp`` directory, creating it (and the
    system temp dir) if needed."""
    # tempfile.gettempdir() is unreliable under some Linux Snap distributions,
    # so fall back to SI's own directory there.
    if sys.executable[0:4] == "/tmp" or sys.executable[0:5] == "/snap":
        system_temp = os.path.dirname(os.path.realpath(__file__))
    else:
        system_temp = tempfile.gettempdir()
    if not os.path.exists(system_temp):
        os.makedirs(system_temp, exist_ok=True)

    tempdir = os.path.join(os.path.abspath(system_temp), "si_temp")
    if not os.path.exists(tempdir):
        os.makedirs(tempdir, exist_ok=True)
    return tempdir


def path(filename):
    """Absolute path to ``filename`` inside the ``si_temp`` directory (the
    directory is ensured to exist)."""
    return os.path.join(root(), filename)
