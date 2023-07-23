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
    Tspan,
    Transform,
    PathElement,
    Line,
    Rectangle,
    Group,
    Polyline,
)
import os, sys, math, copy

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh
from dhelpers import bbox

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


# Determines plot area from a list of elements and their geometric bounding boxes 
def Find_Plot_Area(els,gbbs):
    vl = dict()      # vertical lines
    hl = dict()      # horizontal lines
    boxes = dict()
    solids = dict()
    for el in list(reversed(els)):
        isrect = False
        if isinstance(el, (PathElement, Rectangle, Line, Polyline)):
            gbb = gbbs[el.get_id()]
            xs, ys = dh.get_points(el)
            if (max(xs) - min(xs)) < 0.001 * gbb[3]:
                vl[el.get_id()] = gbb
            if (max(ys) - min(ys)) < 0.001 * gbb[2]: 
                hl[el.get_id()] = gbb

            tol = 1e-3 * max(max(xs) - min(xs), max(ys) - min(ys))
            if 3 <= len(xs) <= 5 and len(dh.uniquetol(xs, tol)) == 2 and len(dh.uniquetol(ys, tol)) == 2:
                isrect = True
        if isrect or isinstance(el, (Rectangle)):
            sf = dh.get_strokefill(el);
            hasfill   = sf.fill is not None   and sf.fill  !=[255, 255, 255,1]
            hasstroke = sf.stroke is not None and sf.stroke!=[255, 255, 255,1]
            
            if hasfill and (not(hasstroke) or sf.stroke == sf.fill):  # solid rectangle
                solids[el.get_id()] = gbb
            elif hasstroke:                                           # framed rectangle
                boxes[el.get_id()]  = gbb
    
    vels = dict()
    hels = dict()
    for k,gbb in vl.items():
        vels[k] = gbb[3]
    for k,gbb in hl.items():
        hels[k] = gbb[2]
    for k,gbb in boxes.items():
        hels[k] = gbb[2]
        vels[k] = gbb[3]
    
    lvel = lhel = None
    if len(vels) != 0:
        lvel = max(vels, key=vels.get)   # largest vertical
    if len(hels) != 0:
        lhel = max(hels, key=hels.get)   # largest horizontal
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
    
def TrTransform(x,y):
    return Transform("translate(" + str(x) + ", " + str(y) + ")")
def SclTransform(x,y):
    return Transform("scale(" + str(x) + ", " + str(y) + ")")


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
        pars.add_argument(
            "--matchwhat", type=int, default=2, help="Match what?"
        )
        pars.add_argument(
            "--matchto", type=int, default=1, help="Match to?"
        )
        
        pars.add_argument(
            "--marksf", type=int, default=1, help="Mark objects as"
        )

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
        sel = [
            k
            for k in sel
            if not (isinstance(k, (Tspan, inkex.NamedView, inkex.Defs, inkex.Metadata, inkex.ForeignObject)))
        ]
        # regular selectable objects only

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
            hmatch = self.options.hmatch
            vmatch = self.options.vmatch
            wholesel = self.options.wholeplot2
        elif self.options.tab == "correction":
            scalex = 1
            scaley = 1
            wholesel = self.options.wholeplot3
            if not (all([isinstance(k, Group) for k in sel])):
                inkex.utils.errormsg(
                    "Correction mode requires that every selected object be a group that has already been scaled."
                )
                
                return
        else:
            # inkex.utils.errormsg("Select Scaling, Matching, or Correction mode")
            self.options.marksf = {1:'scale_free',2:'aspect_locked',3:'normal',4:None}[self.options.marksf]
            for el in sel:
                el.set('inkscape-scientific-scaletype',self.options.marksf)
            return
        self.options.matchwhat = {1:'bbox',2:'plotarea'}[self.options.matchwhat]
        self.options.matchto   = {1:'firstbbox',2:'firstplotarea',3:'meanbbox',4:'meanplotarea'}[self.options.matchto]
        self.options.figuremode= {1:False,2:True}[self.options.figuremode]

        if wholesel:
            tickcorrect = False

        dsfchildren = [] # objects whose children are designated scale-free
        dsfels = []      # designated scale-free els, whether or not they're selected

        # full visual bbs
        fbbs = dh.BB2(self,dh.unique([d for el in sel for d in el.descendants2()]))
        firstsel = sel[0]
        if self.options.tab == "matching":
            sel = sel[1:]
        
        all_pels = [sel]
        if all([isinstance(k, Group) for k in sel]): # grouped mode
            trs = [Transform(s.get("transform")) for s in sel]
            # for correction mode
            all_pels = [list(s) for s in sel]

        for i0 in range(len(all_pels)):  # sel in asel:
            pels = [k for k in all_pels[i0] if k.get_id() in list(fbbs.keys())]  # plot elements list
            
            # Calculate geometric (tight) bounding boxes of plot elements
            gbbs = dict()
            for el in [firstsel] + pels + dsfels + list(firstsel):
                if el.get_id() in fbbs:
                    gbbs[el.get_id()] = geometric_bbox(el, fbbs[el.get_id()]).sbb

            vl, hl, lvel, lhel = Find_Plot_Area(pels,gbbs)   
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
                        + ").\n\nDraw a box with a stroke to define the plot area."
                        + "\nScaling will still be performed, but the results may not be ideal."
                    )
            else:
                noplotarea = False
            
            # A class that contains geometric and full bounding boxes
            class bbox2:
                def __init__(self,g,f):
                    if isinstance(g,list) or g is None:
                        g = bbox(g)
                    if isinstance(f,list) or f is None:
                        f = bbox(f)
                    self.g = g;
                    self.f = f;
                def union(self, g,f):
                    return(bbox2(self.g.union(g),self.f.union(f)));
                
                    
            bba = bbox2(None,None);    # all elements
            bbp = bbox2(None,None);    # plot area
            for el in pels:
                bba  = bba.union(gbbs[el.get_id()],fbbs[el.get_id()])
                if el.get_id() in [lvel, lhel] or noplotarea:
                    bbp  = bbp.union(gbbs[el.get_id()],fbbs[el.get_id()])

            if self.options.tab == "correction":
                # Invert the existing transform so we can run the rest of the code regularly
                extr = trs[i0]
                # existing transform

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

                if not (self.options.figuremode):
                    refx = (bbp.g.x1 + bbp.g.x2) / 2
                    refy = (bbp.g.y1 + bbp.g.y2) / 2
                else:
                    refx = bba.f.x1
                    refy = bba.f.y1
                trl = TrTransform(refx,refy)
                scl = SclTransform(1 / scalex, 1 / scaley)
                iextr = trl @ scl @ (-trl)
                # invert existing transform
                dh.global_transform(sel[i0], iextr)

                # Invert the transform on the bounding boxes (fix later)
                import copy

                actfbbs = copy.deepcopy(fbbs)
                actgbbs = copy.deepcopy(gbbs)
                for elid in fbbs.keys():
                    fbbs[elid] = bbox(fbbs[elid]).transform(iextr).sbb
                for elid in gbbs.keys():
                    gbbs[elid] = bbox(gbbs[elid]).transform(iextr).sbb
                
                tr_bba = bba;   # bb with transform to be corrected
                        
                bba = bbox2(None,None);    # bbox of all elements
                bbp = bbox2(None,None);    # bbox of plot area
                for el in pels:
                    bba  = bba.union(gbbs[el.get_id()],fbbs[el.get_id()])
                    if el.get_id() in [lvel, lhel] or noplotarea:
                        bbp  = bbp.union(gbbs[el.get_id()],fbbs[el.get_id()])
                
                if self.options.figuremode:
                    oscalex = scalex
                    oscaley = scaley
                    scalex = ((tr_bba.f.x2 - tr_bba.f.x1) - (bba.f.x2 - bba.f.x1 - (bbp.g.x2 - bbp.g.x1))) / (
                        (bbp.g.x2 - bbp.g.x1)
                    )
                    scaley = ((tr_bba.f.y2 - tr_bba.f.y1) - (bba.f.y2 - bba.f.y1 - (bbp.g.y2 - bbp.g.y1))) / (
                        (bbp.g.y2 - bbp.g.y1)
                    )

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
                if self.options.matchto == 'firstbbox':
                    bbmatch = bbox(gbbs[firstsel.get_id()]);
                elif self.options.matchto == 'firstplotarea':
                    vl0, hl0, lvel0, lhel0 = Find_Plot_Area(list(firstsel),gbbs)   
                    if lvel0 is None or lhel0 is None:
                        inkex.utils.errormsg(
                            "A box-like plot area could not be automatically detected on the "
                            + "first selected object (ID "
                            + firstsel.get_id()
                            + ").\n\nIts bounding box will be matched instead. If this is not ideal,"
                            + " draw an outlined box to define the plot area.\n"
                        )
                        bbmatch = bbox(gbbs[firstsel.get_id()]);
                    else:
                        bbmatch = bbox(gbbs[lvel0]).union(bbox(gbbs[lhel0]));
                elif self.options.matchto == 'meanbbox':
                    pass
                elif self.options.matchto == 'meanplotarea':
                    pass
                
                scalex = scaley = 1
                if hmatch:
                    if self.options.matchwhat == 'plotarea':
                        scalex = bbmatch.w / bbp.g.w;
                    elif self.options.matchwhat == 'bbox':
                        scalex = (bbmatch.w + bbp.g.w - bba.g.w)/bbp.g.w
                if vmatch:
                    if self.options.matchwhat == 'plotarea':
                        scaley = bbmatch.h / bbp.g.h
                    elif self.options.matchwhat == 'bbox':
                        scaley = (bbmatch.h + bbp.g.h - bba.g.h)/bbp.g.h
            

            # Compute global transformation
            if self.options.tab != "correction":
                if self.options.hdrag == 1:     # right
                    refx = bba.g.x1
                elif self.options.hdrag == 2:   # left
                    refx = bba.g.x2
                else:                           # center
                    refx = (bba.g.x1+bba.g.x2)/2
                if self.options.vdrag == 1:     # bottom
                    refy = bba.g.y1
                elif self.options.vdrag == 2:   # top
                    refy = bba.g.y2
                else:                           # center
                    refy = (bba.g.y1+bba.g.y2)/2
            trl = TrTransform(refx,refy);
            scl = SclTransform(scalex, scaley)

            gtr = trl @ scl @ (-trl)
            # global transformation
            iscl = SclTransform(1 / scalex, 1 / scaley)  # inverse scale
            liscl = SclTransform(math.sqrt(scalex*scaley), math.sqrt(scalex*scaley)) @ iscl # aspect-scaled and inverse scaled
            trul = gtr.apply_to_point([bbp.g.x1, bbp.g.y1])  # transformed upper-left
            trbr = gtr.apply_to_point([bbp.g.x2, bbp.g.y2])  # transformed bottom-right

            # Diagnostic mode
            diagmode = False
            if diagmode:
                r = Rectangle()
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
                if (
                    el in dsfchildren
                ):  # Is a scale-free group, apply transform to children instead
                    for k in list(el):
                        if k not in sclels:
                            sclels.append(k)
                else:
                    if el not in sclels:
                        sclels.append(el)

            # Apply transform and compute corrections (if needed)
            for el in sclels:
                dh.global_transform(el, gtr)
                # apply the transform

                elid = el.get_id()
                gbb = gbbs[elid]
                fbb = fbbs[elid]
                
                if isinstance(el, (TextElement, Group, FlowRoot)) or el in dsfels:
                    stype = 'scale_free'
                else:
                    stype = 'normal'
                
                mtype = el.get('inkscape-scientific-scaletype');
                if mtype is not None:
                    stype = mtype
                    
                if hasattr(self.options,'hcall') and self.options.hcall:
                    if isinstance(el, (TextElement, Group, FlowRoot)):
                        stype = 'normal'

                vtickt = vtickb = htickl = htickr = False
                # el is a tick
                if tickcorrect and (
                    (elid in list(vl.keys())) or (elid in list(hl.keys()))
                ):
                    isvert = elid in list(vl.keys())
                    ishorz = elid in list(hl.keys())
                    gbb = gbbs[elid]
                    if isvert and gbb[3] < tickthr * (bbp.g.y2 - bbp.g.y1):  # vertical tick
                        if gbb[1] + gbb[3] < bbp.g.y1 + tickthr * (bbp.g.y2 - bbp.g.y1):
                            vtickt = True
                        elif gbb[1] > bbp.g.y2 - tickthr * (bbp.g.y2 - bbp.g.y1):
                            vtickb = True
                    if ishorz and gbb[2] < tickthr * (bbp.g.x2 - bbp.g.x1):  # horizontal tick
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
                            trl = TrTransform(cx,gbb_tr.y1)   # inner tick
                        else:
                            trl = TrTransform(cx,gbb_tr.y2)   # outer tick
                    elif vtickb:
                        if cy < trbr[1]:
                            trl = TrTransform(cx,gbb_tr.y2)     # inner tick
                        else:
                            trl = TrTransform(cx,gbb_tr.y1)    # outer tick
                    elif htickl:
                        if cx > trul[0]:
                            trl = TrTransform(gbb_tr.x1,cy)    # inner tick
                        else:
                            trl = TrTransform(gbb_tr.x2,cy)    # outer tick
                    elif htickr:
                        if cx < trbr[0]:
                            trl = TrTransform(gbb_tr.x2,cy)   # inner tick
                        else:
                            trl = TrTransform(gbb_tr.x1,cy)   # outer tick
                    tr1 = trl @ iscl @ (-trl)
                    dh.global_transform(el, tr1)
                # elif isalwayscorr or isoutsideplot or issf:
                elif stype in ['scale_free','aspect_locked']:
                    # dh.idebug(el.get_id())
                    # Invert the transformation for text/groups, anything outside the plot, scale-free
                    cbc = el.get("inkscape-scientific-combined-by-color")
                    if cbc is None:
                        gbb_tr = bbox(gbb).transform(gtr)
                        cx = gbb_tr.xc
                        cy = gbb_tr.yc
                        trl = TrTransform(cx,cy)
                        if stype=='scale_free':
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
                        tr2 = TrTransform(dx,dy)
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
                            trl = TrTransform(cx,cy)
                            # tr1 = trl @ iscl @ (-trl)
                            if stype=='scale_free':
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
                            tr2 = TrTransform(dx,dy)
                            irng.append([cbc[ii], cbc[ii + 1]])
                            trng.append((tr2 @ tr1))
                        dh.global_transform(el, It, irange=irng, trange=trng)
                    

            # restore bbs
            if self.options.tab == "correction":
                fbbs = actfbbs
                gbbs = actgbbs

        dh.flush_stylesheet_entries(self.svg)

if __name__ == "__main__":
    dh.Run_SI_Extension(ScalePlots(),"Scale plots")
