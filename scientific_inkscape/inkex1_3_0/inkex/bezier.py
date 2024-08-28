# coding=utf-8
#
# Copyright (C) 2010 Nick Drobchenko, nick@cnc-club.ru
# Copyright (C) 2005 Aaron Spike, aaron@ekips.org
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
# pylint: disable=invalid-name,too-many-locals
#
"""
Bezier calculations
"""

import cmath
import math

import numpy

from .transforms import DirectedLineSegment
from .localization import inkex_gettext as _

# bez = ((bx0,by0),(bx1,by1),(bx2,by2),(bx3,by3))


def pointdistance(point_a, point_b):
    """The straight line distance between two points"""
    return math.sqrt(
        ((point_b[0] - point_a[0]) ** 2) + ((point_b[1] - point_a[1]) ** 2)
    )


def between_point(point_a, point_b, time=0.5):
    """Returns the point between point a and point b"""
    return point_a[0] + time * (point_b[0] - point_a[0]), point_a[1] + time * (
        point_b[1] - point_a[1]
    )


def percent_point(point_a, point_b, percent=50.0):
    """Returns between_point but takes percent instead of 0.0-1.0"""
    return between_point(point_a, point_b, percent / 100.0)


def root_wrapper(root_a, root_b, root_c, root_d):
    """Get the Cubic function, moic formular of roots, simple root"""
    if root_a:
        # Monics formula, see
        # http://en.wikipedia.org/wiki/Cubic_function#Monic_formula_of_roots
        mono_a, mono_b, mono_c = (root_b / root_a, root_c / root_a, root_d / root_a)
        m = 2.0 * mono_a**3 - 9.0 * mono_a * mono_b + 27.0 * mono_c
        k = mono_a**2 - 3.0 * mono_b
        n = m**2 - 4.0 * k**3
        w1 = -0.5 + 0.5 * cmath.sqrt(-3.0)
        w2 = -0.5 - 0.5 * cmath.sqrt(-3.0)
        if n < 0:
            m1 = pow(complex((m + cmath.sqrt(n)) / 2), 1.0 / 3)
            n1 = pow(complex((m - cmath.sqrt(n)) / 2), 1.0 / 3)
        else:
            if m + math.sqrt(n) < 0:
                m1 = -pow(-(m + math.sqrt(n)) / 2, 1.0 / 3)
            else:
                m1 = pow((m + math.sqrt(n)) / 2, 1.0 / 3)
            if m - math.sqrt(n) < 0:
                n1 = -pow(-(m - math.sqrt(n)) / 2, 1.0 / 3)
            else:
                n1 = pow((m - math.sqrt(n)) / 2, 1.0 / 3)
        return (
            -1.0 / 3 * (mono_a + m1 + n1),
            -1.0 / 3 * (mono_a + w1 * m1 + w2 * n1),
            -1.0 / 3 * (mono_a + w2 * m1 + w1 * n1),
        )
    if root_b:
        det = root_c**2.0 - 4.0 * root_b * root_d
        if det:
            return (
                (-root_c + cmath.sqrt(det)) / (2.0 * root_b),
                (-root_c - cmath.sqrt(det)) / (2.0 * root_b),
            )
        return (-root_c / (2.0 * root_b),)
    if root_c:
        return (1.0 * (-root_d / root_c),)
    return ()


def bezlenapprx(sp1, sp2):
    """Return the aproximate length between two beziers"""
    return (
        pointdistance(sp1[1], sp1[2])
        + pointdistance(sp1[2], sp2[0])
        + pointdistance(sp2[0], sp2[1])
    )


def cspbezsplit(sp1, sp2, time=0.5):
    """Split a cubic bezier at the time period"""
    m1 = tpoint(sp1[1], sp1[2], time)
    m2 = tpoint(sp1[2], sp2[0], time)
    m3 = tpoint(sp2[0], sp2[1], time)
    m4 = tpoint(m1, m2, time)
    m5 = tpoint(m2, m3, time)
    m = tpoint(m4, m5, time)
    return [[sp1[0][:], sp1[1][:], m1], [m4, m, m5], [m3, sp2[1][:], sp2[2][:]]]


def cspbezsplitatlength(sp1, sp2, length=0.5, tolerance=0.001):
    """Split a cubic bezier at length"""
    bez = (sp1[1][:], sp1[2][:], sp2[0][:], sp2[1][:])
    time = beziertatlength(bez, length, tolerance)
    return cspbezsplit(sp1, sp2, time)


def cspseglength(sp1, sp2, tolerance=0.001):
    """Get cubic bezier segment length"""
    bez = (sp1[1][:], sp1[2][:], sp2[0][:], sp2[1][:])
    return bezierlength(bez, tolerance)


def csplength(csp):
    """Get cubic bezier length"""
    total = 0
    lengths = []
    for sp in csp:
        lengths.append([])
        for i in range(1, len(sp)):
            l = cspseglength(sp[i - 1], sp[i])
            lengths[-1].append(l)
            total += l
    return lengths, total


def bezierparameterize(bez):
    """Return the bezier parameter size
    Converts the bezier parametrisation from the default form
    P(t) = (1-t)³ P_1 + 3(1-t)²t P_2 + 3(1-t)t² P_3 + t³ x_4
    to the a form which can be differentiated more easily
    P(t) = a t³ + b t² + c t + P0

    Args:
        bez (List[Tuple[float, float]]): the Bezier curve. The elements of the list the
            coordinates of the points (in this order): Start point, Start control point,
            End control point, End point.

    Returns:
        Tuple[float, float, float, float, float, float, float, float]:
            the values ax, ay, bx, by, cx, cy, x0, y0
    """
    ((bx0, by0), (bx1, by1), (bx2, by2), (bx3, by3)) = bez
    # parametric bezier
    x0 = bx0
    y0 = by0
    cx = 3 * (bx1 - x0)
    bx = 3 * (bx2 - bx1) - cx
    ax = bx3 - x0 - cx - bx
    cy = 3 * (by1 - y0)
    by = 3 * (by2 - by1) - cy
    ay = by3 - y0 - cy - by

    return ax, ay, bx, by, cx, cy, x0, y0


def linebezierintersect(arg_a, bez):
    """Where a line and bezier intersect"""
    ((lx1, ly1), (lx2, ly2)) = arg_a
    # parametric line
    dd = lx1
    cc = lx2 - lx1
    bb = ly1
    aa = ly2 - ly1

    if aa:
        coef1 = cc / aa
        coef2 = 1
    else:
        coef1 = 1
        coef2 = aa / cc

    ax, ay, bx, by, cx, cy, x0, y0 = bezierparameterize(bez)
    # cubic intersection coefficients
    a = coef1 * ay - coef2 * ax
    b = coef1 * by - coef2 * bx
    c = coef1 * cy - coef2 * cx
    d = coef1 * (y0 - bb) - coef2 * (x0 - dd)

    roots = root_wrapper(a, b, c, d)
    retval = []
    for i in roots:
        if isinstance(i, complex) and i.imag == 0:
            i = i.real
        if not isinstance(i, complex) and 0 <= i <= 1:
            retval.append(bezierpointatt(bez, i))
    return retval


def bezierpointatt(bez, t):
    """Get coords at the given time point along a bezier curve"""
    ax, ay, bx, by, cx, cy, x0, y0 = bezierparameterize(bez)
    x = ax * (t**3) + bx * (t**2) + cx * t + x0
    y = ay * (t**3) + by * (t**2) + cy * t + y0
    return x, y


def bezierslopeatt(bez, t):
    """Get slope at the given time point along a bezier curve
        The slope is computed as (dx, dy) where dx = df_x(t)/dt and dy = df_y(t)/dt.
        Note that for lines P1=P2 and P3=P4, so the slope at the end points is dx=dy=0
        (slope not defined).

    Args:
        bez (List[Tuple[float, float]]): the Bezier curve. The elements of the list the
            coordinates of the points (in this order): Start point, Start control point,
            End control point, End point.
        t (float): time in the interval [0, 1]

    Returns:
        Tuple[float, float]: x and y increment
    """
    ax, ay, bx, by, cx, cy, _, _ = bezierparameterize(bez)
    dx = 3 * ax * (t**2) + 2 * bx * t + cx
    dy = 3 * ay * (t**2) + 2 * by * t + cy
    return dx, dy


def beziertatslope(bez, d):
    """Reverse; get time from slope along a bezier curve"""
    ax, ay, bx, by, cx, cy, _, _ = bezierparameterize(bez)
    (dy, dx) = d
    # quadratic coefficients of slope formula
    if dx:
        slope = 1.0 * (dy / dx)
        a = 3 * ay - 3 * ax * slope
        b = 2 * by - 2 * bx * slope
        c = cy - cx * slope
    elif dy:
        slope = 1.0 * (dx / dy)
        a = 3 * ax - 3 * ay * slope
        b = 2 * bx - 2 * by * slope
        c = cx - cy * slope
    else:
        return []

    roots = root_wrapper(0, a, b, c)
    retval = []
    for i in roots:
        if isinstance(i, complex) and i.imag == 0:
            i = i.real
        if not isinstance(i, complex) and 0 <= i <= 1:
            retval.append(i)
    return retval


def tpoint(p1, p2, t):
    """Linearly interpolate between p1 and p2.

    t = 0.0 returns p1, t = 1.0 returns p2.

    :return: Interpolated point
    :rtype: tuple

    :param p1: First point as sequence of two floats
    :param p2: Second point as sequence of two floats
    :param t: Number between 0.0 and 1.0
    :type t: float
    """
    x1, y1 = p1
    x2, y2 = p2
    return x1 + t * (x2 - x1), y1 + t * (y2 - y1)


def beziersplitatt(bez, t):
    """Split bezier at given time"""
    ((bx0, by0), (bx1, by1), (bx2, by2), (bx3, by3)) = bez
    m1 = tpoint((bx0, by0), (bx1, by1), t)
    m2 = tpoint((bx1, by1), (bx2, by2), t)
    m3 = tpoint((bx2, by2), (bx3, by3), t)
    m4 = tpoint(m1, m2, t)
    m5 = tpoint(m2, m3, t)
    m = tpoint(m4, m5, t)

    return ((bx0, by0), m1, m4, m), (m, m5, m3, (bx3, by3))


def addifclose(bez, l, error=0.001):
    """Gravesen, Add if the line is closed, in-place addition to array l"""
    box = 0
    for i in range(1, 4):
        box += pointdistance(bez[i - 1], bez[i])
    chord = pointdistance(bez[0], bez[3])
    if (box - chord) > error:
        first, second = beziersplitatt(bez, 0.5)
        addifclose(first, l, error)
        addifclose(second, l, error)
    else:
        l[0] += (box / 2.0) + (chord / 2.0)


# balfax, balfbx, balfcx, balfay, balfby, balfcy = 0, 0, 0, 0, 0, 0


def balf(t, args):
    """Bezier Arc Length Function"""
    ax, bx, cx, ay, by, cy = args
    retval = (ax * (t**2) + bx * t + cx) ** 2 + (ay * (t**2) + by * t + cy) ** 2
    return math.sqrt(retval)


def simpson(start, end, maxiter, tolerance, bezier_args):
    """Calculate the length of a bezier curve using Simpson's algorithm:
    http://steve.hollasch.net/cgindex/curves/cbezarclen.html

    Args:
        start (int): Start time (between 0 and 1)
        end (int): End time (between start time and 1)
        maxiter (int): Maximum number of iterations. If not a power of 2, the algorithm
        will behave like the value is set to the next power of 2.
        tolerance (float):  maximum error ratio
        bezier_args (list): arguments as computed by bezierparametrize()

    Returns:
        float: the appoximate length of the bezier curve
    """

    n = 2
    multiplier = (end - start) / 6.0
    endsum = balf(start, bezier_args) + balf(end, bezier_args)
    interval = (end - start) / 2.0
    asum = 0.0
    bsum = balf(start + interval, bezier_args)
    est1 = multiplier * (endsum + (2.0 * asum) + (4.0 * bsum))
    est0 = 2.0 * est1
    # print(multiplier, endsum, interval, asum, bsum, est1, est0)
    while n < maxiter and abs(est1 - est0) > tolerance:
        n *= 2
        multiplier /= 2.0
        interval /= 2.0
        asum += bsum
        bsum = 0.0
        est0 = est1
        for i in range(1, n, 2):
            bsum += balf(start + (i * interval), bezier_args)
            est1 = multiplier * (endsum + (2.0 * asum) + (4.0 * bsum))
    # print(multiplier, endsum, interval, asum, bsum, est1, est0)
    return est1


def bezierlength(bez, tolerance=0.001, time=1.0):
    """Get length of bezier curve"""
    ax, ay, bx, by, cx, cy, _, _ = bezierparameterize(bez)
    return simpson(0.0, time, 4096, tolerance, [3 * ax, 2 * bx, cx, 3 * ay, 2 * by, cy])


def beziertatlength(bez, l=0.5, tolerance=0.001):
    """Get bezier curve time at the length specified"""
    curlen = bezierlength(bez, tolerance, 1.0)
    time = 1.0
    tdiv = time
    targetlen = l * curlen
    diff = curlen - targetlen
    while abs(diff) > tolerance:
        tdiv /= 2.0
        if diff < 0:
            time += tdiv
        else:
            time -= tdiv
        curlen = bezierlength(bez, tolerance, time)
        diff = curlen - targetlen
    return time


def maxdist(bez):
    """Get maximum distance within bezier curve"""
    seg = DirectedLineSegment(bez[0], bez[3])
    return max(seg.distance_to_point(*bez[1]), seg.distance_to_point(*bez[2]))


def cspsubdiv(csp, flat):
    """Sub-divide cubic sub-paths"""
    for sp in csp:
        subdiv(sp, flat)


def subdiv(sp, flat, i=1):
    """sub divide bezier curve"""
    while i < len(sp):
        p0 = sp[i - 1][1]
        p1 = sp[i - 1][2]
        p2 = sp[i][0]
        p3 = sp[i][1]

        bez = (p0, p1, p2, p3)
        mdist = maxdist(bez)
        if mdist <= flat:
            i += 1
        else:
            one, two = beziersplitatt(bez, 0.5)
            sp[i - 1][2] = one[1]
            sp[i][0] = two[2]
            p = [one[2], one[3], two[1]]
            sp[i:1] = [p]


def csparea(csp):
    """Get area in cubic sub-path"""
    MAT_AREA = numpy.array(
        [[0, 2, 1, -3], [-2, 0, 1, 1], [-1, -1, 0, 2], [3, -1, -2, 0]]
    )
    area = 0.0
    for sp in csp:
        if len(sp) < 2:
            continue
        for x, coord in enumerate(sp):  # calculate polygon area
            area += 0.5 * sp[x - 1][1][0] * (coord[1][1] - sp[x - 2][1][1])
        for i in range(1, len(sp)):  # add contribution from cubic Bezier
            vec_x = numpy.array(
                [sp[i - 1][1][0], sp[i - 1][2][0], sp[i][0][0], sp[i][1][0]]
            )
            vec_y = numpy.array(
                [sp[i - 1][1][1], sp[i - 1][2][1], sp[i][0][1], sp[i][1][1]]
            )
            vex = numpy.matmul(vec_x, MAT_AREA)
            area += 0.15 * numpy.matmul(vex, vec_y.T)
    return -area


def cspcofm(csp):
    """Get cubic sub-path coefficient"""
    MAT_COFM_0 = numpy.array(
        [[0, 35, 10, -45], [-35, 0, 12, 23], [-10, -12, 0, 22], [45, -23, -22, 0]]
    )

    MAT_COFM_1 = numpy.array(
        [[0, 15, 3, -18], [-15, 0, 9, 6], [-3, -9, 0, 12], [18, -6, -12, 0]]
    )

    MAT_COFM_2 = numpy.array(
        [[0, 12, 6, -18], [-12, 0, 9, 3], [-6, -9, 0, 15], [18, -3, -15, 0]]
    )

    MAT_COFM_3 = numpy.array(
        [[0, 22, 23, -45], [-22, 0, 12, 10], [-23, -12, 0, 35], [45, -10, -35, 0]]
    )
    area = csparea(csp)
    xc = 0.0
    yc = 0.0
    if abs(area) < 1.0e-8:
        raise ValueError(_("Area is zero, cannot calculate Center of Mass"))
    for sp in csp:
        for x, coord in enumerate(sp):  # calculate polygon moment
            xc += (
                sp[x - 1][1][1]
                * (sp[x - 2][1][0] - coord[1][0])
                * (sp[x - 2][1][0] + sp[x - 1][1][0] + coord[1][0])
                / 6
            )
            yc += (
                sp[x - 1][1][0]
                * (coord[1][1] - sp[x - 2][1][1])
                * (sp[x - 2][1][1] + sp[x - 1][1][1] + coord[1][1])
                / 6
            )
        for i in range(1, len(sp)):  # add contribution from cubic Bezier
            vec_x = numpy.array(
                [sp[i - 1][1][0], sp[i - 1][2][0], sp[i][0][0], sp[i][1][0]]
            )
            vec_y = numpy.array(
                [sp[i - 1][1][1], sp[i - 1][2][1], sp[i][0][1], sp[i][1][1]]
            )

            def _mul(MAT, vec_x=vec_x, vec_y=vec_y):
                return numpy.matmul(numpy.matmul(vec_x, MAT), vec_y.T)

            vec_t = numpy.array(
                [_mul(MAT_COFM_0), _mul(MAT_COFM_1), _mul(MAT_COFM_2), _mul(MAT_COFM_3)]
            )
            xc += numpy.matmul(vec_x, vec_t.T) / 280
            yc += numpy.matmul(vec_y, vec_t.T) / 280
    return -xc / area, -yc / area
