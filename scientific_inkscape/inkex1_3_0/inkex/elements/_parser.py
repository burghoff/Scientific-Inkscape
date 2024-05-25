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

"""Utilities for parsing SVG documents.

.. versionadded:: 1.2
    Separated out from :py:mod:`inkex.elements._base`"""

from collections import defaultdict
from typing import DefaultDict, List, Any, Type

from lxml import etree

from ..interfaces.IElement import IBaseElement

from ._utils import splitNS
from ..utils import errormsg
from ..localization import inkex_gettext as _


class NodeBasedLookup(etree.PythonElementClassLookup):
    """
    We choose what kind of Elements we should return for each element, providing useful
    SVG based API to our extensions system.
    """

    default: Type[IBaseElement]

    # (ns,tag) -> list(cls) ; ascending priority
    lookup_table = defaultdict(list)  # type: DefaultDict[str, List[Any]]

    @classmethod
    def register_class(cls, klass):
        """Register the given class using it's attached tag name"""
        cls.lookup_table[splitNS(klass.tag_name)].append(klass)

    @classmethod
    def find_class(cls, xpath):
        """Find the class for this type of element defined by an xpath

        .. versionadded:: 1.1"""
        if isinstance(xpath, type):
            return xpath
        for kls in cls.lookup_table[splitNS(xpath.split("/")[-1])]:
            # TODO: We could create a apply the xpath attrs to the test element
            # to narrow the search, but this does everything we need right now.
            test_element = kls()
            if kls.is_class_element(test_element):
                return kls
        raise KeyError(f"Could not find svg tag for '{xpath}'")

    def lookup(self, doc, element):  # pylint: disable=unused-argument
        """Lookup called by lxml when assigning elements their object class"""
        try:
            for kls in reversed(self.lookup_table[splitNS(element.tag)]):
                if kls.is_class_element(element):  # pylint: disable=protected-access
                    return kls
        except TypeError:
            # Handle non-element proxies case
            # The documentation implies that it's not possible
            # Didn't found a reliable way to check whether proxy corresponds to element
            # or not
            # Look like lxml issue to me.
            # The troubling element is "<!--Comment-->"
            return None
        return NodeBasedLookup.default


SVG_PARSER = etree.XMLParser(huge_tree=True, strip_cdata=False, recover=True)
SVG_PARSER.set_element_class_lookup(NodeBasedLookup())


def load_svg(stream):
    """Load SVG file using the SVG_PARSER"""
    if (isinstance(stream, str) and stream.lstrip().startswith("<")) or (
        isinstance(stream, bytes) and stream.lstrip().startswith(b"<")
    ):
        parsed = etree.ElementTree(etree.fromstring(stream, parser=SVG_PARSER))
    else:
        parsed = etree.parse(stream, parser=SVG_PARSER)
    if len(SVG_PARSER.error_log) > 0:
        errormsg(
            _(
                "A parsing error occurred, which means you are likely working with "
                "a non-conformant SVG file. The following errors were found:\n"
            )
        )
        for __, element in enumerate(SVG_PARSER.error_log):
            errormsg(
                _("{}. Line {}, column {}").format(
                    element.message, element.line, element.column
                )
            )
        errormsg(
            _(
                "\nProcessing will continue; however we encourage you to fix your"
                " file manually."
            )
        )
    return parsed
