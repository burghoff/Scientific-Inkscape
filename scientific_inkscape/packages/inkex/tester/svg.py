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
"""
SVG specific utilities for tests.
"""

from lxml import etree

from inkex import SVG_PARSER


def svg(svg_attrs=""):
    """Returns xml etree based on a simple SVG element.

    svg_attrs: A string containing attributes to add to the
        root <svg> element of a minimal SVG document.
    """
    return etree.fromstring(
        str.encode(
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
            f"<svg {svg_attrs}></svg>"
        ),
        parser=SVG_PARSER,
    )


def svg_unit_scaled(width_unit):
    """Same as svg, but takes a width unit (top-level transform) for the new document.

    The transform is the ratio between the SVG width and the viewBox width.
    """
    return svg(f'width="1{width_unit}" viewBox="0 0 1 1"')


def svg_file(filename):
    """Parse an svg file and return it's document root"""
    with open(filename, "r", encoding="utf-8") as fhl:
        doc = etree.parse(fhl, parser=SVG_PARSER)
        return doc.getroot()
