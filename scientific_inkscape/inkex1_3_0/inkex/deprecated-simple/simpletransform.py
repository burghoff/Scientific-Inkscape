# coding=utf-8
#
# pylint: disable=invalid-name
#
"""
Depreicated simpletransform replacements with documentation
"""

import warnings

from inkex.deprecated import deprecate
from inkex.transforms import Transform, BoundingBox, cubic_extrema
from inkex.paths import Path

import inkex, cubicsuperpath


def _lists(mat):
    return [list(row) for row in mat]


@deprecate
def parseTransform(transf, mat=None):
    """Transform(str).matrix"""
    t = Transform(transf)
    if mat is not None:
        t = Transform(mat) @ t
    return _lists(t.matrix)


@deprecate
def formatTransform(mat):
    """str(Transform(mat))"""
    if len(mat) == 3:
        warnings.warn("3x3 matrices not suported")
        mat = mat[:2]
    return str(Transform(mat))


@deprecate
def invertTransform(mat):
    """-Transform(mat)"""
    return _lists((-Transform(mat)).matrix)


@deprecate
def composeTransform(mat1, mat2):
    """Transform(M1) * Transform(M2)"""
    return _lists((Transform(mat1) @ Transform(mat2)).matrix)


@deprecate
def composeParents(node, mat):
    """elem.composed_transform() or elem.transform * Transform(mat)"""
    return (node.transform @ Transform(mat)).matrix


@deprecate
def applyTransformToNode(mat, node):
    """elem.transform = Transform(mat) * elem.transform"""
    node.transform = Transform(mat) @ node.transform


@deprecate
def applyTransformToPoint(mat, pt):
    """Transform(mat).apply_to_point(pt)"""
    pt2 = Transform(mat).apply_to_point(pt)
    # Apply in place as original method was modifying arrays in place.
    # but don't do this in your code! This is not good code design.
    pt[0] = pt2[0]
    pt[1] = pt2[1]


@deprecate
def applyTransformToPath(mat, path):
    """Path(path).transform(mat)"""
    return Path(path).transform(Transform(mat)).to_arrays()


@deprecate
def fuseTransform(node):
    """node.apply_transform()"""
    return node.apply_transform()


@deprecate
def boxunion(b1, b2):
    """list(BoundingBox(b1) + BoundingBox(b2))"""
    bbox = BoundingBox(b1[:2], b1[2:]) + BoundingBox(b2[:2], b2[2:])
    return bbox.x.minimum, bbox.x.maximum, bbox.y.minimum, bbox.y.maximum


@deprecate
def roughBBox(path):
    """list(Path(path)).bounding_box())"""
    bbox = Path(path).bounding_box()
    return bbox.x.minimum, bbox.x.maximum, bbox.y.minimum, bbox.y.maximum


@deprecate
def refinedBBox(path):
    """list(Path(path)).bounding_box())"""
    bbox = Path(path).bounding_box()
    return bbox.x.minimum, bbox.x.maximum, bbox.y.minimum, bbox.y.maximum


@deprecate
def cubicExtrema(y0, y1, y2, y3):
    """from inkex.transforms import cubic_extrema"""
    return cubic_extrema(y0, y1, y2, y3)


@deprecate
def computeBBox(aList, mat=[[1, 0, 0], [0, 1, 0]]):
    """sum([node.bounding_box() for node in aList])"""
    return sum([node.bounding_box() for node in aList], None)


@deprecate
def computePointInNode(pt, node, mat=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]):
    """(-Transform(node.transform * mat)).apply_to_point(pt)"""
    return (-Transform(node.transform * mat)).apply_to_point(pt)
