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
    FlowRegion,
    FlowSpan,
    Tspan,
    TextPath,
    Rectangle,
    PathElement,
    Line,
    Path,
    StyleElement,
    NamedView,
    Defs,
    Metadata,
    ForeignObject,
    Group,
)

import os, sys

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh

import lxml, os
import RemoveKerning, Style0


class FlattenPlots(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument(
            "--deepungroup", type=inkex.Boolean, default=True, help="Deep ungroup"
        )
        pars.add_argument(
            "--fixtext", type=inkex.Boolean, default=True, help="Text fixes"
        )
        pars.add_argument(
            "--removerectw",
            type=inkex.Boolean,
            default=True,
            help="Remove white rectangles",
        )
        pars.add_argument(
            "--splitdistant",
            type=inkex.Boolean,
            default=True,
            help="Split distant text",
        )
        pars.add_argument(
            "--mergenearby", type=inkex.Boolean, default=True, help="Merge nearby text"
        )
        pars.add_argument(
            "--fixshattering",
            type=inkex.Boolean,
            default=True,
            help="Fix text shattering",
        )
        pars.add_argument(
            "--mergesubsuper",
            type=inkex.Boolean,
            default=True,
            help="Import superscripts and subscripts",
        )
        pars.add_argument(
            "--setreplacement",
            type=inkex.Boolean,
            default=False,
            help="Replace missing fonts",
        )
        pars.add_argument(
            "--replacement", type=str, default="Arial", help="Missing font replacement"
        )
        pars.add_argument(
            "--justification", type=int, default=1, help="Text justification"
        )
        pars.add_argument(
            "--testmode", type=inkex.Boolean, default=False, help="Test mode"
        )
        pars.add_argument("--v", type=str, default="1.2", help="Version for debugging")
        pars.add_argument(
            "--debugparser", type=inkex.Boolean, default=False, help="Use parser debugger?"
        )

    def duplicate_layer1(self):
        # For testing, duplicate selection and flatten its elements
        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        # should work with both v1.0 and v1.1
        for el in sel:
            d = el.duplicate()
            el.getparent().insert(list(el.getparent()).index(el), d)
            if d.get("inkscape:label") is not None:
                el.set("inkscape:label", el.get("inkscape:label") + " flat")
                d.set("inkscape:label", d.get("inkscape:label") + " original")
            d.set("sodipodi:insensitive", "true")
            # lock original
            d.set("opacity", 0.3)
        sel = [list(el) for el in sel]
        import itertools

        sel = list(itertools.chain.from_iterable(sel))
        return sel

    def effect(self):
        if self.options.testmode:
            if not hasattr(self.options,'enabled_profile'):
                self.options.enabled_profile = True
                self.options.lyr1 = self.duplicate_layer1()
                dh.ctic()
                self.effect()
                dh.ctoc()
                return
            else:
                sel = self.options.lyr1
                self.options.deepungroup = True
                self.options.fixtext = True
                self.options.removerectw = True
                self.options.splitdistant = True
                self.options.mergenearby = True
                self.options.fixshattering = True
                self.options.mergesubsuper = True
                self.options.setreplacement = True
                self.options.replacement = "sans-serif"
                self.options.justification = 1
        else:
            sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        
        splitdistant = self.options.splitdistant and self.options.fixtext
        fixshattering = self.options.fixshattering and self.options.fixtext
        mergesubsuper = self.options.mergesubsuper and self.options.fixtext
        mergenearby = self.options.mergenearby and self.options.fixtext
        setreplacement = self.options.setreplacement and self.options.fixtext

        sel = [el for el in self.svg.descendants2() if el in sel] # doc order
        seld = [v for el in sel for v in el.descendants2()]

        # Move selected defs/clips/mask into global defs
        if self.options.deepungroup:
            seldefs = [el for el in seld if isinstance(el, Defs)]
            for el in seldefs:
                self.svg.cdefs.append(el)
                for d in el.descendants2():
                    if d in seld:
                        seld.remove(d)  # no longer selected
            selcm = [
                el for el in seld if isinstance(el, (inkex.ClipPath)) or dh.isMask(el)
            ]
            for el in selcm:
                self.svg.cdefs.append(el)
                for d in el.descendants2():
                    if d in seld:
                        seld.remove(d)  # no longer selected
        
        
        ignores = (NamedView, Defs, Metadata, ForeignObject)
        
        gtag = inkex.Group.ctag
        gigtags = dh.tags(ignores+(Group,))
        
        gs = [el for el in seld if el.tag==gtag]
        ngs = [el for el in seld if el.tag not in gigtags]

        if len(gs) == 0 and len(ngs) == 0:
            inkex.utils.errormsg("No objects selected!")
            return

        if self.options.deepungroup:
            # Unlink all clones
            nels = []; oels = [] 
            for el in seld:
                if isinstance(el, inkex.Use):
                    useel = el.get_link("xlink:href")
                    if useel is not None and not(isinstance(useel, (inkex.Symbol))):
                        ul = dh.unlink2(el)
                        nels.append(ul);
                        oels.append(el);
            for nel in nels:
                seld += nel.descendants2()
            for oel in oels:
                seld.remove(oel)
            gs = [el for el in seld if el.tag==gtag]
            ngs = [el for el in seld if el.tag not in gigtags]

            sorted_gs = sorted(gs, key=lambda group: len(list(group)))
            # ascending order of size to reduce number of calls
            for g in sorted_gs:
                # dh.idebug(g.get_id())
                ks = g.getchildren()
                if any([isinstance(k, lxml.etree._Comment) for k in ks]) and all(
                    [
                        isinstance(k, (lxml.etree._Comment, Defs))
                        or dh.EBget(k,"unlinked_clone") == "True"
                        for k in ks
                    ]
                ):
                    # Leave Matplotlib text glyphs grouped together
                    cmnt = ";".join(
                        [
                            str(k).strip("<!-- ").strip(" -->")
                            for k in ks
                            if isinstance(k, lxml.etree._Comment)
                        ]
                    )
                    g.set("mpl_comment", cmnt)
                    [g.remove(k) for k in ks if isinstance(k, lxml.etree._Comment)]
                    # remove comment, but leave grouped
                elif dh.EBget(g,"mpl_comment") is not None:
                    pass
                else:
                    dh.ungroup(g)
            dh.flush_stylesheet_entries(self.svg)

        if self.options.fixtext:
            if setreplacement:
                repl = self.options.replacement
                for el in ngs:
                    if (
                        isinstance(el, (TextElement, Tspan))
                        and el.getparent() is not None
                    ):  # textelements not deleted
                        ff = el.cspecified_style.get("font-family")
                        # dh.Set_Style_Comp(el, "-inkscape-font-specification", None)
                        el.cstyle["-inkscape-font-specification"]= None
                        if ff == None or ff == "none" or ff == "":
                            # dh.Set_Style_Comp(el, "font-family", replacement)
                            el.cstyle["font-family"]=repl
                        elif ff == repl:
                            pass
                        else:
                            ff = [x.strip("'").strip() for x in ff.split(",")]
                            if not (ff[-1].lower() == repl.lower()):
                                ff.append(repl)
                            # dh.Set_Style_Comp(el, "font-family", ",".join(ff))
                            el.cstyle["font-family"]=",".join(ff)

            if fixshattering or mergesubsuper or splitdistant or mergenearby:
                jdict = {1: "middle", 2: "start", 3: "end", 4: None}
                justification = jdict[self.options.justification]
                ngs = RemoveKerning.remove_kerning(
                    ngs,
                    fixshattering,
                    mergesubsuper,
                    splitdistant,
                    mergenearby,
                    justification,self.options.debugparser
                )

        if self.options.removerectw:
            prltag = dh.tags((PathElement, Rectangle, Line))
            fltag  = dh.tags((FlowPara, FlowRegion, FlowRoot))
            nones = {None, "none", "None"}
            wrects = []
            for ii, el in enumerate(ngs):
                if el.tag in prltag:
                    myp = el.getparent()
                    if myp is not None and not(myp.tag in fltag) and dh.isrectangle(el,includingtransform=False):
                        sty = el.cspecified_style
                        strk = sty.get("stroke", None)
                        fill = sty.get("fill", None)
                        if strk in nones and fill not in nones:
                            sf = dh.get_strokefill(el)
                            if sf.fill is not None and tuple(sf.fill) == (255, 255, 255, 1):
                                wrects.append(el)
                                
            ngset = set(ngs)
            ngs2 = [el for el in self.svg.descendants2() if el in ngset and dh.isdrawn(el)]
            bbs = dh.BB2(self,ngs2,roughpath=True,parsed=True);
            ngs3 = [el for el in ngs2 if el.get_id() in bbs]
            bbs = [dh.bbox(bbs.get(el.get_id())) for el in ngs3];
            wriis = [ii for ii,el in enumerate(ngs3) if el in wrects]
            wrbbs = [bbs[ii] for ii in wriis]
            intrscts = dh.bb_intersects(bbs,wrbbs);
            for jj,ii in enumerate(wriis):                    
                if not any(intrscts[:ii,jj]):
                    dh.deleteup(ngs3[ii])
                    intrscts[ii,:]=False



        # Remove any unused clips we made, unnecessary white space in document
        ds = self.svg.iddict.ds
        clips = [dh.EBget(el,"clip-path") for el in ds]
        masks = [dh.EBget(el,"mask") for el in ds]
        clips = [url[5:-1] for url in clips if url is not None]
        masks = [url[5:-1] for url in masks if url is not None]
        
        ctag = inkex.ClipPath.ctag
        if hasattr(self.svg, "newclips"):
            for el in self.svg.newclips:
                if el.tag==ctag and not (el.get_id() in clips):
                    dh.deleteup(el)
                elif dh.isMask(el) and not (el.get_id() in masks):
                    dh.deleteup(el)

        ttags = dh.tags((Tspan, TextPath, FlowPara, FlowRegion, FlowSpan))
        ttags2 = dh.tags((StyleElement,TextElement,Tspan,TextPath,)+dh.flow_types)
        for el in reversed(ds):
            if not (el.tag in ttags):
                if el.tail is not None:
                    el.tail = None
            if not (el.tag in ttags2):
                if el.text is not None:
                    el.text = None


if __name__ == "__main__":
    dh.Run_SI_Extension(FlattenPlots(),"Flattener")

