DEBUG_PARSER = True;
DEBUG_PARSER = False;

DEBUG_MERGE = True; # for checking why elements aren't merging
DEBUG_MERGE = False; 

NUM_SPACES = 1.0;     # number of spaces beyond which text will be merged/split
XTOL = 0.6            # x tolerance (number of spaces)...let be big since there are kerning inaccuracies (as big as -0.56 in Whitney)
YTOL = 0.03           # y tolerance (number of spaces)...can be small
XTOLMK = XTOL*2       # tolerance for manual kerning removal...be more open-minded
SUBSUPER_THR = 1.0;  # ensuring sub/superscripts are smaller helps reduce false merges
SUBSUPER_YTHR = 1/3; # superscripts must be at least 1/3 of the way above the baseline to merge (1/3 below cap for sub)

import inkex
import TextParser

import os,sys
sys.path.append(os.path.dirname(os.path.realpath(sys.argv[0]))) # make sure my directory is on the path
import dhelpers as dh

def remove_kerning(caller,os,removemanual,mergesupersub,splitdistant,mergenearby,justification=None):    
    ct = TextParser.Character_Table(os,caller)
    lls=[]
    for el in os:
        if isinstance(el,inkex.TextElement) and el.getparent() is not None:
            lls.append(TextParser.LineList(el,ct,debug=False));
            if DEBUG_PARSER: 
                lls[-1].Position_Check();
    
    if not(DEBUG_PARSER):
        if splitdistant: lls, os = Split_Distant_Manual_Kerning(lls,os)
        if removemanual: lls, os = Remove_Manual_Kerning(lls,os,mergesupersub)
        # # for ll in lls: ll.Position_Check()
        # # for ll in lls: dh.debug(ll.txt())
        if mergenearby or mergesupersub: lls, os = External_Merges(lls,os,mergenearby,mergesupersub)
        if splitdistant: lls, os = Split_Lines(lls,os);
        lls, os = Change_Justification(lls,os,justification)
        lls, os = Make_All_Editable(lls,os);
        lls, os = Final_Cleanup(lls,os);
    return os

def Final_Cleanup(lls,os):
    for ll in lls:
        ll.Delete_Empty()
    return lls, os

def Make_All_Editable(lls,os):
    for ll in lls:
        ll.Make_Editable();
    return lls,os
    

def Change_Justification(lls,os,justification):
    if justification is not None:
        for ll in lls:
            # ll.Position_Check()
            if not(ll.isinkscape) or (ll.lns is not None and len(ll.lns)<2): # skip Inkscape-generated text
                for ln in ll.lns:
                    ln.change_alignment(justification);
                dh.Set_Style_Comp(ll.textel,'text-anchor',justification)
                alignd = {'start': 'start', 'middle': 'center', 'end': 'end'}
                dh.Set_Style_Comp(ll.textel,'text-align' ,alignd[justification])
            # ll.Position_Check()
    return lls,os
    

# Split different lines
def Split_Lines(lls,os):
    newlls = [];            
    for jj in range(len(lls)):
        ll = lls[jj];
        if ll.lns is not None and len(ll.lns)>1 and not(ll.isinkscape):
            for il in reversed(range(1,len(ll.lns))):
                newtxt,nll = ll.Split_Off_Words(ll.lns[il].ws)
                os.append(newtxt)
                newlls.append(nll)
    lls += newlls;
    return lls,os
     
# Generate splitting of distantly-kerned text
def Split_Distant_Manual_Kerning(lls,os):
    newlls=[];
    for ll in lls:
        if ll.lns is not None:
            for il in reversed(range(len(ll.lns))):
                ln = ll.lns[il];
                sws = [x for _, x in sorted(zip([w.x for w in ln.ws], ln.ws), key=lambda pair: pair[0])] # words sorted in ascending x
                splits = [];
                for ii in range(1,len(ln.ws)):
                    w = sws[ii-1]
                    w2= sws[ii]
                    dx = w.sw*NUM_SPACES
                    xtol = XTOL*w.sw/w.sf;
                    
                    bl2 = w2.pts_ut[0];
                    br1 = w.pts_ut[3];      
                    if bl2.x > br1.x + dx/w.sf + xtol:
                        splits.append(ii);
                ln.splits = splits; ln.sws = sws;
            
                if len(splits)>0:
                    for ii in reversed(range(len(splits))):
                        sstart = splits[ii];
                        if ii!=len(splits)-1:
                            sstop  = splits[ii+1]
                        else:
                            sstop = len(ln.ws)

                        newtxt,nll = ll.Split_Off_Words(sws[sstart:sstop])
                        os.append(newtxt);
                        newlls.append(nll)
    lls+=newlls;    
    return lls,os    

import numpy as np
def External_Merges(lls,os,mergenearby,mergesupersub):
    # Generate list of merges     
    ws = [];
    for ll in lls:           
        if ll.lns is not None:
            ws += [w for ln in ll.lns for w in ln.ws];
        # ll.Position_Check()
    for w in ws:
        dx = w.sw*(NUM_SPACES+1*XTOL) # a big bounding box that includes the extra space
        if w.orig_bb is not None:
            w.bb_big = TextParser.bbox([w.orig_bb.x1-dx,w.orig_bb.y1-dx,w.orig_bb.w+2*dx,w.orig_bb.h+2*dx])
        else:
            w.bb_big = TextParser.bbox([w.bb.x1-dx,w.bb.y1-dx,w.bb.w+2*dx,w.bb.h+2*dx])
        w.mw = []
    
    # Vectorized angle / bbox calculations
    angles = np.array([[w.angle for w in ws]]);
    sameangle = (abs(angles-angles.T)<.001)
    xc1,yc1,wd1,ht1,xc2,yc2,wd2,ht2 = np.zeros((8,len(ws)))
    for ii in range(len(ws)):
        box1 = ws[ii].bb_big;
        box2 = ws[ii].bb;
        if ws[ii].orig_bb is not None:
            box2 = ws[ii].orig_bb
        xc1[ii] = box1.xc; yc1[ii] = box1.yc; wd1[ii] = box1.w;  ht1[ii] = box1.h
        xc2[ii] = box2.xc; yc2[ii] = box2.yc; wd2[ii] = box2.w;  ht2[ii] = box2.h
    intersects =  np.logical_and((abs(xc1.reshape(-1,1) - xc2) * 2 < (wd1.reshape(-1,1) + wd2)), \
                                 (abs(yc1.reshape(-1,1) - yc2) * 2 < (ht1.reshape(-1,1) + ht2))); # reshape(-1,1) is a transpose
    potentials = np.logical_and(sameangle,intersects)
    potentials = np.logical_and(potentials,np.identity(len(ws))==0) #off-diagonal only
    goodl = np.argwhere(potentials)
         
    
    for ii in range(goodl.shape[0]):
        w = ws[goodl[ii,0]]
        w2= ws[goodl[ii,1]]

        dx   = w.sw*NUM_SPACES/w.sf
        xtol = XTOL*w.sw/w.sf;
        ytol = YTOL*w.sw/w.sf;

        # calculate 2's coords in 1's system
        tr1, br1, tl2, bl2 = w.get_orig_pts(w2)
        xpenmatch = (br1.x-xtol <= bl2.x <= br1.x + dx + xtol);
        neitherempty = len(wstrip(w.txt()))>0 and len(wstrip(w2.txt()))>0
        if xpenmatch and neitherempty:
            type = None;
            # samecolor = Style2(w2.cs[0].nstyc).get('fill')==Style2(w.cs[-1].nstyc).get('fill')
            if abs(bl2.y-br1.y)<ytol and abs(w.fs-w2.fs)<.001 and mergenearby:
                if not(isnumeric(w.ln.txt())) or not(isnumeric(w2.ln.txt())) \
                   or w.ln.ll.inittextel==w2.ln.ll.inittextel: # don't merge two numbers (may be ticks)
                    type = 'same';
                # dh.debug(w.txt()+' '+w2.txt())
            elif br1.y+ytol >= bl2.y >= tr1.y-ytol and mergesupersub: # above baseline
                aboveline = br1.y*(1-SUBSUPER_YTHR)+tr1.y*SUBSUPER_YTHR+ytol >= bl2.y;
                if w2.fs<w.fs*SUBSUPER_THR-.01: # new smaller, expect super
                    if aboveline: 
                        type = 'super';
                elif w.fs<w2.fs*SUBSUPER_THR-.01: # old smaller, expect reutrn
                        type = 'subreturn';
                else:
                    if aboveline: 
                        type = 'superorsubreturn'; # could be either, decide later
                    else:
                        type = 'subreturn';
            elif br1.y+ytol >= tl2.y >= tr1.y-ytol and mergesupersub:
                belowline = tl2.y >= br1.y*SUBSUPER_YTHR+tr1.y*(1-SUBSUPER_YTHR)-ytol;
                if w2.fs<w.fs*SUBSUPER_THR-.01: # new smaller, expect sub
                    if  belowline:
                        type = 'sub';
                elif w.fs<w2.fs*SUBSUPER_THR+.01: # old smaller, expect superreturn
                        type = 'superreturn'
                else:
                    if  belowline:
                        type = 'suborsuperreturn'; # could be either, decide later
                    else:
                        type = 'superreturn';
            if type is not None:
                w.mw.append([w2,type,br1,bl2])
#                            dh.debug(w.txt+' to '+w2.txt+' as '+type)

        if DEBUG_MERGE:
            dh.debug('\nMerging '+w.txt() + ' and ' + w2.txt())
            if not(xpenmatch):
                dh.debug('Aborted, x pen too far: '+str([br1.x,bl2.x]))
            elif not(neitherempty):
                dh.debug('Aborted, one empty')
            else:
                if type is None:
                    if not(abs(bl2.y-br1.y)<ytol):
                        dh.debug('Aborted, y pen too far: '+str([bl2.y,br1.y]))
                    elif not(abs(w.fs-w2.fs)<.001):
                        dh.debug('Aborted, fonts too different: '+str([w.fs,w2.fs]))
                    elif not(not(isnumeric(w.ln.txt())) or not(isnumeric(w2.ln.txt()))):
                        dh.debug('Aborted, both numbers')
                else:
                    dh.debug('Merged as '+type)

    Perform_Merges(ws)
    return lls,os

def Remove_Manual_Kerning(lls,os,mergesupersub):
    # Generate list of merges     
    ws = [];
    for ll in lls:           
        if ll.lns is not None:
            ws += [w for ln in ll.lns for w in ln.ws];
        # ll.Position_Check()
    for w in ws:
        dx = w.sw*(NUM_SPACES+1*XTOL) # a big bounding box that includes the extra space
        w.bb_big = TextParser.bbox([w.bb.x1-dx,w.bb.y1-dx,w.bb.w+2*dx,w.bb.h+2*dx])
    # for w in ws:
    #     while w.nextw is not None and w.txt()[-1]==' ' and w.nextw.txt()==' ':
    #         w.nextw = w.nextw.nextw;
    for w in ws:
        mw = [];
        dx = w.sw*NUM_SPACES/w.sf
        xtol2 = XTOLMK*w.sw/w.sf;

        w2=w.nextw       # part of the same line, so same transform and y
        if w2 is not None and w2 in ws:
            bl2 = w2.pts_ut[0];
            br1 = w.pts_ut[3];
            if br1.x-xtol2 <= bl2.x <= br1.x + dx + xtol2:
                mw.append([w2,'same',br1,bl2])
        w.mw = mw;
        
    Perform_Merges(ws)    
                    
    # Following manual kerning removal, lines with multiple words need to be split out into new text els
    newlls=[];
    for ll in lls:
        for ln in ll.lns:
            while len(ln.ws)>1:
                newtxt,nll = ll.Split_Off_Words([ln.ws[-1]])
                os.append(newtxt)
                newlls.append(nll)
    lls+=newlls
    return lls,os

def Perform_Merges(ws):
    for w in ws:
        mw = w.mw;
        # Amongst all candidate merges, pick the one whose starting pen best matches the stop of the previous one
        minx = float('inf');
        for ii in range(len(mw)):
            w2=mw[ii][0]; type=mw[ii][1]; br1=mw[ii][2]; bl2=mw[ii][3];
            if abs(bl2.x-br1.x) < minx:
                minx = abs(bl2.x-br1.x);
                mi   = ii
        w.merges = [];
        w.mergetypes = [];
        w.merged = False;
        # if w.txt()==' ':
        #     dh.debug(w.nextw.txt())
        if len(mw)>0:
            w2=mw[mi][0]; type=mw[mi][1]; br1=mw[mi][2]; bl2=mw[mi][3];
            w.merges     = [w2];
            w.mergetypes = [type];
            # dh.debug(w.txt()+' in '+w.ln.el.get_id()+' to '+ w.merges[0].txt()+' in '+w2.ln.el.get_id()+' as '+w.mergetypes[0])
        
    
    # Generate chains of merges
    for w in ws:
        # if w.txt=='T':
        if not(w.merged) and len(w.merges)>0:
            w.merges[-1].merged = True;
            nextmerge  = w.merges[-1].merges
            nextmerget = w.merges[-1].mergetypes
            while len(nextmerge)>0:
                w.merges += nextmerge
                w.mergetypes += nextmerget
                w.merges[-1].merged = True;
                nextmerge  = w.merges[-1].merges
                nextmerget = w.merges[-1].mergetypes
    
    # Create a merge plan            
    for w in ws:
        if len(w.merges)>0:
            ctype = 'normal';
            w.wtypes = [ctype]; bail=False;
            for mt in w.mergetypes:
                if ctype=='normal':
                    if   mt=='same':             pass
                    elif mt=='sub':              ctype = 'sub';
                    elif mt=='super':            ctype = 'super';
                    elif mt=='suborsuperreturn': ctype = 'sub';
                    elif mt=='superorsubreturn': ctype = 'super';
                    elif all([t=='normal' for t in w.wtypes]): # maybe started on sub/super
#                        if mt=='subreturn':
#                            w.wtypes = ['sub']*len(w.wtypes);
#                            ctype = 'normal';
#                        elif mt=='superreturn':
#                            w.wtypes = ['super']*len(w.wtypes);
#                            ctype = 'normal';
                        bail = True
                    else: bail=True
                elif ctype=='super':
                    if   mt=='same':             pass
                    elif mt=='superreturn':      ctype = 'normal'
                    elif mt=='suborsuperreturn': ctype = 'normal'
                    else:                        bail=True
                elif ctype=='sub':
                    if   mt=='same':             pass
                    elif mt=='subreturn':        ctype = 'normal'
                    elif mt=='superorsubreturn': ctype = 'normal'
                    else:                        bail = True
                w.wtypes.append(ctype)
            if bail==True:
                w.wtypes = []
                w.merges = []
        # dh.debug(w.merges)
    # Pre-merge position calculation
    # for w in ws:
    #     w.premerge_br = w.pts_t[3];
    # Execute the merge plan
    for w in ws:
        if len(w.merges)>0 and not(w.merged):
            for ii in range(len(w.merges)):
                w.appendw(w.merges[ii],w.wtypes[ii+1]);
            for c in w.cs:
                if c.pending_style is not None:
                    c.applypending();

# Check if text represents a number
ncs = ['0','1','2','3','4','5','6','7','8','9','.','e','E','-','−',','];
def isnumeric(s):
    allnum = all([sv in ncs for sv in s]);
    isnum=False
    if allnum:
        try:
            s = s.replace('−','-').replace(',',''); # replace minus signs with -, remove commas
            float(s);
            isnum = True
        except:
            isnum = False
    return isnum
                
# Strip whitespaces
def wstrip(txt): 
     return txt.translate({ord(c):None for c in ' \n\t\r'}); 


## for w in ws:
#    # mw = [];
#    dx = w.sw*NUM_SPACES
#    xtol  = XTOL*w.sw/w.sf;
#    ytol = YTOL*w.sw/w.sf;
#    # for w2 in ws:
#    if w2 is not w:
#        # sameangle=samenstyc=False;
#        # sameangle   = abs(w2.angle-w.angle)<.001;
#        # if sameangle:
#        if True:
#            # if w2.orig_bb is not None:
#            #     bbintersects = w.bb_big.intersect(w2.orig_bb);
#            # else:
#            #     bbintersects = w.bb_big.intersect(w2.bb);
#            # samenstyc   = w2.cs[0].nstyc==w.cs[-1].nstyc;
#            # allgood.append(bbintersects==intersects[sameanglel[ii,0],sameanglel[ii,1]])
#            # if bbintersects: # so we don't waste time transforming, check if bboxes overlap
#            if True: # so we don't waste time transforming, check if bboxes overlap
#                # calculate 2's coords in 1's system

    
# Recursively delete empty elements
# Tspans are deleted if they're totally empty, TextElements are deleted if they contain only whitespace
# def deleteempty(el):
#     for k in el.getchildren():
#         deleteempty(k)
#     txt = el.text;
#     tail = el.tail;
#     if (txt is None or len((txt))==0) and (tail is None or len((tail))==0) and len(el.getchildren())==0:
#         el.delete();                    # delete anything empty
#     elif isinstance(el, (TextElement)):    
#         def wstrip(txt): # strip whitespaces
#              return txt.translate({ord(c):None for c in ' \n\t\r'}); 
#         if all([(d.text is None or len(wstrip(d.text))==0) and (d.tail is None or len(wstrip(d.tail))==0) for d in dh.descendants2(el)]):
#             el.delete(); # delete any text elements that are just white space    
    
# No longer used
#def All_Merges(lls,os,removemanual,mergenearby,mergesupersub):
#    # Generate list of merges     
#    ws = [];
#    for ll in lls:           
#        if ll.lns is not None:
#            ws += [w for ln in ll.lns for w in ln.ws];
#        # ll.Position_Check()
#    for w in ws:
#        dx = w.sw*(NUM_SPACES+1*XTOL) # a big bounding box that includes the extra space
#        w.bb_big = TextParser.bbox([w.bb.x1-dx,w.bb.y1-dx,w.bb.w+2*dx,w.bb.h+2*dx])
#    for w in ws:
#        mw = [];
#        dx = w.sw*NUM_SPACES
#        xtol  = XTOL*w.sw/w.sf;
#        xtol2 = XTOLMK*w.sw/w.sf;
#        ytol = YTOL*w.sw/w.sf;
#        for w2 in ws:
#            if w2 is not w:
#                sameangle=samenstyc=diffparents=False;
#                sameangle   = abs(w2.angle-w.angle)<.001;
#                diffparents = (w.cs[-1].loc.el!=w2.cs[0].loc.el or w.cs[-1].loc.tt!=w2.cs[0].loc.tt);
#                if sameangle and diffparents:    
#                    bbintersects = w.bb_big.intersect(w2.bb)
#                    samenstyc   = w2.cs[0].nstyc==w.cs[-1].nstyc;
#                    if bbintersects: # so we don't waste time transforming, check if bboxes overlap
#                        # calculate 2's coords in 1's system
#                        bl2 = (-w.transform).apply_to_point(w2.pts_t[0])
#                        tl2 = (-w.transform).apply_to_point(w2.pts_t[1])
#                        tr1 = w.pts_ut[2];
#                        br1 = w.pts_ut[3];
#                        xpenmatch = (br1.x-xtol <= bl2.x <= br1.x + dx/w.sf + xtol);
#                        if xpenmatch:
#                            type = None;
#                            samecolor = Style(w2.cs[0].nstyc).get('fill')==Style(w.cs[-1].nstyc).get('fill')
#                            if abs(bl2.y-br1.y)<ytol and abs(w.fs-w2.fs)<.001 and (removemanual or mergenearby):
#                                if (w.cs[0].loc.textel == w2.cs[-1].loc.textel and removemanual) or mergenearby:
#                                    if not(isnumeric(w.ln.txt())) or not(isnumeric(w2.ln.txt())): # don't merge two numbers (may be ticks)
#                                        type = 'same';
#                                # dh.debug(w.txt()+' '+w2.txt())
#                            elif br1.y+ytol >= bl2.y >= tr1.y-ytol and mergesupersub and samecolor:
#                                if   w2.fs<w.fs*SUBSUPER_THR: 
#                                    type = 'super';
#                                elif w.fs<w2.fs*SUBSUPER_THR:
#                                    type = 'subreturn';
#                            elif br1.y+ytol >= tl2.y >= tr1.y-ytol and mergesupersub and samecolor:
#                                if   w2.fs<w.fs*SUBSUPER_THR:
#                                    type = 'sub';
#                                elif w.fs<w2.fs*SUBSUPER_THR:
#                                    type = 'superreturn'
#                            if type is not None:
#                                mw.append([w2,type,br1,bl2])
##                                    dh.debug(w.txt+' to '+w2.txt+' as '+type)
#                elif w2==w.nextw and removemanual:       # part of the same line, so same transform and y
#                    bl2 = w2.pts_ut[0];
#                    br1 = w.pts_ut[3];
#                    if br1.x-xtol2 <= bl2.x <= br1.x + dx/w.sf + xtol2:
#                        mw.append([w2,'same',br1,bl2])
#                        # dh.debug(w.txt() +' in '+w.cs[0].loc.el.get_id()   + ' to ' \
#                        #         +w2.txt() +' in '+w2.cs[0].loc.el.get_id())
#
#                if DEBUG_MERGE:
#                    dh.debug('\nMerging '+w.txt() + ' and ' + w2.txt())
#                    if not(sameangle): dh.debug('Aborted, diff angles: '+str([w.angle,w2.angle]))
#                    elif not(samenstyc): dh.debug('Aborted, diff styles: '+str([w.cs[-1].nstyc,w2.cs[0].nstyc]))
#                    elif not(diffparents): dh.debug('Aborted, same parent');
#                    if sameangle and samenstyc and diffparents:
#                        if not(bbintersects): dh.debug('Aborted, bounding box too far');
#                        else:
#                            if not(xpenmatch): dh.debug('Aborted, x pen too far: '+str([br1.x,bl2.x]))
#        
#        # Amongst all candidate merges, pick the one whose starting pen best matches the stop of the previous one
#        minx = float('inf');
#        for ii in range(len(mw)):
#            w2=mw[ii][0]; type=mw[ii][1]; br1=mw[ii][2]; bl2=mw[ii][3];
#            if abs(bl2.x-br1.x) < minx:
#                minx = abs(bl2.x-br1.x);
#                mi   = ii
#        w.merges = [];
#        w.mergetypes = [];
#        w.merged = False;
#        # if w.txt()==' ':
#        #     dh.debug(w.nextw.txt())
#        if len(mw)>0:
#            w2=mw[mi][0]; type=mw[mi][1]; br1=mw[mi][2]; bl2=mw[mi][3];
#            w.merges     = [w2];
#            w.mergetypes = [type];
#            # dh.debug(w.txt()+' in '+w.ln.el.get_id()+' to '+ w.merges[0].txt()+' in '+w2.ln.el.get_id()+' as '+w.mergetypes[0])
#        
#    # Generate chains of merges
#    for w in ws:
#        # if w.txt=='T':
#        if not(w.merged) and len(w.merges)>0:
#            w.merges[-1].merged = True;
#            nextmerge  = w.merges[-1].merges
#            nextmerget = w.merges[-1].mergetypes
#            while len(nextmerge)>0:
#                w.merges += nextmerge
#                w.mergetypes += nextmerget
#                w.merges[-1].merged = True;
#                nextmerge  = w.merges[-1].merges
#                nextmerget = w.merges[-1].mergetypes
#    
#    # Create a merge plan            
#    for w in ws:
#        if len(w.merges)>0:
#            ctype = 'normal';
#            w.wtypes = [ctype]; bail=False;
#            for mt in w.mergetypes:
#                if ctype=='normal':
#                    if   mt=='same':        pass
#                    elif mt=='sub':         ctype = 'sub';
#                    elif mt=='super':       ctype = 'super';
#                    elif all([t=='normal' for t in w.wtypes]): # maybe started on sub/super
#                        bail = True
#                    else: bail=True
#                elif ctype=='super':
#                    if   mt=='same':        pass
#                    elif mt=='superreturn': ctype = 'normal'
#                    else:                   bail=True
#                elif ctype=='sub':
#                    if   mt=='same':        pass
#                    elif mt=='subreturn':   ctype = 'normal'
#                    else:                   bail = True
#                w.wtypes.append(ctype)
#            if bail==True:
#                w.wtypes = []
#                w.merges = []
#        # dh.debug(w.merges)
#    # Pre-merge position calculation
#    for w in ws:
#        w.premerge_br = w.pts_t[3];
#    # Execute the merge plan
#    for w in ws:
#        # debug(ws[0].ln.xsrc.get_id())
#        if len(w.merges)>0 and not(w.merged):
#            for ii in range(len(w.merges)):
#                w.appendw(w.merges[ii],w.wtypes[ii+1])
#            for c in w.cs:
#
#                if c.pending_style is not None:
#                    c.applypending();
#    
#    # Following manual kerning removal, lines with multiple words need to be split out
#    if mergenearby:
#        newlls=[];
#        for ll in lls:
#            for ln in ll.lns:
#                while len(ln.ws)>1:
#                    newtxt,nll = ll.Split_Off_Words([ln.ws[-1]])
#                    os.append(newtxt)
#                    newlls.append(nll)
#        lls+=newlls
#    return lls,os