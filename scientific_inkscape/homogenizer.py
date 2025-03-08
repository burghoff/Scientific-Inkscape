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
from inkex import TextElement, FlowRoot, FlowPara, Tspan, Transform, Group, FlowSpan
from inkex.text.cache import BaseElementCache
otp_support_tags = BaseElementCache.otp_support_tags
from inkex.text.utils import default_style_atts

from applytransform_mod import fuseTransform
import math

badels = (
    inkex.NamedView,
    inkex.Defs,
    inkex.Metadata,
    inkex.ForeignObject,
    inkex.SVGfont,
    inkex.FontFace,
    inkex.MissingGlyph,
)

dispprofile = False


class Homogenizer(inkex.EffectExtension):
    #    def document_path(self):
    #        return 'test'

    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument(
            "--setfontsize", type=inkex.Boolean, default=False, help="Set font size?"
        )
        pars.add_argument("--fontsize", type=float, default=8, help="New font size")
        pars.add_argument(
            "--fixtextdistortion",
            type=inkex.Boolean,
            default=False,
            help="Fix distorted text?",
        )
        pars.add_argument("--fontmodes", type=int, default=1, help="Font size options")

        pars.add_argument(
            "--setfontfamily",
            type=inkex.Boolean,
            default=False,
            help="Set font family?",
        )
        pars.add_argument("--fontfamily", type=str, default="", help="New font family")

        #        pars.add_argument("--setreplacement", type=inkex.Boolean, default=False,help="Replace missing fonts?")
        #        pars.add_argument("--replacement", type=str, default='', help="Missing fon replacement");

        pars.add_argument(
            "--setstroke", type=inkex.Boolean, default=False, help="Set stroke width?"
        )
        pars.add_argument(
            "--setstrokew", type=float, default=1, help="New stroke width"
        )
        pars.add_argument(
            "--strokemodes", type=int, default=1, help="Stroke width options"
        )
        pars.add_argument(
            "--clearclipmasks", type=inkex.Boolean, default=False, help="Clear clips and masks"
        )
        pars.add_argument(
            "--fusetransforms",
            type=inkex.Boolean,
            default=False,
            help="Fuse transforms to paths?",
        )
        pars.add_argument(
            "--plotaware",
            type=inkex.Boolean,
            default=False,
            help="Plot-aware text scaling?",
        )

    def effect(self):
        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey

            pr = cProfile.Profile()
            pr.enable()

        setfontsize = self.options.setfontsize
        # setfontsize = (self.options.fontmodes>1);

        fontsize = self.options.fontsize
        setfontfamily = self.options.setfontfamily
        fontfamily = self.options.fontfamily
        setstroke = self.options.setstroke
        setstrokew = self.options.setstrokew
        fixtextdistortion = self.options.fixtextdistortion

        sel0 = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        # should work with both v1.0 and v1.1
        sel = [v for el in sel0 for v in el.descendants2()]

        itag = inkex.Image.ctag
        if all([el.tag == itag for el in sel]):
            inkex.utils.errormsg(
                """Thanks for using Scientific Inkscape!
            
It appears that you're attempting to homogenize a raster Image object. Please note that Inkscape is mainly for working with vector images, not raster images. Vector images preserve all of the information used to generate them, whereas raster images do not. Read about the difference here:
https://en.wikipedia.org/wiki/Vector_graphics
            
Unfortunately, this means that there is not much the Homogenizer can do to edit raster images. If you want to edit a raster image, you will need to use a program like Photoshop or GIMP.
            """
            )
            quit()
        elif self.options.plotaware and any([not isinstance(k, Group) for k in sel0]):
            inkex.utils.errormsg(
                "Plot-aware scaling requires that every selected object be a grouped plot."
            )
            return

        sela = [el for el in sel if not (isinstance(el, badels))]
        sel = [
            el
            for el in sel
            if isinstance(el, (TextElement, Tspan, FlowRoot, FlowPara, FlowSpan))
        ]

        if setfontfamily or setfontsize or fixtextdistortion:
            tels = [d for d in sel if isinstance(d, (TextElement, FlowRoot))]
            if not self.options.plotaware:
                bbs = dh.BB2(self.svg, tels, False)
            else:
                aels = [d for el in sel0 for d in el.descendants2()]
                bbs = dh.BB2(self.svg, aels, False)

        if setfontsize:
            # Get all font sizes and scale factors
            onept = self.svg.cdocsize.unittouu("1pt")
            szs = dict()
            for el in tels:
                cszs = [c.tfs / onept for ln in el.parsed_text.lns for c in ln.chrs]
                if len(cszs) > 0:
                    szs[el] = max(cszs)

            # Determine scale and/or size
            fixedscale = False
            try:
                if self.options.fontmodes == 3:
                    fixedscale = True
                elif self.options.fontmodes == 4:
                    fixedscale = True
                    fontsize = fontsize / max(szs.values()) * 100
                elif self.options.fontmodes == 5:
                    from statistics import mean

                    fontsize = mean(szs.values())
                elif self.options.fontmodes == 6:
                    from statistics import median

                    fontsize = median(szs.values())
                elif self.options.fontmodes == 7:
                    fontsize = min(szs.values())
                elif self.options.fontmodes == 8:
                    fontsize = max(szs.values())
            except ValueError:
                fontsize = 12

            from inkex.text import parser

            for el in szs:
                for d in reversed(el.descendants2()):
                    sty = d.cspecified_style
                    if el == d or "font-size" in sty:
                        dfs, sf, utdfs = dh.composed_width(d, "font-size")
                        if dfs==0:
                            continue
                        bshift = parser.TChar.get_baseline(sty, d.getparent())
                        if bshift != 0 or "%" in sty.get("font-size", ""):
                            # Convert sub/superscripts into relative size
                            pfs, sf, _ = dh.composed_width(d.getparent(), "font-size")
                            d.cstyle["font-size"] = f"{dfs / pfs * 100:.2f}%"
                        else:
                            # Set absolute size
                            scl = (
                                fontsize * onept / dfs
                                if not fixedscale
                                else fontsize / 100
                            )
                            nfs = utdfs * scl
                            nfs = f"{nfs:.2f}" if abs(nfs) > 1 else "{:.3g}".format(nfs)
                            d.cstyle["font-size"] = nfs.rstrip("0").rstrip(".") + "px"

        if fixtextdistortion:
            # make a new transform that removes bad scaling and shearing (see General_affine_transformation.nb)
            for el in sel:
                ct = el.ccomposed_transform
                detv = ct.a * ct.d - ct.b * ct.c
                if detv!=0:
                    signdet = -1 * (detv < 0) + (detv >= 0)
                    sqrtdet = math.sqrt(abs(detv))
                    magv = math.sqrt(ct.b**2 + ct.a**2)
                    ctnew = Transform(
                        [
                            [ct.a * sqrtdet / magv, -ct.b * sqrtdet * signdet / magv, ct.e],
                            [ct.b * sqrtdet / magv, ct.a * sqrtdet * signdet / magv, ct.f],
                        ]
                    )
                    dh.global_transform(el, (ctnew @ (-ct)))

        if setfontfamily:
            from inkex.text.font_properties import inkscape_spec_to_css
            sty = inkscape_spec_to_css(fontfamily)
            if sty is None:
                dh.idebug('Font seems to be invalid—check its spelling.')
                import sys
                sys.exit()
            # If any type of Font Style is being set, reset the others to default
            if any(k in sty for k in ["font-weight", "font-style", "font-stretch"]):
                for k in ["font-weight", "font-style", "font-stretch"]:
                    sty.setdefault(k, default_style_atts[k])

            for el in reversed(sel):
                for k,v in sty.items():
                    el.cstyle[k] = v
                el.cstyle["-inkscape-font-specification"] = None

            from inkex.text import parser

            dh.character_fixer(tels)

        if setfontfamily or setfontsize or fixtextdistortion:
            bbs2 = dh.BB2(self.svg, tels, True)
            if not self.options.plotaware:
                for el in sel:
                    myid = el.get_id()
                    if (
                        isinstance(el, (TextElement, FlowRoot))
                        and myid in bbs
                        and myid in bbs2
                    ):
                        bb = bbs[el.get_id()]
                        bb2 = bbs2[el.get_id()]
                        tx = (bb2[0] + bb2[2] / 2) - (bb[0] + bb[2] / 2)
                        ty = (bb2[1] + bb2[3] / 2) - (bb[1] + bb[3] / 2)
                        trl = Transform("translate({0}, {1})".format(-tx, -ty))
                        dh.global_transform(el, trl)

            else:
                from scale_plots import (
                    geometric_bbox,
                    Find_Plot_Area,
                    trtf,
                    appendInt,
                )

                gbbs = {elid: geometric_bbox(el, fbb).sbb for elid, fbb in bbs.items()}
                for i0, g in enumerate(sel0):
                    pels = [k for k in g if k.get_id() in bbs]  # plot elements list
                    vl, hl, lvel, lhel = Find_Plot_Area(pels, gbbs)

                    if lvel is None or lhel is None:
                        lvel = None
                        lhel = None
                        # Display warning and proceed
                        numgroup = str(i0 + 1) + appendInt(i0 + 1)
                        inkex.utils.errormsg(
                            "A box-like plot area could not be automatically detected on the "
                            + numgroup
                            + " selected plot (group ID "
                            + g.get_id()
                            + ").\n\nDraw a box with a stroke to define the plot area."
                            + "\nAdjustment will still be performed, but the results may not be ideal."
                        )

                    bbp = dh.bbox(None)
                    # plot area
                    for el in pels:
                        if el.get_id() in [lvel, lhel]:
                            bbp = bbp.union(gbbs[el.get_id()])
                    for el in g.descendants2():
                        if el in tels:
                            bb1 = dh.bbox(bbs[el.get_id()])
                            bb2 = dh.bbox(bbs2[el.get_id()])
                            if bbp.isnull:
                                dx = bb1.xc - bb2.xc
                                dy = bb1.yc - bb2.yc
                            else:
                                # For elements outside the plot area, adjust position to maintain
                                # the scaled distance to the plot area
                                if bb1.xc < bbp.x1:
                                    dx = (bbp.x1 - bb2.x2) - (
                                        bbp.x1 - bb1.x2
                                    ) * bb2.w / bb1.w
                                elif bb1.xc > bbp.x2:
                                    dx = (bb1.x1 - bbp.x2) * bb2.w / bb1.w - (
                                        bb2.x1 - bbp.x2
                                    )
                                else:
                                    dx = bb1.xc - bb2.xc
                                if bb1.yc < bbp.y1:
                                    dy = (bbp.y1 - bb2.y2) - (
                                        bbp.y1 - bb1.y2
                                    ) * bb2.h / bb1.h
                                elif bb1.yc > bbp.y2:
                                    dy = (bb1.y1 - bbp.y2) * bb2.h / bb1.h - (
                                        bb2.y1 - bbp.y2
                                    )
                                else:
                                    dy = bb1.yc - bb2.yc
                            tr2 = trtf(dx, dy)
                            dh.global_transform(el, tr2)

        if setstroke:
            szd = dict()
            sfd = dict()
            szs = []
            for el in sela:
                sw, sf, _ = dh.composed_width(el, "stroke-width")

                elid = el.get_id()
                szd[elid] = sw
                sfd[elid] = sf
                if sw is not None:
                    szs.append(sw)

            fixedscale = False
            if self.options.strokemodes == 2:
                setstrokew = self.svg.cdocsize.unittouu(str(setstrokew) + "px")
            elif self.options.strokemodes == 3:
                fixedscale = True
            elif self.options.strokemodes == 5:
                from statistics import mean

                setstrokew = mean(szs)
            elif self.options.strokemodes == 6:
                from statistics import median

                setstrokew = median(szs)
            elif self.options.strokemodes == 7:
                setstrokew = min(szs)
            elif self.options.strokemodes == 8:
                setstrokew = max(szs)

            for el in sela:
                elid = el.get_id()
                if not (szd[elid] is None):
                    if not (fixedscale):
                        newsize = setstrokew
                    else:
                        newsize = szd[elid] * (setstrokew / 100)
                    if sfd[elid]==0:
                        continue
                    el.cstyle["stroke-width"] = str(newsize / sfd[elid]) + "px"

        if self.options.fusetransforms:
            for el in sela:
                if el.tag in otp_support_tags:
                    # Fuse the composed transform onto the path
                    el.ctransform = el.ccomposed_transform
                    fuseTransform(el)
                    el.ctransform = -el.getparent().ccomposed_transform
                    
                    
        if self.options.clearclipmasks:
            for el in sela:
                el.cstyle['clip-path'] = 'none'
                el.cstyle['mask'] = 'none'

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())


if __name__ == "__main__":
    dh.Run_SI_Extension(Homogenizer(), "Homogenizer")
