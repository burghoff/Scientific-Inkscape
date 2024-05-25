# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 Martin Owens <doctormo@gmail.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Ryan Jarvis <ryan@shopboxretail.com>
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
Interface for all group based elements such as Groups, Use, Markers etc.
"""

from lxml import etree  # pylint: disable=unused-import

from ..paths import Path
from ..transforms import Transform

from ._utils import addNS
from ._base import ShapeElement, ViewboxMixin
from ._polygons import PathElement

try:
    from typing import Optional, List  # pylint: disable=unused-import
except ImportError:
    pass


class GroupBase(ShapeElement):
    """Base Group element"""

    def get_path(self):
        ret = Path()
        for child in self:
            if isinstance(child, ShapeElement):
                ret += child.path.transform(child.transform)
        return ret

    def shape_box(self, transform=None):
        bbox = None
        effective_transform = Transform(transform) @ self.transform
        for child in self:
            if isinstance(child, ShapeElement):
                child_bbox = child.bounding_box(transform=effective_transform)
                if child_bbox is not None:
                    bbox += child_bbox
        return bbox

    def bake_transforms_recursively(self, apply_to_paths=True):
        """Bake transforms, i.e. each leaf node has the effective transform (starting
        from this group) set, and parent transforms are removed.

        .. versionadded:: 1.4

        Args:
            apply_to_paths (bool, optional): For path elements, the
                path data is transformed with its effective transform. Nodes and handles
                will have the same position as before, but visual appearance of the
                stroke may change (stroke-width is not touched). Defaults to True.
        """
        # pylint: disable=attribute-defined-outside-init
        self.transform: Transform
        for element in self:
            if isinstance(element, PathElement) and apply_to_paths:
                element.path = element.path.transform(self.transform)
            else:
                element.transform = self.transform @ element.transform
                if isinstance(element, GroupBase):
                    element.bake_transforms_recursively(apply_to_paths)
        self.transform = None


class Group(GroupBase):
    """Any group element (layer or regular group)"""

    tag_name = "g"

    @classmethod
    def new(cls, label, *children, **attrs):
        attrs["inkscape:label"] = label
        return super().new(*children, **attrs)

    def effective_style(self):
        """A blend of each child's style mixed together (last child wins)"""
        style = self.style
        for child in self:
            style.update(child.effective_style())
        return style

    @property
    def groupmode(self):
        """Return the type of group this is"""
        return self.get("inkscape:groupmode", "group")


class Layer(Group):
    """Inkscape extension of svg:g"""

    def _init(self):
        self.set("inkscape:groupmode", "layer")

    @classmethod
    def is_class_element(cls, elem):
        # type: (etree.Element) -> bool
        return elem.attrib.get(addNS("inkscape:groupmode"), None) == "layer"


class Anchor(GroupBase):
    """An anchor or link tag"""

    tag_name = "a"

    @classmethod
    def new(cls, href, *children, **attrs):
        attrs["xlink:href"] = href
        return super().new(*children, **attrs)


class ClipPath(GroupBase):
    """A path used to clip objects"""

    tag_name = "clipPath"


class Marker(GroupBase, ViewboxMixin):
    """The <marker> element defines the graphic that is to be used for drawing
    arrowheads or polymarkers on a given <path>, <line>, <polyline> or <polygon>
    element."""

    tag_name = "marker"

    def get_viewbox(self) -> List[float]:
        """Returns the viewbox of the Marker, falling back to
        [0 0 markerWidth markerHeight]

        .. versionadded:: 1.3"""
        vbox = self.get("viewBox", None)
        result = self.parse_viewbox(vbox)
        if result is None:
            # use viewport, https://www.w3.org/TR/SVG11/painting.html#MarkerElement
            return [
                0,
                0,
                self.to_dimensionless(self.get("markerWidth")),
                self.to_dimensionless(self.get("markerHeight")),
            ]
        return result
