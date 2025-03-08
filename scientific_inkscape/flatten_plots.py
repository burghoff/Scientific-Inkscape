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
    StyleElement,
    NamedView,
    Defs,
    Metadata,
    ForeignObject,
    Group,
)

from inkex.text.utils import isrectangle
import lxml
from remove_kerning import remove_kerning


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
            "--removemanualkerning",
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
            "--removeduppaths",
            type=inkex.Boolean,
            default=True,
            help="Delete overlapping duplicate paths?",
        )
        pars.add_argument(
            "--removetextclips",
            type=inkex.Boolean,
            default=True,
            help="Remove clips and masks from text?",
        )
        pars.add_argument(
            "--replacement", type=str, default="Arial", help="Missing font replacement"
        )
        pars.add_argument(
            "--justification", type=int, default=1, help="Text justification"
        )
        pars.add_argument("--markexc", type=int, default=1, help="Exclude objects")
        pars.add_argument(
            "--testmode", type=inkex.Boolean, default=False, help="Test mode"
        )
        pars.add_argument("--v", type=str, default="1.2", help="Version for debugging")
        pars.add_argument(
            "--debugparser",
            type=inkex.Boolean,
            default=False,
            help="Use parser debugger?",
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
            if not hasattr(self.options, "enabled_profile"):
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
                self.options.removemanualkerning = True
                self.options.mergesubsuper = True
                self.options.setreplacement = True
                self.options.reversions = True
                self.options.removetextclips = True
                self.options.replacement = "sans-serif"
                self.options.justification = 1
        else:
            sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]

        splitdistant = self.options.splitdistant and self.options.fixtext
        removemanualkerning = self.options.removemanualkerning and self.options.fixtext
        mergesubsuper = self.options.mergesubsuper and self.options.fixtext
        mergenearby = self.options.mergenearby and self.options.fixtext
        setreplacement = self.options.setreplacement and self.options.fixtext
        reversions = self.options.reversions and self.options.fixtext
        removetextclips = self.options.removetextclips and self.options.fixtext

        sel = [el for el in self.svg.descendants2() if el in sel]  # doc order
        if self.options.tab == "Exclusions":
            self.options.markexc = {1: True, 2: False}[self.options.markexc]
            for el in sel:
                if self.options.markexc:
                    el.set("inkscape-scientific-flattenexclude", self.options.markexc)
                else:
                    el.set("inkscape-scientific-flattenexclude", None)
            return
        for el in sel:
            if el.get("inkscape-scientific-flattenexclude"):
                sel.remove(el)
        seld = [v for el in sel for v in el.descendants2()]
        for el in seld:
            if el.get("inkscape-scientific-flattenexclude"):
                seld.remove(el)

        # Move selected defs/clips/mask into global defs
        defstag = inkex.Defs.ctag
        clipmask = {inkex.addNS("mask", "svg"), inkex.ClipPath.ctag}
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
        gigtags = dh.tags((NamedView, Defs, Metadata, ForeignObject) + (Group,))

        gs = [el for el in seld if el.tag == gtag]
        ngs = [el for el in seld if el.tag not in gigtags]
        if len(gs) == 0 and len(ngs) == 0:
            inkex.utils.errormsg("No objects selected!")
            return

        if self.options.deepungroup:
            # Unlink all clones
            nels = []
            oels = []
            for el in seld:
                if isinstance(el, inkex.Use):
                    useel = el.get_link("xlink:href")
                    if useel is not None and not (isinstance(useel, (inkex.Symbol))):
                        ul = dh.unlink2(el)
                        nels.append(ul)
                        oels.append(el)
            for nel in nels:
                seld += nel.descendants2()
            for oel in oels:
                seld.remove(oel)
            gs = [el for el in seld if el.tag == gtag]
            ngs = [el for el in seld if el.tag not in gigtags]

            commenttag = lxml.etree.Comment
            commentdefs = {commenttag, defstag}
            sorted_gs = sorted(gs, key=lambda group: len(list(group)))
            # ascending order of size to reduce number of calls
            for g in sorted_gs:
                ks = g.getchildren()
                if any([k.tag == commenttag for k in ks]) and all(
                    [
                        k.tag in commentdefs or dh.EBget(k, "unlinked_clone") == "True"
                        for k in ks
                    ]
                ):
                    # Leave Matplotlib text glyphs grouped together
                    cmnt = ";".join(
                        [
                            str(k).strip("<!-- ").strip(" -->")
                            for k in ks
                            if k.tag == commenttag
                        ]
                    )
                    g.set("mpl_comment", cmnt)
                    [g.remove(k) for k in ks if isinstance(k, lxml.etree._Comment)]
                    # remove comment, but leave grouped
                elif dh.EBget(g, "mpl_comment") is not None:
                    pass
                else:
                    dh.ungroup(g, removetextclips)
            # dh.flush_stylesheet_entries(self.svg)

        prltag = dh.tags((PathElement, Rectangle, Line))
        if self.options.removerectw or reversions or self.options.revertpaths:
            from inkex.text.utils import default_style_atts as dsa

            fltag = dh.tags((FlowPara, FlowRegion, FlowRoot))
            nones = {None, "none"}
            wrects = []

            minusp = inkex.Path(
                "M 106,355 H 732 V 272 H 106 Z"
            )  # Matplotlib minus sign
            RECT_THRESHOLD = 2.49  # threshold ratio for rectangle reversion
            for ii, el in enumerate(ngs):
                if el.tag in prltag:
                    myp = el.getparent()
                    if (
                        myp is not None
                        and not (myp.tag in fltag)
                        and isrectangle(el, includingtransform=False)
                    ):
                        sty = el.cspecified_style
                        strk = sty.get("stroke", dsa.get("stroke"))
                        fill = sty.get("fill", dsa.get("fill"))
                        if strk in nones and fill not in nones:
                            sf = dh.get_strokefill(el)
                            if sf.fill is not None and tuple(sf.fill) == (
                                255,
                                255,
                                255,
                                1,
                            ):
                                wrects.append(el)

                            if reversions:
                                dv = el.get("d")
                                if (
                                    dv is not None
                                    and inkex.Path(dv)[0:3] == minusp[0:3]
                                ):
                                    t0 = el.ccomposed_transform
                                    if t0.a * t0.d - t0.b * t0.c < 0:
                                        bb = dh.bounding_box2(
                                            el, includestroke=False, dotransform=False
                                        )
                                        trl = inkex.Transform(
                                            "translate({0},{1})".format(bb.xc, bb.yc)
                                        )
                                        scl = inkex.Transform("scale(1,-1)")
                                        t0 = t0 @ trl @ scl @ (-trl)
                                    nt = inkex.TextElement()
                                    nt.set("id", el.get_id())
                                    myi = list(myp).index(el)
                                    el.delete()
                                    myp.insert(myi, nt)
                                    nt.text = chr(0x2212)  # minus sign
                                    nt.ctransform = (-myp.ccomposed_transform) @ t0
                                    nt.set("x", str(19.3964))
                                    nt.set("y", str(626.924))
                                    nt.cstyle = "font-size:999.997; font-family:sans-serif; fill:{0};".format(
                                        sf.fill
                                    )

                                    ngs.append(nt)
                                    ngs.remove(el)

                            if self.options.revertpaths:
                                bb = dh.bounding_box2(
                                    el, includestroke=False, dotransform=False, includeclipmask=False
                                )
                                if not bb.isnull:
                                    if bb.w < bb.h / RECT_THRESHOLD and not sf.fill_isurl:
                                        el.object_to_path()
                                        npv = "m {0},{1} v {2}".format(bb.xc, bb.y1, bb.h)
                                        el.set("d", npv)
                                        el.cstyle["stroke"] = sf.fill.to_rgb()
                                        if sf.fill.alpha != 1.0:
                                            el.cstyle["stroke-opacity"] = sf.fill.alpha
                                            el.cstyle["opacity"] = 1
                                        el.cstyle["fill"] = "none"
                                        el.cstyle["stroke-width"] = str(bb.w)
                                        el.cstyle["stroke-linecap"] = "butt"
                                    elif bb.h < bb.w / RECT_THRESHOLD and not sf.fill_isurl:
                                        el.object_to_path()
                                        npv = "m {0},{1} h {2}".format(bb.x1, bb.yc, bb.w)
                                        el.set("d", npv)
                                        el.cstyle["stroke"] = sf.fill.to_rgb()
                                        if sf.fill.alpha != 1.0:
                                            el.cstyle["stroke-opacity"] = sf.fill.alpha
                                            el.cstyle["opacity"] = 1
                                        el.cstyle["fill"] = "none"
                                        el.cstyle["stroke-width"] = str(bb.h)
                                        el.cstyle["stroke-linecap"] = "butt"

        TE_TAG = TextElement.ctag;
        if self.options.fixtext:
            if setreplacement:
                repl = self.options.replacement
                ttags = dh.tags((TextElement, Tspan))
                for el in ngs:
                    if el.tag in ttags and el.getparent() is not None:
                        # textelements not deleted
                        ff = el.cspecified_style.get("font-family")
                        el.cstyle["-inkscape-font-specification"] = None
                        if ff == None or ff == "none" or ff == "":
                            el.cstyle["font-family"] = repl
                        elif ff == repl:
                            pass
                        else:
                            ff = [
                                x.strip("'").strip('"').strip() for x in ff.split(",")
                            ]
                            if not (ff[-1].lower() == repl.lower()):
                                ff.append(repl)
                            el.cstyle["font-family"] = ",".join(ff)

            if removemanualkerning or mergesubsuper or splitdistant or mergenearby:
                jdict = {1: "middle", 2: "start", 3: "end", 4: None}
                justification = jdict[self.options.justification]
                ngs = remove_kerning(
                    ngs,
                    removemanualkerning,
                    mergesubsuper,
                    splitdistant,
                    mergenearby,
                    justification,
                    self.options.debugparser,
                )
            if removetextclips:
                for el in ngs:
                    if el.tag in dh.ttags:
                        el.set("clip-path", None)
                        el.set("mask", None)

        if self.options.removerectw or self.options.removeduppaths:
            ngset = set(ngs)
            ngs2 = [
                el for el in self.svg.descendants2() if el in ngset and dh.isdrawn(el)
            ]
            bbs = dh.BB2(self.svg, ngs2, roughpath=True, parsed=True)
            
            if self.options.removeduppaths:
                # Prune identical overlapping paths
                bbsp = {el:bbs[el.get_id()] for el in ngs2 if el.get_id() in bbs}
                txts = [el for el in self.svg.descendants2() if el.tag==TE_TAG and 'shape-inside' in el.cspecified_style]
                txt_inside = [el.cspecified_style.get_link("shape-inside",el.croot) for el in txts]
                bbsp = {el:v for el,v in bbsp.items() if el.tag in prltag and el not in txt_inside}
                
                els = list(bbsp.keys())
                sfs = [None]*len(els)
                
                import numpy as np
                if len(els)>0:
                    bbox_values = np.array(list(bbsp.values()))
                    left = bbox_values[:, 0]
                    top = bbox_values[:, 1]
                    width = bbox_values[:, 2]
                    height = bbox_values[:, 3]
                    right = left + width
                    bottom = top + height
                    size = np.maximum(width, height)
                    is_empty = (width == 0) | (height == 0)
                    left_diff = np.abs(left[:, np.newaxis] - left[np.newaxis, :])
                    top_diff = np.abs(top[:, np.newaxis] - top[np.newaxis, :])
                    right_diff = np.abs(right[:, np.newaxis] - right[np.newaxis, :])
                    bottom_diff = np.abs(bottom[:, np.newaxis] - bottom[np.newaxis, :])
                    size_i = size[:, np.newaxis]
                    size_j = size[np.newaxis, :]
                    size_max = np.maximum(size_i, size_j)
                    tol = 1e-6 * size_max
                    is_empty_pair = is_empty[:, np.newaxis] | is_empty[np.newaxis, :]
                    equal = (~is_empty_pair) & \
                            (left_diff <= tol) & \
                            (top_diff <= tol) & \
                            (right_diff <= tol) & \
                            (bottom_diff <= tol)
                else:
                    equal = np.zeros((0, 0), dtype=bool)
                        
                for jj in reversed(range(len(els))):
                    for ii in range(jj):
                        if equal[ii,jj]:
                            for kk in [ii,jj]:
                                if sfs[kk] is None:
                                    sfs[kk] = dh.get_strokefill(els[kk])
                            mysf  = sfs[jj]
                            othsf = sfs[ii]
                            if mysf.stroke is None and mysf.fill is None:
                                continue
                            if mysf.stroke is not None:
                                if mysf.stroke.alpha != 1.0 or othsf.stroke is None:
                                    continue
                                if not mysf.stroke == othsf.stroke:
                                    continue
                            if mysf.fill is not None:
                                if mysf.fill.alpha != 1.0 or othsf.fill is None:
                                    continue
                                if not mysf.fill == othsf.fill:
                                    continue
                            if not els[jj].cspecified_style == els[ii].cspecified_style:
                                continue
                                
                            mypth = els[jj].cpath.transform(els[jj].ccomposed_transform).to_absolute();
                            othpth= els[ii].cpath.transform(els[ii].ccomposed_transform).to_absolute();
                            if mypth!=othpth and mypth!=othpth.reverse():
                                continue
                            # dh.idebug(els[ii].get_id())
                            els[ii].delete(deleteup=True)
                            equal[ii,:] = False
                            ngs2.remove(els[ii])
            
            if self.options.removerectw:
                ngs3 = [el for el in ngs2 if el.get_id() in bbs]
                bbs3 = [dh.bbox(bbs.get(el.get_id())) for el in ngs3]
                wriis = [ii for ii, el in enumerate(ngs3) if el in wrects]
                wrbbs = [bbs3[ii] for ii in wriis]
                intrscts = dh.bb_intersects(bbs3, wrbbs)
                for jj, ii in enumerate(wriis):
                    if not any(intrscts[:ii, jj]):
                        ngs3[ii].delete(deleteup=True)
                        intrscts[ii, :] = False
                        ngs2.remove(ngs3[ii])
                        
                    

        # Remove any unused clips we made, unnecessary white space in document
        ds = self.svg.iddict.descendants
        clips = [dh.EBget(el, "clip-path") for el in ds]
        masks = [dh.EBget(el, "mask") for el in ds]
        clips = [url[5:-1] for url in clips if url is not None]
        masks = [url[5:-1] for url in masks if url is not None]

        ctag = inkex.ClipPath.ctag
        if hasattr(self.svg, "newclips"):
            for el in self.svg.newclips:
                if el.tag == ctag and not (el.get_id() in clips):
                    el.delete(deleteup=True)
                elif dh.isMask(el) and not (el.get_id() in masks):
                    el.delete(deleteup=True)

        ttags = dh.tags((Tspan, TextPath, FlowPara, FlowRegion, FlowSpan))
        ttags2 = dh.tags(
            (
                StyleElement,
                TextElement,
                Tspan,
                TextPath,
                inkex.FlowRoot,
                inkex.FlowPara,
                inkex.FlowRegion,
                inkex.FlowSpan,
            )
        )
        for el in reversed(ds):
            if not (el.tag in ttags):
                if el.tail is not None:
                    el.tail = None
            if not (el.tag in ttags2):
                if el.text is not None:
                    el.text = None


if __name__ == "__main__":
    dh.Run_SI_Extension(FlattenPlots(), "Flattener")
