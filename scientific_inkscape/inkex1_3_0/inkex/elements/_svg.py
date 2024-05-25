# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 Martin Owens <doctormo@gmail.com>
#                    Thomas Holder <thomas.holder@schrodinger.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Windell Oskay <windell@oskay.net>
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
# pylint: disable=attribute-defined-outside-init
#
"""
Provide a way to load lxml attributes with an svg API on top.
"""

import random
import math
import re

from lxml import etree

from ..css import ConditionalRule
from ..interfaces.IElement import ISVGDocumentElement

from ..deprecated.meta import DeprecatedSvgMixin, deprecate
from ..units import discover_unit, parse_unit
from ._selected import ElementList
from ..transforms import BoundingBox
from ..styles import StyleSheets

from ._base import BaseElement, ViewboxMixin
from ._meta import StyleElement, NamedView
from ._utils import registerNS

from typing import Optional, List, Tuple

if False:  # pylint: disable=using-constant-test
    import typing  # pylint: disable=unused-import


class SvgDocumentElement(
    DeprecatedSvgMixin, ISVGDocumentElement, BaseElement, ViewboxMixin
):
    """Provide access to the document level svg functionality"""

    # pylint: disable=too-many-public-methods
    tag_name = "svg"

    selection: ElementList
    """The selection as passed by Inkscape (readonly)"""

    def _init(self):
        self.current_layer = None
        self.view_center = (0.0, 0.0)
        self.selection = ElementList(self)
        self.ids = {}

    def tostring(self):
        """Convert document to string"""
        return etree.tostring(etree.ElementTree(self))

    def get_ids(self):
        """Returns a set of unique document ids"""
        if not self.ids:
            self.ids = set(self.xpath("//@id"))
        return self.ids

    def get_unique_id(
        self,
        prefix: str,
        size: Optional[int] = None,
        blacklist: Optional[List[str]] = None,
    ):
        """Generate a new id from an existing old_id

        The id consists of a prefix and an appended random integer with size digits.

        If size is not given, it is determined automatically from the length of
        existing ids, i.e. those in the document plus those in the blacklist.

        Args:
            prefix (str): the prefix of the new ID.
            size (Optional[int], optional): number of digits of the second part of the
                id. If None, the length is chosen based on the amount of existing
                objects. Defaults to None.

                .. versionchanged:: 1.1
                    The default of this parameter has been changed from 4 to None.
            blacklist (Optional[Iterable[str]], optional): An additional iterable of ids
                that are not allowed to be used. This is useful when bulk inserting
                objects.
                Defaults to None.

                .. versionadded:: 1.2

        Returns:
            _type_: _description_
        """
        ids = self.get_ids()
        if size is None:
            size = max(math.ceil(math.log10(len(ids) or 1000)) + 1, 4)
        if blacklist is not None:
            ids.update(blacklist)
        new_id = None
        _from = 10**size - 1
        _to = 10**size
        while new_id is None or new_id in ids:
            # Do not use randint because py2/3 incompatibility
            new_id = prefix + str(int(random.random() * _from - _to) + _to)
        self.ids.add(new_id)
        return new_id

    def get_page_bbox(self, page=None) -> BoundingBox:
        """Gets the page dimensions as a bbox. For single-page documents, the viewbox
        dimensions are returned.

        Args:
            page (int, optional): Page number. Defaults to the first page.

                .. versionadded:: 1.3

        Raises:
            IndexError: if the page number provided does not exist in the document.

        Returns:
            BoundingBox: the bounding box of the page
        """
        if page is None:
            page = 0
        pages = self.namedview.get_pages()
        if 0 <= page < len(pages):
            return pages[page].bounding_box
        raise IndexError("Invalid page number")

    def get_current_layer(self):
        """Returns the currently selected layer"""
        layer = self.getElementById(self.namedview.current_layer, "svg:g")
        if layer is None:
            return self
        return layer

    def add_namespace(self, prefix, url):
        """Adds an xml namespace to the xml parser with the desired prefix.

        If the prefix or url are already in use with different values, this
        function will raise an error. Remove any attributes or elements using
        this namespace before calling this function in order to rename it.

        .. versionadded:: 1.3
        """
        if self.nsmap.get(prefix, None) == url:
            registerNS(prefix, url)
            return

        # Attempt to clean any existing namespaces
        if prefix in self.nsmap or url in self.nsmap.values():
            nskeep = [k for k, v in self.nsmap.items() if k != prefix and v != url]
            etree.cleanup_namespaces(self, keep_ns_prefixes=nskeep)
            if prefix in self.nsmap:
                raise KeyError("ns prefix already used with a different url")
            if url in self.nsmap.values():
                raise ValueError("ns url already used with a different prefix")

        # These are globals, but both will overwrite previous uses.
        registerNS(prefix, url)
        etree.register_namespace(prefix, url)

        # Set and unset an attribute to add the namespace to this root element.
        self.set(f"{prefix}:temp", "1")
        self.set(f"{prefix}:temp", None)

    def getElement(self, xpath):  # pylint: disable=invalid-name
        """Gets a single element from the given xpath or returns None"""
        return self.findone(xpath)

    def getElementById(
        self, eid: str, elm="*", literal=False
    ):  # pylint: disable=invalid-name
        """Get an element in this svg document by it's ID attribute.

        Args:
            eid (str): element id
            elm (str, optional): element type, including namespace, e.g. ``svg:path``.
                Defaults to "*".
            literal (bool, optional): If ``False``, ``#url()`` is stripped from ``eid``.
                Defaults to False.

                .. versionadded:: 1.1

        Returns:
            Union[BaseElement, None]: found element
        """
        if eid is not None and not literal:
            eid = eid.strip()[4:-1] if eid.startswith("url(") else eid
            eid = eid.lstrip("#")
        return self.getElement(f'//{elm}[@id="{eid}"]')

    def getElementByName(self, name, elm="*"):  # pylint: disable=invalid-name
        """Get an element by it's inkscape:label (aka name)"""
        return self.getElement(f'//{elm}[@inkscape:label="{name}"]')

    def getElementsByClass(self, class_name):  # pylint: disable=invalid-name
        """Get elements by it's class name"""

        return self.xpath(ConditionalRule(f".{class_name}").to_xpath())

    def getElementsByHref(
        self, eid: str, attribute="href"
    ):  # pylint: disable=invalid-name
        """Get elements that reference the element with id eid.

        Args:
            eid (str): _description_
            attribute (str, optional): Attribute to look for.
                Valid choices: "href", "xlink:href", "mask", "clip-path".
                Defaults to "href".

                .. versionadded:: 1.2

            attribute set to "href" or "xlink:href" handles both cases.
                .. versionchanged:: 1.3

        Returns:
            Any: list of elements
        """
        if attribute == "href" or attribute == "xlink:href":
            return self.xpath(f'//*[@href|@xlink:href="#{eid}"]')
        elif attribute == "mask":
            return self.xpath(f'//*[@mask="url(#{eid})"]')
        elif attribute == "clip-path":
            return self.xpath(f'//*[@clip-path="url(#{eid})"]')

    def getElementsByStyleUrl(self, eid, style=None):  # pylint: disable=invalid-name
        """Get elements by a style attribute url"""
        url = f"url(#{eid})"
        if style is not None:
            url = style + ":" + url
        return self.xpath(f'//*[contains(@style,"{url}")]')

    @property
    def name(self):
        """Returns the Document Name"""
        return self.get("sodipodi:docname", "")

    @property
    def namedview(self) -> NamedView:
        """Return the sp namedview meta information element"""
        return self.get_or_create("//sodipodi:namedview", prepend=True)

    @property
    def metadata(self):
        """Return the svg metadata meta element container"""
        return self.get_or_create("//svg:metadata", prepend=True)

    @property
    def defs(self):
        """Return the svg defs meta element container"""
        return self.get_or_create("//svg:defs", prepend=True)

    def get_viewbox(self) -> List[float]:
        """Parse and return the document's viewBox attribute"""
        return self.parse_viewbox(self.get("viewBox", "0")) or [0, 0, 0, 0]

    @property
    def viewbox_width(self) -> float:  # getDocumentWidth(self):
        """Returns the width of the `user coordinate system
        <https://www.w3.org/TR/SVG2/coords.html#Introduction>`_ in user units, i.e.
        the width of the viewbox, as defined in the SVG file. If no viewbox is defined,
        the value of the width attribute is returned. If the height is not defined,
        returns 0.

        .. versionadded:: 1.2"""
        return self.get_viewbox()[2] or self.viewport_width

    @property
    def viewport_width(self) -> float:
        """Returns the width of the `viewport coordinate system
        <https://www.w3.org/TR/SVG2/coords.html#Introduction>`_ in user units, i.e. the
        width attribute of the svg element converted to px

        .. versionadded:: 1.2"""
        return self.to_dimensionless(self.get("width")) or self.get_viewbox()[2]

    @property
    def viewbox_height(self) -> float:  # getDocumentHeight(self):
        """Returns the height of the `user coordinate system
        <https://www.w3.org/TR/SVG2/coords.html#Introduction>`_ in user units, i.e. the
        height of the viewbox, as defined in the SVG file. If no viewbox is defined, the
        value of the height attribute is returned. If the height is not defined,
        returns 0.

        .. versionadded:: 1.2"""
        return self.get_viewbox()[3] or self.viewport_height

    @property
    def viewport_height(self) -> float:
        """Returns the width of the `viewport coordinate system
        <https://www.w3.org/TR/SVG2/coords.html#Introduction>`_ in user units, i.e. the
        height attribute of the svg element converted to px

        .. versionadded:: 1.2"""
        return self.to_dimensionless(self.get("height")) or self.get_viewbox()[3]

    @property
    def scale(self):
        """Returns the ratio between the viewBox width and the page width.

        .. versionchanged:: 1.2
            Previously, the scale as shown by the document properties was computed,
            but the computation of this in core Inkscape changed in Inkscape 1.2, so
            this was moved to :attr:`inkscape_scale`."""
        return self._base_scale()

    @property
    def inkscape_scale(self):
        """Returns the ratio between the viewBox width (in width/height units) and the
        page width, which is displayed as "scale" in the Inkscape document
        properties.

        .. versionadded:: 1.2"""

        viewbox_unit = (
            parse_unit(self.get("width")) or parse_unit(self.get("height")) or (0, "px")
        )[1]
        return self._base_scale(viewbox_unit)

    def _base_scale(self, unit="px"):
        """Returns what Inkscape shows as "user units per `unit`"

        .. versionadded:: 1.2"""
        try:
            scale_x = (
                self.to_dimensional(self.viewport_width, unit) / self.viewbox_width
            )
            scale_y = (
                self.to_dimensional(self.viewport_height, unit) / self.viewbox_height
            )
            value = max([scale_x, scale_y])
            return 1.0 if value == 0 else value
        except (ValueError, ZeroDivisionError):
            return 1.0

    @property
    def equivalent_transform_scale(self) -> float:
        """Return the scale of the equivalent transform of the svg tag, as defined by
        https://www.w3.org/TR/SVG2/coords.html#ComputingAViewportsTransform
        (highly simplified)

        .. versionadded:: 1.2"""
        return self.scale

    @property
    def unit(self):
        """Returns the unit used for in the SVG document.
        In the case the SVG document lacks an attribute that explicitly
        defines what units are used for SVG coordinates, it tries to calculate
        the unit from the SVG width and viewBox attributes.
        Defaults to 'px' units."""
        if not hasattr(self, "_unit"):
            self._unit = "px"  # Default is px
            viewbox = self.get_viewbox()
            if viewbox and set(viewbox) != {0}:
                self._unit = discover_unit(self.get("width"), viewbox[2], default="px")
        return self._unit

    @property
    def document_unit(self):
        """Returns the display unit (Inkscape-specific attribute) of the document

        .. versionadded:: 1.2"""
        return self.namedview.get("inkscape:document-units", "px")

    @property
    def stylesheets(self):
        """Get all the stylesheets, bound together to one, (for reading)"""
        sheets = StyleSheets(self)
        for node in self.xpath("//svg:style"):
            sheets.append(node.stylesheet())
        return sheets

    @property
    def stylesheet(self):
        """Return the first stylesheet or create one if needed (for writing)"""
        for sheet in self.stylesheets:
            return sheet

        style_node = StyleElement()
        self.defs.append(style_node)
        return style_node.stylesheet()


def width(self):
    """Use :func:`viewport_width` instead"""
    return self.viewport_width


def height(self):
    """Use :func:`viewport_height` instead"""
    return self.viewport_height


SvgDocumentElement.width = property(deprecate(width, "1.2"))
SvgDocumentElement.height = property(deprecate(height, "1.2"))
