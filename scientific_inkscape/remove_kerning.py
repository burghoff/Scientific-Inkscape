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

# for debugging parser
DEBUG_PARSER = True
DEBUG_PARSER = False

# for checking why elements aren't merging
DEBUG_MERGE = True
DEBUG_MERGE = False

NUM_SPACES = 1.0
# number of spaces beyond which text will be merged/split
XTOLEXT = 0.6
# x tolerance (number of spaces), let be big since there are
# kerning inaccuracies (as big as -0.56 in Whitney)
YTOLEXT = 0.1
# y tolerance (fraction of cap height), should be pretty small
XTOLMKN = 1.5
# left tolerance for manual kerning removal, used to be huge but is now tighter
# since differential kerning was made default for PDF
XTOLMKP = (
    0.99
)
# right tolerance for manual kerning removal, should be fairly open-minded
YTOLMK = .01
XTOLSPLIT = 0.5
# tolerance for manual kerning splitting, should be fairly tight
SUBSUPER_THR = 0.99
# ensuring sub/superscripts are smaller helps reduce false merges
SUBSUPER_YTHR = 1 / 3
# superscripts must be at least 1/3 of the way above the baseline to merge
# (1/3 below cap for sub)

import inkex
import inkex.text.parser as tp

import os, sys, re

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh


def remove_kerning(
    els,
    removemanual,
    mergesupersub,
    splitdistant,
    mergenearby,
    justification=None,
    debugparser=False,
):
    tels = [el for el in els if isinstance(el, (inkex.TextElement, inkex.FlowRoot))]
    if len(tels) > 0:
        tels[0].croot.make_char_table(tels)
    if DEBUG_PARSER or debugparser:
        for el in tels:
            el.parsed_text.make_highlights("char")
    else:
        # Do merges first (deciding based on original position)
        tels = [el for el in els if isinstance(el, (inkex.TextElement,))]
        ptl = tp.ParsedTextList(tels)
        ptl.precalcs()
        ptl.make_next_chain()
        if removemanual:
            for pt in ptl:
                pt.differential_to_absolute_kerning()
                pt.make_next_chain()
            tels = Remove_Manual_Kerning(tels, mergesupersub)
        if mergenearby or mergesupersub:
            tels = External_Merges(tels, mergenearby, mergesupersub)
        # # Then do splits (deciding based on current position, not original position,
        # # since merges intentionally change position)
        if splitdistant:
            tels = Split_Distant_Chunks(tels)
        if splitdistant:
            tels = Split_Distant_Intrachunk(tels)
        if splitdistant:
            tels = Split_Lines(tels)
        # # Final tweaks
        tels = Change_Justification(tels, justification)
        tels, removedspc = Remove_Trailing_Leading_Spaces(tels)
        if removemanual or mergenearby or mergesupersub or removedspc:
            tels = Fix_Merge_Positions(tels)
        tels = Make_All_Editable(tels)
        tels = Final_Cleanup(tels)
    return dh.unique(els + tels)


def Final_Cleanup(els):
    for el in els:
        el.parsed_text.delete_empty()
    return els


def Fix_Merge_Positions(els):
    for el in els:
        for line in el.parsed_text.lns:
            for w in line.chks:
                w.fix_merged_position()
    return els


def Remove_Trailing_Leading_Spaces(els):
    removed = False
    for el in els:
        if not (el.parsed_text.ismlinkscape) and not (
            el.parsed_text.isflow
        ):  # skip Inkscape-generated text
            for line in el.parsed_text.lns:
                mtxt = line.txt()
                ii = len(mtxt) - 1
                while ii >= 0 and mtxt[ii] == " ":
                    line.chrs[ii].delc()
                    ii -= 1
                    removed = True

                mtxt = line.txt()
                ii = 0
                while ii < len(mtxt) and mtxt[ii] == " ":
                    line.chrs[0].delc()
                    ii += 1
                    removed = True
    return els, removed


def Make_All_Editable(els):
    for el in els:
        el.parsed_text.make_editable()
    return els

def Change_Justification(els, justification):
    if justification is not None:
        for ptxt in [el.parsed_text for el in els]:
            if not (ptxt.ismlinkscape) and not (
                ptxt.isflow
            ):  # skip Inkscape-generated text
                for line in ptxt.lns:
                    line.change_alignment(justification)
                alignd = {"start": "start", "middle": "center", "end": "end"}
                ptxt.textel.cstyle.__setitem__(
                    "text-anchor", justification, "text-align", alignd[justification]
                )
    return els


# Split different lines
def Split_Lines(els, ignoreinkscape=True):
    ptxts = [el.parsed_text for el in els]
    for jj in range(len(ptxts)):
        ptxt = ptxts[jj]
        if (
            ptxt.lns is not None
            and len(ptxt.lns) > 1
            and (not (ptxt.ismlinkscape) or not (ignoreinkscape))
            and not (ptxt.isflow)
        ):
            for il in reversed(range(1, len(ptxt.lns))):
                newtxt = ptxt.split_off_characters(ptxt.lns[il].chrs)
                els.append(newtxt)
    return els


# Generate splitting of distantly-kerned text
def Split_Distant_Chunks(els):
    for ptxt in [el.parsed_text for el in els]:
        if ptxt.lns is not None:
            for il in reversed(range(len(ptxt.lns))):
                line = ptxt.lns[il]
                sws = [
                    x
                    for _, x in sorted(
                        zip([w.x for w in line.chks], line.chks),
                        key=lambda pair: pair[0],
                    )
                ]  # chunks sorted in ascending x
                splits = []
                for ii in range(1, len(line.chks)):
                    w = sws[ii - 1]
                    w2 = sws[ii]

                    trl_spcs, ldg_spcs = trailing_leading(w.txt, w2.txt)
                    dx = w.spw * (NUM_SPACES - trl_spcs - ldg_spcs)
                    xtol = XTOLSPLIT * w.spw

                    tr1, br1, tl2, bl2 = w.get_ut_pts(w2, current_pts=True)
                    if bl2[0] > br1[0] + dx + xtol:
                        splits.append(ii)
                line.splits = splits
                line.sws = sws

                if len(splits) > 0:
                    for ii in reversed(range(len(splits))):
                        sstart = splits[ii]
                        if ii != len(splits) - 1:
                            sstop = splits[ii + 1]
                        else:
                            sstop = len(line.chks)

                        newtxt = ptxt.split_off_chunks(sws[sstart:sstop])
                        els.append(newtxt)
    return els


# Generate splitting of distantly-kerned text
def Split_Distant_Intrachunk(els):
    for ptxt in [el.parsed_text for el in els]:
        if ptxt.lns is not None and not (ptxt.ismlinkscape) and not (ptxt.isflow):
            for line in ptxt.lns:
                for w in line.chks:
                    if len(w.chrs) > 0:
                        chrs = sorted(w.chrs, key=lambda chr: chr.pts_ut[0][0])
                        lastnspc = None
                        splitiis = []
                        prevsplit = 0
                        if chrs[0].c not in [" ", "\u00a0"]:
                            lastnspc = chrs[0]
                        for ii in range(1, len(chrs)):
                            if lastnspc is not None:
                                c = lastnspc
                                c2 = chrs[ii]

                                bl2 = c2.pts_ut[0]
                                br1 = c.pts_ut[3]

                                dx = w.spw * (NUM_SPACES)
                                xtol = XTOLSPLIT * w.spw

                                # If this character is splitting two numbers,
                                # should always split in case they are ticks
                                import re

                                remainingnumeric = False
                                numbersplits = [" ", "-", "−"]
                                # chars that may separate numbers
                                splrest = re.split("|".join(numbersplits), w.txt[ii:])
                                splrest = [v for v in splrest if v != ""]
                                if len(splrest) > 0:
                                    remainingnumeric = isnumeric(splrest[0])
                                numbersplit = (
                                    isnumeric(w.txt[prevsplit:ii])
                                    and (c2.c in numbersplits and remainingnumeric)
                                    and c.loc.elem == c2.loc.elem
                                )

                                if bl2[0] > br1[0] + dx + xtol or numbersplit:
                                    splitiis.append(ii)
                                    prevsplit = ii
                            if chrs[ii].c not in [" ", "\u00a0"]:
                                lastnspc = chrs[ii]

                        if len(splitiis) > 0:
                            for ii in reversed(range(len(splitiis))):
                                sstart = splitiis[ii]
                                if ii != len(splitiis) - 1:
                                    sstop = splitiis[ii + 1]
                                else:
                                    sstop = len(chrs)
                                split_chrs = [chr for chr in w.chrs if chr in chrs[sstart:sstop]]
                                newtxt = ptxt.split_off_characters(split_chrs)
                                els.append(newtxt)
    return els


def Remove_Manual_Kerning(els, mergesupersub):
    # Generate list of merges
    chks = []
    ptxts = [el.parsed_text for el in els]
    for ptxt in ptxts:
        if ptxt.lns is not None:
            chks += [w for line in ptxt.lns for w in line.chks]
    for w in chks:
        mw = []
        w2 = w.nextw
        if w2 is not None and w2 in chks and not (twospaces(w.txt, w2.txt)):
            trl_spcs, ldg_spcs = trailing_leading(w.txt, w2.txt)
            dx = w.spw * (NUM_SPACES - trl_spcs - ldg_spcs)
            xtoln = XTOLMKN * w.spw
            xtolp = XTOLMKP * w.spw
            ytol  = YTOLMK  * w.mch

            try:
                tr1, br1, tl2, bl2 = w.get_ut_pts(w2)
            except ZeroDivisionError:
                w.mw = mw
                continue

            if isnumeric(w.txt) and isnumeric(w2.txt, True):
                dx = w.spw * 0

            previoussp = w.txt == " " and w.prevw is not None
            validmerge = br1[0] - xtoln <= bl2[0] <= br1[0] + dx + xtolp
            validmerge = validmerge and br1[1] - ytol <= bl2[1] <= br1[1] + ytol
            if previoussp and not validmerge:
                # reconsider in case previous space was weirdly-kerned
                tr1p, br1p, tl2p, bl2p = w.prevw.get_ut_pts(w2)
                dx = w.spw * (NUM_SPACES - trl_spcs - ldg_spcs + 1)
                validmerge = br1p[0] - xtoln <= bl2p[0] <= br1p[0] + dx + xtolp
                
            if validmerge:
                mw.append([w2, "same", br1, bl2])

        w.mw = mw

    Perform_Merges(chks, mk=True)

    # Following manual kerning removal, lines with multiple chunks
    # need to be split out into new text els
    newptxts = []
    for ptxt in ptxts:
        for line in ptxt.lns:
            while len(line.chks) > 1:
                newtxt = ptxt.split_off_chunks([line.chks[-1]])
                els.append(newtxt)
                newptxts.append(newtxt.parsed_text)
    return els


import numpy as np


def External_Merges(els, mergenearby, mergesupersub):
    # Generate list of merges
    chks = []
    for ptxt in [el.parsed_text for el in els]:
        if ptxt.lns is not None:
            chks += [w for line in ptxt.lns for w in line.chks]

    pbbs = [None]*len(chks)
    for ii, w in enumerate(chks):
        cx = [v[0] for c in w.chrs for v in c.parsed_pts_t]
        cy = [v[1] for c in w.chrs for v in c.parsed_pts_t]
        pbbs[ii] = tp.bbox([min(cx),min(cy),max(cx)-min(cx),max(cy)-min(cy)]);
    
    for ii, w in enumerate(chks):
        dx = (
            w.spw * w.scf * (NUM_SPACES + XTOLEXT)
        )  # a big bounding box that includes the extra space
        
        w.bb_big = tp.bbox(
            [
                pbbs[ii].x1 - dx,
                pbbs[ii].y1 - dx,
                pbbs[ii].w + 2 * dx,
                pbbs[ii].h + 2 * dx,
            ]
        )
        w.mw = []

    # Vectorized angle / bbox calculations
    angles = np.array([[w.angle for w in chks]])
    sameangle = abs(angles - angles.T) < 0.001

    bb1s = [w.bb_big for w in chks]
    bb2s = pbbs
    intersects = dh.bb_intersects(bb1s, bb2s)

    # reshape(-1,1) is a transpose
    potentials = np.logical_and(sameangle, intersects)
    potentials = np.logical_and(
        potentials, np.identity(len(chks)) == 0
    )  # off-diagonal only
    goodl = np.argwhere(potentials)

    for ii in range(goodl.shape[0]):
        w = chks[goodl[ii, 0]]
        w2 = chks[goodl[ii, 1]]
        trl_spcs, ldg_spcs = trailing_leading(w.txt, w2.txt)

        dx = w.spw * (NUM_SPACES - trl_spcs - ldg_spcs)
        xtol = XTOLEXT * w.spw
        ytol = YTOLEXT * w.mch

        # calculate 2's coords in 1's system
        tr1, br1, tl2, bl2 = w.get_ut_pts(w2)
        xpenmatch = br1[0] - xtol <= bl2[0] <= br1[0] + dx + xtol
        neitherempty = len(wstrip(w.txt)) > 0 and len(wstrip(w2.txt)) > 0
        if xpenmatch and neitherempty and not twospaces(w.txt, w2.txt):
            weight_match = w.chrs[-1].tsty['font-weight'] == w2.chrs[0].tsty['font-weight']
            # Don't sub/super merge when differences in font-weight
            # Helps prevent accidental merges of subfigure label to tick
            letterinpar = bool(re.fullmatch(r"^\([a-zA-Z]\)$", w.txt))
            # Don't sub/super merge when is letter enclosed in parentheses
            # Helps prevent accidental merges of subfigure label to tick
            mtype = None
            if (
                abs(bl2[1] - br1[1]) < ytol
                and abs(w.tfs - w2.tfs) < 0.001
                and mergenearby
            ):
                if isnumeric(w.line.txt()) and isnumeric(w2.line.txt(), True):
                    numsp = (bl2[0] - br1[0]) / (w.spw)
                    if abs(numsp) < 0.25:
                        # only merge numbers if very close (could be x ticks)
                        mtype = "same"
                else:
                    mtype = "same"
            elif (
                br1[1] + ytol >= bl2[1] >= tr1[1] - ytol and mergesupersub and weight_match and not letterinpar
            ):  # above baseline
                aboveline = (
                    br1[1] * (1 - SUBSUPER_YTHR) + tr1[1] * SUBSUPER_YTHR + ytol
                    >= bl2[1]
                )
                
                if w2.tfs < w.tfs * SUBSUPER_THR:  # new smaller, expect super
                    if aboveline:
                        mtype = "super"
                elif w.tfs < w2.tfs * SUBSUPER_THR:  # old smaller, expect reutrn
                    mtype = "subreturn"
                elif SUBSUPER_THR == 1:
                    if aboveline:
                        if len(w2.line.txt()) > 2:  # long text, probably not super
                            mtype = "subreturn"
                        else:
                            mtype = "superorsubreturn"
                            # could be either, decide later
                    else:
                        mtype = "subreturn"
            elif br1[1] + ytol >= tl2[1] >= tr1[1] - ytol and mergesupersub and weight_match and not letterinpar:
                belowline = (
                    tl2[1]
                    >= br1[1] * SUBSUPER_YTHR + tr1[1] * (1 - SUBSUPER_YTHR) - ytol
                )
                if w2.tfs < w.tfs * SUBSUPER_THR:  # new smaller, expect sub
                    if belowline:
                        mtype = "sub"
                elif w.tfs < w2.tfs * SUBSUPER_THR:  # old smaller, expect superreturn
                    mtype = "superreturn"
                elif SUBSUPER_THR == 1:
                    if belowline:
                        if len(w2.line.txt()) > 2:  # long text, probably not sub
                            mtype = "superreturn"
                        else:
                            mtype = "suborsuperreturn"
                            # could be either, decide later
                    else:
                        mtype = "superreturn"
            if mtype is not None:
                w.mw.append([w2, mtype, br1, bl2])
        #                            dh.debug(w.txt+' to '+w2.txt+' as '+mtype)

        if DEBUG_MERGE:
            dh.idebug('\nMerging "' + w.txt + '" and "' + w2.txt + '"')
            if not (xpenmatch):
                dh.idebug("Aborted, x pen too far: " + str([br1[0], bl2[0], dx]))
            elif not (neitherempty):
                dh.idebug("Aborted, one empty")
            else:
                if mtype is None:
                    if not (abs(bl2[1] - br1[1]) < ytol):
                        dh.idebug("Aborted, y pen too far: " + str([bl2[1], br1[1]]))
                    elif not (abs(w.tfs - w2.tfs) < 0.001):
                        dh.idebug(
                            "Aborted, fonts too different: " + str([w.tfs, w2.tfs])
                        )
                    elif not (
                        not (isnumeric(w.line.txt())) or not (isnumeric(w2.line.txt()))
                    ):
                        dh.idebug("Aborted, both numbers")
                else:
                    dh.idebug("Merged as " + mtype)

    Perform_Merges(chks)
    return els


def Perform_Merges(chks, mk=False):
    for w in chks:
        mw = w.mw
        minx = float("inf")
        for ii in range(len(mw)):
            w2 = mw[ii][0]
            mtype = mw[ii][1]
            br1 = mw[ii][2]
            bl2 = mw[ii][3]
            if abs(bl2[0] - br1[0]) < minx:
                minx = abs(bl2[0] - br1[0])
                # starting pen best matches the stop of the previous one
                mi = ii
        w.merges = []
        w.mergetypes = []
        w.merged = False
        if len(mw) > 0:
            w2 = mw[mi][0]
            mtype = mw[mi][1]
            br1 = mw[mi][2]
            bl2 = mw[mi][3]
            w.merges = [w2]
            w.mergetypes = [mtype]

    # Generate chains of merges
    for w in chks:
        # if w.txt=='T':
        if not (w.merged) and len(w.merges) > 0:
            w.merges[-1].merged = True
            nextmerge = w.merges[-1].merges
            nextmerget = w.merges[-1].mergetypes
            while len(nextmerge) > 0:
                w.merges += nextmerge
                w.mergetypes += nextmerget
                w.merges[-1].merged = True
                nextmerge = w.merges[-1].merges
                nextmerget = w.merges[-1].mergetypes

    # Create a merge plan
    for w in chks:
        if len(w.merges) > 0:
            ctype = "normal"
            w.wtypes = [ctype]
            bail = False
            for mt in w.mergetypes:
                if ctype == "normal":
                    if mt == "same":
                        pass
                    elif mt == "sub":
                        ctype = "sub"
                    elif mt == "super":
                        ctype = "super"
                    elif mt == "suborsuperreturn":
                        ctype = "sub"
                    elif mt == "superorsubreturn":
                        ctype = "super"
                    elif all(
                        [t == "normal" for t in w.wtypes]
                    ):  # maybe started on sub/super
                        bail = True
                    else:
                        bail = True
                elif ctype == "super":
                    if mt == "same":
                        pass
                    elif mt == "superreturn":
                        ctype = "normal"
                    elif mt == "suborsuperreturn":
                        ctype = "normal"
                    else:
                        bail = True
                elif ctype == "sub":
                    if mt == "same":
                        pass
                    elif mt == "subreturn":
                        ctype = "normal"
                    elif mt == "superorsubreturn":
                        ctype = "normal"
                    else:
                        bail = True
                w.wtypes.append(ctype)
            if bail == True:
                w.wtypes = []
                w.merges = []
    # Pre-merge position calculation

    # Execute the merge plan
    for w in chks:
        if len(w.merges) > 0 and not (w.merged):
            maxii = len(w.merges)
            alltxt = "".join([w.txt] + [w2.txt for w2 in w.merges])
            hasspaces = " " in alltxt

            mels = []
            for ii in range(maxii):
                maxspaces = None
                if mk and hasspaces and w.merges[ii].prevsametspan:
                    maxspaces = 0
                if (
                    w.txt is not None and len(w.txt) > 0 and w.txt[-1] == " "
                ) or w.wtypes[ii + 1] in [
                    "super",
                    "sub",
                ]:  # no extra spaces for sub/supers or if there's already one
                    maxspaces = 0

                mels.append(w.merges[ii].line.ptxt.textel)
                w.append_chk(w.merges[ii], w.wtypes[ii + 1], maxspaces)

            # Union clips if necessary
            mels = dh.unique([w.line.ptxt.textel] + mels)
            if len(mels) > 1:
                clips = [el.get_link("clip-path") for el in mels]
                if any([c is None for c in clips]):
                    w.line.ptxt.textel.set("clip-path", None)
                else:
                    # Duplicate main clip
                    dc = clips[0].duplicate()
                    wt = mels[0].ccomposed_transform
                    for ii in range(1, len(mels)):
                        # Duplicate merged clip, group contents, move to main dupe
                        dc2 = clips[ii].duplicate()
                        ng = dh.group(list(dc2))
                        dc.append(ng)
                        ng.ctransform = (-wt) @ mels[ii].ccomposed_transform
                        dc2.delete()
                    mels[0].set("clip-path", dc.get_id(2))


# Check if text represents a number
ncs = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "e", "E", "-", "−", ","]


def isnumeric(s, countminus=False):
    s = (
        s.strip().replace("−", "-").replace(",", "")
    )  # strip whitespaces, replace minus signs with -, remove commas
    if countminus and s == "-":  # count a minus sign as a number
        return True
    try:
        float(s)
        return True
    except ValueError:
        return False


# Strip whitespaces
def wstrip(txt):
    return txt.translate({ord(c): None for c in " \n\t\r"})


def twospaces(w1txt, w2txt):
    if (
        (w1txt is not None and len(w1txt) > 1 and w1txt[-2:] == "  ")
        or (
            w1txt is not None
            and len(w1txt) > 0
            and w1txt[-1:] == " "
            and w2txt is not None
            and len(w2txt) > 0
            and w2txt[0] == " "
        )
        or (w2txt is not None and len(w2txt) > 1 and w2txt[:1] == "  ")
    ):
        return True  # resultant chunk has two spaces
    return False


def trailing_leading(wtxt, w2txt):
    trl_spcs = sum([all([c == " " for c in wtxt[ii:]]) for ii in range(len(wtxt))])
    ldg_spcs = sum(
        [all([c == " " for c in w2txt[: ii + 1]]) for ii in range(len(w2txt))]
    )
    return trl_spcs, ldg_spcs
