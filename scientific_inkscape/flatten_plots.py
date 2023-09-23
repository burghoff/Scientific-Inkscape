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
import RemoveKerning


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
            "--reversions",
            type=inkex.Boolean,
            default=True,
            help="Revert known paths to text",
        )
        pars.add_argument(
            "--revertpaths",
            type=inkex.Boolean,
            default=True,
            help="Revert certain paths to strokes?",
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
                self.options.revertpaths = True
                self.options.splitdistant = True
                self.options.mergenearby = True
                self.options.fixshattering = True
                self.options.mergesubsuper = True
                self.options.setreplacement = True
                self.options.reversions = True
                self.options.replacement = "sans-serif"
                self.options.justification = 1
        else:
            sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        
        splitdistant = self.options.splitdistant and self.options.fixtext
        fixshattering = self.options.fixshattering and self.options.fixtext
        mergesubsuper = self.options.mergesubsuper and self.options.fixtext
        mergenearby = self.options.mergenearby and self.options.fixtext
        setreplacement = self.options.setreplacement and self.options.fixtext
        reversions = self.options.reversions and self.options.fixtext

        sel = [el for el in self.svg.descendants2() if el in sel] # doc order
        seld = [v for el in sel for v in el.descendants2()]

        # Move selected defs/clips/mask into global defs
        defstag = inkex.Defs.ctag
        clipmask = {inkex.addNS('mask','svg'),inkex.ClipPath.ctag}
        if self.options.deepungroup:
            seldefs = [el for el in seld if el.tag == defstag]
            for el in seldefs:
                self.svg.cdefs.append(el)
                for d in el.descendants2():
                    if d in seld:
                        seld.remove(d)  # no longer selected
            selcm = [el for el in seld if el.tag in clipmask]
            for el in selcm:
                self.svg.cdefs.append(el)
                for d in el.descendants2():
                    if d in seld:
                        seld.remove(d)  # no longer selected

        gtag = inkex.Group.ctag
        gigtags = dh.tags((NamedView, Defs, Metadata, ForeignObject)+(Group,))
        
        gs  = [el for el in seld if el.tag==gtag]
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

            commenttag = lxml.etree.Comment
            commentdefs = {commenttag, defstag}
            sorted_gs = sorted(gs, key=lambda group: len(list(group)))
            # ascending order of size to reduce number of calls
            for g in sorted_gs:
                ks = g.getchildren()
                if any([k.tag==commenttag for k in ks]) and all(
                    [
                        k.tag in commentdefs
                        or dh.EBget(k,"unlinked_clone") == "True"
                        for k in ks
                    ]
                ):
                    # Leave Matplotlib text glyphs grouped together
                    cmnt = ";".join(
                        [str(k).strip("<!-- ").strip(" -->") for k in ks if k.tag==commenttag]
                    )
                    g.set("mpl_comment", cmnt)
                    [g.remove(k) for k in ks if isinstance(k, lxml.etree._Comment)]
                    # remove comment, but leave grouped
                elif dh.EBget(g,"mpl_comment") is not None:
                    pass
                else:
                    dh.ungroup(g)
            dh.flush_stylesheet_entries(self.svg)

        if self.options.removerectw or reversions or self.options.revertpaths:
            prltag = dh.tags((PathElement, Rectangle, Line))
            fltag  = dh.tags((FlowPara, FlowRegion, FlowRoot))
            nones = {None, "none", "None"}
            wrects = []
            
            minusp = inkex.Path('M 106,355 H 732 V 272 H 106 Z') # Matplotlib minus sign
            for ii, el in enumerate(ngs):
                if el.tag in prltag:
                    myp = el.getparent()
                    # dh.idebug((el.get_id(),dh.isrectangle(el,includingtransform=False)[0]))
                    if myp is not None and not(myp.tag in fltag) and dh.isrectangle(el,includingtransform=False)[0]:
                        sty = el.cspecified_style
                        strk = sty.get("stroke", None)
                        fill = sty.get("fill", None)
                        if strk in nones and fill not in nones:
                            sf = dh.get_strokefill(el)
                            if sf.fill is not None and tuple(sf.fill) == (255, 255, 255, 1):
                                wrects.append(el)
                                
                            if reversions:
                                dv = el.get('d')
                                if dv is not None and inkex.Path(dv)[0:3]==minusp[0:3]:
                                    t0 = el.ccomposed_transform
                                    if t0.a*t0.d-t0.b*t0.c<0:
                                        bb = dh.bounding_box2(el,includestroke=False,dotransform=False)
                                        trl = inkex.Transform('translate({0},{1})'.format(bb.xc,bb.yc))
                                        scl = inkex.Transform('scale(1,-1)')
                                        t0 = t0 @ trl @ scl @ (-trl)
                                    nt = inkex.TextElement()
                                    nt.set('id',el.get_id())
                                    myi = list(myp).index(el)
                                    el.delete()
                                    myp.insert(myi,nt)
                                    nt.text = chr(0x2212) # minus sign
                                    nt.ctransform = (-myp.ccomposed_transform) @ t0
                                    nt.set('x',str(19.3964))
                                    nt.set('y',str(626.924))
                                    nt.cstyle='font-size:999.997; font-family:sans-serif; fill:{0};'.format(sf.fill)
                                    
                                    ngs.append(nt)
                                    ngs.remove(el)
                                    
                            if self.options.revertpaths:
                                bb = dh.bounding_box2(el,includestroke=False,dotransform=False)
                                if bb.w < bb.h*0.1:
                                    dh.object_to_path(el)
                                    np = 'm {0},{1} v {2}'.format(bb.xc,bb.y1,bb.h)
                                    el.set('d',np)
                                    el.cstyle['stroke']=sf.fill.to_rgb()
                                    if sf.fill.alpha!=1.0:
                                        el.cstyle['stroke-opacity']=sf.fill.alpha
                                        el.cstyle['opacity']=1
                                    el.cstyle['fill']='none'
                                    el.cstyle['stroke-width']=str(bb.w)
                                elif bb.h < bb.w*0.1:
                                    dh.object_to_path(el)
                                    np = 'm {0},{1} h {2}'.format(bb.x1,bb.yc,bb.w)
                                    el.set('d',np)
                                    el.cstyle['stroke']=sf.fill
                                    el.cstyle['fill']='none'
                                    el.cstyle['stroke-width']=str(bb.h)
                                    
                                    
        if self.options.fixtext:
            if setreplacement:
                repl = self.options.replacement
                ttags = dh.tags((TextElement, Tspan))
                for el in ngs:
                    if el.tag in ttags and el.getparent() is not None:
                        # textelements not deleted
                        ff = el.cspecified_style.get("font-family")
                        el.cstyle["-inkscape-font-specification"]= None
                        if ff == None or ff == "none" or ff == "":
                            el.cstyle["font-family"]=repl
                        elif ff == repl:
                            pass
                        else:
                            ff = [x.strip("'").strip() for x in ff.split(",")]
                            if not (ff[-1].lower() == repl.lower()):
                                ff.append(repl)
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

