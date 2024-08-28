#
# Copyright 2011-2022 Martin Owens <doctormo@geek-2.com>
#
# This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>
#
# pylint: disable=wrong-import-position
"""
This is a wrapper layer to make interacting with Gtk a little less painful.
The main issues with Gtk is that it expects an awful lot of the developer,
code which is repeated over and over and patterns which every single developer
will use are not given easy to use convenience functions.

This makes Gtk programming WET, unattractive and error prone. This module steps
inbetween and adds in all those missing bits. It's not meant to replace Gtk and
certainly it's possible to use Gtk and threading directly.

.. versionadded:: 1.2
"""

import os
import sys
import logging
import threading

from ..utils import DependencyError

try:
    import gi

    gi.require_version("Gtk", "3.0")

    # Importing while covering stderr because pygobject has broken
    # warnings support and will force import warnings on our users.
    tmp, sys.stderr = sys.stderr, None  # type: ignore
    from gi.repository import Gtk, GLib

    sys.stderr = tmp  # type: ignore
except ImportError:  # pragma: no cover
    raise DependencyError(
        "You are missing the required libraries for Gtk."
        " Please report this problem to the Inkscape developers."
    )

from .app import GtkApp
from .window import Window, ChildWindow, FakeWidget
from .listview import TreeView, IconView, ViewColumn, ViewSort, Separator
from .pixmap import PixmapManager
