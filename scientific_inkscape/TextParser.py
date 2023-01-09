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

import os, sys
import numpy as np

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh
from dhelpers import v2d_simple as v2ds
from dhelpers import bbox

from pango_renderer import PangoRenderer
pr = PangoRenderer();

from copy import copy, deepcopy
import inkex
from inkex import TextElement, Tspan, Transform


# Add parsed_text property to TextElements
def get_parsed_text(el):
    if not (hasattr(el, "_parsed_text")):
        el._parsed_text = ParsedText(el, el.croot.char_table);
    return el._parsed_text
inkex.TextElement.parsed_text = property(get_parsed_text)

# Add character table property and function to SVG
def make_char_table_fcn(svg,els=None):
    # Can be called with els argument to examine list of elements only 
    # (otherwise use entire SVG)
    if els is None: 
        tels = [d for d in svg.cdescendants if isinstance(d,TextElement)];
    else:           
        tels = [d for d in els              if isinstance(d,TextElement)]
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

        # self.lns = self.Parse_Lines(el,debug=debug);
        # self.Finish_Lines();

        self.lns = self.Parse_Lines()
        self.Finish_Lines()

        for ln in self.lns:
            for w in ln.ws:
                w.parsed_bb = deepcopy(w.bb)
                for c in w.cs:
                    c.parsed_pts_ut = c.pts_ut
                    c.parsed_pts_t = c.pts_t

        # dh.idebug('\n')
        # for ln in self.lns:
        #     dh.idebug(ln.txt())
        #     # for c in ln.cs:
        #     #     dh.idebug([c.c,c.lsp])
        #     dh.idebug(ln.continuex)
        #     dh.idebug(ln.sprl)
        #     dh.idebug(ln.x)
        #     dh.idebug(ln.xsrc.get_id())
        #     for c in ln.cs:
        #         dh.idebug((c.c,c.cw))
        #     # dh.debug(ln.sprl)
        #     # dh.debug(ln.tlvlno)

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
        # Duplicates a PT and its text
        ret = copy(self)
        ret.textel = self.textel.duplicate2()
        # d1 = dh.descendants2(self.textel);
        d1 = self.textds
        d2 = dh.descendants2(ret.textel)
        ret.textds = d2
        ret.ctable = self.ctable
        ret.lns = []
        for ln in self.lns:
            # eli = d1.index(ln.el);
            xsi = d1.index(ln.xsrc)
            ysi = d1.index(ln.ysrc)
            ret.lns.append(
                tline(
                    ret,
                    copy(ln.x),
                    copy(ln.y),
                    d2[xsi],
                    d2[ysi],
                    ln.sprl,
                    ln.sprlabove,
                    ln.anchor,
                    ln.transform,
                    ln.angle,
                    ln.tlvlno,
                    ln.style,
                    ln.continuex,
                    ln.continuey,
                )
            )
            # ret.lns[-1].anchor = ln.anchor;
            ret.lns[-1].cs = []
            for c in ln.cs:
                myi = d1.index(c.loc.el)
                newloc = cloc(d2[myi], c.loc.tt, c.loc.ind)
                prop = c.prop
                prop.charw = c.cw
                #                    prop = self.ctable.get_prop(' ',c.nsty)*c.fs # cannot just use old one for some reason???
                ret.lns[-1].addc(tchar(c.c, c.fs, c.sf, prop, c.sty, c.nsty, newloc))
        ret.Finish_Lines()
        # generates the new words
        for ii in range(len(self.lns)):
            for jj in range(len(self.lns[ii].ws)):
                ret.lns[ii].ws[jj].parsed_bb = self.lns[ii].ws[jj].parsed_bb
            for jj in range(len(self.lns[ii].cs)):
                ret.lns[ii].cs[jj].parsed_pts_ut = self.lns[ii].cs[jj].parsed_pts_ut
                ret.lns[ii].cs[jj].parsed_pts_t = self.lns[ii].cs[jj].parsed_pts_t

        ret.isinkscape = self.isinkscape
        ret.dxs = copy(self.dxs)
        ret.dys = copy(self.dys)
        ret.flatdelta = self.flatdelta

        ret._dxchange = self._dxchange
        ret._hasdx = self._hasdx
        ret._dychange = self._dychange
        ret._hasdy = self._hasdy
        return ret

    def txt(self):
        return [v.txt() for v in self.lns]

    # Every text element in an SVG can be thought of as a group of lines.
    # A line is a collection of text that gets its position from a single source element.
    # This position may be directly set, continued from a previous line, or inherited from a previous line
    def Parse_Lines(self, srcsonly=False):
        el = self.textel
        # First we get the tree structure of the text and do all our gets
        ds, pts, cd, pd = dh.descendants2(el, True)
        Nd = len(ds)
        self.textds = ds
        ks = list(el)
        text = [d.text for d in ds]
        ptail = [[tel.tail for tel in pt] for pt in pts]  # preceding tails
        if len(ptail) > 0 and len(ptail[-1]) > 0:
            ptail[-1][-1] = None
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
        for di, tt in ttiterator(Nd):
            if tt == 0:
                txts = ptail[di]
                tels = pts[di]
            else:
                txts = [text[di]]
                tels = [ds[di]]

            for ii in range(len(tels)):
                tel = tels[ii]
                txt = txts[ii]

                # dh.idebug((ds[di].get_id2(),types[di],tt))
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
                        
                        lns.append(
                            tline(
                                self,
                                xv,
                                yv,
                                xsrc,
                                ysrc,
                                issprl,
                                sprlabove,
                                anch,
                                ct,
                                ang,
                                tlvlno,
                                sty,
                                continuex,
                                continuey,
                            )
                        )

                        if newsprl or len(lns) == 1:
                            sprl_inherits = lns[-1]

                    if txt is not None:

                        for jj in range(len(txt)):
                            c = txt[jj]
                            prop = self.ctable.get_prop(c, nsty) * fs
                            ttv = "text"
                            if tt == 0:
                                ttv = "tail"
                            lns[-1].addc(
                                tchar(c, fs, sf, prop, sty, nsty, cloc(tel, ttv, jj))
                            )

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

    @staticmethod
    def GetXY(el, xy):
        val = el.get(xy)
        if val is None:
            val = [None]
            # None forces inheritance
        else:
            tmp = []
            for x in val.split():
                if x.lower() == "none":
                    tmp.append(None)
                else:
                    tmp.append(dh.implicitpx(x))
            val = tmp
        return val
    
    # Traverse the element tree to find dx/dy values and apply them to the chars
    def Get_Delta(self, lns, el, xy, dxin=None, cntin=None, dxysrc=None):
        if dxin is None:
            dxy = ParsedText.GetXY(el, xy)
            dxysrc = el
            cnt = 0
            toplevel = True
        else:
            dxy = dxin
            cnt = cntin
            toplevel = False
        if len(dxy) > 0 and dxy[0] is not None:
            allcs = [c for ln in lns for c in ln.cs]
            # get text, then each child, then each child's tail
            if el.text is not None:
                for ii in range(len(el.text)):
                    thec = [
                        c
                        for c in allcs
                        if c.loc.el == el and c.loc.tt == "text" and c.loc.ind == ii
                    ]
                    if cnt < len(dxy):
                        # if dxy[cnt]==30: dh.debug(dxysrc.get_id())
                        if xy == "dx":
                            thec[0].dx = dxy[cnt]
                        if xy == "dy":
                            thec[0].dy = dxy[cnt]
                        cnt += 1
            for k in el.getchildren():
                cnt = self.Get_Delta(lns, k, xy, dxy, cnt, dxysrc)
                if (
                    k.get("sodipodi:role") == "line"
                    and isinstance(k, Tspan)
                    and isinstance(k.getparent(), TextElement)
                ):
                    cnt += 1
                    # top-level Tspans have an implicit CR
                if k.tail is not None:
                    for ii in range(len(k.tail)):
                        thec = [
                            c
                            for c in allcs
                            if c.loc.el == k and c.loc.tt == "tail" and c.loc.ind == ii
                        ]
                        if cnt < len(dxy):
                            if xy == "dx":
                                thec[0].dx = dxy[cnt]
                            if xy == "dy":
                                thec[0].dy = dxy[cnt]
                            cnt += 1
        if toplevel:
            for k in el.getchildren():
                self.Get_Delta(lns, k, xy)
        return cnt

    # Traverse the tree to find where deltas need to be located relative to the top-level text
    def Get_DeltaNum(self, lns, el, topcnt=0):
        allcs = [c for ln in lns for c in ln.cs]
        # get text, then each child, then each child's tail
        if el.text is not None:
            for ii in range(len(el.text)):
                thec = [
                    c
                    for c in allcs
                    if c.loc.el == el and c.loc.tt == "text" and c.loc.ind == ii
                ]
                if len(thec) == 0:
                    dh.debug("Missing " + el.text[ii])
                    tll = ParsedText(self.textel, self.ctable)
                    dh.debug(self.txt())
                    dh.debug(tll.txt())
                thec[0].deltanum = topcnt
                topcnt += 1
        for k in el.getchildren():
            topcnt = self.Get_DeltaNum(lns, k, topcnt=topcnt)
            if (
                k.get("sodipodi:role") == "line"
                and isinstance(k, Tspan)
                and isinstance(k.getparent(), TextElement)
            ):
                topcnt += 1  # top-level Tspans have an implicit CR
            if k.tail is not None:
                for ii in range(len(k.tail)):
                    thec = [
                        c
                        for c in allcs
                        if c.loc.el == k and c.loc.tt == "tail" and c.loc.ind == ii
                    ]
                    if len(thec) == 0:
                        dh.idebug("\nMissing " + k.tail[ii])
                        tll = ParsedText(self.textel, self.ctable)
                        dh.idebug(self.txt())
                        dh.idebug(tll.txt())
                        quit()
                    thec[0].deltanum = topcnt
                    topcnt += 1
        return topcnt

    # After dx/dy has changed, call this to write them to the text element
    # For simplicity, this is best done at the ParsedText level all at once
    def Update_Delta(self, forceupdate=False):
        if self._dxchange or self._dychange or forceupdate:
            dxs = [c.dx for ln in self.lns for c in ln.cs]
            dys = [c.dy for ln in self.lns for c in ln.cs]

            anynewx = self.dxs != dxs and any([dxv != 0 for dxv in self.dxs + dxs])
            # only if new is not old and at least one is non-zero
            anynewy = self.dys != dys and any([dyv != 0 for dyv in self.dys + dys])

            if anynewx or anynewy or forceupdate:
                self.Get_DeltaNum(self.lns, self.textel)
                dx = []
                dy = []
                for ln in self.lns:
                    for c in ln.cs:
                        if c.deltanum is not None:
                            dx = extendind(dx, c.deltanum, c.dx, 0)
                            dy = extendind(dy, c.deltanum, c.dy, 0)

                if not (self.flatdelta):  # flatten onto textel
                    # for d in dh.descendants2(self.textel):
                    for d in self.textds:
                        d.set("dx", None)
                        d.set("dy", None)
                    self.flatdelta = True
                    # only need to do this once

                dxset = None
                dyset = None
                if any([dxv != 0 for dxv in dx]):
                    dxset = " ".join([str(v) for v in dx])
                if any([dyv != 0 for dyv in dy]):
                    dyset = " ".join([str(v) for v in dy])
                self.textel.set("dx", dxset)
                self.textel.set("dy", dyset)
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

                tlvl.getparent().set("x", tline.writev(ln.x))
                tlvl.getparent().set("y", tline.writev(ln.y))

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
        ciis = [c.ln.cs.index(c) for c in cs]  # indexs of charsin line

        # Record position
        dxl = [c.dx for c in cs]
        dyl = [c.dy for c in cs]

        # dh.idebug(dxl)

        fusex = self.lns[il].continuex or ciis[0] > 0 or dxl[0] != 0
        fusey = self.lns[il].continuey or ciis[0] > 0 or dyl[0] != 0
        if fusex:
            xf = self.lns[il].anchorfrac
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
        deleteempty(self.textel)
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
                    

    


# For lines, words, and chars
def get_anchorfrac(anch):
    anch_frac = {"start": 0, "middle": 0.5, "end": 1}
    return anch_frac[anch]


# A single line, which represents a list of characters. Typically a top-level Tspan or TextElement.
# This is further subdivided into a list of words
class tline:
    def __init__(
        self,
        ll,
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
        self.pt = ll

    # x property
    def get_x(self):
        if self.continuex:  # For continuing lines, need to calculate anchor position
            if self.pt is not None:
                ii = self.pt.lns.index(self)
                if ii > 0 and len(self.pt.lns[ii - 1].ws) > 0:
                    xf = self.anchorfrac
                    xanch = (1 + xf) * self.pt.lns[ii - 1].ws[-1].pts_ut[
                        3
                    ].x - xf * self.pt.lns[ii - 1].ws[-1].pts_ut[0].x
                    return [xanch]
                else:
                    return [0]
            else:
                return [0]
        else:
            return self._x

    def set_x(self, xi):
        self._x = xi

    x = property(get_x, set_x)

    # y property
    def get_y(self):
        if self.continuey:  # For continuing lines, need to calculate anchor position
            if self.pt is not None:
                ii = self.pt.lns.index(self)
                if ii > 0 and len(self.pt.lns[ii - 1].ws) > 0:
                    xf = self.anchorfrac
                    yanch = (1 + xf) * self.pt.lns[ii - 1].ws[-1].pts_ut[
                        3
                    ].y - xf * self.pt.lns[ii - 1].ws[-1].pts_ut[0].y
                    return [yanch]
                else:
                    return [0]
            else:
                return [0]
        else:
            return self._y

    def set_y(self, yi):
        self._y = yi

    y = property(get_y, set_y)
    anchorfrac = property(lambda self: get_anchorfrac(self.anchor))

    def addc(self, c):
        self.cs.append(c)
        c.ln = self

    def insertc(self, c, ec):  # insert below
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

        # if len(self.x)>1:
        #     xn = [self.x[ii] for ii in range(len(self.x)) if self.x[ii] is not None]; # non-None
        #     sws = [x for _, x in sorted(zip(xn, self.ws), key=lambda pair: pair[0])] # words sorted in ascending x
        #     for ii in range(len(sws)-1):
        #         sws[ii].nextw = sws[ii+1]
        # dh.debug([self.x,len(self.ws)])

    def dell(self):  # deletes the whole line
        for c in reversed(self.cs):
            c.delc()
        if self in self.pt.lns:
            self.pt.lns.remove(self)
        # self.pt = None;

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
                    maxx -= w.cs[-1].cw / w.cs[-1].sf

                xf = get_anchorfrac(newanch)
                newx = (1 - xf) * minx + xf * maxx

                if len(w.cs) > 0:
                    newxv = self.x
                    newxv[self.cs.index(w.cs[0])] = newx

                    # dh.idebug([w.txt(),newx,newxv])
                    self.change_pos(newxv)
                    dh.Set_Style_Comp(w.cs[0].loc.el, "text-anchor", newanch)
                    alignd = {"start": "start", "middle": "center", "end": "end"}
                    dh.Set_Style_Comp(w.cs[0].loc.el, "text-align", alignd[newanch])

                self.anchor = newanch
                for w in self.ws:
                    w.pts_ut = None  # invalidate word positions

    @staticmethod
    def writev(v):
        if v == []:
            return None
        else:
            return " ".join([str(w) for w in v])

    # Disable sodipodi:role = line
    def disablesodipodi(self, force=False):
        if len(self.sprlabove)>0 or force:
            if len(self.cs) > 0:
                newsrc = self.cs[0].loc.el  # disabling snaps src to first char
                if self.cs[0].loc.tt == "tail":
                    newsrc = self.cs[0].loc.el.getparent()
                newsrc.set("sodipodi:role", None)
                
                # for cel in self.sprlabove:
                #     cel.set("sodipodi:role", None)
                
                self.sprlabove = []
                self.xsrc = newsrc
                self.ysrc = newsrc
                self.xsrc.set("x", tline.writev(self.x))  # fuse position to new source
                self.ysrc.set("y", tline.writev(self.y))
                self.sprl = False

    # Update the line's position in the document, accounting for inheritance
    # Never change x/y directly, always call this function
    def change_pos(self, newx=None, newy=None, reparse=False):
        if newx is not None:
            sibsrc = [ln for ln in self.pt.lns if ln.xsrc == self.xsrc]
            if len(sibsrc) > 1:
                for ln in reversed(sibsrc):
                    ln.disablesodipodi()  # Disable sprl when lines share an xsrc

            if all([v is None for v in newx[1:]]) and len(newx) > 0:
                newx = [newx[0]]
            oldx = self.x
            self.x = newx
            self.xsrc.set("x", tline.writev(newx))
            # dh.idebug([self.txt(),self.xsrc.get('x')])

            if (
                len(oldx) > 1 and len(self.x) == 1 and len(self.sprlabove)>0
            ):  # would re-enable sprl
                self.disablesodipodi()

            # dh.idebug([self.txt(),self.xsrc.get_id(),self.xsrc.get('x')])

        if newy is not None:
            sibsrc = [ln for ln in self.pt.lns if ln.ysrc == self.ysrc]
            if len(sibsrc) > 1:
                for ln in reversed(sibsrc):
                    ln.disablesodipodi()  # Disable sprl when lines share a ysrc

            if all([v is None for v in newy[1:]]) and len(newy) > 0:
                newy = [newy[0]]
            oldy = self.y
            self.y = newy
            self.ysrc.set("y", tline.writev(newy))

            if (
                len(oldy) > 1 and len(self.y) == 1 and len(self.sprlabove)>0
            ):  # would re-enable sprl
                self.disablesodipodi()
        if reparse:
            self.parse_words()
            # usually don't want to do this since it generates new words


# A word (a group of characters with the same assigned anchor)
class tword:
    def __init__(self, ii, x, y, ln):
        c = ln.cs[ii]
        self.cs = [c]
        self.iis = [ii]
        # character index in word
        self._x = x
        self._y = y
        self.sf = c.sf
        # all letters have the same scale
        self.ln = ln
        self.transform = ln.transform
        c.w = self
        # self.unrenderedspace = False;
        self.nextw = self.prevw = self.sametspan = None
        self._pts_ut = self._pts_t = self._bb = None
        # invalidate
        self._lsp = self._bshft = self._dxeff = self._charpos = None
        self._cpts_ut = None
        self._cpts_t = None
        self._ntransform = None
        # self.orig_pts_t = None; self.orig_pts_ut = None; self.orig_bb = None; # for merging later

    def addc(self, ii):  # adds an existing char to a word
        c = self.ln.cs[ii]
        self.cs.append(c)
        self.cchange()
        self.iis.append(ii)
        c.w = self

    def removec(self, ii):  # removes a char from a word
        # myc = self.cs[ii]
        self.cs = del2(self.cs, ii)
        self.cchange()
        self.iis = del2(self.iis, ii)
        if len(self.cs) == 0:  # word now empty
            self.delw()
        # myc.w = None

    # Callback for character addition/deletion. Used to invalidate cached properties
    def cchange(self):
        self.lsp = None
        self.bshft = None
        self.dxeff = None
        self.charpos = None

        if self.ln.pt._hasdx:
            self.ln.pt._dxchange = True
        if self.ln.pt._hasdy:
            self.ln.pt._dychange = True

    @property
    def x(self):
        if self.ln is not None:
            lnx = self.ln.x
            if len(self.iis) > 0:
                fi = self.iis[0]
                if fi < len(lnx):
                    return lnx[fi]
                else:
                    return lnx[-1]
            else:
                return 0
        else:
            return 0

    @property
    def y(self):
        if self.ln is not None:
            lny = self.ln.y
            if len(self.iis) > 0:
                fi = self.iis[0]
                if fi < len(lny):
                    return lny[fi]
                else:
                    return lny[-1]
            else:
                return 0
        else:
            return 0

    @property
    def ntransform(self):
        if self._ntransform is None:
            self._ntransform = -self.transform
        return self._ntransform

    # Deletes me from everywhere
    def delw(self):
        for c in reversed(self.cs):
            c.delc()
        if self in self.ln.ws:
            self.ln.ws.remove(self)

    # Gets all text
    def txt(self):
        return "".join([c.c for c in self.cs])

    # Generate a new character and add it to the end of the word
    def appendc(self, ncv, ncw, ndx, ndy, totail=None):
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
        c.cw = ncw
        c.dx = ndx
        c.dy = ndy
        # c.pending_style = None;
        # c.lsp = nlsp

        if totail is None:
            c.loc = cloc(c.loc.el, c.loc.tt, c.loc.ind + 1)  # updated location
        else:
            c.loc = cloc(totail, "tail", 0)
        c.sty = c.loc.pel.cspecified_style

        # Add to line
        myi = self.ln.cs.index(lc) + 1  # insert after last character
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
                i2 = ca.w.cs.index(ca)
                ca.w.iis[i2] += 1
        # Add to word, recalculate properties
        self.addc(myi)

        # Adding a character causes the word to move if it's center- or right-justified
        # Need to fix this by adjusting position
        deltax = -self.anchorfrac * self.ln.cs[myi].cw / self.sf
        if deltax != 0:
            newx = self.ln.x
            newx[self.ln.cs.index(self.cs[0])] -= deltax
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
            numsp = (bl2.x - br1.x) / (lc.sw / self.sf)
            numsp = max(0, round(numsp))
            if maxspaces is not None:
                numsp = min(numsp, maxspaces)

            # dh.idebug([self.txt(),nw.txt(),(bl2.x-br1.x)/(lc.sw/self.sf)])
            # dh.idebug([self.txt(),nw.txt(),lc.sw,lc.cw])
            for ii in range(numsp):
                self.appendc(" ", lc.sw, -lc.lsp, 0)

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

                # dh.idebug(noneid(totail))
                self.appendc(c.c, c.cw, mydx, c.dy, totail=totail)
                newc = self.cs[-1]

                newc.parsed_pts_ut = [
                    (self.transform).applyI_to_point(p) for p in c.parsed_pts_t
                ]
                newc.parsed_pts_t = c.parsed_pts_t

                # Update the style
                newsty = None
                if c.sty != newc.sty:
                    newsty = c.sty

                if ntype in ["super", "sub"]:
                    newsty = c.sty

                    # Nativize super/subscripts
                    if ntype == "super":
                        newsty["baseline-shift"] = "super"
                    else:
                        newsty["baseline-shift"] = "sub"

                    newsty["font-size"] = "65%"
                    # Leave size unchanged
                    # sz = round(c.sw/newc.sw*100)
                    # newsty['font-size'] = str(sz)+'%';

                    # Leave baseline unchanged (works, but do I want it?)
                    # shft = round(-(bl2.y-br1.y)/self.fs*100*self.sf);
                    # newsty['baseline-shift']= str(shft)+'%';
                elif c.sf != newc.sf:
                    # Prevent accidental font size changes when differently transformed
                    sz = round(c.sw/newc.sw*100)
                    newsty['font-size'] = str(sz)+'%';

                if newsty is not None:
                    # dh.idebug(newsty)
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

            xf = self.anchorfrac
            deltaanch = (nminx * (1 - xf) + nmaxx * xf) - (
                ominx * (1 - xf) + omaxx * xf
            )
            # how much the final anchor moved
            # dh.debug(deltaanch)
            if deltaanch != 0:
                newx = self.ln.x
                newx[self.ln.cs.index(self.cs[0])] -= deltaanch
                self.ln.change_pos(newx)
                # self.x -= deltaanch
            self.ln.pt.Update_Delta()

    @property
    def lsp(self):
        if self._lsp is None:
            self._lsp = [c.lsp for c in self.cs]
        return self._lsp

    @lsp.setter
    def lsp(self, li):
        if li is None:
            self._lsp = None
            self.dxeff = None

    # @property
    # def bshft(self):
    #     if self._bshft is None:
    #         self._bshft = [c.bshft for c in self.cs];
    #     return self._bshft
    # @bshft.setter
    # def bshft(self,li):
    #     if li is None:
    #         self._bshft = None

    # Effective dx (with letter-spacing). Note that letter-spacing adds space
    # after the char, so dxl ends up being longer than the number of chars by 1
    # @property
    @property
    def dxeff(self):
        if self._dxeff is None:
            dxlsp = [0] + self.lsp
            # letter-spacing applies to next character
            self._dxeff = [self.cs[ii].dx + dxlsp[ii] for ii in range(len(self.cs))] + [
                dxlsp[-1]
            ]
        return self._dxeff

    @dxeff.setter
    def dxeff(self, di):
        if di is None:
            self._dxeff = None

    # Word properties
    def get_fs(self):
        return maxnone([c.fs for c in self.cs])

    fs = property(get_fs)

    def get_sw(self):
        return maxnone([c.sw for c in self.cs])

    sw = property(get_sw)

    def get_ch(self):
        return maxnone([c.ch for c in self.cs])

    ch = property(get_ch)

    def get_ang(self):
        return self.ln.angle

    angle = property(get_ang)
    anchorfrac = property(lambda self: get_anchorfrac(self.ln.anchor))

    @property
    def unrenderedspace(
        self,
    ):  # If last char of a multichar line is a space, is not rendered
        return (
            len(self.cs) > 1
            and self.cs[-1] == self.ln.cs[-1]
            and self.cs[-1].c in [" ", "\u00A0"]
        )

    @property
    def charpos(self):
        # Where characters in a word are relative to the left side of the word, in x units
        if self._charpos is None:
            if len(self.cs) > 0:
                dxl = self.dxeff
                wadj = [0 for c in self.cs]
                if KERN_TABLE:
                    for ii in range(1, len(self.cs)):
                        dk = self.cs[ii].dkerns.get((self.cs[ii - 1].c, self.cs[ii].c))
                        if dk is None:
                            dk = 0
                            # for chars of different style
                        wadj[ii] = dk
                tmp = [
                    self.cs[ii].cw + dxl[ii] * self.sf + wadj[ii]
                    for ii in range(len(self.cs))
                ]
                cstop = [sum(tmp[: ii + 1]) for ii in range(len(tmp))]
                # cumulative width up to and including the iith char
                cstrt = [cstop[ii] - self.cs[ii].cw for ii in range(len(self.cs))]
            else:
                cstop = []
                cstrt = []

            cstrt = np.array(cstrt)
            cstop = np.array(cstop)

            ww = cstop[-1]
            offx = -self.anchorfrac * (
                ww - self.unrenderedspace * self.cs[-1].cw
            )  # offset of the left side of the word from the anchor
            wx = self.x
            wy = self.y

            lx = (wx + (cstrt + offx) / self.sf).reshape(-1, 1)
            rx = (wx + (cstop + offx) / self.sf).reshape(-1, 1)
            dyl = [c.dy for c in self.cs]
            chs = [c.ch for c in self.cs]
            bss = [c.bshft for c in self.cs]

            # dh.idebug(self.bshft)
            by = np.array(
                [wy + sum(dyl[: ii + 1]) - bss[ii] for ii in range(len(dyl))]
            ).reshape(-1, 1)
            ty = np.array(
                [
                    wy + sum(dyl[: ii + 1]) - chs[ii] / self.sf - bss[ii]
                    for ii in range(len(dyl))
                ]
            ).reshape(-1, 1)

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
            offx = -self.anchorfrac * (
                ww - self.unrenderedspace * self.cs[-1].cw
            )  # offset of the left side of the word from the anchor

            wx = self.x
            wy = self.y
            if len(self.cs) > 0:
                ymin = min([wy + c.dy - c.ch / self.sf for c in self.cs])
                ymax = max([wy + c.dy for c in self.cs])
            else:
                ymin = ymax = wy
            self._pts_ut = [
                v2ds(wx + offx / self.sf, ymax),
                v2ds(wx + offx / self.sf, ymin),
                v2ds(wx + (ww + offx) / self.sf, ymin),
                v2ds(wx + (ww + offx) / self.sf, ymax),
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
            self._bb = bbox(
                [
                    min([p.x for p in ptt]),
                    min([p.y for p in ptt]),
                    max([p.x for p in ptt]) - min([p.x for p in ptt]),
                    max([p.y for p in ptt]) - min([p.y for p in ptt]),
                ]
            )
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

            self._cpts_ut = [
                np.hstack((lx, by)),
                np.hstack((lx, ty)),
                np.hstack((rx, ty)),
                np.hstack((rx, by)),
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
            ps = np.hstack(
                (
                    np.vstack((lx, lx, rx, rx)),
                    np.vstack((by, ty, ty, by)),
                    np.ones([4 * Nc, 1]),
                )
            )
            M = np.vstack((np.array(self.transform.matrix), np.array([[0, 0, 1]])))
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


# A single character and its style
class tchar:
    def __init__(self, c, fs, sf, prop, sty, nsty, loc):
        self.c = c
        self.fs = fs
        # nominal font size
        self.sf = sf
        # how much it is scaled to get to the actual width
        self.prop = prop
        self.cw = prop.charw
        # actual character width in user units
        self._sty = sty
        # actual style
        self.nsty = nsty
        # normalized style
        self.loc = loc
        # true location: [parent, 'text' or 'tail', index]
        self.ch = prop.caph
        # cap height (height of flat capitals like T)
        # self.dr = dr;     # descender (length of p/q descender))
        self.sw = prop.spacew
        # space width for style
        self.ln = None
        # my line (to be assigned)
        self.w = None
        # my word (to be assigned)
        self.type = None
        # 'normal','super', or 'sub' (to be assigned)
        self.ofs = fs
        # original character width (never changed, even if character is updated later)
        self._dx = 0
        # get later
        self._dy = 0
        # get later
        self.deltanum = None
        # get later
        self.dkerns = prop.dkerns
        # self.pending_style = None; # assign later (maybe)
        self.parsed_pts_t = None
        self.parsed_pts_ut = None
        # for merging later
        self._lsp = self._bshft = None
        # letter spacing

    # def __copy__(self):
    #     ret = tchar(self.c,self.fs,self.sf,self.prop,self.sty,self.nsty,self.loc)
    #     for a,v in self.__dict__.items():
    #         ret.__dict__[a]=v
    #     ret.loc = copy(self.loc)
    #     return ret

    @property
    def dx(self):
        return self._dx

    @dx.setter
    def dx(self, di):
        if self._dx != di:
            self._dx = di
            if self.w is not None:
                self.w.dxeff = None
                # invalidate
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
        return self._sty

    @sty.setter
    def sty(self, si):
        self._sty = si
        self.lsp = None
        self.bshft = None

    anchorfrac = property(lambda self: get_anchorfrac(self.ln.anchor))

    @property
    def lsp(self):
        if self._lsp is None:
            styv = self.sty
            if "letter-spacing" in styv:
                lspv = styv.get("letter-spacing")
                if "em" in lspv:  # em is basically the font size
                    fs2 = styv.get("font-size")
                    if fs2 is None:
                        fs2 = "12px"
                    lspv = float(lspv.strip("em")) * dh.implicitpx(fs2)
                else:
                    lspv = dh.implicitpx(lspv)
            else:
                lspv = 0
            self._lsp = lspv
        return self._lsp

    @lsp.setter
    def lsp(self, si):
        if si != self._lsp:
            self._lsp = si
            if self.w is not None:
                self.w.lsp = None

    @property
    def bshft(self):
        if self._bshft is None:
            styv = self.sty
            if "baseline-shift" in styv:
                cel = self.loc.pel
                bshft = 0
                while cel != self.ln.pt.textel:  # sum all ancestor baseline-shifts
                    if "baseline-shift" in cel.cstyle:
                        bshft += tchar.get_baseline(cel.cstyle, cel.getparent())
                    cel = cel.getparent()
            else:
                bshft = 0
            self._bshft = bshft
        return self._bshft

    @bshft.setter
    def bshft(self, si):
        if si != self._bshft:
            self._bshft = si
            # if self.w is not None:
            #     self.w.bshft = None

    # @property
    # def actual_font(self):
    #     myfont = self.sty.get('font-family')
    #     if myfont is not None:
    #         myfont = ",".join([v.strip().strip("'") for v in myfont.split(",")])
    #     if myfont is None or myfont=='' or myfont=='sans-serif':
    #         ret = 'sans-serif'
    #     else:
    #         # dh.idebug(self.ln.pt.ctable.docfonts)
    #         # dh.idebug(myfont)
    #         ret = self.ln.pt.ctable.docfonts[myfont]
    #     return ret
            

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
            bshft = dh.implicitpx(bshft)
        return bshft

    def delc(self):
        # Deletes character from document (and from my word/line)
        # Deleting a character causes the word to move if it's center- or right-justified. Adjust position to fix
        myi = self.ln.cs.index(self)  # index in line
        
        # Differential kerning affect on character width
        dko1 = dko2 = dkn = 0
        if myi<len(self.ln.cs)-1:
            dko2 = self.dkerns.get((self.ln.cs[myi].c,self.ln.cs[myi+1].c),0.0) # old from right
            if myi > 0:
                dkn = self.dkerns.get((self.ln.cs[myi-1].c,self.ln.cs[myi+1].c),0.0) # new
        if myi>0:
            dko1 = self.dkerns.get((self.ln.cs[myi-1].c,self.ln.cs[myi].c),0.0) # old from left
        dk = dko1+dko2-dkn
        
        cwo = self.cw + dk + self.dx + self.lsp * (self.w.cs[0] != self)
        if self.w.unrenderedspace and self.w.cs[-1] == self:
            if len(self.w.cs) > 1 and self.w.cs[-2].c != " ":
                cwo = dk
                # deletion will not affect position
                # weirdly dkerning from unrendered spaces still counts

        if self == self.w.cs[0]:  # from beginning of line
            deltax = (self.anchorfrac - 1) * cwo / self.sf
        else:  # assume end of line
            deltax = self.anchorfrac * cwo / self.sf
        if deltax != 0:
            newx = self.ln.x
            nnii = [ii for ii in range(len(self.ln.x)) if self.ln.x[ii] is not None]
            # non-None
            newx[nnii[self.ln.ws.index(self.w)]] -= deltax
            self.ln.change_pos(newx)

        # Delete from document
        if self.loc.tt == "text":
            self.loc.el.text = del2(self.loc.el.text, self.loc.ind)
        else:
            self.loc.el.tail = del2(self.loc.el.tail, self.loc.ind)

        if len(self.ln.x) > 1:
            if myi < len(self.ln.x):
                if (
                    myi < len(self.ln.x) - 1
                    and self.ln.x[myi] is not None
                    and self.ln.x[myi + 1] is None
                ):
                    newx = del2(
                        self.ln.x, myi + 1
                    )  # next x is None, delete that instead
                elif myi == len(self.ln.x) - 1 and len(self.ln.cs) > len(self.ln.x):
                    newx = self.ln.x
                    # last x, characters still follow
                else:
                    newx = del2(self.ln.x, myi)
                newx = newx[: len(self.ln.cs) - 1]
                # we haven't deleted the char yet, so make it len-1 long
                self.ln.change_pos(newx)

        # Delete from line
        for ii in range(
            myi + 1, len(self.ln.cs)
        ):  # need to decrement index of subsequent objects with the same parent
            ca = self.ln.cs[ii]
            if ca.loc.tt == self.loc.tt and ca.loc.el == self.loc.el:
                ca.loc.ind -= 1
            if ca.w is not None:
                i2 = ca.w.cs.index(ca)
                ca.w.iis[i2] -= 1
        self.ln.cs = del2(self.ln.cs, myi)
        if len(self.ln.cs) == 0:  # line now empty, can delete
            self.ln.dell()
        # self.ln = None

        # Remove from word
        myi = self.w.cs.index(self)
        self.w.removec(myi)

        # Update the dx/dy value in the ParsedText
        self.ln.pt.Update_Delta()

    def add_style(self, sty):
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
            pi = (gp.getchildren()).index(prt)
            gp.insert(pi + 1, t)
            # after the parent

            t.tail = tafter

        # dh.idebug([v.get_id() for v in dh.descendants2(self.ln.pt.textel)])
        # dh.idebug([v.get_id() for v in self.ln.pt.textds])
        textd = self.ln.pt.textds
        # update the descendants list
        textd.insert(textd.index(prt) + 1, t)

        myi = self.ln.cs.index(self)
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
            if a not in sty:
                sty[a] = dh.default_style_atts[a]
                # dh.idebug([t.get_id2(),a,sty])

        t.cstyle = sty

        self.sty = sty
        self.lsp = None
        self.bshft = None

    def makesubsuper(self, sz=65):
        if self.type == "super":
            sty = "font-size:" + str(sz) + "%;baseline-shift:super"
        else:  # sub
            sty = "font-size:" + str(sz) + "%;baseline-shift:sub"
        self.add_style(sty)

    # def applypending(self):
    #     self.add_style(self.pending_style);
    #     self.pending_style = None

    # def interp_pts(self):
    #     """  Interpolate the pts of a word to get a specific character's pts"""
    #     myi = self.w.cs.index(self)
    #     cput = self.w.cpts_ut;
    #     ret_pts_ut = [v2ds(cput[0][myi][0],cput[0][myi][1]),\
    #                   v2ds(cput[1][myi][0],cput[1][myi][1]),\
    #                   v2ds(cput[2][myi][0],cput[2][myi][1]),\
    #                   v2ds(cput[3][myi][0],cput[3][myi][1])]

    #     cpt = self.w.cpts_t;
    #     ret_pts_t = [v2ds(cpt[0][myi][0],cpt[0][myi][1]),\
    #                  v2ds(cpt[1][myi][0],cpt[1][myi][1]),\
    #                  v2ds(cpt[2][myi][0],cpt[2][myi][1]),\
    #                  v2ds(cpt[3][myi][0],cpt[3][myi][1])]

    #     return ret_pts_ut, ret_pts_t

    @property
    def pts_ut(self):
        """  Interpolate the pts of a word to get a specific character's pts"""
        myi = self.w.cs.index(self)
        cput = self.w.cpts_ut
        ret_pts_ut = [
            v2ds(cput[0][myi][0], cput[0][myi][1]),
            v2ds(cput[1][myi][0], cput[1][myi][1]),
            v2ds(cput[2][myi][0], cput[2][myi][1]),
            v2ds(cput[3][myi][0], cput[3][myi][1]),
        ]
        return ret_pts_ut

    @property
    def pts_t(self):
        myi = self.w.cs.index(self)
        cpt = self.w.cpts_t
        ret_pts_t = [
            v2ds(cpt[0][myi][0], cpt[0][myi][1]),
            v2ds(cpt[1][myi][0], cpt[1][myi][1]),
            v2ds(cpt[2][myi][0], cpt[2][myi][1]),
            v2ds(cpt[3][myi][0], cpt[3][myi][1]),
        ]
        return ret_pts_t


    @property
    def pts_ut_ink(self):
        put = self.pts_ut;
        nw = self.prop.inkbb[2]/self.sf;
        nh = self.prop.inkbb[3]/self.sf;
        nx = put[0].x+self.prop.inkbb[0]/self.sf;
        ny = put[0].y+self.prop.inkbb[1]/self.sf+nh;
        return [v2ds(nx,ny),v2ds(nx,ny-nh),v2ds(nx+nw,ny-nh),v2ds(nx+nw,ny)]

    # @property
    # def parsed_pts_ut(self):
    #     if self._parsed_pts_ut is None:
    #         self._parsed_pts_ut = self.pts_ut
    #     return self._parsed_pts_ut
    # @parsed_pts_ut.setter
    # def parsed_pts_ut(self,pi):
    #     self._parsed_pts_ut = pi;
    # @property
    # def parsed_pts_t(self):
    #     if self._parsed_pts_t is None:
    #         self._parsed_pts_t = self.pts_t
    #     return self._parsed_pts_t
    # @parsed_pts_t.setter
    # def parsed_pts_t(self,pi):
    #     self._parsed_pts_t = pi;

    # def changex(self,newx):
    #     self.ln.x[self.ln.cs.index(self)] = newx
    #     if self.ln.x==[]: self.ln.xsrc.set('x',None)
    #     else:             self.ln.xsrc.set('x',' '.join([str(v) for v in self.ln.x]))


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
class cprop:
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
        self.dkerns = (
            dkerns  # table of how much extra width a preceding character adds to me
        )
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
    def __init__(self, el, tt, ind):
        self.el = el
        # the element it belongs to
        self.tt = tt
        # 'text' or 'tail'
        self.ind = ind
        # its index

        # tmp = el;
        # if isinstance(tmp.getparent(),(TextElement,Tspan)):
        #     tmp = tmp.getparent()
        # self.textel = tmp; # parent TextElement

        if self.tt == "text":
            self.pel = self.el  # parent element (different for tails)
        else:
            self.pel = self.el.getparent()

    def __eq__(self, other):
        return self.el == other.el and self.tt == other.tt and self.ind == other.ind


# A class representing the properties of a collection of characters
class Character_Table:
    def __init__(self, els):
        self.fonttestchars = 'pIaA10mMvo' # don't need that many, just to figure out which fonts we have
        self.ctable  = self.meas_char_ws(els)

    def get_prop(self, char, sty):
        if sty in list(self.ctable.keys()):
            return self.ctable[sty][char]
        else:
            dh.debug("No style matches!")
            dh.debug("Character: " + char)
            dh.debug("Style: " + sty)
            dh.debug("Existing styles: " + str(list(self.ctable.keys())))

    def generate_character_table(self, els):
        ctable = dict()
        pctable = dict()         # a dictionary of preceding characters in the same style
        
        atxt = [];
        asty = [];
        for el in els:
            ds, pts, cd, pd = dh.descendants2(el, True)
            Nd = len(ds)
            text = [d.text for d in ds]
            ptail = [[tel.tail for tel in pt] for pt in pts]  # preceding tails
            if len(ptail) > 0 and len(ptail[-1]) > 0:
                ptail[-1][-1] = None
                # do not count el's tail

            for di, tt in ttiterator(Nd):
                if tt == 0:
                    txts = ptail[di]
                    tels = pts[di]
                else:
                    txts = [text[di]]
                    tels = [ds[di]]
                for ii in range(len(tels)):
                    tel = tels[ii]
                    txt = txts[ii]
                    if txt is not None and len(txt) > 0:
                        sel = tel
                        if tt == 0:
                            sel = pd[tel]
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

        ct2 = dict(); bareids = [];
        for s in ct:
            ct2[s] = dict()
            for ii in range(len(ct[s])):
                myc = ct[s][ii]
                t  = Make_Character(prefix + myc + suffix, s)
                tb = Make_Character(         myc         , s);
                bareids.append(tb)
                dkern = dict()
                if KERN_TABLE:
                    for jj in range(len(ct[s])):
                        pc = ct[s][jj]
                        if myc in pct[s] and pc in pct[s][myc]:
                            t2 = Make_Character(prefix + pc+myc + suffix, s)
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
            # dh.idebug(ct)  
            for sty in ct:
                joinch = ' ';
                mystrs = [v[0] for k,v in nbb.items() if v[1]==sty]
                myids  = [k    for k,v in nbb.items() if v[1]==sty]
                
                success,fm = pr.Set_Text_Style(sty)
                if not(success):
                    return self.meas_char_ws(els, forcecommand=True)
                pr.Render_Text(joinch.join(mystrs))
                exts,nu = pr.Get_Character_Extents(fm[1])
                ws = [v[0][2] for v in exts]
                if nu>0:
                    # dh.idebug(nu)
                    return self.meas_char_ws(els, forcecommand=True)
                
                cnt=0; x=0;
                for ii in range(len(mystrs)):
                    s = slice(cnt,cnt+len(mystrs[ii]))
                    w = sum(ws[s]);
                        
                    firstch = exts[s][0];
                    (xb,yb,wb,hb) = tuple(firstch[2]);
                    if myids[ii] not in bareids:
                        xb = x; wb = w; # use logical width
                    if mystrs[ii]==prefix+suffix:
                        ycorr = hb+yb
                        
                    nbb[myids[ii]] = [v*TEXTSIZE for v in [xb,yb,wb,hb]]
                    cnt += len(mystrs[ii])+len(joinch);
                    x += w;    
                    
                # Certain Windows fonts do not seem to comply with the Pango spec.
                # The ascent+descent of a font is supposed to match its logical height,
                # but this is not always the case. Correct using the top of the 'I' character.
                for ii in range(len(mystrs)):
                    # if myids[ii] in bareids:
                    nbb[myids[ii]][1] -= ycorr*TEXTSIZE
            

        dkern = dict()
        for s in list(ct.keys()):
            for ii in ct[s].keys():
                ct[s][ii].bb = bbox(nbb[ct[s][ii].strid])
                if KERN_TABLE:
                    precwidth = dict()
                    for jj in ct[s][ii].dkern.keys():
                        precwidth[jj] = bbox(nbb[ct[s][ii].dkern[jj]]).w
                        # width including the preceding character and extra kerning
                    ct[s][ii].precwidth = precwidth

            if KERN_TABLE:
                dkern[s] = dict()
                for ii in ct[s].keys():
                    mcw = ct[s][ii].bb.w  - ct[s][blnk].bb.w # my character width
                    for jj in ct[s][ii].precwidth.keys():
                        # myi = mycs.index(jj);
                        pcw = ct[s][jj].bb.w - ct[s][blnk].bb.w          # preceding char width
                        bcw = ct[s][ii].precwidth[jj] - ct[s][blnk].bb.w  # both char widths
                        dkern[s][jj, ct[s][ii].strval] = bcw - pcw - mcw   # preceding char, then next char

        for s in list(ct.keys()):
            blnkwd = ct[s][blnk].bb.w;
            sw = ct[s][' '].bb.w - blnkwd      # space width
            ch = ct[s][blnk].bb.h          # cap height
            dr =  ct[s][pI].bb.y2          # descender
            for ii in ct[s].keys():
                cw = ct[s][ii].bb.w - blnkwd # character width (full, including extra space on each side)
                
                
                if ct[s][ii].bareid in nbb:
                    inkbb = nbb[ct[s][ii].bareid]
                else:
                    inkbb = [ct[s][ii].bb.x1,ct[s][ii].bb.y1,0,0] # whitespace: make zero-width
                dkernscl = dict()
                if KERN_TABLE:
                    for k in dkern[s].keys():
                        dkernscl[k] = dkern[s][k]/TEXTSIZE
                ct[s][ii] = cprop(
                    ct[s][ii].strval,
                    cw/TEXTSIZE,
                    sw/TEXTSIZE,
                    ch/TEXTSIZE,
                    dr/TEXTSIZE,
                    dkernscl, [v/TEXTSIZE for v in inkbb]
                )
                # dh.idebug((cw/TEXTSIZE,[v/TEXTSIZE for v in inkbb]))
        # dh.idebug(nbb)
        return ct #, nbb

    # For generating test characters, we want to normalize the style so that we don't waste time
    # generating a bunch of identical characters whose font-sizes are different. A style is generated
    # with a single font-size, and only with presentation attributes that affect character shape.
    textshapeatt = [
        "font-family",
        "font-size-adjust",
        "font-stretch",
        "font-style",
        "font-variant",
        "font-weight",
        "text-decoration",
        "text-rendering",
        "font-size",
    ]
    # 'stroke','stroke-width' do not affect kerning at all
    @staticmethod
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
        
        sty2 = ";".join(
            ["{0}:{1}".format(*seg) for seg in sty2.items()]
        )  # from Style to_str
        return sty2


# Recursively delete empty elements
# Tspans are deleted if they're totally empty, TextElements are deleted if they contain only whitespace
def deleteempty(el):
    for k in el.getchildren():
        deleteempty(k)
    txt = el.text
    tail = el.tail
    if (
        (txt is None or len((txt)) == 0)
        and (tail is None or len((tail)) == 0)
        and len(el.getchildren()) == 0
    ):
        el.delete2()
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
            # delete any text elements that are just white space


# An iterator for crawling through a text descendant tree
# Returns the current descendant index and tt (0 for tail, 1 for text)
class ttiterator:
    def __init__(self, Nd):
        self.Nd = Nd

    def __iter__(self):
        self.di = 0
        self.tt = 0
        return self

    def __next__(self):
        if self.tt == 1:
            self.di += 1
            self.tt = 0
        else:
            self.tt = 1
        if self.di == self.Nd and self.tt == 1:
            raise StopIteration
        else:
            return self.di, self.tt


def maxnone(xi):
    if len(xi) > 0:
        return max(xi)
    else:
        return None


def noneid(el):
    if el is None:
        return None
    else:
        return el.get("id")