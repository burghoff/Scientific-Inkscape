# coding=utf-8
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
# pylint: disable=invalid-name,missing-docstring
"""Deprecated ffgeom API"""

from collections import namedtuple

from inkex.deprecated import deprecate
from inkex.transforms import DirectedLineSegment as NewSeg

try:
    NaN = float("NaN")
except ValueError:
    PosInf = 1e300000
    NaN = PosInf / PosInf


class Point(namedtuple("Point", "x y")):
    __slots__ = ()

    def __getitem__(self, key):
        if isinstance(key, str):
            key = "xy".index(key)
        return super(Point, self).__getitem__(key)


class Segment(NewSeg):
    @deprecate
    def __init__(self, e0, e1):
        """inkex.transforms.Segment(((x1, y1), (x2, y2)))"""
        if isinstance(e0, dict):
            e0 = (e0["x"], e0["y"])
        if isinstance(e1, dict):
            e1 = (e1["x"], e1["y"])
        super(Segment, self).__init__((e0, e1))

    def __getitem__(self, key):
        if key:
            return {"x": self.x.maximum, "y": self.y.maximum}
        return {"x": self.x.minimum, "y": self.y.minimum}

    delta_x = lambda self: self.width
    delta_y = lambda self: self.height
    run = delta_x
    rise = delta_y

    def distanceToPoint(self, p):
        return self.distance_to_point(p["x"], p["y"])

    def perpDistanceToPoint(self, p):
        return self.perp_distance(p["x"], p["y"])

    def angle(self):
        return super(Segment, self).angle

    def length(self):
        return super(Segment, self).length

    def pointAtLength(self, length):
        return self.point_at_length(length)

    def pointAtRatio(self, ratio):
        return self.point_at_ratio(ratio)

    def createParallel(self, p):
        self.parallel(p["x"], p["y"])


@deprecate
def intersectSegments(s1, s2):
    """transforms.Segment(s1).intersect(s2)"""
    return Point(*s1.intersect(s2))


@deprecate
def dot(s1, s2):
    """transforms.Segment(s1).dot(s2)"""
    return s1.dot(s2)
