#!/usr/bin/env python
# coding=utf-8
#
# Copyright (c) 2025 David Burghoff <burghoff@utexas.edu>
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

import dhelpers as dh
import inkex
from inkex import Transform
import math, copy
from dhelpers import bbox
from inkex.text.utils import uniquetol
import lxml

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
SCALEFREE_DFLTS = TEXTLIKE_TAGS + [GROUP_TAG]
EXCLUDE_TAGS = [
    inkex.Tspan.ctag,
    inkex.NamedView.ctag,
    inkex.Defs.ctag,
    inkex.Metadata.ctag,
    inkex.ForeignObject.ctag,
]
COMMENT_TAG = lxml.etree.Comment("").tag
IMAGE_TAG = inkex.Image.ctag


def geometric_bbox(el, vis_bbox, irange=None):
    gbb = copy.copy(vis_bbox)
    if el.tag in PATHLIKE_TAGS:  # if path-like, use nodes instead
        xs, ys = dh.get_points(el, irange=irange)
        # For clipped objects the list of points is a bad description of the
        # geometric bounding box. As a rough workaround, use the visual bbox if
        # its limits are smaller than the geometric bbox. This is almost
        # always fine since clips use the geometric bbox.
        minx = max(min(xs), vis_bbox[0])
        maxx = min(max(xs), vis_bbox[0] + vis_bbox[2])
        miny = max(min(ys), vis_bbox[1])
        maxy = min(max(ys), vis_bbox[1] + vis_bbox[3])
        gbb = [minx, miny, maxx - minx, maxy - miny]  # geometric bounding box
    return bbox(gbb)


# Determines plot area from a list of elements and their geometric bounding boxes
def find_plot_area(els, gbbs):
    vl = dict()  # vertical lines
    hl = dict()  # horizontal lines
    boxes = dict()
    solids = dict()
    plotareas = dict()
    for el in reversed(els):
        isrect = False
        if el.tag in PATHLIKE_TAGS:
            gbb = gbbs[el]
            xs, ys = dh.get_points(el)
            if (max(xs) - min(xs)) < 0.001 * gbb[3]:
                vl[el] = gbb
            if (max(ys) - min(ys)) < 0.001 * gbb[2]:
                hl[el] = gbb

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
                solids[el] = gbb
            elif hasstroke:  # framed rectangle
                boxes[el] = gbb

        if el.get("inkscape-scientific-scaletype") == "plot_area":
            plotareas[el] = gbb

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
def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def warn_non_plot(idx, gid):
    numgroup = ordinal(idx + 1)
    inkex.utils.errormsg(
        "A box-like plot area could not be automatically detected on the "
        + numgroup
        + " selected plot (group ID "
        + gid
        + ").\n\nDraw a box with a stroke to define the plot area or mark objects"
        " as plot area-determining in the Advanced tab."
        "\nScaling will still be performed, but the results may not be ideal."
    )


IMAGE_ERR = (
    "Thanks for using Scientific Inkscape!\n\n"
    "It appears that you're attempting to scale a raster Image object. Please note that "
    "Inkscape is mainly for working with vector images, not raster images. Vector images "
    "preserve all of the information used to generate them, whereas raster images do not. "
    "Read about the difference here: \nhttps://en.wikipedia.org/wiki/Vector_graphics\n\n"
    "While raster images can be embedded in vector images, they cannot be modified directly. "
    "If you want to edit a raster image, you will need to "
    "use a program like Photoshop or GIMP."
)


def trtf(x, y):
    return Transform("translate(" + str(x) + ", " + str(y) + ")")


def sctf(x, y):
    return Transform("scale(" + str(x) + ", " + str(y) + ")")


class bbox2:
    """Contains geometric and full bounding boxes"""

    def __init__(self, g, f):
        if isinstance(g, list) or g is None:
            g = bbox(g)
        if isinstance(f, list) or f is None:
            f = bbox(f)
        self.g = g
        self.f = f

    def union(self, g, f):
        return bbox2(self.g.union(g), self.f.union(f))


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

        if all([el.tag == IMAGE_TAG for el in sel]) and self.options.tab != "options":
            inkex.utils.errormsg(IMAGE_ERR)
            quit()

        self.options.tickthr = self.options.tickthreshold / 100
        # layerfix = self.options.layerfix
        if self.options.tab == "matching":
            self.options.hmatch = self.options.hmatchopts in [2, 3]
            self.options.vmatch = self.options.vmatchopts in [2, 3]
            self.options.matchxpos = self.options.hmatchopts == 3
            self.options.matchypos = self.options.vmatchopts == 3
            self.options.wholesel = self.options.wholeplot2
        elif self.options.tab == "correction":
            self.options.wholesel = self.options.wholeplot3
        else:
            # Advanced tab
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

        cmode = self.options.tab == "correction"

        if self.options.wholesel:
            self.options.tickcorrect = False

        # Full visual bounding boxes
        self.fbbs = dh.BB2(self.svg, dh.unique([d for el in sel for d in el.iter("*")]))
        self.fbbs = {self.svg.getElementById(k): v for k, v in self.fbbs.items()}
        
        # Geometric (tight) bounding boxes of plot elements
        self.gbbs = {k: geometric_bbox(k, v).sbb for k, v in self.fbbs.items()}

        self.firstsel = sel[0]
        if not cmode:
            plots = sel[1:]
        else:
            plots = sel[:]
        self.plots = plots

        if not all(p.tag == GROUP_TAG for p in self.plots):
            inkex.utils.errormsg(
                "Non-Group objects detected in selection. "
                "Objects in a plot should be grouped prior to scaling."
            )
            return

        for i, _ in enumerate(plots):  # sel in asel:
            self.scale_plot(i, cmode)

        if not cmode and self.options.deletematch:
            self.firstsel.delete()

    def scale_plot(self, i, cmode=True):
        """
        Scale an individual grouped plot
        cmode = True: Correction mode
        cmode = False: Matching mode
        """
        if not cmode:
            # If in matching mode and plot has a transform, correct first
            extr = self.plots[i].ctransform
            sx = math.sqrt(extr.a**2 + extr.b**2)
            sy = (-extr.b * extr.c + extr.a * extr.d) / math.sqrt(extr.a**2 + extr.b**2)
            if abs(sx - 1) > 1e-5 or abs(sy - 1) > 1e-5:
                self.scale_plot(i, True)

        pel_list = dh.list2(self.plots[i])
        pels = [k for k in pel_list if k in self.fbbs]  # plot elements

        vl, hl, lvel, lhel = find_plot_area(pels, self.gbbs)
        if lvel is None or lhel is None or self.options.wholesel:
            noplotarea = True
            lvel = None
            lhel = None
            if not (self.options.wholesel):  # Display warning message
                warn_non_plot(i, self.plots[i].get_id())
        else:
            noplotarea = False

        bba = bbox2(None, None)  # all elements
        bbp = bbox2(None, None)  # plot area
        for el in pels:
            bba = bba.union(self.gbbs[el], self.fbbs[el])
            if el in [lvel, lhel] or noplotarea:
                bbp = bbp.union(self.gbbs[el], self.fbbs[el])

        if cmode:
            # Invert the existing transform so we can run the rest of the code regularly
            extr = self.plots[i].ctransform
            # existing transform

            sx = math.sqrt(extr.a**2 + extr.b**2)
            sy = (-extr.b * extr.c + extr.a * extr.d) / math.sqrt(extr.a**2 + extr.b**2)
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
            dh.global_transform(self.plots[i], iextr)

            # Invert the transform on the bounding boxes
            fbbs2 = {
                k: bbox(v).transform(iextr).sbb
                for k, v in self.fbbs.items()
                if k in pels
            }
            gbbs2 = {
                k: bbox(v).transform(iextr).sbb
                for k, v in self.gbbs.items()
                if k in pels
            }
            tr_bba = bba
            # bb with transform to be corrected

            bba = bbox2(None, None)
            # bbox of all elements
            bbp = bbox2(None, None)
            # bbox of plot area
            for el in pels:
                bba = bba.union(gbbs2[el], fbbs2[el])
                if el in [lvel, lhel] or noplotarea:
                    bbp = bbp.union(gbbs2[el], fbbs2[el])

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
        else:
            fbbs2 = self.fbbs
            gbbs2 = self.gbbs

            bbmatch = None
            if self.options.matchto == "bbox":
                bbmatch = bbox(gbbs2[self.firstsel])
            elif self.options.matchto == "plotarea":
                if self.firstsel.tag == GROUP_TAG:
                    plotareaels = list(self.firstsel)
                else:
                    plotareaels = [self.firstsel]

                vl0, hl0, lvel0, lhel0 = find_plot_area(plotareaels, gbbs2)
                if lvel0 is None or lhel0 is None:
                    if self.firstsel.tag != IMAGE_TAG:
                        warn_non_plot(0, self.firstsel.get_id())
                    bbmatch = bbox(gbbs2[self.firstsel])
                else:
                    bbmatch = bbox(gbbs2[lvel0]).union(bbox(gbbs2[lhel0]))

            scalex = scaley = 1
            if self.options.hmatch:
                if self.options.matchwhat == "plotarea":
                    scalex = bbmatch.w / bbp.g.w
                elif self.options.matchwhat == "bbox":
                    scalex = (bbmatch.w + bbp.g.w - bba.g.w) / bbp.g.w
            if self.options.vmatch:
                if self.options.matchwhat == "plotarea":
                    scaley = bbmatch.h / bbp.g.h
                elif self.options.matchwhat == "bbox":
                    scaley = (bbmatch.h + bbp.g.h - bba.g.h) / bbp.g.h

        # Compute global transformation
        if not cmode:
            if self.options.matchwhat == "plotarea":
                refx = bbp.g.xc
                refy = bbp.g.yc
            else:
                refx = bba.g.xc
                refy = bba.g.yc

        finx = refx  # final x
        finy = refy  # final y
        if not cmode:
            if self.options.matchxpos:
                finx = bbmatch.xc
            if self.options.matchypos:
                finy = bbmatch.yc
            if self.options.matchwhat == "bbox":
                # Following scaling, margins stay the same size so the
                # bounding box center has moved
                finx -= (
                    0.5 * ((bba.g.x2 - bbp.g.x2) - (bbp.g.x1 - bba.g.x1)) * (1 - scalex)
                )
                finy -= (
                    0.5 * ((bba.g.y2 - bbp.g.y2) - (bbp.g.y1 - bba.g.y1)) * (1 - scaley)
                )

        gtr = trtf(finx, finy) @ sctf(scalex, scaley) @ (-trtf(refx, refy))
        # global transformation
        iscl = sctf(1 / scalex, 1 / scaley)  # inverse scale
        liscl = (
            sctf(math.sqrt(abs(scalex * scaley)), math.sqrt(abs(scalex * scaley))) @ iscl
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

        # Apply transform and compute corrections (if needed)
        for el in pels:
            dh.global_transform(el, gtr)  # apply the transform

            fbb, gbb = fbbs2[el], gbbs2[el]

            stype = el.get("inkscape-scientific-scaletype") or (
                "scale_free" if el.tag in SCALEFREE_DFLTS else "normal"
            )
            if hasattr(self.options, "hcall") and self.options.hcall:
                if el.tag in SCALEFREE_DFLTS:
                    stype = "normal"

            vtickt = vtickb = htickl = htickr = False
            # el is a tick
            if self.options.tickcorrect and (el in vl or el in hl):
                isvert = el in vl
                ishorz = el in hl
                if isvert and gbb[3] < self.options.tickthr * (
                    bbp.g.y2 - bbp.g.y1
                ):  # vertical tick
                    if gbb[1] + gbb[3] < bbp.g.y1 + self.options.tickthr * (
                        bbp.g.y2 - bbp.g.y1
                    ):
                        vtickt = True
                    elif gbb[1] > bbp.g.y2 - self.options.tickthr * (
                        bbp.g.y2 - bbp.g.y1
                    ):
                        vtickb = True
                if ishorz and gbb[2] < self.options.tickthr * (
                    bbp.g.x2 - bbp.g.x1
                ):  # horizontal tick
                    if gbb[0] + gbb[2] < bbp.g.x1 + self.options.tickthr * (
                        bbp.g.x2 - bbp.g.x1
                    ):
                        htickl = True
                    elif gbb[0] > bbp.g.x2 - self.options.tickthr * (
                        bbp.g.x2 - bbp.g.x1
                    ):
                        htickr = True

            if any([vtickt, vtickb, htickl, htickr]):
                # If a tick, scale using the edge as a reference point
                gbb_tr = bbox(gbb).transform(gtr)
                cx = gbb_tr.xc
                cy = gbb_tr.yc

                if vtickt:
                    trl = trtf(cx, gbb_tr.y1 if cy > trul[1] else gbb_tr.y2)
                elif vtickb:
                    trl = trtf(cx, gbb_tr.y2 if cy < trbr[1] else gbb_tr.y1)
                elif htickl:
                    trl = trtf(gbb_tr.x1 if cx > trul[0] else gbb_tr.x2, cy)
                elif htickr:
                    trl = trtf(gbb_tr.x2 if cx < trbr[0] else gbb_tr.x1, cy)

                tr1 = trl @ iscl @ (-trl)
                dh.global_transform(el, tr1)
            elif stype in ["scale_free", "aspect_locked"]:
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
                    dx, dy = 0, 0
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
                    irng, trng = [], []
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
                        dx, dy = 0, 0
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


if __name__ == "__main__":
    dh.Run_SI_Extension(ScalePlots(), "Scale plots")
