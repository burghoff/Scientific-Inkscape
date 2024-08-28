#!/usr/bin/env python
# coding=utf-8
#
# Copyright (c) 2023 David Burghoff <burghoff@utexas.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


"""
This submodule gives all TextElements and FlowRoots the parsed_text property,
which is a cached instance of ParsedText. To use, simply run

    import text

Following this, text properties will be available at el.parsed_text. For more
details, see parser.py. To check if it is working properly, run the
following on some text:

    el.parsed_text.Make_Highlights('char')

Rectangles should appear surrounding the logical extents of each character.

Before parsing is done, a character table must be generated to determine the properties
of all the characters present. This is done automatically by the first invocation of
.parsed_text, which automatically analyzes the whole document and adds it to the SVG.
If you are only parsing a few text elements, this can be sped up by calling
svg.make_char_table(els). On the rare occasions this fails, a command call may
be performed as a fallback.
"""

# Give inkex an inkex.text submodule that refers to this directory
import sys
import os
import inspect
import inkex

if not hasattr(inkex, "text"):
    import importlib

    mydir = os.path.dirname(os.path.abspath(__file__))
    myloc, myname = os.path.split(mydir)
    oldpath = sys.path
    sys.path.append(myloc)
    inkex.text = importlib.import_module(myname)
    sys.modules["inkex.text"] = inkex.text
    sys.path = oldpath

# Gives inkex elements some additional cached attributes, for further speedups
import inkex.text.cache  # pylint: disable=wrong-import-position


def add_cache(base, derived):
    """
    Adds the cache capabilities from a derived class to a base class by dynamically
    attaching methods, properties, and data descriptors that are unique to the derived
    class to the base class.
    """
    predfn = (
        lambda x: isinstance(x, property)
        or inspect.isfunction(x)
        or inspect.isdatadescriptor(x)
    )
    base_m = dict(inspect.getmembers(base, predicate=predfn))
    for name, memb in inspect.getmembers(derived, predicate=predfn):
        if memb not in base_m.values():
            setattr(base, name, memb)


add_cache(inkex.BaseElement, inkex.text.cache.BaseElementCache)
add_cache(inkex.SvgDocumentElement, inkex.text.cache.SvgDocumentElementCache)
add_cache(inkex.Style, inkex.text.cache.StyleCache)
