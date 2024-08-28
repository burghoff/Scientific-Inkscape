# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 Martin Owens <doctormo@gmail.com>
#                    Maren Hachmann <moini>
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
Provide extra utility to each svg element type specific to its type.

This is useful for having a common interface for each element which can
give path, transform, and property access easily.
"""

from __future__ import annotations
import math

from typing import List, Optional

from lxml import etree

from inkex.deprecated.meta import deprecate

from ..styles import StyleSheet
from ..transforms import BoundingBox, Vector2d, VectorLike, DirectedLineSegment

from ._base import BaseElement


class Defs(BaseElement):
    """A header defs element, one per document"""

    tag_name = "defs"


class StyleElement(BaseElement):
    """A CSS style element containing multiple style definitions"""

    tag_name = "style"

    def set_text(self, content):
        """Sets the style content text as a CDATA section"""
        self.text = etree.CDATA(str(content))

    def stylesheet(self):
        """Return the StyleSheet() object for the style tag"""
        return StyleSheet(self.text, callback=self.set_text)


class Script(BaseElement):
    """A javascript tag in SVG"""

    tag_name = "script"

    def set_text(self, content):
        """Sets the style content text as a CDATA section"""
        self.text = etree.CDATA(str(content))


class Desc(BaseElement):
    """Description element"""

    tag_name = "desc"


class Title(BaseElement):
    """Title element"""

    tag_name = "title"


class NamedView(BaseElement):
    """The NamedView element is Inkscape specific metadata about the file"""

    tag_name = "sodipodi:namedview"

    current_layer = property(lambda self: self.get("inkscape:current-layer"))

    @property
    def center(self):
        """Returns view_center in terms of document units"""
        return Vector2d(
            self.root.viewport_to_unit(self.get("inkscape:cx") or 0),
            self.root.viewport_to_unit(self.get("inkscape:cy") or 0),
        )

    def get_guides(self):
        """Returns a list of guides"""
        return self.findall("sodipodi:guide")

    def add_guide(self, position, orient=True, name=None) -> Guide:
        """Creates a new guide in this namedview

        .. versionadded:: 1.3

        Args:
            position: a float containing the y position for ``orient is True``, or
                the x position for ``orient is False``. The position is specified in the
                post-1.0 coordinate system, i.e. y=0 is at the top left of the viewbox,
                positive y axis pointing down.

                Alternatively, the position may be given as Tuple (or VectorLike)
            orient: True for horizontal, False for Vertical

                alternatively: Tuple / Vector specifying x and y coordinates of the
                normal vector of the guide, or the (clockwise) angle between the
                horizontal axis and the guide. Defaults to True (horizontal)
            name: label of the guide

        Returns:
            the created guide"""
        elem = self.add(Guide())

        if orient is True:
            elem.set_position(0, position, (0, -1))
        elif orient is False:
            elem.set_position(position, self.root.viewbox_height, (1, 0))
        else:
            pos = Vector2d(position)
            elem.set_position(pos.x, pos.y, orient)
        if name:
            elem.set("inkscape:label", str(name))
        return elem

    @deprecate
    def new_guide(self, position, orient=True, name=None):
        """
        .. deprecated:: 1.3
            Use :func:`add_guide` instead.

        Creates a new guide in this namedview

        Args:
            position: a float containing the y position for ``orient is True``, or
                the x position for ``orient is False``

                .. versionchanged:: 1.2
                    Alternatively, the position may be given as Tuple (or VectorLike)
            orient: True for horizontal, False for Vertical

                .. versionchanged:: 1.2
                    Tuple / Vector specifying x and y coordinates of the normal vector
                    of the guide.
            name: label of the guide

        Returns:
            the created guide"""
        if orient is True:
            elem = Guide().move_to(0, position, (0, 1))
        elif orient is False:
            elem = Guide().move_to(position, 0, (1, 0))
        else:
            elem = Guide().move_to(*position, orient)
        if name:
            elem.set("inkscape:label", str(name))
        return self.add(elem)

    @deprecate
    def new_unique_guide(
        self, position: VectorLike, orientation: VectorLike
    ) -> Optional[Guide]:
        """
        .. deprecated:: 1.3
            Use :func:`add_unique_guide` instead.

        Add a guide iif there is no guide that looks the same.

        .. versionadded:: 1.2

        """
        elem = Guide().move_to(position[0], position[1], orientation)
        return self.add(elem) if self.get_similar_guide(elem) is None else None

    def add_unique_guide(
        self, position: VectorLike, orientation: VectorLike
    ) -> Optional[Guide]:
        """Add a guide iif there is no guide that looks the same.

        .. versionadded:: 1.3

        Args:
            position: Position as Tuple / Vector
            orientation: Tuple / Vector specifying x and y coordinates of the normal
                vector of the guide.
            name: label of the guide
        """
        elem = self.add(Guide()).set_position(position[0], position[1], orientation)
        if self.get_similar_guide(elem) is not None:
            self.remove(elem)
            return None
        return elem

    def get_similar_guide(self, other: Guide) -> Optional[Guide]:
        """Check if the namedview contains a guide that looks identical to one
        defined by (position, orientation) and is not identity (same element) as the
        first one. If such a guide exists, return it; otherwise, return None.

        .. versionadded:: 1.2"""
        for guide in self.get_guides():
            if Guide.guides_coincident(guide, other) and guide != other:
                return guide
        return None

    def _get_pages(self) -> List[Page]:
        """Returns all page elements"""
        return self.findall("inkscape:page")

    def _equivalent_page(self) -> Page:
        """Returns an unrooted page based on the viewbox dimensions"""
        return Page.new(self.root.viewbox_width, self.root.viewbox_height, 0, 0)

    def get_pages(self) -> List[Page]:
        """Returns a list of pages within the document. For single page documents,
        a detached page element with dimensions according to the viewbox will be
        returned.

        .. versionadded:: 1.2

        .. versionchanged:: 1.3
            For single-page documents, this function now returns the viewbox
            dimensions.
        """
        pages = self._get_pages()
        if len(pages) < 2:
            return [self._equivalent_page()]
        return pages

    def new_page(self, x, y, width, height, label=None):
        """Creates a new page in this namedview. Always add pages through this
        function to ensure that single-page documents are treated correctly.

        .. versionadded:: 1.2

        .. versionchanged:: 1.3
            If none exists, a page element with the viewbox dimensions will be
            inserted before the new page."""
        if len(self._get_pages()) == 0:
            self.add(self._equivalent_page())
        elem = Page(width=width, height=height, x=x, y=y)
        if label:
            elem.set("inkscape:label", str(label))
        return self.add(elem)


class Guide(BaseElement):
    """An inkscape guide"""

    tag_name = "sodipodi:guide"

    @property
    def orientation(self) -> Vector2d:
        """Vector normal to the guide, in the pre-1.0 coordinate system (y axis upwards)

        .. versionadded:: 1.2"""
        return Vector2d(self.get("orientation"), fallback=(1, 0))

    @property
    def angle(self) -> float:
        """(Clockwise) angle between the guide and the horizontal axis in degrees
        (i.e. what Inkscape 1.2+ shows as "Angle" in the guide properties)

        .. versionadded:: 1.3"""
        return math.degrees(math.atan2(*self.orientation))

    is_horizontal = property(
        lambda self: self.orientation[0] == 0 and self.orientation[1] != 0
    )
    is_vertical = property(
        lambda self: self.orientation[0] != 0 and self.orientation[1] == 0
    )

    @property
    def raw_position(self) -> Vector2d:
        """Position of the guide handle. The y coordinate is flipped and relative
        to the bottom of the viewbox, this is a remnant of the pre-1.0 coordinate system
        """
        return Vector2d(self.get("position"), fallback=(0, 0))

    def point(self):
        """Use raw_position or position instead"""
        return self.raw_position

    point = property(deprecate(point))  # type: ignore

    @property
    def position(self) -> Vector2d:
        """Position of the guide handle in normal coordinates, i.e. (0,0) is at
        the top left corner of the viewbox, positive y axis pointing downwards.

        This function can only be used for guides which are attached to a root
        svg element."""
        pos = self.raw_position
        return Vector2d(pos.x, self.root.viewbox_height - pos.y)

    @classmethod
    def new(cls, pos_x, pos_y, angle, **attrs):
        guide = super().new(**attrs)
        guide.set_position(pos_x, pos_y, angle=angle)
        return guide

    def set_position(self, pos_x, pos_y, angle=None):
        """
        Move this guide to the given x,y position and optionally set its orientation.
        The coordinate system used is the post-1.0 coordinate system (origin in the
        top left corner, y axis pointing down), which also defines the sense of
        rotation.

        The guide must be rooted for this function to be used. Preferably, use
        :func:`inkex.elements._meta.add_guide` to create a new guide.

        .. versionadded:: 1.3

        Args:
            pos_x (Union[str, int, float]): x position of the guide's reference point
            pos_y (Union[str, int, float]): y position of the guide's reference point
            angle (Union[str, float, int, tuple, list], optional): Angle may be a
                string, float or integer, which will set the clockwise angle between the
                horizontal axis and the guide.

                Alternatively, it may be a pair of numbers (tuple) which will be set
                as normal vector.

                If not given at all, the orientation remains unchanged.
                Defaults to None.

        Returns:
            Guide: the modified guide
        """
        pos_y = self.root.viewbox_height - float(pos_y)
        self.set("position", f"{float(pos_x):g},{float(pos_y):g}")
        if isinstance(angle, str):
            if "," not in angle:
                angle = float(angle)

        if isinstance(angle, (float, int)):
            # Generate orientation from angle
            angle = (math.sin(math.radians(angle)), -math.cos(math.radians(angle)))

        if isinstance(angle, (tuple, list)) and len(angle) == 2:
            angle = ",".join(f"{i:g}" for i in [angle[0], -angle[1]])

        if angle is not None:
            self.set("orientation", angle)
        return self

    @deprecate
    def move_to(self, pos_x, pos_y, angle=None):
        """
        .. deprecated:: 1.3
            Use :func:`set_position` instead.

        Move this guide to the given x,y position,

        Angle may be a float or integer, which will change the orientation. Alternately,
        it may be a pair of numbers (tuple) which will set the orientation directly.
        If not given at all, the orientation remains unchanged.
        """
        self.set("position", f"{float(pos_x):g},{float(pos_y):g}")
        if isinstance(angle, str):
            if "," not in angle:
                angle = float(angle)

        if isinstance(angle, (float, int)):
            # Generate orientation from angle
            angle = (math.sin(math.radians(angle)), -math.cos(math.radians(angle)))

        if isinstance(angle, (tuple, list)) and len(angle) == 2:
            angle = ",".join(f"{i:g}" for i in angle)

        if angle is not None:
            self.set("orientation", angle)
        return self

    @staticmethod
    def guides_coincident(guide1, guide2):
        """Check if two guides defined by (position, orientation) and (opos, oor) look
        identical (i.e. the position lies on the other guide AND the guide is
        (anti)parallel to the other guide).

        .. versionadded:: 1.2"""
        # normalize orientations first
        orientation = guide1.orientation / guide1.orientation.length
        oor = guide2.orientation / guide2.orientation.length

        position = guide1.raw_position
        opos = guide2.raw_position

        return (
            DirectedLineSegment(
                position, position + Vector2d(orientation[1], -orientation[0])
            ).perp_distance(*opos)
            < 1e-6
            and abs(abs(orientation[1] * oor[0]) - abs(orientation[0] * oor[1])) < 1e-6
        )


class Metadata(BaseElement):
    """Inkscape Metadata element"""

    tag_name = "metadata"


class ForeignObject(BaseElement):
    """SVG foreignObject element"""

    tag_name = "foreignObject"


class Switch(BaseElement):
    """A switch element"""

    tag_name = "switch"


class Grid(BaseElement):
    """A namedview grid child"""

    tag_name = "inkscape:grid"


class Page(BaseElement):
    """A namedview page child

    .. versionadded:: 1.2"""

    tag_name = "inkscape:page"

    width = property(lambda self: self.to_dimensionless(self.get("width") or 0))
    height = property(lambda self: self.to_dimensionless(self.get("height") or 0))
    x = property(lambda self: self.to_dimensionless(self.get("x") or 0))
    y = property(lambda self: self.to_dimensionless(self.get("y") or 0))

    @classmethod
    def new(cls, width, height, x, y):
        """Creates a new page element in the namedview"""
        page = super().new()
        page.move_to(x, y)
        page.set("width", width)
        page.set("height", height)
        return page

    def move_to(self, x, y):
        """Move this page to the given x,y position"""
        self.set("x", f"{float(x):g}")
        self.set("y", f"{float(y):g}")
        return self

    @property
    def bounding_box(self) -> BoundingBox:
        """Returns the bounding box of the page."""
        return BoundingBox(
            (self.x, self.x + self.width), (self.y, self.y + self.height)
        )
