# coding=utf-8
# COPYRIGHT
#
# pylint: disable=invalid-name
#
"""
Depreicated simplepath replacements with documentation
"""

import math
from inkex.deprecated import deprecate, DeprecatedDict
from inkex.transforms import Transform
from inkex.paths import Path

pathdefs = DeprecatedDict(
    {
        "M": ["L", 2, [float, float], ["x", "y"]],
        "L": ["L", 2, [float, float], ["x", "y"]],
        "H": ["H", 1, [float], ["x"]],
        "V": ["V", 1, [float], ["y"]],
        "C": [
            "C",
            6,
            [float, float, float, float, float, float],
            ["x", "y", "x", "y", "x", "y"],
        ],
        "S": ["S", 4, [float, float, float, float], ["x", "y", "x", "y"]],
        "Q": ["Q", 4, [float, float, float, float], ["x", "y", "x", "y"]],
        "T": ["T", 2, [float, float], ["x", "y"]],
        "A": [
            "A",
            7,
            [float, float, float, int, int, float, float],
            ["r", "r", "a", 0, "s", "x", "y"],
        ],
        "Z": ["L", 0, [], []],
    }
)


@deprecate
def parsePath(d):
    """element.path.to_arrays()"""
    return Path(d).to_arrays()


@deprecate
def formatPath(a):
    """str(element.path) or str(Path(array))"""
    return str(Path(a))


@deprecate
def translatePath(p, x, y):
    """Path(array).translate(x, y)"""
    p[:] = Path(p).translate(x, y).to_arrays()


@deprecate
def scalePath(p, x, y):
    """Path(array).scale(x, y)"""
    p[:] = Path(p).scale(x, y).to_arrays()


@deprecate
def rotatePath(p, a, cx=0, cy=0):
    """Path(array).rotate(angle_degrees, (center_x, center_y))"""
    p[:] = Path(p).rotate(math.degrees(a), (cx, cy)).to_arrays()
