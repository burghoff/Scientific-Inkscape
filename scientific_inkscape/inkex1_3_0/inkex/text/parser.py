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


"""
text.parser module parses text in a document according to the way Inkscape
handles it. In short, every TextElement or FlowRoot is parsed into a ParsedText.
Each ParsedText contains a collection of tlines, representing one line of text.
Each TLine contains a collection of tchars, representing a single character.
Characters are also grouped into tchunks, which represent chunks of characters
sharing an anchor (usually from manually-kerned text).

These functions allow text metrics and bounding boxes to be calculated without
binary calls to Inkscape. It can calculate both the ink bounding box (i.e., where
characters' ink is) as well as the extent bounding box (i.e, its logical location).
The extent of a character is defined as extending between cursor positions in the
x-direction and between the baseline and capital height in the y-direction.

Some examples:
- el.parsed_text.get_full_inkbbox(): gets the untransformed bounding box of the
  whole element
- el.parsed_text.get_char_extents(): gets all characters' untransformed extents
- el.parse_text.lns[0].chrs[0].pts_ut: the untransformed points of the extent of the
  first character of the first line
- el.parse_text.lns[0].chrs[0].pts_t : the transformed points of the extent of the
  first character of the first line

To check if things are working properly, you can run the make_highlights() function,
which draws rectangles that tell you where the extents / bboxes are. For example,
- el.parsed_text.make_highlights('char')    : shows the extent of each character
- el.parsed_text.make_highlights('fullink') : shows the bbox of the whole element
"""

import itertools
import math
from copy import copy
import threading
import lxml
import numpy as np
import inkex
from inkex import (
    TextElement,
    Tspan,
    Transform,
    Style,
    FlowRoot,
    FlowRegion,
    FlowPara,
    FlowSpan,
)
from inkex.text.utils import (
    uniquetol,
    composed_width,
    composed_lineheight,
    default_style_atts,
    isrectangle,
    ipx,
    bbox,
)
from inkex.text.font_properties import (
    PangoRenderer,
    HASPANGO,
    fcfg,
    font_style,
    true_style,
)
from inkex.utils import debug

DIFF_ADVANCES = True  # generate a differential advances table for each font?
TEXTSIZE = 100  # size of rendered text
DEPATHOLOGIZE = True  # clean up pathological atts not normally made by Inkscape

EBget = lxml.etree.ElementBase.get
EBset = lxml.etree.ElementBase.set

TEtag, TStag, FRtag = TextElement.ctag, Tspan.ctag, FlowRoot.ctag
TEFRtags = {TEtag, FRtag}
TEtags = {TEtag, TStag}
FRtags = {FRtag, FlowRegion.ctag, FlowPara.ctag, FlowSpan.ctag}

LOCK = threading.Lock()


class ParsedTextList(list):
    """
    A list of parsed text whose coordinates are computed
    vectorially using numpy. Normally they are calculated as they are needed,
    but this is inefficient when dealing with thousands of manually-kerned
    characters (e.g., from PDFs).
    """

    def __init__(self, els):
        """Initializes ParsedTextList with a list of elements."""
        super().__init__([el.parsed_text for el in els])

    def precalcs(self):
        """
        Calculate parsed_bb, parsed_pts_ut, parsed_pts_t for all chunks
        simultaneously
        """
        tws = [chk for ptxt in self for line in ptxt.lns for chk in line.chks]
        nchrs = sum(chk.ncs for chk in tws)

        # Preallocate arrays
        dadv, cwd, dxeff, dy, bshft, caph, unsp, anfr = np.zeros(
            (8, nchrs), dtype=float
        )
        fidx, lidx, widx = np.zeros((3, nchrs)).astype(int)

        unsp = np.array([chk.unrenderedspace for chk in tws], dtype=float)
        anfr = np.array([chk.line.anchfrac for chk in tws], dtype=float)
        chkx = np.array([chk.x for chk in tws], dtype=float)
        chky = np.array([chk.y for chk in tws], dtype=float)
        m00, m01, m02, m10, m11, m12 = (
            np.array([chk.transform.matrix[i][j] for chk in tws], dtype=float)
            for i in (0, 1)
            for j in (0, 1, 2)
        )
        lx2, rx2, by2, ty2 = np.zeros((4, len(tws))).astype(float)

        # Collect values for dadv, cwd, dxeff, dy, bshft, and caph
        idx = 0
        for j, chk in enumerate(tws):
            if DIFF_ADVANCES:
                for i in range(1, chk.ncs):
                    dadv[idx + i] = chk.chrs[i].dadvs(chk.chrs[i - 1].c, chk.chrs[i].c)*(chk.dxeff[i]==0)

            for i in range(chk.ncs):
                cwd[idx + i] = chk.cwd[i]
                dxeff[idx + i] = chk.dxeff[i]
                dy[idx + i] = chk.dy[i]
                bshft[idx + i] = chk.bshft[i]
                caph[idx + i] = chk.caph[i]
            fidx[idx : idx + chk.ncs] = idx
            lidx[idx : idx + chk.ncs] = idx + chk.ncs - 1
            widx[idx : idx + chk.ncs] = j
            idx += chk.ncs

        # Calculate wds, cstop, and cstrt
        wds = cwd + dxeff + dadv
        cstop = np.array(list(itertools.accumulate(wds)), dtype=float)
        cstop += wds[fidx] - cstop[fidx]
        cstrt = cstop - cwd

        # # Calculate adyl
        adyl = np.array(list(itertools.accumulate(dy)), dtype=float)
        adyl += dy[fidx] - adyl[fidx]

        # Calculate chkw, offx, lftx, and rgtx
        offx = -anfr[widx] * (cstop[lidx] - unsp[widx] * cwd[lidx])
        lftx = chkx[widx] + cstrt + offx
        rgtx = chkx[widx] + cstop + offx
        btmy = chky[widx] + adyl - bshft
        topy = btmy - caph

        idx_ncs = np.cumsum([0] + [chk.ncs for chk in tws])
        starts = idx_ncs[:-1]
        subtract_ufunc = np.frompyfunc(lambda a, b: a - b, 2, 1)
        lx_minus_dxeff = subtract_ufunc(lftx, dxeff)
        lx2 = np.minimum.reduceat(lx_minus_dxeff, starts)
        rx2 = lx2 + cstop[idx_ncs[1:] - 1]
        by2 = np.maximum.reduceat(btmy, starts)
        ty2 = np.minimum.reduceat(topy, starts)

        cpts_ut = [
            np.hstack((lftx[:, np.newaxis], btmy[:, np.newaxis])),
            np.hstack((lftx[:, np.newaxis], topy[:, np.newaxis])),
            np.hstack((rgtx[:, np.newaxis], topy[:, np.newaxis])),
            np.hstack((rgtx[:, np.newaxis], btmy[:, np.newaxis])),
        ]
        mat = ((m00[widx], m01[widx], m02[widx]), (m10[widx], m11[widx], m12[widx]))
        cpts_t = [
            np.vstack(vmult(mat, lftx, btmy)).T,
            np.vstack(vmult(mat, lftx, topy)).T,
            np.vstack(vmult(mat, rgtx, topy)).T,
            np.vstack(vmult(mat, rgtx, btmy)).T,
        ]
        pts_ut = [
            np.vstack((lx2, by2)),
            np.vstack((lx2, ty2)),
            np.vstack((rx2, ty2)),
            np.vstack((rx2, by2)),
        ]
        mat = ((m00, m01, m02), (m10, m11, m12))
        pts_t = [
            np.vstack(vmult(mat, lx2, by2)),
            np.vstack(vmult(mat, lx2, ty2)),
            np.vstack(vmult(mat, rx2, ty2)),
            np.vstack(vmult(mat, rx2, by2)),
        ]

        # pylint:disable=protected-access
        # Split outputs into lists of column vectors
        # maxerr = float('-inf')
        for i, chk in enumerate(tws):
            # Extract the slices of the relevant arrays for this TChunk
            lxw = lftx[idx_ncs[i] : idx_ncs[i + 1], np.newaxis]
            rxw = rgtx[idx_ncs[i] : idx_ncs[i + 1], np.newaxis]
            byw = btmy[idx_ncs[i] : idx_ncs[i + 1], np.newaxis]
            tyw = topy[idx_ncs[i] : idx_ncs[i + 1], np.newaxis]

            chk._charpos = (lxw, rxw, byw, tyw, lx2[i], rx2[i], by2[i], ty2[i])
            chk._cpts_ut = [cpv[idx_ncs[i] : idx_ncs[i + 1], :] for cpv in cpts_ut]
            chk._cpts_t = [cpv[idx_ncs[i] : idx_ncs[i + 1], :] for cpv in cpts_t]
            chk._pts_ut = [
                (float(pts_ut[0][0][i]), float(pts_ut[0][1][i])),
                (float(pts_ut[1][0][i]), float(pts_ut[1][1][i])),
                (float(pts_ut[2][0][i]), float(pts_ut[2][1][i])),
                (float(pts_ut[3][0][i]), float(pts_ut[3][1][i])),
            ]
            chk._pts_t = [
                (float(pts_t[0][0][i]), float(pts_t[0][1][i])),
                (float(pts_t[1][0][i]), float(pts_t[1][1][i])),
                (float(pts_t[2][0][i]), float(pts_t[2][1][i])),
                (float(pts_t[3][0][i]), float(pts_t[3][1][i])),
            ]

            for j, c in enumerate(chk.chrs):
                c.parsed_pts_ut = [
                    (float(chk._cpts_ut[0][j][0]), float(chk._cpts_ut[0][j][1])),
                    (float(chk._cpts_ut[1][j][0]), float(chk._cpts_ut[1][j][1])),
                    (float(chk._cpts_ut[2][j][0]), float(chk._cpts_ut[2][j][1])),
                    (float(chk._cpts_ut[3][j][0]), float(chk._cpts_ut[3][j][1])),
                ]
                c.parsed_pts_t = [
                    (float(chk._cpts_t[0][j][0]), float(chk._cpts_t[0][j][1])),
                    (float(chk._cpts_t[1][j][0]), float(chk._cpts_t[1][j][1])),
                    (float(chk._cpts_t[2][j][0]), float(chk._cpts_t[2][j][1])),
                    (float(chk._cpts_t[3][j][0]), float(chk._cpts_t[3][j][1])),
                ]
        # pylint:enable=protected-access
    
    def make_next_chain(self):
        for pt in self:
            pt.make_next_chain()


def vmult(mat, x, y):
    """Multiplies mat times (x;y) in a way compatible with vectorization"""
    return (
        mat[0][0] * x + mat[0][1] * y + mat[0][2],
        mat[1][0] * x + mat[1][1] * y + mat[1][2],
    )


def vmultinv(mat, x, y):
    """Performs inverse matrix multiplication with vectors."""
    det = mat[0][0] * mat[1][1] - mat[0][1] * mat[1][0]
    inv_det = 1 / det
    sxv = x - mat[0][2]
    syv = y - mat[1][2]
    return (
        (mat[1][1] * sxv - mat[0][1] * syv) * inv_det,
        (mat[0][0] * syv - mat[1][0] * sxv) * inv_det,
    )


class ParsedText:
    """A text element that has been parsed into a list of lines"""

    def __init__(self, elem, ctable):
        """Initializes ParsedText with an element and a character table."""
        self.ctable = ctable
        self.textel = elem

        sty = elem.cspecified_style
        self.isflow = (
            elem.tag == FRtag
            or (elem.croot is not None and sty.get_link("shape-inside", elem.croot) is not None)
            or ipx(sty.get("inline-size"))
        )
        self._tree = None
        self.dchange, self.writtendx, self.writtendy = [None] * 3
        self.achange = False
        if DEPATHOLOGIZE:
            remove_position_overflows(elem)
        if self.isflow:
            self.parse_lines_flow()
        else:
            self.parse_lines()
        self.finish_lines()

        tlvllns = [
            line for line in self.lns if line.tlvlno is not None and line.tlvlno > 0
        ]
        # top-level lines after 1st
        self.isinkscape = (
            all(line.sprl for line in tlvllns)
            and len(tlvllns) > 0
            and all(
                line.style.get("-inkscape-font-specification") is not None
                for line in self.lns
            )
        )
        # probably made in Inkscape
        self.ismlinkscape = self.isinkscape and len(self.lns) > 1
        # multi-line Inkscape

    def duplicate(self):
        """Duplicates a PT and its text without reparsing"""
        ret = copy(self)
        ret.textel = self.textel.duplicate()
        ret.tree = None
        cmemo = dict(zip(self.tree.dds, ret.tree.dds))

        ret.lns = []
        for line in self.lns:
            if len(line.chrs) == 0:
                continue
            ret_ln = line.copy(cmemo)
            ret_ln.ptxt = ret
            ret.lns.append(ret_ln)

        # nextw et al. could be from any line, update after copying
        for ret_ln in ret.lns:
            for ret_w in ret_ln.chks:
                ret_w.nextw = cmemo.get(ret_w.nextw)
                ret_w.prevw = cmemo.get(ret_w.prevw)
                ret_w.prevsametspan = cmemo.get(ret_w.prevsametspan)
        return ret

    def txt(self):
        """Returns the text content of the parsed lines."""
        return [line.txt() for line in self.lns]

    def reparse(self):
        """Reparses the text element."""
        self.__init__(self.textel, self.ctable)

    @property
    def chrs(self):
        """Returns a list of characters in the parsed lines."""
        return [c for line in self.lns for c in line.chrs]

    def parse_lines(self, srcsonly=False):
        """
        Every text element in an SVG can be thought of as a group of lines.
        A line is a collection of text that gets its position from a single
        source element. This position may be directly set, continued from a
        previous line, or inherited from a previous line.
        """
        elem = self.textel
        # First we get the tree structure of the text and do all our gets
        dds, pts, pdict = self.tree.dds, self.tree.ptails, self.tree.pdict

        numd = len(dds)
        kids = list(elem)
        text = [ddv.text for ddv in dds]
        ptail = [[tel.tail for tel in ptv] for ptv in pts]  # preceding tails

        # Next we find the top-level sodipodi:role lines
        xvs = [ParsedText.get_xy(ddv, "x") for ddv in dds]
        yvs = [ParsedText.get_xy(ddv, "y") for ddv in dds]
        dxvs = [ParsedText.get_xy(ddv, "dx") for ddv in dds]
        dyvs = [ParsedText.get_xy(ddv, "dy") for ddv in dds]
        nsprl = {ddv:ddv.get("sodipodi:role")=='line' for ddv in dds}

        # Find effective sprls (ones that are not disabled)
        esprl = [False]*len(dds)
        for i, ddv in enumerate(dds):
            esprl[i] = nsprl[ddv] and len(xvs[i]) == 1 and len(yvs[i]) == 1 and dds[i] in kids
            
            # If I don't have text and any descendants have position, disables spr:l
            if esprl[i] and (text[i] == "" or text[i] is None):
                dstop = [j for j in range(len(pts)) if dds[i] in pts[j]][0]
                # should exist
                for ddi in range(i + 1, dstop):
                    if xvs[ddi][0] is not None or yvs[ddi][0] is not None:
                        if text[ddi] is not None and text[ddi] != "":
                            esprl[i] = False
                            
        if DEPATHOLOGIZE and not srcsonly:
            # Prune any sodipodi:roles that are inactive
            for ii, d in enumerate(dds):
                if not esprl[ii] and nsprl[d]:
                    d.set('sodipodi:role',None)
                    nsprl[d] = False

        # Figure out which effective sprls are top-level
        types = [None] * len(dds)
        for i,ddv in enumerate(dds):
            if not esprl[i]:
                types[i] = NORMAL
            elif len(ptail[i]) > 0 and ptail[i][-1] is not None:
                types[i] = PRECEDEDSPRL
            elif dds[i] == kids[0] and text[0] is not None:  # and len(text[0])>0:
                # 2022.08.17: I am not sure if the len(text[0])==0 condition
                # should be included. Inkscape prunes text='', so not relevant
                # most of the time. It does seem to make a difference though.
                types[i] = PRECEDEDSPRL
            else:
                types[i] = TLVLSPRL

        # Position has a property of bidirectional inheritance. A tspan can inherit
        # position from its parent or its descendant unless there is text in between.
        # Down-inheritance requires that text be present
        # Aborts if a sprl is encountered
        def inherits_from(iin):
            jmax = iin
            while (
                jmax < numd - 1
                and text[jmax] in ["", None]
                and pdict[dds[jmax + 1]] == dds[jmax]
                and not (esprl[jmax + 1])
            ):
                jmax += 1
            if jmax < numd - 1 and text[jmax] in ["", None]:
                jmax = iin

            jmin = iin
            while (
                jmin > 0
                and text[jmin - 1] in ["", None]
                and dds[jmin - 1] == pdict[dds[jmin]]
                and not (esprl[jmin - 1])
            ):
                jmin -= 1
            return jmin, jmax  # includes endpoints

        def inherit_none(iin, xyt):
            if xyt[iin][0] is None:
                imin, imax = inherits_from(iin)
                vld = [i for i in range(imin, imax + 1) if xyt[i][0] is not None]
                if len(vld) > 0:
                    if any(i <= iin for i in vld):
                        vld = [i for i in vld if i <= iin]
                        # inherit up if possible
                    dist = [abs(i - iin) for i in vld]
                    j = [vld[i] for i in range(len(vld)) if dist[i] == min(dist)][0]
                    return xyt[j], dds[j]
            return xyt[iin], dds[iin]

        # For positions that are None, inherit from ancestor/descendants if possible
        ixs, iys = xvs[:], yvs[:]
        xsrcs, ysrcs = dds[:], dds[:]

        for i in [i for i in range(0, len(dds)) if ixs[i][0] is None]:
            ixs[i], xsrcs[i] = inherit_none(i, xvs)
        for i in [i for i in range(0, len(dds)) if iys[i][0] is None]:
            iys[i], ysrcs[i] = inherit_none(i, yvs)

        if ixs[0][0] is None:
            ixs[0] = [0]  # at least the parent needs a position
        if iys[0][0] is None:
            iys[0] = [0]

        # Finally, walk the text tree generating lines
        lns = []
        if not srcsonly:
            self.lns = []
        sprl_inherits = None
        for ddi, typ, tel, sel, txt in self.tree.dgenerator():
            newsprl = typ == TYP_TEXT and types[ddi] == TLVLSPRL
            
            if (txt is not None and len(txt) > 0) or newsprl:
                sty = sel.cspecified_style
                ctf = sel.ccomposed_transform
                fsz, scf, utfs = composed_width(sel, "font-size")

                if newsprl:
                    lht = max(
                        composed_lineheight(sel), composed_lineheight(sel.getparent())
                    )

                # Make a new line if we're sprl or if we have a new x or y
                makeline = len(lns) == 0
                makeline |= typ == TYP_TEXT and (
                    newsprl
                    or (
                        types[ddi] == NORMAL
                        and (ixs[ddi][0] is not None or iys[ddi][0] is not None)
                    )
                )
                if makeline:
                    edi = ddi
                    if typ == TYP_TAIL:
                        edi = dds.index(sel)
                    xvl = ixs[edi]
                    xsrc = xsrcs[edi]
                    yvl = iys[edi]
                    ysrc = ysrcs[edi]
                    if newsprl:
                        if len(lns) == 0:
                            xvl = [ixs[0][0]]
                            xsrc = xsrcs[0]
                            yvl = [iys[0][0]]
                            ysrc = ysrcs[0]
                        else:
                            xvl = [sprl_inherits.x[0]]
                            xsrc = sprl_inherits.xsrc
                            yvl = [sprl_inherits.y[0] + lht / scf]
                            ysrc = sprl_inherits.ysrc
                        issprl = True
                        continuex = False
                        continuey = False
                    else:
                        continuex = False
                        issprl = False
                        if xvl[0] is None:
                            if len(lns) > 0:
                                xvl = lns[-1].x[:]
                                xsrc = lns[-1].xsrc
                            else:
                                xvl = ixs[0][:]
                                xsrc = xsrcs[0]
                            continuex = True
                        continuey = False
                        if yvl[0] is None:
                            if len(lns) > 0:
                                yvl = lns[-1].y[:]
                                ysrc = lns[-1].ysrc
                            else:
                                yvl = iys[0][:]
                                ysrc = ysrcs[0]
                            continuey = True

                    if srcsonly:  # quit and return srcs of first line
                        return xsrc, ysrc

                    tlvlno = None
                    if ddi < numd and dds[ddi] in kids:
                        tlvlno = kids.index(dds[ddi])
                    elif edi == 0:
                        tlvlno = 0

                    anch = sty.get("text-anchor")
                    if len(lns) > 0 and not nsprl[sel] and edi>0:
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
                    cel = dds[edi]
                    while cel != elem:
                        if nsprl[cel]:
                            sprlabove.append(cel)
                        cel = pdict[cel]

                    lns.append(
                        TLine(
                            self,
                            xvl,
                            yvl,
                            xsrc,
                            ysrc,
                            issprl,
                            sprlabove,
                            anch,
                            ctf,
                            tlvlno,
                            sty,
                            continuex,
                            continuey,
                        )
                    )

                    if newsprl or len(lns) == 1:
                        sprl_inherits = lns[-1]

                fsty = font_style(sty)
                tsty = true_style(fsty)
                if txt is not None:
                    if typ==TYP_TEXT:
                        dxv = dxvs[ddi]
                        dyv = dyvs[ddi]
                        if dxv[0] is None:
                            dxv = [0]*len(txt)
                        else:
                            dxv = dxv + [0]*(len(txt)-len(dxv))
                        if dyv[0] is None:
                            dyv = [0]*len(txt)
                        else:
                            dyv = dyv + [0]*(len(txt)-len(dyv))
                    else:
                        dxv = [0]*len(txt)
                        dyv = [0]*len(txt)
                    
                    
                    for j, c in enumerate(txt):
                        csty = self.font_picker(txt, j, fsty, tsty)
                        prop = self.ctable.get_prop(c, csty)
                        _ = TChar(
                            c,
                            fsz,
                            utfs,
                            prop,
                            sty,
                            csty,
                            CLoc(tel, typ, j),
                            lns[-1], dxv[j], dyv[j]
                        )

                        if j == 0:
                            lsp0 = lns[-1].chrs[-1].lsp
                            bshft0 = lns[-1].chrs[-1].bshft
                        else:
                            lns[-1].chrs[-1].lsp = lsp0
                            lns[-1].chrs[-1].bshft = bshft0
                                
        self.lns = lns

    def finish_lines(self):
        """Finalizes the parsed lines by calculating deltas and chunks."""
        if self.lns is not None:
            self.writtendx = any(c.dx != 0 for c in self.chrs)
            self.writtendy = any(c.dy != 0 for c in self.chrs)

            for line in self.lns:
                line.ptxt = self
                line.parse_chunks()

            for line in reversed(self.lns):
                if len(line.chrs) == 0:
                    self.lns.remove(line)
                    # prune empty lines

    def make_next_chain(self):
        """ For manual kerning removal, assign next and previous chunks """
        yvs = [
            line.y[0] for line in self.lns if line.y is not None and len(line.y) > 0
        ]
        tol = 0.001
        for unqy in uniquetol(yvs, tol):
            samey = [
                self.lns[i]
                for i in range(len(self.lns))
                if abs(yvs[i] - unqy) < tol
            ]
            sameyws = [chk for line in samey for chk in line.chks]
            xvs = [0.5*(chk.pts_ut[0][0] + chk.pts_ut[3][0]) for line in samey for chk in line.chks]
            sws = [
                x for _, x in sorted(zip(xvs, sameyws), key=lambda pair: pair[0])
            ]  # chunks sorted in ascending x
            for i in range(1, len(sws)):
                # Account for space import bug where space has same position as prior char
                if sws[i - 1].txt==' ' and abs(sws[i - 1].pts_ut[0][0]-sws[i].pts_ut[0][0])<.01*sws[i - 1].spw:
                    sws[i-1:i+1] = [sws[i],sws[i-1]]
            for i in range(1, len(sws)):
                sws[i - 1].nextw = sws[i]
                sws[i].prevw = sws[i - 1]
                sws[i].prevsametspan = (
                    sws[i - 1].chrs[-1].loc.sel == sws[i].chrs[0].loc.sel
                )

    def font_picker(self, txt, j, fsty, tsty):
        """Determine what font Inkscape will render a character as"""
        if txt[j] != " ":
            # Most of the time we want the true style of the text. When this is
            # determined by Pango measurement, this practically always matches
            # Inkscape's font selection
            return tsty
        # If the character is a space and the surrounding characters are
        # missing from the true style, Pango will replace the space with a
        # space from the missing characters' font
        lbc = next((txt[i] for i in range(j - 1, -1, -1) if txt[i].strip()), None)
        fac = next((txt[i] for i in range(j + 1, len(txt)) if txt[i].strip()), None)
        if (
            lbc is not None
            and fac is not None
            and self.ctable.cstys[fsty][lbc] == self.ctable.cstys[fsty][fac]
        ):
            return self.ctable.cstys[fsty][lbc]
        if lbc is None and fac is not None:
            return self.ctable.cstys[fsty][fac]
        if fac is None and lbc is not None:
            return self.ctable.cstys[fsty][lbc]
        return tsty
        # Good fonts to check:
        #   MS Outlook : missing most characters, but has a space
        #   Marlett : charset doesn't have a space character, but somehow Pango
        #             is finding one different from the one provided by
        #             fontconfig's font_sort fallback

    def strip_sodipodi_role_line(self):
        """Strip every sodipodi:role line from an element without changing
        positions"""
        if any(ddv.get("sodipodi:role") == "line" for ddv in self.tree.dds):
            # Store old positions
            oxs = [c.pts_ut[0][0] for line in self.lns for c in line.chrs]
            oys = [c.pts_ut[0][1] for line in self.lns for c in line.chrs]
            odxs = [c.dx for line in self.lns for c in line.chrs]
            odys = [c.dy for line in self.lns for c in line.chrs]
            _ = [ddv.set("sodipodi:role", None) for ddv in self.tree.dds]
            
            pput = [c.parsed_pts_ut for line in self.lns for c in line.chrs]
            ppt  = [c.parsed_pts_t  for line in self.lns for c in line.chrs]
            
            deleteempty(self.textel)
            self.reparse()
            ii = 0;
            for line in self.lns:
                for c in line.chrs:
                    c.parsed_pts_ut = pput[ii]
                    c.parsed_pts_t  = ppt[ii]
                    ii += 1

            # Correct the position of the first character
            chrs = [c for line in self.lns for c in line.chrs]
            for i, line in enumerate(self.lns):
                myi = chrs.index(line.chrs[0])
                dx = oxs[myi] - chrs[myi].pts_ut[0][0]
                dy = oys[myi] - chrs[myi].pts_ut[0][1]
                if abs(dx) > 0.001 or abs(dy) > 0.001:
                    newxv = [x + dx for x in line.x]
                    newyv = [y + dy for y in line.y]
                    if line.continuex or line.continuey:
                        if line.chrs[0].loc.typ == TYP_TAIL:
                            # wrap in a trivial Tspan so we can set x and y
                            line.chrs[0].add_style(
                                {"baseline-shift": "0%"}, setdefault=False
                            )
                        line.xsrc = line.chrs[0].loc.elem
                        line.ysrc = line.chrs[0].loc.elem
                        line.continuex = False
                        line.continuey = False
                    line.write_xy(newx=newxv, newy=newyv)

            # Fix non-first dxs
            ndxs = [c.dx for line in self.lns for c in line.chrs]
            ndys = [c.dy for line in self.lns for c in line.chrs]
            for i, c in enumerate(chrs):
                if c.lnindex > 0:
                    if abs(odxs[i] - ndxs[i]) > 0.001 or abs(odys[i] - ndys[i]) > 0.001:
                        c.dx = odxs[i]
                        c.dy = odys[i]
            self.write_dxdy()
            for line in self.lns:
                for chk in line.chks:
                    chk.charpos = None

    def strip_text_baseline_shift(self):
        """Remove baseline-shift if applied to the whole element"""
        if "baseline-shift" in self.textel.cspecified_style:
            if len(self.lns) > 0 and len(self.lns[0].chrs) > 0:
                lny = self.lns[0].y[:]
                bsv = self.lns[0].chrs[0].bshft
                self.textel.cstyle["baseline-shift"] = None
                self.reparse()
                newy = [y - bsv for y in lny]
                self.lns[0].write_xy(newy=newy)

    @staticmethod
    def get_xy(elem, xyt):
        """Gets the x or y coordinate values from an element."""
        val = EBget(elem, xyt)  # fine for 'x','y','dx','dy'
        if not val:
            return [None]  # None forces inheritance
        return [None if x == "none" else ipx(x) for x in val.split()]

    def write_dxdy(self):
        """
        After dx/dy has changed, call this to write them to the text element
        For simplicity, this is best done at the ParsedText level all at once
        """
        if self.dchange:
            # Group characters by location
            cs_loc = {(d,typ):[] for d in self.textel.descendants2() for typ in [TYP_TEXT,TYP_TAIL]}
            for ln in self.lns:
                for c in ln.chrs:
                    cs_loc[c.loc.elem,c.loc.typ].append(c)

            for (d, typ), cd in cs_loc.items():
                dx = [c.dx for c in cd]
                dy = [c.dy for c in cd]

                dxset = trim_list(dx,0)
                dyset = trim_list(dy,0)

                if typ==TYP_TAIL and (dxset is not None or dyset is not None):
                    d = wrap_string(d,typ)
                    self.tree = None  # invalidate
                    typ = TYP_TEXT
                    for c in cd:
                        c.loc = CLoc(d,TYP_TEXT,c.loc.ind)
                        
                if typ==TYP_TEXT:
                    xyset(d,"dx",dxset)
                    xyset(d,"dy",dyset)
            
            for chk in [chk for line in self.lns for chk in line.chks]:
                chk.charpos = None

            self.writtendx = any(c.dx != 0 for c in self.chrs)
            self.writtendy = any(c.dy != 0 for c in self.chrs)
            self.dchange = False
            
    def write_axay(self):
        """
        After dx/dy has changed, call this to write them to the text element
        For simplicity, this is best done at the ParsedText level all at once
        """
        if self.achange:
            # Group characters by location
            cs_loc = {(d,typ):[] for d in self.textel.descendants2() for typ in [TYP_TEXT,TYP_TAIL]}
            for ln in self.lns:
                for c in ln.chrs:
                    cs_loc[c.loc.elem,c.loc.typ].append(c)

            for (d, typ), cd in cs_loc.items():
                ax = [c.ax for c in cd]
                ay = [c.ay for c in cd]

                axset = trim_list(ax,None)
                ayset = trim_list(ay,None)
                if ayset is not None and all(ayset[0]==ayv for ayv in ayset):
                    ayset = ayset[0:1]

                if typ==TYP_TAIL and (axset is not None or ayset is not None):
                    d = wrap_string(d,typ)
                    self.tree = None  # invalidate
                    typ = TYP_TEXT
                    for c in cd:
                        c.loc = CLoc(d,TYP_TEXT,c.loc.ind)
                        
                if typ==TYP_TEXT:
                    # When an x/y ends in Nones they can be trimmed off, but when
                    # they have internal Nones the string must be split
                    if (axset is not None and None in axset) or (ayset is not None and None in ayset):
                        span = inkex.Tspan if d.tag in TEtags else inkex.FlowSpan
                        sx = [i+1 for i,v in enumerate(axset[:-1]) if v is None and axset[i+1] is not None]
                        sy = [i+1 for i,v in enumerate(ayset[:-1]) if v is None and ayset[i+1] is not None]
                        sidx = sorted(sx+sy)
                        ranges = [(sidx[i-1] if i > 0 else 0, sidx[i] if i < len(sidx) else len(cd)) for i in range(len(sidx) + 1)]
                        txt = d.text
                        d.text = None
                        for k,(r1,r2) in enumerate(reversed(ranges)):
                            t = span() if k<len(ranges)-1 else d
                            t.text = txt[r1:r2]
                            if k<len(ranges)-1:
                                d.insert(0,t)
                            xyset(t,"x",trim_list(axset[r1:r2],None))
                            xyset(t,"y",trim_list(ayset[r1:r2],None))
                            for j,c in enumerate(cd[r1:r2]):
                                c.loc = CLoc(t,TYP_TEXT,j)
                    else:                    
                        xyset(d,"x",axset) 
                        xyset(d,"y",ayset)
            
            for chk in [chk for line in self.lns for chk in line.chks]:
                chk.charpos = None
            self.achange = False

    def make_editable(self):
        """
        Text is hard to edit unless xml:space is set to preserve and
        sodipodi:role is set to line. Should usually be called last
        """
        elem = self.textel
        elem.set("xml:space", "preserve")
        if (
            len(self.lns) == 1
            and self.lns[0].tlvlno is not None
            and not (self.lns[0].sprl)
        ):  # only one line that is a top-level tspan
            line = self.lns[0]
            olddx = [c.dx for line in self.lns for c in line.chrs]
            olddy = [c.dy for line in self.lns for c in line.chrs]

            if len(line.chrs) > 0:
                cel = line.chrs[0].loc.elem
                while cel != elem and cel.getparent() != elem:
                    cel = cel.getparent()
                tlvl = cel

                xyset(tlvl.getparent(), "x", line.x)
                xyset(tlvl.getparent(), "y", line.y)

                tlvl.set("sodipodi:role", "line")
                # reenable sodipodi so we can insert returns

                if self.writtendx or self.writtendy:
                    for i, chrv in enumerate(self.lns[0].chrs):
                        chrv.dx = olddx[i]
                        chrv.dy = olddy[i]
                    self.dchange = True
                    # may have deleted spr lines

        # For single lines, reset line-height to default
        changed_styles = dict()
        if len(self.lns) == 1:
            for ddv in elem.descendants2():
                if "line-height" in ddv.cstyle:
                    changed_styles[ddv] = ddv.cstyle
                    del changed_styles[ddv]["line-height"]

        if len(self.chrs) > 0:
            # Clear all fonts and only apply to relevant Tspans

            for ddv in elem.descendants2():
                sty = changed_styles.get(ddv, ddv.cstyle)
                for key in [
                    "font-family",
                    "font-stretch",
                    "font-weight",
                    "font-style",
                    "-inkscape-font-specification",
                ]:
                    if key in sty:
                        del sty[key]
                        changed_styles[ddv] = sty

            for c in self.chrs:
                sty = changed_styles.get(c.loc.sel, c.loc.sel.cstyle)
                sty.update(c.fsty)
                changed_styles[c.loc.sel] = sty

            # Put the first char's font at top since that's what Inkscape displays
            # sty = Style(tuple(elem.cstyle.items()))
            sty = changed_styles.get(elem, elem.cstyle)
            sty.update(self.chrs[0].fsty)
            changed_styles[elem] = sty

            # Try to set nominal font size to max value
            # (value used by line-height, what Inkscape reports, etc.)
            fs_origins = set()
            for c in self.chrs:
                cel = c.loc.sel
                fs_origins.add(cel)
                celstyle = changed_styles.get(cel, cel.cstyle)
                while (
                    ("font-size" in celstyle and "%" in str(celstyle["font-size"]))
                    or ("font-size" not in celstyle)
                ) and cel is not elem:
                    cel = cel.getparent()
                    fs_origins.add(cel)
                    celstyle = changed_styles.get(cel, cel.cstyle)
            if elem not in fs_origins and (
                len(self.lns) == 1 or all(not line.sprl for line in self.lns[1:])
            ):
                sty = changed_styles.get(elem, elem.cstyle)
                maxsize = max([c.utfs for c in self.chrs])
                if "font-size" not in sty or sty["font-size"] != maxsize:
                    sty["font-size"] = str(max([c.utfs for c in self.chrs]))
                    changed_styles[elem] = sty
        for k, val in changed_styles.items():
            k.cstyle = val

    def split_off_chunks(self, chks):
        """Splits off specified chunks of text into a new element."""
        return self.split_off_characters([c for chk in chks for c in chk.chrs])

    def split_off_characters(self, chrs):
        """Splits off specified characters into a new element."""
        npt = self.duplicate()
        newtxt = npt.textel
        
        # Record position
        cs1 = [c for ln in self.lns for c in ln.chrs]
        cs2 = [c for ln in  npt.lns for c in ln.chrs]
        dmemo = dict(zip(cs1,cs2))
        
        ps1 = {c:c.pts_ut[0] for c in cs1}
        ps2 = {c:c.pts_ut[0] for c in cs2}
        ds = {c:(c.dx,c.dy) for c in cs2}
        fc = dmemo[chrs[0]]
        
        
        # chars' line index
        iln = self.lns.index(chrs[0].line)
        ciis = [c.lnindex for c in chrs]  # indexs of charsin line

        fusex = self.lns[iln].continuex or ciis[0] > 0 or ds[fc][0] != 0
        fusey = self.lns[iln].continuey or ciis[0] > 0 or ds[fc][1] != 0
        if fusex:
            anfr = self.lns[iln].anchfrac
            oldx = chrs[0].pts_ut[0][0] * (1 - anfr) + chrs[-1].pts_ut[3][0] * anfr
        if fusey:
            oldy = chrs[0].chk.y + ds[fc][1]

        for c in reversed(chrs):
            c.delc(updatedelta=False)

        # Delete the other lines/chars in the copy
        for il2 in reversed(range(len(npt.lns))):
            if il2 != iln:
                npt.lns[il2].dell()
            else:
                nln = npt.lns[il2]
                for j in reversed(range(len(nln.chrs))):
                    if j not in ciis:
                        nln.chrs[j].delc(updatedelta=False)

        # Deletion of text can cause the srcs to be wrong.
        # Reparse to find whereit is now
        nln.xsrc, nln.ysrc = npt.parse_lines(srcsonly=True)
        nln.write_xy(newx=nln.x, newy=nln.y)
        nln.disablesodipodi(force=True)
        if len(self.lns) > 0:
            self.lns[0].xsrc, self.lns[0].ysrc = self.parse_lines(srcsonly=True)
            self.lns[0].write_xy(newx=self.lns[0].x, newy=self.lns[0].y)

        if fusex:
            nln.continuex = False
            nln.write_xy(newx=[oldx])
            ds[fc] = (0,ds[fc][1])
        if fusey:
            nln.continuey = False
            nln.write_xy(newy=[oldy])
            ds[fc] = (ds[fc][0],0)


        for ln in npt.lns:
            for c in ln.chrs:
                c.dx = ds[c][0]
                c.dy = ds[c][1]
        npt.write_dxdy()

        # In case there are some errors, correct with deltas
        for pt, ps in [(self,ps1), (npt,ps2)]:
            for ln in pt.lns:
                for chk in ln.chks:
                    Deltax = [c.pts_ut[0][0] - ps[c][0] for c in chk.chrs]
                    Deltay = [c.pts_ut[0][1] - ps[c][1] for c in chk.chrs]
                    
                    if any(abs(d) > 0.001 for d in Deltax + Deltay):
                        for i in range(len(Deltax)):
                            if i == 0:
                                if ln.anchfrac == 0:
                                    dx = Deltax[0]
                                    dy = Deltay[0]
                                elif ln.anchfrac == 0.5:
                                    dx = Deltax[0] + Deltax[-1]
                                    dy = Deltay[0] + Deltay[-1]
                                else:
                                    dx = 0
                                    dy = 0
                                    # right aligned: would not be able to compute
                            else:
                                dx = Deltax[i] - Deltax[i - 1]
                                dy = Deltay[i] - Deltay[i - 1]
                            chk.chrs[i].dx -= dx
                            chk.chrs[i].dy -= dy
                        pt.write_dxdy()

        newtxt._parsed_text = npt
        return newtxt

    def delete_empty(self):
        """Deletes empty elements from the doc. Generally this is done last"""
        ocs_pts = [c.pts_t for c in self.chrs]
        ocs_dx  = [c.dx for c in self.chrs]
        ocs_dy  = [c.dy for c in self.chrs]
        dltd = deleteempty(self.textel)
        if dltd:
            self.tree = None
            self.reparse()
            # Correct the position of the first character
            chrs = [c for line in self.lns for c in line.chrs]
            for i, line in enumerate(self.lns):
                myi = chrs.index(line.chrs[0])
                dxt = ocs_pts[myi][0][0] - chrs[myi].pts_t[0][0]
                dyt = ocs_pts[myi][0][1] - chrs[myi].pts_t[0][1]
                
                if abs(dxt) > 0.001 or abs(dyt) > 0.001:
                    oldpos = vmultinv(chrs[myi].line.transform.matrix, ocs_pts[myi][0][0], ocs_pts[myi][0][1])
                    dltax = oldpos[0] - chrs[myi].pts_ut[0][0]
                    dltay = oldpos[1] - chrs[myi].pts_ut[0][1]
                    newxv = [x + dltax for x in line.x]
                    newyv = [y + dltay for y in line.y]
                    
                    if line.continuex or line.continuey:
                        if line.chrs[0].loc.typ == TYP_TAIL:
                            # wrap in a trivial Tspan so we can set x and y
                            line.chrs[0].add_style(
                                {"baseline-shift": "0%"}, setdefault=False
                            )
                        line.xsrc = line.chrs[0].loc.elem
                        line.ysrc = line.chrs[0].loc.elem
                        line.continuex = False
                        line.continuey = False
                    line.write_xy(newx=newxv, newy=newyv)

            # Fix non-first dxs
            ndxs = [c.dx for line in self.lns for c in line.chrs]
            ndys = [c.dy for line in self.lns for c in line.chrs]
            for i, c in enumerate(chrs):
                if c.lnindex > 0:
                    if abs(ocs_dx[i] - ndxs[i]) > 0.001 or abs(ocs_dy[i] - ndys[i]) > 0.001:
                        c.dx = ocs_dx[i]
                        c.dy = ocs_dy[i]
            self.write_dxdy()
            for line in self.lns:
                for chk in line.chks:
                    chk.charpos = None

    def fuse_fonts(self):
        """
        For exporting, one usually wants to replace fonts with the actual font
        that each character is rendered as.

        Other SVG renderers may only be able to use the font face name (i.e.,
        the fullname in fontconfig, which is the same name reported as Face in
        Text and Font), so we make this the family name and add the true
        family as a backup (with appropriate weight, width, and slant).

        For example, the ultra-bold variation of Arial has a face name of
        Arial Black, while in Inkscape its CSS name is Arial Heavy. Therefore,
        we would change its font-family to 'Arial Black','Arial'.
        """
        # Collect all the fonts and how they are rendered
        cstys = self.ctable.cstys
        newfams = []
        for line in self.lns:
            for c in line.chrs:
                newfam = (c.fsty, c, c.loc.sel)
                if c.c in cstys[c.fsty] and cstys[c.fsty][c.c] is not None:
                    csty = cstys[c.fsty][c.c]
                    fullname = fcfg.get_true_font_fullname(csty)
                    fontfam = csty["font-family"].strip("'")
                    fusefam = "'" + fullname + "','" + fontfam + "'"
                    fusesty = Style(
                        {
                            k: v if k != "font-family" else fusefam
                            for k, v in csty.items()
                        }
                    )
                    if not c.fsty == fusesty:
                        newfam = (fusesty, c, c.loc.sel)

                newfams.append(newfam)

        # Make a dictionary whose keys are the elements whose styles we
        # want to modify and whose values are (the new family, a list of characters)
        # In descending order of the number of characters
        torepl = {}
        for csty, c, sel in newfams:
            torepl.setdefault(sel, []).append((csty, c))
        for sel, value in torepl.items():
            count_dict = {}
            for csty, c in value:
                count_dict.setdefault(csty, []).append(c)
            new_value = []
            for k, val in count_dict.items():
                new_tup = (k, val)
                new_value.append(new_tup)
            new_value.sort(key=lambda x: len(x[1]), reverse=True)
            torepl[sel] = new_value

        # Replace fonts
        for elem, rlst in torepl.items():
            # For the most common family, set the element style itself
            if not font_style(elem.ccascaded_style) == rlst[0][0]:
                elem.cstyle = elem.ccascaded_style
                for k, val in rlst[0][0].items():
                    elem.cstyle[k] = val
                elem.cstyle["-inkscape-font-specification"] = None
                for c in rlst[0][1]:
                    c.sty = elem.cstyle
            # For less common, need to wrap in a new Tspan
            for r in rlst[1:]:
                for c in r[1]:
                    c.add_style(
                        {
                            "font-family": r[0]["font-family"],
                            "font-weight": r[0]["font-weight"],
                            "font-style": r[0]["font-style"],
                            "font-stretch": r[0]["font-stretch"],
                            "baseline-shift": "0%",
                        },
                        setdefault=False,
                    )

    def flow_to_text(self):
        """Converts flowed text into normal text, returning the text els."""
        if self.isflow:
            newtxts = []
            for line in reversed(self.lns):
                nany = any(math.isnan(yvl) for yvl in line.y)

                anch = line.anchor
                algn = {"start": "start", "middle": "center", "end": "end"}[anch]

                origx = None
                if len(line.chrs) > 0:
                    origx = line.chrs[0].pts_ut[0][0]

                newtxt = self.split_off_characters(line.chrs)
                if newtxt.tag == FRtag:
                    for ddv in newtxt.descendants2():
                        if ddv.tag == FRtag:
                            ddv.tag = TextElement.ctag
                        elif isinstance(ddv, (FlowPara, FlowSpan)):
                            ddv.tag = TStag
                        elif isinstance(ddv, inkex.FlowRegion):
                            ddv.delete()
                else:
                    newtxt.cstyle["shape-inside"] = None
                    newtxt.cstyle["inline-size"] = None
                    for k in list(newtxt):
                        k.cstyle["text-align"] = algn
                        k.cstyle["text-anchor"] = anch

                if nany:
                    newtxt.delete()
                else:
                    deleteempty(newtxt)
                    npt = newtxt.parsed_text
                    if (
                        origx is not None
                        and len(npt.lns) > 0
                        and len(npt.lns[0].chrs) > 0
                    ):
                        npt.reparse()
                        newx = [
                            xvl + origx - npt.lns[0].chrs[0].pts_ut[0][0]
                            for xvl in npt.lns[0].x
                        ]
                        npt.lns[0].write_xy(newx)
                    newtxts.append(newtxt)

            self.textel.delete()
            return newtxts
        return []

    # For debugging: make a rectange at all of the line's chunks' nominal extents
    HIGHLIGHT_STYLE = "fill:#007575;fill-opacity:0.4675"  # mimic selection

    def make_highlights(self, htype):
        """Creates rectangles to highlight extents or bounding boxes."""
        if htype == "char":
            exts = self.get_char_extents()
        elif htype == "charink":
            exts = self.get_char_inkbbox()
        elif htype == "fullink":
            exts = [self.get_full_inkbbox()]
        elif htype == "chunk":
            exts = self.get_chunk_extents()
        elif htype == "line":
            exts = self.get_line_extents()
        elif htype == "chunkink":
            exts = self.get_chunk_ink()
        elif htype == "lineink":
            exts = self.get_line_ink()
        else:  # 'all'
            exts = [self.get_full_extent()]
        for i, ext in enumerate(exts):
            r = inkex.Rectangle()
            r.set("x", ext.x1)
            r.set("y", ext.y1)
            r.set("height", ext.h)
            r.set("width", ext.w)
            r.set("transform", self.textel.ccomposed_transform)
            sty = (
                ParsedText.HIGHLIGHT_STYLE
                if i % 2 == 0
                else ParsedText.HIGHLIGHT_STYLE.replace("0.4675", "0.5675")
            )
            r.set("style", sty)
            self.textel.croot.append(r)
            
    def differential_to_absolute_kerning(self):
        """ Converts any differential kerning to absolute kerning """
        if not self.isflow and any(c.dx!=0 for c in self.chrs):
            for ln in self.lns:
                ln.disablesodipodi()
                for i,w in enumerate(ln.chks):                    
                    pts = [c.pts_ut for c in w.chrs]
                    for j, c in enumerate(w.chrs):
                        if c.dx != 0:
                            # Get last char in chunk without a dx
                            lc = next((j + idx for idx, c in enumerate(w.chrs[j+1:]) if c.dx != 0), len(w.chrs) - 1)
                            c.ax = pts[j][0][0] * (1 - ln.anchfrac) + pts[lc][3][0] * ln.anchfrac
                            c.dx = 0
                        else:
                            c.ax = w.x if j==0 else None
                            
                        if c.dy !=0:
                            c.ay = pts[j][0][1]
                            c.dy = 0
                        else:
                            c.ay = w.y if j==0 else None
            self.write_dxdy()
            self.write_axay()
            
            ptsut = [c.parsed_pts_ut for c in self.chrs]
            ptst = [c.parsed_pts_t for c in self.chrs]
            self.reparse()
            for i, c in enumerate(self.chrs):
                c.parsed_pts_ut = ptsut[i]
                c.parsed_pts_t = ptst[i]

    # Bounding box functions
    def get_char_inkbbox(self):
        """Gets the untransformed bounding boxes of all characters' ink."""
        exts = []
        if self.lns is not None and len(self.lns) > 0 and self.lns[0].xsrc is not None:
            for line in self.lns:
                for chk in line.chks:
                    for c in chk.chrs:
                        pt1 = c.pts_ut_ink[0]
                        pt2 = c.pts_ut_ink[2]
                        if not math.isnan(pt1[1]):
                            exts.append(bbox((pt1, pt2)))
        return exts

    def get_full_inkbbox(self):
        """Gets the untransformed bounding box of the whole element."""
        ext = bbox(None)
        if self.lns is not None and len(self.lns) > 0 and self.lns[0].xsrc is not None:
            for line in self.lns:
                for chk in line.chks:
                    for c in chk.chrs:
                        pt1 = c.pts_ut_ink[0]
                        pt2 = c.pts_ut_ink[2]
                        ext = ext.union(bbox((pt1, pt2)))
        return ext

    # Extent functions
    def get_char_extents(self):
        """Gets the untransformed extent of each character."""
        exts = []
        if self.lns is not None and len(self.lns) > 0 and self.lns[0].xsrc is not None:
            for line in self.lns:
                for chk in line.chks:
                    for c in chk.chrs:
                        pt1 = c.pts_ut[0]
                        pt2 = c.pts_ut[2]
                        if not math.isnan(pt1[1]):
                            exts.append(bbox((pt1, pt2)))
        return exts

    def get_chunk_extents(self):
        """Gets the untransformed extent of each chunk."""
        exts = []
        if self.lns is not None and len(self.lns) > 0 and self.lns[0].xsrc is not None:
            for line in self.lns:
                for chk in line.chks:
                    pt1 = chk.pts_ut[0]
                    pt2 = chk.pts_ut[2]
                    if not math.isnan(pt1[1]):
                        exts.append(bbox((pt1, pt2)))
        return exts

    def get_line_extents(self):
        """Gets the untransformed extent of each line."""
        exts = []
        if self.lns is not None and len(self.lns) > 0 and self.lns[0].xsrc is not None:
            for line in self.lns:
                extln = bbox(None)
                for chk in line.chks:
                    pt1 = chk.pts_ut[0]
                    pt2 = chk.pts_ut[2]
                    if not math.isnan(pt1[1]):
                        extln = extln.union(bbox((pt1, pt2)))
                if not (extln.isnull):
                    exts.append(extln)
        return exts

    def get_chunk_ink(self):
        """Gets the untransformed extent of each chunk's ink."""
        exts = []
        if self.lns is not None and len(self.lns) > 0 and self.lns[0].xsrc is not None:
            for line in self.lns:
                for chk in line.chks:
                    ext = bbox(None)
                    for c in chk.chrs:
                        pt1 = c.pts_ut_ink[0]
                        pt2 = c.pts_ut_ink[2]
                        ext = ext.union(bbox((pt1, pt2)))
                    exts.append(ext)
        return exts

    def get_line_ink(self):
        """Gets the untransformed extent of each line's ink."""
        exts = []
        if self.lns is not None and len(self.lns) > 0 and self.lns[0].xsrc is not None:
            for line in self.lns:
                ext = bbox(None)
                for c in line.chrs:
                    pt1 = c.pts_ut_ink[0]
                    pt2 = c.pts_ut_ink[2]
                    ext = ext.union(bbox((pt1, pt2)))
                exts.append(ext)
        return exts

    def get_full_extent(self, parsed=False):
        """
        Gets the untransformed extent of the whole element.
        parsed=True gets original prior to any mods
        """
        ext = bbox(None)
        if self.lns is not None and len(self.lns) > 0 and self.lns[0].xsrc is not None:
            for line in self.lns:
                for chk in line.chks:
                    for c in chk.chrs:
                        pts = (
                            c.parsed_pts_ut
                            if parsed and c.parsed_pts_ut is not None
                            else c.pts_ut
                        )
                        pt1 = pts[0]
                        pt2 = pts[2]
                        if not math.isnan(pt1[1]):
                            ext = ext.union(bbox((pt1, pt2)))
        return ext

    @property
    def tree(self):
        """Returns the text tree of the element."""
        if self._tree is None:
            self._tree = TextTree(self.textel)
        return self._tree

    @tree.setter
    def tree(self, val):
        """Sets the text tree of the element."""
        if val is None:
            self._tree = None

    def parse_lines_flow(self):
        """
        Parses lines of flowed text.
        For non-rectangular flow regions, uses svgpathtools to find where
        lines are drawn (this is imported conditionally).
        """
        self.lns = []
        sty = self.textel.cspecified_style
        isflowroot = self.textel.tag == FRtag
        isshapeins = (
            self.textel.tag == TEtag
            and sty.get_link("shape-inside", self.textel.croot) is not None
        )
        isz = ipx(sty.get("inline-size"))
        isinlinesz = self.textel.tag == TEtag and isz
        # Inkscape ignores 0 and invalid inline-size

        # Determine the flow region
        otp_support = self.textel.otp_support_prop
        if isshapeins:
            frgn = sty.get_link("shape-inside", self.textel.croot)
            dfr = frgn.duplicate()

            # Fuse transform to path
            dfr.object_to_path()
            dfr.set("d", str(dfr.cpath.transform(dfr.ctransform)))
            dfr.cpath = None
            dfr.ctransform = None

            # shape transform fused on path (not composed transform though)
            self.textel.append(dfr)
            region = dfr
        # Find the bbox of the FlowRegion
        elif isflowroot:
            for ddv in self.textel.descendants2():
                if isinstance(ddv, FlowRegion):
                    pths = [p for p in ddv.descendants2() if p.tag in otp_support]
                    if len(pths) > 0:
                        region = pths[0]
        elif isinlinesz:
            # Make a Rectangle and treat it as the flow region
            r = inkex.Rectangle()
            _, ysrc = self.parse_lines(srcsonly=True)
            iszx = self.textel.get("x")
            iszy = self.textel.get("y", ysrc.get("y"))

            afr = get_anchorfrac(sty.get("text-anchor"))
            r.set("x", -isz * afr)  # pylint:disable=invalid-unary-operand-type
            r.set("y", 0)
            r.set("height", isz)
            r.set("width", isz)
            self.textel.croot.append(r)
            region = r

        padding = ipx(self.textel.cspecified_style.get("shape-padding", "0"))
        isrect = isrectangle(region, includingtransform=False)

        usesvt = not isrect and region.tag in otp_support and padding == 0
        if not isrect and not usesvt:
            # Flow region we cannot yet handle, parse as normal text
            # This works as long as the SVG1.1 fallback is being used
            self.isflow = False
            return self.parse_lines()
        if usesvt:
            region.object_to_path()
            import svgpathtools as spt  # pylint: disable=import-error, import-outside-toplevel

            sptregion = spt.parse_path(region.get("d"))
            if not sptregion.isclosed():
                end = sptregion[-1].end
                start = sptregion[0].start
                sptregion.append(spt.Line(end, start))
                sptregion.closed = True

        bbx = region.cpath.bounding_box()
        bbx = [bbx.left, bbx.top, bbx.width, bbx.height]
        if not padding == 0:
            bbx = [
                bbx[0] + padding,
                bbx[1] + padding,
                bbx[2] - 2 * padding,
                bbx[3] - 2 * padding,
            ]

        # Delete duplicate
        if isshapeins:
            dfr.delete()
        elif isinlinesz:
            r.delete()

        def height_above_below_baseline(elem):
            lht = composed_lineheight(elem)
            lsty = true_style(elem.cspecified_style)
            fsz, scf, _ = composed_width(elem, "font-size")

            absp = (0.5000 * (lht / fsz - 1) + CharacterTable.flowy(lsty)) * (
                fsz / scf
            )  # spacing above baseline
            bbsp = (0.5000 * (lht / fsz - 1) + 1 - CharacterTable.flowy(lsty)) * (
                fsz / scf
            )  # spacing below baseline
            rawfs = fsz / scf
            return absp, bbsp, rawfs

        # Get the properties of the FlowRoot
        rabsp, rbbsp, rfs = height_above_below_baseline(self.textel)
        rpct = (
            "line-height" in self.textel.cspecified_style
            and "%" in self.textel.cspecified_style["line-height"]
        )
        if rpct:
            pctage = float(self.textel.cspecified_style["line-height"].strip("%"))

        # Group characters into lines
        lns = []
        fparas = [
            k for k in list(self.textel) if isinstance(k, FlowPara)
        ]  # top-level FlowParas
        for ddi, typ, tel, sel, txt in self.tree.dgenerator():
            if txt is not None and len(txt) > 0:
                if isflowroot:
                    lnno = [
                        i
                        for i, fpv in enumerate(fparas)
                        if fpv in tel.ancestors2(includeme=True)
                    ]
                    if len(lnno) == 0:
                        lnno = 0
                    else:
                        lnno = lnno[0]
                    # tails of a FlowPara belong to the next line
                    if tel == fparas[lnno] and typ == TYP_TAIL:
                        lnno += 1
                else:
                    # Note: Tspans don't do anything in SVG2 flows
                    lnno = 0

                # Determine above- and below-baseline lineheight
                sty = sel.cspecified_style
                ctf = sel.ccomposed_transform
                fsz, scf, utfs = composed_width(sel, "font-size")
                absp, bbsp, mrfs = height_above_below_baseline(sel)
                lsty = true_style(sel.cspecified_style)
                fabsp = max(rabsp, absp)
                fbbsp = max(rbbsp, bbsp)

                # Inkscape has a bug when the FlowRoot has a line-height
                # specified as a percentage and the FlowPara doesn't have one
                # specified. Account for this
                anc = sel.ancestors2(includeme=True, stopbefore=self.textel)
                if rpct and all("line-height" not in a.cstyle for a in anc):
                    if rbbsp > bbsp:
                        fbbsp += (CharacterTable.flowy(lsty) - 0.5) * (rfs - mrfs)
                    if absp > rabsp:
                        fabsp -= (0.5 * (pctage / 100)) * (mrfs - rfs)
                        fbbsp -= (
                            0.5 * (pctage / 100) - (CharacterTable.flowy(lsty) - 0.5)
                        ) * (mrfs - rfs)

                if lnno >= len(lns):
                    algn = sty.get("text-align", "start")
                    anch = sty.get("text-anchor", "start")
                    if not algn == "start" and anch == "start":
                        anch = {"start": "start", "center": "middle", "end": "end"}[
                            algn
                        ]
                    cln = TLine(
                        self,
                        [0],
                        [0],
                        self.textel,
                        self.textel,
                        False,
                        [],
                        anch,
                        ctf,
                        None,
                        sty,
                        False,
                        False,
                    )
                    lns.append(cln)
                    cln.broken = False
                    cln.effabsp = fabsp
                    cln.effbbsp = fbbsp
                else:
                    cln = lns[lnno]
                    
                if typ==TYP_TEXT:
                    dxv = ParsedText.get_xy(self.tree.dds[ddi],'dx')
                    dyv = ParsedText.get_xy(self.tree.dds[ddi],'dy')
                    if dxv[0] is None:
                        dxv = [0]*len(txt)
                    else:
                        dxv = dxv + [0]*(len(txt)-len(dxv))
                    if dyv[0] is None:
                        dyv = [0]*len(txt)
                    else:
                        dyv = dyv + [0]*(len(txt)-len(dyv))
                else:
                    dxv = [0]*len(txt)
                    dyv = [0]*len(txt)

                fsty = font_style(sty)
                tsty = true_style(fsty)
                for j, c in enumerate(txt):
                    csty = self.font_picker(txt, j, fsty, tsty)
                    prop = self.ctable.get_prop(c, csty)
                    tchr = TChar(
                        c, fsz, utfs, prop, sty, csty, CLoc(tel, typ, j), cln, dxv[j], dyv[j]
                    )
                    tchr.lhs = (fabsp, fbbsp)
                    if j == 0:
                        lsp0 = tchr.lsp
                        bshft0 = tchr.bshft
                    else:
                        tchr.lsp = lsp0
                        tchr.bshft = bshft0
        self.lns = lns
        self.finish_lines()
        self.fparaafter = False

        # Figure out where to break lines
        # Currently only works for rectangular flows
        i = 0
        breakcs = " -—!}|/?"
        lncs = [line.chrs for line in lns]
        blns = []
        lchr = None
        y = 0
        while i < len(lncs):
            if len(lncs[i]) > 0:
                fchr = lncs[i][0]

                lht = None
                getxintervals = True
                while getxintervals:
                    getxintervals = False
                    if lht is None:
                        lht = fchr.line.effabsp + fchr.line.effbbsp

                    # Determine x intervals where we can draw text
                    if not usesvt:
                        # For rectangles this is just the bounding box
                        xlims = [(bbx[0], bbx[2])]
                    else:
                        # For other flows this is where at least 90% of the line
                        # is unobstructed by the path
                        # Start by finding intervals where the y=10% and 90% points
                        # of the baseline intersect with the flow region
                        ln10 = spt.Line(
                            bbx[0] + (bbx[1] + y + lht * 0.1) * 1j,
                            bbx[0] + bbx[2] + (bbx[1] + y + lht * 0.1) * 1j,
                        )
                        ln90 = spt.Line(
                            bbx[0] + (bbx[1] + y + lht * 0.9) * 1j,
                            bbx[0] + bbx[2] + (bbx[1] + y + lht * 0.9) * 1j,
                        )
                        isc10 = sptregion.intersect(ln10)
                        isc90 = sptregion.intersect(ln90)
                        pts10 = sorted(
                            [
                                sptregion.point(T1).real
                                for (T1, seg1, t1), (T2, seg2, t2) in isc10
                            ]
                        )
                        pts90 = sorted(
                            [
                                sptregion.point(T1).real
                                for (T1, seg1, t1), (T2, seg2, t2) in isc90
                            ]
                        )
                        intervals = []
                        for j in range(int(len(pts10) / 2)):
                            int10 = (pts10[2 * j], pts10[2 * j + 1])
                            for k in range(int(len(pts90) / 2)):
                                int90 = (pts90[2 * k], pts90[2 * k + 1])
                                intrsc = (
                                    max(int10[0], int90[0]),
                                    min(int10[1], int90[1]),
                                )
                                if intrsc[1] > intrsc[0]:
                                    intervals.append(intrsc)

                        # Use the tangent line at the 10 and 90% points to find the
                        # points where the line is at least 90% unobstructed
                        tol = lht * 1e-6

                        def tangent_line(pos):
                            pnt = sptregion.point(pos)
                            drv = sptregion.derivative(pos)
                            if not drv.real == 0:
                                slp = drv.imag / drv.real
                                intcp = pnt.imag - drv.imag / drv.real * pnt.real
                            else:
                                slp = drv.imag / tol
                                intcp = pnt.imag - drv.imag / tol * pnt.real
                            return slp, intcp

                        def intersection_belowabove(pos, below=True):
                            pnt = sptregion.point(pos)
                            vrtl = spt.Line(
                                pnt.real + (bbx[1]) * 1j,
                                pnt.real + (bbx[1] + bbx[3]) * 1j,
                            )
                            try:
                                intrsct = sptregion.intersect(vrtl)
                            except AssertionError:
                                return None, None
                            yvs = sorted(
                                [
                                    sptregion.point(T1b).imag
                                    for (T1b, seg1b, t1b), (T2b, seg2b, t2b) in intrsct
                                ]
                            )
                            if below:
                                yvs = [yvl for yvl in yvs if yvl > pnt.imag + tol]
                                ret = yvs[0] if len(yvs) > 0 else None
                            else:
                                yvs = [yvl for yvl in yvs if yvl < pnt.imag - tol]
                                ret = yvs[-1] if len(yvs) > 0 else None
                            rett = (
                                [
                                    T1b
                                    for (T1b, seg1b, t1b), (T2b, seg2b, t2b) in intrsct
                                    if sptregion.point(T1b).imag == ret
                                ][0]
                                if ret is not None
                                else None
                            )
                            return ret, rett

                        def bounding_lines(p_top, p_btm):
                            if len(p_top) > 0:
                                p_top = p_top[0]
                                (mtop, btop) = tangent_line(p_top)
                                ry, r_pos = intersection_belowabove(p_top, below=True)
                                if ry is None or ry > bbx[1] + y + lht:
                                    (mbtm, bbtm) = (0, bbx[1] + y + lht)
                                else:
                                    (mbtm, bbtm) = tangent_line(r_pos)
                            else:
                                p_btm = p_btm[0]
                                (mbtm, bbtm) = tangent_line(p_btm)
                                ry, r_pos = intersection_belowabove(p_btm, below=False)
                                if ry is None or ry < bbx[1] + y:
                                    (mtop, btop) = (0, bbx[1] + y)
                                else:
                                    (mtop, btop) = tangent_line(r_pos)
                            return mtop, btop, mbtm, bbtm

                        ints2 = []
                        for inta, intb in intervals:
                            t10a = [
                                T1
                                for (T1, seg1, t1), (T2, seg2, t2) in isc10
                                if sptregion.point(T1).real == inta
                            ]
                            t90a = [
                                T1
                                for (T1, seg1, t1), (T2, seg2, t2) in isc90
                                if sptregion.point(T1).real == inta
                            ]
                            t10b = [
                                T1
                                for (T1, seg1, t1), (T2, seg2, t2) in isc10
                                if sptregion.point(T1).real == intb
                            ]
                            t90b = [
                                T1
                                for (T1, seg1, t1), (T2, seg2, t2) in isc90
                                if sptregion.point(T1).real == intb
                            ]

                            mtopa, btopa, mbtma, bbtma = bounding_lines(t10a, t90a)
                            mtopb, btopb, mbtmb, bbtmb = bounding_lines(t10b, t90b)

                            dya = (mbtma * inta + bbtma) - (mtopa * inta + btopa)
                            if dya < 0.9 * lht - tol:
                                xp9a = (
                                    (0.9 * lht - (bbtma - btopa)) / (mbtma - mtopa)
                                    if mbtma != mtopa
                                    else None
                                )
                                xp9a = xp9a if xp9a >= inta else None
                            else:
                                xp9a = inta

                            dyb = (mbtmb * intb + bbtmb) - (mtopb * intb + btopb)
                            if dyb < 0.9 * lht - tol:
                                xp9b = (
                                    (0.9 * lht - (bbtmb - btopb)) / (mbtmb - mtopb)
                                    if mbtmb != mtopb
                                    else None
                                )
                                xp9b = xp9b if xp9b <= intb else None
                            else:
                                xp9b = intb

                            if xp9a is not None and xp9b is not None and xp9b >= xp9a:
                                ints2.append((xp9a, xp9b))
                        xlims = [(intv[0], intv[1] - intv[0]) for intv in ints2]

                        # Intersection diagnostics
                        # for p in pts10:
                        #     c = dh.new_element(inkex.Circle, self.textel)
                        #     c.set('cx',str(p))
                        #     c.set('cy',str(bbx[1]+y+lht*0.1))
                        #     c.set('r',str(fchr.utfs/10))
                        #     c.set('style','fill:#000000;stroke:none')
                        #     self.textel.croot.append(c)
                        #     c.ctransform = self.textel.ccomposed_transform
                        # for p in pts90:
                        #     c = dh.new_element(inkex.Circle, self.textel)
                        #     c.set('cx',str(p))
                        #     c.set('cy',str(bbx[1]+y+lht*0.9))
                        #     c.set('r',str(fchr.utfs/10))
                        #     c.set('style','fill:#000000;stroke:none')
                        #     self.textel.croot.append(c)
                        #     c.ctransform = self.textel.ccomposed_transform

                    # For every interval, find what text we can insert and where
                    # we should make breaks
                    breaks = []
                    for xlim in xlims:
                        breakaft = None
                        hardbreak = False
                        strt = 0 if len(breaks) == 0 else breaks[-1] + 1
                        csleft = lncs[i][strt:]
                        for j, c in enumerate(csleft):
                            if j == 0:
                                fcrun = c
                            if not isflowroot and c.c == "\n":
                                breakaft = j
                                hardbreak = True
                                break
                            if c.pts_ut[3][0] - fcrun.pts_ut[0][0] > xlim[1]:
                                spcs = [cv for cv in csleft[:j] if cv.c in breakcs]
                                # inkex.utils.debug('Break on '+str((c.c,j)))
                                if c.c == " ":
                                    breakaft = j
                                    # inkex.utils.debug('Break overflow space')
                                elif len(spcs) > 0:
                                    breakaft = [
                                        k
                                        for k, cv in enumerate(csleft)
                                        if spcs[-1] == cv
                                    ][0]
                                    # inkex.utils.debug('Break chunk')
                                elif (
                                    xlim[1] > 4 * (c.line.effabsp + c.line.effbbsp)
                                    and j > 0
                                ):
                                    # When the flowregion width is > 4*line height,
                                    # allow intraword break
                                    # https://gitlab.com/inkscape/inkscape/-/blob/master/src/libnrtype/Layout-TNG-Compute.cpp#L1989
                                    breakaft = j - 1
                                    # inkex.utils.debug('Break intraword')
                                else:
                                    # Break whole line and hope that the next
                                    # line is wider
                                    breakaft = -1
                                    # inkex.utils.debug('Break whole line')
                                break
                        if breakaft is not None:
                            c.line.broken = True
                            breaks.append(breakaft + strt)
                            if hardbreak:
                                break
                        else:
                            break
                    if len(xlims) == 0:
                        breaks = [-1]

                    # Use break points to split the line, pushing text after the
                    # last break to the next line
                    if not breaks:
                        splitcs = [lncs[i]]
                    else:
                        splitcs = []
                        prev_index = -1
                        for index in breaks:
                            splitcs.append(lncs[i][prev_index + 1 : index + 1])
                            prev_index = index
                        splitcs.append(lncs[i][prev_index + 1 :])
                    nextcs = None
                    if len(splitcs) > 1:
                        nextcs = splitcs.pop(-1)  # push to next line
                        mycs = [item for sublist in splitcs[:-1] for item in sublist]

                    allcs = [c for s in splitcs for c in s]
                    maxabsp = (
                        max([c.lhs[0] for c in allcs])
                        if len(allcs) > 0
                        else fchr.line.effabsp
                    )
                    maxbbsp = (
                        max([c.lhs[1] for c in allcs])
                        if len(allcs) > 0
                        else fchr.line.effbbsp
                    )
                    if not lht == maxabsp + maxbbsp:
                        lht = maxabsp + maxbbsp
                        getxintervals = True

                if nextcs is not None:
                    lncs = lncs[0:i] + [mycs, nextcs] + lncs[i + 1 :]
                y += maxabsp
                for j, chrs in enumerate(splitcs):
                    line = fchr.line
                    cln = TLine(
                        self,
                        [0],
                        [0],
                        self.textel,
                        self.textel,
                        False,
                        [],
                        line.anchor,
                        line.transform,
                        None,
                        line.style,
                        False,
                        False,
                    )
                    cln.broken = line.broken
                    cln.effabsp = maxabsp
                    cln.effbbsp = maxbbsp
                    blns.append(cln)
                    for c in chrs:
                        lchr = TChar(
                            c.c,
                            c.tfs,
                            c.utfs,
                            c.prop,
                            c._sty,
                            c.tsty,
                            c.loc,
                            cln, c._dx, c._dy
                        )

                    if len(chrs) > 0:
                        anfr = cln.anchfrac
                        x = (
                            xlims[j][0] * (1 - anfr)
                            + (xlims[j][0] + xlims[j][1]) * anfr
                        )
                        if i == 0 and isinlinesz and iszy is not None:
                            y += ipx(iszy) - cln.effabsp
                        if isinlinesz and iszx is not None:
                            x += ipx(iszx)
                        cln.x = [x]
                        cln.y = [bbx[1] + y]
                y += maxbbsp

                if y - 0.1 * (maxabsp + maxbbsp) > bbx[3] and not isinlinesz:
                    # When we reached the end of the flow region, add the remaining
                    # characters to a line that is given a NaN y position
                    cln.chrs = [c for lnc in lncs[i:] for c in lnc]
                    for j, c in enumerate(cln.chrs):
                        c.line = cln
                        c.lnindex = j
                    cln.y = [float("nan")]
                    break

            i += 1
            if i > 1000:
                # inkex.utils.debug('Infinite loop')
                break

        # Determine if any FlowParas follow the last character
        # (Needed for unrenderedspace determination)
        if lchr is not None:
            dds = self.textel.descendants2()
            j = dds.index(lchr.loc.elem)
            if j < len(dds) - 1:
                self.fparaafter = any(isinstance(ddv, FlowPara) for ddv in dds[j + 1 :])
        self.lns = blns


TYP_TEXT = 1
TYP_TAIL = 0

NORMAL = 0
PRECEDEDSPRL = 1
TLVLSPRL = 2

class TextTree:
    """
    Descendant tree class for text, with a generator for iterating through blocks of
    text. Generator returns the current descendant index, typ (TYP_TAIL or TYP_TEXT),
    descendant element, element from which it gets its style, and text string.
    When starting at subel, only gets the tree subset corresponding to that element.
    Note: If there is no text/tail, returns None for that block.
    """

    def __init__(self, elem):
        """Initializes the text tree of an element."""
        dds, pts = elem.descendants2(True)
        self.dds = dds
        self.ptails = pts
        self.pdict = {ddv: ddv.getparent() for ddv in dds}

    def dgenerator(self, subel=None):
        """Yields descendants and their text in the tree."""
        if subel is None:
            starti = 0
            stopi = len(self.dds)
            subel = self.dds[0]
        else:
            starti = self.dds.index(subel)
            stopi = [i for i, ptail in enumerate(self.ptails) if subel in ptail][0]

        for ddi, typ in TextTree.ttgenerator(len(self.dds), starti, stopi):
            srcs = self.ptails[ddi] if typ == TYP_TAIL else [self.dds[ddi]]
            for src in srcs:
                if (
                    typ == TYP_TAIL and src == subel
                ):  # finish at my own tail (do not yield it)
                    return
                txt = src.tail if typ == TYP_TAIL else src.text
                sel = (
                    self.pdict[src] if typ == TYP_TAIL else src
                )  # tails get style from parent
                yield ddi, typ, src, sel, txt

    @staticmethod
    def ttgenerator(numd, starti=0, stopi=None):
        """
        A generator for crawling through a general text descendant tree
        Returns the current descendant index and typ (TYP_TAIL for tail,
                                                      TYP_TEXT for text)
        """
        ddi = starti
        if stopi is None:
            stopi = numd
        typ = TYP_TAIL
        while True:
            if typ == TYP_TEXT:
                ddi += 1
                typ = TYP_TAIL
            else:
                typ = TYP_TEXT
            if ddi == stopi and typ == TYP_TEXT:
                return
            yield ddi, typ


def get_anchorfrac(anch):
    """Gets the anchor fraction based on the text anchor."""
    anch_frac = {"start": 0, "middle": 0.5, "end": 1}
    return anch_frac.get(anch, 0)


class TLine:
    """
    A single line, which represents a list of characters. Typically a top-level
    Tspan or TextElement. This is further subdivided into a list of chunks.
    """

    __slots__ = (
        "_xv",
        "_yv",
        "sprl",
        "sprlabove",
        "anchor",
        "anchfrac",
        "chrs",
        "chks",
        "transform",
        "xsrc",
        "ysrc",
        "tlvlno",
        "style",
        "continuex",
        "continuey",
        "ptxt",
        "splits",
        "sws",
        "effabsp",
        "effbbsp",
        "broken",
    )

    def __init__(
        self,
        ptxt,
        x,
        y,
        xsrc,
        ysrc,
        sprl,
        sprlabove,
        anch,
        xform,
        tlvlno,
        sty,
        continuex,
        continuey,
    ):
        """Initializes TLine with given parameters."""
        self._xv = x
        self._yv = y
        self.sprl = sprl
        # is this line truly a sodipodi:role line
        self.sprlabove = sprlabove
        # nominal value of spr (sprl may actually be disabled)
        self.anchor = anch
        self.anchfrac = get_anchorfrac(anch)
        self.chrs = []
        self.chks = []
        if xform is None:
            self.transform = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        else:
            self.transform = xform
        self.xsrc = xsrc
        # element from which we derive our x value
        self.ysrc = ysrc
        # element from which we derive our x value
        self.tlvlno = tlvlno
        # which number Tspan I am if I'm top-level (otherwise None)
        self.style = sty
        # self.elem = elem;
        self.continuex = continuex
        # when enabled, x of a line is the endpoint of the previous line
        self.continuey = continuey
        # when enabled, y of a line is the endpoint of the previous line
        self.ptxt = ptxt
        # Flow-specific
        self.broken = None  # text is broken
        self.effabsp = None  # above-baseline space
        self.effbbsp = None  # below-baseline space
        ptxt.lns.append(self)

    def copy(self, memo):
        """Creates a copy of the TLine instance."""
        ret = TLine.__new__(TLine)
        memo[self] = ret

        ret._xv = self._xv[:]
        ret._yv = self._yv[:]
        ret.sprl = self.sprl
        ret.sprlabove = [memo[sa] for sa in self.sprlabove]
        ret.anchor = self.anchor
        ret.anchfrac = self.anchfrac
        ret.chrs = [c.copy(memo) for c in self.chrs]
        ret.chks = [chk.copy(memo) for chk in self.chks]
        ret.transform = self.transform
        ret.xsrc = memo[self.xsrc]
        ret.ysrc = memo[self.ysrc]
        ret.tlvlno = self.tlvlno
        ret.style = self.style
        ret.continuex = self.continuex
        ret.continuey = self.continuey
        ret.ptxt = self.ptxt
        ret.broken = self.broken
        ret.effabsp = self.effabsp  # above-baseline space
        ret.effbbsp = self.effbbsp  # below-baseline space

        return ret

    @property
    def angle(self):
        """Returns the transform angle in degrees."""
        return math.atan2(self.transform.c, self.transform.d) * 180 / math.pi

    def get_x(self):
        """Returns the x property value."""
        if not self.continuex:
            return self._xv
        if self.ptxt is None:
            return [0]
        i = self.ptxt.lns.index(self)
        if i > 0 and len(self.ptxt.lns[i - 1].chks) > 0:
            anfr = self.anchfrac
            xanch = (1 + anfr) * self.ptxt.lns[i - 1].chks[-1].pts_ut[3][
                0
            ] - anfr * self.ptxt.lns[i - 1].chks[-1].pts_ut[0][0]
            return [xanch]
        return [0]

    def set_x(self, xvi):
        """Sets the x property value."""
        self._xv = xvi

    x = property(get_x, set_x)

    def get_y(self):
        """Returns the y property value."""
        if not self.continuey:
            return self._yv
        if self.ptxt is None:
            return [0]
        i = self.ptxt.lns.index(self)
        if i > 0 and len(self.ptxt.lns[i - 1].chks) > 0:
            anfr = self.anchfrac
            yanch = (1 + anfr) * self.ptxt.lns[i - 1].chks[-1].pts_ut[3][
                1
            ] - anfr * self.ptxt.lns[i - 1].chks[-1].pts_ut[0][1]
            return [yanch]
        return [0]

    def set_y(self, yvi):
        """Sets the y property value."""
        self._yv = yvi

    y = property(get_y, set_y)
    # anchorfrac = property(lambda self: get_anchorfrac(self.anchor))

    def insertc(self, c, i):
        """Inserts a character below a specified position."""
        for ch2 in self.chrs[i:]:
            ch2.lnindex += 1
        c.lnindex = i
        self.chrs = self.chrs[0:i] + [c] + self.chrs[i:]
        c.line = self

    def addw(self, chk):
        """Adds a complete chunk to the line."""
        self.chks.append(chk)

    def parse_chunks(self):
        """
        Parses the line into chunks based on characters.
        Parsing a line into chunks is the final step that should be called once
        the line parser has gotten all the characters.
        """
        chk = None
        self.chks = []
        for i in range(len(self.chrs)):
            if i == 0:
                chk = TChunk(i, self.x[0], self.y[0], self)
                # open new chunk
            elif (i < len(self.x) and self.x[i] is not None) or (i < len(self.y) and self.y[i] is not None):  # None means keep the same chunk
                self.addw(chk)  # close previous chunk
                chk = TChunk(i, self.x[min(i,len(self.x)-1)], self.y[min(i,len(self.y)-1)], self)
                # open new chunk
            else:
                chk.addc(i)
                # add to existing chunk
        if chk is not None:
            self.addw(chk)

    def dell(self):
        """Deletes the whole line."""
        self.write_xy(self.x[:1])
        for _, c in enumerate(reversed(self.chrs)):
            if c.loc.typ == TYP_TEXT:
                c.loc.elem.text = (
                    c.loc.elem.text[: c.loc.ind] + c.loc.elem.text[c.loc.ind + 1 :]
                )
            else:
                c.loc.elem.tail = (
                    c.loc.elem.tail[: c.loc.ind] + c.loc.elem.tail[c.loc.ind + 1 :]
                )
        self.ptxt.write_dxdy()

        if self in self.ptxt.lns:
            self.ptxt.lns.remove(self)

    def txt(self):
        """Returns the concatenated text of all characters."""
        return "".join([c.c for c in self.chrs])

    def change_alignment(self, newanch):
        """Changes the alignment of the line without affecting character position."""
        if newanch != self.anchor:
            sibsrc = [
                line
                for line in self.ptxt.lns
                if line.xsrc == self.xsrc or line.ysrc == self.ysrc
            ]
            for line in reversed(sibsrc):
                line.disablesodipodi()
                # Disable sprl for all lines sharing our src, including us
                # Note that it's impossible to change one line without affecting
                # the others

            for chk in self.chks:
                minx = min([chk.pts_ut[i][0] for i in range(4)])
                maxx = max([chk.pts_ut[i][0] for i in range(4)])

                if chk.unrenderedspace and self.chrs[-1] in chk.chrs:
                    maxx -= chk.chrs[-1].cwd

                anfr = get_anchorfrac(newanch)
                newx = (1 - anfr) * minx + anfr * maxx

                if len(chk.chrs) > 0:
                    newxv = self.x
                    newxv[chk.chrs[0].lnindex] = newx
                    self.write_xy(newxv)
                    alignd = {"start": "start", "middle": "center", "end": "end"}
                    chk.chrs[0].loc.elem.cstyle.__setitem__(
                        "text-anchor", newanch, "text-align", alignd[newanch]
                    )
                    self.continuex = False

                self.anchor = newanch
                self.anchfrac = anfr
                chk.charpos = None  # invalidate chunk positions

    def disablesodipodi(self, force=False):
        """Disables sodipodi:role=line."""
        if len(self.sprlabove) > 0 or force:
            if len(self.chrs) > 0:
                newsrc = self.chrs[0].loc.elem  # disabling snaps src to first char
                if self.chrs[0].loc.typ == TYP_TAIL:
                    newsrc = self.chrs[0].loc.elem.getparent()
                newsrc.set("sodipodi:role", None)

                self.sprlabove = []
                self.xsrc = newsrc
                self.ysrc = newsrc
                xyset(self.xsrc, "x", self.x)  # fuse position to new source
                xyset(self.ysrc, "y", self.y)
                self.sprl = False

    def write_xy(self, newx=None, newy=None):
        """
        Changes the position of the line in the document.
        Update the line's position in the document, accounting for inheritance
        Never change x/y directly, always call this function
        """
        if newx is not None:
            sibsrc = [line for line in self.ptxt.lns if line.xsrc == self.xsrc]
            if len(sibsrc) > 1:
                for line in reversed(sibsrc):
                    line.disablesodipodi()  # Disable sprl when lines share an xsrc

            while len(newx) > 1 and newx[-1] is None:
                newx.pop()
            oldx = self._xv if not self.continuex else self.x
            self._xv = newx
            xyset(self.xsrc, "x", newx)

            if (
                len(oldx) > 1 and len(newx) == 1 and len(self.sprlabove) > 0
            ):  # would re-enable sprl
                self.disablesodipodi()

        if newy is not None:
            sibsrc = [line for line in self.ptxt.lns if line.ysrc == self.ysrc]
            if len(sibsrc) > 1:
                for line in reversed(sibsrc):
                    line.disablesodipodi()  # Disable sprl when lines share a ysrc

            while len(newy) > 1 and newy[-1] is None:
                newx.pop()
            oldy = self._yv if not self.continuey else self.y
            self._yv = newy
            xyset(self.ysrc, "y", newy)

            if (
                len(oldy) > 1 and len(newy) == 1 and len(self.sprlabove) > 0
            ):  # would re-enable sprl
                self.disablesodipodi()
                
    def split(self,i):
        if i>=len(self.chrs):
            return
        self.ptxt.split_off_characters(self.chrs[i:])        

class TChunk:
    """Represents a chunk, a group of characters with the same assigned anchor."""

    __slots__ = (
        "chrs",
        "windex",
        "iis",
        "ncs",
        "_xv",
        "_yv",
        # "scf",
        "line",
        "transform",
        "nextw",
        "prevw",
        "prevsametspan",
        "_pts_ut",
        "_pts_t",
        "_bb",
        "_dxeff",
        "_charpos",
        "_cpts_ut",
        "_cpts_t",
        "txt",
        "lsp",
        "dxeff",
        "cwd",
        "dy",
        "caph",
        "bshft",
        "mw",
        "merges",
        "mergetypes",
        "merged",
        "wtypes",
        "bb_big",
    )

    def __init__(self, i, x, y, line):
        """Initializes TChunk with given parameters."""
        c = line.chrs[i]
        self.chrs = [c]
        c.windex = 0
        self.iis = [i]
        # character index in chunk
        self.ncs = len(self.iis)
        self._xv = x
        self._yv = y
        # all letters have the same scale
        self.line = line
        self.transform = line.transform
        c.chk = self
        self.nextw = self.prevw = self.prevsametspan = None
        self._pts_ut = self._pts_t = self._bb = None
        self._dxeff = self._charpos = None
        self._cpts_ut = None
        self._cpts_t = None

        # Character attribute lists
        self.txt = c.c
        self.lsp = [c.lsp]
        self.dxeff = [c.dx, c.lsp]
        # Effective dx (with letter-spacing). Note that letter-spacing adds space
        # after the char, so dxeff ends up being longer than the number of chars by 1
        self.cwd = [c.cwd]
        self.dy = [c.dy]
        self.caph = [c.caph]
        self.bshft = [c.bshft]

    def copy(self, memo):
        """Creates a copy of the TChunk instance."""
        ret = TChunk.__new__(TChunk)
        memo[self] = ret

        # pylint:disable=protected-access
        ret.ncs = self.ncs
        ret._xv = self._xv
        ret._yv = self._yv
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
        ret.txt = self.txt
        ret.lsp = self.lsp[:]
        ret.dxeff = self.dxeff[:]
        ret.cwd = self.cwd[:]
        ret.dy = self.dy[:]
        ret.caph = self.caph[:]
        ret.bshft = self.bshft[:]
        # pylint:enable=protected-access

        ret.chrs = list(
            map(memo.get, self.chrs, self.chrs)
        )  # faster than [memo.get(c) for c in self.chrs]
        for ret_c in ret.chrs:
            ret_c.chk = ret
        ret.iis = self.iis[:]
        ret.line = memo[self.line]
        return ret

    def addc(self, i):
        """Adds an existing character to a chunk based on line index."""
        c = self.line.chrs[i]
        c.chk = None  # avoid problems in character properties
        self.chrs.append(c)
        self.cchange()
        self.iis.append(i)
        self.ncs = len(self.iis)
        c.windex = self.ncs - 1

        self.txt += c.c
        self.lsp.append(c.lsp)
        self.dxeff[-1] += c.dx
        self.dxeff.append(c.lsp)
        self.cwd.append(c.cwd)
        self.dy.append(c.dy)
        self.caph.append(c.caph)
        self.bshft.append(c.bshft)
        c.chk = self

    def removec(self, c):
        """Removes a character from a chunk based on chunk index."""
        i = c.windex
        for ch2 in self.chrs[i + 1 :]:
            ch2.windex -= 1
        c.windex = None
        c.chk = None
        self.chrs = del2(self.chrs, i)
        self.iis.pop(i)
        self.ncs = len(self.iis)
        self.cchange()

        self.txt = del2(self.txt, i)
        self.lsp.pop(i)
        self.dxeff.pop(i)
        self.dxeff[i] = (self.chrs[i].dx if i < self.ncs else 0) + (
            self.chrs[i - 1].lsp if i > 0 else 0
        )
        self.cwd.pop(i)
        self.dy.pop(i)
        self.caph.pop(i)
        self.bshft.pop(i)

        if len(self.chrs) == 0:  # chunk now empty
            self.del_chk()

    def cchange(self):
        """
        Callback for character addition/deletion. Used to invalidate cached
        properties
        """
        self.charpos = None

        if self.line.ptxt.writtendx or self.line.ptxt.writtendy:
            self.line.ptxt.dchange = True

    @property
    def x(self):
        """Get effective x value"""
        if self.line and self.ncs > 0:
            lnx = self.line._xv if not self.line.continuex else self.line.x
            # checking for continuex early eliminates most unnecessary calls
            i = self.iis[0]  # first char
            return lnx[i] if i < len(lnx) else lnx[-1]
        return 0

    @property
    def y(self):
        """Get effective y value"""
        if self.line and self.ncs > 0:
            lny = self.line._yv if not self.line.continuey else self.line.y
            # checking for continuex early eliminates most unnecessary calls
            i = self.iis[0]  # first char
            return lny[i] if i < len(lny) else lny[-1]
        return 0
    
    @property
    def scf(self):
        """Get scale of first character"""
        return self.chrs[0].scf if self.ncs>0 else None

    def del_chk(self,updatedelta=True):
        """Deletes the chunk from the line."""
        for c in reversed(self.chrs):
            c.delc(updatedelta=updatedelta)
        if self in self.line.chks:
            self.line.chks.remove(self)

    def appendc(self, ncv, ncprop, ndx, ndy, totail=None):
        """Generates a new character and adds it to the end of the chunk."""
        # Add to document
        lchr = self.chrs[-1]
        # last character
        if totail is None:
            myi = lchr.loc.ind + 1
            # insert after last character
            if lchr.loc.typ == TYP_TEXT:
                lchr.loc.elem.text = (
                    lchr.loc.elem.text[0:myi] + ncv + lchr.loc.elem.text[myi:]
                )
            else:
                lchr.loc.elem.tail = (
                    lchr.loc.elem.tail[0:myi] + ncv + lchr.loc.elem.tail[myi:]
                )
        else:
            if totail.tail is None:
                totail.tail = ncv
            else:
                totail.tail = ncv + totail.tail

        # Make new character as a copy of the last one of the current chunk
        c = copy(lchr)
        c.chk = None # so we don't have problems during style setting
        c.c = ncv
        c.prop = ncprop
        c.cwd = ncprop.charw * c.utfs
        c.dx = ndx
        c.dy = ndy

        if totail is None:
            c.loc = CLoc(c.loc.elem, c.loc.typ, c.loc.ind + 1)  # updated location
        else:
            c.loc = CLoc(totail, TYP_TAIL, 0)
        c.sty = c.loc.sel.cspecified_style

        # Add to line
        myi = lchr.lnindex + 1  # insert after last character
        if len(self.line.x) > 0:
            newx = self.line.x[0:myi] + [None] + self.line.x[myi:]
            newx = newx[0 : len(self.line.chrs) + 1]
            self.line.write_xy(newx)

        self.line.insertc(c, myi)
        for i in range(myi + 1, len(self.line.chrs)):
            # need to increment index of subsequent objects with the same parent
            cha = self.line.chrs[i]
            if cha.loc.typ == c.loc.typ and cha.loc.elem == c.loc.elem:
                cha.loc.ind += 1
            if cha.chk is not None:
                cha.chk.iis[cha.windex] += 1
        # Add to chunk, recalculate properties
        self.addc(myi)

        # Adding a character causes the chunk to move if it's center- or right-justified
        # Need to fix this by adjusting position
        deltax = -self.line.anchfrac * self.line.chrs[myi].cwd
        if deltax != 0:
            newx = self.line.x
            newx[self.chrs[0].lnindex] -= deltax
            self.line.write_xy(newx)
        
        self.line.ptxt.write_dxdy()

    def append_chk(self, nchk, stype, maxspaces=None):
        """
        Adds a new chunk (possibly from another line) into the current one.
        Equivalent to typing it in
        """
        if len(nchk.chrs) > 0:
            # Calculate the number of spaces we need to keep the position constant
            # (still need to adjust for anchors)
            _, br1, _, bl2 = self.get_ut_pts(nchk)
            lchr = self.chrs[-1]
            # last character
            numsp = (bl2[0] - br1[0]) / (lchr.spw)
            numsp = max(0, round(numsp))
            if maxspaces is not None:
                numsp = min(numsp, maxspaces)

            for _ in range(numsp):
                self.appendc(
                    " ", lchr.line.ptxt.ctable.get_prop(" ", lchr.tsty), -lchr.lsp, 0
                )

            fchr = nchk.chrs[0]
            prevc = self.chrs[-1]
            for c in nchk.chrs:
                mydx = (c != fchr) * c.dx - prevc.lsp * (c == fchr)
                # use dx to remove lsp from the previous c
                c.delc()

                ntype = copy(stype)
                otype = c.sty.get("baseline-shift")
                if otype in ["super", "sub"] and stype == "normal":
                    ntype = otype

                # Nested tspans should be appended to the end of tails
                totail = None
                if self.chrs[-1].loc.sel != self.chrs[0].loc.sel:
                    cel = self.chrs[-1].loc.sel
                    while (
                        cel is not None
                        and cel.getparent() != self.chrs[0].loc.sel
                        and cel.getparent() != self.line.ptxt.textel
                    ):
                        cel = cel.getparent()
                    totail = cel

                self.appendc(c.c, c.prop, mydx, c.dy, totail=totail)
                newc = self.chrs[-1]
                
                # Make sure items on tails have right font size
                if totail is not None:
                    fsz, scf, utfs = composed_width(totail.getparent(), "font-size")
                    newc.utfs = utfs
                    newc.tfs = fsz
                    newc.cwd = newc.prop.charw * utfs
                    newc.caph = newc.prop.caph * utfs
                    newc.spw = newc.prop.spacew * utfs
                    newc.chk.cwd[newc.windex] = newc.cwd
                    newc.chk.caph[newc.windex] = newc.caph

                newc.parsed_pts_ut = [
                    vmultinv(self.transform.matrix, p[0], p[1]) for p in c.parsed_pts_t
                ]
                newc.parsed_pts_t = c.parsed_pts_t

                # Update the style
                newsty = None
                if c.sty != newc.sty or ntype in ["super", "sub"] or abs(c.scf - newc.scf)>1e-4:
                    newsty = c.sty
                    if ntype in ["super", "sub"]:
                        # newsty = c.sty
                        # Nativize super/subscripts
                        newsty["baseline-shift"] = (
                            "super" if ntype == "super" else "sub"
                        )
                        newsty["font-size"] = "65%"
                        # Leave size unchanged
                        # nsz = round((c.spw*c.scf)/(newc.spw*newc.scf)*100)
                        # newsty['font-size'] = str(nsz)+'%';

                        # Leave baseline unchanged (works)
                        # shft = round(-(bl2.y-br1.y)/self.tfs*100*self.scf);
                        # newsty['baseline-shift']= str(shft)+'%';
                    elif abs(c.scf - newc.scf)>1e-4:
                        # Prevent accidental font size changes when differently
                        # transformed
                        nsz = round((c.spw * c.scf) / (newc.spw * newc.scf) * 100)
                        # newsty['font-size'] = str(nsz)+'%';
                        newsty["font-size"] = (
                            f"{format(nsz, '.2f').rstrip('0').rstrip('.')}%"
                        )

                if newsty is not None:
                    newc.add_style(newsty, newfs=True)
                prevc = newc

    def get_ut_pts(self, chk2, current_pts=False):
        """Gets the coordinates of another chunk in my coordinate system."""
        if current_pts:
            c1uts = [c.pts_ut for c in self.chrs]
            c2uts = [c.pts_ut for c in chk2.chrs]
            c2ts = [c.pts_t for c in chk2.chrs]
        else:
            c1uts = [c.parsed_pts_ut for c in self.chrs]
            c2uts = [c.parsed_pts_ut for c in chk2.chrs]
            c2ts = [c.parsed_pts_t for c in chk2.chrs]

        minv = float("inf")
        chri = None
        
        for i in range(len(chk2.chrs)):
            if c2uts[i] is not None:
                if c2uts[i][0][0] < minv:
                    minv = c2uts[i][0][0]
                    chri = i

        bl2 = vmultinv(self.transform.matrix, c2ts[chri][0][0], c2ts[chri][0][1])
        tl2 = vmultinv(self.transform.matrix, c2ts[chri][1][0], c2ts[chri][1][1])

        maxv = float("-inf")
        chri = None
        for i in range(len(self.chrs)):
            if c1uts[i] is not None:
                if c1uts[i][3][0] > maxv:
                    maxv = c1uts[i][3][0]
                    chri = i

        tr1 = c1uts[chri][2]
        br1 = c1uts[chri][3]
        return tr1, br1, tl2, bl2

    def fix_merged_position(self):
        """
        Adjusts the position of merged text to account for small changes in
        chunk position that occur. This depends on alignment, so it is
        generally done after the final justification is set.
        """
        gcs = [c for c in self.chrs if c.c != " "]
        if len(gcs) > 0:
            omaxx = max([c.parsed_pts_ut[3][0] for c in gcs])
            ominx = min([c.parsed_pts_ut[0][0] for c in gcs])
            newptsut = [c.pts_ut for c in gcs]
            nmaxx = max([p[3][0] for p in newptsut])
            nminx = min([p[0][0] for p in newptsut])

            anfr = self.line.anchfrac
            deltaanch = (nminx * (1 - anfr) + nmaxx * anfr) - (
                ominx * (1 - anfr) + omaxx * anfr
            )
            # how much the final anchor moved
            if deltaanch != 0:
                newx = self.line.x
                newx[self.chrs[0].lnindex] -= deltaanch
                self.line.write_xy(newx)
                self.charpos = None
            self.line.ptxt.write_dxdy()

    def get_fs(self):
        """Returns the font size of the chunk."""
        return maxnone([c.tfs for c in self.chrs])

    tfs = property(get_fs)

    @property
    def spw(self):
        """Returns the space width of the chunk."""
        return maxnone([c.spw for c in self.chrs])

    def get_mch(self):
        """Returns the maximum character height of the chunk."""
        return maxnone(self.caph)

    mch = property(get_mch)

    @property
    def angle(self):
        """Returns the angle of the chunk."""
        return self.line.angle

    @property
    def unrenderedspace(self):
        """
        Returns True if the last character of a multichar line is a space
        and is not rendered.
        """
        lastspc = (
            self.ncs > 1
            and self.chrs[-1] == self.line.chrs[-1]
            and self.chrs[-1].c in [" ", "\u00a0"]
        )
        if not self.line.ptxt.isflow:
            return lastspc
        if lastspc:
            # For flows, is rendered when not the last line and line isn't broken
            lastln = (
                self.line.ptxt.lns[-1] == self.line and not self.line.ptxt.fparaafter
            )
            return lastln or self.line.broken
        return False

    @property
    def charpos(self):
        """
        Returns the character positions relative to the left side of the chunk.
        """
        if self._charpos is None:
            dadv = [0] * self.ncs
            if DIFF_ADVANCES:
                for i in range(1, self.ncs):
                    dadv[i] = self.chrs[i].dadvs(self.chrs[i - 1].c, self.chrs[i].c)*(self.dxeff[i]==0)
                    # default to 0 for chars of different style
                    # any dx value overrides differential advances

            chks = [self.cwd[i] + self.dxeff[i] + dadv[i] for i in range(self.ncs)]
            cstop = list(itertools.accumulate(chks))
            # cumulative width up to and including the ith char
            cstrt = [cstop[i] - self.cwd[i] for i in range(self.ncs)]

            cstrt = np.array(cstrt, dtype=float)
            cstop = np.array(cstop, dtype=float)

            chkw = cstop[-1]
            offx = -self.line.anchfrac * (
                chkw - self.unrenderedspace * self.chrs[-1].cwd
            )
            # offset of the left side of the chunk from the anchor
            chkx = self.x
            chky = self.y

            lftx = (chkx + cstrt + offx)[:, np.newaxis]
            rgtx = (chkx + cstop + offx)[:, np.newaxis]

            adyl = list(itertools.accumulate(self.dy))
            btmy = np.array(
                [chky + dy - bs for dy, bs in zip(adyl, self.bshft)], dtype=float
            )[:, np.newaxis]
            topy = np.array(
                [
                    chky + dy - bs - caph
                    for dy, caph, bs in zip(adyl, self.caph, self.bshft)
                ],
                dtype=float,
            )[:, np.newaxis]

            lx2 = float(min(lftx - self.dxeff[0]).squeeze())
            rx2 = float(lx2 + chkw)
            by2 = float(max(btmy).squeeze())
            ty2 = float(min(topy).squeeze())

            self._charpos = (lftx, rgtx, btmy, topy, lx2, rx2, by2, ty2)

        return self._charpos

    @charpos.setter
    def charpos(self, svi):
        """Sets the character positions and invalidates dependent properties."""
        if svi is None:  # invalidate self and dependees
            self._charpos = None
            self.pts_ut = None
            self.cpts_ut = None
            self.cpts_t = None

    @property
    def pts_ut(self):
        """Returns the untransformed bounding box of the chunk."""
        if self._pts_ut is None:
            (_, _, _, _, lx2, rx2, by2, ty2) = self.charpos
            self._pts_ut = [
                (lx2, by2),
                (lx2, ty2),
                (rx2, ty2),
                (rx2, by2),
            ]
        return self._pts_ut

    @pts_ut.setter
    def pts_ut(self, _):
        """Sets the untransformed bounding box and invalidates dependent properties."""
        if _ is None and self._pts_ut is not None:  # invalidate self and dependees
            self._pts_ut = None
            self.pts_t = None
            # self.cpts_ut = None

    @property
    def pts_t(self):
        """Returns the transformed bounding box of the chunk."""
        if self._pts_t is None:
            self._pts_t = [
                vmult(self.transform.matrix, p[0], p[1]) for p in self.pts_ut
            ]
        return self._pts_t

    @pts_t.setter
    def pts_t(self, _):
        """Sets the transformed bounding box and invalidates dependent properties."""
        if _ is None and self._pts_t is not None:  # invalidate self and dependees
            self._pts_t = None
            self.bbx = None
            # self.cpts_t = None

    @property
    def bbx(self):
        """Returns the bounding box of the chunk."""
        if self._bb is None:
            ptt = self.pts_t
            min_x = min(ptt[0][0], ptt[1][0], ptt[2][0], ptt[3][0])
            min_y = min(ptt[0][1], ptt[1][1], ptt[2][1], ptt[3][1])
            max_x = max(ptt[0][0], ptt[1][0], ptt[2][0], ptt[3][0])
            max_y = max(ptt[0][1], ptt[1][1], ptt[2][1], ptt[3][1])
            self._bb = bbox([min_x, min_y, max_x - min_x, max_y - min_y])
        return self._bb

    @bbx.setter
    def bbx(self, bbi):
        """Sets the bounding box and invalidates dependent properties."""
        if bbi is None:  # invalidate
            self._bb = None

    @property
    def cpts_ut(self):
        """Returns the untransformed bounding box of characters."""
        if self._cpts_ut is None:
            (lftx, rgtx, btmy, topy, _, _, _, _) = self.charpos
            n_rows = lftx.shape[0]
            self._cpts_ut = [
                tuple((coord[i][0], val[i][0]) for i in range(n_rows))
                for coord, val in zip(
                    (lftx, lftx, rgtx, rgtx), (btmy, topy, topy, btmy)
                )
            ]

        return self._cpts_ut

    @cpts_ut.setter
    def cpts_ut(self, svi):
        """Sets the untransformed bounding box of characters and invalidates
        dependent properties."""
        if svi is None:
            self._cpts_ut = None

    @property
    def cpts_t(self):
        """Returns the transformed bounding box of characters."""
        if self._cpts_t is None:
            (lftx, rgtx, btmy, topy, _, _, _, _) = self.charpos
            nch = len(lftx)
            pts = np.array(
                [
                    (coord[i][0], val[i][0], 1)
                    for coord, val in zip(
                        (lftx, lftx, rgtx, rgtx), (btmy, topy, topy, btmy)
                    )
                    for i in range(nch)
                ],
                dtype=float,
            )
            mat = np.array(self.transform.matrix + ((0, 0, 1),), dtype=float)

            tps = np.dot(mat, pts.T).T
            self._cpts_t = [
                tps[0:nch, 0:2],
                tps[nch : 2 * nch, 0:2],
                tps[2 * nch : 3 * nch, 0:2],
                tps[3 * nch : 4 * nch, 0:2],
            ]

        return self._cpts_t

    @cpts_t.setter
    def cpts_t(self, svi):
        """Sets the transformed bounding box of characters and invalidates
        dependent properties."""
        if svi is None:
            self._cpts_t = None


class TChar:
    """Represents a single character and its style."""

    def __init__(self, c, tfs, utfs, prop, sty, tsty, loc, line, dx, dy):
        """Initializes TChar with given parameters."""
        self.c = c
        self.tfs = tfs
        # transformed font size (uu)
        self.utfs = utfs
        # untransformed font size
        self.prop = prop
        # properties of a 1 uu character
        self.cwd = prop.charw * utfs
        # ut character width
        self._sty = sty
        # actual style
        self.tsty = tsty
        # true font style
        self.fsty = font_style(sty)
        # font style
        self.loc = loc
        # true location: [parent, TYP_TEXT or TYP_TAIL, index]
        self.caph = prop.caph * utfs
        # cap height (height of flat capitals like T)
        self.spw = prop.spacew * utfs
        # space width for style
        self.line = line
        line.chrs.append(self)
        self.lnindex = len(line.chrs) - 1
        # my line
        self.chk = None
        # my chunk (to be assigned)
        self.windex = None  # index in chunk
        # 'normal','super', or 'sub' (to be assigned)
        self._dx = dx
        self._dy = dy
        self._ax = None
        self._ay = None
        self.dadvs = lambda cL, cR: prop.dadvs.get((cL, cR), 0) * utfs
        self.parsed_pts_t = None
        self.parsed_pts_ut = None
        # for merging later
        self._lsp = TChar.lspfunc(self.sty)
        self._bshft = TChar.bshftfunc(self.sty, self.loc.sel)
        # letter spacing
        self.lhs = None
        # flow line-heights

    def copy(self, memo=None):
        """Creates a copy of the TChar instance."""
        if memo is None:
            memo = dict()
        ret = TChar.__new__(TChar)
        memo[self] = ret
        ret.__dict__.update(self.__dict__)
        ret.loc = CLoc(
            memo.get(self.loc.elem, self.loc.elem), self.loc.typ, self.loc.ind
        )
        ret.line = memo.get(self.line, self.line)
        return ret

    @property
    def dx(self):
        """Returns the dx property."""
        return self._dx

    @dx.setter
    def dx(self, dxi):
        """Sets the dx property and invalidates dependent properties."""
        if self._dx != dxi:
            self._dx = dxi
            if self.chk is not None:
                self.chk.charpos = None  # invalidate
                i = self.windex
                chk = self.chk
                chk.dxeff[i] = (chk.chrs[i].dx if i < chk.ncs else 0) + (
                    chk.chrs[i - 1].lsp if i > 0 else 0
                )
            self.line.ptxt.dchange = True

    @property
    def dy(self):
        """Returns the dy property."""
        return self._dy

    @dy.setter
    def dy(self, dxi):
        """Sets the dy property and invalidates dependent properties."""
        if self._dy != dxi:
            self._dy = dxi
            if self.chk is not None:
                self.chk.dy[self.windex] = dxi
            self.line.ptxt.dchange = True
            
    @property
    def ax(self):
        """Returns the ax property."""
        return self._ax

    @ax.setter
    def ax(self, axi):
        """Sets the ax property and invalidates dependent properties."""
        if self._ax != axi:
            self._ax = axi
            self.line.ptxt.achange = True

    @property
    def ay(self):
        """Returns the ay property."""
        return self._ay

    @ay.setter
    def ay(self, axi):
        """Sets the dy property and invalidates dependent properties."""
        if self._ay != axi:
            self._ay = axi
            self.line.ptxt.achange = True

    @property
    def sty(self):
        """Returns the style of the character."""
        # Character style
        return self._sty

    @sty.setter
    def sty(self, styi):
        """Sets the style of the character and updates dependent properties."""
        self._sty = styi
        self.lsp = TChar.lspfunc(self._sty)
        self.bshft = TChar.bshftfunc(self._sty, self.loc.sel)

        self.fsty = font_style(styi)
        self.tsty = true_style(styi)

    @staticmethod
    def lspfunc(styv):
        """Returns the letter spacing for the given style."""
        if "letter-spacing" in styv:
            lspv = styv.get("letter-spacing")
            if "em" in lspv:  # em is basically the font size
                fs2 = styv.get("font-size")
                if fs2 is None:
                    fs2 = "12px"
                lspv = float(lspv.strip("em")) * ipx(fs2)
            else:
                lspv = ipx(lspv) or 0
        else:
            lspv = 0
        return lspv

    @property
    def lsp(self):
        """Returns the letter spacing of the character."""
        return self._lsp

    @lsp.setter
    def lsp(self, sval):
        """Sets the letter spacing and invalidates dependent properties."""
        if sval != self._lsp:
            self._lsp = sval
            if self.chk is not None:
                self.chk.charpos = None
                i = self.windex
                chk = self.chk
                chk.lsp[i] = sval
                chk.dxeff[i + 1] = (chk.chrs[i + 1].dx if i < chk.ncs - 1 else 0) + (
                    chk.chrs[i].lsp if i < chk.ncs else 0
                )

    @staticmethod
    def bshftfunc(styv, strtel):
        """Calculates the baseline shift for the given style."""
        if "baseline-shift" in styv:
            # Find all ancestors with baseline-shift
            bsancs = []
            cel = strtel
            while cel is not None and "baseline-shift" in cel.cspecified_style:
                bsancs.append(cel)
                cel = cel.getparent()

            # Starting from the most distant ancestor, calculate relative
            # baseline shifts (i.e., how much each element is raised/lowered
            # from the last block of text)
            relbs = []
            for att in reversed(bsancs):
                if "baseline-shift" in att.cstyle:
                    relbs.append(TChar.get_baseline(att.cstyle, att.getparent()))
                else:
                    # When an element has a baseline-shift from inheritance
                    # but no baseline-shift is specified, implicitly gets the
                    # sum of the previous values
                    relbs.append(sum(relbs))
            bshft = sum(relbs)
        else:
            bshft = 0
        return bshft

    # Character baseline shift
    @property
    def bshft(self):
        """Returns the baseline shift of the character."""
        return self._bshft

    @bshft.setter
    def bshft(self, sval):
        """Sets the baseline shift and invalidates dependent properties."""
        if sval != self._bshft:
            self._bshft = sval
            if self.chk is not None:
                self.chk.charpos = None
                self.chk.bshft[self.windex] = sval

    @staticmethod
    def get_baseline(styin, fsel):
        """Gets the baseline shift value based on style and font size."""
        bshft = styin.get("baseline-shift", "0")
        if bshft == "super":
            bshft = "40%"
        elif bshft == "sub":
            bshft = "-20%"
        if "%" in bshft:  # relative to parent
            fs2, sf2, _ = composed_width(fsel, "font-size")
            bshft = fs2 / sf2 * float(bshft.strip("%")) / 100
        else:
            bshft = ipx(bshft) or 0
        return bshft
    
    @property
    def scf(self):
        """Returns the scale from the utfs to tfs."""
        return self.tfs / self.utfs
    
    def __str__(self):
        return str((self.c,self.loc.elem.get_id(), self.loc.typ, self.loc.ind))

    def delc(self,updatedelta=True):
        """Deletes the character from the document and its chunk/line."""
        # Deleting a character causes the chunk to move if it's center- or
        # right-justified. Adjust position to fix
        lncs = self.line.chrs
        myi = self.lnindex  # index in line

        # Differential kerning affect on character width
        dko1 = dko2 = dkn = 0
        if myi < len(lncs) - 1:
            dko2 = self.dadvs(lncs[myi].c, lncs[myi + 1].c)  # old from right
            if myi > 0:
                dkn = self.dadvs(lncs[myi - 1].c, lncs[myi + 1].c)  # new
        if myi > 0:
            dko1 = self.dadvs(lncs[myi - 1].c, lncs[myi].c)  # old from left
        tdk = dko1 + dko2 - dkn

        cwo = self.cwd + tdk + self._dx + self.lsp * (self.windex != 0)
        if self.chk.unrenderedspace and self.chk.chrs[-1] == self:
            if len(self.chk.chrs) > 1 and self.chk.chrs[-2].c != " ":
                cwo = tdk
                # Deletion will not affect position
                # Weirdly dkerning from unrendered spaces still counts

        if self == self.chk.chrs[0]:  # from beginning of line
            deltax = (self.line.anchfrac - 1) * cwo
        else:  # assume end of line
            deltax = self.line.anchfrac * cwo

        lnx = self.line.x
        changedx = False
        if deltax != 0:
            chkidx = self.line.chks.index(self.chk)
            if chkidx < len(lnx) and lnx[chkidx] is not None:
                lnx[chkidx] -= deltax
                changedx = True

        # Delete from document
        if self.loc.typ == TYP_TEXT:
            self.loc.elem.text = (
                self.loc.elem.text[: self.loc.ind]
                + self.loc.elem.text[self.loc.ind + 1 :]
            )
        else:
            self.loc.elem.tail = (
                self.loc.elem.tail[: self.loc.ind]
                + self.loc.elem.tail[self.loc.ind + 1 :]
            )

        if len(lnx) > 1 and myi < len(lnx):
            if myi < len(lnx) - 1 and lnx[myi] is not None and lnx[myi + 1] is None:
                newx = (
                    lnx[: myi + 1] + lnx[myi + 2 :]
                )  # next x is None, delete that instead
            elif myi == len(lnx) - 1 and len(lncs) > len(lnx):
                newx = lnx  # last x, characters still follow
            else:
                newx = lnx[:myi] + lnx[myi + 1 :]

            lnx = newx[: len(lncs) - 1]
            # we haven't deleted the char yet, so make it len-1 long
            changedx = True
        if changedx:
            self.line.write_xy(lnx)

        # Delete from line
        _ = [
            setattr(ca.loc, "ind", ca.loc.ind - 1)
            for ca in lncs[myi + 1 :]
            if ca.loc.typ == self.loc.typ and ca.loc.elem == self.loc.elem
        ]
        _ = [
            ca.chk.iis.__setitem__(ca.windex, ca.chk.iis[ca.windex] - 1)
            for ca in lncs[myi + 1 :]
            if ca.chk is not None
        ]
        _ = [setattr(c, "lnindex", c.lnindex - 1) for c in self.line.chrs[myi + 1 :]]

        lncs[myi].lnindex = None
        self.line.chrs = lncs[:myi] + lncs[myi + 1 :]

        if len(self.line.chrs) == 0:  # line now empty, can delete
            self.line.dell()

        # Remove from chunk
        self.chk.removec(self)
        
        # Update the dx/dy value in the ParsedText
        if updatedelta:
            self.line.ptxt.write_dxdy()

    def add_style(self, sty, setdefault=True, newfs=False):
        """Adds a style to the character by wrapping it in a new Tspan."""
        span = Tspan if self.line.ptxt.textel.tag == TEtag else inkex.FlowSpan
        t = span()
        t.text = self.c

        prt = self.loc.elem
        if self.loc.typ == TYP_TEXT:
            tbefore = prt.text[0 : self.loc.ind]
            tafter = prt.text[self.loc.ind + 1 :]
            prt.text = tbefore
            prt.insert(0, t)
            t.tail = tafter
        else:
            tbefore = prt.tail[0 : self.loc.ind]
            tafter = prt.tail[self.loc.ind + 1 :]
            prt.tail = tbefore
            grp = prt.getparent()
            # parent is a Tspan, so insert it into the grandparent
            grp.insert(grp.index(prt) + 1, t)
            # after the parent

            t.tail = tafter

        self.line.ptxt.tree = None  # invalidate

        myi = self.lnindex
        for i in range(
            myi + 1, len(self.line.chrs)
        ):  # for characters after, update location
            cha = self.line.chrs[i]
            if cha.loc.elem == self.loc.elem and cha.loc.typ == self.loc.typ:
                cha.loc = CLoc(t, TYP_TAIL, i - myi - 1)
        self.loc = CLoc(t, TYP_TEXT, 0)  # update my own location

        # When the specified style has something new span doesn't, are inheriting and
        # need to explicitly assign the default value
        styset = Style(sty)
        newspfd = t.cspecified_style
        for att in newspfd:
            if att not in styset and setdefault:
                styset[att] = default_style_atts.get(att)

        t.cstyle = styset
        self.sty = styset
        if newfs:
            fsz, scf, _ = composed_width(self.loc.sel, "font-size")
            self.utfs = fsz / scf
            self.tfs = fsz
            self.cwd = self.prop.charw * self.utfs
            self.chk.cwd[self.windex] = self.cwd
            self.caph = self.prop.caph * self.utfs
            self.chk.caph[self.windex] = self.caph
            self.chk.charpos = None

    @property
    def pts_ut(self):
        """Returns the untransformed bounding box of the character."""
        myi = self.windex
        cput = self.chk.cpts_ut
        ret_pts_ut = [
            (cput[0][myi][0], cput[0][myi][1]),
            (cput[1][myi][0], cput[1][myi][1]),
            (cput[2][myi][0], cput[2][myi][1]),
            (cput[3][myi][0], cput[3][myi][1]),
        ]
        return ret_pts_ut

    @property
    def pts_t(self):
        """Returns the transformed bounding box of the character."""
        myi = self.windex
        cpt = self.chk.cpts_t
        ret_pts_t = [
            (cpt[0][myi][0], cpt[0][myi][1]),
            (cpt[1][myi][0], cpt[1][myi][1]),
            (cpt[2][myi][0], cpt[2][myi][1]),
            (cpt[3][myi][0], cpt[3][myi][1]),
        ]
        return ret_pts_t

    @property
    def pts_ut_ink(self):
        """Returns the untransformed ink bounding box of the character."""
        put = self.pts_ut
        nwd = self.prop.inkbb[2] * self.utfs
        nht = self.prop.inkbb[3] * self.utfs
        x = put[0][0] + self.prop.inkbb[0] * self.utfs
        y = put[0][1] + self.prop.inkbb[1] * self.utfs + nht
        return [(x, y), (x, y - nht), (x + nwd, y - nht), (x + nwd, y)]


def del2(x, ind):
    """deletes an index from a list"""
    return x[:ind] + x[ind + 1 :]


def extendind(x, ind, val, default=None):
    """indexes a matrix, extending it if necessary"""
    if ind >= len(x):
        x += [default] * (ind + 1 - len(x))
    x[ind] = val
    return x


def sortnone(x):
    """sorts an x skipping Nones"""
    rem = list(range(len(x)))
    minxrem = min([x[r] for r in rem if x[r] is not None])
    i = min([r for r in rem if x[r] == minxrem])
    sord = [i]
    rem.remove(i)
    while len(rem) > 0:
        if i == len(x) - 1 or x[i + 1] is not None:
            minxrem = min([x[r] for r in rem if x[r] is not None])
            i = min([r for r in rem if x[r] == minxrem])
            sord += [i]
        else:
            i += 1
        rem.remove(i)
    return sord


class CProp:
    """
    A class representing the properties of a single character
    It is meant to be immutable...do not modify attributes
    """

    __slots__ = ("char", "charw", "spacew", "caph", "dadvs", "inkbb")

    def __init__(self, char, cwd, spw, caph, dadvs, inkbb):
        """Initializes CProp with given parameters."""
        self.char = char
        self.charw = cwd
        # character width
        self.spacew = spw
        # space width
        self.caph = caph
        # cap height
        self.dadvs = dadvs
        # table of how much extra width a preceding character adds to me
        self.inkbb = inkbb

    def __mul__(self, scl):
        """Scales the character properties by a given factor."""
        dadv2 = {k: val * scl for k, val in self.dadvs.items()}
        inkbb2 = [val * scl for val in self.inkbb]
        return CProp(
            self.char,
            self.charw * scl,
            self.spacew * scl,
            self.caph * scl,
            dadv2,
            inkbb2,
        )

    @property
    def __dict__(self):
        """Returns a dictionary of character properties."""
        return {
            "char": self.char,
            "charw": self.charw,
            "spacew": self.spacew,
            "caph": self.caph,
            "inkbb": self.inkbb,
        }


class CLoc:
    """Represents the location of a single character in the SVG."""

    __slots__ = ("elem", "typ", "ind", "sel")

    def __init__(self, elem, typ, ind):
        """Initializes CLoc with given parameters."""
        self.elem = elem
        # the element it belongs to
        self.typ = typ
        # TYP_TEXT or TYP_TAIL
        self.ind = ind
        # its index
        self.sel = elem if typ == TYP_TEXT else elem.getparent()
        # where style comes from

    def copy(self, memo):
        """Creates a copy of the CLoc instance."""
        ret = CLoc.__new__(CLoc)
        memo[self] = ret

        ret.elem = memo[self.elem]
        ret.typ = self.typ
        ret.ind = self.ind
        ret.sel = memo[self.sel]
        return ret

    def __eq__(self, other):
        """Checks equality with another CLoc instance."""
        return (
            self.elem == other.elem and self.typ == other.typ and self.ind == other.ind
        )

    def __hash__(self):
        """Returns the hash value of the CLoc instance."""
        return hash((self.elem, self.typ, self.ind))


class CharacterTable:
    """Represents the properties of a collection of characters."""

    def __init__(self, els):
        """Initializes CharacterTable with a list of elements."""
        self.els = els
        self.root = els[0].croot if len(els) > 0 else None
        self.tstyset, self.pchrset, self.fstyset, self.cstys = (
            CharacterTable.collect_characters(els)
        )

        # HASPANGO = False; os.environ["HASPANGO"]='False'
        if HASPANGO:
            # Prefer to measure with Pango if we have it (faster, more accurate)
            self.ctable = self.measure_characters()
        else:
            # Can also extract directly using fonttools, which is pure Python
            self.ctable = self.extract_characters()

        self.mults = dict()
        self._ftable = None

    @staticmethod
    def collect_characters(els):
        """Finds all the characters in a list of elements."""
        fstyset = dict()  # set of characters in a given font style
        txtfsty = []
        for elem in els:
            tree = TextTree(elem)
            for _, _, _, sel, txt in tree.dgenerator():
                if txt is not None and len(txt) > 0:
                    sty = sel.cspecified_style
                    fsty = font_style(sty)
                    fstyset.setdefault(fsty, set()).update(txt + " ")
                    txtfsty.append((txt, fsty))

        cstys = dict()  # cstys[fsty][c] looks up a character's true style
        tstyset = dict()  # set of characters in a given true style
        for fsty, chrs in fstyset.items():
            tfbc = fcfg.get_true_font_by_char(fsty, chrs)
            cstys[fsty] = tfbc
            tstyset.setdefault(true_style(fsty), set()).update(chrs)
            for c, csty in tfbc.items():
                cstys.setdefault(csty, dict()).__setitem__(c, csty)
                tstyset.setdefault(csty, set()).update({c, " "})

        pchrset = dict()
        # set of characters that precede a char in a true style
        # used to apply differential kerning
        for txt, fsty in txtfsty:
            for j in range(1, len(txt)):
                csty = cstys[fsty][txt[j]]
                pchrset.setdefault(csty, dict())
                if csty == cstys[fsty][txt[j - 1]]:
                    pchrset[csty].setdefault(txt[j], set()).update({txt[j - 1], " "})

        return tstyset, pchrset, fstyset, cstys

    def extract_characters(self):
        """
        Direct extraction of character metrics from the font file using fonttools
        fonttools is pure Python, so this usually works
        """
        badchars = {"\n", "\r"}
        ret = dict()
        for sty, chrs in self.tstyset.items():
            if sty is not None:
                bdcs = {c for c in chrs if c in badchars}  # unusual chars
                gcs = {c for c in chrs if c not in badchars}
                chrfs = fcfg.get_true_font_by_char(sty, gcs)
                fntcs = dict()  # font: corresponding characters
                for k, val in chrfs.items():
                    fntcs.setdefault(val, []).append(k)

                if None in fntcs:  # unrendered characters are bad
                    bdcs.update(fntcs[None])
                    gcs = gcs - set(fntcs[None])
                    del fntcs[None]

                ret[sty] = dict()
                for fnt, chs in fntcs.items():
                    ftfnt = fcfg.get_fonttools_font(fnt)
                    if sty in self.pchrset:
                        pct2 = {
                            k: val for k, val in self.pchrset[sty].items() if k in chs
                        }
                    else:
                        pct2 = dict()
                    advs, dadv, inkbbs = ftfnt.get_char_advances(chs, pct2)
                    for c in chs:
                        cwd = advs[c]
                        caph = ftfnt.cap_height
                        # dr = 0
                        inkbb = inkbbs[c]
                        ret[sty][c] = CProp(c, cwd, None, caph, dadv, inkbb)
                spc = ret[sty][" "]
                for c in ret[sty]:
                    ret[sty][c].spacew = spc.charw
                    ret[sty][c].caph = spc.caph
                for bdc in bdcs:
                    ret[sty][bdc] = CProp(
                        bdc, 0, spc.charw, spc.caph, dict(), [0, 0, 0, 0]
                    )
            else:
                ret[sty] = dict()
                for c in self.tstyset[None]:
                    ret[sty][c] = CProp(c, 0, 0, 0, dict(), [0, 0, 0, 0])
        return ret

    def measure_characters(self):
        """
        Uses Pango to measure character properties by rendering them on an unseen
        context. Requires GTK Python bindings, generally present in Inkscape 1.1 and
        later. If Pango is absent, extract_characters will be called instead.

        Generates prefixed, suffixed copies of each string, compares them to a blank
        version without any character. This measures the logical advance, i.e., the
        width including intercharacter space. Width corresponds to a character with
        a composed font size of 1 uu.
        """
        cnt = 0
        pstrings = dict()

        def make_string(c, sty):
            nonlocal cnt
            cnt += 1
            pstrings["text" + str(cnt)] = (c, sty)
            return "text" + str(cnt)

        class StringInfo:
            """Stores metadata on strings"""

            def __init__(self, strval, strid, dadv, bareid=None):
                self.strval = strval
                self.strid = strid
                self.dadv = dadv
                self.bareid = bareid

        badchars = {"\n": " ", "\r": " "}

        def effc(c):
            return badchars.get(c, c)

        ixes = dict()
        validtstyset = {
            sty: chrs for sty, chrs in self.tstyset.items() if sty is not None
        }
        for sty in validtstyset:
            chrs = [chr(c) for c in fcfg.fontcharsets[sty]]
            if "=" in chrs:
                bufc = "="
            elif "M" in chrs:
                bufc = "M"
            else:
                bufc = min([ch for ch in chrs if ord(ch) >= ord("A")], key=ord)
            prefix = "I" + bufc
            suffix = bufc + "I"
            # Use an equals sign to eliminate differential kerning effects
            # (characters like '=' rarely have differential kerning), then I for
            # capital height.

            empty = prefix + suffix
            pistr = prefix + "pI" + suffix
            # Add 'pI' as test characters. 'p' provides the font's descender
            # (how much the tail descends), and 'I' gives cap height
            # (how tall capital letters are).
            ixes[sty] = (prefix, suffix, empty, pistr)

        ctbl = dict()
        bareids = []
        for sty, chrs in validtstyset.items():
            prefix, suffix, empty, pistr = ixes[sty]
            ctbl[sty] = dict()
            for myc in chrs:
                t = make_string(prefix + effc(myc) + suffix, sty)
                tbare = make_string(effc(myc), sty)
                bareids.append(tbare)
                dadv = dict()
                if DIFF_ADVANCES:
                    for pchr in chrs:
                        if (
                            sty in self.pchrset
                            and myc in self.pchrset[sty]
                            and pchr in self.pchrset[sty][myc]
                        ):
                            tpc = make_string(
                                prefix + effc(pchr) + effc(myc) + suffix, sty
                            )
                            # precede by all chars of the same style
                            dadv[pchr] = tpc
                ctbl[sty][myc] = StringInfo(myc, t, dadv, tbare)

            ctbl[sty][pistr] = StringInfo(pistr, make_string(pistr, sty), dict())
            ctbl[sty][empty] = StringInfo(empty, make_string(empty, sty), dict())

        # Pango querying doesn't multithread well
        lock = threading.Lock()
        lock.acquire()
        try:
            pngr = PangoRenderer()
            nbb = dict()
            for sty in ctbl:
                joinch = " "
                mystrs = [val[0] for k, val in pstrings.items() if val[1] == sty]
                myids = [k for k, val in pstrings.items() if val[1] == sty]

                success, metrics = pngr.set_text_style(sty)
                if not (success):
                    lock.release()
                    return self.extract_characters()
                joinedstr = joinch.join(mystrs) + joinch + prefix

                # We need to render all the characters, but we don't
                # need all of their extents. For most of them we just
                # need the first character, unless the following string
                # has length 1 (and may be differently differentially kerned)
                modw = [
                    any(
                        len(mystrs[i]) == 1
                        for i in range(i, i + 2)
                        if 0 <= i < len(mystrs)
                    )
                    for i in range(len(mystrs))
                ]
                needexts = [
                    "1"
                    if len(s) == 1
                    else "1" + "0" * (len(s) - 2) + ("1" if modw[i] else "0")
                    for i, s in enumerate(mystrs)
                ]
                needexts2 = "0".join(needexts) + "1" + "1" * len(prefix)
                pngr.render_text(joinedstr)
                exts, _ = pngr.get_character_extents(metrics[1], needexts2)

                spw = exts[-len(prefix) - 1][0][2]
                cnt = 0
                x = 0
                for i, mystr in enumerate(mystrs):
                    if modw[i]:
                        altw = (
                            exts[cnt + len(mystr) - 1][0][0]
                            + exts[cnt + len(mystr) - 1][0][2]
                            - exts[cnt][0][0]
                        )
                    else:
                        altw = (
                            exts[cnt + len(mystr) + 1][0][0] - exts[cnt][0][0] - spw
                        )
                    wdt = altw

                    firstch = exts[cnt]
                    (xbr, ybr, wbr, hbr) = tuple(firstch[2])
                    if myids[i] not in bareids:
                        xbr = x
                        wbr = wdt
                        # use logical width

                    nbb[myids[i]] = [val * TEXTSIZE for val in [xbr, ybr, wbr, hbr]]
                    cnt += len(mystr) + len(joinch)
                    x += wdt
        finally:
            lock.release()

        dadv = dict()
        for sty, chd in ctbl.items():
            prefix, suffix, empty, pistr = ixes[sty]
            for i in chd:
                chd[i].bbx = bbox(nbb[chd[i].strid])
                if DIFF_ADVANCES:
                    precwidth = dict()
                    for j in chd[i].dadv:
                        precwidth[j] = bbox(nbb[chd[i].dadv[j]]).w
                        # width including the preceding character and extra kerning
                    chd[i].precwidth = precwidth

            if DIFF_ADVANCES:
                dadv[sty] = dict()
                for i in chd:
                    mcw = chd[i].bbx.w - chd[empty].bbx.w  # my character width
                    for j in chd[i].precwidth:
                        pcw = chd[j].bbx.w - chd[empty].bbx.w  # preceding char width
                        bcw = chd[i].precwidth[j] - chd[empty].bbx.w  # both char widths
                        dadv[sty][j, chd[i].strval] = bcw - pcw - mcw
                        # preceding char, then next char

        for sty, chd in ctbl.items():
            prefix, suffix, empty, pistr = ixes[sty]
            blnkwd = chd[empty].bbx.w
            spw = chd[" "].bbx.w - blnkwd  # space width
            caph = -chd[empty].bbx.y1
            # cap height is the top of I (relative to baseline)

            dadvscl = dict()
            if DIFF_ADVANCES:
                for k in dadv[sty]:
                    dadvscl[k] = dadv[sty][k] / TEXTSIZE

            for i in chd:
                cwd = chd[i].bbx.w - blnkwd
                # character width (full, including extra space on each side)
                if chd[i].bareid in nbb:
                    inkbb = nbb[chd[i].bareid]
                else:
                    # whitespace: make zero-width
                    inkbb = [chd[i].bbx.x1, chd[i].bbx.y1, 0, 0]

                if chd[i].strval in badchars:
                    cwd = 0
                chd[i] = CProp(
                    chd[i].strval,
                    cwd / TEXTSIZE,
                    spw / TEXTSIZE,
                    caph / TEXTSIZE,
                    dadvscl,
                    [val / TEXTSIZE for val in inkbb],
                )
        if None in self.tstyset:
            ctbl[None] = dict()
            for c in self.tstyset[None]:
                ctbl[None][c] = CProp(c, 0, 0, 0, dict(), [0, 0, 0, 0])
        return ctbl

    def __str__(self):
        ret = ""
        for sty in self.ctable:
            ret += str(sty) + "\n"
            val = None
            for c, val in self.ctable[sty].items():
                ret += "    " + c + " : " + str(vars(val)) + "\n"
            if val is not None:
                ret += "    " + str(val.dadvs)
        return ret

    @staticmethod
    def flowy(sty):
        """Returns the font's ascent value for the given style."""
        return fcfg.get_fonttools_font(sty)._ascent

    def get_prop(self, char, sty):
        """Returns the properties of a character for a given style."""
        try:
            return self.ctable[sty][char]
        except KeyError as excp:
            reset_msg = (
                "This probably means that new text was generated and the SVG's "
                "character table is outdated. Reset it by setting"
            )
            reset_action = "self.svg.char_table = None"
            frequency_msg = (
                "(This can take a long time, so best practice is to do this as few "
                "times as is possible.)"
            )
            if sty not in self.ctable:
                debug("No style matches found!")
                debug(reset_msg)
                debug("     " + reset_action)
                debug(frequency_msg)
                debug("\nCharacter: " + char)
                debug("Style: " + str(sty))
                debug("Existing styles: " + str(list(self.ctable.keys())))
            else:
                debug("No character matches!")
                debug(reset_msg)
                debug("     " + reset_action)
                debug(frequency_msg)
                debug("\nCharacter: " + char)
                debug("Style: " + str(sty))
                debug("Existing chars: " + str(list(self.ctable[sty].keys())))
            raise KeyError from excp

    def get_prop_mult(self, char, sty, scl):
        """Returns the scaled properties of a character for a given style."""
        try:
            return self.mults[(char, sty, scl)]
        except KeyError:
            self.mults[(char, sty, scl)] = self.get_prop(char, sty) * scl
            return self.mults[(char, sty, scl)]


def wstrip(txt):
    """strip whitespaces"""
    return txt.translate({ord(c): None for c in " \n\t\r"})


def deleteempty(elem):
    """
    Recursively delete empty elements
    Tspans are deleted if they're totally empty, TextElements are deleted
    if they contain only whitespace
    """
    anydeleted = False
    for k in list(elem):
        dcsndt = deleteempty(k)
        anydeleted |= dcsndt
    txt = elem.text
    tail = elem.tail
    if (
        (txt is None or len(txt) == 0)
        and (tail is None or len(tail) == 0)
        and len(elem) == 0
    ):
        elem.delete()
        anydeleted = True
        # delete anything empty
    elif elem.tag == TEtag:
        if all(
            (dcsndt.text is None or len(wstrip(dcsndt.text)) == 0)
            and (dcsndt.tail is None or len(wstrip(dcsndt.tail)) == 0)
            for dcsndt in elem.descendants2()
        ):
            elem.delete()
            anydeleted = True
            # delete any text elements that are just white space
    return anydeleted


def maxnone(x):
    """Returns the maximum value of a list, or None if the list is empty."""
    if len(x) > 0:
        return max(x)
    return None


def xyset(elem, xyt, val):
    """
    A fast setter for 'x', 'y', 'dx', and 'dy' that uses lxml's set directly and
    converts arrays to a string
    """
    if not (val):
        elem.attrib.pop(xyt, None)  # pylint: disable=no-member
    else:
        EBset(elem, xyt, ' '.join('%s' % v for v in val))

def remove_position_overflows(el):
    """
    Normally Inkscape only produces multiple position attributes (x,y,dx,dy) on a
    tspan corresponding to the number of characters. It does support more than this,
    but that is a somewhat pathological case that makes editing difficult.
    Removing this prior to parsing simplifies the logic needed.
    """
    xyvs = {(d, patt) : ParsedText.get_xy(d, patt) for d in el.descendants2() for patt in ['x','y','dx','dy']}
    anyoverflow = False
    ttree = [v for v in TextTree(el).dgenerator()]
    for ddi0, typ0, src0, sel0, txt0 in ttree:
        if typ0==TYP_TEXT:
            for patt in ['x','y','dx','dy']:
                anyoverflow |= (len(xyvs[src0,patt])>1 and 
                                ((txt0 is not None and len(xyvs[src0,patt])>len(txt0)) 
                                 or (txt0 is None)))
                # inkex.utils.debug((anyoverflow, patt,src0.get_id(),typ0))
    
    
    if anyoverflow:       
        toplevels = list(el)
        xvs, yvs, dxs, dys = [[] for _ in range(4)]
        pos = {'x':xvs,'y':yvs,'dx':dxs,'dy':dys}
        diffs = ['dx','dy']
        topidx = 0
        for ddi0, typ0, src0, sel0, txt0 in ttree:
            if typ0==TYP_TEXT:
                for patt in ['x','y','dx','dy']:
                    xyv = xyvs[src0, patt]
                    # Objects lower in the descendant list override ancestors
                    # dx and dy don't affect flows
                    if len(xyv) > 0 and xyv[0] is not None:
                        if patt in diffs or len(xyv)>1:
                            src0.set(patt,None)  # leave individual x,y alone
                        cntd = 0
                        cntl = 0
                        for _, typ, src, _, txt in TextTree(el).dgenerator(subel=src0):
                            if (
                                typ == TYP_TAIL
                                and src.get("sodipodi:role") == "line"
                                and src in toplevels
                            ):
                                cntd += 1
                                # top-level Tspans have an implicit CR at
                                # the beginning of the tail
                            
                            if txt is not None:
                                srtd = cntd
                                stpd = min(len(xyv),cntd+len(txt))
                                srtl = topidx+cntl
                                stpl = topidx+cntl+stpd-srtd
                                
                                if stpl>=len(pos[patt]):
                                    pos[patt] += [None] * (stpl-len(pos[patt])+1)
                                pos[patt][srtl:stpl] = xyv[srtd:stpd]
                                cntd += len(txt)
                                cntl += len(txt)
                            if cntd >= len(xyv):
                                break
            if txt0 is not None:
                topidx += len(txt0)
        
        topidx = 0
        for ddi, typ, src, sel, txt in ttree:
            if txt is not None:
                wrapped_tail = False
                for patt in ['x','y','dx','dy']:
                    vals = [v for v in pos[patt][topidx:topidx+len(txt)] if v is not None]
                    if len(vals)>0:
                        if typ==TYP_TAIL and not wrapped_tail:
                            # Tails need to be wrapped in a new Tspan
                            src =  wrap_string(src,typ)
                            wrapped_tail = True

                        if not(len(vals)==1 and patt not in diffs and wrapped_tail):
                            # wrapping a tail could mess with sprl if single x/y specified
                            xyset(src, patt, vals)
                topidx += len(txt)
                
def wrap_string(src,typ):
    ''' Wrap a string in a new Tspan/FlowSpan'''
    if typ==TYP_TAIL:
        span = inkex.Tspan if src.tag in TEtags else inkex.FlowSpan
        t = span()
        t.text = src.tail
        src.tail = None
        src.getparent().insert(src.getparent().index(src) + 1, t)
    else:
        span = inkex.Tspan if src.tag in TEtags else inkex.FlowSpan
        t = span()
        t.text = src.text
        src.text = None
        src.insert(0, t)
    return t

def trim_list(lst,val):
    """ Trims any values from the end of a list equal to val """
    trim = lst[:len(lst) - next((i for i, x in enumerate(reversed(lst)) if x != val), len(lst))]
    return trim if len(trim)>0 else None