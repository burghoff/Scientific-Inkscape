# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 Martin Owens <doctormo@gmail.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Thomas Holder <thomas.holder@schrodinger.com>
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
# pylint: disable=arguments-differ
"""
Interface for all shapes/polygons such as lines, paths, rectangles, circles etc.
"""

from math import cos, pi, sin
from typing import Optional, Tuple
from ..paths import Arc, Curve, Move, Path, ZoneClose
from ..paths import Line as PathLine
from ..transforms import Transform, ImmutableVector2d, Vector2d
from ..bezier import pointdistance

from ._utils import addNS
from ._base import ShapeElement


class PathElementBase(ShapeElement):
    """Base element for path based shapes"""

    get_path = lambda self: Path(self.get("d"))

    @classmethod
    def new(cls, path, **attrs):
        return super().new(d=Path(path), **attrs)

    def set_path(self, path):
        """Set the given data as a path as the 'd' attribute"""
        self.set("d", str(Path(path)))

    def apply_transform(self):
        """Apply the internal transformation to this node and delete"""
        if "transform" in self.attrib:
            self.path = self.path.transform(self.transform)
            self.set("transform", Transform())

    @property
    def original_path(self):
        """Returns the original path if this is a LPE, or the path if not"""
        return Path(self.get("inkscape:original-d", self.path))

    @original_path.setter
    def original_path(self, path):
        if addNS("inkscape:original-d") in self.attrib:
            self.set("inkscape:original-d", str(Path(path)))
        else:
            self.path = path


class PathElement(PathElementBase):
    """Provide a useful extension for path elements"""

    tag_name = "path"

    @staticmethod
    def _arcpath(
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        start: float,
        end: float,
        arctype: str,
    ) -> Optional[Path]:
        """Compute the path for an arc defined by Inkscape-specific attributes.

        For details on arguments, see :func:`arc`.

        .. versionadded:: 1.2"""
        if abs(rx) < 1e-8 or abs(ry) < 1e-8:
            return None
        incr = end - start
        if incr < 0:
            incr += 2 * pi
        numsegs = min(1 + int(incr * 2.0 / pi), 4)
        incr = incr / numsegs

        computed = Path()
        computed.append(Move(cos(start), sin(start)))
        for seg in range(1, numsegs + 1):
            computed.append(
                Arc(1, 1, 0, 0, 1, cos(start + seg * incr), sin(start + seg * incr))
            )
        if abs(incr * numsegs - 2 * pi) > 1e-8 and (
            arctype in ("slice", "")
        ):  # slice is default
            computed.append(PathLine(0, 0))
        if arctype != "arc":
            computed.append(ZoneClose())
        computed.transform(
            Transform().add_translate(cx, cy).add_scale(rx, ry), inplace=True
        )
        return computed.to_relative()

    @classmethod
    def arc(
        cls, center, rx, ry=None, arctype="", pathonly=False, **kw
    ):  # pylint: disable=invalid-name
        """Generates a sodipodi elliptical arc (special type). Also computes the path
        that Inkscape uses under the hood.
        All data may be given as parseable strings or using numeric data types.

        Args:
            center (tuple-like): Coordinates of the star/polygon center as tuple or
                Vector2d
            rx (Union[float, str]): Radius in x direction
            ry (Union[float, str], optional): Radius in y direction. If not given,
                ry=rx. Defaults to None.
            arctype (str, optional): "arc", "chord" or "slice". Defaults to "", i.e.
                "slice".

                .. versionadded:: 1.2
                    Previously set to "arc" as fixed value
            pathonly (bool, optional): Whether to create the path without
                Inkscape-specific attributes. Defaults to False.

                .. versionadded:: 1.2
        Keyword args:
            start (Union[float, str]): start angle in radians
            end (Union[float, str]): end angle in radians
            open (str): whether the path should be open (true/false). Not used in
                Inkscape > 1.1

        Returns:
            PathElement : the created star/polygon
        """
        others = [(name, kw.pop(name, None)) for name in ("start", "end", "open")]
        elem = cls(**kw)
        elem.set("sodipodi:cx", center[0])
        elem.set("sodipodi:cy", center[1])
        elem.set("sodipodi:rx", rx)
        elem.set("sodipodi:ry", ry or rx)
        elem.set("sodipodi:type", "arc")
        if arctype != "":
            elem.set("sodipodi:arc-type", arctype)
        for name, value in others:
            if value is not None:
                elem.set("sodipodi:" + name, str(value).lower())

        path = cls._arcpath(
            float(center[0]),
            float(center[1]),
            float(rx),
            float(ry or rx),
            float(elem.get("sodipodi:start", 0)),
            float(elem.get("sodipodi:end", 2 * pi)),
            arctype,
        )
        if pathonly:
            elem = cls(**kw)
        if path is not None:
            elem.path = path
        return elem

    @staticmethod
    def _starpath(
        c: Tuple[float, float],
        sides: int,
        r: Tuple[float, float],  # pylint: disable=invalid-name
        arg: Tuple[float, float],
        rounded: float,
        flatsided: bool,
    ):
        """Helper method to generate the path for an Inkscape star/ polygon; randomized
        is ignored.

        For details on arguments, see :func:`star`.

        .. versionadded:: 1.2"""

        def _star_get_xy(point, index):
            cur_arg = arg[point] + 2 * pi / sides * (index % sides)
            return Vector2d(*c) + r[point] * Vector2d(cos(cur_arg), sin(cur_arg))

        def _rot90_rel(origin, other):
            """Returns a unit length vector at 90 deg from origin to other"""
            return (
                1
                / pointdistance(other, origin)
                * Vector2d(other.y - origin.y, other.x - origin.x)
            )

        def _star_get_curvepoint(point, index, is_prev: bool):
            index = index % sides
            orig = _star_get_xy(point, index)
            previ = (index - 1 + sides) % sides
            nexti = (index + 1) % sides
            # neighbors of the current point depend on polygon or star
            prev = (
                _star_get_xy(point, previ)
                if flatsided
                else _star_get_xy(1 - point, index if point == 1 else previ)
            )
            nextp = (
                _star_get_xy(point, nexti)
                if flatsided
                else _star_get_xy(1 - point, index if point == 0 else nexti)
            )
            mid = 0.5 * (prev + nextp)
            # direction of bezier handles
            rot = _rot90_rel(orig, mid + 100000 * _rot90_rel(mid, nextp))
            ret = (
                rounded
                * rot
                * (
                    -1 * pointdistance(prev, orig)
                    if is_prev
                    else pointdistance(nextp, orig)
                )
            )
            return orig + ret

        pointy = abs(rounded) < 1e-4
        result = Path()
        result.append(Move(*_star_get_xy(0, 0)))
        for i in range(0, sides):
            # draw to point type 1 for stars
            if not flatsided:
                if pointy:
                    result.append(PathLine(*_star_get_xy(1, i)))
                else:
                    result.append(
                        Curve(
                            *_star_get_curvepoint(0, i, False),
                            *_star_get_curvepoint(1, i, True),
                            *_star_get_xy(1, i),
                        )
                    )
            # draw to point type 0 for both stars and rectangles
            if pointy and i < sides - 1:
                result.append(PathLine(*_star_get_xy(0, i + 1)))
            if not pointy:
                if not flatsided:
                    result.append(
                        Curve(
                            *_star_get_curvepoint(1, i, False),
                            *_star_get_curvepoint(0, i + 1, True),
                            *_star_get_xy(0, i + 1),
                        )
                    )
                else:
                    result.append(
                        Curve(
                            *_star_get_curvepoint(0, i, False),
                            *_star_get_curvepoint(0, i + 1, True),
                            *_star_get_xy(0, i + 1),
                        )
                    )

        result.append(ZoneClose())
        return result.to_relative()

    @classmethod
    def star(
        cls,
        center,
        radii,
        sides=5,
        rounded=0,
        args=(0, 0),
        flatsided=False,
        pathonly=False,
    ):
        """Generate a sodipodi star / polygon. Also computes the path that Inkscape uses
        under the hood. The arguments for center, radii, sides, rounded and args can be
        given as strings or as numeric data.

        .. versionadded:: 1.1

        Args:
            center (Tuple-like): Coordinates of the star/polygon center as tuple or
                Vector2d
            radii (tuple): Radii of the control points, i.e. their distances from the
                center. The control points are specified in polar coordinates. Only the
                first control point is used for polygons.
            sides (int, optional): Number of sides / tips of the polygon / star.
                Defaults to 5.
            rounded (int, optional): Controls the rounding radius of the polygon / star.
                For `rounded=0`, only straight lines are used. Defaults to 0.
            args (tuple, optional): Angle between horizontal axis and control points.
                Defaults to (0,0).

                .. versionadded:: 1.2
                    Previously fixed to (0.85, 1.3)
            flatsided (bool, optional): True for polygons, False for stars.
                Defaults to False.

                .. versionadded:: 1.2
            pathonly (bool, optional): Whether to create the path without
                Inkscape-specific attributes. Defaults to False.

                .. versionadded:: 1.2

        Returns:
            PathElement : the created star/polygon
        """
        elem = cls()
        elem.set("sodipodi:cx", center[0])
        elem.set("sodipodi:cy", center[1])
        elem.set("sodipodi:r1", radii[0])
        elem.set("sodipodi:r2", radii[1])
        elem.set("sodipodi:arg1", args[0])
        elem.set("sodipodi:arg2", args[1])
        elem.set("sodipodi:sides", max(sides, 3) if flatsided else max(sides, 2))
        elem.set("inkscape:rounded", rounded)
        elem.set("inkscape:flatsided", str(flatsided).lower())
        elem.set("sodipodi:type", "star")

        path = cls._starpath(
            (float(center[0]), float(center[1])),
            int(sides),
            (float(radii[0]), float(radii[1])),
            (float(args[0]), float(args[1])),
            float(rounded),
            flatsided,
        )
        if pathonly:
            elem = cls()
        # inkex.errormsg(path)
        if path is not None:
            elem.path = path

        return elem


class Polyline(ShapeElement):
    """Like a path, but made up of straight line segments only"""

    tag_name = "polyline"

    def get_path(self):
        return Path("M" + self.get("points"))

    def set_path(self, path):
        points = [f"{x:g},{y:g}" for x, y in Path(path).end_points]
        self.set("points", " ".join(points))


class Polygon(ShapeElement):
    """A closed polyline"""

    tag_name = "polygon"
    get_path = lambda self: Path("M" + self.get("points") + " Z")


class Line(ShapeElement):
    """A line segment connecting two points"""

    tag_name = "line"
    x1 = property(lambda self: self.to_dimensionless(self.get("x1", 0)))
    y1 = property(lambda self: self.to_dimensionless(self.get("y1", 0)))
    x2 = property(lambda self: self.to_dimensionless(self.get("x2", 0)))
    y2 = property(lambda self: self.to_dimensionless(self.get("y2", 0)))
    get_path = lambda self: Path(f"M{self.x1},{self.y1} L{self.x2},{self.y2}")

    @classmethod
    def new(cls, start, end, **attrs):
        start = Vector2d(start)
        end = Vector2d(end)
        return super().new(x1=start.x, y1=start.y, x2=end.x, y2=end.y, **attrs)


class RectangleBase(ShapeElement):
    """Provide a useful extension for rectangle elements"""

    left = property(lambda self: self.to_dimensionless(self.get("x", "0")))
    top = property(lambda self: self.to_dimensionless(self.get("y", "0")))
    right = property(lambda self: self.left + self.width)
    bottom = property(lambda self: self.top + self.height)
    width = property(lambda self: self.to_dimensionless(self.get("width", "0")))
    height = property(lambda self: self.to_dimensionless(self.get("height", "0")))
    rx = property(
        lambda self: self.to_dimensionless(self.get("rx", self.get("ry", 0.0)))
    )
    ry = property(
        lambda self: self.to_dimensionless(self.get("ry", self.get("rx", 0.0)))
    )  # pylint: disable=invalid-name

    def get_path(self):
        """Calculate the path as the box around the rect"""
        if self.rx or self.ry:
            # pylint: disable=invalid-name
            rx = min(self.rx if self.rx > 0 else self.ry, self.width / 2)
            ry = min(self.ry if self.ry > 0 else self.rx, self.height / 2)
            cpts = [self.left + rx, self.right - rx, self.top + ry, self.bottom - ry]
            return (
                f"M {cpts[0]},{self.top}"
                f"L {cpts[1]},{self.top}    "
                f"A {rx},{ry} 0 0 1 {self.right},{cpts[2]}"
                f"L {self.right},{cpts[3]}  "
                f"A {rx},{ry} 0 0 1 {cpts[1]},{self.bottom}"
                f"L {cpts[0]},{self.bottom} "
                f"A {rx},{ry} 0 0 1 {self.left},{cpts[3]}"
                f"L {self.left},{cpts[2]}   "
                f"A {rx},{ry} 0 0 1 {cpts[0]},{self.top} z"
            )

        return f"M {self.left},{self.top} h{self.width}v{self.height}h{-self.width} z"


class Rectangle(RectangleBase):
    """Provide a useful extension for rectangle elements"""

    tag_name = "rect"

    @classmethod
    def new(cls, left, top, width, height, **attrs):
        return super().new(x=left, y=top, width=width, height=height, **attrs)


class EllipseBase(ShapeElement):
    """Absorbs common part of Circle and Ellipse classes"""

    def get_path(self):
        """Calculate the arc path of this circle"""
        rx, ry = self.rxry()
        cx, y = self.center.x, self.center.y - ry
        return (
            "M {cx},{y} "
            "a {rx},{ry} 0 1 0 {rx}, {ry} "
            "a {rx},{ry} 0 0 0 -{rx}, -{ry} z"
        ).format(cx=cx, y=y, rx=rx, ry=ry)

    @property
    def center(self):
        """Return center of circle/ellipse"""
        return ImmutableVector2d(
            self.to_dimensionless(self.get("cx", "0")),
            self.to_dimensionless(self.get("cy", "0")),
        )

    @center.setter
    def center(self, value):
        value = Vector2d(value)
        self.set("cx", value.x)
        self.set("cy", value.y)

    def rxry(self):
        # type: () -> Vector2d
        """Helper function"""
        raise NotImplementedError()

    @classmethod
    def new(cls, center, radius, **attrs):
        circle = super().new(**attrs)
        circle.center = center
        circle.radius = radius
        return circle


class Circle(EllipseBase):
    """Provide a useful extension for circle elements"""

    tag_name = "circle"

    @property
    def radius(self) -> float:
        """Return radius of circle"""
        return self.to_dimensionless(self.get("r", "0"))

    @radius.setter
    def radius(self, value):
        self.set("r", self.to_dimensionless(value))

    def rxry(self):
        r = self.radius
        return Vector2d(r, r)


class Ellipse(EllipseBase):
    """Provide a similar extension to the Circle interface for ellipses"""

    tag_name = "ellipse"

    @property
    def radius(self) -> ImmutableVector2d:
        """Return radii of ellipse"""
        return ImmutableVector2d(
            self.to_dimensionless(self.get("rx", "0")),
            self.to_dimensionless(self.get("ry", "0")),
        )

    @radius.setter
    def radius(self, value):
        value = Vector2d(value)
        self.set("rx", str(value.x))
        self.set("ry", str(value.y))

    def rxry(self):
        return self.radius
