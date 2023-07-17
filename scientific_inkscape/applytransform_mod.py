#!/usr/bin/env python3
#
# License: GPL2
# Copyright Mark "Klowner" Riedesel
# https://github.com/Klowner/inkscape-applytransforms
# Modified by David Burghoff

import inkex
import math, re
from inkex.paths import CubicSuperPath, Path
from inkex.transforms import Transform
from inkex import Line, Rectangle, Polygon, Polyline, Ellipse, Circle

import os, sys
sys.path.append(os.path.dirname(os.path.realpath(sys.argv[0])))  # make sure my directory is on the path
import dhelpers as dh

Itr = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

# @staticmethod
def remove_attrs(el):
    if el.tag == inkex.addNS("g", "svg"):
        return el
    if el.tag == inkex.addNS("path", "svg") or el.tag == "path":
        for attName in el.attrib.keys():
            if (
                (("sodipodi" in attName)
                or ("inkscape" in attName))
                and 'inkscape-academic' not in attName and 'inkscape-scientific' not in attName):
                del el.attrib[attName]
        return el
    return el

# Scale stroke width and dashes
def applyToStrokes(el, tf):
    if "style" in el.attrib:
        style = el.cstyle
        update = False
        if "stroke-width" in style:
            try:
                stroke_width = dh.ipx(style.get("stroke-width"))
                stroke_width *= math.sqrt(
                    abs(tf.a * tf.d - tf.b * tf.c)
                )
                style["stroke-width"] = str(stroke_width)
                update = True
            except AttributeError:
                pass
        if "stroke-dasharray" in style:
            try:
                strokedasharray = style.get("stroke-dasharray")
                if strokedasharray.lower() != "none":
                    strokedasharray = dh.listsplit(style.get("stroke-dasharray"))
                    strokedasharray = [
                        sdv
                        * math.sqrt(abs(tf.a * tf.d - tf.b * tf.c))
                        for sdv in strokedasharray
                    ]
                    style["stroke-dasharray"] = (
                        str(strokedasharray).strip("[").strip("]")
                    )
                    update = True
            except AttributeError:
                pass
        if update:
            el.cstyle = style

def transform_clipmask(el, mask=False):
    if not (mask):
        cm = "clip-path"
    else:
        cm = "mask"
    clippathurl = el.get(cm)
    if clippathurl is not None and el.ctransform is not None:
        svg = el.croot
        clippath = svg.getElementById(clippathurl[5:-1])
        if clippath is not None:
            d = clippath.duplicate()
            clippathurl = "url(#" + d.get_id() + ")"
            el.set(cm, clippathurl)
            dh.fix_css_clipmask(el, mask=mask)
            for k in d.getchildren():
                if k.ctransform is not None:
                    tr = el.ctransform @ k.ctransform
                else:
                    tr = el.ctransform
                k.ctransform = tr
             
def fuseTransform(el, transf=Itr, irange=None, trange=None, applytostroke=True):
    # Fuses an object's transform to its path, adding the additional transformation transf
    # When applytostroke enabled, transform goes onto stroke/dashes, keeping it looking the same
    # Without it, it is applied to the points only

    if el.tag in dh.otp_support_tags:  # supported types
        # Since transforms apply to an object's clips, before applying the transform
        # we will need to duplicate the clip path and transform it
        transform_clipmask(el, mask=False)
        transform_clipmask(el, mask=True)

        transf = Transform(transf) @ el.ctransform
        el.ctransform = None
        el = remove_attrs(el)

        if not (transf.b == 0 and transf.c == 0) and isinstance(
            el, (Rectangle, Ellipse, Circle)
        ):
            # Rectangles, Ellipses, and Circles need to be converted to paths if there is shear/rotation
            dh.object_to_path(el)

        if not(transf == Itr and irange is None and trange is None):
            # Don't do anything if there is effectively no transform applied
            if "d" in el.attrib:
                d = el.get("d")
                try:
                    p = CubicSuperPath(d)
                except ZeroDivisionError:
                    p = Path(d)
                if irange is None:
                    p = Path(p).to_absolute().transform(transf, True)
                if irange is not None:
                    p = Path(p).to_absolute()
                    pnew = []
                    for ii in range(len(irange)):
                        xf = (
                            trange[ii] @ el.ctransform
                        )  # Transform(el.get("transform", None))
                        pnew += Path(p[irange[ii][0] : irange[ii][1]]).transform(
                            xf, True
                        )
                    p = pnew
                
                try:
                    p2 = str(Path(CubicSuperPath(p).to_path()))
                except ZeroDivisionError:
                    p2 = str(Path(p))
                el.set("d",p2)
            elif isinstance(
                el, (Polygon, Polyline)
            ):  # el.tag in [inkex.addNS('polygon', 'svg'), inkex.addNS('polyline', 'svg')]:
                points = el.get("points")
                points = points.strip().split(" ")
                for k, p in enumerate(points):
                    if "," in p:
                        p = p.split(",")
                        p = [float(p[0]), float(p[1])]
                        p = transf.apply_to_point(p)
                        p = [str(p[0]), str(p[1])]
                        p = ",".join(p)
                        points[k] = p
                points = " ".join(points)
                el.set("points", points)
            elif isinstance(
                el, (Ellipse, Circle)
            ):  # el.tag in [inkex.addNS("ellipse", "svg"), inkex.addNS("circle", "svg")]:

                def isequal(a, b):
                    return abs(a - b) <= transf.absolute_tolerance

                if el.tag == inkex.addNS('ellipse','svg'): #"{http://www.w3.org/2000/svg}ellipse":
                    rx = dh.ipx(el.get("rx"))
                    ry = dh.ipx(el.get("ry"))
                else:
                    rx = dh.ipx(el.get("r"))
                    ry = rx
                cx = dh.ipx(el.get("cx"))
                cy = dh.ipx(el.get("cy"))
                sqxy1 = (cx - rx, cy - ry)
                sqxy2 = (cx + rx, cy - ry)
                sqxy3 = (cx + rx, cy + ry)
                newxy1 = transf.apply_to_point(sqxy1)
                newxy2 = transf.apply_to_point(sqxy2)
                newxy3 = transf.apply_to_point(sqxy3)
                el.set("cx", (newxy1[0] + newxy3[0]) / 2)
                el.set("cy", (newxy1[1] + newxy3[1]) / 2)
                edgex = math.sqrt(
                    abs(newxy1[0] - newxy2[0]) ** 2
                    + abs(newxy1[1] - newxy2[1]) ** 2
                )
                edgey = math.sqrt(
                    abs(newxy2[0] - newxy3[0]) ** 2
                    + abs(newxy2[1] - newxy3[1]) ** 2
                )

                if isequal(edgex, edgey):
                    el.tag = inkex.addNS('circle','svg') #"{http://www.w3.org/2000/svg}circle"
                    el.set("rx", None)
                    el.set("ry", None)
                    el.set("r", edgex / 2)
                else:
                    el.tag = inkex.addNS('ellipse','svg') #"{http://www.w3.org/2000/svg}ellipse"
                    el.set("rx", edgex / 2)
                    el.set("ry", edgey / 2)
                    el.set("r", None)

            # Modficiations by David Burghoff: Added support for lines, rectangles, polylines
            elif isinstance(el, Line):
                x1 = dh.ipx(el.get("x1"))
                x2 = dh.ipx(el.get("x2"))
                y1 = dh.ipx(el.get("y1"))
                y2 = dh.ipx(el.get("y2"))
                p1 = transf.apply_to_point([x1, y1])
                p2 = transf.apply_to_point([x2, y2])
                el.set("x1", str(p1[0]))
                el.set("y1", str(p1[1]))
                el.set("x2", str(p2[0]))
                el.set("y2", str(p2[1]))

            elif isinstance(el, Rectangle):
                x = dh.ipx(el.get("x"))
                y = dh.ipx(el.get("y"))
                w = dh.ipx(el.get("width"))
                h = dh.ipx(el.get("height"))
                pts = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]
                xs = []
                ys = []
                for p in pts:
                    p = transf.apply_to_point(p)
                    xs.append(p.x)
                    ys.append(p.y)
                el.set("x", str(min(xs)))
                el.set("y", str(min(ys)))
                el.set("width", str(max(xs) - min(xs)))
                el.set("height", str(max(ys) - min(ys)))

            if applytostroke:
                applyToStrokes(el, transf)
                
            
            # Duplicate any gradient and apply the transform
            for sf in ['fill','stroke']:
                sfel = el.cstyle.get_link(sf,svg=el.croot)
                if sfel is not None and 'gradient' in sfel.tag.lower():
                    d = sfel.duplicate()
                    # dh.Set_Style_Comp(el,sf,'url(#{0})'.format(d.get_id()))
                    el.cstyle[sf]='url(#{0})'.format(d.get_id())
                    gt = d.get('gradientTransform');
                    gt = Transform(gt) if gt is not None else Itr
                    d.set('gradientTransform',str(transf @ gt))

        for child in list(el):
            fuseTransform(child, transf)