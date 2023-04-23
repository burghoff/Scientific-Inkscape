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


# The TextParser parses text in a document according to the way Inkscape handles it.
# In short, every TextElement is parsed into a ParsedText.
# Each ParsedText contains a collection of tlines, representing one line of text.
# Each tline contains a collection of tchars, representing a single character.
# Characters are also grouped into twords, which represent groups of characters 
# sharing an anchor (may or may not be actual words).
#
# These functions allow text metrics and bounding boxes to be calculated without binary
# calls to Inkscape. It can calculate both the ink bounding box (i.e., where characters'
# ink is) as well as the extent bounding box (i.e, its logical location).
# The extent of a character is defined as extending between cursor positions in the 
# x-direction and between the baseline and capital height in the y-direction.
# 
# Some examples:
# el.parsed_text.get_full_inkbbox(): gets the untransformed bounding box of the whole element
# el.parsed_text.get_char_extents(): gets all characters' untransformed extents
# el.parse_text.lns[0].cs[0].pts_ut: the untransformed points of the extent of the first character of the first line
# el.parse_text.lns[0].cs[0].pts_t : the transformed points of the extent of the first character of the first line
#
# Before parsing is done, a character table must be generated to determine the properties
# of all the characters present. This is done automatically by the first invocation of .parsed_text,
# which automatically analyzes the whole document and adds it to the SVG. If you are only 
# parsing a few text elements, this can be sped up by calling svg.make_char_table(els).
# This can occasionally fail: when this happens, a command call is performed instead as a fallback.
#
# Known limitations:
#   Does not support flows, only TextElements
#   When a font has missing characters, command fallback is invoked.
#   When Pango cannot find the appropriate font, command fallback is invoked.
#   Ligatures width not exactly correct

KERN_TABLE = True # generate a fine kerning table for each font?
TEXTSIZE = 100;   # size of rendered text

import os, sys, itertools
from functools import lru_cache
import numpy as np

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh
from speedups import Vector2da as v2d
import speedups as su
from dhelpers import bbox

from pango_renderer import PangoRenderer
pr = PangoRenderer();

from copy import copy
import inkex
from inkex import TextElement, Tspan, Transform


# Add parsed_text property to TextElements
def get_parsed_text(el):
    if not (hasattr(el, "_parsed_text")):
        el._parsed_text = ParsedText(el, el.croot.char_table);
    return el._parsed_text
inkex.TextElement.parsed_text = property(get_parsed_text)

# Add character table property and function to SVG
tetag = TextElement.tag2
def make_char_table_fcn(svg,els=None):
    # Can be called with els argument to examine list of elements only 
    # (otherwise use entire SVG)
    if els is None: 
        tels = [d for d in svg.cdescendants if d.tag==tetag];
    else:           
        tels = [d for d in els              if d.tag==tetag]
    svg._char_table = Character_Table(tels)
def get_char_table(svg):
    if not (hasattr(svg, "_char_table")):
        svg.make_char_table()
    return svg._char_table
inkex.SvgDocumentElement.make_char_table = make_char_table_fcn
inkex.SvgDocumentElement.char_table = property(get_char_table)



# A text element that has been parsed into a list of lines
class ParsedText:
    def __init__(self, el, ctable, debug=False):
        self.ctable = ctable
        self.textel = el

        self.lns = self.Parse_Lines()
        self.Finish_Lines()

        # Compute the bb/pts_ut/pts_t after parsing, prior to any mods
        for ln in self.lns:
            for w in ln.ws:
                w.parsed_bb = copy(w.bb)
                for c in w.cs:
                    c.parsed_pts_ut = c.pts_ut
                    c.parsed_pts_t = c.pts_t

        tlvllns = [ln for ln in self.lns if ln.tlvlno is not None and ln.tlvlno > 0]
        # top-level lines after 1st
        self.isinkscape = (
            all([ln.sprl for ln in tlvllns])
            and len(tlvllns) > 0
            and all(
                [
                    ln.style.get("-inkscape-font-specification") is not None
                    for ln in self.lns
                ]
            )
        )
        # probably made in Inkscape
        self.ismlinkscape = self.isinkscape and len(self.lns) > 1
        # multi-line Inkscape

        sty = el.cspecified_style
        self.issvg2 = (
            sty.get("inline-size") is not None or sty.get("shape-inside") is not None
        )
        # svg2 flows

    def duplicate(self):
        # Duplicates a PT and its text without reparsing
        ret = copy(self)
        ret.textel = self.textel.duplicate2()
        ret.tree = None
        cmemo = {d1v : d2v for d1v,d2v in zip(self.tree.ds,ret.tree.ds)}

        ret.dxs, ret.dys = ret.dxs[:], ret.dys[:]
        ret.lns = []
        for ln in self.lns:
            if len(ln.cs) == 0:
                continue
            ret_ln = ln.copy(cmemo)
            ret_ln.pt = ret
            ret.lns.append(ret_ln)
        
        # nextw et al. could be from any line, update after copying
        for ret_ln in ret.lns:
            for ret_w in ret_ln.ws:
                ret_w.nextw = cmemo.get(ret_w.nextw)
                ret_w.prevw = cmemo.get(ret_w.prevw)
                ret_w.prevsametspan = cmemo.get(ret_w.prevsametspan)
        return ret

    def txt(self):
        return [v.txt() for v in self.lns]

    # Every text element in an SVG can be thought of as a group of lines.
    # A line is a collection of text that gets its position from a single source element.
    # This position may be directly set, continued from a previous line, or inherited from a previous line
    def Parse_Lines(self, srcsonly=False):
        # dh.idebug('hello')
        el = self.textel
        # First we get the tree structure of the text and do all our gets
        # ds, pts, cd, pd = dh.descendants2(el, True)
        ds, pts, pd = self.tree.ds, self.tree.ptails, self.tree.pdict
        
        Nd = len(ds)
        ks = list(el)
        text = [d.text for d in ds]
        ptail = [[tel.tail for tel in pt] for pt in pts]  # preceding tails
        # if len(ptail) > 0 and len(ptail[-1]) > 0:
        #     ptail[-1][-1] = None
            # do not count el's tail

        # Next we find the top-level sodipodi:role lines
        xs = [ParsedText.GetXY(d, "x") for d in ds]
        ys = [ParsedText.GetXY(d, "y") for d in ds]
        nspr = [d.get("sodipodi:role") for d in ds]
        nspr[0] = None
        sprl = [
            nspr[ii] == "line" and len(xs[ii]) == 1 and len(ys[ii]) == 1
            for ii in range(len(ds))
        ]

        # Find effective sprls (ones that are not disabled)
        esprl = copy(sprl)
        for ii in range(len(ds)):
            # Any non-sprl ancestor disables spr:l on me
            cel = ds[ii]
            while esprl[ii] and cel != el:
                esprl[ii] = esprl[ii] and sprl[ds.index(cel)]
                cel = pd[cel]

            # If I don't have text and any descendants have position, disables spr:l
            if esprl[ii] and (text[ii] == "" or text[ii] is None):
                dstop = [jj for jj in range(len(pts)) if ds[ii] in pts[jj]][0]
                # should exist
                for di in range(ii + 1, dstop):
                    if xs[di][0] is not None or ys[di][0] is not None:
                        if text[di] is not None and text[di] != "":
                            # dh.debug(text[di])
                            esprl[ii] = False

            # Only top-level tspans are sprl
            esprl[ii] = esprl[ii] and ds[ii] in ks

        # Figure out which effective sprls are top-level
        types = [None] * len(ds)
        for ii in range(len(ds)):
            if esprl[ii]:
                if len(ptail[ii]) > 0 and ptail[ii][-1] is not None:
                    types[ii] = "precededsprl"
                elif ds[ii] == ks[0] and text[0] is not None:# and len(text[0])>0:
                    # 2022.08.17: I am not sure if the len(text[0])==0 condition should be included
                    # Inkscape prunes text='', so not relevant most of the time
                    # It does seem to make a difference though
                    types[ii] = "precededsprl"
                else:
                    types[ii] = "tlvlsprl"
            else:
                types[ii] = "normal"

        # Position has a property of bidirectional inheritance. A tspan can inherit
        # position from its parent or its descendant unless there is text in between.
        # Down-inheritance requires that text be present
        # Aborts if a sprl is encountered
        def inherits_from(iin):
            jmax = iin
            while (
                jmax < Nd - 1
                and text[jmax] in ["", None]
                and pd[ds[jmax + 1]] == ds[jmax]
                and not (esprl[jmax + 1])
            ):
                jmax += 1
            if jmax < Nd - 1 and text[jmax] in ["", None]:
                jmax = iin

            jmin = iin
            while (
                jmin > 0
                and text[jmin - 1] in ["", None]
                and ds[jmin - 1] == pd[ds[jmin]]
                and not (esprl[jmin - 1])
            ):
                jmin -= 1
            return jmin, jmax  # includes endpoints

        def inheritNone(iin, xy):
            if xy[iin][0] is None:
                imin, imax = inherits_from(iin)
                vld = [ii for ii in range(imin, imax + 1) if xy[ii][0] is not None]
                if len(vld) > 0:
                    if any([ii <= iin for ii in vld]):
                        vld = [ii for ii in vld if ii <= iin]
                        # inherit up if possible
                    dist = [abs(ii - iin) for ii in vld]
                    ic = [vld[ii] for ii in range(len(vld)) if dist[ii] == min(dist)][0]
                    return xy[ic], ds[ic]
            return xy[iin], ds[iin]

        # For positions that are None, inherit from ancestor/descendants if possible
        ixs = copy(xs)
        iys = copy(ys)
        xsrcs = [None] * len(ds)
        ysrcs = [None] * len(ds)
        for ii in range(0, len(ds)):
            xv = xs[ii]
            xsrc = ds[ii]
            yv = ys[ii]
            ysrc = ds[ii]
            if xv[0] is None:
                xv, xsrc = inheritNone(ii, xs)
            if yv[0] is None:
                yv, ysrc = inheritNone(ii, ys)
            ixs[ii] = xv
            iys[ii] = yv
            xsrcs[ii] = xsrc
            ysrcs[ii] = ysrc

        if ixs[0][0] is None:
            ixs[0] = [0]  # at least the parent needs a position
        if iys[0][0] is None:
            iys[0] = [0]

        # Finally, walk the text tree generating lines
        lns = []
        sprl_inherits = None
        # for di, tt in ttgenerator(Nd):
        #     if tt == 0:
        #         txts = ptail[di]
        #         tels = pts[di]
        #     else:
        #         txts = [text[di]]
        #         tels = [ds[di]]

        #     for ii in range(len(tels)):
        #         tel = tels[ii]
        #         txt = txts[ii]
                
        for di, tt, tel, txt in self.tree.dgenerator():
            newsprl = tt == 1 and types[di] == "tlvlsprl"
            if (txt is not None and len(txt) > 0) or newsprl:
                sel = tel
                if tt == 0:
                    sel = pd[tel]
                    # tails get their sty from the parent of the element the tail belongs to
                sty = sel.cspecified_style
                ct = sel.ccomposed_transform
                fs, sf, ct, ang = dh.Get_Composed_Width(sel, "font-size", 4)

                if newsprl:
                    lh = dh.Get_Composed_LineHeight(sel)
                nsty = Character_Table.normalize_style(sty)

                # Make a new line if we're sprl or if we have a new x or y
                if len(lns) == 0 or (
                    tt == 1
                    and (
                        newsprl
                        or (
                            types[di] == "normal"
                            and (ixs[di][0] is not None or iys[di][0] is not None)
                        )
                    )
                ):
                    edi = di
                    if tt == 0:
                        edi = ds.index(sel)
                    xv = ixs[edi]
                    xsrc = xsrcs[edi]
                    yv = iys[edi]
                    ysrc = ysrcs[edi]
                    if newsprl:
                        if len(lns) == 0:
                            xv = [ixs[0][0]]
                            xsrc = xsrcs[0]
                            yv = [iys[0][0]]
                            ysrc = ysrcs[0]
                        else:
                            xv = [sprl_inherits.x[0]]
                            xsrc = sprl_inherits.xsrc
                            yv = [sprl_inherits.y[0] + lh / sf]
                            ysrc = sprl_inherits.ysrc
                        issprl = True
                        continuex = False
                        continuey = False
                    else:
                        continuex = False
                        issprl = False
                        if xv[0] is None:
                            if len(lns) > 0:
                                xv = copy(lns[-1].x)
                                xsrc = lns[-1].xsrc
                            else:
                                xv = copy(ixs[0])
                                xsrc = xsrcs[0]
                            continuex = True
                            # issprl = True;
                        continuey = False
                        if yv[0] is None:
                            if len(lns) > 0:
                                yv = copy(lns[-1].y)
                                ysrc = lns[-1].ysrc
                            else:
                                yv = copy(iys[0])
                                ysrc = ysrcs[0]
                            continuey = True

                    if srcsonly:  # quit and return srcs of first line
                        return xsrc, ysrc

                    tlvlno = None
                    if di < Nd and ds[di] in ks:
                        tlvlno = ks.index(ds[di])
                    elif edi == 0:
                        tlvlno = 0

                    anch = sty.get("text-anchor")
                    if len(lns) > 0 and nspr[edi] != "line":
                        if lns[-1].anchor is not None:
                            anch = lns[
                                -1
                            ].anchor  # non-spr lines inherit the previous line's anchor
                    if anch is None:
                        anch = "start"
                    txtdir = sty.get("direction")
                    if txtdir is not None:
                        if txtdir == "rtl":
                            if anch == "start":
                                anch = "end"
                            elif anch == "end":
                                anch = "start"
                    
                    sprlabove = []
                    cel = ds[edi];
                    while cel!=el:
                        if cel.get('sodipodi:role')=='line':
                            sprlabove.append(cel);
                        cel = pd[cel]
                    
                    lns.append(tline(self,xv,yv,xsrc,ysrc,issprl,sprlabove,
                            anch,ct,ang,tlvlno,sty,continuex,continuey))

                    if newsprl or len(lns) == 1:
                        sprl_inherits = lns[-1]

                if txt is not None:
                    for jj, c in enumerate(txt):
                        # prop = self.ctable.get_prop(c, nsty) * fs
                        # prop = self.ctable.get_prop_mult(c, nsty, fs/sf)
                        prop = self.ctable.get_prop(c, nsty)
                        ttv = 'tail' if tt==0 else 'text'
                        tchar(c, fs, sf, prop, sty, nsty, cloc(tel, ttv, jj),lns[-1])

                        if jj == 0:
                            lsp0 = lns[-1].cs[-1].lsp
                            bshft0 = lns[-1].cs[-1].bshft
                        else:
                            lns[-1].cs[-1].lsp = lsp0
                            lns[-1].cs[-1].bshft = bshft0
        return lns

    def Finish_Lines(self):
        if self.lns is not None:
            self.Get_Delta(self.lns, self.textel, "dx")
            self.Get_Delta(self.lns, self.textel, "dy")

            self.dxs = [c.dx for ln in self.lns for c in ln.cs]
            self.dys = [c.dy for ln in self.lns for c in ln.cs]
            self.flatdelta = False
            self._dxchange = False
            self._hasdx = any([dxv != 0 for dxv in self.dxs])
            self._dychange = False
            self._hasdy = any([dyv != 0 for dyv in self.dys])

            for ii in range(len(self.lns)):
                ln = self.lns[ii]
                ln.pt = self
                ln.parse_words()

            for ln in reversed(self.lns):
                if len(ln.cs) == 0:
                    self.lns.remove(ln)
                    # prune empty lines

            # For manual kerning removal, assign next and previous words. These can be in different lines
            ys = [ln.y[0] for ln in self.lns if ln.y is not None and len(ln.y) > 0]
            tol = 0.001
            for uy in dh.uniquetol(ys, tol):
                samey = [
                    self.lns[ii]
                    for ii in range(len(self.lns))
                    if abs(ys[ii] - uy) < tol
                ]
                sameyws = [w for ln in samey for w in ln.ws]
                xs = [w.x for ln in samey for w in ln.ws]
                sws = [
                    x for _, x in sorted(zip(xs, sameyws), key=lambda pair: pair[0])
                ]  # words sorted in ascending x
                for ii in range(1, len(sws)):
                    sws[ii - 1].nextw = sws[ii]
                    sws[ii].prevw = sws[ii - 1]
                    sws[ii].prevsametspan = (
                        sws[ii - 1].cs[-1].loc.pel == sws[ii].cs[0].loc.pel
                    )
    
    # Strip every sodipodi:role line from an element without changing positions
    def Strip_Sodipodirole_Line(self):
        if any([d.get('sodipodi:role')=='line' for d in self.tree.ds]):
            # Store old positions
            oxs = [c.pts_ut[0].x for ln in self.lns for c in ln.cs]
            oys = [c.pts_ut[0].y for ln in self.lns for c in ln.cs]
            odxs = [c.dx for ln in self.lns for c in ln.cs]
            odys = [c.dy for ln in self.lns for c in ln.cs]
            [d.set('sodipodi:role',None) for d in self.tree.ds]
            self.__init__(self.textel, self.ctable) # reparse
            
            # Correct the position of the first character
            cs = [c for ln in self.lns for c in ln.cs]
            for ii, ln in enumerate(self.lns):
                myi = cs.index(ln.cs[0])
                dx = oxs[myi]-cs[myi].pts_ut[0].x;
                dy = oys[myi]-cs[myi].pts_ut[0].y;
                if abs(dx)>0.001 or abs(dy)>0.001:
                    newxv = [v+dx for v in ln.x]
                    newyv = [v+dy for v in ln.y]
                    if ln.continuex or ln.continuey:
                        if ln.cs[0].loc.tt=='tail': # wrap in a trivial Tspan so we can set x and y
                            ln.cs[0].add_style({'baseline-shift':'0%'},setdefault=False)
                        ln.xsrc = ln.cs[0].loc.el
                        ln.ysrc = ln.cs[0].loc.el
                        ln.continuex = False
                        ln.continuey = False
                    ln.change_pos(newx=newxv, newy=newyv)
            
            # Fix non-first dxs
            ndxs = [c.dx for ln in self.lns for c in ln.cs]
            ndys = [c.dy for ln in self.lns for c in ln.cs]
            for ii,c in enumerate(cs):
                # if c.ln.cs.index(c)>0:
                if c.lnindex>0:
                    if abs(odxs[ii]-ndxs[ii])>0.001 or abs(odys[ii]-ndys[ii])>0.001:
                        c.dx = odxs[ii]
                        c.dy = odys[ii]
            self.Update_Delta();
            for ln in self.lns:
                for w in ln.ws:
                    w.charpos = None


    @staticmethod
    def GetXY(el, xy):
        val = su.fget(el,xy) # fine for 'x','y','dx','dy'
        if val is None:
            val = [None]  # None forces inheritance
        else:
            val = [None if x.lower() == "none" else dh.ipx(x) for x in val.split()]
        return val
    
    # Traverse the tree to find where deltas need to be located relative to the top-level text
    def Get_DeltaNum(self):
        allcs = [c for ln in self.lns for c in ln.cs]
        topcnt=0
        for di, tt, d, txt in self.tree.dgenerator():
            ttv = 'tail' if tt==0 else 'text'
            if (
                tt==0
                and d.get("sodipodi:role") == "line"
                and isinstance(d, Tspan)
                and isinstance(self.tree.pdict[d],TextElement)
            ):
                topcnt += 1  # top-level Tspans have an implicit CR at the beginning of the tail
            if txt is not None:
                for ii in range(len(txt)):
                    thec = [c for c in allcs if c.loc == cloc(d,ttv,ii)]
                    thec[0].deltanum = topcnt
                    topcnt += 1
                    
    def Get_Delta(self, lns, el, xy):
        for do in self.tree.ds:
            dxy = ParsedText.GetXY(do, xy)
            # Objects lower in the descendant list override ancestors
            if len(dxy) > 0 and dxy[0] is not None:
                allcs = [c for ln in self.lns for c in ln.cs]
                cnt = 0;
                for di, tt, d, txt in self.tree.dgenerator(subel=do):
                    ttv = 'tail' if tt==0 else 'text'
                    if (
                        tt==0
                        and d.get("sodipodi:role") == "line"
                        and isinstance(d, Tspan)
                        and isinstance(self.tree.pdict[d],TextElement)
                    ):
                        cnt  += 1  # top-level Tspans have an implicit CR at the beginning of the tail
                    if txt is not None:
                        for ii in range(len(txt)):
                            thec = [c for c in allcs if c.loc == cloc(d,ttv,ii)]
                            if cnt < len(dxy):
                                if xy == "dx":
                                    thec[0].dx = dxy[cnt]
                                if xy == "dy":
                                    thec[0].dy = dxy[cnt]
                            cnt += 1
                    if cnt >= len(dxy):
                        break

    # After dx/dy has changed, call this to write them to the text element
    # For simplicity, this is best done at the ParsedText level all at once
    def Update_Delta(self, forceupdate=False):
        if self._dxchange or self._dychange or forceupdate:
            dxs = [c.dx for ln in self.lns for c in ln.cs]
            dys = [c.dy for ln in self.lns for c in ln.cs]

            anynewx = self.dxs != dxs and any([dxv != 0 for dxv in self.dxs + dxs])
            anynewy = self.dys != dys and any([dyv != 0 for dyv in self.dys + dys])
            # only if new is not old and at least one is non-zero

            if anynewx or anynewy or forceupdate:
                self.Get_DeltaNum()
                dx = []
                dy = []
                for ln in self.lns:
                    for c in ln.cs:
                        if c.deltanum is not None:
                            dx = extendind(dx, c.deltanum, c.dx, 0)
                            dy = extendind(dy, c.deltanum, c.dy, 0)

                if not(self.flatdelta):  # flatten onto textel (only do once)
                    for d in self.tree.ds:
                        d.set("dx", None)
                        d.set("dy", None)
                    self.flatdelta = True

                dxset = None
                dyset = None
                if any([dxv != 0 for dxv in dx]):
                    dxset = " ".join([str(v) for v in dx])
                if any([dyv != 0 for dyv in dy]):
                    dyset = " ".join([str(v) for v in dy])
                self.textel.set("dx", dxset)
                self.textel.set("dy", dyset)
                for w in [w for ln in self.lns for w in ln.ws]:
                    # w.dxeff = None
                    w.charpos = None
            self.dxs = dxs
            self.dys = dys

            self._hasdx = any([dxv != 0 for dxv in dxs])
            self._dxchange = False
            self._hasdy = any([dyv != 0 for dyv in dys])
            self._dychange = False

    # Text is hard to edit unless xml:space is set to preserve and sodipodi:role is set to line
    # Should usually be called last
    def Make_Editable(self):
        el = self.textel
        el.set("xml:space", "preserve")
        # dh.debug(self.lns[0].tlvlno)
        # if len(self.lns)==1 and self.lns[0].tlvlno==0: # only child, no nesting, not a sub/superscript
        if (
            len(self.lns) == 1
            and self.lns[0].tlvlno is not None
            and not (self.lns[0].sprl)
        ):  # only one line that is a top-level tspan
            ln = self.lns[0]
            olddx = [c.dx for ln in self.lns for c in ln.cs]
            olddy = [c.dy for ln in self.lns for c in ln.cs]

            # ln.el.set('sodipodi:role','line')
            # self.lns = self.Parse_Lines(el); # unnecessary if called last
            # self.lns[0].change_pos(oldx,oldy);

            if len(ln.cs) > 0:
                cel = ln.cs[0].loc.el
                while cel != el and cel.getparent() != el:
                    cel = cel.getparent()
                tlvl = cel

                xyset(tlvl.getparent(),"x",ln.x)
                xyset(tlvl.getparent(),"y",ln.y)

                # tx = ln.el.get('x'); ty=ln.el.get('y');
                # # myp = ln.el.getparent();
                # if tx is not None: tlvl.set('x',tx)      # enabling sodipodi causes it to move to the parent's x and y
                # if ty is not None: tlvl.set('y',ty)      # enabling sodipodi causes it to move to the parent's x and y
                tlvl.set("sodipodi:role", "line")
                # reenable sodipodi so we can insert returns

                if self._hasdx or self._hasdy:
                    for ii in range(len(self.lns[0].cs)):
                        self.lns[0].cs[ii].dx = olddx[ii]
                        self.lns[0].cs[ii].dy = olddy[ii]
                    self.Update_Delta(forceupdate=True)
                    # may have deleted spr lines

    def Split_Off_Words(self, ws):
        # newtxt = dh.duplicate2(ws[0].ln.pt.textel);
        # nll = ParsedText(newtxt,self.ctable);
        nll = self.duplicate()
        newtxt = nll.textel

        il = self.lns.index(ws[0].ln)
        # words' line index
        wiis = [w.ln.ws.index(w) for w in ws]  # indexs of words in line

        # Record position and d
        dxl = [c.dx for w in ws for c in w.cs]
        dyl = [c.dy for w in ws for c in w.cs]

        for w in reversed(ws):
            w.delw()

        # If line was continuing, fuse the coordinates
        if nll.lns[il].continuex:
            nll.lns[il].continuex = False
            nll.lns[il].xsrc = nll.lns[il].cs[0].loc.pel
            nll.lns[il].change_pos(newx=nll.lns[il].x)
        if nll.lns[il].continuey:
            nll.lns[il].continuey = False
            nll.lns[il].ysrc = nll.lns[il].cs[0].loc.pel
            nll.lns[il].change_pos(newy=nll.lns[il].y)

        # Delete the other lines/words in the copy
        for il2 in reversed(range(len(nll.lns))):
            if il2 != il:
                nll.lns[il2].dell()
            else:
                nln = nll.lns[il2]
                for jj in reversed(range(len(nln.ws))):
                    if not (jj in wiis):
                        nln.ws[jj].delw()

        cnt = 0
        for l2 in nll.lns:
            for c in l2.cs:
                c.dx = dxl[cnt]
                c.dy = dyl[cnt]
                cnt += 1
        nll.Update_Delta()

        newtxt._parsed_text = nll
        return newtxt


    def Split_Off_Characters(self, cs):
        nll = self.duplicate()
        newtxt = nll.textel

        il = self.lns.index(cs[0].ln)
        # chars' line index
        # ciis = [c.ln.cs.index(c) for c in cs]  # indexs of charsin line
        ciis = [c.lnindex for c in cs]  # indexs of charsin line

        # Record position
        dxl = [c.dx for c in cs]
        dyl = [c.dy for c in cs]

        # dh.idebug(dxl)

        fusex = self.lns[il].continuex or ciis[0] > 0 or dxl[0] != 0
        fusey = self.lns[il].continuey or ciis[0] > 0 or dyl[0] != 0
        if fusex:
            xf = self.lns[il].anchfrac
            oldx = cs[0].pts_ut[0].x * (1 - xf) + cs[-1].pts_ut[3].x * xf
        if fusey:
            oldy = cs[0].w.y + dyl[0]

        for c in reversed(cs):
            c.delc()

        # Delete the other lines/chars in the copy
        for il2 in reversed(range(len(nll.lns))):
            if il2 != il:
                nll.lns[il2].dell()
            else:
                nln = nll.lns[il2]
                for jj in reversed(range(len(nln.cs))):
                    if jj not in ciis:
                        nln.cs[jj].delc()

        # Deletion of text can cause the srcs to be wrong. Reparse to find where it is now
        nln.xsrc, nln.ysrc = nll.Parse_Lines(srcsonly=True)
        nln.change_pos(newx=nln.x, newy=nln.y)
        nln.disablesodipodi(force=True)
        if len(self.lns)>0:
            self.lns[0].xsrc, self.lns[0].ysrc = self.Parse_Lines(srcsonly=True)
            self.lns[0].change_pos(newx=self.lns[0].x, newy=self.lns[0].y)
            # self.lns[0].disablesodipodi(force=True)

        # dh.idebug([''.join([c.c for c in cs]),dyl,fusey])
        if fusex:
            nln.continuex = False
            nln.change_pos(newx=[oldx])
            dxl[0] = 0
        if fusey:
            nln.continuey = False
            nln.change_pos(newy=[oldy])
            dyl[0] = 0

        cnt = 0
        for l2 in nll.lns:
            for c in l2.cs:
                c.dx = dxl[cnt]
                c.dy = dyl[cnt]
                cnt += 1
        nll.Update_Delta()

        newtxt._parsed_text = nll;
        return newtxt
    
    
    # Deletes empty elements from the doc. Generally this is done last
    def Delete_Empty(self):
        dxl = [c.dx for ln in self.lns for c in ln.cs]
        dyl = [c.dy for ln in self.lns for c in ln.cs]
        dltd = deleteempty(self.textel)
        if dltd:
            self.tree = None
        cnt = 0
        for ln in self.lns:
            for c in ln.cs:
                c.dx = dxl[cnt]
                c.dy = dyl[cnt]
                cnt += 1
        if self._hasdx or self._hasdy:
            self.Update_Delta(forceupdate=True)
            # force an update, could have deleted sodipodi lines

    # For debugging: make a rectange at all of the line's words' nominal extents
    HIGHLIGHT_STYLE = "fill:#007575;fill-opacity:0.4675"  # mimic selection
    def Make_Highlights(self,htype):
        if htype=='char':
            exts = self.get_char_extents();
        elif htype=='charink':
            exts = self.get_char_inkbbox();
        elif htype=='fullink':
            exts = [self.get_full_inkbbox()];
        elif htype=='word':
            exts = self.get_word_extents();
        elif htype=='line':
            exts = self.get_line_extents();
        else:  # 'all'
            exts = [self.get_full_extent()];
        for ext in exts:
            r = inkex.Rectangle()
            r.set('x',ext.x1)
            r.set('y',ext.y1)
            r.set('height',ext.h)
            r.set('width', ext.w)
            r.set("transform", self.textel.ccomposed_transform)
            r.set("style", ParsedText.HIGHLIGHT_STYLE)
            self.textel.croot.append(r)
    
    # Bounding box functions
    def get_char_inkbbox(self):
        # Get the untranformed bounding boxes of all characters' ink
        exts = []
        if self.lns is not None and len(self.lns) > 0:
            if self.lns[0].xsrc is not None:
                for ln in self.lns:
                    for w in ln.ws:
                        for c in w.cs:
                            p1 = c.pts_ut_ink[0]
                            p2 = c.pts_ut_ink[2]
                            exts.append(dh.bbox(((p1.x,p1.y),(p2.x,p2.y))))
        return exts
    
    def get_full_inkbbox(self):
        # Get the untranformed bounding box of the whole element
        ext = dh.bbox(None);
        if self.lns is not None and len(self.lns) > 0:
            if self.lns[0].xsrc is not None:
                for ln in self.lns:
                    for w in ln.ws:
                        for c in w.cs:
                            p1 = c.pts_ut_ink[0]
                            p2 = c.pts_ut_ink[2]
                            ext = ext.union(dh.bbox(((p1.x,p1.y),(p2.x,p2.y))))
        return ext
    
    # Extent functions
    def get_char_extents(self):
        # Get the untranformed extent of each character
        exts = []
        if self.lns is not None and len(self.lns) > 0:
            if self.lns[0].xsrc is not None:
                for ln in self.lns:
                    for w in ln.ws:
                        for c in w.cs:
                            p1 = c.pts_ut[0]
                            p2 = c.pts_ut[2]
                            exts.append(dh.bbox(((p1.x,p1.y),(p2.x,p2.y))))
        return exts
    def get_word_extents(self):
        # Get the untranformed extent of each word
        exts = []
        if self.lns is not None and len(self.lns) > 0:
            if self.lns[0].xsrc is not None:
                for ln in self.lns:
                    for w in ln.ws:
                        p1 = w.pts_ut[0]
                        p2 = w.pts_ut[2]
                        exts.append(dh.bbox(((p1.x,p1.y),(p2.x,p2.y))))
        return exts
    def get_line_extents(self):
        # Get the untranformed extent of each line
        exts = []
        if self.lns is not None and len(self.lns) > 0:
            if self.lns[0].xsrc is not None:
                for ln in self.lns:
                    extln = dh.bbox(None)
                    for w in ln.ws:
                        p1 = w.pts_ut[0]
                        p2 = w.pts_ut[2]
                        extln = extln.union(dh.bbox(((p1.x,p1.y),(p2.x,p2.y))))
                    if not(extln.isnull):
                        exts.append(extln)
        return exts
    def get_full_extent(self):
        # Get the untranformed extent of the whole element
        ext = dh.bbox(None);
        if self.lns is not None and len(self.lns) > 0:
            if self.lns[0].xsrc is not None:
                for ln in self.lns:
                    for w in ln.ws:
                        for c in w.cs:
                            p1 = c.pts_ut[0]
                            p2 = c.pts_ut[2]
                            ext = ext.union(dh.bbox(((p1.x,p1.y),(p2.x,p2.y))))
        return ext
                    
    @property
    def tree(self):
        if not(hasattr(self,'_tree')):
            self._tree = txttree(self.textel)
        return self._tree
    @tree.setter
    def tree(self, val):
        if val is None and hasattr(self,'_tree'):
            delattr(self,'_tree')
    
    
# Descendant tree class
class txttree():
    def __init__(self,el):
        ds, pts = dh.descendants2(el, True)
        self.ds = ds;
        self.ptails = pts;
        # self.cdict = cd;
        # self.pdict = pd;
        self.pdict = {d:d.getparent() for d in ds}        
    # A generator for crawling through a specific text descendant tree
    # Returns the current descendant index, tt (0 for tail, 1 for text),
    # descendant element, and text. When starting at subel, only gets the
    # tree subset corresponding to that element
    def dgenerator(self, subel=None):
        if subel is None:
            starti = 0
            stopi  = len(self.ds)
            subel = self.ds[0]
        else:
            starti = self.ds.index(subel)
            stopi = [ii for ii,pt in enumerate(self.ptails) if subel in pt][0]
            
        for di, tt in ttgenerator(len(self.ds),starti,stopi):
            ds = self.ptails[di] if tt == 0 else [self.ds[di]]
            for d in ds:
                if tt==0 and d==subel: # finish at my own tail (do not yield it)
                    return
                txt = d.tail if tt==0 else d.text
                yield di, tt, d, txt


# A generator for crawling through a general text descendant tree
# Returns the current descendant index and tt (0 for tail, 1 for text)
def ttgenerator(Nd,starti=0,stopi=None):
    di = starti
    if stopi is None: stopi = Nd
    tt = 0
    while True:
        if tt == 1:
            di += 1
            tt = 0
        else:
            tt = 1
        if di == stopi and tt == 1:
            return
        else:
            yield di, tt


# For lines, words, and chars
def get_anchorfrac(anch):
    anch_frac = {"start": 0, "middle": 0.5, "end": 1}
    return anch_frac[anch]


# A single line, which represents a list of characters. Typically a top-level Tspan or TextElement.
# This is further subdivided into a list of words
class tline:
    __slots__ = ('_x', '_y', 'sprl', 'sprlabove', 'anchor', 'anchfrac', 
                 'cs', 'ws', 'transform', 'angle', 'xsrc', 'ysrc', 'tlvlno', 
                 'style', 'continuex', 'continuey', 'pt',
                 'splits','sws')
    def __init__(
        self,
        pt,
        x,
        y,
        xsrc,
        ysrc,
        sprl,
        sprlabove,
        anch,
        xform,
        ang,
        tlvlno,
        sty,
        continuex,
        continuey,
    ):
        self._x = x
        self._y = y
        self.sprl = sprl
        # is this line truly a sodipodi:role line
        self.sprlabove = sprlabove
        # nominal value of spr (sprl may actually be disabled)
        self.anchor = anch
        self.anchfrac = get_anchorfrac(anch)
        self.cs = []
        self.ws = []
        if xform is None:
            self.transform = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        else:
            self.transform = xform
        if ang is None:
            self.angle = 0
        else:
            self.angle = ang
        self.xsrc = xsrc
        # element from which we derive our x value
        self.ysrc = ysrc
        # element from which we derive our x value
        self.tlvlno = tlvlno
        # which number Tspan I am if I'm top-level (otherwise None)
        self.style = sty
        # self.el = el;
        self.continuex = continuex
        # when enabled, x of a line is the endpoint of the previous line
        self.continuey = continuey
        # when enabled, y of a line is the endpoint of the previous line
        self.pt = pt
        
    def copy(self,memo):
        ret = tline.__new__(tline)
        memo[self]=ret
        
        ret._x = self._x[:]
        ret._y = self._y[:]
        ret.sprl = self.sprl
        ret.sprlabove = [memo[sa] for sa in self.sprlabove]
        ret.anchor = self.anchor
        ret.anchfrac = self.anchfrac
        ret.cs = [c.copy(memo) for c in self.cs]
        ret.ws = [w.copy(memo) for w in self.ws]
        ret.transform = self.transform
        ret.angle = self.angle
        ret.xsrc = memo[self.xsrc]   
        ret.ysrc = memo[self.ysrc]    
        ret.tlvlno = self.tlvlno
        ret.style = self.style
        ret.continuex = self.continuex
        ret.continuey = self.continuey
        ret.pt = self.pt
        return ret

    # x property
    def get_x(self):
        if not self.continuex:
            return self._x
        if self.pt is None:
            return [0]
        ii = self.pt.lns.index(self)
        if ii > 0 and len(self.pt.lns[ii - 1].ws) > 0:
            xf = self.anchfrac
            xanch = (1 + xf) * self.pt.lns[ii - 1].ws[-1].pts_ut[3].x - xf * self.pt.lns[ii - 1].ws[-1].pts_ut[0].x
            return [xanch]
        else:
            return [0]


    def set_x(self, xi):
        self._x = xi

    x = property(get_x, set_x)

    # y property
    def get_y(self):
        if not self.continuey:
            return self._y
        if self.pt is None:
            return [0]
        ii = self.pt.lns.index(self)
        if ii > 0 and len(self.pt.lns[ii - 1].ws) > 0:
            xf = self.anchfrac
            yanch = (1 + xf) * self.pt.lns[ii - 1].ws[-1].pts_ut[3].y - xf * self.pt.lns[ii - 1].ws[-1].pts_ut[0].y
            return [yanch]
        else:
            return [0]


    def set_y(self, yi):
        self._y = yi

    y = property(get_y, set_y)
    # anchorfrac = property(lambda self: get_anchorfrac(self.anchor))

    def insertc(self, c, ec):  # insert below ec
        for c2 in self.cs[ec:]:
            c2.lnindex += 1
        c.lnindex = ec
        self.cs = self.cs[0:ec] + [c] + self.cs[ec:]
        c.ln = self
        
    def addw(self, w):  # Add a complete word
        self.ws.append(w)

    def parse_words(self):
        # Parsing a line into words is the final step that should be called once
        # the line parser has gotten all the characters
        w = None
        self.ws = []
        for ii in range(len(self.cs)):
            if ii == 0:
                w = tword(ii, self.x[0], self.y[0], self)
                # open new word
            elif ii < len(self.x) and not (
                self.x[ii] is None
            ):  # None means keep the same word
                self.addw(w)  # close previous word
                w = tword(ii, self.x[ii], self.y[0], self)
                # open new word
            else:
                w.addc(ii)
                # add to existing word
        if w is not None:
            self.addw(w)

    def dell(self):  # deletes the whole line
        self.change_pos(self.x[:1])
        for ii, c in enumerate(reversed(self.cs)):
            if c.loc.tt == "text":
                c.loc.el.text = c.loc.el.text[:c.loc.ind] + c.loc.el.text[c.loc.ind + 1:]
            else:
                c.loc.el.tail = c.loc.el.tail[:c.loc.ind] + c.loc.el.tail[c.loc.ind + 1:]
        self.pt.Update_Delta()
        
        if self in self.pt.lns:
            self.pt.lns.remove(self)

    def txt(self):
        return "".join([c.c for c in self.cs])

    # Change the alignment of a line without affecting character position
    def change_alignment(self, newanch):
        if newanch != self.anchor:
            sibsrc = [
                ln for ln in self.pt.lns if ln.xsrc == self.xsrc or ln.ysrc == self.ysrc
            ]
            for ln in reversed(sibsrc):
                ln.disablesodipodi()  # Disable sprl for all lines sharing our src, including us
                # Note that it's impossible to change one line without affecting the others

            for w in self.ws:
                minx = min([w.pts_ut[ii].x for ii in range(4)])
                maxx = max([w.pts_ut[ii].x for ii in range(4)])

                if w.unrenderedspace and self.cs[-1] in w.cs:
                    maxx -= w.cs[-1].cw

                xf = get_anchorfrac(newanch)
                newx = (1 - xf) * minx + xf * maxx

                if len(w.cs) > 0:
                    newxv = self.x
                    # newxv[self.cs.index(w.cs[0])] = newx
                    newxv[w.cs[0].lnindex] = newx

                    # dh.idebug([w.txt(),newx,newxv])
                    self.change_pos(newxv)
                    # dh.Set_Style_Comp(w.cs[0].loc.el, "text-anchor", newanch)
                    w.cs[0].loc.el.cstyle["text-anchor"]=newanch
                    alignd = {"start": "start", "middle": "center", "end": "end"}
                    # dh.Set_Style_Comp(w.cs[0].loc.el, "text-align", alignd[newanch])
                    w.cs[0].loc.el.cstyle["text-align"]=alignd[newanch]

                self.anchor = newanch
                self.anchfrac = xf
                for w in self.ws:
                    w.pts_ut = None  # invalidate word positions

    @staticmethod
    def writevA(v):
        return None if not(v) else str(v)[1:-1].replace(',','')
    


    # Disable sodipodi:role = line
    def disablesodipodi(self, force=False):
        if len(self.sprlabove)>0 or force:
            if len(self.cs) > 0:
                newsrc = self.cs[0].loc.el  # disabling snaps src to first char
                if self.cs[0].loc.tt == "tail":
                    newsrc = self.cs[0].loc.el.getparent()
                newsrc.set("sodipodi:role", None)
                
                self.sprlabove = []
                self.xsrc = newsrc
                self.ysrc = newsrc
                xyset(self.xsrc,"x",self.x)  # fuse position to new source
                xyset(self.ysrc,"y",self.y)
                self.sprl = False

    # Update the line's position in the document, accounting for inheritance
    # Never change x/y directly, always call this function
    def change_pos(self, newx=None, newy=None, reparse=False):
        if newx is not None:
            sibsrc = [ln for ln in self.pt.lns if ln.xsrc == self.xsrc]
            if len(sibsrc) > 1:
                for ln in reversed(sibsrc):
                    ln.disablesodipodi()  # Disable sprl when lines share an xsrc

            # if all([v is None for v in newx[1:]]) and len(newx) > 0:
            #     newx = [newx[0]]
            while len(newx) > 1 and newx[-1] is None:
                newx.pop()
            oldx = self._x if not self.continuex else self.x
            self._x = newx
            xyset(self.xsrc,"x", newx)
            # dh.idebug([self.txt(),self.xsrc.get('x')])

            if len(oldx) > 1 and len(newx) == 1 and len(self.sprlabove)>0:  # would re-enable sprl
                self.disablesodipodi()


        if newy is not None:
            sibsrc = [ln for ln in self.pt.lns if ln.ysrc == self.ysrc]
            if len(sibsrc) > 1:
                for ln in reversed(sibsrc):
                    ln.disablesodipodi()  # Disable sprl when lines share a ysrc

            # if all([v is None for v in newy[1:]]) and len(newy) > 0:
            #     newy = [newy[0]]
            while len(newy) > 1 and newy[-1] is None:
                newx.pop()
            oldy = self._y if not self.continuey else self.y
            self._y = newy
            xyset(self.ysrc,"y", newy)

            if len(oldy) > 1 and len(newy) == 1 and len(self.sprlabove)>0:  # would re-enable sprl
                self.disablesodipodi()
        if reparse:
            self.parse_words()
            # usually don't want to do this since it generates new words


# A word (a group of characters with the same assigned anchor)
class tword:
    __slots__ = ('cs', 'windex', 'iis', 'Ncs', '_x', '_y', 'sf', 'ln', 'transform',
                 'nextw', 'prevw', 'prevsametspan', '_pts_ut', '_pts_t', '_bb',
                 '_dxeff', '_charpos', '_cpts_ut', '_cpts_t', 'parsed_bb', 'txt',
                 'lsp', 'dxeff', 'cw', 'dy', 'ch', 'bshft',
                 'mw','merges','mergetypes','merged','wtypes','bb_big')
    def __init__(self, ii, x, y, ln):
        c = ln.cs[ii]
        self.cs = [c]
        c.windex = 0
        self.iis = [ii]
        # character index in word
        self.Ncs = len(self.iis)
        self._x = x
        self._y = y
        self.sf = c.sf
        # all letters have the same scale
        self.ln = ln
        self.transform = ln.transform
        c.w = self
        self.nextw = self.prevw = self.prevsametspan = None
        self._pts_ut = self._pts_t = self._bb = None
        self._dxeff = self._charpos = None
        self._cpts_ut = None
        self._cpts_t = None
        self.parsed_bb = None
        
        # Character attribute lists
        self.txt = c.c
        self.lsp = [c.lsp]
        self.dxeff = [c.dx, c.lsp]
        # letter-spacing applies to next character
        # dxeff[ii] = cs[ii].dx + w.cs[ii-1].lsp (0 at edges)
        self.cw = [c.cw]
        self.dy = [c.dy]
        self.ch = [c.ch]
        self.bshft = [c.bshft]
    
        
    def copy(self,memo):
        ret = tword.__new__(tword)
        memo[self] = ret
        
        ret.Ncs = self.Ncs
        ret._x = self._x
        ret._y = self._y
        ret.sf = self.sf
        ret.transform = self.transform
        ret.nextw = self.nextw
        ret.prevw = self.prevw
        ret.prevsametspan = self.prevsametspan
        ret._pts_ut = self._pts_ut
        ret._pts_t = self._pts_t
        ret._bb = self._bb
        ret._dxeff = self._dxeff
        ret._charpos = self._charpos
        ret._cpts_ut = self._cpts_ut
        ret._cpts_t = self._cpts_t
        ret.parsed_bb = self.parsed_bb
        ret.txt = self.txt
        ret.lsp = self.lsp[:]
        ret.dxeff = self.dxeff[:]
        ret.cw = self.cw[:]
        ret.dy = self.dy[:]
        ret.ch = self.ch[:]
        ret.bshft = self.bshft[:]
        
        ret.cs = list(map(memo.get, self.cs, self.cs)) # faster than [memo.get(c) for c in self.cs]
        for ret_c in ret.cs:
            ret_c.w = ret
        ret.iis = self.iis[:]
        ret.ln = memo[self.ln]
        return ret
    
    def addc(self, ii):  # adds an existing char to a word based on line index
        c = self.ln.cs[ii]
        c.w = None # avoid problems in character properties
        self.cs.append(c)
        self.cchange()
        self.iis.append(ii)
        self.Ncs = len(self.iis)
        c.windex = self.Ncs - 1 
        
        self.txt += c.c
        self.lsp.append(c.lsp)
        self.dxeff[-1] += c.dx
        self.dxeff.append(c.lsp)
        self.cw.append(c.cw)
        self.dy.append(c.dy)
        self.ch.append(c.ch)
        self.bshft.append(c.bshft)
        c.w = self

    def removec(self, c):  # removes a char from a word based on word index
        ii = c.windex
        for c2 in self.cs[ii+1:]:
            c2.windex -= 1
        c.windex = None
        c.w = None
        self.cs= del2(self.cs, ii)
        self.iis.pop(ii)
        self.Ncs = len(self.iis)
        self.cchange()
        
        self.txt = del2(self.txt, ii)
        self.lsp.pop(ii)
        self.dxeff.pop(ii)
        self.dxeff[ii] = (self.cs[ii].dx if ii<self.Ncs else 0) + (self.cs[ii-1].lsp if ii>0 else 0)
        self.cw.pop(ii)
        self.dy.pop(ii)
        self.ch.pop(ii)
        self.bshft.pop(ii)
        
        if len(self.cs) == 0:  # word now empty
            self.delw()

    # Callback for character addition/deletion. Used to invalidate cached properties
    def cchange(self):
        self.charpos = None

        if self.ln.pt._hasdx:
            self.ln.pt._dxchange = True
        if self.ln.pt._hasdy:
            self.ln.pt._dychange = True

    @property
    def x(self):
        if self.ln and self.Ncs > 0:
            lnx = self.ln._x if not self.ln.continuex else self.ln.x
            # checking for continuex early eliminates most unnecessary calls
            fi = self.iis[0]
            return lnx[fi] if fi < len(lnx) else lnx[-1]
        else:
            return 0


    @property
    def y(self):
        if self.ln and self.Ncs > 0:
            lny = self.ln._y if not self.ln.continuey else self.ln.y
            # checking for continuex early eliminates most unnecessary calls
            fi = self.iis[0]
            return lny[fi] if fi < len(lny) else lny[-1]
        else:
            return 0

    # Deletes me from everywhere
    def delw(self):
        for c in reversed(self.cs):
            c.delc()
        if self in self.ln.ws:
            self.ln.ws.remove(self)


    # Generate a new character and add it to the end of the word
    def appendc(self, ncv, ncprop, ndx, ndy, totail=None):
        # Add to document
        lc = self.cs[-1]
        # last character
        if totail is None:
            myi = lc.loc.ind + 1
            # insert after last character
            if lc.loc.tt == "text":
                lc.loc.el.text = lc.loc.el.text[0:myi] + ncv + lc.loc.el.text[myi:]
            else:
                lc.loc.el.tail = lc.loc.el.tail[0:myi] + ncv + lc.loc.el.tail[myi:]
        else:
            if totail.tail is None:
                totail.tail = ncv
            else:
                totail.tail = ncv + totail.tail

        # Make new character as a copy of the last one of the current word
        c = copy(lc)
        c.c = ncv
        c.prop = ncprop
        c.cw = ncprop.charw*c.utfs
        c.dx = ndx
        c.dy = ndy

        if totail is None:
            c.loc = cloc(c.loc.el, c.loc.tt, c.loc.ind + 1)  # updated location
        else:
            c.loc = cloc(totail, "tail", 0)
        c.sty = c.loc.pel.cspecified_style

        # Add to line
        # myi = self.ln.cs.index(lc) + 1  # insert after last character
        myi = lc.lnindex + 1  # insert after last character
        if len(self.ln.x) > 0:
            newx = self.ln.x[0:myi] + [None] + self.ln.x[myi:]
            newx = newx[0 : len(self.ln.cs) + 1]
            self.ln.change_pos(newx)

        self.ln.insertc(c, myi)
        for ii in range(
            myi + 1, len(self.ln.cs)
        ):  # need to increment index of subsequent objects with the same parent
            ca = self.ln.cs[ii]
            if ca.loc.tt == c.loc.tt and ca.loc.el == c.loc.el:
                ca.loc.ind += 1
            if ca.w is not None:
                # i2 = ca.w.cs.index(ca)
                # ca.w.iis[i2] += 1
                ca.w.iis[ca.windex] += 1
        # Add to word, recalculate properties
        self.addc(myi)

        # Adding a character causes the word to move if it's center- or right-justified
        # Need to fix this by adjusting position
        deltax = -self.ln.anchfrac * self.ln.cs[myi].cw
        if deltax != 0:
            newx = self.ln.x
            # newx[self.ln.cs.index(self.cs[0])] -= deltax
            newx[self.cs[0].lnindex] -= deltax
            self.ln.change_pos(newx)
        self.ln.pt.Update_Delta()

    # Add a new word (possibly from another line) into the current one
    # Equivalent to typing it in
    def appendw(self, nw, type, maxspaces=None):
        if len(nw.cs) > 0:
            # Calculate the number of spaces we need to keep the position constant
            # (still need to adjust for anchors)
            tr1, br1, tl2, bl2 = self.get_ut_pts(nw)
            lc = self.cs[-1]
            # last character
            numsp = (bl2.x - br1.x) / (lc.sw)
            numsp = max(0, round(numsp))
            if maxspaces is not None:
                numsp = min(numsp, maxspaces)

            # dh.idebug([self.txt(),nw.txt(),(bl2.x-br1.x)/(lc.sw/self.sf)])
            # dh.idebug([self.txt(),nw.txt(),lc.sw,lc.cw])
            for ii in range(numsp):
                self.appendc(" ", lc.ln.pt.ctable.get_prop(' ',lc.nsty), -lc.lsp, 0)
                # self.appendc(" ", lc.ln.pt.ctable.get_prop(' ',lc.nsty)*lc.tfs, -lc.lsp, 0)

            fc = nw.cs[0]
            prevc = self.cs[-1]
            for c in nw.cs:
                mydx = (c != fc) * c.dx - prevc.lsp * (c == fc)
                # use dx to remove lsp from the previous c
                # dh.idebug(ParsedText(self.ln.pt.textel,self.ln.pt.ctable).txt())
                c.delc()

                ntype = copy(type)
                otype = c.sty.get("baseline-shift")
                if otype in ["super", "sub"] and type == "normal":
                    ntype = otype

                # Nested tspans should be appended to the end of tails
                totail = None
                if self.cs[-1].loc.pel != self.cs[0].loc.pel:
                    cel = self.cs[-1].loc.pel
                    while (
                        cel is not None and cel.getparent() != self.cs[0].loc.pel
                        and cel.getparent() != self.ln.pt.textel
                    ):
                        cel = cel.getparent()
                    totail = cel

                self.appendc(c.c, c.prop, mydx, c.dy, totail=totail)
                newc = self.cs[-1]

                newc.parsed_pts_ut = [
                    (self.transform).applyI_to_point(p) for p in c.parsed_pts_t
                ]
                newc.parsed_pts_t = c.parsed_pts_t

                # Update the style
                newsty = None
                if c.sty != newc.sty or ntype in ["super", "sub"] or c.sf != newc.sf:
                    newsty = c.sty
                    if ntype in ["super", "sub"]:
                        # newsty = c.sty
                        # Nativize super/subscripts
                        newsty["baseline-shift"] = "super" if ntype == "super" else "sub"
                        newsty["font-size"] = "65%"
                        # Leave size unchanged
                        # sz = round((c.sw*c.sf)/(newc.sw*newc.sf)*100)
                        # newsty['font-size'] = str(sz)+'%';
    
                        # Leave baseline unchanged (works, but do I want it?)
                        # shft = round(-(bl2.y-br1.y)/self.tfs*100*self.sf);
                        # newsty['baseline-shift']= str(shft)+'%';
                    elif c.sf != newc.sf:
                        # Prevent accidental font size changes when differently transformed
                        sz = round((c.sw*c.sf)/(newc.sw*newc.sf)*100)
                        newsty['font-size'] = str(sz)+'%';

                if newsty is not None:
                    newc.add_style(newsty)
                prevc = newc

            # Following the merge, append the new word's data to the orig pts lists
            self.parsed_bb = self.parsed_bb.union(nw.parsed_bb)

    # Get the coordinates of another word in my coordinate system
    def get_ut_pts(self, w2, current_pts=False):
        if current_pts:
            c1uts = [c.pts_ut for c in self.cs]
            c2uts = [c.pts_ut for c in w2.cs]
            c2ts = [c.pts_t for c in w2.cs]
        else:
            c1uts = [c.parsed_pts_ut for c in self.cs]
            c2uts = [c.parsed_pts_ut for c in w2.cs]
            c2ts = [c.parsed_pts_t for c in w2.cs]

        mv = float("inf")
        ci = None
        for ii in range(len(w2.cs)):
            if c2uts[ii] is not None:
                if c2uts[ii][0].x < mv:
                    mv = c2uts[ii][0].x
                    ci = ii

        bl2 = (self.transform).applyI_to_point(c2ts[ci][0])
        tl2 = (self.transform).applyI_to_point(c2ts[ci][1])

        mv = float("-inf")
        ci = None
        for ii in range(len(self.cs)):
            if c1uts[ii] is not None:
                if c1uts[ii][3].x > mv:
                    mv = c1uts[ii][3].x
                    ci = ii

        tr1 = c1uts[ci][2]
        br1 = c1uts[ci][3]
        return tr1, br1, tl2, bl2

    # Adjusts the position of merged text to account for small changes in word position that occur
    # This depends on alignment, so it is generally done after the final justification is set
    def fix_merged_position(self):
        gcs = [c for c in self.cs if c.c != " "]
        if len(gcs) > 0:
            omaxx = max([c.parsed_pts_ut[3].x for c in gcs])
            ominx = min([c.parsed_pts_ut[0].x for c in gcs])
            newptsut = [c.pts_ut for c in gcs]
            nmaxx = max([p[3].x for p in newptsut])
            nminx = min([p[0].x for p in newptsut])

            xf = self.ln.anchfrac
            deltaanch = (nminx * (1 - xf) + nmaxx * xf) - (
                ominx * (1 - xf) + omaxx * xf
            )
            # how much the final anchor moved
            # dh.debug(deltaanch)
            if deltaanch != 0:
                newx = self.ln.x
                # newx[self.ln.cs.index(self.cs[0])] -= deltaanch
                newx[self.cs[0].lnindex] -= deltaanch
                self.ln.change_pos(newx)
            self.ln.pt.Update_Delta()

    # @property
    # def lsp(self):
    #     # Word letter-spacing
    #     if self._lsp is None:
    #         self._lsp = [c.lsp for c in self.cs]
    #     return self._lsp

    # @lsp.setter
    # def lsp(self, li):
    #     # Word letter-spacing
    #     if li is None:
    #         self._lsp = None
    #         self.dxeff = None

    # Effective dx (with letter-spacing). Note that letter-spacing adds space
    # after the char, so dxl ends up being longer than the number of chars by 1
    # @property
    # @property
    # def dxeff(self):
    #     if self._dxeff is None:
    #         dxlsp = [0] + self.lsp
    #         # letter-spacing applies to next character
    #         self._dxeff = [c.dx + d for c, d in zip(self.cs, dxlsp)] + [dxlsp[-1]]
            
    #         if not self._dxeff == self.dxeff2:
    #             dh.idebug('1: '+str(self._dxeff))
    #             dh.idebug('2: '+str(self.dxeff2))
    #             dh.idebug('1: '+str(len(self._dxeff)))
    #             dh.idebug('2: '+str(len(self.dxeff2)))
    #     return self._dxeff

    # @dxeff.setter
    # def dxeff(self, di):
    #     if di is None:
    #         self._dxeff = None
    #         self.charpos = None

    # Word properties
    def get_fs(self):
        return maxnone([c.tfs for c in self.cs])

    tfs = property(get_fs)

    def get_sw(self):
        return maxnone([c.sw for c in self.cs])

    sw = property(get_sw)

    def get_mch(self):
        return maxnone(self.ch)

    mch = property(get_mch)

    def get_ang(self):
        return self.ln.angle

    angle = property(get_ang)
    # anchorfrac = property(lambda self: get_anchorfrac(self.ln.anchor))

    @property
    def unrenderedspace(
        self,
    ):  # If last char of a multichar line is a space, is not rendered
        return (
            self.Ncs > 1
            and self.cs[-1] == self.ln.cs[-1]
            and self.cs[-1].c in [" ", "\u00A0"]
        )

    @property
    def charpos(self):
        # Where characters in a word are relative to the left side of the word, in x units
        if self._charpos is None:
            wadj = [0]*self.Ncs
            if KERN_TABLE:
                for ii in range(1, self.Ncs):
                    wadj[ii] = self.cs[ii].dkerns(self.cs[ii - 1].c, self.cs[ii].c)
                    # default to 0 for chars of different style
                    
            ws = [self.cw[ii] + self.dxeff[ii] + wadj[ii] for ii in range(self.Ncs)]
            cstop = list(itertools.accumulate(ws))
            # cumulative width up to and including the iith char
            cstrt = [cstop[ii] - self.cw[ii] for ii in range(self.Ncs)]
            
            cstrt = np.array(cstrt,dtype=float)
            cstop = np.array(cstop,dtype=float)

            ww = cstop[-1]
            offx = -self.ln.anchfrac * (ww - self.unrenderedspace * self.cs[-1].cw)
            # offset of the left side of the word from the anchor
            wx = self.x
            wy = self.y
            
            lx = (wx + cstrt + offx)[:, np.newaxis]
            rx = (wx + cstop + offx)[:, np.newaxis]
            
            # dyl, chs, bss = zip(*[(c.dy, c.ch, c.bshft) for c in self.cs])
            adyl = list(itertools.accumulate(self.dy))
            by = np.array([wy + dy - bs for dy, bs in 
                           zip(adyl, self.bshft)],dtype=float)[:, np.newaxis]
            ty = np.array([wy + dy - bs - ch for dy, ch, bs 
                           in zip(adyl, self.ch, self.bshft)],dtype=float)[:, np.newaxis]

            self._charpos = (cstrt, cstop, lx, rx, by, ty)

        return self._charpos

    @charpos.setter
    def charpos(self, ci):
        if ci is None:  # invalidate self and dependees
            self._charpos = None
            self.pts_ut = None
            self.cpts_ut = None
            self.cpts_t = None

    # Untransformed bounding box of word
    @property
    def pts_ut(self):
        if self._pts_ut is None:
            (cstrt, cstop, lx, rx, by, ty) = self.charpos
            ww = cstop[-1]
            offx = -self.ln.anchfrac * (
                ww - self.unrenderedspace * self.cs[-1].cw
            )  # offset of the left side of the word from the anchor

            wx = self.x
            wy = self.y
            if len(self.cs) > 0:
                ymin = min([wy + c.dy - c.ch  for c in self.cs])
                ymax = max([wy + c.dy for c in self.cs])
            else:
                ymin = ymax = wy
            self._pts_ut = [
                v2d(wx + offx, ymax),
                v2d(wx + offx, ymin),
                v2d(wx + (ww + offx), ymin),
                v2d(wx + (ww + offx), ymax),
            ]
        return self._pts_ut

    @pts_ut.setter
    def pts_ut(self, pi):
        if pi is None and self._pts_ut is not None:  # invalidate self and dependees
            self._pts_ut = None
            self.pts_t = None
            # self.cpts_ut = None

    @property
    def pts_t(self):
        if self._pts_t is None:
            self._pts_t = [
                self.transform.apply_to_point(p, simple=True) for p in self.pts_ut
            ]
        return self._pts_t

    @pts_t.setter
    def pts_t(self, pi):
        if pi is None and self._pts_t is not None:  # invalidate self and dependees
            self._pts_t = None
            self.bb = None
            # self.cpts_t = None

    @property
    def bb(self):
        if self._bb is None:
            ptt = self.pts_t
            
            min_x, min_y = float('inf'), float('inf')
            max_x, max_y = float('-inf'), float('-inf')
            for p in ptt:
                min_x, min_y = min(min_x, p.x), min(min_y, p.y)
                max_x, max_y = max(max_x, p.x), max(max_y, p.y)
            self._bb = bbox([min_x, min_y, max_x - min_x, max_y - min_y])
            
            # self._bb = bbox(
            #     [
            #         min([p.x for p in ptt]),
            #         min([p.y for p in ptt]),
            #         max([p.x for p in ptt]) - min([p.x for p in ptt]),
            #         max([p.y for p in ptt]) - min([p.y for p in ptt]),
            #     ]
            # )
        return self._bb

    @bb.setter
    def bb(self, bbi):
        if bbi is None:  # invalidate
            self._bb = None

    @property
    def cpts_ut(self):
        if self._cpts_ut is None:
            """  Get the characters' pts"""
            (cstrt, cstop, lx, rx, by, ty) = self.charpos

            # self._cpts_ut = [
            #     np.hstack((lx, by)),
            #     np.hstack((lx, ty)),
            #     np.hstack((rx, ty)),
            #     np.hstack((rx, by)),
            # ]
            n_rows = lx.shape[0]
            self._cpts_ut = [
                tuple((coord[i][0], v[i][0]) for i in range(n_rows)) for coord, v in zip((lx, lx, rx, rx), (by, ty, ty, by))
            ]

        return self._cpts_ut
    @cpts_ut.setter
    def cpts_ut(self, ci):
        if ci is None:
            self._cpts_ut = None

    @property
    def cpts_t(self):
        if self._cpts_t is None:
            """  Get the characters' pts"""
            (cstrt, cstop, lx, rx, by, ty) = self.charpos
            Nc = len(lx)
            # ps = np.hstack(
            #     (
            #         np.vstack((lx, lx, rx, rx)),
            #         np.vstack((by, ty, ty, by)),
            #         np.ones([4 * Nc, 1],dtype=float),
            #     )
            # )
            ps = np.array([
                (coord[i][0], v[i][0], 1)
                for coord, v in zip((lx, lx, rx, rx), (by, ty, ty, by))
                for i in range(Nc)
            ],dtype=float)
            
            # M = np.vstack((np.array(self.transform.matrix,dtype=float), np.array([[0, 0, 1]],dtype=float)))
            M = np.array(self.transform.matrix + ((0, 0, 1),),dtype=float) 
            
            tps = np.dot(M, ps.T).T
            self._cpts_t = [
                tps[0:Nc, 0:2],
                tps[Nc : 2 * Nc, 0:2],
                tps[2 * Nc : 3 * Nc, 0:2],
                tps[3 * Nc : 4 * Nc, 0:2],
            ]

        return self._cpts_t
    @cpts_t.setter
    def cpts_t(self, ci):
        if ci is None:
            self._cpts_t = None

# Some properties that need to be calculated from the style
def style_derived(styv,pel,textel):
    if "letter-spacing" in styv:
        lspv = styv.get("letter-spacing")
        if "em" in lspv:  # em is basically the font size
            fs2 = styv.get("font-size")
            if fs2 is None:
                fs2 = "12px"
            lspv = float(lspv.strip("em")) * dh.ipx(fs2)
        else:
            lspv = dh.ipx(lspv) or 0
    else:
        lspv = 0
        
    if "baseline-shift" in styv:
        cel = pel
        bshft = 0
        while cel != textel:  # sum all ancestor baseline-shifts
            if "baseline-shift" in cel.cstyle:
                bshft += tchar.get_baseline(cel.cstyle, cel.getparent())
            cel = cel.getparent()
    else:
        bshft = 0
    return ()

# A single character and its style
class tchar:
    __slots__ = ('c', 'tfs', 'utfs', 'sf', 'prop', 'cw', '_sty', 'nsty', 'loc', 'ch', 'sw', 'ln', 'lnindex', 'w', 'windex', 'type', '_dx', '_dy', 'deltanum', 'dkerns', 'parsed_pts_t', 'parsed_pts_ut', '_lsp', '_bshft')
    def __init__(self, c, tfs, sf, prop, sty, nsty, loc,ln):
        self.c = c
        self.tfs = tfs
        # transformed font size (uu)
        utfs = tfs/sf
        self.utfs = utfs
        # untransformed font size
        self.sf = sf
        # transform scale
        self.prop = prop
        # properties of a 1 uu character
        self.cw = prop.charw * utfs
        # ut character width 
        self._sty = sty
        # actual style
        self.nsty = nsty
        # normalized style
        self.loc = loc
        # true location: [parent, 'text' or 'tail', index]
        self.ch = prop.caph * utfs
        # cap height (height of flat capitals like T)
        # self.dr = dr;     # descender (length of p/q descender))
        self.sw = prop.spacew * utfs
        # space width for style
        self.ln = ln
        ln.cs.append(self)
        self.lnindex = len(ln.cs)-1
        # my line
        self.w = None
        # my word (to be assigned)
        self.windex = None # index in word
        self.type = None
        # 'normal','super', or 'sub' (to be assigned)
        self._dx = 0
        # get later
        self._dy = 0
        # get later
        self.deltanum = None
        # get later
        self.dkerns = lambda cL,cR : prop.dkerns.get((cL,cR),0)*utfs
        self.parsed_pts_t = None
        self.parsed_pts_ut = None
        # for merging later
        self._lsp = tchar.lspfunc(self.sty)
        self._bshft = tchar.bshftfunc(self.sty,self.loc.pel,self.ln.pt.textel)
        # letter spacing
        
    def copy(self,memo=dict()):
        ret = tchar.__new__(tchar)
        memo[self] = ret
        
        ret.c = self.c
        ret.tfs = self.tfs
        ret.sf = self.sf
        ret.utfs = self.utfs
        ret.prop = self.prop
        ret.cw = self.cw
        ret._sty = self._sty
        ret.nsty = self.nsty
        ret.ch = self.ch
        ret.sw = self.sw
        ret.lnindex = self.lnindex
        ret.w = self.w
        ret.windex = self.windex
        ret.type = self.type
        ret._dx = self._dx
        ret._dy = self._dy
        ret.deltanum = self.deltanum
        ret.dkerns = self.dkerns
        ret.parsed_pts_t = self.parsed_pts_t
        ret.parsed_pts_ut = self.parsed_pts_ut
        ret._lsp = self._lsp
        ret._bshft = self._bshft
        
        ret.loc = cloc(memo.get(self.loc.el,self.loc.el), self.loc.tt, self.loc.ind)
        ret.ln = memo.get(self.ln,self.ln)
        return ret

    @property
    def dx(self):
        return self._dx

    @dx.setter
    def dx(self, di):
        if self._dx != di:
            self._dx = di
            if self.w is not None:
                self.w.charpos = None  # invalidate
                ii=self.windex; w = self.w
                w.dxeff[ii] = (w.cs[ii].dx if ii<w.Ncs else 0) + (w.cs[ii-1].lsp if ii>0 else 0)
            self.ln.pt._dxchange = True

    @property
    def dy(self):
        return self._dy

    @dy.setter
    def dy(self, di):
        if self._dy != di:
            self._dy = di
            self.ln.pt._dychange = True

    @property
    def sty(self):
        # Character style
        return self._sty

    @sty.setter
    def sty(self, si):
        # Character style
        self._sty = si
        self.lsp = tchar.lspfunc(self._sty)
        self.bshft = tchar.bshftfunc(self._sty,self.loc.pel,self.ln.pt.textel)

    # anchorfrac = property(lambda self: get_anchorfrac(self.ln.anchor))

    @staticmethod
    def lspfunc(styv):
        if "letter-spacing" in styv:
            lspv = styv.get("letter-spacing")
            if "em" in lspv:  # em is basically the font size
                fs2 = styv.get("font-size")
                if fs2 is None:
                    fs2 = "12px"
                lspv = float(lspv.strip("em")) * dh.ipx(fs2)
            else:
                lspv = dh.ipx(lspv) or 0
        else:
            lspv = 0
        return lspv

    @property
    def lsp(self):
        # Character letter spacing
        return self._lsp

    @lsp.setter
    def lsp(self, sv):
        # Character letter spacing
        if sv != self._lsp:
            self._lsp = sv
            if self.w is not None:
                self.w.charpos = None
                ii=self.windex; w = self.w
                w.lsp[ii] = sv
                w.dxeff[ii+1] = (w.cs[ii+1].dx if ii<w.Ncs-1 else 0) + (w.cs[ii].lsp if ii<w.Ncs else 0)

    @staticmethod
    def bshftfunc(styv,strtel,stopel):
        if "baseline-shift" in styv:
            cel = strtel
            bshft = 0
            while cel != stopel:  # sum all ancestor baseline-shifts
                if "baseline-shift" in cel.cstyle:
                    bshft += tchar.get_baseline(cel.cstyle, cel.getparent())
                cel = cel.getparent()
        else:
            bshft = 0
        return bshft

    # Character baseline shift
    @property
    def bshft(self):
        return self._bshft

    @bshft.setter
    def bshft(self, sv):
        if sv != self._bshft:
            self._bshft = sv
            if self.w is not None:
                self.w.charpos = None
                self.w.bshft[self.windex] = sv
            

    @staticmethod
    def get_baseline(styin, fsel):
        bshft = styin.get("baseline-shift")
        if bshft == "super":
            bshft = "40%"
        elif bshft == "sub":
            bshft = "-20%"
        if "%" in bshft:  # relative to parent
            fs2, sf2, tmp, tmp = dh.Get_Composed_Width(fsel, "font-size", 4)
            bshft = fs2 / sf2 * float(bshft.strip("%")) / 100
        else:
            bshft = dh.ipx(bshft) or 0
        return bshft

    def delc(self):
        # Deletes character from document (and from my word/line)
        # Deleting a character causes the word to move if it's center- or right-justified. Adjust position to fix
        lncs = self.ln.cs
        # myi = lncs.index(self)  # index in line
        myi = self.lnindex # index in line
        
        # Differential kerning affect on character width
        dko1 = dko2 = dkn = 0
        if myi<len(lncs)-1:
            dko2 = self.dkerns(lncs[myi].c,lncs[myi+1].c) # old from right
            if myi > 0:
                dkn = self.dkerns(lncs[myi-1].c,lncs[myi+1].c) # new
        if myi>0:
            dko1 = self.dkerns(lncs[myi-1].c,lncs[myi].c) # old from left
        dk = dko1+dko2-dkn
        
        cwo = self.cw + dk + self._dx + self.lsp*(self.windex != 0)
        if self.w.unrenderedspace and self.w.cs[-1] == self:
            if len(self.w.cs) > 1 and self.w.cs[-2].c != " ":
                cwo = dk
                # deletion will not affect position
                # weirdly dkerning from unrendered spaces still counts

        if self == self.w.cs[0]:  # from beginning of line
            deltax = (self.ln.anchfrac - 1) * cwo 
        else:  # assume end of line
            deltax = self.ln.anchfrac * cwo
        
        lnx = [v for v in self.ln.x]
        changedx = False
        if deltax != 0:
            nnii = [ii for ii, x in enumerate(lnx) if x is not None]
            # non-None
            lnx[nnii[self.ln.ws.index(self.w)]] -= deltax
            changedx = True
            # self.ln.change_pos(newx)

        # Delete from document
        if self.loc.tt == "text":
            self.loc.el.text = self.loc.el.text[:self.loc.ind] + self.loc.el.text[self.loc.ind + 1:]
        else:
            self.loc.el.tail = self.loc.el.tail[:self.loc.ind] + self.loc.el.tail[self.loc.ind + 1:]

        # lnx = self.ln.x
        if len(lnx) > 1 and myi < len(lnx):
            if myi < len(lnx) - 1 and lnx[myi] is not None and lnx[myi + 1] is None:
                newx = lnx[:myi + 1] + lnx[myi + 2:]  # next x is None, delete that instead
            elif myi == len(lnx) - 1 and len(lncs) > len(lnx):
                newx = lnx  # last x, characters still follow
            else:
                newx = lnx[:myi] + lnx[myi + 1:]
            
            lnx = newx[: len(lncs) - 1]
            # we haven't deleted the char yet, so make it len-1 long
            # self.ln.change_pos(newx)
            changedx = True
        if changedx:
            self.ln.change_pos(lnx)

        # Delete from line
        for ii, ca in enumerate(lncs[myi + 1:], start=myi + 1):
            # need to decrement index of subsequent objects with the same parent
            if ca.loc.tt == self.loc.tt and ca.loc.el == self.loc.el:
                ca.loc.ind -= 1
            if ca.w is not None:
                # i2 = ca.w.cs.index(ca)
                # ca.w.iis[i2] -= 1
                ca.w.iis[ca.windex] -= 1
                
        for c in self.ln.cs[myi+1:]:
            c.lnindex -= 1
        lncs[myi].lnindex = None
        self.ln.cs = lncs[:myi] + lncs[myi + 1:]
        
        if len(self.ln.cs) == 0:  # line now empty, can delete
            self.ln.dell()
        # self.ln = None

        # Remove from word
        # myi = self.w.cs.index(self)
        # self.w.removec(myi)
        self.w.removec(self)

        # Update the dx/dy value in the ParsedText
        self.ln.pt.Update_Delta()

    def add_style(self, sty, setdefault=True):
        # Adds a style to an existing character by wrapping it in a new Tspan
        # t = Tspan();
        t = dh.new_element(Tspan, self.loc.el)
        t.text = self.c

        prt = self.loc.el
        if self.loc.tt == "text":
            tbefore = prt.text[0 : self.loc.ind]
            tafter = prt.text[self.loc.ind + 1 :]
            prt.text = tbefore
            prt.insert(0, t)

            t.tail = tafter
        else:
            tbefore = prt.tail[0 : self.loc.ind]
            tafter = prt.tail[self.loc.ind + 1 :]
            prt.tail = tbefore
            gp = prt.getparent()
            # parent is a Tspan, so insert it into the grandparent
            pi = gp.index(prt)
            gp.insert(pi + 1, t)
            # after the parent

            t.tail = tafter
            
        self.ln.pt.tree = None # invalidate

        # myi = self.ln.cs.index(self)
        myi = self.lnindex
        for ii in range(
            myi + 1, len(self.ln.cs)
        ):  # for characters after, update location
            ca = self.ln.cs[ii]
            if ca.loc.el == self.loc.el and ca.loc.tt == self.loc.tt:
                ca.loc = cloc(t, "tail", ii - myi - 1)
        self.loc = cloc(t, "text", 0)  # update my own location

        # When the specified style has something new span doesn't, are inheriting and
        # need to explicitly assign the default value
        newspfd = t.cspecified_style
        for a in newspfd:
            if a not in sty and setdefault:
                sty[a] = dh.default_style_atts[a]
                # dh.idebug([t.get_id2(),a,sty])

        t.cstyle = sty
        self.sty = sty

    def makesubsuper(self, sz=65):
        if self.type == "super":
            sty = "font-size:" + str(sz) + "%;baseline-shift:super"
        else:  # sub
            sty = "font-size:" + str(sz) + "%;baseline-shift:sub"
        self.add_style(sty)

    @property
    def pts_ut(self):
        # A specific character's untransformed pts
        # myi = self.w.cs.index(self)
        myi = self.windex
        cput = self.w.cpts_ut
        ret_pts_ut = [
            v2d(cput[0][myi][0], cput[0][myi][1]),
            v2d(cput[1][myi][0], cput[1][myi][1]),
            v2d(cput[2][myi][0], cput[2][myi][1]),
            v2d(cput[3][myi][0], cput[3][myi][1]),
        ]
        return ret_pts_ut

    @property
    def pts_t(self):
        # A specific character's transformed pts
        # myi = self.w.cs.index(self)
        myi = self.windex
        cpt = self.w.cpts_t
        ret_pts_t = [
            v2d(cpt[0][myi][0], cpt[0][myi][1]),
            v2d(cpt[1][myi][0], cpt[1][myi][1]),
            v2d(cpt[2][myi][0], cpt[2][myi][1]),
            v2d(cpt[3][myi][0], cpt[3][myi][1]),
        ]
        return ret_pts_t


    @property
    def pts_ut_ink(self):
        put = self.pts_ut;
        nw = self.prop.inkbb[2]*self.utfs;
        nh = self.prop.inkbb[3]*self.utfs;
        nx = put[0].x+self.prop.inkbb[0]*self.utfs;
        ny = put[0].y+self.prop.inkbb[1]*self.utfs+nh;
        return [v2d(nx,ny),v2d(nx,ny-nh),v2d(nx+nw,ny-nh),v2d(nx+nw,ny)]

def del2(x, ind):  # deletes an index from a list
    return x[:ind] + x[ind + 1 :]


def extendind(x, ind, val, default=None):  # indexes a matrix, extending it if necessary
    if ind >= len(x):
        x += [default] * (ind + 1 - len(x))
    x[ind] = val
    return x


def sortnone(x):  # sorts an x with Nones (skip Nones)
    rem = list(range(len(x)))
    minxrem = min([x[r] for r in rem if x[r] is not None])
    ii = min([r for r in rem if x[r] == minxrem])
    so = [ii]
    rem.remove(ii)
    while len(rem) > 0:
        if ii == len(x) - 1 or x[ii + 1] is not None:
            minxrem = min([x[r] for r in rem if x[r] is not None])
            ii = min([r for r in rem if x[r] == minxrem])
            so += [ii]
        else:
            ii += 1
        rem.remove(ii)
    return so


# A class representing the properties of a single character
# It is meant to be immutable...do not modify attributes
class cprop:
    __slots__ = ("char", "charw", "spacew", "caph", "descrh", "dkerns", "inkbb")
    def __init__(self, char, cw, sw, ch, dr, dkerns,inkbb):
        self.char = char
        self.charw = cw
        # character width
        self.spacew = sw
        # space width
        self.caph = ch
        # cap height
        self.descrh = dr
        # descender height
        self.dkerns = dkerns
        # table of how much extra width a preceding character adds to me
        self.inkbb = inkbb;

    def __mul__(self, scl):
        # dkern2 = dict();
        # for c in self.dkerns.keys():
        #     dkern2[c] = self.dkerns[c]*scl;
        dkern2 = {k: v * scl for k, v in self.dkerns.items()}
        inkbb2 = [v*scl for v in self.inkbb]
        return cprop(
            self.char,
            self.charw * scl,
            self.spacew * scl,
            self.caph * scl,
            self.descrh * scl,
            dkern2, inkbb2
        )


# A class indicating a single character's location in the SVG
class cloc:
    __slots__ = ("el", "tt", "ind", "pel")
    def __init__(self, el, tt, ind):
        self.el = el
        # the element it belongs to
        self.tt = tt
        # 'text' or 'tail'
        self.ind = ind
        # its index
        self.pel = el if tt == "text" else el.getparent()
        # where style comes from
            
    def copy(self,memo):
        ret = cloc.__new__(cloc)
        memo[self]=ret
        
        ret.el = memo[self.el]
        ret.tt = self.tt
        ret.ind = self.ind
        ret.pel = memo[self.pel]
        return ret

    def __eq__(self, other):
        return self.el == other.el and self.tt == other.tt and self.ind == other.ind
    
    def __hash__(self):
        return hash((self.el, self.tt, self.ind))


# A class representing the properties of a collection of characters
class Character_Table:
    def __init__(self, els):
        self.fonttestchars = 'pIaA10mMvo' # don't need that many, just to figure out which fonts we have
        self.ctable  = self.meas_char_ws(els)
        self.mults = dict()

    def get_prop(self, char, sty):
        if sty in self.ctable:
            return self.ctable[sty][char]
        else:
            dh.debug("No style matches!")
            dh.debug("Character: " + char)
            dh.debug("Style: " + sty)
            dh.debug("Existing styles: " + str(list(self.ctable.keys())))
            
    def get_prop_mult(self,char,sty,scl):
        try:
            return self.mults[(char,sty,scl)]
        except:
            self.mults[(char,sty,scl)] = self.get_prop(char,sty) * scl
            return self.mults[(char,sty,scl)]

    def generate_character_table(self, els):
        ctable = dict()
        pctable = dict()         # a dictionary of preceding characters in the same style
        
        atxt = [];
        asty = [];
        for el in els:
            tree = txttree(el)
            for di, tt, tel, txt in tree.dgenerator():
                    if txt is not None and len(txt) > 0:
                        sel = tel
                        if tt == 0:
                            sel = tree.pdict[tel]
                            # tails get their sty from the parent of the element the tail belongs to
                        sty = sel.cspecified_style
                        
                        asty.append(Character_Table.normalize_style(sty))
                        atxt.append(txt)
                        
        for ii in range(len(atxt)):
            sty = asty[ii]; txt = atxt[ii];
            ctable[sty] = list(set(ctable.get(sty, []) + list(txt)))
            if sty not in pctable:
                pctable[sty] = dict()
            for jj in range(1, len(txt)):
                pctable[sty][txt[jj]] = list(
                    set(pctable[sty].get(txt[jj], []) + [txt[jj - 1]])
                )
        for sty in ctable:  # make sure they have spaces
            ctable[sty] = dh.unique(ctable[sty] + [" "])
            for pc in pctable[sty]:
                pctable[sty][pc] = dh.unique(pctable[sty][pc] + [" "])
            # dh.idebug(' ' in ctable[sty])
        
        # Make a dictionary of all font specs in the document, along with the backup fonts in those specs
        # e.g. {'': ['sans-serif'], 'Calibri,Arial': ['Calibri', 'Arial', 'sans-serif']}
        # Add these to the table so we can check which fonts the system has
        # docfonts = dict()
        # for sty in ctable:
        #     if 'font-family' in sty:
        #         sspl = sty.split(';');
        #         ffii = [ii for ii in range(len(sspl)) if 'font-family' in sspl[ii]][0]
        #         allffs = sspl[ffii].split(':')[1]
        #         ffs = [x.strip("'").strip() for x in allffs.split(",")]
        #     else:
        #         ffs = []
        #         allffs = ''
        #     if 'sans-serif' not in ffs:
        #         ffs.append('sans-serif')
        #     docfonts[allffs]=ffs
        # bfs = list(set([v for lst in list(docfonts.values()) for v in lst]))
        # for bf in list(set(bfs+list(docfonts.keys()))):
        #     if bf!='':
        #         sty = 'font-family:'+bf
        #         ctable[sty] = list(set(ctable.get(sty, [' ']) + list(self.fonttestchars)))
        #         if sty not in pctable:
        #             pctable[sty] = dict()
            
        
        return ctable, pctable
    


    def meas_char_ws(self, els, forcecommand = False):
        # Measure the width of all characters of a given style by generating copies with a prefix and suffix.
        # To get the character width we compare this to a blank that does not contain any character.
        # Note that this is the logical "pen width," the width including intercharacter space
        # The width will be the width of a character whose composed font size is 1 uu.
        ctels = els
        if forcecommand and len(els)>0:
            # Examine the whole document if using command
            ctels = [d for d in els[0].croot.cdescendants if isinstance(d,TextElement)];
        ct, pct = self.generate_character_table(ctels)

        prefix = 'I='
        suffix = '=I'
        # We use an equals sign to get rid of differential kerning effects
        # (= and similar characters don't seem to ever have them), then I for capital height
        
        blnk = prefix+suffix
        pI = "pI"
        # We add pI as test characters because p gives the font's descender (how much the tail descends)
        # and I gives its cap height (how tall capital letters are).

        usepango = pr.haspango and not(forcecommand)
        # usepango = False
        # dh.idebug(usepango)
        cnt = 0
        if not(usepango):
            # A new document is generated instead of using the existing one. We don't have to parse an entire element tree
            # pxinuu = inkex.units.convert_unit("1px", "mm")
            # test document has uu = 1 mm (210 mm / 210)
            svgstart = '<svg width="210mm" height="297mm" viewBox="0 0 210 297" id="svg60386" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg"> <defs id="defs60383" /> <g id="layer1">'
            svgstop = "</g> </svg>"
            txt1 = '<text xml:space="preserve" style="'
            txt2 = '" id="text'
            txt3 = '">'
            txt4 = "</text>"
            svgtexts = ""
            import tempfile, os
            f = tempfile.NamedTemporaryFile(mode="wb",delete=False)
            tmpname = os.path.abspath(f.name);
            # tmpname = self.caller.options.input_file + "_tmp"
            # f = open(tmpname, "wb")
            f.write(svgstart.encode("utf8"))
            from xml.sax.saxutils import escape
        else:
            nbb = dict()
            # dh.idebug(ct)
        

        def Make_Character(c, sty):
            nonlocal cnt
            cnt += 1
            if not(usepango):
                nonlocal svgtexts
                svgtexts += txt1 + sty + txt2 + str(cnt) + txt3 + escape(c) + txt4
                if cnt % 1000 == 0:
                    f.write(svgtexts.encode("utf8"))
                    svgtexts = ""
            else:
                nbb["text" + str(cnt)] = (c,sty);
            return "text" + str(cnt)
        
        class StringInfo:
            def __init__(self, strval,strid,dkern,bareid=None):
                self.strval = strval
                self.strid = strid;
                self.dkern = dkern;
                self.bareid = bareid;

        badchars = {'\n':' ','\r':''}
        def effc(c):
            return badchars.get(c,c)
        
        ct2 = dict(); bareids = [];
        for s in ct:
            ct2[s] = dict()
            for ii in range(len(ct[s])):
                myc = ct[s][ii]
                t  = Make_Character(prefix + effc(myc) + suffix, s)
                tb = Make_Character(         effc(myc)         , s);
                bareids.append(tb)
                dkern = dict()
                if KERN_TABLE:
                    for jj in range(len(ct[s])):
                        pc = ct[s][jj]
                        if myc in pct[s] and pc in pct[s][myc]:
                            t2 = Make_Character(prefix + effc(pc)+effc(myc) + suffix, s)
                            # precede by all chars of the same style
                            dkern[pc] = t2
                ct2[s][myc] = StringInfo(myc, t, dkern,tb)

            ct2[s][pI]   = StringInfo(pI,   Make_Character(pI,   s), dict())
            ct2[s][blnk] = StringInfo(blnk, Make_Character(blnk, s), dict())

        ct = ct2
        if not(usepango):
            f.write((svgtexts + svgstop).encode("utf8"))
            f.close()
            nbb = dh.Get_Bounding_Boxes(filename=tmpname)
            import os
            os.remove(tmpname)
        else:
            # Pango doesn't play well with multithreading
            # Add a lock to prevent multiple simultaneous calls
            global pangolocked
            if 'pangolocked' not in globals():
                pangolocked = False
            finished = False
            while not(finished):
                if pangolocked:
                    import random, time
                    time.sleep(random.uniform(0.010, 0.020))
                else:
                    pangolocked = True
                    # dh.idebug(ct.keys())
                    for sty in ct:
                        joinch = ' ';
                        mystrs = [v[0] for k,v in nbb.items() if v[1]==sty]
                        myids  = [k    for k,v in nbb.items() if v[1]==sty]
                        
                        success,fm = pr.Set_Text_Style(sty)
                        if not(success):
                            pangolocked = False
                            return self.meas_char_ws(els, forcecommand=True)
                        joinedstr = joinch.join(mystrs)+joinch+prefix
                        
                        # We need to render all the characters, but we don't need all of their extents.
                        # For most of them we just need the first character, unless the following string
                        # has length 1 (and may be differently differentially kerned)
                        modw = [any(len(mystrs[i]) == 1 for i in range(ii, ii + 2) if 0 <= i < len(mystrs)) for ii in range(len(mystrs))]
                        needexts = ["1" if len(s) == 1 else "1" + "0"*(len(s)-2)+ ('1' if modw[ii] else '0') for ii,s in enumerate(mystrs)]
                        needexts2 = '0'.join(needexts) + '1' + '1'*len(prefix)
                        # needexts2 = '1'*len(joinedstr)
                        
                        pr.Render_Text(joinedstr)
                        exts,nu = pr.Get_Character_Extents(fm[1],needexts2)
                        # ws = [v[0][2] if v is not None else None for v in exts] # logical width by char
                        if nu>0:
                            pangolocked = False
                            return self.meas_char_ws(els, forcecommand=True)
                        
                        sw = exts[-len(prefix)-1][0][2]
                        cnt=0; x=0;
                        for ii,mystr in enumerate(mystrs):
                            # w = sum(ws[cnt:cnt+len(mystr)])
                            if modw[ii]:
                                altw = exts[cnt+len(mystr)-1][0][0] + exts[cnt+len(mystr)-1][0][2]- exts[cnt][0][0]
                            else:
                                altw = exts[cnt+len(mystr)+1][0][0] - exts[cnt][0][0] -sw
                            w = altw

                            if abs(altw-w)>1e-12:
                                dh.idebug((w,cnt,altw-w))
                                dh.idebug(mystr)
                                # dh.idebug([ord(c) for c in mystr])
                                dh.idebug(sty)
                                dh.idebug([v[0] for v in exts[cnt:cnt+len(mystr)]])
                                dh.idebug(len(mystrs[ii+1]))
                                
                            firstch = exts[cnt];
                            (xb,yb,wb,hb) = tuple(firstch[2]);
                            if myids[ii] not in bareids:
                                xb = x; wb = w; # use logical width
                            if mystr==prefix+suffix:
                                ycorr = hb+yb
                                
                            nbb[myids[ii]] = [v*TEXTSIZE for v in [xb,yb,wb,hb]]
                            cnt += len(mystr)+len(joinch);
                            x += w;    
                            
                        # Certain Windows fonts do not seem to comply with the Pango spec.
                        # The ascent+descent of a font is supposed to match its logical height,
                        # but this is not always the case. Correct using the top of the 'I' character.
                        for ii in range(len(mystrs)):
                            # if myids[ii] in bareids:
                            nbb[myids[ii]][1] -= ycorr*TEXTSIZE
                    pangolocked = False
                    finished = True
            

        dkern = dict()
        for s in ct:
            for ii in ct[s]:
                ct[s][ii].bb = bbox(nbb[ct[s][ii].strid])
                if KERN_TABLE:
                    precwidth = dict()
                    for jj in ct[s][ii].dkern:
                        precwidth[jj] = bbox(nbb[ct[s][ii].dkern[jj]]).w
                        # width including the preceding character and extra kerning
                    ct[s][ii].precwidth = precwidth

            if KERN_TABLE:
                dkern[s] = dict()
                for ii in ct[s]:
                    mcw = ct[s][ii].bb.w  - ct[s][blnk].bb.w # my character width
                    for jj in ct[s][ii].precwidth:
                        pcw = ct[s][jj].bb.w - ct[s][blnk].bb.w          # preceding char width
                        bcw = ct[s][ii].precwidth[jj] - ct[s][blnk].bb.w  # both char widths
                        dkern[s][jj, ct[s][ii].strval] = bcw - pcw - mcw   # preceding char, then next char

        for s in ct:
            blnkwd = ct[s][blnk].bb.w;
            sw = ct[s][' '].bb.w - blnkwd      # space width
            ch = ct[s][blnk].bb.h          # cap height
            dr =  ct[s][pI].bb.y2          # descender
            
            dkernscl = dict()
            if KERN_TABLE:
                for k in dkern[s]:
                    dkernscl[k] = dkern[s][k]/TEXTSIZE
            
            for ii in ct[s]:
                cw = ct[s][ii].bb.w - blnkwd # character width (full, including extra space on each side)
                if ct[s][ii].bareid in nbb:
                    inkbb = nbb[ct[s][ii].bareid]
                else:
                    inkbb = [ct[s][ii].bb.x1,ct[s][ii].bb.y1,0,0] # whitespace: make zero-width
                # if ct[s][ii].strval in badchars:
                #     cw = 0
                ct[s][ii] = cprop(
                    ct[s][ii].strval,
                    cw/TEXTSIZE,
                    sw/TEXTSIZE,
                    ch/TEXTSIZE,
                    dr/TEXTSIZE,
                    dkernscl, [v/TEXTSIZE for v in inkbb]
                )
        return ct

    # For generating test characters, we want to normalize the style so that we don't waste time
    # generating a bunch of identical characters whose font-sizes are different. A style is generated
    # with a single font-size, and only with presentation attributes that affect character shape.
    textshapeatt = ['font-family','font-weight','font-style','font-variant','font-stretch','font-size']
    
    # 'stroke','stroke-width' do not affect kerning at all
    @staticmethod
    @lru_cache(maxsize=None)
    def normalize_style(sty):
        nones = [None, "none", "None"]
        sty2 = inkex.OrderedDict()
        # we don't need a full Style since we only want the string (for speed)
        for a in Character_Table.textshapeatt:
            if a in sorted(sty):
                styv = sty.get(a)
                # if styv is not None and styv.lower()=='none':
                #     styv=None # actually don't do this because 'none' might be overriding inherited styles
                if styv is not None:
                    if a == "font-family" and styv not in nones:
                        # dh.idebug([styv,",".join([v.strip().strip("'") for v in styv.split(",")])])
                        styv = ",".join([v.strip().strip("'") for v in styv.split(",")])
                    sty2[a] = styv
        sty2["font-size"] = str(TEXTSIZE)+"px"
        
        # Replace nominal font with true rendered font
        ffam = sty.get('font-family','');
        fsty = sty.get('font-style',dh.default_style_atts['font-style']);
        fstr = sty.get('font-stretch',dh.default_style_atts['font-stretch']);
        fwgt = sty.get('font-weight',dh.default_style_atts['font-weight']);
        
        sty2['font-family']=pr.get_true_font((ffam,fstr,fwgt,fsty));
        
        sty2 = inkex.OrderedDict(sorted(sty2.items())) # sort alphabetically by keys
        for a in Character_Table.textshapeatt:
            if sty2.get(a)==dh.default_style_atts[a]:
                del sty2[a]
        
        sty2 = ";".join([f"{key}:{value}" for key, value in sty2.items()])
        return sty2


# Recursively delete empty elements
# Tspans are deleted if they're totally empty, TextElements are deleted if they contain only whitespace
def deleteempty(el):
    anydeleted = False
    for k in list(el):
        d = deleteempty(k)
        anydeleted = anydeleted or d
    txt = el.text
    tail = el.tail
    if (
        (txt is None or len((txt)) == 0)
        and (tail is None or len((tail)) == 0)
        and len(list(el)) == 0
    ):
        el.delete2()
        anydeleted = True
        # delete anything empty
        # dh.debug(el.get_id())
    elif isinstance(el, (TextElement)):

        def wstrip(txt):  # strip whitespaces
            return txt.translate({ord(c): None for c in " \n\t\r"})

        if all(
            [
                (d.text is None or len(wstrip(d.text)) == 0)
                and (d.tail is None or len(wstrip(d.tail)) == 0)
                for d in dh.descendants2(el)
            ]
        ):
            el.delete2()
            anydeleted = True
            # delete any text elements that are just white space
    return anydeleted



def maxnone(xi):
    if len(xi) > 0:
        return max(xi)
    else:
        return None

# A fast setter for 'x', 'y', 'dx', and 'dy' that uses lxml's set directly and
# converts arrays to a string
fset = su.fset
def xyset(el,xy,v):
    if not(v):
        el.attrib.pop(xy, None)  # pylint: disable=no-member
    else:
        fset(el,xy, str(v)[1:-1].replace(',',''))
