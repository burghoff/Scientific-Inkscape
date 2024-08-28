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
# pylint: disable=invalid-name
"""Deprecated cubic super path API"""

from inkex.deprecated import deprecate
from inkex import paths


@deprecate
def ArcToPath(p1, params):
    return paths.arc_to_path(p1, params)


@deprecate
def CubicSuperPath(simplepath):
    return paths.Path(simplepath).to_superpath()


@deprecate
def unCubicSuperPath(csp):
    return paths.CubicSuperPath(csp).to_path().to_arrays()


@deprecate
def parsePath(d):
    return paths.CubicSuperPath(paths.Path(d))


@deprecate
def formatPath(p):
    return str(paths.Path(unCubicSuperPath(p)))


matprod = deprecate(paths.matprod)
rotmat = deprecate(paths.rotmat)
applymat = deprecate(paths.applymat)
norm = deprecate(paths.norm)
