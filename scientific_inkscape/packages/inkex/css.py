# coding=utf-8
#
# Copyright (C) 2021 - Jonathan Neuhauser <jonathan.neuhauser@outlook.com>
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

"""Toplevel CSS utils that do not depend on other inkex functionality

.. versionadded:: 1.2
    Previously a part of :py:mod:`inkex.styles`"""


import re
import cssselect


class ConditionalRule:
    """A single css rule

    .. versionchanged:: 1.2
        The CSS rule is now processed using cssselect."""

    step_to_xpath = [
        # namespace addition
        (re.compile(r"(::|\/)([a-z]+)(?=\W)(?!-)"), r"\1svg:\2"),
    ]

    def __init__(self, rule):
        self.rule = rule.strip()
        self.selector = cssselect.parse(self.rule)[0]

    def __str__(self):
        return self.rule

    def to_xpath(self):
        """Attempt to convert the rule into a simplified xpath"""
        # the space in the end is needed for the negative lookbehind in the regex, will
        # be removed on return
        ret = cssselect.HTMLTranslator().selector_to_xpath(self.selector) + " "
        for matcher, replacer in self.step_to_xpath:
            ret = matcher.sub(replacer, ret)
        return ret.strip()

    def get_specificity(self):
        """gets the css specificity of this selector

        .. versionadded:: 1.2"""
        return self.selector.specificity()
