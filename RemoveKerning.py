import inkex
from inkex import (
    TextElement, FlowRoot, FlowPara, FlowSpan, Tspan, TextPath, Rectangle, \
        addNS, Transform, Style, ClipPath, Use, NamedView, Defs, \
        Metadata, ForeignObject, Vector2d, Path, Line, PathElement,command,\
        SvgDocumentElement,Image,Group,Polyline,Anchor,Switch,ShapeElement, BaseElement,FlowRegion)
import TextParser
import dhelpers as dh

diagmode = True;
diagmode = False;

def remove_kerning(caller,os,fixshattering,mergesupersub,splitdistant,mergenearby,justification=None):
    NUM_SPACES = 1.0;   # number of spaces beyond which text will be merged/split
    XTOL = 0.5          # x tolerance (number of spaces)...let be big since there are kerning inaccuracies
    YTOL = 0.01         # y tolerance (number of spaces)...can be small
    SUBSUPER_THR = 0.9;  # ensuring sub/superscripts are smaller helps reduce false merges
    
    
    ct = TextParser.Character_Table(os,caller)
    ws = []; lls=[]
    for el in os:
        # debug(el.get_id());
        # debug(selected_style_local(el));
        if isinstance(el,TextElement) and el.getparent() is not None:
            lls.append(TextParser.LineList(el,ct,debug=False));
            if diagmode: 
                lls[-1].Position_Check();
            if lls[-1].lns is not None:
                ws += [w for ln in lls[-1].lns for w in ln.ws];
    
    # for ll in lls:
    #     for ln in ll.lns:
    #         debug(ln.x)
    #         debug(ln.dx)
    
    if not(diagmode):
        # Generate splits
        if splitdistant:
            for ll in lls:
                if ll.lns is not None:
                    for il in range(len(ll.lns)):
                        ln = ll.lns[il];
                        sws = [x for _, x in sorted(zip([w.x for w in ln.ws], ln.ws), key=lambda pair: pair[0])] # words sorted in ascending x
                        splits = [];
                        for ii in range(1,len(ln.ws)):
                            w = sws[ii-1]
                            w2= sws[ii]
                            dx = w.sw*NUM_SPACES
                            xtol = XTOL*w.sw/w.sf;
                            
                            bl2 = w2.pts_ut[0]; tl2 = w2.pts_ut[1];
                            tr1 = w.pts_ut[2];  br1 = w.pts_ut[3];      
                            if bl2.x > br1.x + dx/w.sf + xtol:
                                splits.append(ii);
                        for ii in reversed(range(len(splits))):
                            sstart = splits[ii];
                            if ii!=len(splits)-1:
                                sstop  = splits[ii+1]
                            else:
                                sstop = len(ln.ws)
                            # to split, duplicate the whole text el and delete all other lines/words
                            newtxt = dh.duplicate2(ln.ws[sstart].cs[0].loc.textel);
                            os.append(newtxt)
                            nll = TextParser.LineList(newtxt,ct);
                            
                            
                            # Record position and d
                            x0 = sws[sstart].x
                            dxl = [c.dx for w in sws[sstart:sstop] for c in w.cs];
                            y0 = sws[sstart].y
                            dyl = [c.dy for w in sws[sstart:sstop] for c in w.cs];
                            
                            for jj in reversed(range(sstart,sstop)):
                                sws[jj].delw();
                            for il2 in reversed(range(len(nll.lns))):
                                if il2!=il:
                                    nll.lns[il2].dell();
                                else:
                                    nln = nll.lns[il2];
                                    nsws = [x for _, x in sorted(zip([w.x for w in nln.ws], nln.ws), key=lambda pair: pair[0])] # words sorted in ascending x
                                    nsws[sstart].cs[0].loc.el.set('x',str(x0))
                                    for jj in reversed(range(len(nsws))):
                                        if not(jj in list(range(sstart,sstop))):
                                            nsws[jj].delw();
                                            

                            for d in newtxt.descendants(): d.set('dx',None)
                            newtxt.set('dx',' '.join([str(v) for v in dxl]));
                            for d in newtxt.descendants(): d.set('dy',None)
                            newtxt.set('dy',' '.join([str(v) for v in dyl]));
                                            
                            lls.append(nll)
                            
        
        # Generate list of merges     
        ws = [];
        for ll in lls:           
            if ll.lns is not None:
                ws += [w for ln in ll.lns for w in ln.ws];
        for w in ws:
            dx = w.sw*NUM_SPACES # a big bounding box that includes the extra space
            w.bb_big = TextParser.bbox([w.bb.x1-dx,w.bb.y1-dx,w.bb.w+2*dx,w.bb.h+2*dx])
        for w in ws:
            mw = [];
            dx = w.sw*NUM_SPACES
            xtol = XTOL*w.sw/w.sf;
            ytol = YTOL*w.sw/w.sf;
            # debug(w.txt())
            # debug(w.ww)
            # debug(w.pts_t[0].x)
            # debug(w.pts_t[3].x)
            # debug(w.transform)
            for w2 in ws:
                if w2 is not w:
                    # if len(w2.cs)==0:
                    #     debug(w2)
                    # debug(abs(w2.angle-w.angle)<.001)
                    # debug(w.txt() + ' ' + w2.txt())
                    # debug(w2.cs[0].nstyc==w.cs[-1].nstyc)
                    # debug(w.cs[-1].nstyc)
                    # debug(w2.cs[0].nstyc)
                    # debug((w.cs[-1].loc.el!=w2.cs[0].loc.el or w.cs[-1].loc.tt!=w2.cs[0].loc.tt))
                    if abs(w2.angle-w.angle)<.001 and \
                        w2.cs[0].nstyc==w.cs[-1].nstyc and \
                        (w.cs[-1].loc.el!=w2.cs[0].loc.el or w.cs[-1].loc.tt!=w2.cs[0].loc.tt):        # different parents
                        if w.bb_big.intersect(w2.bb): # so we don't waste time transforming, check if bboxes overlap
                            # calculate 2's coords in 1's system
                            bl2 = (-w.transform).apply_to_point(w2.pts_t[0])
                            tl2 = (-w.transform).apply_to_point(w2.pts_t[1])
                            tr1 = w.pts_ut[2];
                            br1 = w.pts_ut[3];
                            # debug(w.txt() + ' ' + w2.txt())
                            # debug(w.pts_t[3].x)
                            # debug(w2.pts_t[0].x)
                            # debug(br1.x)
                            # debug(bl2.x)
                            # debug(br1.x + dx/w.sf + xtol)
                            if br1.x-xtol <= bl2.x <= br1.x + dx/w.sf + xtol:
                                type = None;
                                if abs(bl2.y-br1.y)<ytol and abs(w.fs-w2.fs)<.001 and (fixshattering or mergenearby):
                                    if (w.cs[0].loc.textel == w2.cs[-1].loc.textel and fixshattering) or mergenearby:
                                        type = 'same';
                                    # debug(w.txt+' '+w2.txt)
                                elif br1.y+ytol >= bl2.y >= tr1.y-ytol and mergesupersub:
                                    if   w2.fs<w.fs*SUBSUPER_THR: 
                                        type = 'super';
                                    elif w.fs<w2.fs*SUBSUPER_THR:
                                        type = 'subreturn';
                                elif br1.y+ytol >= tl2.y >= tr1.y-ytol and mergesupersub:
                                    if   w2.fs<w.fs*SUBSUPER_THR:
                                        type = 'sub';
                                    elif w.fs<w2.fs*SUBSUPER_THR:
                                        type = 'superreturn'
                                if type is not None:
                                    mw.append([w2,type,br1,bl2])
    #                                    dh.debug(w.txt+' to '+w2.txt+' as '+type)
                    elif w2==w.nextw and fixshattering:       # part of the same line, so same transform and y
                        bl2 = w2.pts_ut[0];
                        br1 = w.pts_ut[3];
                        mw.append([w2,'same',br1,bl2])
            
            minx = float('inf');
            for ii in range(len(mw)):
                w2=mw[ii][0]; type=mw[ii][1]; br1=mw[ii][2]; bl2=mw[ii][3];
                if bl2.x < minx:
                    minx = bl2.x; # only use the furthest left one
                    mi   = ii
            w.merges = [];
            w.mergetypes = [];
            w.merged = False;
            if len(mw)>0:
                w2=mw[mi][0]; type=mw[mi][1]; br1=mw[mi][2]; bl2=mw[mi][3];
                w.merges     = [w2];
                w.mergetypes = [type];
                # debug(w.txt+' to '+ w.merges[0].txt+' as '+w.mergetypes[0])
            
        # Generate chains of merges
        for w in ws:
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
                        if   mt=='same':        pass
                        elif mt=='sub':         ctype = 'sub';
                        elif mt=='super':       ctype = 'super';
                        elif all([t=='normal' for t in w.wtypes]): # maybe started on sub/super
                            bail = True
                            # if mt=='superreturn':
                            #     w.wtypes = ['super' for t in w.wtypes];
                            #     ctype = 'normal'
                            # elif mt=='subreturn':
                            #     w.wtypes = ['sub' for t in w.wtypes];
                            #     ctype = 'normal'
                            # else: bail=True
                        else: bail=True
                    elif ctype=='super':
                        if   mt=='same':        pass
                        elif mt=='superreturn': ctype = 'normal'
                        else:                   bail=True
                    elif ctype=='sub':
                        if   mt=='same':        pass
                        elif mt=='subreturn':   ctype = 'normal'
                        else:                   bail = True
                    w.wtypes.append(ctype)
                if bail==True:
                    w.wtypes = []
                    w.merges = []
        # Execute the merge plan
        for w in ws:
            # debug(ws[0].ln.xsrc.get_id())
            if len(w.merges)>0 and not(w.merged):
                # debug(w.mergetypes)
                # if w.wtypes[0]=='sub' or w.wtypes[0]=='super': # initial sub/super
                #     iin = [v=='normal' for v in w.wtype].index(True) # first normal index
                #     fc = w.cs[0]
                for ii in range(len(w.merges)):
                    # debug(w.txt)
                    # debug(w.merges[ii].txt)
                    w.appendw(w.merges[ii],w.wtypes[ii+1])
                for c in w.cs:
                    if c.type=='super' or c.type=='sub':
                        c.makesubsuper(round(c.reduction_factor*100));
        
        # Split different lines
        if splitdistant:       
            newlls = []; dellls = [];            
            for jj in range(len(lls)):
                ll = lls[jj];
                if ll.lns is not None and len(ll.lns)>1:
                    for il in reversed(range(1,len(ll.lns))):
                        # To split by line, duplicate the whole text el and delete all other lines
                        ln = ll.lns[il]; # line to be popped out
                        if len(ln.cs)>0:
                            newtxt = dh.duplicate2(ll.textel);
                            os.append(newtxt)
                            nll = TextParser.LineList(newtxt,ct,debug=False);
                            nln = nll.lns[il]  # new copy of line
                            
                            # Record positions and d's
                            x0 = nln.ws[0].x
                            dxl = [c.dx for c in ln.cs];# dh.debug(dxl)
                            y0 = nln.ws[0].y
                            dyl = [c.dy for c in ln.cs];

                            # dh.debug(nll.txt())
                            # Delete other lines
                            ln.dell();
                            if nll.lns is not None:
                                for il2 in reversed(range(len(nll.lns))):
                                    if il2!=il:
                                        nll.lns[il2].dell();
                            
                            deleteempty(newtxt)                               # prune empty Tspans
                            if newtxt.getparent() is not None:
                                for d in newtxt.descendants(): d.set('dx',None)
                                newtxt.set('dx',' '.join([str(v) for v in dxl]));
                                for d in newtxt.descendants(): d.set('dy',None)
                                newtxt.set('dy',' '.join([str(v) for v in dyl]));
                                nll = TextParser.LineList(newtxt,ct,debug=False); # reparse since we deleted lines
                                if len(nll.lns)>0:
                                    nll.lns[0].change_pos([x0],[y0])

                                newlls.append(nll)
                    
                    deleteempty(ll.textel);
                    if ll.textel.getparent() is not None:
                        lls[jj]=TextParser.LineList(ll.textel,ct,debug=False);
                    else:
                        dellls.append(lls[jj])
                        
            lls = lls+newlls;
            for dll in dellls: lls.remove(dll) 
        if justification is not None:
            for ll in lls:
                # ll.Position_Check()
                for ln in ll.lns:
                    ln.change_alignment(justification);
                dh.Set_Style_Comp(ll.textel,'text-anchor',justification)
                alignd = {'start': 'start', 'middle': 'center', 'end': 'end'}
                dh.Set_Style_Comp(ll.textel,'text-align' ,alignd[justification])
                        
    # Clean up empty elements and make editable
    for el in reversed(os):
         if isinstance(el,TextElement) and el.getparent() is not None:
              deleteempty(el)
              inkscape_editable(el)
#                 el.set('xml:space','preserve')  
                
    # os = [el for el in os if el.getparent() is not None]            
    # lls=[]
    # for el in os:
    #     if isinstance(el,TextElement) and el.getparent() is not None:
    #         lls.append(TextParser.LineList(el,ct,debug=False));
    # if justification is not None:
    #     for ll in lls:
    #         for ln in ll.lns:
    #             ln.change_alignment(justification);
    #         alignd = {'start': 'start', 'middle': 'center', 'end': 'end'}
    #         dh.Set_Style_Comp(ll.textel,'text-anchor',justification)
    #         dh.Set_Style_Comp(ll.textel,'text-align' ,alignd[justification]);
    
#    for el in os:
#        inkscape_editable(el);
        
    return os
            
    
# Recursively delete empty elements
# Tspans are deleted if they're totally empty, TextElements are deleted if they contain only whitespace
def deleteempty(el):
    for k in el.getchildren():
        deleteempty(k)
    txt = el.text;
    tail = el.tail;
    if (txt is None or len((txt))==0) and (tail is None or len((tail))==0) and len(el.getchildren())==0:
        el.delete();                    # delete anything empty
    elif isinstance(el, (TextElement)):    
        def wstrip(txt): # strip whitespaces
             return txt.translate({ord(c):None for c in ' \n\t\r'}); 
        if all([(d.text is None or len(wstrip(d.text))==0) and (d.tail is None or len(wstrip(d.tail))==0) for d in dh.descendants2(el)]):
            el.delete(); # delete any text elements that are just white space
        
            
def inkscape_editable(el):
    if not(diagmode):
        ks=el.getchildren();
        for k in ks:
            if isinstance(k, (Tspan,TextElement)):
                inkscape_editable(k)
        if isinstance(el,TextElement):  # enable xml preserve so we can add spaces
            el.set('xml:space','preserve')      
        elif isinstance(el,Tspan):
            myp = el.getparent();
            if myp is not None and len(myp.getchildren())==1 and isinstance(myp,TextElement):  # only child, no nesting
                if el.get('sodipodi:role')!='line':
                    tx = el.get('x'); ty=el.get('y');
                    myp = el.getparent();
                    if tx is not None: myp.set('x',tx)      # enabling sodipodi causes it to move to the parent's x and y
                    if ty is not None: myp.set('y',ty)      # enabling sodipodi causes it to move to the parent's x and y
                    el.set('sodipodi:role','line'); # reenable sodipodi so we can insert returns