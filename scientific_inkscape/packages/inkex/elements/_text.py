# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 Martin Owens <doctormo@gmail.com>
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
Provide text based element classes interface.

Because text is not rendered at all, no information about a text's path
size or actual location can be generated yet.
"""
from __future__ import annotations

from tempfile import TemporaryDirectory

from ..interfaces.IElement import BaseElementProtocol
from ..paths import Path
from ..transforms import Transform, BoundingBox
from ..command import inkscape, write_svg
from ._base import BaseElement, ShapeElement
from ._polygons import PathElementBase


class TextBBMixin:  # pylint: disable=too-few-public-methods
    """Mixin to query the bounding box from Inkscape

    .. versionadded:: 1.2"""

    def get_inkscape_bbox(self: BaseElementProtocol) -> BoundingBox:
        """Query the bbbox of a single object. This calls the Inkscape command,
        so it is rather slow to use in a loop."""
        with TemporaryDirectory(prefix="inkscape-command") as tmpdir:
            svg_file = write_svg(self.root, tmpdir, "input.svg")
            out = inkscape(svg_file, "-X", "-Y", "-W", "-H", query_id=self.get_id())
            out = list(map(self.root.viewport_to_unit, out.splitlines()))
            if len(out) != 4:
                raise ValueError("Error: Bounding box computation failed")
            return BoundingBox.new_xywh(*out)


class FlowRegion(ShapeElement):
    """SVG Flow Region (SVG 2.0)"""

    tag_name = "flowRegion"

    def get_path(self):
        # This ignores flowRegionExcludes
        return sum([child.path for child in self], Path())


class FlowRoot(ShapeElement, TextBBMixin):
    """SVG Flow Root (SVG 2.0)"""

    tag_name = "flowRoot"

    @property
    def region(self):
        """Return the first flowRegion in this flowRoot"""
        return self.findone("svg:flowRegion")

    def get_path(self):
        region = self.region
        return region.get_path() if region is not None else Path()


class FlowPara(ShapeElement):
    """SVG Flow Paragraph (SVG 2.0)"""

    tag_name = "flowPara"

    def get_path(self):
        # XXX: These empty paths mean the bbox for text elements will be nothing.
        return Path()


class FlowDiv(ShapeElement):
    """SVG Flow Div (SVG 2.0)"""

    tag_name = "flowDiv"

    def get_path(self):
        # XXX: These empty paths mean the bbox for text elements will be nothing.
        return Path()


class FlowSpan(ShapeElement):
    """SVG Flow Span (SVG 2.0)"""

    tag_name = "flowSpan"

    def get_path(self):
        # XXX: These empty paths mean the bbox for text elements will be nothing.
        return Path()


class TextElement(ShapeElement, TextBBMixin):
    """A Text element"""

    tag_name = "text"
    x = property(lambda self: self.to_dimensionless(self.get("x", 0)))
    y = property(lambda self: self.to_dimensionless(self.get("y", 0)))

    def get_path(self):
        return Path()

    def tspans(self):
        """Returns all children that are tspan elements"""
        return self.findall("svg:tspan")

    def get_text(self, sep="\n"):
        """Return the text content including tspans"""
        nodes = [self] + list(self.tspans())
        return sep.join([elem.text for elem in nodes if elem.text is not None])

    def shape_box(self, transform=None):
        """
        Returns a horrible bounding box that just contains the coord points
        of the text without width or height (which is impossible to calculate)
        """
        effective_transform = Transform(transform) @ self.transform
        x, y = effective_transform.apply_to_point((self.x, self.y))
        bbox = BoundingBox(x, y)
        for tspan in self.tspans():
            bbox += tspan.bounding_box(effective_transform)
        return bbox


class TextPath(ShapeElement, TextBBMixin):
    """A textPath element"""

    tag_name = "textPath"

    def get_path(self):
        return Path()


class Tspan(ShapeElement, TextBBMixin):
    """A tspan text element"""

    tag_name = "tspan"
    x = property(lambda self: self.to_dimensionless(self.get("x", 0)))
    y = property(lambda self: self.to_dimensionless(self.get("y", 0)))

    @classmethod
    def superscript(cls, text):
        """Adds a superscript tspan element"""
        return cls(text, style="font-size:65%;baseline-shift:super")

    def get_path(self):
        return Path()

    def shape_box(self, transform=None):
        """
        Returns a horrible bounding box that just contains the coord points
        of the text without width or height (which is impossible to calculate)
        """
        effective_transform = Transform(transform) @ self.transform
        x1, y1 = effective_transform.apply_to_point((self.x, self.y))
        fontsize = self.to_dimensionless(self.style.get("font-size", "12px"))
        x2 = self.x + 0  # XXX This is impossible to calculate!
        y2 = self.y + float(fontsize)
        x2, y2 = effective_transform.apply_to_point((x2, y2))
        return BoundingBox((x1, x2), (y1, y2))


class SVGfont(BaseElement):
    """An svg font element"""

    tag_name = "font"


class FontFace(BaseElement):
    """An svg font font-face element"""

    tag_name = "font-face"


class Glyph(PathElementBase):
    """An svg font glyph element"""

    tag_name = "glyph"


class MissingGlyph(BaseElement):
    """An svg font missing-glyph element"""

    tag_name = "missing-glyph"
