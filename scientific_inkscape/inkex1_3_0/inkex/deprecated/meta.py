# coding=utf-8
#
# Copyright (C) 2018 - Martin Owens <doctormo@gmail.com>
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
Deprecation functionality which does not require imports from Inkex.
"""

import os
import traceback
import warnings
from typing import Optional

try:
    DEPRECATION_LEVEL = int(os.environ.get("INKEX_DEPRECATION_LEVEL", 1))
except ValueError:
    DEPRECATION_LEVEL = 1


def _deprecated(msg, stack=2, level=DEPRECATION_LEVEL):
    """Internal method for raising a deprecation warning"""
    if level > 1:
        msg += " ; ".join(traceback.format_stack())
    if level:
        warnings.warn(msg, category=DeprecationWarning, stacklevel=stack + 1)


def deprecate(func, version: Optional[str] = None):
    r"""Function decorator for deprecation functions which have a one-liner
    equivalent in the new API. The one-liner has to passed as a string
    to the decorator.

    >>> @deprecate
    >>> def someOldFunction(*args):
    >>>     '''Example replacement code someNewFunction('foo', ...)'''
    >>>     someNewFunction('foo', *args)

    Or if the args API is the same:

    >>> someOldFunction = deprecate(someNewFunction)

    """

    def _inner(*args, **kwargs):
        _deprecated(f"{func.__module__}.{func.__name__} -> {func.__doc__}", stack=2)
        return func(*args, **kwargs)

    _inner.__name__ = func.__name__
    if func.__doc__:
        if version is None:
            _inner.__doc__ = "Deprecated -> " + func.__doc__
        else:
            _inner.__doc__ = f"""{func.__doc__}\n\n.. deprecated:: {version}\n"""
    return _inner


class DeprecatedSvgMixin:
    """Mixin which adds deprecated API elements to the SvgDocumentElement"""

    @property
    def selected(self):
        """svg.selection"""
        return self.selection

    @deprecate
    def set_selected(self, *ids):
        r"""svg.selection.set(\*ids)"""
        return self.selection.set(*ids)

    @deprecate
    def get_z_selected(self):
        """svg.selection.rendering_order()"""
        return self.selection.rendering_order()

    @deprecate
    def get_selected(self, *types):
        r"""svg.selection.filter(\*types).values()"""
        return self.selection.filter(*types).values()

    @deprecate
    def get_selected_or_all(self, *types):
        """Set select_all = True in extension class"""
        if not self.selection:
            self.selection.set_all()
        return self.selection.filter(*types)

    @deprecate
    def get_selected_bbox(self):
        """selection.bounding_box()"""
        return self.selection.bounding_box()

    @deprecate
    def get_first_selected(self, *types):
        r"""selection.filter(\*types).first() or [0] if you'd like an error"""
        return self.selection.filter(*types).first()
