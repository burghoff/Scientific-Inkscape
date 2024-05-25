# -*- coding: utf-8 -*-
#
# Copyright (c) Aaron Spike <aaron@ekips.org>
#               Aurélio A. Heckert <aurium(a)gmail.com>
#               Bulia Byak <buliabyak@users.sf.net>
#               Nicolas Dufour, nicoduf@yahoo.fr
#               Peter J. R. Moulder <pjrm@users.sourceforge.net>
#               Martin Owens <doctormo@gmail.com>
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
#
"""
Convert to and from various units and find the closest matching unit.
"""

import re

# a dictionary of unit to user unit conversion factors
CONVERSIONS = {
    "in": 96.0,
    "pt": 1.3333333333333333,
    "px": 1.0,
    "mm": 3.779527559055118,
    "cm": 37.79527559055118,
    "m": 3779.527559055118,
    "km": 3779527.559055118,
    "Q": 0.94488188976378,
    "pc": 16.0,
    "yd": 3456.0,
    "ft": 1152.0,
    "": 1.0,  # Default px
}

# allowed unit types, including percentages, relative units, and others
# that are not suitable for direct conversion to a length.
# Note that this is _not_ an exhaustive list of allowed unit types.
UNITS = [
    "in",
    "pt",
    "px",
    "mm",
    "cm",
    "m",
    "km",
    "Q",
    "pc",
    "yd",
    "ft",
    "",
    "%",
    "em",
    "ex",
    "ch",
    "rem",
    "vw",
    "vh",
    "vmin",
    "vmax",
    "deg",
    "grad",
    "rad",
    "turn",
    "s",
    "ms",
    "Hz",
    "kHz",
    "dpi",
    "dpcm",
    "dppx",
]

UNIT_MATCH = re.compile(rf"({'|'.join(UNITS)})")
NUMBER_MATCH = re.compile(r"(([-+]?[0-9]+(\.[0-9]*)?|[-+]?\.[0-9]+)([eE][-+]?[0-9]+)?)")
BOTH_MATCH = re.compile(rf"^\s*{NUMBER_MATCH.pattern}\s*{UNIT_MATCH.pattern}\s*$")


def parse_unit(value, default_unit="px", default_value=None):
    """
    Takes a value such as 55.32px and returns (55.32, 'px')
    Returns default (None) if no match can be found
    """
    ret = BOTH_MATCH.match(str(value))
    if ret:
        return float(ret.groups()[0]), ret.groups()[-1] or default_unit
    return (default_value, default_unit) if default_value is not None else None


def are_near_relative(point_a, point_b, eps=0.01):
    """Return true if the points are near to eps"""
    return (point_a - point_b <= point_a * eps) and (
        point_a - point_b >= -point_a * eps
    )


def discover_unit(value, viewbox, default="px"):
    """Attempt to detect the unit being used based on the viewbox"""
    # Default 100px when width can't be parsed
    (value, unit) = parse_unit(value, default_value=100.0)
    if unit not in CONVERSIONS:
        return default
    this_factor = CONVERSIONS[unit] * value / viewbox

    # try to find the svgunitfactor in the list of units known. If we don't find
    # something, ...
    for unit, unit_factor in CONVERSIONS.items():
        if unit != "":
            # allow 1% error in factor
            if are_near_relative(this_factor, unit_factor, eps=0.01):
                return unit
    return default


def convert_unit(value, to_unit, default="px"):
    """Returns userunits given a string representation of units in another system

    Args:
        value: <length> string
        to_unit: unit to convert to
        default: if ``value`` contains no unit, what unit should be assumed.

            .. versionadded:: 1.1
    """
    value, from_unit = parse_unit(value, default_unit=default, default_value=0.0)
    if from_unit in CONVERSIONS and to_unit in CONVERSIONS:
        return (
            value * CONVERSIONS[from_unit] / CONVERSIONS.get(to_unit, CONVERSIONS["px"])
        )
    return 0.0


def render_unit(value, unit):
    """Checks and then renders a number with its unit"""
    try:
        if isinstance(value, str):
            (value, unit) = parse_unit(value, default_unit=unit)
        return f"{value:.6g}{ unit:s}"
    except TypeError:
        return ""
