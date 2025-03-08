#!/usr/bin/env python
# coding=utf-8
#
# Copyright (c) 2023 David Burghoff <burghoff@utexas.edu>
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

import dhelpers as dh
import inkex
from inkex import Transform
import math, copy
from dhelpers import bbox
from inkex.text.utils import uniquetol

It = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

# Define global tags
PATHLIKE_TAGS = [
    inkex.PathElement.ctag,
    inkex.Rectangle.ctag,
    inkex.Line.ctag,
    inkex.Polyline.ctag,
]
RECTANGLE_TAG = inkex.Rectangle.ctag
TEXTLIKE_TAGS = [inkex.TextElement.ctag, inkex.FlowRoot.ctag]
GROUP_TAG = inkex.Group.ctag
EXCLUDE_TAGS = [
    inkex.Tspan.ctag,
    inkex.NamedView.ctag,
    inkex.Defs.ctag,
    inkex.Metadata.ctag,
    inkex.ForeignObject.ctag,
]


def geometric_bbox(el, vis_bbox, irange=None):
    gbb = copy.copy(vis_bbox)
    if el.tag in PATHLIKE_TAGS:  # if path-like, use nodes instead
        xs, ys = dh.get_points(el, irange=irange)
        # For clipped objects the list of points is a bad description of the
        # geometric bounding box. As a rough workaround, use the visual bbox if
        # its limits are smaller than the geometric bbox. I think this is almost
        # always fine since clips use the geometric bbox.
        minx = max(min(xs), vis_bbox[0])
        maxx = min(max(xs), vis_bbox[0] + vis_bbox[2])
        miny = max(min(ys), vis_bbox[1])
        maxy = min(max(ys), vis_bbox[1] + vis_bbox[3])
        gbb = [minx, miny, maxx - minx, maxy - miny]  # geometric bounding box
    return bbox(gbb)


# Determines plot area from a list of elements and their geometric bounding boxes
def Find_Plot_Area(els, gbbs):
    vl = dict()  # vertical lines
    hl = dict()  # horizontal lines
    boxes = dict()
    solids = dict()
    plotareas = dict()
    for el in list(reversed(els)):
        isrect = False
        if el.tag in PATHLIKE_TAGS:
            gbb = gbbs[el.get_id()]
            xs, ys = dh.get_points(el)
            if (max(xs) - min(xs)) < 0.001 * gbb[3]:
                vl[el.get_id()] = gbb
            if (max(ys) - min(ys)) < 0.001 * gbb[2]:
                hl[el.get_id()] = gbb

            tol = 1e-3 * max(max(xs) - min(xs), max(ys) - min(ys))
            if (
                3 <= len(xs) <= 5
                and len(uniquetol(xs, tol)) == 2
                and len(uniquetol(ys, tol)) == 2
            ):
                isrect = True
        if isrect or el.tag == RECTANGLE_TAG:
            sf = dh.get_strokefill(el)
            hasfill = sf.fill is not None and sf.fill != [255, 255, 255, 1]
            hasstroke = sf.stroke is not None and sf.stroke != [255, 255, 255, 1]

            if hasfill and (not (hasstroke) or sf.stroke == sf.fill):  # solid rectangle
                solids[el.get_id()] = gbb
            elif hasstroke:  # framed rectangle
                boxes[el.get_id()] = gbb

        if el.get("inkscape-scientific-scaletype") == "plot_area":
            plotareas[el.get_id()] = gbb

    vels = dict()
    hels = dict()
    for k, gbb in vl.items():
        vels[k] = gbb[3]
    for k, gbb in hl.items():
        hels[k] = gbb[2]
    for k, gbb in boxes.items():
        hels[k] = gbb[2]
        vels[k] = gbb[3]
    for k, gbb in plotareas.items():
        hels[k] = gbb[2]
        vels[k] = gbb[3]

    lvel = lhel = None
    if len(vels) != 0:
        lvel = max(vels, key=vels.get)  # largest vertical
    if len(hels) != 0:
        lhel = max(hels, key=hels.get)  # largest horizontal
    return vl, hl, lvel, lhel


# Get the proper suffix for an integer (1st, 2nd, 3rd, etc.)
def appendInt(num):
    if num > 9:
        secondToLastDigit = str(num)[-2]
        if secondToLastDigit == "1":
            return "th"
    lastDigit = num % 10
    if lastDigit == 1:
        return "st"
    elif lastDigit == 2:
        return "nd"
    elif lastDigit == 3:
        return "rd"
    else:
        return "th"


def trtf(x, y):
    return Transform("translate(" + str(x) + ", " + str(y) + ")")


def sctf(x, y):
    return Transform("scale(" + str(x) + ", " + str(y) + ")")


class ScalePlots(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument(
            "--hscale", type=float, default=100, help="Horizontal scaling"
        )
        pars.add_argument("--vscale", type=float, default=100, help="Vertical scaling")
        pars.add_argument(
            "--figuremode", type=int, default=1, help="Scale by bounding box?"
        )
        pars.add_argument("--matchprop", type=int, default=1, help="Match what?")
        pars.add_argument(
            "--hmatchopts", type=int, default=1, help="Horizontal matching"
        )
        pars.add_argument("--vmatchopts", type=int, default=1, help="Vertical matching")
        pars.add_argument(
            "--deletematch",
            type=inkex.Boolean,
            default=False,
            help="Delete first selection?",
        )
        pars.add_argument("--marksf", type=int, default=1, help="Mark objects as")
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument(
            "--tickcorrect", type=inkex.Boolean, default=True, help="Auto tick correct?"
        )
        pars.add_argument(
            "--tickthreshold", type=int, default=10, help="Tick threshold"
        )
        pars.add_argument(
            "--wholeplot1",
            type=inkex.Boolean,
            default=False,
            help="Treat whole selection as plot area?",
        )
        pars.add_argument(
            "--wholeplot2",
            type=inkex.Boolean,
            default=False,
            help="Treat whole selection as plot area?",
        )
        pars.add_argument(
            "--wholeplot3",
            type=inkex.Boolean,
            default=False,
            help="Treat whole selection as plot area?",
        )

    def effect(self):
        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        sel = [k for k in sel if k.tag not in EXCLUDE_TAGS]
        # regular selectable objects only

        itag = inkex.Image.ctag
        if all([el.tag == itag for el in sel]) and self.options.tab != "options":
            inkex.utils.errormsg(
                "Thanks for using Scientific Inkscape!\n\n"
                "It appears that you're attempting to scale a raster Image object. Please note that "
                "Inkscape is mainly for working with vector images, not raster images. Vector images "
                "preserve all of the information used to generate them, whereas raster images do not. "
                "Read about the difference here: \nhttps://en.wikipedia.org/wiki/Vector_graphics\n\n"
                "Unfortunately, this means that there is not much Scale Plots can do to edit raster images "
                "beyond simple stretching or scaling. If you want to edit a raster image, you will need to "
                "use a program like Photoshop or GIMP."
            )
            quit()

        tickcorrect = self.options.tickcorrect
        tickthr = self.options.tickthreshold / 100
        # layerfix = self.options.layerfix
        if self.options.tab == "scaling":
            hscale = self.options.hscale
            vscale = self.options.vscale
            scalex = hscale / 100
            scaley = vscale / 100
            wholesel = self.options.wholeplot1
        elif self.options.tab == "matching":
            hmatch = self.options.hmatchopts in [2, 3]
            vmatch = self.options.vmatchopts in [2, 3]
            matchxpos = self.options.hmatchopts == 3
            matchypos = self.options.vmatchopts == 3
            wholesel = self.options.wholeplot2
        elif self.options.tab == "correction":
            scalex = 1
            scaley = 1
            wholesel = self.options.wholeplot3
            if not all(k.tag == GROUP_TAG for k in sel):
                inkex.utils.errormsg(
                    "Correction mode requires that every selected object be a group that has already been scaled."
                )

                return
        else:
            self.options.marksf = {
                1: "scale_free",
                2: "aspect_locked",
                3: "normal",
                4: "plot_area",
                5: None,
            }[self.options.marksf]
            for el in sel:
                el.set("inkscape-scientific-scaletype", self.options.marksf)
            return
        self.options.matchwhat = {1: "plotarea", 2: "bbox"}[self.options.matchprop]
        self.options.matchto = {1: "plotarea", 2: "bbox"}[self.options.matchprop]
        self.options.figuremode = {1: False, 2: True}[self.options.figuremode]

        if wholesel:
            tickcorrect = False

        dsfels = []  # designated scale-free els, whether or not they're selected

        # full visual bbs
        fbbs = dh.BB2(self.svg, dh.unique([d for el in sel for d in el.descendants2()]))
        firstsel = sel[0]
        if self.options.tab == "matching":
            sel = sel[1:]

        all_pels = [sel]
        if all(k.tag == GROUP_TAG for k in sel):  # grouped mode
            trs = [s.ctransform for s in sel]
            # for correction mode
            all_pels = [list(s) for s in sel]

        for i0 in range(len(all_pels)):  # sel in asel:
            pels = [
                k for k in all_pels[i0] if k.get_id() in list(fbbs.keys())
            ]  # plot elements list

            # Calculate geometric (tight) bounding boxes of plot elements
            gbbs = dict()
            for el in [firstsel] + pels + dsfels + list(firstsel):
                if el.get_id() in fbbs:
                    gbbs[el.get_id()] = geometric_bbox(el, fbbs[el.get_id()]).sbb

            vl, hl, lvel, lhel = Find_Plot_Area(pels, gbbs)
            if lvel is None or lhel is None or wholesel:
                noplotarea = True
                lvel = None
                lhel = None
                if not (wholesel):
                    # Display warning message
                    numgroup = str(i0 + 1) + appendInt(i0 + 1)
                    inkex.utils.errormsg(
                        "A box-like plot area could not be automatically detected on the "
                        + numgroup
                        + " selected plot (group ID "
                        + sel[i0].get_id()
                        + ").\n\nDraw a box with a stroke to define the plot area or mark objects as plot area-determining in the Advanced tab."
                        + "\nScaling will still be performed, but the results may not be ideal."
                    )
            else:
                noplotarea = False

            # A class that contains geometric and full bounding boxes
            class bbox2:
                def __init__(self, g, f):
                    if isinstance(g, list) or g is None:
                        g = bbox(g)
                    if isinstance(f, list) or f is None:
                        f = bbox(f)
                    self.g = g
                    self.f = f

                def union(self, g, f):
                    return bbox2(self.g.union(g), self.f.union(f))

            bba = bbox2(None, None)
            # all elements
            bbp = bbox2(None, None)
            # plot area
            for el in pels:
                bba = bba.union(gbbs[el.get_id()], fbbs[el.get_id()])
                if el.get_id() in [lvel, lhel] or noplotarea:
                    bbp = bbp.union(gbbs[el.get_id()], fbbs[el.get_id()])

            if self.options.tab == "correction":
                # Invert the existing transform so we can run the rest of the code regularly
                extr = trs[i0]
                # existing transform

                sx = math.sqrt(extr.a**2 + extr.b**2)
                sy = (-extr.b * extr.c + extr.a * extr.d) / math.sqrt(
                    extr.a**2 + extr.b**2
                )
                if sx < 0:
                    sx = -sx
                    sy = -sy
                scalex = sx
                scaley = sy
                # allow for rotations

                if not (self.options.figuremode):
                    refx = bbp.g.xc
                    refy = bbp.g.yc
                else:
                    refx = bba.f.x1
                    refy = bba.f.y1
                trl = trtf(refx, refy)
                scl = sctf(1 / scalex, 1 / scaley)
                iextr = trl @ scl @ (-trl)
                # invert existing transform
                dh.global_transform(sel[i0], iextr)

                # Invert the transform on the bounding boxes (fix later)
                actfbbs = {k: v for k, v in fbbs.items()}
                actgbbs = {k: v for k, v in gbbs.items()}
                fbbs = {k: bbox(v).transform(iextr).sbb for k, v in fbbs.items()}
                gbbs = {k: bbox(v).transform(iextr).sbb for k, v in gbbs.items()}
                tr_bba = bba
                # bb with transform to be corrected

                bba = bbox2(None, None)
                # bbox of all elements
                bbp = bbox2(None, None)
                # bbox of plot area
                for el in pels:
                    bba = bba.union(gbbs[el.get_id()], fbbs[el.get_id()])
                    if el.get_id() in [lvel, lhel] or noplotarea:
                        bbp = bbp.union(gbbs[el.get_id()], fbbs[el.get_id()])

                if self.options.figuremode:
                    oscalex = scalex
                    oscaley = scaley
                    scalex = (
                        (tr_bba.f.x2 - tr_bba.f.x1)
                        - (bba.f.x2 - bba.f.x1 - (bbp.g.x2 - bbp.g.x1))
                    ) / (bbp.g.x2 - bbp.g.x1)
                    scaley = (
                        (tr_bba.f.y2 - tr_bba.f.y1)
                        - (bba.f.y2 - bba.f.y1 - (bbp.g.y2 - bbp.g.y1))
                    ) / (bbp.g.y2 - bbp.g.y1)

                    tlx = (tr_bba.f.x1 - refx) / oscalex + refx
                    # where top left is now
                    dxl = bbp.g.x1 - tlx
                    if scalex != 1:
                        refx = (tr_bba.f.x1 + dxl - bbp.g.x1 * scalex) / (1 - scalex)
                        # what refx needs to be to maintain top-left
                    else:
                        refx = tr_bba.f.x1 + dxl

                    tly = (tr_bba.f.y1 - refy) / oscaley + refy
                    # where top left is now
                    dyl = bbp.g.y1 - tly
                    if scaley != 1:
                        refy = (tr_bba.f.y1 + dyl - bbp.g.y1 * scaley) / (1 - scaley)
                        # what refx needs to be to maintain top-left
                    else:
                        refy = tr_bba.f.y1 + dyl

            if self.options.tab == "matching":
                bbmatch = None
                if self.options.matchto == "bbox":
                    bbmatch = bbox(gbbs[firstsel.get_id()])
                elif self.options.matchto == "plotarea":
                    if firstsel.tag == GROUP_TAG:
                        plotareaels = list(firstsel)
                    else:
                        plotareaels = [firstsel]

                    vl0, hl0, lvel0, lhel0 = Find_Plot_Area(plotareaels, gbbs)
                    if lvel0 is None or lhel0 is None:
                        inkex.utils.errormsg(
                            "A box-like plot area could not be automatically detected on the "
                            + "first selected object (ID "
                            + firstsel.get_id()
                            + ").\n\nIts bounding box will be matched instead. If this is not ideal,"
                            + " draw an outlined box to define the plot area or mark objects as plot area-determining in the Advanced tab.\n"
                        )
                        bbmatch = bbox(gbbs[firstsel.get_id()])
                    else:
                        bbmatch = bbox(gbbs[lvel0]).union(bbox(gbbs[lhel0]))

                scalex = scaley = 1
                if hmatch:
                    if self.options.matchwhat == "plotarea":
                        scalex = bbmatch.w / bbp.g.w
                    elif self.options.matchwhat == "bbox":
                        scalex = (bbmatch.w + bbp.g.w - bba.g.w) / bbp.g.w
                if vmatch:
                    if self.options.matchwhat == "plotarea":
                        scaley = bbmatch.h / bbp.g.h
                    elif self.options.matchwhat == "bbox":
                        scaley = (bbmatch.h + bbp.g.h - bba.g.h) / bbp.g.h

            # Compute global transformation
            if self.options.tab != "correction":
                if self.options.matchwhat == 'plotarea':
                    refx = bbp.g.xc
                    refy = bbp.g.yc
                else:
                    refx = bba.g.xc
                    refy = bba.g.yc

            finx = refx  # final x
            finy = refy  # final y
            if self.options.tab == "matching":
                if matchxpos:
                    finx = bbmatch.xc
                if matchypos:
                    finy = bbmatch.yc
                if self.options.matchwhat == "bbox":
                    # Following scaling, margins stay the same size so the
                    # bounding box center has moved
                    finx -= 1/2*( (bba.g.x2 - bbp.g.x2) - (bbp.g.x1 - bba.g.x1)) * (1-scalex)
                    finy -= 1/2*( (bba.g.y2 - bbp.g.y2) - (bbp.g.y1 - bba.g.y1)) * (1-scaley)

            gtr = trtf(finx, finy) @ sctf(scalex, scaley) @ (-trtf(refx, refy))
            # global transformation
            iscl = sctf(1 / scalex, 1 / scaley)  # inverse scale
            liscl = (
                sctf(math.sqrt(scalex * scaley), math.sqrt(scalex * scaley)) @ iscl
            )  # aspect-scaled and inverse scaled
            trul = gtr.apply_to_point([bbp.g.x1, bbp.g.y1])  # transformed upper-left
            trbr = gtr.apply_to_point([bbp.g.x2, bbp.g.y2])  # transformed bottom-right

            # Diagnostic mode
            diagmode = False
            if diagmode:
                r = inkex.Rectangle()
                r.set("x", bbp.g.x1)
                r.set("y", bbp.g.y1)
                r.set("width", abs(bbp.g.x2 - bbp.g.x1))
                r.set("height", abs(bbp.g.y2 - bbp.g.y1))
                r.cstyle = "fill-opacity:0.5"
                self.svg.append(r)
                dh.global_transform(r, gtr)
                dh.debug("Largest vertical line: " + lvel)
                dh.debug("Largest horizontal line: " + lhel)

            # Make a list of elements to be transformed
            sclels = []
            for el in pels:
                if el not in sclels:
                    sclels.append(el)

            # Apply transform and compute corrections (if needed)
            for el in sclels:
                dh.global_transform(el, gtr)
                # apply the transform

                elid = el.get_id()
                gbb = gbbs[elid]
                fbb = fbbs[elid]

                if el.tag in TEXTLIKE_TAGS + [GROUP_TAG] or el in dsfels:
                    stype = "scale_free"
                else:
                    stype = "normal"

                mtype = el.get("inkscape-scientific-scaletype")
                if mtype is not None:
                    stype = mtype

                if hasattr(self.options, "hcall") and self.options.hcall:
                    if el.tag in TEXTLIKE_TAGS + [GROUP_TAG]:
                        stype = "normal"

                vtickt = vtickb = htickl = htickr = False
                # el is a tick
                if tickcorrect and (
                    (elid in list(vl.keys())) or (elid in list(hl.keys()))
                ):
                    isvert = elid in list(vl.keys())
                    ishorz = elid in list(hl.keys())
                    gbb = gbbs[elid]
                    if isvert and gbb[3] < tickthr * (
                        bbp.g.y2 - bbp.g.y1
                    ):  # vertical tick
                        if gbb[1] + gbb[3] < bbp.g.y1 + tickthr * (bbp.g.y2 - bbp.g.y1):
                            vtickt = True
                        elif gbb[1] > bbp.g.y2 - tickthr * (bbp.g.y2 - bbp.g.y1):
                            vtickb = True
                    if ishorz and gbb[2] < tickthr * (
                        bbp.g.x2 - bbp.g.x1
                    ):  # horizontal tick
                        if gbb[0] + gbb[2] < bbp.g.x1 + tickthr * (bbp.g.x2 - bbp.g.x1):
                            htickl = True
                        elif gbb[0] > bbp.g.x2 - tickthr * (bbp.g.x2 - bbp.g.x1):
                            htickr = True

                if any([vtickt, vtickb, htickl, htickr]):
                    # If a tick, scale using the edge as a reference point
                    gbb_tr = bbox(gbb).transform(gtr)
                    cx = gbb_tr.xc
                    cy = gbb_tr.yc

                    if vtickt:
                        if cy > trul[1]:
                            trl = trtf(cx, gbb_tr.y1)  # inner tick
                        else:
                            trl = trtf(cx, gbb_tr.y2)  # outer tick
                    elif vtickb:
                        if cy < trbr[1]:
                            trl = trtf(cx, gbb_tr.y2)  # inner tick
                        else:
                            trl = trtf(cx, gbb_tr.y1)  # outer tick
                    elif htickl:
                        if cx > trul[0]:
                            trl = trtf(gbb_tr.x1, cy)  # inner tick
                        else:
                            trl = trtf(gbb_tr.x2, cy)  # outer tick
                    elif htickr:
                        if cx < trbr[0]:
                            trl = trtf(gbb_tr.x2, cy)  # inner tick
                        else:
                            trl = trtf(gbb_tr.x1, cy)  # outer tick
                    tr1 = trl @ iscl @ (-trl)
                    dh.global_transform(el, tr1)
                # elif isalwayscorr or isoutsideplot or issf:
                elif stype in ["scale_free", "aspect_locked"]:
                    # dh.idebug(el.get_id())
                    # Invert the transformation for text/groups, anything outside the plot, scale-free
                    cbc = el.get("inkscape-scientific-combined-by-color")
                    if cbc is None:
                        gbb_tr = bbox(gbb).transform(gtr)
                        cx = gbb_tr.xc
                        cy = gbb_tr.yc
                        trl = trtf(cx, cy)
                        if stype == "scale_free":
                            tr1 = trl @ iscl @ (-trl)
                        else:
                            tr1 = trl @ liscl @ (-trl)

                        # For elements outside the plot area, adjust position to maintain
                        # the distance to the plot area
                        dx = 0
                        dy = 0
                        if cx < trul[0]:
                            ox = gbb[0] + gbb[2] / 2 - bbp.g.x1
                            dx = ox - (cx - trul[0])
                        if cx > trbr[0]:
                            ox = gbb[0] + gbb[2] / 2 - bbp.g.x2
                            dx = ox - (cx - trbr[0])
                        if cy < trul[1]:
                            oy = gbb[1] + gbb[3] / 2 - bbp.g.y1
                            dy = oy - (cy - trul[1])
                        if cy > trbr[1]:
                            oy = gbb[1] + gbb[3] / 2 - bbp.g.y2
                            dy = oy - (cy - trbr[1])
                        tr2 = trtf(dx, dy)
                        dh.global_transform(el, (tr2 @ tr1))

                    else:  # If previously combined, apply to subpaths instead
                        cbc = [int(v) for v in cbc.split()]
                        fbb_tr = bbox(fbb).transform(gtr).sbb
                        irng = []
                        trng = []
                        for ii in range(len(cbc) - 1):
                            gbb_tr = geometric_bbox(
                                el, fbb_tr, irange=[cbc[ii], cbc[ii + 1]]
                            )
                            gbb = gbb_tr.transform(-gtr).sbb
                            cx = gbb_tr.xc
                            cy = gbb_tr.yc
                            trl = trtf(cx, cy)
                            # tr1 = trl @ iscl @ (-trl)
                            if stype == "scale_free":
                                tr1 = trl @ iscl @ (-trl)
                            else:
                                tr1 = trl @ liscl @ (-trl)
                            dx = 0
                            dy = 0
                            if cx < trul[0]:
                                ox = gbb[0] + gbb[2] / 2 - bbp.g.x1
                                dx = ox - (cx - trul[0])
                            if cx > trbr[0]:
                                ox = gbb[0] + gbb[2] / 2 - bbp.g.x2
                                dx = ox - (cx - trbr[0])
                            if cy < trul[1]:
                                oy = gbb[1] + gbb[3] / 2 - bbp.g.y1
                                dy = oy - (cy - trul[1])
                            if cy > trbr[1]:
                                oy = gbb[1] + gbb[3] / 2 - bbp.g.y2
                                dy = oy - (cy - trbr[1])
                            tr2 = trtf(dx, dy)
                            irng.append([cbc[ii], cbc[ii + 1]])
                            trng.append((tr2 @ tr1))
                        dh.global_transform(el, It, irange=irng, trange=trng)

            # restore bbs
            if self.options.tab == "correction":
                fbbs = actfbbs
                gbbs = actgbbs

        if self.options.tab == "matching" and self.options.deletematch:
            firstsel.delete()


if __name__ == "__main__":
    dh.Run_SI_Extension(ScalePlots(), "Scale plots")
