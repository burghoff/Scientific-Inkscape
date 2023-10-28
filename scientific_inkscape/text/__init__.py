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
#
#
# This submodule gives all TextElements and FlowRoots the parsed_text property,
# which is a cached instance of ParsedText. To use, simply run
#
#     import text
#
# Following this, text properties will be available at el.parsed_text. For more
# details, see TextParser.py. To check if it is working properly, run the
# following on some text:
#
#     el.parsed_text.Make_Highlights('char')
#
# Rectangles should appear surround the logical extents of each character.
#
# Before parsing is done, a character table must be generated to determine the properties
# of all the characters present. This is done automatically by the first invocation of .parsed_text,
# which automatically analyzes the whole document and adds it to the SVG. If you are only
# parsing a few text elements, this can be sped up by calling svg.make_char_table(els).
# On the rare occasions this fails, a command call may be performed as a fallback.

# Give inkex an inkex.text submodule that refers to this directory
import inkex, sys, os

if not hasattr(inkex, "text"):
    import importlib

    # mymodname = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
    # sys.modules["inkex.text"] = importlib.import_module(mymodname)

    mydir = os.path.dirname(os.path.abspath(__file__))
    myloc, myname = os.path.split(mydir)
    oldpath = sys.path
    sys.path.append(myloc)
    sys.modules["inkex.text"] = importlib.import_module(myname)
    sys.path = oldpath

# Patches inkex functions for faster operation
# This is optional
import inkex.text.speedups

# Gives inkex elements some additional cached attributes, for further speedups
# This is not optional
import inkex.text.cache


# Make sure Style can be hashed
def __hash__mod(self):
    # type: (inkex.Style) -> int
    return hash(tuple(self.items()))


inkex.Style.__hash__ = __hash__mod  # type: ignore


# Add parsed_text property to text, which is used to get the properties of text
def get_parsed_text(el):
    from inkex.text.TextParser import ParsedText  # import only if needed

    if not (hasattr(el, "_parsed_text")):
        el._parsed_text = ParsedText(el, el.croot.char_table)
    return el._parsed_text


def set_parsed_text(el, sv):
    if hasattr(el, "_parsed_text") and sv is None:
        delattr(el, "_parsed_text")


inkex.TextElement.parsed_text = property(get_parsed_text, set_parsed_text)
inkex.FlowRoot.parsed_text = property(get_parsed_text, set_parsed_text)

# Add char_table property to SVGs, which are used to collect all of the
# properties of fonts in the document. Alternatively, calling make_char_table
# on a subset of elements will cause only those elements to be included.
ttags = {inkex.TextElement.ctag, inkex.FlowRoot.ctag}


def make_char_table_fcn(svg, els=None):
    # Can be called with els argument to examine list of elements only
    # (otherwise use entire SVG)
    if els is None:
        tels = [d for d in svg.iddict.ds if d.tag in ttags]
    else:
        tels = [d for d in els if d.tag in ttags]
    if not (hasattr(svg, "_char_table")) or any(
        [t not in svg._char_table.els for t in tels]
    ):
        from inkex.text.TextParser import Character_Table  # import if needed

        svg._char_table = Character_Table(tels)


def get_char_table(svg):
    if not (hasattr(svg, "_char_table")):
        svg.make_char_table()
    return svg._char_table


def set_char_table(svg, sv):
    if sv is None and hasattr(svg, "_char_table"):
        delattr(svg, "_char_table")


inkex.SvgDocumentElement.make_char_table = make_char_table_fcn
inkex.SvgDocumentElement.char_table = property(get_char_table, set_char_table)
