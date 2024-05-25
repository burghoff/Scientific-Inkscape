# coding=utf-8
#
# Copyright (C) 2005 Aaron Spike, aaron@ekips.org
#               2020 Jonathan Neuhauser, jonathan.neuhauser@outlook.com
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
"""Module for interpolating attributes and styles

.. versionchanged:: 1.2
    Rewritten in inkex 1.2 in an object-oriented structure to support more attributes.
"""
from bisect import bisect_left
import abc
import copy

from .styles import Style
from .elements._filters import LinearGradient, RadialGradient, Stop
from .transforms import Transform
from .colors import Color
from .units import convert_unit, parse_unit, render_unit
from .bezier import bezlenapprx, cspbezsplit, cspbezsplitatlength, csplength
from .paths import Path, CubicSuperPath
from .elements import SvgDocumentElement
from .utils import FragmentError


try:
    from typing import Tuple, TypeVar

    Value = TypeVar("Value")
    Number = TypeVar("Number", int, float)
except ImportError:
    pass


def interpcoord(coord_a: Number, coord_b: Number, time: float):
    """Interpolate single coordinate by the amount of time"""
    return ValueInterpolator(coord_a, coord_b).interpolate(time)


def interppoints(point1, point2, time):
    # type: (Tuple[float, float], Tuple[float, float], float) -> Tuple[float, float]
    """Interpolate coordinate points by amount of time"""
    return ArrayInterpolator(point1, point2).interpolate(time)


class AttributeInterpolator(abc.ABC):
    """Interpolate between attributes"""

    def __init__(self, start_value, end_value):
        self.start_value = start_value
        self.end_value = end_value

    @staticmethod
    def best_style(node):
        """Gets the best possible approximation to a node's style. For nodes inside the
        element tree of an SVG file, stylesheets defined in the defs of that file can be
        taken into account. This should be the case for input elements, but is not
        required - in that case, only the local inline style is used.

        During the interpolation process, some nodes are created temporarily, such as
        plain gradients of a single color to allow solid<->gradient interpolation. These
        are not attached to the document tree and therefore have no root. Since the only
        style relevant for them is the inline style, it is acceptable to fallback to it.

        Args:
            node (BaseElement): The node to get the best approximated style of

        Returns:
            Style: If the node is rooted, the CSS specified style. Else, the inline
            style."""
        try:
            return node.specified_style()
        except FragmentError:
            return node.style

    @staticmethod
    def create_from_attribute(snode, enode, attribute, method=None):
        """Creates an interpolator for an attribute. Currently, only path, transform and
        style attributes are supported

        Args:
            snode (BaseElement): start element
            enode (BaseElement): end element
            attribute (str): attribute name (for styles, starting with "style/")
            method (AttributeInterpolator, optional): (currently only used for paths).
                Specifies a method used to interpolate the attribute. Defaults to None.

        Raises:
            ValueError: if an attribute is passed that is not a style, path or transform
                attribute

        Returns:
            AttributeInterpolator: an interpolator whose type depends on attribute.
        """
        if attribute in Style.color_props:
            return StyleInterpolator.create_from_fill_stroke(snode, enode, attribute)
        if attribute == "d":
            if method is None:
                method = FirstNodesInterpolator
            return method(snode.path, enode.path)
        if attribute == "style":
            return StyleInterpolator(snode, enode)
        if attribute.startswith("style/"):
            return StyleInterpolator.create(snode, enode, attribute[6:])
        if attribute == "transform":
            return TransformInterpolator(snode.transform, enode.transform)
        if method is not None:
            return method(snode.get(attribute), enode.get(attribute))
        raise ValueError("only path and style attributes are supported")

    @abc.abstractmethod
    def interpolate(self, time=0):
        """Interpolation method, needs to be implemented by subclasses"""
        return


class StyleInterpolator(AttributeInterpolator):
    """Class to interpolate styles"""

    def __init__(self, start_value, end_value):
        super().__init__(start_value, end_value)
        self.interpolators = {}
        # some keys are always processed in a certain order, these provide alternative
        # interpolation routes if e.g. Color<->none is interpolated
        all_keys = list(
            dict.fromkeys(
                ["fill", "stroke", "fill-opacity", "stroke-opacity", "stroke-width"]
                + list(self.best_style(start_value).keys())
                + list(self.best_style(end_value).keys())
            )
        )
        for attr in all_keys:
            sstyle = self.best_style(start_value)
            estyle = self.best_style(end_value)
            if attr not in sstyle and attr not in estyle:
                continue
            try:
                interp = StyleInterpolator.create(
                    self.start_value, self.end_value, attr
                )
                self.interpolators[attr] = interp
            except ValueError:
                # no interpolation method known for this attribute
                pass

    @staticmethod
    def create(snode, enode, attribute):
        """Creates an Interpolator for a given style attribute, depending on its type:

            - Color properties (such as fill, stroke) -> :class:`ColorInterpolator`,
              :class:`GradientInterpolator` ect.
            - Unit properties -> :class:`UnitValueInterpolator`
            - other properties -> :class:`ValueInterpolator`

        Args:
            snode (BaseElement): start element
            enode (BaseElement): end element
            attribute (str): attribute to interpolate

        Raises:
            ValueError: if the attribute is not in any of the lists

        Returns:
            AttributeInterpolator: an interpolator object whose type depends on the
            attribute.
        """
        if attribute in Style.color_props:
            return StyleInterpolator.create_from_fill_stroke(snode, enode, attribute)

        if attribute in Style.unit_props:
            return UnitValueInterpolator(
                AttributeInterpolator.best_style(snode)(attribute),
                AttributeInterpolator.best_style(enode)(attribute),
            )

        if attribute in Style.opacity_props:
            return ValueInterpolator(
                AttributeInterpolator.best_style(snode)(attribute),
                AttributeInterpolator.best_style(enode)(attribute),
            )

        raise ValueError("Unknown attribute")

    @staticmethod
    def create_from_fill_stroke(snode, enode, attribute):
        """Creates an Interpolator for a given color-like attribute

        Args:
            snode (BaseElement): start element
            enode (BaseElement): end element
            attribute (str): attribute to interpolate

        Raises:
            ValueError: if the attribute is not color-like
            ValueError: if the attribute is unset on both start and end style

        Returns:
            AttributeInterpolator: an interpolator object whose type depends on the
            attribute.
        """
        if attribute not in Style.color_props:
            raise ValueError("attribute must be a color property")

        sstyle = AttributeInterpolator.best_style(snode)
        estyle = AttributeInterpolator.best_style(enode)

        styles = [[snode, sstyle], [enode, estyle]]
        for cur, curstyle in styles:
            if curstyle(attribute) is None:
                cur.style[attribute + "-opacity"] = 0.0
                if attribute == "stroke":
                    cur.style["stroke-width"] = 0.0

        # check if style is none, unset or a color
        if isinstance(
            sstyle(attribute), (LinearGradient, RadialGradient)
        ) or isinstance(estyle(attribute), (LinearGradient, RadialGradient)):
            # if one of the two styles is a gradient, use gradient interpolation.
            try:
                return GradientInterpolator.create(snode, enode, attribute)
            except ValueError:
                # different gradient types, just duplicate the first
                return TrivialInterpolator(sstyle(attribute))
        if sstyle(attribute) is None and estyle(attribute) is None:
            return TrivialInterpolator("none")
        return ColorInterpolator.create(sstyle, estyle, attribute)

    def interpolate(self, time=0):
        """Interpolates a style using the interpolators set in self.interpolators

        Args:
            time (int, optional): Interpolation position. If 0, start_value is returned,
                if 1, end_value is returned. Defaults to 0.

        Returns:
            inkex.Style: interpolated style
        """
        style = Style()
        for prop, interp in self.interpolators.items():
            style[prop] = interp.interpolate(time)
        return style


class TrivialInterpolator(AttributeInterpolator):
    """Trivial interpolator, returns value for every time"""

    def __init__(self, value):
        super().__init__(value, value)

    def interpolate(self, time=0):
        return self.start_value


class ValueInterpolator(AttributeInterpolator):
    """Class for interpolation of a single value"""

    def __init__(self, start_value=0, end_value=0):
        super().__init__(float(start_value), float(end_value))

    def interpolate(self, time=0):
        """(Linearly) interpolates a value

        Args:
            time (int, optional): Interpolation position. If 0, start_value is returned,
                if 1, end_value is returned. Defaults to 0.

        Returns:
            int: interpolated value
        """
        return self.start_value + ((self.end_value - self.start_value) * time)


class UnitValueInterpolator(ValueInterpolator):
    """Class for interpolation of a value with unit"""

    def __init__(self, start_value=0, end_value=0):
        start_val, start_unit = parse_unit(start_value)
        end_val = convert_unit(end_value, start_unit)
        super().__init__(start_val, end_val)
        self.unit = start_unit

    def interpolate(self, time=0):
        return render_unit(super().interpolate(time), self.unit)


class ArrayInterpolator(AttributeInterpolator):
    """Interpolates array-like objects element-wise, e.g. color, transform,
    coordinate"""

    def __init__(self, start_value, end_value):
        super().__init__(start_value, end_value)
        self.interpolators = [
            ValueInterpolator(cur, other)
            for (cur, other) in zip(start_value, end_value)
        ]

    def interpolate(self, time=0):
        """Interpolates an array element-wise

        Args:
            time (int, optional): [description]. Defaults to 0.

        Returns:
            List: interpolated array
        """
        return [interp.interpolate(time) for interp in self.interpolators]


class TransformInterpolator(ArrayInterpolator):
    """Class for interpolation of transforms"""

    def __init__(self, start_value=Transform(), end_value=Transform()):
        """Creates a transform interpolator.

        Args:
            start_value (inkex.Transform, optional): start transform. Defaults to
                inkex.Transform().
            end_value (inkex.Transform, optional): end transform. Defaults to
                inkex.Transform().
        """
        super().__init__(start_value.to_hexad(), end_value.to_hexad())

    def interpolate(self, time=0):
        """Interpolates a transform by interpolating each item in the transform hexad
        separately.

        Args:
            time (int, optional): Interpolation position. If 0, start_value is returned,
                if 1, end_value is returned. Defaults to 0.

        Returns:
            Transform: interpolated transform
        """
        return Transform(super().interpolate(time))


class ColorInterpolator(ArrayInterpolator):
    """Class for color interpolation"""

    @staticmethod
    def create(sst, est, attribute):
        """Creates a ColorInterpolator for either Fill or stroke, depending on the
        attribute.

        Args:
            sst (Style): Start style
            est (Style): End style
            attribute (string): either fill or stroke

        Raises:
            ValueError: if none of the start or end style is a color.

        Returns:
            ColorInterpolator: A ColorInterpolator object
        """
        styles = [sst, est]
        for cur, other in zip(styles, reversed(styles)):
            if not isinstance(cur(attribute), Color) or cur(attribute) is None:
                cur[attribute] = other(attribute)
        this = ColorInterpolator(
            Color(styles[0](attribute)), Color(styles[1](attribute))
        )
        if this is None:
            raise ValueError("One of the two attribute needs to be a plain color")
        return this

    def __init__(self, start_value=Color("#000000"), end_value=Color("#000000")):
        super().__init__(start_value, end_value)

    def interpolate(self, time=0):
        """Interpolates a color by interpolating its r, g, b, a channels separately.

        Args:
            time (int, optional): Interpolation position. If 0, start_value is returned,
                if 1, end_value is returned. Defaults to 0.

        Returns:
            Color: interpolated color
        """
        return Color(list(map(int, super().interpolate(time))))


class GradientInterpolator(AttributeInterpolator):
    """Base class for Gradient Interpolation"""

    def __init__(self, start_value, end_value, svg=None):
        super().__init__(start_value, end_value)
        self.svg = svg
        # If one of the styles is empty, set it to the gradient of the other
        if start_value is None:
            self.start_value = end_value
        if end_value is None:
            self.end_value = start_value
        self.transform_interpolator = TransformInterpolator(
            self.start_value.gradientTransform, self.end_value.gradientTransform
        )
        self.orientation_interpolator = {
            attr: UnitValueInterpolator(
                self.start_value.get(attr), self.end_value.get(attr)
            )
            for attr in self.start_value.orientation_attributes
            if self.start_value.get(attr) is not None
            and self.end_value.get(attr) is not None
        }
        if not (
            self.start_value.href is not None
            and self.start_value.href is self.end_value.href
        ):
            # the gradient link to different stops, interpolate between them
            # add both start and end offsets, then take distict
            newoffsets = sorted(
                list(set(self.start_value.stop_offsets + self.end_value.stop_offsets))
            )

            def func(start, end, time):
                return StopInterpolator(start, end).interpolate(time)

            sstops = GradientInterpolator.interpolate_linear_list(
                self.start_value.stop_offsets,
                list(self.start_value.stops),
                newoffsets,
                func,
            )
            ostops = GradientInterpolator.interpolate_linear_list(
                self.end_value.stop_offsets,
                list(self.end_value.stops),
                newoffsets,
                func,
            )
            self.newstop_interpolator = [
                StopInterpolator(s1, s2) for s1, s2 in zip(sstops, ostops)
            ]
        else:
            self.newstop_interpolator = None

    @staticmethod
    def create(snode, enode, attribute):
        """Creates a `GradientInterpolator` for either fill or stroke, depending on
        attribute.

        Cases: (A, B) -> Interpolator

          - Linear Gradient, Linear Gradient -> LinearGradientInterpolator
          - Color or None, Linear Gradient -> LinearGradientInterpolator
          - Radial Gradient, Radial Gradient -> RadialGradientInterpolator
          - Color or None, Radial Gradient -> RadialGradientInterpolator
          - Radial Gradient, Linear Gradient -> ValueError
          - Color or None, Color or None -> ValueError

        Args:
            snode (BaseElement): start element
            enode (BaseElement): end element
            attribute (string): either fill or stroke

        Raises:
            ValueError: if none of the styles are a gradient or if they are gradients
                of different types

        Returns:
            GradientInterpolator: an Interpolator object
        """
        interpolator = None
        gradienttype = None
        # first find out which type of interpolator we need
        sstyle = AttributeInterpolator.best_style(snode)
        estyle = AttributeInterpolator.best_style(enode)
        for cur in [sstyle, estyle]:
            curgrad = None
            if isinstance(cur(attribute), (LinearGradient, RadialGradient)):
                curgrad = cur(attribute)
            for gradtype, interp in [
                [LinearGradient, LinearGradientInterpolator],
                [RadialGradient, RadialGradientInterpolator],
            ]:
                if curgrad is not None and isinstance(curgrad, gradtype):
                    if interpolator is None:
                        interpolator = interp
                        gradienttype = gradtype
                    if not (interp == interpolator):
                        raise ValueError("Gradient types don't match")
        # If one of the styles is empty, set it to the gradient of the other, but with
        # zero opacity (and stroke-width for strokes)
        # If one of the styles is a plain color, replace it by a gradient with a single
        # stop
        iterator = [[snode, gradienttype(), enode], [enode, gradienttype(), snode]]
        for index in [0, 1]:
            curstyle = AttributeInterpolator.best_style(iterator[index][0])
            value = curstyle(attribute)
            if value is None:
                # if the attribute of one of the two ends is unset, set the opacity to
                # zero.
                iterator[index][0].style[attribute + "-opacity"] = 0.0
                if attribute == "stroke":
                    iterator[index][0].style["stroke-width"] = 0.0
            if isinstance(value, Color):
                # if the attribute of one of the two ends is a color, convert it to a
                # one-stop gradient. Type depends on the type of the other gradient.
                interpolator.initialize_position(
                    iterator[index][1], iterator[index][0].bounding_box()
                )
                stop = Stop()
                stop.style = Style()
                stop.style["stop-color"] = value
                stop.offset = 0
                iterator[index][1].add(stop)
                stop = Stop()
                stop.style = Style()
                stop.style["stop-color"] = value
                stop.offset = 1
                iterator[index][1].add(stop)
            else:
                iterator[index][1] = value  # is a gradient
        if interpolator is None:
            raise ValueError("None of the two styles is a gradient")
        if interpolator in [LinearGradientInterpolator, RadialGradientInterpolator]:
            return interpolator(iterator[0][1], iterator[1][1], snode)
        return interpolator(iterator[0][1], iterator[1][1])

    @staticmethod
    def interpolate_linear_list(positions, values, newpositions, func):
        """Interpolates a list of values given at n positions to the best approximation
        at m newpositions.

        >>>
            |
            |         x
            |  x
            _________________
               pq  q  p   q
            (x denotes function values, p: positions, q: newpositions)
            A function may be given to interpolate between given values.

        Args:
            positions (list[number-like]): position of current function values
            values (list[Type]): list of arbitrary type,
                ``len(values) == len(positions)``
            newpositions (list[number-like]): position of interpolated values
            func (Callable[[Type, Type, float], Type]): Function to interpolate between
                values

        Returns:
            list[Type]: interpolated function values at positions
        """
        newvalues = []
        positions = list(map(float, positions))
        newpositions = list(map(float, newpositions))
        for pos in newpositions:
            if len(positions) == 1:
                newvalues.append(values[0])
            else:
                # current run:
                #       idxl pos idxr
                # p     p    |   p
                #    q       q
                idxl = max(0, bisect_left(positions, pos) - 1)
                idxr = min(len(positions) - 1, idxl + 1)
                fraction = (pos - positions[idxl]) / (positions[idxr] - positions[idxl])
                vall = values[idxl]
                valr = values[idxr]
                newval = func(vall, valr, fraction)
                newvalues.append(newval)
        return newvalues

    @staticmethod
    def append_to_doc(element, gradient):
        """Splits a gradient into stops and orientation, appends it to the document's
        defs and returns the href to the orientation gradient.

        Args:
            element (BaseElement): an element inside the SVG that the gradient should be
                added to
            gradient (Gradient): the gradient to append to the document

        Returns:
            Gradient: the orientation gradient, or the gradient object if
            element has no root or is None
        """
        stops, orientation = gradient.stops_and_orientation()
        if element is None or (
            element.getparent() is None and not isinstance(element, SvgDocumentElement)
        ):
            return gradient
        element.root.defs.add(orientation)
        if len(stops) > 0:
            element.root.defs.add(stops, orientation)
            orientation.href = stops.get_id()
        return orientation

    def interpolate(self, time=0):
        """Interpolate with another gradient."""
        newgrad = self.start_value.copy()
        # interpolate transforms
        newgrad.gradientTransform = self.transform_interpolator.interpolate(time)

        # interpolate orientation
        for attr in self.orientation_interpolator.keys():
            newgrad.set(attr, self.orientation_interpolator[attr].interpolate(time))

        # interpolate stops
        if self.newstop_interpolator is not None:
            newgrad.remove_all(Stop)
            newgrad.add(
                *[interp.interpolate(time) for interp in self.newstop_interpolator]
            )
        if self.svg is None:
            return newgrad
        return GradientInterpolator.append_to_doc(self.svg, newgrad)


class LinearGradientInterpolator(GradientInterpolator):
    """Class for interpolation of linear gradients"""

    def __init__(
        self, start_value=LinearGradient(), end_value=LinearGradient(), svg=None
    ):
        super().__init__(start_value, end_value, svg)

    @staticmethod
    def initialize_position(grad, bbox):
        """Initializes a linear gradient's position"""
        grad.set("x1", bbox.left)
        grad.set("x2", bbox.right)
        grad.set("y1", bbox.center.y)
        grad.set("y2", bbox.center.y)


class RadialGradientInterpolator(GradientInterpolator):
    """Class to interpolate radial gradients"""

    def __init__(
        self, start_value=RadialGradient(), end_value=RadialGradient(), svg=None
    ):
        super().__init__(start_value, end_value, svg)

    @staticmethod
    def initialize_position(grad, bbox):
        """Initializes a radial gradient's position"""
        x, y = bbox.center
        grad.set("cx", x)
        grad.set("cy", y)
        grad.set("fx", x)
        grad.set("fy", y)
        grad.set("r", bbox.right - bbox.center.x)


class StopInterpolator(AttributeInterpolator):
    """Class to interpolate gradient stops"""

    def __init__(self, start_value, end_value):
        super().__init__(start_value, end_value)
        self.style_interpolator = StyleInterpolator(start_value, end_value)
        self.position_interpolator = ValueInterpolator(
            float(start_value.offset), float(end_value.offset)
        )

    def interpolate(self, time=0):
        """Interpolates a gradient stop by interpolating style and offset separately

        Args:
            time (int, optional): Interpolation position. If 0, start_value is returned,
                if 1, end_value is returned. Defaults to 0.

        Returns:
            Stop: interpolated gradient stop
        """
        newstop = Stop()
        newstop.style = self.style_interpolator.interpolate(time)
        newstop.offset = self.position_interpolator.interpolate(time)
        return newstop


class PathInterpolator(AttributeInterpolator):
    """Base class for Path interpolation"""

    def __init__(self, start_value=Path(), end_value=Path()):
        super().__init__(start_value.to_superpath(), end_value.to_superpath())
        self.processed_end_path = None
        self.processed_start_path = None

    def truncate_subpaths(self):
        """Truncates the longer path so that all subpaths in both paths have an equal
        number of bezier commands"""
        s = [[]]
        e = [[]]
        # loop through all subpaths as long as there are remaining ones
        while self.start_value and self.end_value:
            # if both subpaths contain a bezier command, append it to s and e
            if self.start_value[0] and self.end_value[0]:
                s[-1].append(self.start_value[0].pop(0))
                e[-1].append(self.end_value[0].pop(0))
            # if the subpath of start_value is empty, add the remaining empty list as
            # new subpath of s and one more item of end_value as new subpath of e.
            # Afterwards, the loop terminates
            elif self.end_value[0]:
                s.append(self.start_value.pop(0))
                e[-1].append(self.end_value[0][0])
                e.append([self.end_value[0].pop(0)])
            elif self.start_value[0]:
                e.append(self.end_value.pop(0))
                s[-1].append(self.start_value[0][0])
                s.append([self.start_value[0].pop(0)])
            # if there are no commands left in both start_value or end_value, add empty
            # list to both start_value and end_value
            else:
                s.append(self.start_value.pop(0))
                e.append(self.end_value.pop(0))
        self.processed_start_path = s
        self.processed_end_path = e

    def interpolate(self, time=0):
        # create an interpolated path for each interval
        interp = []
        # process subpaths
        for ssubpath, esubpath in zip(
            self.processed_start_path, self.processed_end_path
        ):
            if not (ssubpath or esubpath):
                break
            # add a new subpath to the interpolated path
            interp.append([])
            # process each bezier command in the subpaths (which now have equal length)
            for sbezier, ebezier in zip(ssubpath, esubpath):
                if not (sbezier or ebezier):
                    break
                # add a new bezier command to the last subpath
                interp[-1].append([])
                # process points
                for point1, point2 in zip(sbezier, ebezier):
                    if not (point1 or point2):
                        break
                    # add a new point to the last bezier command
                    interp[-1][-1].append(
                        ArrayInterpolator(point1, point2).interpolate(time)
                    )
        # remove final subpath if empty.
        if not interp[-1]:
            del interp[-1]
        return CubicSuperPath(interp)


class EqualSubsegmentsInterpolator(PathInterpolator):
    """Interpolates the path by rediscretizing the subpaths first."""

    @staticmethod
    def get_subpath_lenghts(path):
        """prepare lengths for interpolation"""
        sp_lenghts, total = csplength(path)
        t = 0
        lenghts = []
        for sp in sp_lenghts:
            for l in sp:
                t += l / total
                lenghts.append(t)
        lenghts.sort()
        return sp_lenghts, total, lenghts

    @staticmethod
    def process_path(path, other):
        """Rediscretize path so that all subpaths have an equal number of segments,
        so that there is a node at the path "times" where path or other have a node

        Args:
            path (Path): the first path
            other (Path): the second path

        Returns:
            Array: the prepared path description for the intermediate path"""
        sp_lenghts, total, _ = EqualSubsegmentsInterpolator.get_subpath_lenghts(path)
        _, _, lenghts = EqualSubsegmentsInterpolator.get_subpath_lenghts(other)
        t = 0
        s = [[]]
        for sp in sp_lenghts:
            if not path[0]:
                s.append(path.pop(0))
            s[-1].append(path[0].pop(0))
            for l in sp:
                pt = t
                t += l / total
                if lenghts and t > lenghts[0]:
                    while lenghts and lenghts[0] < t:
                        nt = (lenghts[0] - pt) / (t - pt)
                        bezes = cspbezsplitatlength(s[-1][-1][:], path[0][0][:], nt)
                        s[-1][-1:] = bezes[:2]
                        path[0][0] = bezes[2]
                        pt = lenghts.pop(0)
                s[-1].append(path[0].pop(0))
        return s

    def __init__(self, start_path=Path(), end_path=Path()):
        super().__init__(start_path, end_path)
        # rediscretisize both paths
        start_copy = copy.deepcopy(self.start_value)
        # TODO find out why self.start_value.copy() doesn't work
        self.start_value = EqualSubsegmentsInterpolator.process_path(
            self.start_value, self.end_value
        )
        self.end_value = EqualSubsegmentsInterpolator.process_path(
            self.end_value, start_copy
        )

        self.truncate_subpaths()


class FirstNodesInterpolator(PathInterpolator):
    """Interpolates a path by discarding the trailing nodes of the longer subpath"""

    def __init__(self, start_path=Path(), end_path=Path()):
        super().__init__(start_path, end_path)
        # which path has fewer segments?
        lengthdiff = len(self.start_value) - len(self.end_value)
        # swap shortest first
        if lengthdiff > 0:
            self.start_value, self.end_value = self.end_value, self.start_value
        # subdivide the shorter path
        for _ in range(abs(lengthdiff)):
            maxlen = 0
            subpath = 0
            segment = 0
            for y, _ in enumerate(self.start_value):
                for z in range(1, len(self.start_value[y])):
                    leng = bezlenapprx(
                        self.start_value[y][z - 1], self.start_value[y][z]
                    )
                    if leng > maxlen:
                        maxlen = leng
                        subpath = y
                        segment = z
            sp1, sp2 = self.start_value[subpath][segment - 1 : segment + 1]
            self.start_value[subpath][segment - 1 : segment + 1] = cspbezsplit(sp1, sp2)
        # if swapped, swap them back
        if lengthdiff > 0:
            self.start_value, self.end_value = self.end_value, self.start_value
        self.truncate_subpaths()
