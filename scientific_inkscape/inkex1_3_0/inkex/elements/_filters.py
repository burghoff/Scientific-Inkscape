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
Element interface for patterns, filters, gradients and path effects.
"""
from __future__ import annotations
from typing import List, Tuple, TYPE_CHECKING, Optional

from lxml import etree

from ..utils import parse_percent

from ..transforms import Transform

from ..styles import Style

from ._utils import addNS
from ._base import BaseElement, ViewboxMixin
from ._groups import GroupBase
from ..units import convert_unit


if TYPE_CHECKING:
    from ._svg import SvgDocumentElement


class Filter(BaseElement):
    """A filter (usually in defs)"""

    tag_name = "filter"

    def add_primitive(self, fe_type, **args):
        """Create a filter primitive with the given arguments"""
        elem = etree.SubElement(self, addNS(fe_type, "svg"))
        elem.update(**args)
        return elem

    class Primitive(BaseElement):
        """Any filter primitive"""

    class Blend(Primitive):
        """Blend Filter element"""

        tag_name = "feBlend"

    class ColorMatrix(Primitive):
        """ColorMatrix Filter element"""

        tag_name = "feColorMatrix"

    class ComponentTransfer(Primitive):
        """ComponentTransfer Filter element"""

        tag_name = "feComponentTransfer"

    class Composite(Primitive):
        """Composite Filter element"""

        tag_name = "feComposite"

    class ConvolveMatrix(Primitive):
        """ConvolveMatrix Filter element"""

        tag_name = "feConvolveMatrix"

    class DiffuseLighting(Primitive):
        """DiffuseLightning Filter element"""

        tag_name = "feDiffuseLighting"

    class DisplacementMap(Primitive):
        """Flood Filter element"""

        tag_name = "feDisplacementMap"

    class Flood(Primitive):
        """DiffuseLightning Filter element"""

        tag_name = "feFlood"

    class GaussianBlur(Primitive):
        """GaussianBlur Filter element"""

        tag_name = "feGaussianBlur"

    class Image(Primitive):
        """Image Filter element"""

        tag_name = "feImage"

    class Merge(Primitive):
        """Merge Filter element"""

        tag_name = "feMerge"

    class Morphology(Primitive):
        """Morphology Filter element"""

        tag_name = "feMorphology"

    class Offset(Primitive):
        """Offset Filter element"""

        tag_name = "feOffset"

    class SpecularLighting(Primitive):
        """SpecularLighting Filter element"""

        tag_name = "feSpecularLighting"

    class Tile(Primitive):
        """Tile Filter element"""

        tag_name = "feTile"

    class Turbulence(Primitive):
        """Turbulence Filter element"""

        tag_name = "feTurbulence"


class Stop(BaseElement):
    """Gradient stop

    .. versionadded:: 1.1"""

    tag_name = "stop"

    @property
    def offset(self) -> float:
        """The offset of the gradient stop"""
        value = self.get("offset", default="0")
        return parse_percent(value)

    @offset.setter
    def offset(self, number):
        self.set("offset", number)

    def interpolate(self, other, fraction):
        """Interpolate gradient stops"""
        from ..tween import StopInterpolator

        return StopInterpolator(self, other).interpolate(fraction)


class Pattern(BaseElement, ViewboxMixin):
    """Pattern element which is used in the def to control repeating fills"""

    tag_name = "pattern"
    WRAPPED_ATTRS = BaseElement.WRAPPED_ATTRS + (("patternTransform", Transform),)

    def get_fallback(self, prop, default="0"):
        val = self.get(prop, None)
        if val is None:
            if isinstance(self.href, Pattern):
                return getattr(self.href, prop)
            val = default
        return val

    x = property(lambda self: self.get_fallback("x"))
    y = property(lambda self: self.get_fallback("y"))
    width = property(lambda self: self.get_fallback("width"))
    height = property(lambda self: self.get_fallback("height"))
    patternUnits = property(
        lambda self: self.get_fallback("patternUnits", "objectBoundingBox")
    )

    def get_viewbox(self) -> Optional[List[float]]:
        """Get the viewbox of the pattern, falling back to the href's viewbox

        .. versionadded:: 1.3"""
        vbox = self.get("viewBox", None)
        if vbox is None:
            if isinstance(self.href, Pattern):
                return self.href.get_viewbox()
        return self.parse_viewbox(vbox)

    def get_effective_parent(self, depth=0, maxDepth=10):
        """If a pattern has no children, but a href, it uses the children from the href.
        Avoids infinite recursion.

        .. versionadded:: 1.3"""
        if (
            len(self) == 0
            and self.href is not None
            and isinstance(self.href, Pattern)
            and depth < maxDepth
        ):
            return self.href.get_effective_parent(depth + 1, maxDepth)
        return self


class Mask(GroupBase):
    """A structural object that serves as opacity mask

    .. versionadded:: 1.3"""

    tag_name = "mask"

    def get_fallback(self, prop, default="0"):
        return self.to_dimensionless(self.get(prop, default))

    x = property(lambda self: self.get_fallback("x"))
    y = property(lambda self: self.get_fallback("y"))
    width = property(lambda self: self.get_fallback("width"))
    height = property(lambda self: self.get_fallback("height"))
    maskUnits = property(lambda self: self.get("maskUnits", "objectBoundingBox"))


class Gradient(BaseElement):
    """A gradient instruction usually in the defs."""

    WRAPPED_ATTRS = BaseElement.WRAPPED_ATTRS + (("gradientTransform", Transform),)
    """Additional to the :attr:`~inkex.elements._base.BaseElement.WRAPPED_ATTRS` of 
    :class:`~inkex.elements._base.BaseElement`, ``gradientTransform`` is wrapped."""

    orientation_attributes = ()  # type: Tuple[str, ...]
    """
    .. versionadded:: 1.1
    """

    @property
    def stops(self):
        """Return an ordered list of own or linked stop nodes

        .. versionadded:: 1.1"""
        gradcolor = (
            self.href
            if isinstance(self.href, (LinearGradient, RadialGradient))
            else self
        )
        return [child for child in gradcolor if isinstance(child, Stop)]

    @property
    def stop_offsets(self):
        # type: () -> List[float]
        """Return a list of own or linked stop offsets

        .. versionadded:: 1.1"""
        return [child.offset for child in self.stops]

    @property
    def stop_styles(self):  # type: () -> List[Style]
        """Return a list of own or linked offset styles

        .. versionadded:: 1.1"""
        return [child.style for child in self.stops]

    def remove_orientation(self):
        """Remove all orientation attributes from this element

        .. versionadded:: 1.1"""
        for attr in self.orientation_attributes:
            self.pop(attr)

    def interpolate(
        self,
        other: LinearGradient,
        fraction: float,
        svg: Optional[SvgDocumentElement] = None,
    ):
        """Interpolate with another gradient.

        .. versionadded:: 1.1"""
        from ..tween import GradientInterpolator

        return GradientInterpolator(self, other, svg).interpolate(fraction)

    def stops_and_orientation(self):
        """Return a copy of all the stops in this gradient

        .. versionadded:: 1.1"""
        stops = self.copy()
        stops.remove_orientation()
        orientation = self.copy()
        orientation.remove_all(Stop)
        return stops, orientation

    def get_percentage_parsed_unit(self, attribute, value, svg=None):
        """Parses an attribute of a gradient, respecting percentage values of
        "userSpaceOnUse" as percentages of document size. See
        https://www.w3.org/TR/SVG2/pservers.html#LinearGradientAttributes for details

        .. versionadded:: 1.3"""
        if isinstance(value, (float, int)):
            return value
        value = value.strip()
        if len(value) > 0 and value[-1] == "%":
            try:
                value = float(value.strip()[0:-1]) / 100.0
                gradientunits = self.get("gradientUnits", "objectBoundingBox")
                if gradientunits == "userSpaceOnUse":
                    if svg is None:
                        raise ValueError("Need root SVG to determine percentage value")
                    bbox = svg.get_page_bbox()
                    if attribute in ("cx", "fx", "x1", "x2"):
                        return bbox.width * value
                    if attribute in ("cy", "fy", "y1", "y2"):
                        return bbox.height * value
                    if attribute in ("r"):
                        return bbox.diagonal_length * value
                if gradientunits == "objectBoundingBox":
                    return value
            except ValueError:
                value = None
        return convert_unit(value, "px")

    def _get_or_href(self, attr, default, svg=None):
        val = self.get(attr)
        if val is None:
            if type(self.href) is type(self):
                return getattr(self.href, attr)()
            val = default
        return self.get_percentage_parsed_unit(attr, val, svg)


class LinearGradient(Gradient):
    """LinearGradient element"""

    tag_name = "linearGradient"
    orientation_attributes = ("x1", "y1", "x2", "y2")
    """
    .. versionadded:: 1.1
    """

    def apply_transform(self):  # type: () -> None
        """Apply transform to orientation points and set it to identity.
        .. versionadded:: 1.1
        """
        trans = self.pop("gradientTransform")
        pt1 = (
            self.to_dimensionless(self.get("x1")),
            self.to_dimensionless(self.get("y1")),
        )
        pt2 = (
            self.to_dimensionless(self.get("x2")),
            self.to_dimensionless(self.get("y2")),
        )
        p1t = trans.apply_to_point(pt1)
        p2t = trans.apply_to_point(pt2)
        self.update(
            x1=self.to_dimensionless(p1t[0]),
            y1=self.to_dimensionless(p1t[1]),
            x2=self.to_dimensionless(p2t[0]),
            y2=self.to_dimensionless(p2t[1]),
        )

    def x1(self, svg=None):
        """Get the x1 attribute

        .. versionadded:: 1.3"""
        return self._get_or_href("x1", "0%", svg)

    def x2(self, svg=None):
        """Get the x2 attribute

        .. versionadded:: 1.3"""
        return self._get_or_href("x2", "100%", svg)

    def y1(self, svg=None):
        """Get the y1 attribute

        .. versionadded:: 1.3"""
        return self._get_or_href("y1", "0%", svg)

    def y2(self, svg=None):
        """Get the y2 attribute

        .. versionadded:: 1.3"""
        return self._get_or_href("y2", "0%", svg)


class RadialGradient(Gradient):
    """RadialGradient element"""

    tag_name = "radialGradient"
    orientation_attributes = ("cx", "cy", "fx", "fy", "r")
    """
    .. versionadded:: 1.1
    """

    def apply_transform(self):  # type: () -> None
        """Apply transform to orientation points and set it to identity.

        .. versionadded:: 1.1
        """
        trans = self.pop("gradientTransform")
        pt1 = (
            self.to_dimensionless(self.get("cx")),
            self.to_dimensionless(self.get("cy")),
        )
        pt2 = (
            self.to_dimensionless(self.get("fx")),
            self.to_dimensionless(self.get("fy")),
        )
        p1t = trans.apply_to_point(pt1)
        p2t = trans.apply_to_point(pt2)
        self.update(
            cx=self.to_dimensionless(p1t[0]),
            cy=self.to_dimensionless(p1t[1]),
            fx=self.to_dimensionless(p2t[0]),
            fy=self.to_dimensionless(p2t[1]),
        )

    def cx(self, svg=None):
        """Get the effective cx (horizontal center) attribute in user units

        .. versionadded:: 1.3"""
        return self._get_or_href("cx", "50%", svg)

    def cy(self, svg=None):
        """Get the effective cy (vertical center) attribute in user units

        .. versionadded:: 1.3"""
        return self._get_or_href("cy", "50%", svg)

    def fx(self, svg=None):
        """Get the effective fx (horizontal focal point) attribute in user units

        .. versionadded:: 1.3"""
        return self._get_or_href("fx", self.cx(svg), svg)

    def fy(self, svg=None):
        """Get the effective fx (vertical focal point) attribute in user units

        .. versionadded:: 1.3"""
        return self._get_or_href("fy", self.cy(svg), svg)

    def r(self, svg=None):
        """Get the effective r (gradient radius) attribute in user units

        .. versionadded:: 1.3"""
        return self._get_or_href("r", "50%", svg)


class PathEffect(BaseElement):
    """Inkscape LPE element"""

    tag_name = "inkscape:path-effect"


class MeshGradient(Gradient):
    """Usable MeshGradient XML base class

    .. versionadded:: 1.1"""

    tag_name = "meshgradient"

    @classmethod
    def new_mesh(cls, pos=None, rows=1, cols=1, autocollect=True):
        """Return skeleton of 1x1 meshgradient definition."""
        # initial point
        if pos is None or len(pos) != 2:
            pos = [0.0, 0.0]
        # create nested elements for rows x cols mesh
        meshgradient = cls()
        for _ in range(rows):
            meshrow: BaseElement = meshgradient.add(MeshRow())
            for _ in range(cols):
                meshrow.append(MeshPatch())
        # set meshgradient attributes
        meshgradient.set("gradientUnits", "userSpaceOnUse")
        meshgradient.set("x", pos[0])
        meshgradient.set("y", pos[1])
        if autocollect:
            meshgradient.set("inkscape:collect", "always")
        return meshgradient


class MeshRow(BaseElement):
    """Each row of a mesh gradient

    .. versionadded:: 1.1"""

    tag_name = "meshrow"


class MeshPatch(BaseElement):
    """Each column or 'patch' in a mesh gradient

    .. versionadded:: 1.1"""

    tag_name = "meshpatch"

    def stops(self, edges, colors):
        """Add or edit meshpatch stops with path and stop-color."""
        # iterate stops based on number of edges (path data)
        for i, edge in enumerate(edges):
            if i < len(self):
                stop = self[i]
            else:
                stop = self.add(Stop())

            # set edge path data
            stop.set("path", str(edge))
            # set stop color
            stop.style["stop-color"] = str(colors[i % 2])
