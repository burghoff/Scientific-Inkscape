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
    Group,
    FontFace,
    FlowSpan,
    Image,
    FlowRegion,
)
import os, sys

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh

from applytransform_mod import ApplyTransform
import math
from Style2 import Style2

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
            "--fusetransforms",
            type=inkex.Boolean,
            default=False,
            help="Fuse transforms to paths?",
        )

    def effect(self):
        import random

        random.seed(1)
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

        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        # should work with both v1.0 and v1.1
        sel = [v for el in sel for v in dh.descendants2(el)]

        sela = [el for el in sel if not (isinstance(el, badels))]
        sel = [
            el
            for el in sel
            if isinstance(el, (TextElement, Tspan, FlowRoot, FlowPara, FlowSpan))
        ]

        def BB2(els,forceupdate):
            if all([isinstance(d, (TextElement)) for d in els]):
                import TextParser
                bbs = dict();
                if forceupdate and hasattr(self.svg, '_char_table'):
                    delattr(self.svg,'_char_table')
                for d in els:
                    inkbb = d.parsed_text.get_full_inkbbox();
                    bbs[d.get_id2()] = inkbb.transform(d.ccomposed_transform).sbb
            else:
                bbs = dh.Get_Bounding_Boxes(self, forceupdate)
                # dh.idebug('here')
            return bbs

        if setfontfamily or setfontsize or fixtextdistortion:
            tels = [d for d in sel if isinstance(d, (TextElement, FlowRoot))]
            bbs = BB2(tels,False)
            # bbs = dh.Get_Bounding_Boxes(self)

        
        if setfontsize:
            # Get all font sizes and scale factors
            szd = dict()
            sfd = dict()
            for el in sel:
                actualsize, sf, ct, ang = dh.Get_Composed_Width(
                    el, "font-size", nargout=4
                )
                elid = el.get_id()
                szd[elid] = actualsize
                sfd[elid] = sf
            # Get font sizes of all root text elements (max size) and convert sub/superscripts to relative size
            szs = []
            for el in sel:
                if isinstance(el, (TextElement, FlowRoot)):
                    maxsz = float("-inf")
                    for d in dh.descendants2(el):
                        if (d.text is not None and len(d.text) > 0) or (
                            d.tail is not None and len(d.tail) > 0
                        ):
                            mysz = szd[d.get_id()]
                            maxsz = max(maxsz, mysz)

                            sty = d.ccascaded_style
                            bshift = sty.get("baseline-shift")
                            if bshift in ["sub", "super"]:
                                psz = szd[d.getparent().get_id()]
                                pct = mysz / psz * 100
                                dh.Set_Style_Comp(d, "font-size", str(pct) + "%")
                    maxsz = maxsz / self.svg.unittouu("1pt")
                    szs.append(maxsz)
            # Determine scale and/or size
            fixedscale = False
            if self.options.fontmodes == 3:
                fixedscale = True
            elif self.options.fontmodes == 4:
                fixedscale = True
                fontsize = fontsize / max(szs) * 100
            elif self.options.fontmodes == 5:
                from statistics import mean

                fontsize = mean(szs)
            elif self.options.fontmodes == 6:
                from statistics import median

                fontsize = median(szs)
            elif self.options.fontmodes == 7:
                fontsize = min(szs)
            elif self.options.fontmodes == 8:
                fontsize = max(szs)
            # Set the font sizes
            for el in sel:
                elid = el.get_id()
                actualsize = szd[elid]
                sf = sfd[elid]
                if not (fixedscale):
                    newsize = self.svg.unittouu("1pt") * fontsize
                else:
                    newsize = actualsize * (fontsize / 100)
                fs = el.cstyle.get("font-size")
                if fs is None or not ("%" in fs):  # keep sub/superscripts relative size
                    dh.Set_Style_Comp(el, "font-size", str(newsize / sf) + "px")

        

        if fixtextdistortion:
            # make a new transform that removes bad scaling and shearing (see General_affine_transformation.nb)
            for el in sel:
                ct = el.ccomposed_transform
                detv = ct.a * ct.d - ct.b * ct.c
                signdet = -1 * (detv < 0) + (detv >= 0)
                sqrtdet = math.sqrt(abs(detv))
                magv = math.sqrt(ct.b ** 2 + ct.a ** 2)
                ctnew = Transform(
                    [
                        [ct.a * sqrtdet / magv, -ct.b * sqrtdet * signdet / magv, ct.e],
                        [ct.b * sqrtdet / magv, ct.a * sqrtdet * signdet / magv, ct.f],
                    ]
                )
                dh.global_transform(el, (ctnew @ (-ct)))

        if setfontfamily:
            for el in reversed(sel):
                dh.Set_Style_Comp(el, "font-family", fontfamily)
                dh.Set_Style_Comp(el, "-inkscape-font-specification", None)
                if fontfamily.lower() in ["avenir", "whitney", "whitney book"] and isinstance(
                    el, (TextElement, FlowRoot)
                ):
                    dh.Replace_Non_Ascii_Font(el, "Avenir Next, Arial")

        
        if setfontfamily or setfontsize or fixtextdistortion:
            bbs2 = BB2(tels,True)
            # bbs2 = dh.Get_Bounding_Boxes(self,True)
            for el in sel:
                myid = el.get_id()
                if (
                    isinstance(el, (TextElement, FlowRoot))
                    and myid in list(bbs.keys())
                    and myid in list(bbs2.keys())
                ):
                    bb = bbs[el.get_id()]
                    bb2 = bbs2[el.get_id()]
                    tx = (bb2[0] + bb2[2] / 2) - (bb[0] + bb[2] / 2)
                    ty = (bb2[1] + bb2[3] / 2) - (bb[1] + bb[3] / 2)
                    trl = Transform("translate(" + str(-tx) + ", " + str(-ty) + ")")
                    dh.global_transform(el, trl)

        if setstroke:
            szd = dict()
            sfd = dict()
            szs = []
            for el in sela:
                sw, sf, ct, ang = dh.Get_Composed_Width(el, "stroke-width", nargout=4)

                elid = el.get_id()
                szd[elid] = sw
                sfd[elid] = sf
                if sw is not None:
                    szs.append(sw)

            fixedscale = False
            if self.options.strokemodes == 2:
                setstrokew = self.svg.unittouu(str(setstrokew) + "px")
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
                    dh.Set_Style_Comp(
                        el, "stroke-width", str(newsize / sfd[elid]) + "px"
                    )

        if self.options.fusetransforms:
            for el in sela:
                ApplyTransform().recursiveFuseTransform(el)

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())


if __name__ == "__main__":
    dh.Version_Check("Homogenizer")
    Homogenizer().run()
