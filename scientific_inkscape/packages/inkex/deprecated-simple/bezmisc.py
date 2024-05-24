# coding=utf-8
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
# pylint: disable=invalid-name,unused-argument
"""Deprecated bezmisc API"""

from inkex.deprecated import deprecate
from inkex import bezier

bezierparameterize = deprecate(bezier.bezierparameterize)
linebezierintersect = deprecate(bezier.linebezierintersect)
bezierpointatt = deprecate(bezier.bezierpointatt)
bezierslopeatt = deprecate(bezier.bezierslopeatt)
beziertatslope = deprecate(bezier.beziertatslope)
tpoint = deprecate(bezier.tpoint)
beziersplitatt = deprecate(bezier.beziersplitatt)
pointdistance = deprecate(bezier.pointdistance)
Gravesen_addifclose = deprecate(bezier.addifclose)
balf = deprecate(bezier.balf)
bezierlengthSimpson = deprecate(bezier.bezierlength)
beziertatlength = deprecate(bezier.beziertatlength)
bezierlength = bezierlengthSimpson


@deprecate
def Simpson(func, a, b, n_limit, tolerance):
    """bezier.simpson(a, b, n_limit, tolerance, balf_arguments)"""
    raise AttributeError(
        """Because bezmisc.Simpson used global variables, it's not possible to
        call the replacement code automatically. In fact it's unlikely you were
        using the code or functionality you think you were since it's a highly
        broken way of writing python."""
    )
