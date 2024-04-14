# coding=utf-8
#
# Copyright (c) 2023 David Burghoff <burghoff@utexas.edu>
#                    Martin Owens <doctormo@gmail.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Thomas Holder <thomas.holder@schrodinger.com>
#                    Jonathan Neuhauser <jonathan.neuhauser@outlook.com>

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

"""Patches for speeding up native Inkex functions after import"""

import inkex
from inkex import Transform
import re, lxml


""" _base.py """
# Inkex's get does a lot of namespace adding that can be cached for speed
# This can be bypassed altogether for known attributes (by using fget instead)

# Wrap gradientTransform and patternTransform
inkex.BaseElement.WRAPPED_ATTRS = (
    ("transform", inkex.Transform),
    ("style", inkex.Style),
    ("classes", "class", inkex.styles.Classes),
    ("gradientTransform", inkex.Transform),
    ("patternTransform", inkex.Transform),
)

fget = lxml.etree.ElementBase.get
fset = lxml.etree.ElementBase.set

wrapped_props = {row[0]: (row[-2], row[-1]) for row in inkex.BaseElement.WRAPPED_ATTRS}
wrapped_props_keys = set(wrapped_props.keys())
wrapped_attrs = {row[-2]: (row[0], row[-1]) for row in inkex.BaseElement.WRAPPED_ATTRS}
wrapped_attrs_keys = set(wrapped_attrs.keys())
from typing import Dict

wrprops: Dict[str, str] = dict()
inkexget = inkex.BaseElement.get


def fast_get(self, attr, default=None):
    try:
        return fget(self, inkex.addNS(attr), default)
    except:
        try:
            value = getattr(self, wrprops[attr], None)
            ret = str(value) if value else (default or None)
            return ret
        except:
            if attr in wrapped_attrs_keys:
                (wrprops[attr], _) = wrapped_attrs[attr]
            return inkexget(self, attr, default)


inkex.BaseElement.get = fast_get  # type: ignore


def fast_set(self, attr, value):
    """Set element attribute named, with addNS support"""
    if attr in wrapped_attrs:
        # Always keep the local wrapped class up to date.
        (prop, cls) = wrapped_attrs[attr]
        setattr(self, prop, cls(value))
        value = getattr(self, prop)
        if not value:
            return

    NSattr = inkex.addNS(attr)

    if value is None:
        self.attrib.pop(NSattr, None)  # pylint: disable=no-member
    else:
        value = str(value)
        fset(self, NSattr, value)


inkex.BaseElement.set = fast_set  # type: ignore


def fast_getattr(self, name):
    """Get the attribute, but load it if it is not available yet"""
    # if name in wrapped_props_keys:   # always satisfied
    (attr, cls) = wrapped_props[name]

    def _set_attr(new_item):
        if new_item:
            self.set(attr, str(new_item))
        else:
            self.attrib.pop(attr, None)  # pylint: disable=no-member

    # pylint: disable=no-member
    value = cls(self.attrib.get(attr, None), callback=_set_attr)
    if name == "style":
        value.element = self
    fast_setattr(self, name, value)
    return value
    # raise AttributeError(f"Can't find attribute {self.typename}.{name}")


def fast_setattr(self, name, value):
    """Set the attribute, update it if needed"""
    # if name in wrapped_props_keys:   # always satisfied
    (attr, cls) = wrapped_props[name]
    # Don't call self.set or self.get (infinate loop)
    if value:
        if not isinstance(value, cls):
            value = cls(value)
        self.attrib[attr] = str(value)
    else:
        self.attrib.pop(attr, None)  # pylint: disable=no-member


# _base.py overloads __setattr__ and __getattr__, which adds a lot of overhead
# since they're invoked for all class attributes, not just transform etc.
# We remove the overloading and replicate it using properties. Since there
# are only a few attributes to overload, this is fine.
del inkex.BaseElement.__setattr__
del inkex.BaseElement.__getattr__
for prop in wrapped_props_keys:
    get_func = lambda self, attr=prop: fast_getattr(self, attr)
    set_func = lambda self, value, attr=prop: fast_setattr(self, attr, value)
    setattr(inkex.BaseElement, str(prop), property(get_func, set_func))


""" paths.py """
# A faster version of Vector2d that only allows for 2 input args
V2d = inkex.transforms.Vector2d


class Vector2da(V2d):
    __slots__ = ("_x", "_y")  # preallocation speeds

    def __init__(self, x, y):
        self._x = float(x)
        self._y = float(y)


def horz_end_point(self, first, prev):
    return Vector2da(self.x, prev.y)


def line_move_arc_end_point(self, first, prev):
    return Vector2da(self.x, self.y)


def vert_end_point(self, first, prev):
    return Vector2da(prev.x, self.y)


def curve_smooth_end_point(self, first, prev):
    return Vector2da(self.x4, self.y4)


def quadratic_tepid_quadratic_end_point(self, first, prev):
    return Vector2da(self.x3, self.y3)


inkex.paths.Line.end_point = line_move_arc_end_point  # type: ignore
inkex.paths.Move.end_point = line_move_arc_end_point  # type: ignore
inkex.paths.Arc.end_point = line_move_arc_end_point  # type: ignore
inkex.paths.Horz.end_point = horz_end_point  # type: ignore
inkex.paths.Vert.end_point = vert_end_point  # type: ignore
inkex.paths.Curve.end_point = curve_smooth_end_point  # type: ignore
inkex.paths.Smooth.end_point = curve_smooth_end_point  # type: ignore
inkex.paths.Quadratic.end_point = quadratic_tepid_quadratic_end_point  # type: ignore
inkex.paths.TepidQuadratic.end_point = quadratic_tepid_quadratic_end_point  # type: ignore


# A version of end_points that avoids unnecessary instance checks
zZmM = {"z", "Z", "m", "M"}


def fast_end_points(self):
    prev = Vector2da(0, 0)
    first = Vector2da(0, 0)
    for seg in self:
        end_point = seg.end_point(first, prev)
        if seg.letter in zZmM:
            first = end_point
        prev = end_point
        yield end_point


inkex.paths.Path.end_points = property(fast_end_points)  # type: ignore

ctqsCTQS = {"c", "t", "q", "s", "C", "T", "Q", "S"}


def fast_proxy_iterator(self):
    previous = V2d()
    prev_prev = V2d()
    first = V2d()
    for seg in self:
        if seg.letter in zZmM:
            first = seg.end_point(first, previous)
        yield inkex.paths.Path.PathCommandProxy(seg, first, previous, prev_prev)
        if seg.letter in ctqsCTQS:
            prev_prev = list(seg.control_points(first, previous, prev_prev))[-2]
        previous = seg.end_point(first, previous)


if not hasattr(inkex.transforms.ImmutableVector2d, "c2t"):
    # The new complex implementation of vector2ds is fast
    inkex.paths.Path.proxy_iterator = fast_proxy_iterator  # type: ignore


def fast_control_points(self):
    """Returns all control points of the Path"""
    prev = Vector2da(0, 0)
    prev_prev = Vector2da(0, 0)
    first = Vector2da(0, 0)
    for seg in self:
        for cpt in seg.control_points(first, prev, prev_prev):
            prev_prev = prev
            prev = cpt
            yield cpt
        if seg.letter in zZmM:
            first = cpt


inkex.paths.Path.control_points = property(fast_control_points)  # type: ignore
from typing import (
    Union,
    List,
    Generator,
)


def fast_control_points_move(
    self, first: Vector2da, prev: Vector2da, prev_prev: Vector2da
) -> Generator[Vector2da, None, None]:
    yield Vector2da(prev.x + self.dx, prev.y + self.dy)


inkex.paths.move.control_points = fast_control_points_move  # type: ignore


def fast_control_points_line(
    self, first: Vector2da, prev: Vector2da, prev_prev: Vector2da
) -> Generator[Vector2da, None, None]:
    yield Vector2da(prev.x + self.dx, prev.y + self.dy)


inkex.paths.line.control_points = fast_control_points_line  # type: ignore


def fast_control_points_Vert(self, first, prev, prev_prev):
    yield Vector2da(prev.x, self.y)


inkex.paths.Vert.control_points = fast_control_points_Vert  # type: ignore


def fast_control_points_vert(self, first, prev, prev_prev):
    yield Vector2da(prev.x, prev.y + self.dy)


inkex.paths.vert.control_points = fast_control_points_vert  # type: ignore


def fast_control_points_Horz(self, first, prev, prev_prev):
    yield Vector2da(self.x, prev.y)


inkex.paths.Horz.control_points = fast_control_points_Horz  # type: ignore


def fast_control_points_horz(self, first, prev, prev_prev):
    yield Vector2da(prev.x + self.dx, prev.y)


inkex.paths.horz.control_points = fast_control_points_horz  # type: ignore

# Optimize Path's init to avoid calls to append and reduce instance checks
# About 50% faster
ipcspth, ipln, ipmv = inkex.paths.CubicSuperPath, inkex.paths.Line, inkex.paths.Move
ipPC = inkex.paths.PathCommand
letter_to_class = ipPC._letter_to_class
PCsubs = set(letter_to_class.values())


# precache all types that are instances of PathCommand
def process_items(items, slf):
    for item in items:
        # if isinstance(item, ipPC):
        itemtype = type(item)
        if itemtype in PCsubs:
            yield item
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            if isinstance(item[1], (list, tuple)):
                yield ipPC.letter_to_class(item[0])(*item[1])
            else:
                if len(slf) == 0:
                    yield ipmv(*item)
                else:
                    yield ipln(*item)
        else:
            raise TypeError(
                f"Bad path type: {type(items).__name__}"
                f"({type(item).__name__}, ...): {item}"
            )


from functools import lru_cache


# @lru_cache(maxsize=None)
def fast_init(self, path_d=None):
    list.__init__(self)
    if isinstance(path_d, str):
        self.extend(cached_parse_string(path_d))
    else:
        if isinstance(path_d, ipcspth):
            path_d = path_d.to_path()
        self.extend(process_items(path_d or (), self))


inkex.paths.Path.__init__ = fast_init  # type: ignore

# Cache PathCommand letters and remove property
letts = dict()
for pc in PCsubs:
    letts[pc] = pc.letter
del ipPC.letter
for pc in PCsubs:
    pc.letter = letts[pc]

# Make parse_string faster by combining with strargs (about 20% faster)
LEX_REX = (
    inkex.paths.LEX_REX if hasattr(inkex.paths, "LEX_REX") else inkex.paths.path.LEX_REX
)  # type: ignore
try:
    NUMBER_REX = inkex.utils.NUMBER_REX
except:
    DIGIT_REX_PART = r"[0-9]"
    DIGIT_SEQUENCE_REX_PART = rf"(?:{DIGIT_REX_PART}+)"
    INTEGER_CONSTANT_REX_PART = DIGIT_SEQUENCE_REX_PART
    SIGN_REX_PART = r"[+-]"
    EXPONENT_REX_PART = rf"(?:[eE]{SIGN_REX_PART}?{DIGIT_SEQUENCE_REX_PART})"
    FRACTIONAL_CONSTANT_REX_PART = rf"(?:{DIGIT_SEQUENCE_REX_PART}?\.{DIGIT_SEQUENCE_REX_PART}|{DIGIT_SEQUENCE_REX_PART}\.)"
    FLOATING_POINT_CONSTANT_REX_PART = rf"(?:{FRACTIONAL_CONSTANT_REX_PART}{EXPONENT_REX_PART}?|{DIGIT_SEQUENCE_REX_PART}{EXPONENT_REX_PART})"
    NUMBER_REX = re.compile(
        rf"(?:{SIGN_REX_PART}?{FLOATING_POINT_CONSTANT_REX_PART}|{SIGN_REX_PART}?{INTEGER_CONSTANT_REX_PART})"
    )
nargs_cache = {cmd: cmd.nargs for cmd in letter_to_class.values()}
next_command_cache = {cmd: cmd.next_command for cmd in letter_to_class.values()}


# Generator version
def fast_parse_string(cls, path_d):
    for cmd, numbers in LEX_REX.findall(path_d):
        args = [float(val) for val in NUMBER_REX.findall(numbers)]
        cmd = letter_to_class[cmd]
        cmd_nargs = nargs_cache[cmd]
        i = 0
        args_len = len(args)
        while i < args_len or cmd_nargs == 0:
            if args_len < i + cmd_nargs:
                return
            seg = cmd(*args[i : i + cmd_nargs])
            i += cmd_nargs
            cmd = next_command_cache[type(seg)]
            cmd_nargs = nargs_cache[cmd]
            yield seg


inkex.paths.Path.parse_string = fast_parse_string  # type: ignore


@lru_cache(maxsize=None)
def cached_parse_string(path_d):
    ret = []
    for cmd, numbers in LEX_REX.findall(path_d):
        args = [float(val) for val in NUMBER_REX.findall(numbers)]
        cmd = letter_to_class[cmd]
        cmd_nargs = nargs_cache[cmd]
        i = 0
        args_len = len(args)
        while i < args_len or cmd_nargs == 0:
            if args_len < i + cmd_nargs:
                return ret
            seg = cmd(*args[i : i + cmd_nargs])
            i += cmd_nargs
            cmd = next_command_cache[type(seg)]
            cmd_nargs = nargs_cache[cmd]
            ret.append(seg)
    return ret


""" transforms.py """


# Faster apply_to_point that gets rid of property calls
def apply_to_point_mod(obj, pt):
    try:
        ptx, pty = pt
    except:
        try:
            ptx, pty = (pt.x, pt.y)
        except:
            raise ValueError
    x = obj.matrix[0][0] * ptx + obj.matrix[0][1] * pty + obj.matrix[0][2]
    y = obj.matrix[1][0] * ptx + obj.matrix[1][1] * pty + obj.matrix[1][2]
    return Vector2da(x, y)


old_atp = inkex.Transform.apply_to_point
inkex.Transform.apply_to_point = apply_to_point_mod  # type: ignore


# Applies inverse of transform to point without making a new Transform
def applyI_to_point(obj, pt):
    m = obj.matrix
    det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
    inv_det = 1 / det
    sx = pt.x - m[0][2]  # pt.x is sometimes a numpy float64?
    sy = pt.y - m[1][2]
    x = (m[1][1] * sx - m[0][1] * sy) * inv_det
    y = (m[0][0] * sy - m[1][0] * sx) * inv_det
    return Vector2da(x, y)


inkex.Transform.applyI_to_point = applyI_to_point  # type: ignore

# Built-in bool initializes multiple Transforms
Itmat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
atol = inkex.Transform.absolute_tolerance
natol = -atol
atp1 = atol + 1
natp1 = -atol + 1


def Tbool(obj):
    # return obj.matrix != Itmat  # exact, not within tolerance. I think this is fine
    return not (
        natp1 < obj.matrix[0][0] < atp1
        and natol < obj.matrix[0][1] < atol
        and natol < obj.matrix[0][2] < atol
        and natol < obj.matrix[1][0] < atol
        and natp1 < obj.matrix[1][1] < atp1
        and natol < obj.matrix[1][2] < atol
    )


inkex.Transform.__bool__ = Tbool  # type: ignore


# Reduce Transform conversions during transform multiplication
def matmul2(obj, matrix):
    if isinstance(matrix, (Transform)):
        othermat = matrix.matrix
    elif isinstance(matrix, (tuple)):
        othermat = matrix
    else:
        othermat = Transform(matrix).matrix
        # I think this is never called
    return Transform(
        (
            obj.matrix[0][0] * othermat[0][0] + obj.matrix[0][1] * othermat[1][0],
            obj.matrix[1][0] * othermat[0][0] + obj.matrix[1][1] * othermat[1][0],
            obj.matrix[0][0] * othermat[0][1] + obj.matrix[0][1] * othermat[1][1],
            obj.matrix[1][0] * othermat[0][1] + obj.matrix[1][1] * othermat[1][1],
            obj.matrix[0][0] * othermat[0][2]
            + obj.matrix[0][1] * othermat[1][2]
            + obj.matrix[0][2],
            obj.matrix[1][0] * othermat[0][2]
            + obj.matrix[1][1] * othermat[1][2]
            + obj.matrix[1][2],
        )
    )


inkex.transforms.Transform.__matmul__ = matmul2  # type: ignore


def imatmul2(self, othermat):
    if isinstance(othermat, (Transform)):
        othermat = othermat.matrix
    self.matrix = (
        (
            self.matrix[0][0] * othermat[0][0] + self.matrix[0][1] * othermat[1][0],
            self.matrix[0][0] * othermat[0][1] + self.matrix[0][1] * othermat[1][1],
            self.matrix[0][0] * othermat[0][2]
            + self.matrix[0][1] * othermat[1][2]
            + self.matrix[0][2],
        ),
        (
            self.matrix[1][0] * othermat[0][0] + self.matrix[1][1] * othermat[1][0],
            self.matrix[1][0] * othermat[0][1] + self.matrix[1][1] * othermat[1][1],
            self.matrix[1][0] * othermat[0][2]
            + self.matrix[1][1] * othermat[1][2]
            + self.matrix[1][2],
        ),
    )
    if self.callback is not None:
        self.callback(self)
    return self


inkex.transforms.Transform.__imatmul__ = imatmul2  # type: ignore

# Rewrite ImmutableVector2d since 2 arguments most common
IV2d = inkex.transforms.ImmutableVector2d


def IV2d_init(self, *args, fallback=None):
    try:
        self._x, self._y = map(float, args)
    except:
        try:
            if len(args) == 0:
                x, y = 0.0, 0.0
            elif len(args) == 1:
                try:
                    x, y = self._parse(args[0])
                except:
                    x, y = float(args[0]), float(args[0])
            else:
                raise ValueError("too many arguments")
        except (ValueError, TypeError) as error:
            if fallback is None:
                raise ValueError("Cannot parse vector and no fallback given") from error
            x, y = IV2d(fallback)
        self._x, self._y = float(x), float(y)


inkex.transforms.ImmutableVector2d.__init__ = IV2d_init  # type: ignore


import math


def matrix_multiply(a, b):
    return (
        (
            a[0][0] * b[0][0] + a[0][1] * b[1][0],
            a[0][0] * b[0][1] + a[0][1] * b[1][1],
            a[0][0] * b[0][2] + a[0][1] * b[1][2] + a[0][2],
        ),
        (
            a[1][0] * b[0][0] + a[1][1] * b[1][0],
            a[1][0] * b[0][1] + a[1][1] * b[1][1],
            a[1][0] * b[0][2] + a[1][1] * b[1][2] + a[1][2],
        ),
    )


trpattern = re.compile(r"\b(scale|translate|rotate|skewX|skewY|matrix)\(([^\)]*)\)")
split_pattern = re.compile(r"[\s,]+")


# Converts a transform string into a standard matrix
@lru_cache(maxsize=None)
def transform_to_matrix(transform):
    null = ((1, 0, 0), (0, 1, 0))
    matrix = ((1, 0, 0), (0, 1, 0))
    if "none" not in transform:
        matches = list(trpattern.finditer(transform))
        if not matches:
            return null
        else:
            for match in matches:
                transform_type = match.group(1)
                transform_args = [
                    float(arg) for arg in split_pattern.split(match.group(2))
                ]

                if transform_type == "scale":
                    # Scale transform
                    if len(transform_args) == 1:
                        sx = sy = transform_args[0]
                    elif len(transform_args) == 2:
                        sx, sy = transform_args
                    else:
                        return null
                    # matrix = matrix_multiply(matrix, [[sx, 0, 0], [0, sy, 0], [0, 0, 1]])
                    matrix = (
                        (matrix[0][0] * sx, matrix[0][1] * sy, matrix[0][2]),
                        (matrix[1][0] * sx, matrix[1][1] * sy, matrix[1][2]),
                    )
                elif transform_type == "translate":
                    # Translation transform
                    if len(transform_args) == 1:
                        tx = transform_args[0]
                        ty = 0
                    elif len(transform_args) == 2:
                        tx, ty = transform_args
                    else:
                        return null
                    # matrix = matrix_multiply(matrix, [[1, 0, tx], [0, 1, ty], [0, 0, 1]])
                    matrix = (
                        (
                            matrix[0][0],
                            matrix[0][1],
                            matrix[0][0] * tx + matrix[0][1] * ty + matrix[0][2],
                        ),
                        (
                            matrix[1][0],
                            matrix[1][1],
                            matrix[1][0] * tx + matrix[1][1] * ty + matrix[1][2],
                        ),
                    )
                elif transform_type == "rotate":
                    # Rotation transform
                    if len(transform_args) == 1:
                        angle = transform_args[0]
                        cx = cy = 0
                    elif len(transform_args) == 3:
                        angle, cx, cy = transform_args
                    else:
                        return null
                    angle = angle * math.pi / 180  # Convert angle to radians
                    matrix = matrix_multiply(matrix, ((1, 0, cx), (0, 1, cy)))
                    matrix = matrix_multiply(
                        matrix,
                        (
                            (math.cos(angle), -math.sin(angle), 0),
                            (math.sin(angle), math.cos(angle), 0),
                        ),
                    )
                    matrix = matrix_multiply(matrix, ((1, 0, -cx), (0, 1, -cy)))
                elif transform_type == "skewX":
                    # SkewX transform
                    if len(transform_args) == 1:
                        angle = transform_args[0]
                    else:
                        return null
                    angle = angle * math.pi / 180  # Convert angle to radians
                    matrix = matrix_multiply(
                        matrix, ((1, math.tan(angle), 0), (0, 1, 0))
                    )
                elif transform_type == "skewY":
                    # SkewY transform
                    if len(transform_args) == 1:
                        angle = transform_args[0]
                    else:
                        return null
                    angle = angle * math.pi / 180  # Convert angle to radians
                    matrix = matrix_multiply(
                        matrix, ((1, 0, 0), (math.tan(angle), 1, 0))
                    )
                elif transform_type == "matrix":
                    # Matrix transform
                    if len(transform_args) == 6:
                        a, b, c, d, e, f = transform_args
                    else:
                        return null
                    # matrix = matrix_multiply(matrix, [[a, c, e], [b, d, f], [0, 0, 1]])
                    matrix = (
                        (
                            matrix[0][0] * a + matrix[0][1] * b,
                            matrix[0][0] * c + matrix[0][1] * d,
                            matrix[0][0] * e + matrix[0][1] * f + matrix[0][2],
                        ),
                        (
                            matrix[1][0] * a + matrix[1][1] * b,
                            matrix[1][0] * c + matrix[1][1] * d,
                            matrix[1][0] * e + matrix[1][1] * f + matrix[1][2],
                        ),
                    )
    # Return the final matrix
    return matrix


if isinstance(getattr(inkex.transforms.Transform, "matrix", None), property):
    # If Transform.matrix is a property, is stored in new complex format
    # Give it a setter that converts tuple of the form ((a,c,e),(b,d,f)) into the new complex format if necessary
    def matrixset(self, mat):
        self.arg1 = (mat[0][0] + mat[1][1]) / 2 + 1j * (mat[1][0] - mat[0][1]) / 2
        self.arg2 = (mat[0][0] - mat[1][1]) / 2 + 1j * (mat[1][0] + mat[0][1]) / 2
        self.arg3 = mat[0][2] + mat[1][2] * 1j

    setfcn = inkex.transforms.Transform.matrix.fget  # type: ignore
    inkex.transforms.Transform.matrix = property(setfcn, matrixset)  # type: ignore

from typing import cast, Tuple


def fast_set_matrix(self, matrix):
    """Parse a given string as an svg transformation instruction.

    .. version added:: 1.1"""
    if isinstance(matrix, str):
        self.matrix = transform_to_matrix(matrix)
    elif isinstance(matrix, (list, tuple)) and len(matrix) == 6:
        self.matrix = (
            (float(matrix[0]), float(matrix[2]), float(matrix[4])),
            (float(matrix[1]), float(matrix[3]), float(matrix[5])),
        )
    elif isinstance(matrix, Transform):
        self.matrix = matrix.matrix
    elif isinstance(matrix, (tuple, list)) and len(matrix) == 2:
        row1 = matrix[0]
        row2 = matrix[1]
        if isinstance(row1, (tuple, list)) and isinstance(row2, (tuple, list)):
            if len(row1) == 3 and len(row2) == 3:
                row1 = cast(Tuple[float, float, float], tuple(map(float, row1)))
                row2 = cast(Tuple[float, float, float], tuple(map(float, row2)))
                self.matrix = (row1, row2)
            else:
                raise ValueError(
                    f"Matrix '{matrix}' is not a valid transformation matrix"
                )
        else:
            raise ValueError(f"Matrix '{matrix}' is not a valid transformation matrix")
    elif not isinstance(matrix, (list, tuple)):
        raise ValueError(f"Invalid transform type: {type(matrix).__name__}")
    else:
        raise ValueError(f"Matrix '{matrix}' is not a valid transformation matrix")


inkex.transforms.Transform._set_matrix = fast_set_matrix  # type: ignore

""" _utils.py """


# Cache the namespace function results

NSloc = inkex.utils if hasattr(inkex.utils, "addNS") else inkex.elements._utils
orig_addNS = getattr(NSloc, "addNS")
orig_removeNS = getattr(NSloc, "removeNS")
orig_splitNS = getattr(NSloc, "splitNS")


@lru_cache(maxsize=None)
def cached_addNS(*args, **kwargs):
    return orig_addNS(*args, **kwargs)


@lru_cache(maxsize=None)
def cached_removeNS(*args, **kwargs):
    return orig_removeNS(*args, **kwargs)


@lru_cache(maxsize=None)
def cached_splitNS(*args, **kwargs):
    return orig_splitNS(*args, **kwargs)


def clear_caches():
    cached_addNS.cache_clear()
    cached_removeNS.cache_clear()
    cached_splitNS.cache_clear()


# Reset the cache before namespace modifications
orig_registerNS = getattr(NSloc, "registerNS", None)
if orig_registerNS:

    def mod_registerNS(*args, **kwargs):
        clear_caches()
        orig_registerNS(*args, **kwargs)

    NSloc.registerNS = mod_registerNS  # type: ignore

orig_add_namespace = getattr(inkex.SvgDocumentElement, "add_namespace", None)
if orig_add_namespace:

    def mod_add_namespace(*args, **kwargs):
        clear_caches()
        orig_add_namespace(*args, **kwargs)

    inkex.SvgDocumentElement.add_namespace = mod_add_namespace  # type: ignore

NSloc.addNS = (  # type: ignore
    inkex.addNS
) = inkex.elements._base.addNS = inkex.elements._groups.addNS = (
    inkex.elements._filters.addNS
) = inkex.elements._polygons.addNS = cached_addNS
NSloc.removeNS = inkex.elements._base.removeNS = cached_removeNS  # type: ignore
NSloc.splitNS = inkex.elements._base.splitNS = cached_splitNS  # type: ignore
try:
    inkex.elements._parser.splitNS = cached_splitNS  # new versions only
except:
    pass


"""_parser.py"""
try:
    lup1 = inkex.elements._parser.NodeBasedLookup.lookup_table
    lup2 = dict()
    for k, v in lup1.items():
        lup2[cached_addNS(k[1], k[0])] = list(
            reversed(lup1[cached_splitNS(cached_addNS(k[1], k[0]))])
        )

    def fast_lookup(self, doc, element):
        try:
            for kls in lup2[element.tag]:
                if kls.is_class_element(element):  # pylint: disable=protected-access
                    return kls
        except KeyError:
            try:
                lup2[element.tag] = list(reversed(lup1[cached_splitNS(element.tag)]))
                for kls in lup2[element.tag]:
                    if kls.is_class_element(element):  # pylint: disable=protected-access
                        return kls
            except TypeError:
                lup2[element.tag] = None  # handle comments
                return None
        except TypeError:
            # Handle non-element proxies case "<!--Comment-->"
            return None
        return inkex.elements._parser.NodeBasedLookup.default

    inkex.elements._parser.NodeBasedLookup.lookup = fast_lookup  # type: ignore
    # new versions only
except:
    pass
