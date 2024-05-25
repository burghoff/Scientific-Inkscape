#
# Copyright (C) 2019 Thomas Holder
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
# pylint: disable=too-few-public-methods
#
"""
Comparison filters for use with the ComparisonMixin.

Each filter should be initialised in the list of
filters that are being used.

.. code-block:: python

    compare_filters = [
        CompareNumericFuzzy(),
        CompareOrderIndependentLines(option=yes),
    ]

"""

import re
from ..utils import to_bytes


class Compare:
    """
    Comparison base class, this acts as a passthrough unless
    the filter staticmethod is overwritten.
    """

    def __init__(self, **options):
        self.options = options

    def __call__(self, content):
        return self.filter(content)

    @staticmethod
    def filter(contents):
        """Replace this filter method with your own filtering"""
        return contents


class CompareNumericFuzzy(Compare):
    """
    Turn all numbers into shorter standard formats

    1.2345678 -> 1.2346
    1.2300 -> 1.23, 50.0000 -> 50.0
    50.0 -> 50
    """

    @staticmethod
    def filter(contents):
        func = lambda m: b"%.3f" % (float(m.group(0)))
        contents = re.sub(rb"\d+\.\d+(e[+-]\d+)?", func, contents)
        contents = re.sub(rb"(\d\.\d+?)0+\b", rb"\1", contents)
        contents = re.sub(rb"(\d)\.0+(?=\D|\b)", rb"\1", contents)
        return contents


class CompareWithoutIds(Compare):
    """Remove all ids from the svg"""

    @staticmethod
    def filter(contents):
        return re.sub(rb' id="([^"]*)"', b"", contents)


class CompareWithPathSpace(Compare):
    """Make sure that path segment commands have spaces around them"""

    @staticmethod
    def filter(contents):
        def func(match):
            """We've found a path command, process it"""
            new = re.sub(rb"\s*([LZMHVCSQTAatqscvhmzl])\s*", rb" \1 ", match.group(1))
            return b' d="' + new.replace(b",", b" ") + b'"'

        return re.sub(rb' d="([^"]*)"', func, contents)


class CompareSize(Compare):
    """Compare the length of the contents instead of the contents"""

    @staticmethod
    def filter(contents):
        return len(contents)


class CompareOrderIndependentBytes(Compare):
    """Take all the bytes and sort them"""

    @staticmethod
    def filter(contents):
        return b"".join([bytes(i) for i in sorted(contents)])


class CompareOrderIndependentLines(Compare):
    """Take all the lines and sort them"""

    @staticmethod
    def filter(contents):
        return b"\n".join(sorted(contents.splitlines()))


class CompareOrderIndependentStyle(Compare):
    """Take all styles and sort the results"""

    @staticmethod
    def filter(contents):
        contents = CompareNumericFuzzy.filter(contents)

        def func(match):
            """Search and replace function for sorting"""
            sty = b";".join(sorted(match.group(1).split(b";")))
            return b'style="%s"' % (sty,)

        return re.sub(rb'style="([^"]*)"', func, contents)


class CompareOrderIndependentStyleAndPath(Compare):
    """Take all styles and paths and sort them both"""

    @staticmethod
    def filter(contents):
        contents = CompareOrderIndependentStyle.filter(contents)

        def func(match):
            """Search and replace function for sorting"""
            path = b"X".join(sorted(re.split(rb"[A-Z]", match.group(1))))
            return b'd="%s"' % (path,)

        return re.sub(rb'\bd="([^"]*)"', func, contents)


class CompareOrderIndependentTags(Compare):
    """Sorts all the XML tags"""

    @staticmethod
    def filter(contents):
        return b"\n".join(sorted(re.split(rb">\s*<", contents)))


class CompareReplacement(Compare):
    """Replace pieces to make output more comparable

    .. versionadded:: 1.1"""

    def __init__(self, *replacements):
        self.deltas = replacements
        super().__init__()

    def filter(self, contents):
        contents = to_bytes(contents)
        for _from, _to in self.deltas:
            contents = contents.replace(to_bytes(_from), to_bytes(_to))
        return contents


class WindowsTextCompat(CompareReplacement):
    """Normalize newlines so tests comparing plain text work

    .. versionadded:: 1.2"""

    def __init__(self):
        super().__init__(("\r\n", "\n"))
