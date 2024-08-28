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
Deprecation functionality for the pre-1.0 Inkex main effect class.
"""
#
# We ignore a lot of pylint warnings here:
#
# pylint: disable=invalid-name,unused-argument,missing-docstring,too-many-public-methods
#

import sys
import argparse
from argparse import ArgumentParser

from .. import utils
from .. import base
from ..base import SvgThroughMixin, InkscapeExtension
from ..localization import inkex_gettext as _
from .meta import _deprecated


class DeprecatedEffect:
    """An Inkscape effect, takes SVG in and outputs SVG, providing a deprecated layer"""

    options = argparse.Namespace()

    def __init__(self):
        super().__init__()
        self._doc_ids = None
        self._args = None

        # These are things we reference in the deprecated code, they are provided
        # by the new effects code, but we want to keep this as a Mixin so these
        # items will keep pylint happy and let use check our code as we write.
        if not hasattr(self, "svg"):
            from ..elements import SvgDocumentElement

            self.svg = SvgDocumentElement()
        if not hasattr(self, "arg_parser"):
            self.arg_parser = ArgumentParser()
        if not hasattr(self, "run"):
            self.run = self.affect

    @classmethod
    def _deprecated(
        cls, name, msg=_("{} is deprecated and should be removed"), stack=3
    ):
        """Give the user a warning about their extension using a deprecated API"""
        _deprecated(
            msg.format("Effect." + name, cls=cls.__module__ + "." + cls.__name__),
            stack=stack,
        )

    @property
    def OptionParser(self):
        self._deprecated(
            "OptionParser",
            _(
                "{} or `optparse` has been deprecated and replaced with `argparser`. "
                "You must change `self.OptionParser.add_option` to "
                "`self.arg_parser.add_argument`; the arguments are similar."
            ),
        )
        return self

    def add_option(self, *args, **kw):
        # Convert type string into type method as needed
        if "type" in kw:
            kw["type"] = {
                "string": str,
                "int": int,
                "float": float,
                "inkbool": utils.Boolean,
            }.get(kw["type"])
        if kw.get("action", None) == "store":
            # Default store action not required, removed.
            kw.pop("action")
        args = [arg for arg in args if arg != ""]
        self.arg_parser.add_argument(*args, **kw)

    def effect(self):
        self._deprecated(
            "effect",
            _(
                "{} method is now a required method. It should "
                "be created on {cls}, even if it does nothing."
            ),
        )

    @property
    def current_layer(self):
        self._deprecated(
            "current_layer",
            _(
                "{} is now a method in the SvgDocumentElement class. "
                "Use `self.svg.get_current_layer()` instead."
            ),
        )
        return self.svg.get_current_layer()

    @property
    def view_center(self):
        self._deprecated(
            "view_center",
            _(
                "{} is now a method in the SvgDocumentElement class. "
                "Use `self.svg.get_center_position()` instead."
            ),
        )
        return self.svg.namedview.center

    @property
    def selected(self):
        self._deprecated(
            "selected",
            _(
                "{} is now a dict in the SvgDocumentElement class. "
                "Use `self.svg.selected`."
            ),
        )
        return {elem.get("id"): elem for elem in self.svg.selected}

    @property
    def doc_ids(self):
        self._deprecated(
            "doc_ids",
            _(
                "{} is now a method in the SvgDocumentElement class. "
                "Use `self.svg.get_ids()` instead."
            ),
        )
        if self._doc_ids is None:
            self._doc_ids = dict.fromkeys(self.svg.get_ids())
        return self._doc_ids

    def getdocids(self):
        self._deprecated(
            "getdocids", _("Use `self.svg.get_ids()` instead of {} and `doc_ids`.")
        )
        self._doc_ids = None
        self.svg.ids.clear()

    def getselected(self):
        self._deprecated("getselected", _("{} has been removed"))

    def getElementById(self, eid):
        self._deprecated(
            "getElementById",
            _(
                "{} is now a method in the SvgDocumentElement class. "
                "Use `self.svg.getElementById(eid)` instead."
            ),
        )
        return self.svg.getElementById(eid)

    def xpathSingle(self, xpath):
        self._deprecated(
            "xpathSingle",
            _(
                "{} is now a new method in the SvgDocumentElement class. "
                "Use `self.svg.getElement(path)` instead."
            ),
        )
        return self.svg.getElement(xpath)

    def getParentNode(self, node):
        self._deprecated(
            "getParentNode",
            _("{} is no longer in use. Use the lxml `.getparent()` method instead."),
        )
        return node.getparent()

    def getNamedView(self):
        self._deprecated(
            "getNamedView",
            _(
                "{} is now a property of the SvgDocumentElement class. "
                "Use `self.svg.namedview` to access this element."
            ),
        )
        return self.svg.namedview

    def createGuide(self, posX, posY, angle):
        from ..elements import Guide

        self._deprecated(
            "createGuide",
            _(
                "{} is now a method of the namedview element object. "
                "Use `self.svg.namedview.add(Guide().move_to(x, y, a))` instead."
            ),
        )
        return self.svg.namedview.add(Guide().move_to(posX, posY, angle))

    def affect(
        self, args=sys.argv[1:], output=True
    ):  # pylint: disable=dangerous-default-value
        # We need a list as the default value to preserve backwards compatibility
        self._deprecated(
            "affect", _("{} is now `Effect.run()`. The `output` argument has changed.")
        )
        self._args = args[-1:]
        return self.run(args=args)

    @property
    def args(self):
        self._deprecated("args", _("self.args[-1] is now self.options.input_file."))
        return self._args

    @property
    def svg_file(self):
        self._deprecated("svg_file", _("self.svg_file is now self.options.input_file."))
        return self.options.input_file

    def save_raw(self, ret):
        # Derived class may implement "output()"
        # Attention: 'cubify.py' implements __getattr__ -> hasattr(self, 'output')
        # returns True
        if hasattr(self.__class__, "output"):
            self._deprecated("output", "Use `save()` or `save_raw()` instead.", stack=5)
            return getattr(self, "output")()
        return base.InkscapeExtension.save_raw(self, ret)

    def uniqueId(self, old_id, make_new_id=True):
        self._deprecated(
            "uniqueId",
            _(
                "{} is now a method in the SvgDocumentElement class. "
                " Use `self.svg.get_unique_id(old_id)` instead."
            ),
        )
        return self.svg.get_unique_id(old_id)

    def getDocumentWidth(self):
        self._deprecated(
            "getDocumentWidth",
            _(
                "{} is now a property of the SvgDocumentElement class. "
                "Use `self.svg.width` instead."
            ),
        )
        return self.svg.get("width")

    def getDocumentHeight(self):
        self._deprecated(
            "getDocumentHeight",
            _(
                "{} is now a property of the SvgDocumentElement class. "
                "Use `self.svg.height` instead."
            ),
        )
        return self.svg.get("height")

    def getDocumentUnit(self):
        self._deprecated(
            "getDocumentUnit",
            _(
                "{} is now a property of the SvgDocumentElement class. "
                "Use `self.svg.unit` instead."
            ),
        )
        return self.svg.unit

    def unittouu(self, string):
        self._deprecated(
            "unittouu",
            _(
                "{} is now a method in the SvgDocumentElement class. "
                "Use `self.svg.unittouu(str)` instead."
            ),
        )
        return self.svg.unittouu(string)

    def uutounit(self, val, unit):
        self._deprecated(
            "uutounit",
            _(
                "{} is now a method in the SvgDocumentElement class. "
                "Use `self.svg.uutounit(value, unit)` instead."
            ),
        )
        return self.svg.uutounit(val, unit)

    def addDocumentUnit(self, value):
        self._deprecated(
            "addDocumentUnit",
            _(
                "{} is now a method in the SvgDocumentElement class. "
                "Use `self.svg.add_unit(value)` instead."
            ),
        )
        return self.svg.add_unit(value)


class Effect(SvgThroughMixin, DeprecatedEffect, InkscapeExtension):
    """An Inkscape effect, takes SVG in and outputs SVG"""
