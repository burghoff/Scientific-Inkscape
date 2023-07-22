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

# for debugging TextParser
DEBUG_PARSER = True
DEBUG_PARSER = False

# for checking why elements aren't merging
DEBUG_MERGE = True
DEBUG_MERGE = False

NUM_SPACES = 1.0
# number of spaces beyond which text will be merged/split
XTOLEXT = 0.6  # x tolerance (number of spaces), let be big since there are kerning inaccuracies (as big as -0.56 in Whitney)
YTOLEXT = 0.1  # y tolerance (fraction of cap height), should be pretty small
XTOLMKN = 0.99 * 1000  # left tolerance for manual kerning removal, should be huge
XTOLMKP = (
    0.99  # right tolerance for manual kerning removal, should be fairly open-minded
)
XTOLSPLIT = 0.5  # tolerance for manual kerning splitting, should be fairly tight
SUBSUPER_THR = 0.99
# ensuring sub/superscripts are smaller helps reduce false merges
SUBSUPER_YTHR = 1 / 3
# superscripts must be at least 1/3 of the way above the baseline to merge (1/3 below cap for sub)

import inkex
import TextParser

import os, sys

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
    justification=None,debugparser=False
):
    tels = [el for el in els if isinstance(el, (inkex.TextElement,inkex.FlowRoot))]
    if len(tels)>0:
        tels[0].croot.make_char_table(tels)
    if DEBUG_PARSER or debugparser:
        for el in tels:
            el.parsed_text.Make_Highlights('char')
    else:
        # Do merges first (deciding based on original position)
        tels = [el for el in els if isinstance(el, (inkex.TextElement,))]
        lls = [TextParser.get_parsed_text(el) for el in tels]
        # dh.idebug(len([1 for pt in lls if pt.isflow]))
        TextParser.ParsedTextList(lls).precalcs()
        if removemanual:
            tels = Remove_Manual_Kerning(tels, mergesupersub)
        if mergenearby or mergesupersub:
            tels = External_Merges(tels, mergenearby, mergesupersub)
        # Then do splits (deciding based on current position, not original position,
        # since merges intentionally change position)
        if splitdistant:
            tels = Split_Distant_Words(tels)
        if splitdistant:
            tels = Split_Distant_Intraword(tels)
        if splitdistant:
            tels = Split_Lines(tels)
        # Final tweaks
        tels = Change_Justification(tels, justification)
        if removemanual or mergenearby or mergesupersub:
            tels = Fix_Merge_Positions(tels)
        tels = Remove_Trailing_Leading_Spaces(tels)
        tels = Make_All_Editable(tels)
        tels = Final_Cleanup(tels)
    return dh.unique(els+tels)

def Final_Cleanup(els):
    for el in els:
        # ll.Position_Check()
        el.parsed_text.Delete_Empty()
    return els


def Fix_Merge_Positions(els):
    for el in els:
        for ln in el.parsed_text.lns:
            for w in ln.ws:
                w.fix_merged_position()
    return els


def Remove_Trailing_Leading_Spaces(els):
    for el in els:
        if not (el.parsed_text.ismlinkscape) and not (el.parsed_text.isflow):  # skip Inkscape-generated text
            for ln in el.parsed_text.lns:
                mtxt = ln.txt()
                ii = len(mtxt) - 1
                while ii >= 0 and mtxt[ii] == " ":
                    ln.cs[ii].delc()
                    ii -= 1

                mtxt = ln.txt()
                ii = 0
                while ii < len(mtxt) and mtxt[ii] == " ":
                    ln.cs[0].delc()
                    ii += 1
    return els


def Make_All_Editable(els):
    for el in els:
        el.parsed_text.Make_Editable()
    return els


def Change_Justification(els, justification):
    if justification is not None:
        for ll in [TextParser.get_parsed_text(el) for el in els]:
            # ll.Position_Check()
            if not (ll.ismlinkscape) and not (
                ll.isflow
            ):  # skip Inkscape-generated text
                for ln in ll.lns:
                    ln.change_alignment(justification)
                # dh.Set_Style_Comp(ll.textel, "text-anchor", justification)
                ll.textel.cstyle["text-anchor"]= justification
                alignd = {"start": "start", "middle": "center", "end": "end"}
                # dh.Set_Style_Comp(ll.textel, "text-align", alignd[justification])
                ll.textel.cstyle["text-align"]=alignd[justification]
            # ll.Position_Check()
    return els


# Split different lines
def Split_Lines(els,ignoreinkscape=True):
    # newlls = []
    lls = [TextParser.get_parsed_text(el) for el in els];
    for jj in range(len(lls)):
        ll = lls[jj]
        if (
            ll.lns is not None
            and len(ll.lns) > 1
            and (not(ll.ismlinkscape) or not(ignoreinkscape))
            and not (ll.isflow)
        ):
            for il in reversed(range(1, len(ll.lns))):
                newtxt = ll.Split_Off_Characters(ll.lns[il].cs)
                els.append(newtxt)
                # newlls.append(newtxt.parsed_text)
    # lls += newlls
    return els


# Generate splitting of distantly-kerned text
def Split_Distant_Words(els):
    # newlls = []
    for ll in [TextParser.get_parsed_text(el) for el in els]:
        if ll.lns is not None:
            for il in reversed(range(len(ll.lns))):
                ln = ll.lns[il]
                sws = [
                    x
                    for _, x in sorted(
                        zip([w.x for w in ln.ws], ln.ws), key=lambda pair: pair[0]
                    )
                ]  # words sorted in ascending x
                splits = []
                for ii in range(1, len(ln.ws)):
                    w = sws[ii - 1]
                    w2 = sws[ii]

                    trl_spcs, ldg_spcs = trailing_leading(w, w2)
                    dx = w.sw * (NUM_SPACES - trl_spcs - ldg_spcs) 
                    xtol = XTOLSPLIT * w.sw 

                    tr1, br1, tl2, bl2 = w.get_ut_pts(w2, current_pts=True)

                    # bl2 = w2.pts_ut[0];
                    # br1 = w.pts_ut[3];

                    if bl2[0] > br1[0] + dx + xtol:
                        splits.append(ii)
                        # dh.idebug([w.txt(),w2.txt(),br1[0]+dx,bl2[0],xtol])
                ln.splits = splits
                ln.sws = sws

                if len(splits) > 0:
                    for ii in reversed(range(len(splits))):
                        sstart = splits[ii]
                        if ii != len(splits) - 1:
                            sstop = splits[ii + 1]
                        else:
                            sstop = len(ln.ws)

                        newtxt = ll.Split_Off_Words(sws[sstart:sstop])
                        els.append(newtxt)
                        # newlls.append(newtxt.parsed_text)
    # lls += newlls
    return els


# Generate splitting of distantly-kerned text
def Split_Distant_Intraword(els):
    # newlls = []
    for ll in [TextParser.get_parsed_text(el) for el in els]:
        if ll.lns is not None and not (ll.ismlinkscape) and not (ll.isflow):
            for ln in ll.lns:
                for w in ln.ws:
                    if len(w.cs) > 0:
                        lastnspc = None
                        splitiis = []
                        prevsplit = 0
                        if w.cs[0].c not in [" ", "\u00A0"]:
                            lastnspc = w.cs[0]
                        for ii in range(1, len(w.cs)):
                            if lastnspc is not None:
                                c = lastnspc
                                c2 = w.cs[ii]

                                bl2 = c2.pts_ut[0]
                                br1 = c.pts_ut[3]

                                # trl_spcs, ldg_spcs = trailing_leading(w,w2)
                                dx = w.sw * (NUM_SPACES) 
                                xtol = XTOLSPLIT * w.sw 

                                # If this character is splitting two numbers, should always split in case they are ticks
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
                                    and c.loc.el == c2.loc.el
                                )

                                if bl2[0] > br1[0] + dx + xtol or numbersplit:
                                    splitiis.append(ii)
                                    prevsplit = ii
                            if w.cs[ii].c not in [" ", "\u00A0"]:
                                lastnspc = w.cs[ii]

                        # if len(splitiis)>0:
                        #     dh.idebug(w.txt)
                        #     for spl in splitiis:
                        #         dh.idebug(w.cs[spl].c)

                        if len(splitiis) > 0:
                            for ii in reversed(range(len(splitiis))):
                                sstart = splitiis[ii]
                                if ii != len(splitiis) - 1:
                                    sstop = splitiis[ii + 1]
                                else:
                                    sstop = len(w.cs)

                                # dh.idebug(w.txt[sstart:sstop])
                                newtxt = ll.Split_Off_Characters(
                                    w.cs[sstart:sstop]
                                )
                                els.append(newtxt)
                                # newlls.append(nll)
    # lls += newlls
    return els


def Remove_Manual_Kerning(els, mergesupersub):
    # Generate list of merges
    ws = []
    lls = [el.parsed_text for el in els]
    for ll in lls:
        if ll.lns is not None:
            ws += [w for ln in ll.lns for w in ln.ws]
        # ll.Position_Check()
    for w in ws:
        mw = []
        w2 = w.nextw
        if w2 is not None and w2 in ws and not (twospaces(w, w2)):
            trl_spcs, ldg_spcs = trailing_leading(w, w2)
            dx = w.sw * (NUM_SPACES - trl_spcs - ldg_spcs) 
            xtoln = XTOLMKN * w.sw 
            xtolp = XTOLMKP * w.sw 

            tr1, br1, tl2, bl2 = w.get_ut_pts(w2)

            if isnumeric(w.txt) and isnumeric(w2.txt, True):
                dx = w.sw * 0 

            previoussp = w.txt == " " and w.prevw is not None
            validmerge = br1[0] - xtoln <= bl2[0] <= br1[0] + dx + xtolp

            if previoussp and not (
                validmerge
            ):  # reconsider in case previous space was weirdly-kerned
                tr1p, br1p, tl2p, bl2p = w.prevw.get_ut_pts(w2)
                dx = w.sw * (NUM_SPACES - trl_spcs - ldg_spcs + 1) 
                validmerge = br1p[0] - xtoln <= bl2p[0] <= br1p[0] + dx + xtolp

            if validmerge:
                mw.append([w2, "same", br1, bl2])
        w.mw = mw

    Perform_Merges(ws, mk=True)

    # Following manual kerning removal, lines with multiple words need to be split out into new text els
    newlls = []
    for ll in lls:
        for ln in ll.lns:
            while len(ln.ws) > 1:
                newtxt = ll.Split_Off_Words([ln.ws[-1]])
                els.append(newtxt)
                newlls.append(newtxt.parsed_text)
    # lls += newlls

    # newlls=[];
    # for ll in lls:
    #     for ln in ll.lns:
    #         for w in ln.ws:
    #             for ii in reversed(range(1,len(w.cs))):
    #                 if w.cs[ii].dy!=0:
    #                     # dh.idebug([w.cs[ii-1].dy,w.cs[ii].dy])
    #                     newtxt,nll = ll.Split_Off_Characters(w.cs[ii:])
    #                     os.append(newtxt)
    #                     newlls.append(nll)
    # lls+=newlls

    return els


import numpy as np


def External_Merges(els, mergenearby, mergesupersub):
    # Generate list of merges
    ws = []
    for ll in [TextParser.get_parsed_text(el) for el in els]:
        if ll.lns is not None:
            ws += [w for ln in ll.lns for w in ln.ws]
        # ll.Position_Check()
    for w in ws:
        dx = w.sw * w.sf * (
            NUM_SPACES + XTOLEXT
        )  # a big bounding box that includes the extra space
        if w.parsed_bb is not None:
            w.bb_big = TextParser.bbox(
                [
                    w.parsed_bb.x1 - dx,
                    w.parsed_bb.y1 - dx,
                    w.parsed_bb.w + 2 * dx,
                    w.parsed_bb.h + 2 * dx,
                ]
            )
        else:
            w.bb_big = TextParser.bbox(
                [w.bb.x1 - dx, w.bb.y1 - dx, w.bb.w + 2 * dx, w.bb.h + 2 * dx]
            )
        w.mw = []

    # Vectorized angle / bbox calculations
    angles = np.array([[w.angle for w in ws]])
    sameangle = abs(angles - angles.T) < 0.001
    # xc1, yc1, wd1, ht1, xc2, yc2, wd2, ht2 = np.zeros((8, len(ws)))
    # for ii in range(len(ws)):
    #     box1 = ws[ii].bb_big
    #     box2 = ws[ii].bb
    #     if ws[ii].parsed_bb is not None:
    #         box2 = ws[ii].parsed_bb
    #     xc1[ii] = box1.xc
    #     yc1[ii] = box1.yc
    #     wd1[ii] = box1.w
    #     ht1[ii] = box1.h
    #     xc2[ii] = box2.xc
    #     yc2[ii] = box2.yc
    #     wd2[ii] = box2.w
    #     ht2[ii] = box2.h
    # intersects = np.logical_and(
    #     (abs(xc1.reshape(-1, 1) - xc2) * 2 < (wd1.reshape(-1, 1) + wd2)),
    #     (abs(yc1.reshape(-1, 1) - yc2) * 2 < (ht1.reshape(-1, 1) + ht2)),
    # )
    
    bb1s = [w.bb_big for w in ws]
    bb2s = [w.bb if w.parsed_bb is None else w.parsed_bb for w in ws]
    intersects = dh.bb_intersects(bb1s,bb2s)
    
    # reshape(-1,1) is a transpose
    potentials = np.logical_and(sameangle, intersects)
    potentials = np.logical_and(
        potentials, np.identity(len(ws)) == 0
    )  # off-diagonal only
    goodl = np.argwhere(potentials)

    for ii in range(goodl.shape[0]):
        w = ws[goodl[ii, 0]]
        w2 = ws[goodl[ii, 1]]

        # dh.idebug([w.txt,w2.txt])

        trl_spcs, ldg_spcs = trailing_leading(w, w2)

        dx = w.sw * (NUM_SPACES - trl_spcs - ldg_spcs) 
        xtol = XTOLEXT * w.sw
        ytol = YTOLEXT * w.mch

        # calculate 2's coords in 1's system
        tr1, br1, tl2, bl2 = w.get_ut_pts(w2)
        xpenmatch = br1[0] - xtol <= bl2[0] <= br1[0] + dx + xtol
        neitherempty = len(wstrip(w.txt)) > 0 and len(wstrip(w2.txt)) > 0
        if xpenmatch and neitherempty and not (twospaces(w, w2)):
            type = None
            # dh.idebug([w.tfs,w2.tfs])
            # dh.idebug([br1.y+ytol>=bl2.y>=tr1.y-ytol,mergesupersub])
            if abs(bl2[1] - br1[1]) < ytol and abs(w.tfs - w2.tfs) < 0.001 and mergenearby:
                if isnumeric(w.ln.txt()) and isnumeric(w2.ln.txt(), True):
                    numsp = (bl2[0]-br1[0])/(w.sw);
                    if abs(numsp)<0.25:
                        # only merge numbers if very close (could be x ticks)
                        type='same'
                else:
                    type = "same"
                # dh.debug(w.txt+' '+w2.txt)
            elif (
                br1[1] + ytol >= bl2[1] >= tr1[1] - ytol and mergesupersub
            ):  # above baseline
                aboveline = (
                    br1[1] * (1 - SUBSUPER_YTHR) + tr1[1] * SUBSUPER_YTHR + ytol >= bl2[1]
                )
                if w2.tfs < w.tfs * SUBSUPER_THR:  # new smaller, expect super
                    if aboveline:
                        type = "super"
                elif w.tfs < w2.tfs * SUBSUPER_THR:  # old smaller, expect reutrn
                    type = "subreturn"
                elif SUBSUPER_THR==1:
                    if aboveline:
                        if len(w2.ln.txt()) > 2:  # long text, probably not super
                            type = "subreturn"
                        else:
                            type = "superorsubreturn"
                            # could be either, decide later
                    else:
                        type = "subreturn"
            elif br1[1] + ytol >= tl2[1] >= tr1[1] - ytol and mergesupersub:
                belowline = (
                    tl2[1] >= br1[1] * SUBSUPER_YTHR + tr1[1] * (1 - SUBSUPER_YTHR) - ytol
                )
                if w2.tfs < w.tfs * SUBSUPER_THR:  # new smaller, expect sub
                    if belowline:
                        type = "sub"
                elif w.tfs < w2.tfs * SUBSUPER_THR:  # old smaller, expect superreturn
                    type = "superreturn"
                elif SUBSUPER_THR==1:
                    if belowline:
                        if len(w2.ln.txt()) > 2:  # long text, probably not sub
                            type = "superreturn"
                        else:
                            type = "suborsuperreturn"
                            # could be either, decide later
                    else:
                        type = "superreturn"
            if type is not None:
                w.mw.append([w2, type, br1, bl2])
        #                            dh.debug(w.txt+' to '+w2.txt+' as '+type)

        if DEBUG_MERGE:
            dh.idebug('\nMerging "' + w.txt + '" and "' + w2.txt + '"')
            if not (xpenmatch):
                dh.idebug("Aborted, x pen too far: " + str([br1[0], bl2[0], dx]))
            elif not (neitherempty):
                dh.idebug("Aborted, one empty")
            else:
                if type is None:
                    if not (abs(bl2[1] - br1[1]) < ytol):
                        dh.idebug("Aborted, y pen too far: " + str([bl2[1], br1[1]]))
                    elif not (abs(w.tfs - w2.tfs) < 0.001):
                        dh.idebug("Aborted, fonts too different: " + str([w.tfs, w2.tfs]))
                    elif not (
                        not (isnumeric(w.ln.txt())) or not (isnumeric(w2.ln.txt()))
                    ):
                        dh.idebug("Aborted, both numbers")
                else:
                    dh.idebug("Merged as " + type)

    Perform_Merges(ws)
    return els


def Perform_Merges(ws, mk=False):
    for w in ws:
        mw = w.mw
        minx = float("inf")
        for ii in range(len(mw)):
            w2 = mw[ii][0]
            type = mw[ii][1]
            br1 = mw[ii][2]
            bl2 = mw[ii][3]
            if abs(bl2[0] - br1[0]) < minx:
                minx = abs(bl2[0] - br1[0])
                # starting pen best matches the stop of the previous one
                mi = ii
            # if bl2.x < minx:
            #     minx = bl2.x;
            #     mi   = ii
        w.merges = []
        w.mergetypes = []
        w.merged = False
        # if w.txt==' ':
        #     dh.debug(w.nextw.txt)
        if len(mw) > 0:
            w2 = mw[mi][0]
            type = mw[mi][1]
            br1 = mw[mi][2]
            bl2 = mw[mi][3]
            w.merges = [w2]
            w.mergetypes = [type]
    #            dh.idebug(w.txt+' in '+w.ln.el.get_id()+' to '+ w.merges[0].txt+' in '+w2.ln.el.get_id()+' as '+w.mergetypes[0])

    # Generate chains of merges
    for w in ws:
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
    for w in ws:
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
                        #                        if mt=='subreturn':
                        #                            w.wtypes = ['sub']*len(w.wtypes);
                        #                            ctype = 'normal';
                        #                        elif mt=='superreturn':
                        #                            w.wtypes = ['super']*len(w.wtypes);
                        #                            ctype = 'normal';
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
        # dh.debug(w.merges)
    # Pre-merge position calculation
    # for w in ws:
    #     w.premerge_br = w.pts_t[3];
    # Execute the merge plan
    for w in ws:
        #        dh.idebug([w.txt,w.merges[ii].txt])
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

                mels.append(w.merges[ii].ln.pt.textel)
                w.appendw(w.merges[ii], w.wtypes[ii + 1], maxspaces)
                
            # Union clips if necessary
            mels = dh.unique([w.ln.pt.textel]+mels)
            if len(mels)>1:
                clips = [el.get_link('clip-path') for el in mels]
                if any([c is None for c in clips]):
                    w.ln.pt.textel.set('clip-path',None)
                else:
                    # Duplicate main clip
                    dc = clips[0].duplicate();
                    wt = mels[0].ccomposed_transform;
                    for ii in range(1,len(mels)):
                        # Duplicate merged clip, group contents, move to main dupe
                        dc2 = clips[ii].duplicate();
                        ng = dh.group(list(dc2))
                        dc.append(ng);
                        ng.ctransform = (-wt) @ mels[ii].ccomposed_transform
                        dc2.delete();
                    mels[0].set('clip-path',dc.get_id(2))
                
    # Clear out clips
    # for el in set(mels):
    #     if el.get_link('clip-path') is not None:
    #         el.set('clip-path',None)


# Check if text represents a number
ncs = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "e", "E", "-", "−", ","]


# def isnumeric(s, countminus=False):
#     s = wstrip(
#         s.replace("−", "-").replace(",", "")
#     )  # replace minus signs with -, remove commas
#     allnum = all([sv in ncs for sv in s])
#     isnum = False
#     if allnum:
#         try:
#             float(s)
#             isnum = True
#         except:
#             isnum = False
#     if not (isnum) and countminus and s == "-":
#         isnum = True  # count a minus sign as a number
#     return isnum

def isnumeric(s, countminus=False):
    s = s.strip().replace("−", "-").replace(",", "")  # strip whitespaces, replace minus signs with -, remove commas
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


def twospaces(w1, w2):
    if w2 is not None:
        w1txt = w1.txt
        w2txt = w2.txt
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
            return True  # resultant word has two spaces
    return False


def trailing_leading(w1, w2):
    wtxt = w1.txt
    w2txt = w2.txt
    trl_spcs = sum([all([c == " " for c in wtxt[ii:]]) for ii in range(len(wtxt))])
    ldg_spcs = sum(
        [all([c == " " for c in w2txt[: ii + 1]]) for ii in range(len(w2txt))]
    )
    return trl_spcs, ldg_spcs