# coding=utf-8
#
# Copyright (C) 2018 - Martin Owens <doctormo@mgail.com>
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
Provide some documentation to existing extensions about why they're failing.
"""
#
# We ignore a lot of pylint warnings here:
#
# pylint: disable=invalid-name,unused-argument,missing-docstring,too-many-public-methods
#

import os
import sys
import warnings
import argparse

from ..transforms import Transform
from .. import utils
from .. import units
from ..elements._base import BaseElement, ShapeElement
from ..elements._selected import ElementList
from .meta import deprecate, _deprecated

warnings.simplefilter("default")
# To load each of the deprecated sub-modules (the ones without a namespace)
# we will add the directory to our pythonpath so older scripts can find them

INKEX_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
SIMPLE_DIR = os.path.join(INKEX_DIR, "deprecated-simple")

if os.path.isdir(SIMPLE_DIR):
    sys.path.append(SIMPLE_DIR)


class DeprecatedDict(dict):
    @deprecate
    def __getitem__(self, key):
        return super().__getitem__(key)

    @deprecate
    def __iter__(self):
        return super().__iter__()


# legacy inkex members


class lazyproxy:
    """Proxy, use as decorator on a function with provides the wrapped object.
    The decorated function is called when a member is accessed on the proxy.
    """

    def __init__(self, getwrapped):
        """
        :param getwrapped: Callable which returns the wrapped object
        """
        self._getwrapped = getwrapped

    def __getattr__(self, name):
        return getattr(self._getwrapped(), name)

    def __call__(self, *args, **kwargs):
        return self._getwrapped()(*args, **kwargs)


@lazyproxy
def localize():
    _deprecated("inkex.localize was moved to inkex.localization.localize.", stack=3)
    from ..localization import localize as wrapped

    return wrapped


def are_near_relative(a, b, eps):
    _deprecated(
        "inkex.are_near_relative was moved to " "inkex.units.are_near_relative", stack=2
    )
    return units.are_near_relative(a, b, eps)


def debug(what):
    _deprecated("inkex.debug was moved to inkex.utils.debug.", stack=2)
    return utils.debug(what)


# legacy inkex members <= 0.48.x


def unittouu(string):
    _deprecated(
        "inkex.unittouu is now a method in the SvgDocumentElement class. "
        "Use `self.svg.unittouu(str)` instead.",
        stack=2,
    )
    return units.convert_unit(string, "px")


# optparse.Values.ensure_value


def ensure_value(self, attr, value):
    _deprecated("Effect().options.ensure_value was removed.", stack=2)
    if getattr(self, attr, None) is None:
        setattr(self, attr, value)
    return getattr(self, attr)


argparse.Namespace.ensure_value = ensure_value  # type: ignore


@deprecate
def zSort(inNode, idList):
    """self.svg.get_z_selected()"""
    sortedList = []
    theid = inNode.get("id")
    if theid in idList:
        sortedList.append(theid)
    for child in inNode:
        if len(sortedList) == len(idList):
            break
        sortedList += zSort(child, idList)
    return sortedList


# This can't be handled as a mixin class because of circular importing.
def description(self, value):
    """Use elem.desc = value"""
    self.desc = value


BaseElement.description = deprecate(description, "1.1")


def composed_style(element: ShapeElement):
    """Calculate the final styles applied to this element
    This function has been deprecated in favor of BaseElement.specified_style()"""
    return element.specified_style()


ShapeElement.composed_style = deprecate(composed_style, "1.2")


def paint_order(selection: ElementList):
    """Use :func:`rendering_order`"""
    return selection.rendering_order()


ElementList.paint_order = deprecate(paint_order, "1.2")  # type: ignore


def transform_imul(self, matrix):
    """Use @= operator instead"""
    return self.__imatmul__(matrix)


def transform_mul(self, matrix):
    """Use @ operator instead"""
    return self.__matmul__(matrix)


Transform.__imul__ = deprecate(transform_imul, "1.2")  # type: ignore
Transform.__mul__ = deprecate(transform_mul, "1.2")  # type: ignore
