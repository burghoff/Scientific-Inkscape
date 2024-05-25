# coding=utf-8
#
# Copyright (C) 2018 Martin Owens <doctormo@gmail.com>
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
functions for digesting paths
"""
from __future__ import annotations

import re
import copy
import abc

from math import atan2, cos, pi, sin, sqrt, acos, tan
from typing import (
    Any,
    Type,
    Dict,
    Optional,
    Union,
    Tuple,
    List,
    Generator,
    TypeVar,
)
from .transforms import (
    Transform,
    BoundingBox,
    Vector2d,
    cubic_extrema,
    quadratic_extrema,
)
from .utils import classproperty, strargs


Pathlike = TypeVar("Pathlike", bound="PathCommand")
AbsolutePathlike = TypeVar("AbsolutePathlike", bound="AbsolutePathCommand")

# All the names that get added to the inkex API itself.
__all__ = (
    "Path",
    "CubicSuperPath",
    "PathCommand",
    "AbsolutePathCommand",
    "RelativePathCommand",
    # Path commands:
    "Line",
    "line",
    "Move",
    "move",
    "ZoneClose",
    "zoneClose",
    "Horz",
    "horz",
    "Vert",
    "vert",
    "Curve",
    "curve",
    "Smooth",
    "smooth",
    "Quadratic",
    "quadratic",
    "TepidQuadratic",
    "tepidQuadratic",
    "Arc",
    "arc",
    # errors
    "InvalidPath",
)

LEX_REX = re.compile(r"([MLHVCSQTAZmlhvcsqtaz])([^MLHVCSQTAZmlhvcsqtaz]*)")
NONE = lambda obj: obj is not None


class InvalidPath(ValueError):
    """Raised when given an invalid path string"""


class PathCommand(abc.ABC):
    """
    Base class of all path commands
    """

    # Number of arguments that follow this path commands letter
    nargs = -1

    @classproperty  # From python 3.9 on, just combine @classmethod and @property
    def name(cls):  # pylint: disable=no-self-argument
        """The full name of the segment (i.e. Line, Arc, etc)"""
        return cls.__name__  # pylint: disable=no-member

    @classproperty
    def letter(cls):  # pylint: disable=no-self-argument
        """The single letter representation of this command (i.e. L, A, etc)"""
        return cls.name[0]

    @classproperty
    def next_command(self):
        """The implicit next command. This is for automatic chains where the next
        command isn't given, just a bunch on numbers which we automatically parse."""
        return self

    @property
    def is_relative(self):  # type: () -> bool
        """Whether the command is defined in relative coordinates, i.e. relative to
        the previous endpoint (lower case path command letter)"""
        raise NotImplementedError

    @property
    def is_absolute(self):  # type: () -> bool
        """Whether the command is defined in absolute coordinates (upper case path
        command letter)"""
        raise NotImplementedError

    def to_relative(self, prev):  # type: (Vector2d) -> RelativePathCommand
        """Return absolute counterpart for absolute commands or copy for relative"""
        raise NotImplementedError

    def to_absolute(self, prev):  # type: (Vector2d) -> AbsolutePathCommand
        """Return relative counterpart for relative commands or copy for absolute"""
        raise NotImplementedError

    def reverse(self, first, prev):
        """Reverse path command

        .. versionadded:: 1.1"""

    def to_non_shorthand(self, prev, prev_control):  # pylint: disable=unused-argument
        # type: (Vector2d, Vector2d) -> AbsolutePathCommand
        """Return an absolute non-shorthand command

        .. versionadded:: 1.1"""
        return self.to_absolute(prev)

    # The precision of the numbers when converting to string
    number_template = "{:.6g}"

    # Maps single letter path command to corresponding class
    # (filled at the bottom of file, when all classes already defined)
    _letter_to_class = {}  # type: Dict[str, Type[Any]]

    @staticmethod
    def letter_to_class(letter):
        """Returns class for given path command letter"""
        return PathCommand._letter_to_class[letter]

    @property
    def args(self):  # type: () -> List[float]
        """Returns path command arguments as tuple of floats"""
        raise NotImplementedError()

    def control_points(
        self, first: Vector2d, prev: Vector2d, prev_prev: Vector2d
    ) -> Union[List[Vector2d], Generator[Vector2d, None, None]]:
        """Returns list of path command control points"""
        raise NotImplementedError

    @classmethod
    def _argt(cls, sep):
        return sep.join([cls.number_template] * cls.nargs)

    def __str__(self):
        return f"{self.letter} {self._argt(' ').format(*self.args)}".strip()

    def __repr__(self):
        # pylint: disable=consider-using-f-string
        return "{{}}({})".format(self._argt(", ")).format(self.name, *self.args)

    def __eq__(self, other):
        previous = Vector2d()
        if type(self) == type(other):  # pylint: disable=unidiomatic-typecheck
            return self.args == other.args
        if isinstance(other, tuple):
            return self.args == other
        if not isinstance(other, PathCommand):
            raise ValueError("Can't compare types")
        try:
            if self.is_relative == other.is_relative:
                return self.to_curve(previous) == other.to_curve(previous)
        except ValueError:
            pass
        return False

    def end_point(self, first, prev):  # type: (Vector2d, Vector2d) -> Vector2d
        """Returns last control point of path command"""
        raise NotImplementedError()

    def update_bounding_box(
        self, first: Vector2d, last_two_points: List[Vector2d], bbox: BoundingBox
    ):
        # pylint: disable=unused-argument
        """Enlarges given bbox to contain path element.

        Args:
            first (Vector2d): first point of path. Required to calculate Z segment
            last_two_points (List[Vector2d]): list with last two control points in abs
                coords.
            bbox (BoundingBox): bounding box to update
        """

        raise NotImplementedError(f"Bounding box is not implemented for {self.name}")

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Vector2d) -> Curve
        """Convert command to :py:class:`Curve`

        Curve().to_curve() returns a copy
        """
        raise NotImplementedError(f"To curve not supported for {self.name}")

    def to_curves(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Vector2d) -> List[Curve]
        """Convert command to list of :py:class:`Curve` commands"""
        return [self.to_curve(prev, prev_prev)]

    def to_line(self, prev):
        # type: (Vector2d) -> Line
        """Converts this segment to a line (copies if already a line)"""
        return Line(*self.end_point(Vector2d(), prev))


class RelativePathCommand(PathCommand):
    """
    Abstract base class for relative path commands.

    Implements most of methods of :py:class:`PathCommand` through
    conversion to :py:class:`AbsolutePathCommand`
    """

    @property
    def is_relative(self):
        return True

    @property
    def is_absolute(self):
        return False

    def control_points(
        self, first: Vector2d, prev: Vector2d, prev_prev: Vector2d
    ) -> Union[List[Vector2d], Generator[Vector2d, None, None]]:
        return self.to_absolute(prev).control_points(first, prev, prev_prev)

    def to_relative(self, prev):
        # type: (Pathlike, Vector2d) -> Pathlike
        return self.__class__(*self.args)

    def update_bounding_box(self, first, last_two_points, bbox):
        self.to_absolute(last_two_points[-1]).update_bounding_box(
            first, last_two_points, bbox
        )

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return self.to_absolute(prev).end_point(first, prev)

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Vector2d) -> Curve
        return self.to_absolute(prev).to_curve(prev, prev_prev)

    def to_curves(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Vector2d) -> List[Curve]
        return self.to_absolute(prev).to_curves(prev, prev_prev)


class AbsolutePathCommand(PathCommand):
    """Absolute path command. Unlike :py:class:`RelativePathCommand` can be transformed
    directly."""

    @property
    def is_relative(self):
        return False

    @property
    def is_absolute(self):
        return True

    def to_absolute(
        self, prev
    ):  # type: (AbsolutePathlike, Vector2d) -> AbsolutePathlike
        return self.__class__(*self.args)

    def transform(
        self, transform
    ):  # type: (AbsolutePathlike, Transform) -> AbsolutePathlike
        """Returns new transformed segment

        :param transform: a transformation to apply
        """
        raise NotImplementedError()

    def rotate(
        self, degrees, center
    ):  # type: (AbsolutePathlike, float, Vector2d) -> AbsolutePathlike
        """
        Returns new transformed segment

        :param degrees: rotation angle in degrees
        :param center: invariant point of rotation
        """
        return self.transform(Transform(rotate=(degrees, center[0], center[1])))

    def translate(self, dr):  # type: (AbsolutePathlike, Vector2d) -> AbsolutePathlike
        """Translate or scale this path command by dr"""
        return self.transform(Transform(translate=dr))

    def scale(
        self, factor
    ):  # type: (AbsolutePathlike, Union[float, Tuple[float,float]]) -> AbsolutePathlike
        """Returns new transformed segment

        :param factor: scale or (scale_x, scale_y)
        """
        return self.transform(Transform(scale=factor))


class Line(AbsolutePathCommand):
    """Line segment"""

    nargs = 2

    @property
    def args(self):
        return self.x, self.y

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def update_bounding_box(self, first, last_two_points, bbox):
        bbox += BoundingBox(
            (last_two_points[-1].x, self.x), (last_two_points[-1].y, self.y)
        )

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]
        yield Vector2d(self.x, self.y)

    def to_relative(self, prev):
        # type: (Vector2d) -> line
        return line(self.x - prev.x, self.y - prev.y)

    def transform(self, transform):
        # type: (Line, Transform) -> Line
        return Line(*transform.apply_to_point((self.x, self.y)))

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return Vector2d(self.x, self.y)

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Optional[Vector2d]) -> Curve
        return Curve(prev.x, prev.y, self.x, self.y, self.x, self.y)

    def reverse(self, first, prev):
        return Line(prev.x, prev.y)


class line(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative line segment"""

    nargs = 2

    @property
    def args(self):
        return self.dx, self.dy

    def __init__(self, dx, dy):
        self.dx = dx
        self.dy = dy

    def to_absolute(self, prev):  # type: (Vector2d) -> Line
        return Line(prev.x + self.dx, prev.y + self.dy)

    def reverse(self, first, prev):
        return line(-self.dx, -self.dy)


class Move(AbsolutePathCommand):
    """Move pen segment without a line"""

    nargs = 2
    next_command = Line

    @property
    def args(self):
        return self.x, self.y

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def update_bounding_box(self, first, last_two_points, bbox):
        bbox += BoundingBox(self.x, self.y)

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]
        yield Vector2d(self.x, self.y)

    def to_relative(self, prev):
        # type: (Vector2d) -> move
        return move(self.x - prev.x, self.y - prev.y)

    def transform(self, transform):
        # type: (Transform) -> Move
        return Move(*transform.apply_to_point((self.x, self.y)))

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return Vector2d(self.x, self.y)

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Optional[Vector2d]) -> Curve
        raise ValueError("Move segments can not be changed into curves.")

    def reverse(self, first, prev):
        return Move(prev.x, prev.y)


class move(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative move segment"""

    nargs = 2
    next_command = line

    @property
    def args(self):
        return self.dx, self.dy

    def __init__(self, dx, dy):
        self.dx = dx
        self.dy = dy

    def to_absolute(self, prev):  # type: (Vector2d) -> Move
        return Move(prev.x + self.dx, prev.y + self.dy)

    def reverse(self, first, prev):
        return move(prev.x - first.x, prev.y - first.y)


class ZoneClose(AbsolutePathCommand):
    """Close segment to finish a path"""

    nargs = 0
    next_command = Move

    @property
    def args(self):
        return ()

    def update_bounding_box(self, first, last_two_points, bbox):
        pass

    def transform(self, transform):
        # type: (Transform) -> ZoneClose
        return ZoneClose()

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]
        yield first

    def to_relative(self, prev):
        # type: (Vector2d) -> zoneClose
        return zoneClose()

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return first

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Optional[Vector2d]) -> Curve
        raise ValueError("ZoneClose segments can not be changed into curves.")

    def reverse(self, first, prev):
        return Line(prev.x, prev.y)


class zoneClose(RelativePathCommand):  # pylint: disable=invalid-name
    """Same as above (svg says no difference)"""

    nargs = 0
    next_command = Move

    @property
    def args(self):
        return ()

    def to_absolute(self, prev):
        return ZoneClose()

    def reverse(self, first, prev):
        return line(prev.x - first.x, prev.y - first.y)


class Horz(AbsolutePathCommand):
    """Horizontal Line segment"""

    nargs = 1

    @property
    def args(self):
        return (self.x,)

    def __init__(self, x):
        self.x = x

    def update_bounding_box(self, first, last_two_points, bbox):
        bbox += BoundingBox((last_two_points[-1].x, self.x), last_two_points[-1].y)

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]
        yield Vector2d(self.x, prev.y)

    def to_relative(self, prev):
        # type: (Vector2d) -> horz
        return horz(self.x - prev.x)

    def to_non_shorthand(self, prev, prev_control):
        # type: (Vector2d, Vector2d) -> Line
        return self.to_line(prev)

    def transform(self, transform):
        # type: (Pathlike, Transform) -> Pathlike
        raise ValueError("Horizontal lines can't be transformed directly.")

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return Vector2d(self.x, prev.y)

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Optional[Vector2d]) -> Curve
        """Convert a horizontal line into a curve"""
        return self.to_line(prev).to_curve(prev)

    def to_line(self, prev):
        # type: (Vector2d) -> Line
        """Return this path command as a Line instead"""
        return Line(self.x, prev.y)

    def reverse(self, first, prev):
        return Horz(prev.x)


class horz(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative horz line segment"""

    nargs = 1

    @property
    def args(self):
        return (self.dx,)

    def __init__(self, dx):
        self.dx = dx

    def to_absolute(self, prev):  # type: (Vector2d) -> Horz
        return Horz(prev.x + self.dx)

    def to_non_shorthand(self, prev, prev_control):
        # type: (Vector2d, Vector2d) -> Line
        return self.to_line(prev)

    def to_line(self, prev):  # type: (Vector2d) -> Line
        """Return this path command as a Line instead"""
        return Line(prev.x + self.dx, prev.y)

    def reverse(self, first, prev):
        return horz(-self.dx)


class Vert(AbsolutePathCommand):
    """Vertical Line segment"""

    nargs = 1

    @property
    def args(self):
        return (self.y,)

    def __init__(self, y):
        self.y = y

    def update_bounding_box(self, first, last_two_points, bbox):
        bbox += BoundingBox(last_two_points[-1].x, (last_two_points[-1].y, self.y))

    def transform(self, transform):  # type: (Pathlike, Transform) -> Pathlike
        raise ValueError("Vertical lines can't be transformed directly.")

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]
        yield Vector2d(prev.x, self.y)

    def to_non_shorthand(self, prev, prev_control):
        # type: (Vector2d, Vector2d) -> Line
        return self.to_line(prev)

    def to_relative(self, prev):
        # type: (Vector2d) -> vert
        return vert(self.y - prev.y)

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return Vector2d(prev.x, self.y)

    def to_line(self, prev):
        # type: (Vector2d) -> Line
        """Return this path command as a line instead"""
        return Line(prev.x, self.y)

    def to_curve(
        self, prev, prev_prev=Vector2d()
    ):  # type: (Vector2d, Optional[Vector2d]) -> Curve
        """Convert a horizontal line into a curve"""
        return self.to_line(prev).to_curve(prev)

    def reverse(self, first, prev):
        return Vert(prev.y)


class vert(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative vertical line segment"""

    nargs = 1

    @property
    def args(self):
        return (self.dy,)

    def __init__(self, dy):
        self.dy = dy

    def to_absolute(self, prev):  # type: (Vector2d) -> Vert
        return Vert(prev.y + self.dy)

    def to_non_shorthand(self, prev, prev_control):
        # type: (Vector2d, Vector2d) -> Line
        return self.to_line(prev)

    def to_line(self, prev):  # type: (Vector2d) -> Line
        """Return this path command as a line instead"""
        return Line(prev.x, prev.y + self.dy)

    def reverse(self, first, prev):
        return vert(-self.dy)


class Curve(AbsolutePathCommand):
    """Absolute Curved Line segment"""

    nargs = 6

    @property
    def args(self):
        return self.x2, self.y2, self.x3, self.y3, self.x4, self.y4

    def __init__(self, x2, y2, x3, y3, x4, y4):  # pylint: disable=too-many-arguments
        self.x2 = x2
        self.y2 = y2

        self.x3 = x3
        self.y3 = y3

        self.x4 = x4
        self.y4 = y4

    def update_bounding_box(self, first, last_two_points, bbox):
        x1, x2, x3, x4 = last_two_points[-1].x, self.x2, self.x3, self.x4
        y1, y2, y3, y4 = last_two_points[-1].y, self.y2, self.y3, self.y4

        if not (x1 in bbox.x and x2 in bbox.x and x3 in bbox.x and x4 in bbox.x):
            bbox.x += cubic_extrema(x1, x2, x3, x4)

        if not (y1 in bbox.y and y2 in bbox.y and y3 in bbox.y and y4 in bbox.y):
            bbox.y += cubic_extrema(y1, y2, y3, y4)

    def transform(self, transform):
        # type: (Transform) -> Curve
        x2, y2 = transform.apply_to_point((self.x2, self.y2))
        x3, y3 = transform.apply_to_point((self.x3, self.y3))
        x4, y4 = transform.apply_to_point((self.x4, self.y4))
        return Curve(x2, y2, x3, y3, x4, y4)

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]
        yield Vector2d(self.x2, self.y2)
        yield Vector2d(self.x3, self.y3)
        yield Vector2d(self.x4, self.y4)

    def to_relative(self, prev):  # type: (Vector2d) -> curve
        return curve(
            self.x2 - prev.x,
            self.y2 - prev.y,
            self.x3 - prev.x,
            self.y3 - prev.y,
            self.x4 - prev.x,
            self.y4 - prev.y,
        )

    def end_point(self, first, prev):
        return Vector2d(self.x4, self.y4)

    def to_curve(
        self, prev, prev_prev=Vector2d()
    ):  # type: (Vector2d, Optional[Vector2d]) -> Curve
        """No conversion needed, pass-through, returns self"""
        return Curve(*self.args)

    def to_bez(self):
        """Returns the list of coords for SuperPath"""
        return [list(self.args[:2]), list(self.args[2:4]), list(self.args[4:6])]

    def reverse(self, first, prev):
        return Curve(self.x3, self.y3, self.x2, self.y2, prev.x, prev.y)


class curve(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative curved line segment"""

    nargs = 6

    @property
    def args(self):
        return self.dx2, self.dy2, self.dx3, self.dy3, self.dx4, self.dy4

    def __init__(
        self, dx2, dy2, dx3, dy3, dx4, dy4
    ):  # pylint: disable=too-many-arguments
        self.dx2 = dx2
        self.dy2 = dy2

        self.dx3 = dx3
        self.dy3 = dy3

        self.dx4 = dx4
        self.dy4 = dy4

    def to_absolute(self, prev):  # type: (Vector2d) -> Curve
        return Curve(
            self.dx2 + prev.x,
            self.dy2 + prev.y,
            self.dx3 + prev.x,
            self.dy3 + prev.y,
            self.dx4 + prev.x,
            self.dy4 + prev.y,
        )

    def reverse(self, first, prev):
        return curve(
            -self.dx4 + self.dx3,
            -self.dy4 + self.dy3,
            -self.dx4 + self.dx2,
            -self.dy4 + self.dy2,
            -self.dx4,
            -self.dy4,
        )


class Smooth(AbsolutePathCommand):
    """Absolute Smoothed Curved Line segment"""

    nargs = 4

    @property
    def args(self):
        return self.x3, self.y3, self.x4, self.y4

    def __init__(self, x3, y3, x4, y4):
        self.x3 = x3
        self.y3 = y3

        self.x4 = x4
        self.y4 = y4

    def update_bounding_box(self, first, last_two_points, bbox):
        self.to_curve(last_two_points[-1], last_two_points[-2]).update_bounding_box(
            first, last_two_points, bbox
        )

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]

        x1, x2, x3, x4 = prev_prev.x, prev.x, self.x3, self.x4
        y1, y2, y3, y4 = prev_prev.y, prev.y, self.y3, self.y4

        # infer reflected point
        x2 = 2 * x2 - x1
        y2 = 2 * y2 - y1

        yield Vector2d(x2, y2)
        yield Vector2d(x3, y3)
        yield Vector2d(x4, y4)

    def to_non_shorthand(self, prev, prev_control):
        # type: (Vector2d, Vector2d) -> Curve
        return self.to_curve(prev, prev_control)

    def to_relative(self, prev):  # type: (Vector2d) -> smooth
        return smooth(
            self.x3 - prev.x, self.y3 - prev.y, self.x4 - prev.x, self.y4 - prev.y
        )

    def transform(self, transform):
        # type: (Transform) -> Smooth
        x3, y3 = transform.apply_to_point((self.x3, self.y3))
        x4, y4 = transform.apply_to_point((self.x4, self.y4))
        return Smooth(x3, y3, x4, y4)

    def end_point(self, first, prev):
        return Vector2d(self.x4, self.y4)

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Vector2d) -> Curve
        """
        Convert this Smooth curve to a regular curve by creating a mirror
        set of nodes based on the previous node. Previous should be a curve.
        """
        (x2, y2), (x3, y3), (x4, y4) = self.control_points(prev, prev, prev_prev)
        return Curve(x2, y2, x3, y3, x4, y4)

    def reverse(self, first, prev):
        return Smooth(self.x3, self.y3, prev.x, prev.y)


class smooth(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative smoothed curved line segment"""

    nargs = 4

    @property
    def args(self):
        return self.dx3, self.dy3, self.dx4, self.dy4

    def __init__(self, dx3, dy3, dx4, dy4):
        self.dx3 = dx3
        self.dy3 = dy3

        self.dx4 = dx4
        self.dy4 = dy4

    def to_absolute(self, prev):  # type: (Vector2d) -> Smooth
        return Smooth(
            self.dx3 + prev.x, self.dy3 + prev.y, self.dx4 + prev.x, self.dy4 + prev.y
        )

    def to_non_shorthand(self, prev, prev_control):
        # type: (Vector2d, Vector2d) -> Curve
        return self.to_absolute(prev).to_non_shorthand(prev, prev_control)

    def reverse(self, first, prev):
        return smooth(-self.dx4 + self.dx3, -self.dy4 + self.dy3, -self.dx4, -self.dy4)


class Quadratic(AbsolutePathCommand):
    """Absolute Quadratic Curved Line segment"""

    nargs = 4

    @property
    def args(self):
        return self.x2, self.y2, self.x3, self.y3

    def __init__(self, x2, y2, x3, y3):
        self.x2 = x2
        self.y2 = y2

        self.x3 = x3
        self.y3 = y3

    def update_bounding_box(self, first, last_two_points, bbox):
        x1, x2, x3 = last_two_points[-1].x, self.x2, self.x3
        y1, y2, y3 = last_two_points[-1].y, self.y2, self.y3

        if not (x1 in bbox.x and x2 in bbox.x and x3 in bbox.x):
            bbox.x += quadratic_extrema(x1, x2, x3)

        if not (y1 in bbox.y and y2 in bbox.y and y3 in bbox.y):
            bbox.y += quadratic_extrema(y1, y2, y3)

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]
        yield Vector2d(self.x2, self.y2)
        yield Vector2d(self.x3, self.y3)

    def to_relative(self, prev):
        # type: (Vector2d) -> quadratic
        return quadratic(
            self.x2 - prev.x, self.y2 - prev.y, self.x3 - prev.x, self.y3 - prev.y
        )

    def transform(self, transform):
        # type: (Transform) -> Quadratic
        x2, y2 = transform.apply_to_point((self.x2, self.y2))
        x3, y3 = transform.apply_to_point((self.x3, self.y3))
        return Quadratic(x2, y2, x3, y3)

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return Vector2d(self.x3, self.y3)

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Vector2d) -> Curve
        """Attempt to convert a quadratic to a curve"""
        prev = Vector2d(prev)
        x1 = 1.0 / 3 * prev.x + 2.0 / 3 * self.x2
        x2 = 2.0 / 3 * self.x2 + 1.0 / 3 * self.x3
        y1 = 1.0 / 3 * prev.y + 2.0 / 3 * self.y2
        y2 = 2.0 / 3 * self.y2 + 1.0 / 3 * self.y3
        return Curve(x1, y1, x2, y2, self.x3, self.y3)

    def reverse(self, first, prev):
        return Quadratic(self.x2, self.y2, prev.x, prev.y)


class quadratic(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative quadratic line segment"""

    nargs = 4

    @property
    def args(self):
        return self.dx2, self.dy2, self.dx3, self.dy3

    def __init__(self, dx2, dy2, dx3, dy3):
        self.dx2 = dx2
        self.dx3 = dx3
        self.dy2 = dy2
        self.dy3 = dy3

    def to_absolute(self, prev):  # type: (Vector2d) -> Quadratic
        return Quadratic(
            self.dx2 + prev.x, self.dy2 + prev.y, self.dx3 + prev.x, self.dy3 + prev.y
        )

    def reverse(self, first, prev):
        return quadratic(
            -self.dx3 + self.dx2, -self.dy3 + self.dy2, -self.dx3, -self.dy3
        )


class TepidQuadratic(AbsolutePathCommand):
    """Continued Quadratic Line segment"""

    nargs = 2

    @property
    def args(self):
        return self.x3, self.y3

    def __init__(self, x3, y3):
        self.x3 = x3
        self.y3 = y3

    def update_bounding_box(self, first, last_two_points, bbox):
        self.to_quadratic(last_two_points[-1], last_two_points[-2]).update_bounding_box(
            first, last_two_points, bbox
        )

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]

        x1, x2, x3 = prev_prev.x, prev.x, self.x3
        y1, y2, y3 = prev_prev.y, prev.y, self.y3

        # infer reflected point
        x2 = 2 * x2 - x1
        y2 = 2 * y2 - y1

        yield Vector2d(x2, y2)
        yield Vector2d(x3, y3)

    def to_non_shorthand(self, prev, prev_control):
        # type: (Vector2d, Vector2d) -> AbsolutePathCommand
        return self.to_quadratic(prev, prev_control)

    def to_relative(self, prev):  # type: (Vector2d) -> tepidQuadratic
        return tepidQuadratic(self.x3 - prev.x, self.y3 - prev.y)

    def transform(self, transform):
        # type: (Transform) -> TepidQuadratic
        x3, y3 = transform.apply_to_point((self.x3, self.y3))
        return TepidQuadratic(x3, y3)

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return Vector2d(self.x3, self.y3)

    def to_curve(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Vector2d) -> Curve
        return self.to_quadratic(prev, prev_prev).to_curve(prev)

    def to_quadratic(self, prev, prev_prev):
        # type: (Vector2d, Vector2d) -> Quadratic
        """
        Convert this continued quadratic into a full quadratic
        """
        (x2, y2), (x3, y3) = self.control_points(prev, prev, prev_prev)
        return Quadratic(x2, y2, x3, y3)

    def reverse(self, first, prev):
        return TepidQuadratic(prev.x, prev.y)


class tepidQuadratic(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative continued quadratic line segment"""

    nargs = 2

    @property
    def args(self):
        return self.dx3, self.dy3

    def __init__(self, dx3, dy3):
        self.dx3 = dx3
        self.dy3 = dy3

    def to_absolute(self, prev):
        # type: (Vector2d) -> TepidQuadratic
        return TepidQuadratic(self.dx3 + prev.x, self.dy3 + prev.y)

    def to_non_shorthand(self, prev, prev_control):
        # type: (Vector2d, Vector2d) -> AbsolutePathCommand
        return self.to_absolute(prev).to_non_shorthand(prev, prev_control)

    def reverse(self, first, prev):
        return tepidQuadratic(-self.dx3, -self.dy3)


class Arc(AbsolutePathCommand):
    """Special Arc segment"""

    nargs = 7

    @property
    def args(self):
        return (
            self.rx,
            self.ry,
            self.x_axis_rotation,
            self.large_arc,
            self.sweep,
            self.x,
            self.y,
        )

    def __init__(
        self, rx, ry, x_axis_rotation, large_arc, sweep, x, y
    ):  # pylint: disable=too-many-arguments
        self.rx = rx
        self.ry = ry
        self.x_axis_rotation = x_axis_rotation
        self.large_arc = large_arc
        self.sweep = sweep
        self.x = x
        self.y = y

    def update_bounding_box(self, first, last_two_points, bbox):
        prev = last_two_points[-1]
        for seg in self.to_curves(prev=prev):
            seg.update_bounding_box(first, [None, prev], bbox)
            prev = seg.end_point(first, prev)

    def control_points(self, first, prev, prev_prev):
        # type: (Vector2d, Vector2d, Vector2d) -> Generator[Vector2d, None, None]
        yield Vector2d(self.x, self.y)

    def to_curves(self, prev, prev_prev=Vector2d()):
        # type: (Vector2d, Vector2d) -> List[Curve]
        """Convert this arc into bezier curves"""
        path = CubicSuperPath([arc_to_path(list(prev), self.args)]).to_path(
            curves_only=True
        )
        # Ignore the first move command from to_path()
        return list(path)[1:]

    def transform(self, transform):
        # type: (Transform) -> Arc
        # pylint: disable=invalid-name, too-many-locals
        x_, y_ = transform.apply_to_point((self.x, self.y))

        T = transform  # type: Transform
        if self.x_axis_rotation != 0:
            T = T @ Transform(rotate=self.x_axis_rotation)
        a, c, b, d, _, _ = list(T.to_hexad())
        # T = | a b |
        #     | c d |

        detT = a * d - b * c
        detT2 = detT**2

        rx = float(self.rx)
        ry = float(self.ry)

        if rx == 0.0 or ry == 0.0 or detT2 == 0.0:
            # invalid Arc parameters
            # transform only last point
            return Arc(
                self.rx,
                self.ry,
                self.x_axis_rotation,
                self.large_arc,
                self.sweep,
                x_,
                y_,
            )

        A = (d**2 / rx**2 + c**2 / ry**2) / detT2
        B = -(d * b / rx**2 + c * a / ry**2) / detT2
        D = (b**2 / rx**2 + a**2 / ry**2) / detT2

        theta = atan2(-2 * B, D - A) / 2
        theta_deg = theta * 180.0 / pi
        DA = D - A
        l2 = 4 * B**2 + DA**2

        if l2 == 0:
            delta = 0.0
        else:
            delta = 0.5 * (-(DA**2) - 4 * B**2) / sqrt(l2)

        half = (A + D) / 2

        rx_ = 1.0 / sqrt(half + delta)
        ry_ = 1.0 / sqrt(half - delta)

        x_, y_ = transform.apply_to_point((self.x, self.y))

        if detT > 0:
            sweep = self.sweep
        else:
            sweep = 0 if self.sweep > 0 else 1

        return Arc(rx_, ry_, theta_deg, self.large_arc, sweep, x_, y_)

    def to_relative(self, prev):
        # type: (Vector2d) -> arc
        return arc(
            self.rx,
            self.ry,
            self.x_axis_rotation,
            self.large_arc,
            self.sweep,
            self.x - prev.x,
            self.y - prev.y,
        )

    def end_point(self, first, prev):
        # type: (Vector2d, Vector2d) -> Vector2d
        return Vector2d(self.x, self.y)

    def reverse(self, first, prev):
        return Arc(
            self.rx,
            self.ry,
            self.x_axis_rotation,
            self.large_arc,
            1 - self.sweep,
            prev.x,
            prev.y,
        )


class arc(RelativePathCommand):  # pylint: disable=invalid-name
    """Relative Arc line segment"""

    nargs = 7

    @property
    def args(self):
        return (
            self.rx,
            self.ry,
            self.x_axis_rotation,
            self.large_arc,
            self.sweep,
            self.dx,
            self.dy,
        )

    def __init__(
        self, rx, ry, x_axis_rotation, large_arc, sweep, dx, dy
    ):  # pylint: disable=too-many-arguments
        self.rx = rx
        self.ry = ry
        self.x_axis_rotation = x_axis_rotation
        self.large_arc = large_arc
        self.sweep = sweep
        self.dx = dx
        self.dy = dy

    def to_absolute(self, prev):  # type: (Vector2d) -> "Arc"
        x1, y1 = prev
        return Arc(
            self.rx,
            self.ry,
            self.x_axis_rotation,
            self.large_arc,
            self.sweep,
            self.dx + x1,
            self.dy + y1,
        )

    def reverse(self, first, prev):
        return arc(
            self.rx,
            self.ry,
            self.x_axis_rotation,
            self.large_arc,
            1 - self.sweep,
            -self.dx,
            -self.dy,
        )


PathCommand._letter_to_class = {  # pylint: disable=protected-access
    "M": Move,
    "L": Line,
    "V": Vert,
    "H": Horz,
    "A": Arc,
    "C": Curve,
    "S": Smooth,
    "Z": ZoneClose,
    "Q": Quadratic,
    "T": TepidQuadratic,
    "m": move,
    "l": line,
    "v": vert,
    "h": horz,
    "a": arc,
    "c": curve,
    "s": smooth,
    "z": zoneClose,
    "q": quadratic,
    "t": tepidQuadratic,
}


class Path(list):
    """A list of segment commands which combine to draw a shape"""

    class PathCommandProxy:
        """
        A handy class for Path traverse and coordinate access

        Reduces number of arguments in user code compared to bare
        :class:`PathCommand` methods
        """

        def __init__(
            self, command, first_point, previous_end_point, prev2_control_point
        ):
            self.command = command  # type: PathCommand
            self.first_point = first_point  # type: Vector2d
            self.previous_end_point = previous_end_point  # type: Vector2d
            self.prev2_control_point = prev2_control_point  # type: Vector2d

        @property
        def name(self):
            """The full name of the segment (i.e. Line, Arc, etc)"""
            return self.command.name

        @property
        def letter(self):
            """The single letter representation of this command (i.e. L, A, etc)"""
            return self.command.letter

        @property
        def next_command(self):
            """The implicit next command."""
            return self.command.next_command

        @property
        def is_relative(self):
            """Whether the command is defined in relative coordinates, i.e. relative to
            the previous endpoint (lower case path command letter)"""
            return self.command.is_relative

        @property
        def is_absolute(self):
            """Whether the command is defined in absolute coordinates (upper case path
            command letter)"""
            return self.command.is_absolute

        @property
        def args(self):
            """Returns path command arguments as tuple of floats"""
            return self.command.args

        @property
        def control_points(self):
            """Returns list of path command control points"""
            return self.command.control_points(
                self.first_point, self.previous_end_point, self.prev2_control_point
            )

        @property
        def end_point(self):
            """Returns last control point of path command"""
            return self.command.end_point(self.first_point, self.previous_end_point)

        def reverse(self):
            """Reverse path command"""
            return self.command.reverse(self.end_point, self.previous_end_point)

        def to_curve(self):
            """Convert command to :py:class:`Curve`
            Curve().to_curve() returns a copy
            """
            return self.command.to_curve(
                self.previous_end_point, self.prev2_control_point
            )

        def to_curves(self):
            """Convert command to list of :py:class:`Curve` commands"""
            return self.command.to_curves(
                self.previous_end_point, self.prev2_control_point
            )

        def to_absolute(self):
            """Return relative counterpart for relative commands or copy for absolute"""
            return self.command.to_absolute(self.previous_end_point)

        def __str__(self):
            return str(self.command)

        def __repr__(self):
            return "<" + self.__class__.__name__ + ">" + repr(self.command)

    def __init__(self, path_d=None):
        super().__init__()
        if isinstance(path_d, str):
            # Returns a generator returning PathCommand objects
            path_d = self.parse_string(path_d)
        elif isinstance(path_d, CubicSuperPath):
            path_d = path_d.to_path()

        for item in path_d or ():
            if isinstance(item, PathCommand):
                self.append(item)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                if isinstance(item[1], (list, tuple)):
                    self.append(PathCommand.letter_to_class(item[0])(*item[1]))
                else:
                    self.append(Line(*item))
            else:
                raise TypeError(
                    f"Bad path type: {type(path_d).__name__}"
                    f"({type(item).__name__}, ...): {item}"
                )

    @classmethod
    def parse_string(cls, path_d):
        """Parse a path string and generate segment objects"""
        for cmd, numbers in LEX_REX.findall(path_d):
            args = list(strargs(numbers))
            cmd = PathCommand.letter_to_class(cmd)
            i = 0
            while i < len(args) or cmd.nargs == 0:
                if len(args[i : i + cmd.nargs]) != cmd.nargs:
                    return
                seg = cmd(*args[i : i + cmd.nargs])
                i += cmd.nargs
                cmd = seg.next_command
                yield seg

    def bounding_box(self):
        # type: () -> Optional[BoundingBox]
        """Return bounding box of the Path"""
        if not self:
            return None
        iterator = self.proxy_iterator()
        proxy = next(iterator)
        bbox = BoundingBox(proxy.first_point.x, proxy.first_point.y)
        try:
            while True:
                proxy = next(iterator)
                proxy.command.update_bounding_box(
                    proxy.first_point,
                    [
                        proxy.prev2_control_point,
                        proxy.previous_end_point,
                    ],
                    bbox,
                )
        except StopIteration:
            return bbox

    def append(self, cmd):
        """Append a command to this path including any chained commands"""
        if isinstance(cmd, list):
            self.extend(cmd)
        elif isinstance(cmd, PathCommand):
            super().append(cmd)

    def translate(self, x, y, inplace=False):  # pylint: disable=invalid-name
        """Move all coords in this path by the given amount"""
        return self.transform(Transform(translate=(x, y)), inplace=inplace)

    def scale(self, x, y, inplace=False):  # pylint: disable=invalid-name
        """Scale all coords in this path by the given amounts"""
        return self.transform(Transform(scale=(x, y)), inplace=inplace)

    def rotate(self, deg, center=None, inplace=False):
        """Rotate the path around the given point"""
        if center is None:
            # Default center is center of bbox
            bbox = self.bounding_box()
            if bbox:
                center = bbox.center
            else:
                center = Vector2d()
        center = Vector2d(center)
        return self.transform(
            Transform(rotate=(deg, center.x, center.y)), inplace=inplace
        )

    @property
    def control_points(self):
        """Returns all control points of the Path"""
        prev = Vector2d()
        prev_prev = Vector2d()
        first = Vector2d()

        for seg in self:  # type: PathCommand
            cpts = list(seg.control_points(first, prev, prev_prev))
            if isinstance(seg, (zoneClose, ZoneClose, move, Move)):
                first = cpts[-1]
            for cpt in cpts:
                prev_prev = prev
                prev = cpt
                yield cpt

    @property
    def end_points(self):
        """Returns all endpoints of all path commands (i.e. the nodes)"""
        prev = Vector2d()
        first = Vector2d()

        for seg in self:  # type: PathCommand
            end_point = seg.end_point(first, prev)
            if isinstance(seg, (zoneClose, ZoneClose, move, Move)):
                first = end_point
            prev = end_point
            yield end_point

    def transform(self, transform, inplace=False):
        """Convert to new path"""
        result = Path()
        previous = Vector2d()
        previous_new = Vector2d()
        start_zone = True
        first = Vector2d()
        first_new = Vector2d()

        for i, seg in enumerate(self):  # type: PathCommand
            if start_zone:
                first = seg.end_point(first, previous)

            if isinstance(seg, (horz, Horz, Vert, vert)):
                seg = seg.to_line(previous)

            if seg.is_relative:
                new_seg = (
                    seg.to_absolute(previous)
                    .transform(transform)
                    .to_relative(previous_new)
                )
            else:
                new_seg = seg.transform(transform)

            if start_zone:
                first_new = new_seg.end_point(first_new, previous_new)

            if inplace:
                self[i] = new_seg
            else:
                result.append(new_seg)
            previous = seg.end_point(first, previous)
            previous_new = new_seg.end_point(first_new, previous_new)
            start_zone = isinstance(seg, (zoneClose, ZoneClose))
        if inplace:
            return self
        return result

    def reverse(self):
        """Returns a reversed path"""
        result = Path()
        *_, first = self.end_points
        closer = None

        # Go through the path in reverse order
        for index, prcom in reversed(list(enumerate(self.proxy_iterator()))):
            if isinstance(prcom.command, (Move, move, ZoneClose, zoneClose)):
                if closer is not None:
                    if len(result) > 0 and isinstance(
                        result[-1], (Line, line, Vert, vert, Horz, horz)
                    ):
                        result.pop()  # We can replace simple lines with Z
                    result.append(closer)  # replace with same type (rel or abs)
                if isinstance(prcom.command, (ZoneClose, zoneClose)):
                    closer = prcom.command
                else:
                    closer = None

            if index == 0:
                if prcom.letter == "M":
                    result.insert(0, Move(first.x, first.y))
                elif prcom.letter == "m":
                    result.insert(0, move(first.x, first.y))
            else:
                result.append(prcom.reverse())

        return result

    def break_apart(self) -> List[Path]:
        """Breaks apart a path into its subpaths

        .. versionadded:: 1.3"""
        result = [Path()]
        current = result[0]

        for cmnd in self.proxy_iterator():
            if cmnd.letter.lower() == "m":
                current = Path()
                result.append(current)
                current.append(Move(*cmnd.end_point))
            else:
                current.append(cmnd.command)
        # Remove all subpaths that are empty or only contain move commands
        return [
            i
            for i in result
            if len(i) != 0 and not all(j.letter.lower() == "m" for j in i)
        ]

    def close(self):
        """Attempt to close the last path segment"""
        if self and not isinstance(self[-1], (zoneClose, ZoneClose)):
            self.append(ZoneClose())

    def proxy_iterator(self):
        """
        Yields :py:class:`AugmentedPathIterator`

        :rtype: Iterator[ Path.PathCommandProxy ]
        """

        previous = Vector2d()
        prev_prev = Vector2d()
        first = Vector2d()

        for seg in self:  # type: PathCommand#
            if isinstance(seg, (zoneClose, ZoneClose, move, Move)):
                first = seg.end_point(first, previous)
            yield Path.PathCommandProxy(seg, first, previous, prev_prev)
            if isinstance(
                seg,
                (
                    curve,
                    tepidQuadratic,
                    quadratic,
                    smooth,
                    Curve,
                    TepidQuadratic,
                    Quadratic,
                    Smooth,
                ),
            ):
                prev_prev = list(seg.control_points(first, previous, prev_prev))[-2]
            previous = seg.end_point(first, previous)

    def to_absolute(self):
        """Convert this path to use only absolute coordinates"""
        return self._to_absolute(True)

    def to_non_shorthand(self):
        # type: () -> Path
        """Convert this path to use only absolute non-shorthand coordinates

        .. versionadded:: 1.1"""
        return self._to_absolute(False)

    def _to_absolute(self, shorthand: bool) -> Path:
        """Make entire Path absolute.

        Args:
            shorthand (bool): If false, then convert all shorthand commands to
                non-shorthand.

        Returns:
            Path: the input path, converted to absolute coordinates.
        """

        abspath = Path()

        previous = Vector2d()
        first = Vector2d()

        for seg in self:  # type: PathCommand
            if isinstance(seg, (move, Move)):
                first = seg.end_point(first, previous)

            if shorthand:
                abspath.append(seg.to_absolute(previous))
            else:
                if abspath and isinstance(abspath[-1], (Curve, Quadratic)):
                    prev_control = list(
                        abspath[-1].control_points(Vector2d(), Vector2d(), Vector2d())
                    )[-2]
                else:
                    prev_control = previous

                abspath.append(seg.to_non_shorthand(previous, prev_control))

            previous = seg.end_point(first, previous)

        return abspath

    def to_relative(self):
        """Convert this path to use only relative coordinates"""
        abspath = Path()

        previous = Vector2d()
        first = Vector2d()

        for seg in self:  # type: PathCommand
            if isinstance(seg, (move, Move)):
                first = seg.end_point(first, previous)

            abspath.append(seg.to_relative(previous))
            previous = seg.end_point(first, previous)

        return abspath

    def __str__(self):
        return " ".join([str(seg) for seg in self])

    def __add__(self, other):
        acopy = copy.deepcopy(self)
        if isinstance(other, str):
            other = Path(other)
        if isinstance(other, list):
            acopy.extend(other)
        return acopy

    def to_arrays(self):
        """Returns path in format of parsePath output, returning arrays of absolute
        command data

        .. deprecated:: 1.0
            This is compatibility function for older API. Should not be used in new code

        """
        return [[seg.letter, list(seg.args)] for seg in self.to_non_shorthand()]

    def to_superpath(self):
        """Convert this path into a cubic super path"""
        return CubicSuperPath(self)

    def copy(self):
        """Make a copy"""
        return copy.deepcopy(self)


class CubicSuperPath(list):
    """
    A conversion of a path into a predictable list of cubic curves which
    can be operated on as a list of simplified instructions.

    When converting back into a path, all lines, arcs etc will be converted
    to curve instructions.

    Structure is held as [SubPath[(point_a, bezier, point_b), ...]], ...]
    """

    def __init__(self, items):
        super().__init__()
        self._closed = True
        self._prev = Vector2d()
        self._prev_prev = Vector2d()

        if isinstance(items, str):
            items = Path(items)

        if isinstance(items, Path):
            items = items.to_absolute()

        for item in items:
            self.append(item)

    def __str__(self):
        return str(self.to_path())

    def append(self, item, force_shift=False):
        """Accept multiple different formats for the data

        .. versionchanged:: 1.2
            ``force_shift`` parameter has been added
        """
        if isinstance(item, list) and len(item) == 2 and isinstance(item[0], str):
            item = PathCommand.letter_to_class(item[0])(*item[1])
        coordinate_shift = True
        if isinstance(item, list) and len(item) == 3 and not force_shift:
            coordinate_shift = False
        is_quadratic = False
        if isinstance(item, PathCommand):
            if isinstance(item, Move):
                if self._closed is False:
                    super().append([])
                item = [list(item.args), list(item.args), list(item.args)]
            elif isinstance(item, ZoneClose) and self and self[-1]:
                # This duplicates the first segment to 'close' the path, it's appended
                # directly because we don't want to last coord to change for the final
                # segment.
                self[-1].append(
                    [self[-1][0][0][:], self[-1][0][1][:], self[-1][0][2][:]]
                )
                # Then adds a new subpath for the next shape (if any)
                self._closed = True
                self._prev.assign(self._first)
                return
            elif isinstance(item, Arc):
                # Arcs are made up of three curves (approximated)
                for arc_curve in item.to_curves(self._prev, self._prev_prev):
                    x2, y2, x3, y3, x4, y4 = arc_curve.args
                    self.append([[x2, y2], [x3, y3], [x4, y4]], force_shift=True)
                    self._prev_prev.assign(x3, y3)
                return
            else:
                is_quadratic = isinstance(
                    item, (Quadratic, TepidQuadratic, quadratic, tepidQuadratic)
                )
                if isinstance(item, (Horz, Vert)):
                    item = item.to_line(self._prev)
                prp = self._prev_prev
                if is_quadratic:
                    self._prev_prev = list(
                        item.control_points(self._first, self._prev, prp)
                    )[-2:-1][0]
                item = item.to_curve(self._prev, prp)

        if isinstance(item, Curve):
            # Curves are cut into three tuples for the super path.
            item = item.to_bez()

        if not isinstance(item, list):
            raise ValueError(f"Unknown super curve item type: {item}")

        if len(item) != 3 or not all(len(bit) == 2 for bit in item):
            # The item is already a subpath (usually from some other process)
            if len(item[0]) == 3 and all(len(bit) == 2 for bit in item[0]):
                super().append(self._clean(item))
                self._prev_prev = Vector2d(self[-1][-1][0])
                self._prev = Vector2d(self[-1][-1][1])
                return
            raise ValueError(f"Unknown super curve list format: {item}")

        if self._closed:
            # Closed means that the previous segment is closed so we need a new one
            # We always append to the last open segment. CSP starts out closed.
            self._closed = False
            super().append([])

        if coordinate_shift:
            if self[-1]:
                # The last tuple is replaced, it's the coords of where the next segment
                # will land.
                self[-1][-1][-1] = item[0][:]
            # The last coord is duplicated, but is expected to be replaced
            self[-1].append(item[1:] + copy.deepcopy(item)[-1:])
        else:
            # Item is already a csp segment and has already been shifted.
            self[-1].append(copy.deepcopy(item))

        self._prev = Vector2d(self[-1][-1][1])
        if not is_quadratic:
            self._prev_prev = Vector2d(self[-1][-1][0])

    def _clean(self, lst):
        """Recursively clean lists so they have the same type"""
        if isinstance(lst, (tuple, list)):
            return [self._clean(child) for child in lst]
        return lst

    @property
    def _first(self):
        try:
            return Vector2d(self[-1][0][0])
        except IndexError:
            return Vector2d()

    def to_path(self, curves_only=False, rtol=1e-5, atol=1e-8):
        """Convert the super path back to an svg path

        Arguments: see :func:`to_segments` for parameters"""
        return Path(list(self.to_segments(curves_only, rtol, atol)))

    def to_segments(self, curves_only=False, rtol=1e-5, atol=1e-8):
        """Generate a set of segments for this cubic super path

        Arguments:
            curves_only (bool, optional): If False, curves that can be represented
                by Lineto / ZoneClose commands, will be. Defaults to False.
            rtol (float, optional): relative tolerance, passed to :func:`is_line` and
                :func:`inkex.transforms.ImmutableVector2d.is_close` for checking if a
                line can be replaced by a ZoneClose command. Defaults to 1e-5.

                .. versionadded:: 1.2
            atol: absolute tolerance, passed to :func:`is_line` and
                :func:`inkex.transforms.ImmutableVector2d.is_close`. Defaults to 1e-8.

                .. versionadded:: 1.2"""
        for subpath in self:
            previous = []
            for segment in subpath:
                if not previous:
                    yield Move(*segment[1][:])
                elif self.is_line(previous, segment, rtol, atol) and not curves_only:
                    if segment is subpath[-1] and Vector2d(segment[1]).is_close(
                        subpath[0][1], rtol, atol
                    ):
                        yield ZoneClose()
                    else:
                        yield Line(*segment[1][:])
                else:
                    yield Curve(*(previous[2][:] + segment[0][:] + segment[1][:]))
                previous = segment

    def transform(self, transform):
        """Apply a transformation matrix to this super path"""
        return self.to_path().transform(transform).to_superpath()

    @staticmethod
    def is_on(pt_a, pt_b, pt_c, tol=1e-8):
        """Checks if point pt_a is on the line between points pt_b and pt_c

        .. versionadded:: 1.2"""
        return CubicSuperPath.collinear(pt_a, pt_b, pt_c, tol) and (
            CubicSuperPath.within(pt_a[0], pt_b[0], pt_c[0])
            if pt_a[0] != pt_b[0]
            else CubicSuperPath.within(pt_a[1], pt_b[1], pt_c[1])
        )

    @staticmethod
    def collinear(pt_a, pt_b, pt_c, tol=1e-8):
        """Checks if points pt_a, pt_b, pt_c lie on the same line,
        i.e. that the cross product (b-a) x (c-a) < tol

        .. versionadded:: 1.2"""
        return (
            abs(
                (pt_b[0] - pt_a[0]) * (pt_c[1] - pt_a[1])
                - (pt_c[0] - pt_a[0]) * (pt_b[1] - pt_a[1])
            )
            < tol
        )

    @staticmethod
    def within(val_b, val_a, val_c):
        """Checks if float val_b is between val_a and val_c

        .. versionadded:: 1.2"""
        return val_a <= val_b <= val_c or val_c <= val_b <= val_a

    @staticmethod
    def is_line(previous, segment, rtol=1e-5, atol=1e-8):
        """Check whether csp segment (two points) can be expressed as a line has retracted handles or the handles
        can be retracted without loss of information (i.e. both handles lie on the
        line)

        .. versionchanged:: 1.2
            Previously, it was only checked if both control points have retracted
            handles. Now it is also checked if the handles can be retracted without
            (visible) loss of information (i.e. both handles lie on the line connecting
            the nodes).

        Arguments:
            previous: first node in superpath notation
            segment: second node in superpath notation
            rtol (float, optional): relative tolerance, passed to
                :func:`inkex.transforms.ImmutableVector2d.is_close` for checking handle
                retraction. Defaults to 1e-5.

                .. versionadded:: 1.2
            atol (float, optional): absolute tolerance, passed to
                :func:`inkex.transforms.ImmutableVector2d.is_close` for checking handle
                retraction and
                :func:`inkex.paths.CubicSuperPath.is_on` for checking if all points
                (nodes + handles) lie on a line. Defaults to 1e-8.

                .. versionadded:: 1.2
        """

        retracted = Vector2d(previous[1]).is_close(
            previous[2], rtol, atol
        ) and Vector2d(segment[0]).is_close(segment[1], rtol, atol)

        if retracted:
            return True

        # Can both handles be retracted without loss of information?
        # Definitely the case if the handles lie on the same line as the two nodes and
        # in the correct order
        # E.g. cspbezsplitatlength outputs non-retracted handles when splitting a
        # straight line
        return CubicSuperPath.is_on(
            segment[0], segment[1], previous[2], atol
        ) and CubicSuperPath.is_on(previous[2], previous[1], segment[0], atol)


def arc_to_path(point, params):
    """Approximates an arc with cubic bezier segments.

    Arguments:
        point:  Starting point (absolute coords)
        params: Arcs parameters as per
              https://www.w3.org/TR/SVG/paths.html#PathDataEllipticalArcCommands

    Returns a list of triplets of points :
    [control_point_before, node, control_point_after]
    (first and last returned triplets are [p1, p1, *] and [*, p2, p2])
    """

    # pylint: disable=invalid-name, too-many-locals
    A = point[:]
    rx, ry, teta, longflag, sweepflag, x2, y2 = params[:]
    teta = teta * pi / 180.0
    B = [x2, y2]
    # Degenerate ellipse
    if rx == 0 or ry == 0 or A == B:
        return [[A[:], A[:], A[:]], [B[:], B[:], B[:]]]

    # turn coordinates so that the ellipse morph into a *unit circle* (not 0-centered)
    mat = matprod((rotmat(teta), [[1.0 / rx, 0.0], [0.0, 1.0 / ry]], rotmat(-teta)))
    applymat(mat, A)
    applymat(mat, B)

    k = [-(B[1] - A[1]), B[0] - A[0]]
    d = k[0] * k[0] + k[1] * k[1]
    k[0] /= sqrt(d)
    k[1] /= sqrt(d)
    d = sqrt(max(0, 1 - d / 4.0))
    # k is the unit normal to AB vector, pointing to center O
    # d is distance from center to AB segment (distance from O to the midpoint of AB)
    # for the last line, remember this is a unit circle, and kd vector is ortogonal to
    # AB (Pythagorean thm)

    if longflag == sweepflag:
        # top-right ellipse in SVG example
        # https://www.w3.org/TR/SVG/images/paths/arcs02.svg
        d *= -1

    O = [(B[0] + A[0]) / 2.0 + d * k[0], (B[1] + A[1]) / 2.0 + d * k[1]]
    OA = [A[0] - O[0], A[1] - O[1]]
    OB = [B[0] - O[0], B[1] - O[1]]
    start = acos(OA[0] / norm(OA))
    if OA[1] < 0:
        start *= -1
    end = acos(OB[0] / norm(OB))
    if OB[1] < 0:
        end *= -1
    # start and end are the angles from center of the circle to A and to B respectively

    if sweepflag and start > end:
        end += 2 * pi
    if (not sweepflag) and start < end:
        end -= 2 * pi

    NbSectors = int(abs(start - end) * 2 / pi) + 1
    dTeta = (end - start) / NbSectors
    v = 4 * tan(dTeta / 4.0) / 3.0
    # I would use v = tan(dTeta/2)*4*(sqrt(2)-1)/3 ?
    p = []
    for i in range(0, NbSectors + 1, 1):
        angle = start + i * dTeta
        v1 = [
            O[0] + cos(angle) - (-v) * sin(angle),
            O[1] + sin(angle) + (-v) * cos(angle),
        ]
        pt = [O[0] + cos(angle), O[1] + sin(angle)]
        v2 = [O[0] + cos(angle) - v * sin(angle), O[1] + sin(angle) + v * cos(angle)]
        p.append([v1, pt, v2])
    p[0][0] = p[0][1][:]
    p[-1][2] = p[-1][1][:]

    # go back to the original coordinate system
    mat = matprod((rotmat(teta), [[rx, 0], [0, ry]], rotmat(-teta)))
    for pts in p:
        applymat(mat, pts[0])
        applymat(mat, pts[1])
        applymat(mat, pts[2])
    return p


def matprod(mlist):
    """Get the product of the mat"""
    prod = mlist[0]
    for mat in mlist[1:]:
        a00 = prod[0][0] * mat[0][0] + prod[0][1] * mat[1][0]
        a01 = prod[0][0] * mat[0][1] + prod[0][1] * mat[1][1]
        a10 = prod[1][0] * mat[0][0] + prod[1][1] * mat[1][0]
        a11 = prod[1][0] * mat[0][1] + prod[1][1] * mat[1][1]
        prod = [[a00, a01], [a10, a11]]
    return prod


def rotmat(teta):
    """Rotate the mat"""
    return [[cos(teta), -sin(teta)], [sin(teta), cos(teta)]]


def applymat(mat, point):
    """Apply the given mat"""
    x = mat[0][0] * point[0] + mat[0][1] * point[1]
    y = mat[1][0] * point[0] + mat[1][1] * point[1]
    point[0] = x
    point[1] = y


def norm(point):
    """Normalise"""
    return sqrt(point[0] * point[0] + point[1] * point[1])
