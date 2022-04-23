#!/usr/bin/env python
# coding=utf-8
#
# Copyright (C) 2021 David Burghoff, dburghoff@nd.edu
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

import inkex

from inkex import (
    TextElement,
    FlowRoot,
    FlowPara,
    Tspan,
    TextPath,
    Rectangle,
    addNS,
    Transform,
    PathElement,
    Line,
    Rectangle,
    Path,
    Vector2d,
    Use,
    NamedView,
    Defs,
    Metadata,
    ForeignObject,
    Group,
    SvgDocumentElement,
    Image,
    Polyline,
)

import lxml

import os, sys

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh

import copy

It = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


def geometric_bbox(el, vis_bbox, irange=None):
    gbb = copy.copy(vis_bbox)
    if isinstance(
        el, (PathElement, Rectangle, Line, Polyline)
    ):  # if path-like, use nodes instead
        xs, ys = dh.get_points(el, irange=irange)
        # For clipped objects the list of points is a bad description of the geometric bounding box.
        # As a rough workaround, use the visual bbox if its limits are smaller than the geometric bbox.
        # I think this is almost always fine since clips use the geometric bbox
        minx = max(min(xs), vis_bbox[0])
        maxx = min(max(xs), vis_bbox[0] + vis_bbox[2])
        miny = max(min(ys), vis_bbox[1])
        maxy = min(max(ys), vis_bbox[1] + vis_bbox[3])
        gbb = [minx, miny, maxx - minx, maxy - miny]  # geometric bounding box
    return bbox(gbb)


class bbox:
    def __init__(self, bb):
        self.x1 = bb[0]
        self.x2 = bb[0] + bb[2]
        self.y1 = bb[1]
        self.y2 = bb[1] + bb[3]
        self.xc = (self.x1 + self.x2) / 2
        self.yc = (self.y1 + self.y2) / 2
        self.w = bb[2]
        self.h = bb[3]
        self.sbb = [self.x1, self.y1, self.w, self.h]
        # standard bbox

    def transform(self, xform):
        tr1 = xform.apply_to_point([self.x1, self.y1])
        tr2 = xform.apply_to_point([self.x2, self.y2])
        return bbox(
            [
                min(tr1[0], tr2[0]),
                min(tr1[1], tr2[1]),
                max(tr1[0], tr2[0]) - min(tr1[0], tr2[0]),
                max(tr1[1], tr2[1]) - min(tr1[1], tr2[1]),
            ]
        )


class ScalePlots(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument(
            "--hscale", type=float, default=100, help="Horizontal scaling"
        )
        pars.add_argument("--vscale", type=float, default=100, help="Vertical scaling")
        pars.add_argument("--hdrag", type=int, default=1, help="Horizontal scaling")
        pars.add_argument("--vdrag", type=int, default=1, help="Vertical scaling")

        pars.add_argument(
            "--hmatch",
            type=inkex.Boolean,
            default=100,
            help="Match width of first selected object?",
        )
        pars.add_argument(
            "--vmatch",
            type=inkex.Boolean,
            default=100,
            help="Match height of first selected object?",
        )
        pars.add_argument(
            "--figuremode", type=int, default=1, help="Scale by bounding box?"
        )
        pars.add_argument("--hdrag2", type=int, default=1, help="Horizontal scaling")
        pars.add_argument("--vdrag2", type=int, default=1, help="Vertical scaling")

        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument(
            "--tickcorrect", type=inkex.Boolean, default=True, help="Auto tick correct?"
        )
        pars.add_argument(
            "--tickthreshold", type=int, default=10, help="Tick threshold"
        )
        pars.add_argument(
            "--layerfix",
            type=str,
            default="None",
            help="Layer whose elements should not be scaled",
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
        import random

        random.seed(1)
        # v1 = all([isinstance(el,(str)) for el in self.svg.selection]); # version 1.0 of Inkscape
        # if v1:
        #    inkex.utils.errormsg('Academic-Inkscape requires version 1.1 of Inkscape or higher. Please install the latest version and try again.');
        #    return
        # # gpe= dh.get_mod(self.svg.selection)
        # # sel =[gpe[k] for k in gpe.id_dict().keys()];
        # else:
        #    sel = [v for el in self.svg.selection for v in dh.descendants2(el)];
        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        # should work with both v1.0 and v1.1

        # print([el.get_id2() for el in sel])
        # sel = [v for el in sel for v in dh.descendants2(el)];

        # starttime = time.time();
        # sel = self.svg.selection;                     # an ElementList
        # inkex.utils.debug(sel)
        # sel=[sel[k] for k in sel.id_dict().keys()];
        sel = [
            k
            for k in sel
            if not (isinstance(k, (Tspan, NamedView, Defs, Metadata, ForeignObject)))
        ]
        # regular selectable objects only

        #        import cProfile, pstats, io
        #        from pstats import SortKey
        #        pr = cProfile.Profile()
        #        pr.enable()

        tickcorrect = self.options.tickcorrect
        tickthr = self.options.tickthreshold / 100
        layerfix = self.options.layerfix
        if self.options.tab == "scaling":
            hscale = self.options.hscale
            vscale = self.options.vscale
            hdrag = self.options.hdrag
            vdrag = self.options.vdrag
            scalex = hscale / 100
            scaley = vscale / 100
            matchingmode = False
            wholesel = self.options.wholeplot1
        elif self.options.tab == "matching":
            hdrag = self.options.hdrag2
            vdrag = self.options.vdrag2
            hmatch = self.options.hmatch
            vmatch = self.options.vmatch
            matchingmode = True
            wholesel = self.options.wholeplot2
        elif self.options.tab == "correction":
            hdrag = 1
            vdrag = 1
            scalex = 1
            scaley = 1
            matchingmode = False
            wholesel = self.options.wholeplot3
            if self.options.figuremode == 1:
                figuremode = False
            else:
                figuremode = True
            if not (all([isinstance(k, Group) for k in sel])):
                inkex.utils.errormsg(
                    "Correction mode requires that every selected object be a group that has already been scaled."
                )
                return
        else:
            inkex.utils.errormsg("Select Scaling, Matching, or Correction mode")
            return

        if wholesel:
            tickcorrect = False

        sfgs = []
        sfels = []
        # all scale-free objects, whether or not they're selected
        if not (layerfix == "None"):  # find scale-free objects
            ls = [t.strip() for t in layerfix.split(",")]
            for el in ls:
                lyr = self.svg.getElementByName(el)
                if lyr is None:  # name didn't work, try ID
                    lyr = self.svg.getElementById(el)
                if lyr is not None:
                    if isinstance(lyr, Group):
                        sfgs.append(lyr)
                        sfels = sfels + lyr.getchildren()
                    elif isinstance(lyr, PathElement):
                        sfels.append(lyr)

        fbbs = dh.Get_Bounding_Boxes(self, False)
        # full visual bbs
        firstsel = sel[0]
        if matchingmode:
            sel = sel[1:]
        groupedmode = all([isinstance(k, Group) for k in sel])
        if not (groupedmode):
            asel = [sel]
        else:
            gsel = sel
            # groups
            trs = [Transform(s.get("transform")) for s in sel]
            # for correction mode
            asel = [list(s.getchildren()) for s in sel]

        for i0 in range(len(asel)):  # sel in asel:
            sel = asel[i0]
            # Calculate geometric (tight) bounding boxes of selected items
            sel = [k for k in sel if k.get_id2() in list(fbbs.keys())]
            # only work on objects with a BB
            bbs = dict()
            for el in [firstsel] + sel + sfels:
                if el.get_id2() in list(fbbs.keys()):
                    bbs[el.get_id2()] = geometric_bbox(el, fbbs[el.get_id2()]).sbb

            # Find horizontal and vertical lines (to within .001 rad), elements to be used in plot area calculations
            vl = dict()
            hl = dict()
            boxes = dict()
            solids = dict()
            vels = dict()
            hels = dict()
            for el in list(reversed(sel)):
                isrect = False
                if isinstance(el, (PathElement, Rectangle, Line, Polyline)):
                    bb = bbs[el.get_id2()]
                    xs, ys = dh.get_points(el)
                    if (max(xs) - min(xs)) < 0.001 * bb[3]:  # vertical line
                        vl[el.get_id2()] = bb[3]
                        # lines only
                        vels[el.get_id2()] = bb[3]
                        # lines and rectangles
                    if (max(ys) - min(ys)) < 0.001 * bb[2]:  # horizontal line
                        hl[el.get_id2()] = bb[2]
                        # lines only
                        hels[el.get_id2()] = bb[2]
                        # lines and rectangles

                    if 3 <= len(xs) <= 5 and len(set(xs)) == 2 and len(set(ys)) == 2:
                        isrect = True
                if isrect or isinstance(el, (Rectangle)):  # el.typename=='Rectangle':
                    sty = el.cspecified_style
                    strk = sty.get("stroke")
                    fill = sty.get("fill")

                    nones = [None, "none", "white", "#ffffff"]
                    if not (fill in nones) and (
                        strk in nones or strk == fill
                    ):  # solid rectangle
                        solids[el.get_id2()] = [bb[2], bb[3]]
                    elif not (strk in nones):  # framed box
                        boxes[el.get_id2()] = [bb[2], bb[3]]
                        vels[el.get_id2()] = bb[3]
                        hels[el.get_id2()] = bb[2]

            if len(vels) == 0 or len(hels) == 0 or wholesel:
                noplotarea = True
                lvl = None
                lhl = None
                if (len(vels) == 0 or len(hels) == 0) and not (wholesel):
                    # Display warning message
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

                    numgroup = str(i0 + 1) + appendInt(i0 + 1)
                    inkex.utils.errormsg(
                        "A box-like plot area could not be automatically detected on the "
                        + numgroup
                        + " selected plot (group ID "
                        + gsel[i0].get_id2()
                        + ").\n\n Draw an outlined box to define the plot area."
                        + "\nScaling will still be performed, but the results will be less ideal."
                    )
            else:
                noplotarea = False
                lvl = max(vels, key=vels.get)
                # largest vertical
                lhl = max(hels, key=hels.get)
                # largest horizontal

            # Determine the bounding box of the whole selection and the plot area
            minx = miny = minxp = minyp = fminxp = fminyp = fminx = fminy = float("inf")
            maxx = maxy = maxxp = maxyp = fmaxxp = fmaxyp = fmaxx = fmaxy = float(
                "-inf"
            )
            for el in sel:
                bb = bbs[el.get_id2()]
                minx = min(minx, bb[0])
                miny = min(miny, bb[1])
                maxx = max(maxx, bb[0] + bb[2])
                maxy = max(maxy, bb[1] + bb[3])
                fbb = fbbs[el.get_id2()]
                fminx = min(fminx, fbb[0])
                fminy = min(fminy, fbb[1])
                fmaxx = max(fmaxx, fbb[0] + fbb[2])
                fmaxy = max(fmaxy, fbb[1] + fbb[3])
                if el.get_id2() in [lvl, lhl] or noplotarea:
                    minyp = min(minyp, bb[1])
                    maxyp = max(maxyp, bb[1] + bb[3])
                    minxp = min(minxp, bb[0])
                    maxxp = max(maxxp, bb[0] + bb[2])
                    fbb = fbbs[el.get_id2()]
                    fminyp = min(fminyp, fbb[1])
                    fmaxyp = max(fmaxyp, fbb[1] + fbb[3])
                    fminxp = min(fminxp, fbb[0])
                    fmaxxp = max(fmaxxp, fbb[0] + fbb[2])

            if self.options.tab == "correction":
                # Invert the existing transform so we can run the rest of the code regularly
                extr = trs[i0]
                # existing transform

                # scalex = extr.a
                # scaley = extr.d
                import math

                sx = math.sqrt(extr.a ** 2 + extr.b ** 2)
                sy = (-extr.b * extr.c + extr.a * extr.d) / math.sqrt(
                    extr.a ** 2 + extr.b ** 2
                )
                if sx < 0:
                    sx = -sx
                    sy = -sy
                scalex = sx
                scaley = sy
                # allow for rotations

                if not (figuremode):
                    refx = (minxp + maxxp) / 2
                    refy = (minyp + maxyp) / 2
                else:
                    refx = fminx
                    refy = fminy
                trl = Transform("translate(" + str(refx) + ", " + str(refy) + ")")
                scl = Transform(
                    "scale(" + str(1 / scalex) + ", " + str(1 / scaley) + ")"
                )
                iextr = trl @ scl @ (-trl)
                # invert existing transform
                dh.global_transform(gsel[i0], iextr)

                # for el in sel:
                #     t1 = el.composed_transform(); t2 =el.ccomposed_transform;
                #     if abs(t1.a-t2.a)>.001 or abs(t1.b-t2.b)>.001 or abs(t1.c-t2.c)>.001 or abs(t1.d-t2.d)>.001 or abs(t1.e-t2.e)>.001 or abs(t1.f-t2.f)>.001:
                #         dh.idebug(el.get_id2())
                #         dh.idebug(t1)
                #         dh.idebug(t2)
                #         raise TypeError

                # Invert the transform on the bounding boxes (fix later)
                import copy

                actfbbs = copy.deepcopy(fbbs)
                actbbs = copy.deepcopy(bbs)
                for elid in fbbs.keys():
                    fbbs[elid] = bbox(fbbs[elid]).transform(iextr).sbb
                for elid in bbs.keys():
                    bbs[elid] = bbox(bbs[elid]).transform(iextr).sbb
                ominx = minx
                ominy = miny
                omaxx = maxx
                omaxy = maxy
                # store for later for figure mode
                ominyp = minyp
                omaxyp = maxyp
                ominxp = minxp
                omaxxp = maxxp
                ofminyp = fminyp
                ofmaxyp = fmaxyp
                ofminxp = fminxp
                ofmaxxp = fmaxxp
                ofminx = fminx
                ofminy = fminy
                ofmaxx = fmaxx
                ofmaxy = fmaxy
                minx = miny = minxp = minyp = fminxp = fminyp = fminx = fminy = float(
                    "inf"
                )
                maxx = maxy = maxxp = maxyp = fmaxxp = fmaxyp = fmaxx = fmaxy = float(
                    "-inf"
                )
                for el in sel:
                    bb = bbs[el.get_id2()]
                    minx = min(minx, bb[0])
                    miny = min(miny, bb[1])
                    maxx = max(maxx, bb[0] + bb[2])
                    maxy = max(maxy, bb[1] + bb[3])
                    fbb = fbbs[el.get_id2()]
                    fminx = min(fminx, fbb[0])
                    fminy = min(fminy, fbb[1])
                    fmaxx = max(fmaxx, fbb[0] + fbb[2])
                    fmaxy = max(fmaxy, fbb[1] + fbb[3])
                    if el.get_id2() in [lvl, lhl] or noplotarea:
                        minyp = min(minyp, bb[1])
                        maxyp = max(maxyp, bb[1] + bb[3])
                        minxp = min(minxp, bb[0])
                        maxxp = max(maxxp, bb[0] + bb[2])
                        fbb = fbbs[el.get_id2()]
                        fminyp = min(fminyp, fbb[1])
                        fmaxyp = max(fmaxyp, fbb[1] + fbb[3])
                        fminxp = min(fminxp, fbb[0])
                        fmaxxp = max(fmaxxp, fbb[0] + fbb[2])
                if figuremode:
                    oscalex = scalex
                    oscaley = scaley
                    scalex = ((ofmaxx - ofminx) - (fmaxx - fminx - (maxxp - minxp))) / (
                        (maxxp - minxp)
                    )
                    scaley = ((ofmaxy - ofminy) - (fmaxy - fminy - (maxyp - minyp))) / (
                        (maxyp - minyp)
                    )

                    tlx = (ofminx - refx) / oscalex + refx
                    # where top left is now
                    dxl = minxp - tlx
                    # tlx = (minxp-refx)*scalex+refx-dxl;    # where top-left will be after scaling
                    if scalex != 1:
                        refx = (ofminx + dxl - minxp * scalex) / (1 - scalex)
                        # what refx needs to be to maintain top-left
                    else:
                        refx = ofminx + dxl

                    tly = (ofminy - refy) / oscaley + refy
                    # where top left is now
                    dyl = minyp - tly
                    # tlyp = (minyp-refy)*scaley+refy-dyl;    # where top-left of plot will be after scaling
                    if scaley != 1:
                        refy = (ofminy + dyl - minyp * scaley) / (1 - scaley)
                        # what refx needs to be to maintain top-left
                    else:
                        refy = ofminy + dyl

            if self.options.tab == "matching":
                bbfirst = bbs[firstsel.get_id2()]
                if hmatch:
                    scalex = bbfirst[2] / (maxxp - minxp)
                else:
                    scalex = 1
                if vmatch:
                    scaley = bbfirst[3] / (maxyp - minyp)
                else:
                    scaley = 1

            # Compute global transformation
            if self.options.tab != "correction":
                if hdrag == 1:  # right
                    refx = minx
                else:  # left
                    refx = maxx
                if vdrag == 1:  # bottom
                    refy = miny
                else:  # top
                    refy = maxy
            trl = Transform("translate(" + str(refx) + ", " + str(refy) + ")")
            scl = Transform("scale(" + str(scalex) + ", " + str(scaley) + ")")

            gtr = trl @ scl @ (-trl)
            # global transformation
            iscl = Transform("scale(" + str(1 / scalex) + ", " + str(1 / scaley) + ")")
            trul = gtr.apply_to_point([minxp, minyp])  # transformed upper-left
            trbr = gtr.apply_to_point([maxxp, maxyp])  # transformed bottom-right

            # Diagnostic mode
            diagmode = False
            if diagmode:
                r = Rectangle()
                r.set("x", minxp)
                r.set("y", minyp)
                r.set("width", abs(maxxp - minxp))
                r.set("height", abs(maxyp - minyp))
                r.cstyle = "fill-opacity:0.5"
                self.svg.append(r)
                dh.global_transform(r, gtr)
                dh.debug("Largest vertical line: " + lvl)
                dh.debug("Largest horizontal line: " + lhl)

            # Make a list of elements to be transformed
            sclels = []
            for el in sel:
                if (
                    el in sfgs
                ):  # Is a scale-free group, apply transform to children instead
                    for k in el.getchildren():
                        if k not in sclels:
                            sclels.append(k)
                else:
                    if el not in sclels:
                        sclels.append(el)
            # sclels = list(set(sclels)) # randomly changes order, bad for repeatability

            # Apply transform and compute corrections (if needed)
            for el in sclels:
                # t1 = el.composed_transform(); t2 =el.ccomposed_transform;
                # if abs(t1.a-t2.a)>.001 or abs(t1.b-t2.b)>.001 or abs(t1.c-t2.c)>.001 or abs(t1.d-t2.d)>.001 or abs(t1.e-t2.e)>.001 or abs(t1.f-t2.f)>.001:
                #     dh.idebug(el.get_id2())
                #     dh.idebug(t1)
                #     dh.idebug(t2)
                #     raise TypeError

                dh.global_transform(el, gtr)
                # apply the transform

                # t1 = el.composed_transform(); t2 =el.ccomposed_transform;
                # if abs(t1.a-t2.a)>.001 or abs(t1.b-t2.b)>.001 or abs(t1.c-t2.c)>.001 or abs(t1.d-t2.d)>.001 or abs(t1.e-t2.e)>.001 or abs(t1.f-t2.f)>.001:
                #     dh.idebug(el.get_id2())
                #     dh.idebug(t1)
                #     dh.idebug(t2)
                #     raise TypeError

                # if el.get('clip-path') is not None:
                #     dh.idebug(el.get_id2())
                elid = el.get_id2()

                bb = bbs[elid]
                fbb = fbbs[elid]
                isalwayscorr = isinstance(el, (TextElement, Group, FlowRoot))
                # els always corrected
                isoutsideplot = (
                    fbb[0] > fmaxxp
                    or fbb[0] + fbb[2] < fminxp
                    or fbb[1] > fmaxyp
                    or fbb[1] + fbb[3] < fminyp
                )
                # els outside plot
                issf = el in sfels
                # is scale-free

                vtickt = vtickb = htickl = htickr = False
                # el is a tick
                if tickcorrect and (
                    (elid in list(vl.keys())) or (elid in list(hl.keys()))
                ):
                    isvert = elid in list(vl.keys())
                    ishorz = elid in list(hl.keys())
                    bb = bbs[elid]
                    if isvert and bb[3] < tickthr * (maxyp - minyp):  # vertical tick
                        if bb[1] + bb[3] < minyp + tickthr * (maxyp - minyp):
                            vtickt = True
                        elif bb[1] > maxyp - tickthr * (maxyp - minyp):
                            vtickb = True
                    if ishorz and bb[2] < tickthr * (maxxp - minxp):  # horizontal tick
                        if bb[0] + bb[2] < minxp + tickthr * (maxxp - minxp):
                            htickl = True
                        elif bb[0] > maxxp - tickthr * (maxxp - minxp):
                            htickr = True

                if any([vtickt, vtickb, htickl, htickr]):
                    # If a tick, scale using the edge as a reference point
                    bb_tr = bbox(bb).transform(gtr)
                    cx = bb_tr.xc
                    cy = bb_tr.yc

                    if vtickt:
                        if cy > trul[1]:
                            trl = Transform(
                                "translate(" + str(cx) + ", " + str(bb_tr.y1) + ")"
                            )
                            # inner tick
                        else:
                            trl = Transform(
                                "translate(" + str(cx) + ", " + str(bb_tr.y2) + ")"
                            )
                            # outer tick
                    elif vtickb:
                        if cy < trbr[1]:
                            trl = Transform(
                                "translate(" + str(cx) + ", " + str(bb_tr.y2) + ")"
                            )
                            # inner tick
                        else:
                            trl = Transform(
                                "translate(" + str(cx) + ", " + str(bb_tr.y1) + ")"
                            )
                            # outer tick
                    elif htickl:
                        if cx > trul[0]:
                            trl = Transform(
                                "translate(" + str(bb_tr.x1) + ", " + str(cy) + ")"
                            )
                            # inner tick
                        else:
                            trl = Transform(
                                "translate(" + str(bb_tr.x2) + ", " + str(cy) + ")"
                            )
                            # outer tick
                    elif htickr:
                        if cx < trbr[0]:
                            trl = Transform(
                                "translate(" + str(bb_tr.x2) + ", " + str(cy) + ")"
                            )
                            # inner tick
                        else:
                            trl = Transform(
                                "translate(" + str(bb_tr.x1) + ", " + str(cy) + ")"
                            )
                            # outer tick
                    tr1 = trl @ iscl @ (-trl)
                    dh.global_transform(el, tr1)
                elif isalwayscorr or isoutsideplot or issf:
                    # Invert the transformation for text/groups, anything outside the plot, scale-free
                    cbc = el.get("inkscape-academic-combined-by-color")
                    if cbc is None:
                        bb_tr = bbox(bb).transform(gtr)
                        cx = bb_tr.xc
                        cy = bb_tr.yc
                        trl = Transform("translate(" + str(cx) + ", " + str(cy) + ")")
                        tr1 = trl @ iscl @ (-trl)

                        # For elements outside the plot area, adjust position to maintain
                        # the distance to the plot area
                        dx = 0
                        dy = 0
                        if cx < trul[0]:
                            ox = bb[0] + bb[2] / 2 - minxp
                            dx = ox - (cx - trul[0])
                        if cx > trbr[0]:
                            ox = bb[0] + bb[2] / 2 - maxxp
                            dx = ox - (cx - trbr[0])
                        if cy < trul[1]:
                            oy = bb[1] + bb[3] / 2 - minyp
                            dy = oy - (cy - trul[1])
                        if cy > trbr[1]:
                            oy = bb[1] + bb[3] / 2 - maxyp
                            dy = oy - (cy - trbr[1])
                        tr2 = Transform("translate(" + str(dx) + ", " + str(dy) + ")")
                        dh.global_transform(el, (tr2 @ tr1))

                    else:  # If previously combined, apply to subpaths instead
                        cbc = [int(v) for v in cbc.split()]
                        fbb_tr = bbox(fbb).transform(gtr).sbb
                        irng = []
                        trng = []
                        for ii in range(len(cbc) - 1):
                            bb_tr = geometric_bbox(
                                el, fbb_tr, irange=[cbc[ii], cbc[ii + 1]]
                            )
                            bb = bb_tr.transform(-gtr).sbb
                            cx = bb_tr.xc
                            cy = bb_tr.yc
                            trl = Transform(
                                "translate(" + str(cx) + ", " + str(cy) + ")"
                            )
                            tr1 = trl @ iscl @ (-trl)
                            dx = 0
                            dy = 0
                            if cx < trul[0]:
                                ox = bb[0] + bb[2] / 2 - minxp
                                dx = ox - (cx - trul[0])
                            if cx > trbr[0]:
                                ox = bb[0] + bb[2] / 2 - maxxp
                                dx = ox - (cx - trbr[0])
                            if cy < trul[1]:
                                oy = bb[1] + bb[3] / 2 - minyp
                                dy = oy - (cy - trul[1])
                            if cy > trbr[1]:
                                oy = bb[1] + bb[3] / 2 - maxyp
                                dy = oy - (cy - trbr[1])
                            tr2 = Transform(
                                "translate(" + str(dx) + ", " + str(dy) + ")"
                            )
                            irng.append([cbc[ii], cbc[ii + 1]])
                            trng.append((tr2 @ tr1))
                        dh.global_transform(el, It, irange=irng, trange=trng)

            # restore bbs
            if self.options.tab == "correction":
                fbbs = actfbbs
                bbs = actbbs

        #        pr.disable()
        #        s = io.StringIO()
        #        sortby = SortKey.CUMULATIVE
        #        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        #        ps.print_stats()
        #        dh.debug(s.getvalue())
        dh.flush_stylesheet_entries(self.svg)
        # dh.debug([el.get_id2() for el in self.svg.defs])
        # dh.write_debug()


if __name__ == "__main__":
    dh.Version_Check("Scale plots")
    try:
        ScalePlots().run()
    except lxml.etree.XMLSyntaxError:
        inkex.utils.errormsg(
            "Error parsing XML! Extensions can only run on SVG files. If this is a file imported from another format, try saving as an SVG or pasting the contents into a new SVG."
        )
