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

# The TextParser parses text in a document according to the way Inkscape handles it.
# In short, every TextElement is parsed into a LineList.
# Each LineList contains a collection of tlines, representing one line of text.
# Each tline contains a collection of tchars, representing a single character.
# Characters are also grouped into twords, which represent groups of characters with the same position.


KERN_TABLE = False;   # if enabled, generates a kern table for each font (slower, but more accurate)

import os,sys
sys.path.append(os.path.dirname(os.path.realpath(sys.argv[0]))) # make sure my directory is on the path
import dhelpers as dh

import copy
import inkex
from inkex import (TextElement, Tspan ,Vector2d,Transform)
from Style2 import Style2

global debug
debug = False;



# A text element that has been parsed into a list of lines
class LineList():
    def __init__(self, el, ctable,debug=False):
        self.ctable = ctable
        self.textel = el;
        self.inittextel = el;                           # prior to any merging/splitting/etc
        
        # self.lns = self.Parse_Lines(el,debug=debug);
        # self.Finish_Lines();
        
        self.lns = self.Parse_Lines2(el,debug=debug);
        self.Finish_Lines2();
        
        for ln in self.lns:
            for w in ln.ws:
                w.parsed_bb = copy.deepcopy(w.bb);
                for c in w.cs:
                    c.parsed_pts_ut, c.parsed_pts_t = c.interp_pts()
                
        # dh.debug('\n')
        # for ln in self.lns:
        #     dh.debug(ln.txt())
        #     dh.debug(ln.el.get_id())
        #     dh.debug(ln.xsrc.get_id())
        #     dh.debug(ln.x)
        #     dh.debug(ln.sprl)
        #     dh.debug(ln.tlvlno)
        
        tlvllns = [ln for ln in self.lns if ln.tlvlno is not None and ln.tlvlno>0]; # top-level lines after 1st
        self.isinkscape = all([ln.sprl for ln in tlvllns]) and len(tlvllns)>0 and\
                          all([ln.style.get('-inkscape-font-specification') is not None \
                               for ln in self.lns]); # probably made in Inkscape
        self.dxs = [c.dx for ln in self.lns for c in ln.cs]; 
        self.dys = [c.dy for ln in self.lns for c in ln.cs]; self.flatdelta = False;

    def duplicate(self):
        # Duplicates a LL and its text
        ret = copy.copy(self);
        ret.textel = dh.duplicate2(self.textel);
        ret.inittextel = self.textel;
        d1 = dh.descendants2(self.textel);
        d2 = dh.descendants2(ret.textel);
        ret.ctable = self.ctable
        ret.lns = []
        for ln in self.lns:
            eli = d1.index(ln.el);
            xsi = d1.index(ln.xsrc);
            ysi = d1.index(ln.ysrc);
            ret.lns.append(tline(copy.copy(ln.x), copy.copy(ln.y), ln.sprl, ln.nominalspr, ln.anchor, \
                                  ln.transform,ln.angle,\
                                  d2[eli],d2[xsi],d2[ysi],ln.tlvlno,ln.style,ln.continuex));
            ret.lns[-1].anchor = ln.anchor;
            ret.lns[-1].cs = []
            for c in ln.cs:
                myi = d1.index(c.loc.el);
                newloc = cloc(d2[myi],c.loc.tt,c.loc.ind);
                prop = copy.copy(c.prop); prop.charw = c.cw;
#                    prop = self.ctable.get_prop(' ',c.nsty)*c.fs # cannot just use old one for some reason???
                ret.lns[-1].addc(tchar(c.c,c.fs,c.sf,prop,c.sty,c.nsty,newloc));
        ret.Finish_Lines2();                              # generates the new words
        for ii in range(len(self.lns)):
            for jj in range(len(self.lns[ii].ws)):
                # ret.lns[ii].ws[jj].orig_pts_ut = copy.deepcopy(self.lns[ii].ws[jj].orig_pts_ut)
                # ret.lns[ii].ws[jj].orig_pts_t  = copy.deepcopy(self.lns[ii].ws[jj].orig_pts_t )
                # ret.lns[ii].ws[jj].orig_bb     = copy.deepcopy(self.lns[ii].ws[jj].orig_bb    )
                ret.lns[ii].ws[jj].parsed_bb   = copy.deepcopy(self.lns[ii].ws[jj].parsed_bb    )
            for jj in range(len(self.lns[ii].cs)):
                ret.lns[ii].cs[jj].parsed_pts_ut = copy.deepcopy(self.lns[ii].cs[jj].parsed_pts_ut)
                ret.lns[ii].cs[jj].parsed_pts_t  = copy.deepcopy(self.lns[ii].cs[jj].parsed_pts_t )
                    
        ret.isinkscape = self.isinkscape;
        ret.dxs = copy.copy(self.dxs);
        ret.dys = copy.copy(self.dys);
        ret.flatdelta = self.flatdelta;
        return ret

            
    def txt(self):
        return [v.txt() for v in self.lns]
    
    # Every text element in an SVG can be thought of as a group of lines.
    # A line is a collection of text that gets its position from a single source element.
    # This position may be directly set, continued from a previous line, or inherited from a previous line
    def Parse_Lines2(self,el,lns=None,debug=False):
        # First we get the tree structure of the text and do all our gets
        ds,pts,cd,pd = dh.descendants2(el,True); Nd = len(ds)
        ks = list(el);
        text = [d.text for d in ds]
        ptail = [[tel.tail for tel in pt] for pt in pts]   # preceding tails
        if len(ptail)>0 and len(ptail[-1])>0:             ptail[-1][-1] = None; # do not count el's tail
        
        # Next we find the top-level sodipodi:role lines
        xs = [LineList.GetXY(d,'x') for d in ds]
        ys = [LineList.GetXY(d,'y') for d in ds]
        nspr = [d.get('sodipodi:role') for d in ds]; nspr[0]=None
        sprl   = [nspr[ii]=='line' and len(xs[ii])==1 and len(ys[ii])==1 for ii in range(len(ds))]
        
        # Find effective sprls (ones that are not disabled)
        esprl = copy.copy(sprl)         
        for ii in range(len(ds)):
            # Any non-sprl ancestor disables spr:l on me
            cel = ds[ii];                                   
            while esprl[ii] and cel!=el:
                esprl[ii] = esprl[ii] and sprl[ds.index(cel)]           
                cel = pd[cel];                       
            
            # If I don't have text and any descendants have position, disables spr:l
            if esprl[ii] and (text[ii]=='' or text[ii] is None):
                # dh.debug(ds[ii].get_id())
                dstop = [jj for jj in range(len(pts)) if ds[ii] in pts[jj]][0]; # should exist
                for di in range(ii+1,dstop):
                    if xs[di][0] is not None or ys[di][0] is not None:
                        if text[di] is not None and text[di]!='':
                            # dh.debug(text[di])
                            esprl[ii] = False   
                            
            # Only top-level tspans are sprl
            esprl[ii] = esprl[ii] and ds[ii] in ks
        
        # Figure out which effective sprls are top-level
        types   = [None]*len(ds);
        for ii in range(len(ds)):
            if esprl[ii]:
                if len(ptail[ii])>0 and ptail[ii][-1]is not None:
                    types[ii] = 'precededsprl'
                elif ds[ii]==ks[0] and text[0] is not None:
                    types[ii] = 'precededsprl'
                else:
                    types[ii] = 'tlvlsprl';  
            else:        
                types[ii] = 'normal'

                
        # Position has a property of bidirectional inheritance. A tspan can inherit
        # position from its parent or its descendant unless there is text in between.   
        # Down-inheritance requires that text be present
        # Aborts if a sprl is encountered
        def inherits_from(iin):
            jmax = iin
            while jmax<Nd-1 and text[jmax] in ['',None] and pd[ds[jmax+1]]==ds[jmax] and not(esprl[jmax+1]):
                jmax+=1
            if jmax<Nd-1 and text[jmax] in ['',None]:
                jmax=iin
                
            jmin = iin
            while jmin>0 and text[jmin-1] in ['',None] and ds[jmin-1]==pd[ds[jmin]] and not(esprl[jmin-1]):
                jmin-=1
            return jmin,jmax   # includes endpoints
        def inheritNone(iin,xy):
            if xy[iin][0] is None:
                imin,imax = inherits_from(iin)
                vld = [ii for ii in range(imin,imax+1) if xy[ii][0] is not None];
                if len(vld)>0:
                    if any([ii<=iin for ii in vld]):
                        vld = [ii for ii in vld if ii<=iin]; # inherit up if possible
                    dist = [abs(ii-iin) for ii in vld]
                    ic   = [vld[ii] for ii in range(len(vld)) if dist[ii]==min(dist)][0];
                    return xy[ic], ds[ic]
            return xy[iin], ds[iin]
        
        # For positions that are None, inherit from ancestor/descendants if possible
        ixs=copy.copy(xs); iys=copy.copy(ys);
        xsrcs=[None]*len(ds); ysrcs=[None]*len(ds);
        for ii in range(0,len(ds)):
            xv = xs[ii]; xsrc = ds[ii];
            yv = ys[ii]; ysrc = ds[ii];
            if xv[0] is None:
                xv,xsrc = inheritNone(ii,xs)
            if yv[0] is None:
                yv,ysrc = inheritNone(ii,ys)
            ixs[ii] = xv;
            iys[ii] = yv;
            xsrcs[ii] = xsrc;
            ysrcs[ii] = ysrc;
            
        if ixs[0][0] is None: ixs[0]=[0]  # at least the parent needs a position
        if iys[0][0] is None: iys[0]=[0]
        
        
        # Finally, walk the text tree generating lines
        lns=[]; sprl_inherits = None; #lastsprlel = None
        
        for di in range(len(ds)+1):
            tstrt = (di==0)
            tstop = 2-(di==len(ds))
            for tt in range(tstrt,tstop):
                if tt==0:
                    txts = ptail[di]
                    tels = pts[di]
                else:
                    txts = [text[di]]
                    tels = [ds[di]]
                    
                for ii in range(len(tels)):
                    tel = tels[ii]; txt = txts[ii]
                    
                    newsprl = tt==1 and types[di]=='tlvlsprl'
                    if (txt is not None and len(txt)>0) or newsprl:
                        sel = tel;
                        if tt==0: sel = pd[tel]; # tails get their sty from the parent of the element the tail belongs to
                        sty = dh.selected_style_local(sel);
                        ct = sel.composed_transform();
                        fs,sf,ct,ang = dh.Get_Composed_Width(sel,'font-size',4,styin=sty,ctin=ct); #dh.debug(el.get_id()); dh.debug(el.composed_transform())
                        # dh.idebug(fs)
                        if newsprl:
                            lh = dh.Get_Composed_LineHeight(sel,styin=sty,ctin=ct);
                        nsty=Character_Table.normalize_style(sty);
                        
                        # Make a new line if we're sprl or if we have a new x or y
                        if len(lns)==0 or (tt==1 and (newsprl or\
                                           (types[di]=='normal' and \
                                           (ixs[di][0] is not None or iys[di][0] is not None)))):
                            edi = di;
                            if tt==0: edi = ds.index(sel)
                            xv = ixs[edi];      xsrc = xsrcs[edi]; 
                            yv = iys[edi];      ysrc = ysrcs[edi];
                            if newsprl:
                                if len(lns)==0:
                                    xv = [ixs[0][0]];                xsrc = xsrcs[0];
                                    yv = [iys[0][0]];                ysrc = ysrcs[0];
                                else:
                                    xv = [sprl_inherits.x[0]];        xsrc = sprl_inherits.xsrc;
                                    yv = [sprl_inherits.y[0]+lh/sf];  ysrc = sprl_inherits.ysrc;
                                issprl  = True;  
                                continuex = False; continuey = False;
                            else:
                                continuex = False; issprl = False;
                                if xv[0] is None:      
                                    if len(lns)>0: xv = copy.copy(lns[-1].x); xsrc = lns[-1].xsrc; 
                                    else:          xv = copy.copy(ixs[0]);        xsrc = xsrcs[0];
                                    continuex = True; #issprl = True;
                                continuey = False; 
                                if yv[0] is None:        
                                    if len(lns)>0: yv = copy.copy(lns[-1].y); ysrc = lns[-1].ysrc; 
                                    else:          yv = copy.copy(iys[0]);        ysrc = ysrcs[0];
                                    continuey = True; 
                            
                            tlvlno = None
                            if ds[di] in ks:  tlvlno = ks.index(ds[di])
                            elif edi==0:      tlvlno = 0;
                                
                            anch = sty.get('text-anchor') 
                            if len(lns)>0 and nspr[edi]!='line':
                                if lns[-1].anchor is not None:
                                    anch = lns[-1].anchor    # non-spr lines inherit the previous line's anchor
                            if anch is None: anch = 'start';
                            lns.append(tline(xv,yv,issprl,nspr[edi],anch,ct,ang,ds[edi],\
                                              xsrc,ysrc,tlvlno,sty,continuex,continuey))
                            if newsprl or len(lns)==1:
                                sprl_inherits = lns[-1];
                                
                        if txt is not None:
                            for jj in range(len(txt)):
                                c = txt[jj]
                                prop = self.ctable.get_prop(c,nsty)*fs;
                                ttv = 'text';
                                if tt==0: ttv='tail'
                                lns[-1].addc(tchar(c,fs,sf,prop,sty,nsty,cloc(tel,ttv,jj)));
            
        return lns
        
    # Seperate a text element into a group of lines
    def Parse_Lines(self,el,lns=None,debug=False):
        sty = dh.selected_style_local(el);
        ct = el.composed_transform();
        fs,sf,ct,ang = dh.Get_Composed_Width(el,'font-size',4,styin=sty,ctin=ct); #dh.debug(el.get_id()); dh.debug(el.composed_transform())
        lh = dh.Get_Composed_LineHeight(el,styin=sty,ctin=ct);
        nsty=Character_Table.normalize_style(sty);
        tv = el.text;
        
        xv = LineList.GetXY(el,'x'); xsrc = el;
        yv = LineList.GetXY(el,'y'); ysrc = el;

        # Notes on sodipodi:role line
        # If a top-level Tspan has sodipodi:role set to line, its position is inherited based on the previous line.
        # The x value is taken from the previous line's x value.
        # The y value is taken by adding the line height to the previous y value.
        # However, inheritance is disabled by the presence of multiple x values or multiple y values.
        # (Multiple dx or dy values does not disable this inheritance.)
        # If sodipodi:role is not line, its anchoring/alignment will be inherited from the previous line.
        
        # Detect if inheriting position
        nspr = el.get('sodipodi:role');
        
        toplevelTspan = isinstance(el,Tspan) and isinstance(el.getparent(),TextElement);
        myi = el.getparent().getchildren().index(el);
        
        if toplevelTspan:                tlvlno=myi;
        elif isinstance(el,TextElement): tlvlno=0;
        else:                            tlvlno=None;
        
        sprl = (nspr=='line');
        multiplepos = len(xv)>1 or len(yv)>1;           # multiple x or y values disable sodipodi:role line
        inheritx = (sprl and not(multiplepos)) or (xv[0] is None)
        inherity = (sprl and not(multiplepos)) or (yv[0] is None)
        
        # Determine if new line
        newline = False;            
        if isinstance(el,TextElement):
            newline = True
        elif toplevelTspan: # top level Tspans
            if (sprl      and (not(inheritx) or not(inherity) or not(myi==0)))\
            or (not(sprl) and (not(inheritx) or not(inherity))):   
                # if not inheriting, continue previous line
                newline = True
        elif isinstance(el,Tspan):                      # nested Tspans: become a new line with an explicit x or y
            if el.get('x') is not None:  
                newline = True; inheritx=False;
            if el.get('y') is not None:  
                newline = True; inherity=False;
        
        # dh.debug(el.get_id() + str(inheritx))
        # dh.debug(el.get_id())
        # dh.debug(len(el.text))
        # dh.debug(newline)
        # dh.debug(inheritx)
        # dh.debug(inherity)
        # dh.debug((nspr=='line' and not(multiplepos)) or (yv[0] is None))
        # dh.debug(' ')
#        dh.debug(toplevelTspan)
        
        # debug = True
        if debug:
            dh.debug(el.get_id())
            dh.debug(tv)
            dh.debug(newline)
            dh.debug(fs)
            dh.debug(xv)
            # dh.debug(inheritx)
        
        if newline:
            continuex = False;
            if lns is None:  
                lns=[];
            else:
                if inheritx:                
                    if len(lns)==0 or len(lns[-1].x)==0: return None
                    else:
                        if toplevelTspan and myi>0: # inheriting from previous top-level line
                            lastln = [ln for ln in lns if ln.tlvlno==tlvlno-1][-1];
                            xv   = [lastln.x[0]]; 
                            xsrc = lastln.xsrc;
                            if lastln.x[0] is None:
                                lli=[ii for ii in range(len(lns)) if lns[ii].x[0] is not None]
                                if len(lli)>0:
                                    xv = [lns[max(lli)].x[0]]
                                    xsrc = lns[max(lli)].xsrc
                        else:                       # continuing previous line
                            xv   = [None]; 
                            xsrc = lns[-1].xsrc;
                            continuex = True;
#                        ct   = lns[-1].transform; # I don't think these do anything (2021.10.18)
#                        ang  = lns[-1].angle;
                if inherity:               
                    if len(lns)==0 or len(lns[-1].y)==0: return None
                    else:
                        if toplevelTspan and myi>0: # inheriting from previous top-level line
                            lastln = [ln for ln in lns if ln.tlvlno==tlvlno-1][-1];
                            offs = lh/sf;
                            if lns[-1].y[0] is not None:
                                if lastln.y[0] is None:
                                    lli=[ii for ii in range(len(lns)) if lns[ii].y[0] is not None]
                                    if len(lli)>0: lyv = lns[max(lli)].y[0]
                                    else: lyv=0
                                else:
                                    lyv = lastln.y[0]
                                yv   = [lyv+offs];
                            else: yv = [None];
                            ysrc = lastln.ysrc;
                        else:                       # continuing previous line
                            yv   = [lns[-1].y[0]];
                            ysrc = lns[-1].ysrc;
                            
            anch = sty.get('text-anchor') 
            if len(lns)!=0 and nspr!='line':
                if lns[-1].anchor is not None:
                    anch = lns[-1].anchor    # non-spr lines inherit the previous line's anchor
            lns.append(tline(xv,yv,inheritx,nspr,anch,ct,ang,el,xsrc,ysrc,tlvlno,sty,continuex))
        
        # First line anchor should be the Tspan style if there are no characters in the text
        if toplevelTspan and myi==0:
            if len(lns)==1 and len(lns[0].cs)==0:
                lns[0].anchor = sty.get('text-anchor');
        
        ctable = self.ctable  
        if tv is not None and tv!='' and len(tv)>0:
            for ii in range(len(tv)):
                # if fs is None: return None # bail if there is text without font
                prop = ctable.get_prop(tv[ii],nsty)*fs;
                lns[-1].addc(tchar(tv[ii],fs,sf,prop,sty,nsty,cloc(el,'text',ii)));
        
        ks = el.getchildren();
        # if debug:
        #     dh.debug(ks)
        for k in ks:
            lns = self.Parse_Lines(k,lns,debug=debug);
            tv = k.tail;
            if tv is not None and tv!='':
                for ii in range(len(tv)):
                    # if fs is None: return None # bail if there is text without font
                    prop = ctable.get_prop(tv[ii],nsty)*fs;
                    lns[-1].addc(tchar(tv[ii],fs,sf,prop,sty,nsty,cloc(k,'tail',ii)));
            
        return lns
    
    def Finish_Lines(self):
        if self.lns is not None:
            self.Get_Delta(self.lns,self.textel,'dx');
            self.Get_Delta(self.lns,self.textel,'dy');
            for ii in range(len(self.lns)):
                ln = self.lns[ii];
                if ln.x[0] is None: # no x ever assigned
                    if ln.continuex and ii>0 and len(self.lns[ii-1].ws)>0:
                        self.lns[ii-1].ws[-1].calcprops();
                        ln.x[0] = self.lns[ii-1].ws[-1].pts_ut[3].x
                    else:
                        ln.x[0] = 0;
                if ln.y[0] is None: # no y ever assigned
                    ln.y[0] = 0;
                ln.parse_words()
            for ln in reversed(self.lns): 
                if len(ln.cs)==0:
                    self.lns.remove(ln); # prune empty lines
            for ln in self.lns:
                ln.ll = self;
            
            # Assign nextw for single-word lines sharing a y (Illustrator SVGs usually have one Tspan per character)
            ys = [ln.y[0] for ln in self.lns if ln.y is not None and len(ln.y)>0]
            for uy in list(set(ys)):
                samey = [self.lns[ii] for ii in range(len(self.lns)) if ys[ii]==uy];
                xs = [ln.x for ln in samey]
                slns = [x for _, x in sorted(zip(xs, samey), key=lambda pair: pair[0])] # words sorted in ascending x
                for ii in range(len(slns)-1):
                    if len(slns[ii].ws)==1 and len(slns[ii+1].ws)==1:
                        slns[ii].ws[-1].nextw = slns[ii+1].ws[0] 
                        
                        
    def Finish_Lines2(self):
        if self.lns is not None:
            self.Get_Delta(self.lns,self.textel,'dx');
            self.Get_Delta(self.lns,self.textel,'dy');
            for ii in range(len(self.lns)):
                ln = self.lns[ii];
                
                if ln.continuex and ii>0 and len(self.lns[ii-1].ws)>0:
                    self.lns[ii-1].ws[-1].calcprops();
                    ln.x = [self.lns[ii-1].ws[-1].pts_ut[3].x]
                if ln.continuey and ii>0 and len(self.lns[ii-1].ws)>0:
                    self.lns[ii-1].ws[-1].calcprops();
                    ln.y = [self.lns[ii-1].ws[-1].pts_ut[3].y]

                ln.parse_words()
            
            for ln in reversed(self.lns): 
                if len(ln.cs)==0:
                    self.lns.remove(ln); # prune empty lines
            for ln in self.lns:
                ln.ll = self;
            
            # Assign nextw for single-word lines sharing a y (Illustrator SVGs usually have one Tspan per character)
            ys = [ln.y[0] for ln in self.lns if ln.y is not None and len(ln.y)>0]
            for uy in list(set(ys)):
                samey = [self.lns[ii] for ii in range(len(self.lns)) if ys[ii]==uy];
                xs = [ln.x for ln in samey]
                slns = [x for _, x in sorted(zip(xs, samey), key=lambda pair: pair[0])] # words sorted in ascending x
                for ii in range(len(slns)-1):
                    if len(slns[ii].ws)==1 and len(slns[ii+1].ws)==1:
                        slns[ii].ws[-1].nextw = slns[ii+1].ws[0]
    
    @staticmethod
    def GetXY(el,xy):
        val = el.get(xy)
        if val is None:   
            val = [None]; # None forces inheritance
        else:             
            tmp = [];
            for x in val.split():
                if x.lower()=='none':  tmp.append(None);
                else:                  tmp.append(float(x));
            val = tmp;
        return val
    
    # For debugging only: make a rectange at all of the line's words' nominal bboxes
    def Position_Check(self):
        if self.lns is not None and len(self.lns)>0:
            if self.lns[0].xsrc is not None:
                svg = dh.get_parent_svg(self.lns[0].xsrc)
                xs = []; ys = []; x2s = []; y2s = [];
                for ln in self.lns:          
                    for w in ln.ws:
                        ap  = w.pts_t[0];
                        ap2 = w.pts_t[2];  
                        xs.append(ap.x); #dh.debug(ap.x/self.svg.scale)
                        ys.append(ap.y);
                        x2s.append(ap2.x);
                        y2s.append(ap2.y);
                # for ln in self.lns:          
                #     for w in ln.ws:
                #         for c in w.cs:
                #             ap  = c.parsed_pts_t[0];
                #             ap2 = c.parsed_pts_t[2];
                #             xs.append(ap.x); #dh.debug(ap.x/self.svg.scale)
                #             ys.append(ap.y);
                #             x2s.append(ap2.x);
                #             y2s.append(ap2.y);
                    
                for ii in range(len(xs)):
                    r = inkex.Rectangle();
                    r.set('x',min(xs[ii],x2s[ii]))
                    r.set('y',min(ys[ii],y2s[ii]))
                    r.set('height',abs(ys[ii]-y2s[ii]))
                    r.set('width', abs(xs[ii]-x2s[ii]))
                    # r.set('style','fill-opacity:0.5')
                    r.set('style','fill:#007575;fill-opacity:0.4675'); # mimic selection boxes
                    svg.append(r)
    
    
    # Traverse the element tree to find dx/dy values and apply them to the chars
    def Get_Delta(self,lns,el,xy,dxin=None,cntin=None,dxysrc=None):
        if dxin is None:
            dxy = LineList.GetXY(el,xy); dxysrc=el;
            cnt = 0;
            toplevel = True;
        else:
            dxy = dxin;
            cnt = cntin;
            toplevel = False;
        if len(dxy)>0 and dxy[0] is not None:
            allcs = [c for ln in lns for c in ln.cs];
            # get text, then each child, then each child's tail
            if el.text is not None:
                for ii in range(len(el.text)):
                    thec = [c for c in allcs if c.loc.el==el and c.loc.tt=='text' and c.loc.ind==ii];
                    if cnt < len(dxy):
                        # if dxy[cnt]==30: dh.debug(dxysrc.get_id())
                        if xy=='dx': thec[0].dx = dxy[cnt]; 
                        if xy=='dy': thec[0].dy = dxy[cnt]; 
                        cnt+=1;
            for k in el.getchildren():
                cnt = self.Get_Delta(lns,k,xy,dxy,cnt,dxysrc);
                if k.get('sodipodi:role')=='line' and isinstance(k,Tspan) and isinstance(k.getparent(),TextElement):
                    cnt += 1; # top-level Tspans have an implicit CR
                if k.tail is not None:
                    for ii in range(len(k.tail)):
                        thec = [c for c in allcs if c.loc.el==k and c.loc.tt=='tail' and c.loc.ind==ii];
                        if cnt < len(dxy):
                            # if dxy[cnt]==30: dh.debug(dxysrc.get_id())
                            # dh.idebug([[c.loc.el.get_id(),c.loc.tt,c.loc.ind] for c in allcs])
                            # quit()
                            if xy=='dx': thec[0].dx = dxy[cnt]; 
                            if xy=='dy': thec[0].dy = dxy[cnt];
                            cnt+=1;    
        if toplevel:
            for k in el.getchildren():
                self.Get_Delta(lns,k,xy);   
        return cnt
    
    # Traverse the tree to find where deltas need to be located relative to the top-level text
    def Get_DeltaNum(self,lns,el,topcnt=0):
        allcs = [c for ln in lns for c in ln.cs];
        # get text, then each child, then each child's tail
        if el.text is not None:
            for ii in range(len(el.text)):
                thec = [c for c in allcs if c.loc.el==el and c.loc.tt=='text' and c.loc.ind==ii];
                if len(thec)==0:
                    dh.debug('Missing '+el.text[ii])
                    tll = LineList(self.textel,self.ctable);
                    dh.debug(self.txt())
                    dh.debug(tll.txt())
                thec[0].deltanum = topcnt; 
                topcnt+=1;
        for k in el.getchildren():
            topcnt = self.Get_DeltaNum(lns,k,topcnt=topcnt);
            if k.get('sodipodi:role')=='line' and isinstance(k,Tspan) and isinstance(k.getparent(),TextElement):
                topcnt+=1# top-level Tspans have an implicit CR
            if k.tail is not None:
                for ii in range(len(k.tail)):
                    thec = [c for c in allcs if c.loc.el==k and c.loc.tt=='tail' and c.loc.ind==ii];
                    if len(thec)==0:
                        dh.debug('Missing '+k.tail[ii])
                        tll = LineList(self.textel,self.ctable);
                        dh.debug(self.txt())
                        dh.debug(tll.txt())
                    thec[0].deltanum = topcnt;
                    topcnt+=1
        return topcnt
    
    # After dx/dy has changed, call this to write them to the text element
    # For simplicity, this is best done at the LineList level all at once
    def Update_Delta(self,forceupdate=False):
        dxs = [c.dx for ln in self.lns for c in ln.cs];
        dys = [c.dy for ln in self.lns for c in ln.cs];
        
        anynewx = self.dxs!=dxs and any([dxv!=0 for dxv in self.dxs+dxs]); # only if new is not old and at least one is non-zero
        anynewy = self.dys!=dys and any([dyv!=0 for dyv in self.dys+dys]);
           
        if anynewx or anynewy or forceupdate:
            self.Get_DeltaNum(self.lns, self.textel)
            dx=[]; dy=[]; 
            for ln in self.lns:
                for c in ln.cs:
                    if c.deltanum is not None:
                        dx = extendind(dx, c.deltanum, c.dx,0)
                        dy = extendind(dy, c.deltanum, c.dy,0)
            
            if not(self.flatdelta): # flatten onto textel
                for d in dh.descendants2(self.textel): d.set('dx',None);
                for d in dh.descendants2(self.textel): d.set('dy',None)
                self.flatdy = True; # only need to do this once
            
            dxset = None; dyset = None;
            if any([dxv!=0 for dxv in dx]):
                dxset = ' '.join([str(v) for v in dx]);
            if any([dyv!=0 for dyv in dy]):
                dyset = ' '.join([str(v) for v in dy]);
            self.textel.set('dx',dxset);
            self.textel.set('dy',dyset);
        self.dxs = dxs;
        self.dys = dys;

    # Text is hard to edit unless xml:space is set to preserve and sodipodi:role is set to line
    # Should usually be called last
    def Make_Editable(self):
        el = self.textel
        el.set('xml:space','preserve')   
        # dh.debug(self.lns[0].tlvlno)
        # if len(self.lns)==1 and self.lns[0].tlvlno==0: # only child, no nesting, not a sub/superscript
        if len(self.lns)==1 and self.lns[0].tlvlno is not None and not(self.lns[0].sprl): # only one line that is a top-level tspan
            ln = self.lns[0];
            olddx = self.dxs;
            olddy = self.dys;
            
            # ln.el.set('sodipodi:role','line')
            # self.lns = self.Parse_Lines(el); # unnecessary if called last
            # self.lns[0].change_pos(oldx,oldy); 
            
            tx = ln.el.get('x'); ty=ln.el.get('y');
            myp = ln.el.getparent();
            if tx is not None: myp.set('x',tx)      # enabling sodipodi causes it to move to the parent's x and y
            if ty is not None: myp.set('y',ty)      # enabling sodipodi causes it to move to the parent's x and y
            ln.el.set('sodipodi:role','line');      # reenable sodipodi so we can insert returns
            
            for ii in range(len(self.lns[0].cs)):
                self.lns[0].cs[ii].dx = olddx[ii]
                self.lns[0].cs[ii].dy = olddy[ii];
            self.Update_Delta(forceupdate=True)
    
            
    def Split_Off_Words(self,ws):
        # newtxt = dh.duplicate2(ws[0].ln.ll.textel);
        # nll = LineList(newtxt,self.ctable);
        nll = self.duplicate();
        newtxt = nll.textel; 
        
        il = self.lns.index(ws[0].ln);              # words' line index
        wiis =  [w.ln.ws.index(w) for w in ws]  # indexs of words in line
        
        # Record position and d
        dxl = [c.dx for w in ws for c in w.cs];
        dyl = [c.dy for w in ws for c in w.cs];
        
        global debug
        debug = True;
        
        for w in reversed(ws):
            w.delw();
        debug = False;
        
        for il2 in reversed(range(len(nll.lns))):
            if il2!=il:
                nll.lns[il2].dell();
            else:
                nln = nll.lns[il2];
                for jj in reversed(range(len(nln.ws))):
                    if not(jj in wiis):
                        nln.ws[jj].delw();

        cnt=0;
        for l2 in nll.lns:
            for c in l2.cs:
                c.dx = dxl[cnt];  c.dy = dyl[cnt]; cnt+=1
        nll.Update_Delta();
        
        return newtxt,nll
    
    # Deletes empty elements from the doc. Generally this is done last
    def Delete_Empty(self):
        dxl = [c.dx for ln in self.lns for c in ln.cs];
        dyl = [c.dy for ln in self.lns for c in ln.cs];
        deleteempty(self.textel);
        cnt=0;
        for ln in self.lns:
            for c in ln.cs:
                c.dx = dxl[cnt];  c.dy = dyl[cnt]; cnt+=1
        self.Update_Delta(forceupdate=True); # force an update, could have deleted sodipodi lines

    
# A single line, which represents a list of characters. Typically a top-level Tspan or TextElement.
# This is further subdivided into a list of words
class tline:
    def __init__(self, x, y, sprl, nspr, anch, xform,ang,el,xsrc,ysrc,tlvlno,sty,continuex=False,continuey=False):
        self.x = x; 
        self.y = y;
        self.sprl = sprl;        # is this line truly a sodipodi:role line
        self.nominalspr = nspr;  # nominal value of spr (sprl may actually be disabled)
        self.anchor = anch
        self.cs = [];
        self.ws = [];
        if xform is None: self.transform = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]);
        else:             self.transform = xform;
        if ang is None:   self.angle = 0;
        else:             self.angle = ang; 
        self.xsrc = xsrc; # element from which we derive our x value
        self.ysrc = ysrc; # element from which we derive our x value
        self.tlvlno = tlvlno;        # which number Tspan I am if I'm top-level (otherwise None)
        self.style = sty;
        self.el = el;
        # self.dx = dx;
        # self.dy = dy;
        
        self.continuex = continuex;  # when enabled, x of a line is the endpoint of the previous line
        self.continuey = continuey;  # when enabled, y of a line is the endpoint of the previous line
        
        # self.ll = None;   # line list we belong to (add later)
    def addc(self,c):
        self.cs.append(c)
        c.ln = self;
    def insertc(self,c,ec): # insert below
        self.cs = self.cs[0:ec]+[c]+self.cs[ec:]
        c.ln = self;
    def addw(self,w): # Add a complete word and calculate its properties
        self.ws.append(w)
        w.calcprops();
        # if len(w.cs)==0:
        #     dh.debug(self.xsrc.get_id())
    def parse_words(self):
        # Parsing a line into words is the final step that should be called once
        # the line parser has gotten all the characters
        
        w=None; self.ws=[];
        for ii in range(len(self.cs)):
            if ii==0:
                w = tword(ii,self.x[0],self.y[0],self);         # open new word
            elif ii<len(self.x) and not(self.x[ii] is None): # None means keep the same word
                self.addw(w)                  # close previous word
                w = tword(ii,self.x[ii],self.y[0],self);   # open new word
            else:
                w.addc(ii);                  # add to existing word
        if w is not None:
            self.addw(w)
            
        if len(self.x)>1:
            xn = [self.x[ii] for ii in range(len(self.x)) if self.x[ii] is not None]; # non-None
            sws = [x for _, x in sorted(zip(xn, self.ws), key=lambda pair: pair[0])] # words sorted in ascending x
            for ii in range(len(sws)-1):
                sws[ii].nextw = sws[ii+1]
        # dh.debug([self.x,len(self.ws)])
            
    def dell(self): # deletes the whole line
        for c in reversed(self.cs):
            c.delc();
        if self.ll is not None:
            self.ll.lns.remove(self)
        self.ll = None;
    def txt(self):   
        return ''.join([c.c for c in self.cs])
    
    # Change the alignment of a line without affecting character position
    def change_alignment(self,newanch):
        if newanch!=self.anchor:
            sibsrc = [ln for ln in self.ll.lns if ln.xsrc==self.xsrc or ln.ysrc==self.ysrc];
            for ln in reversed(sibsrc):
                ln.disablesodipodi()     # Disable sprl for all lines sharing our src, including us
                                         # Note that it's impossible to change one line without affecting the others
                
            # if len(self.cs)>0 and self.cs[-1].c==' ':
            #     self.cs[-1].delc(); # can delete final space since it's never rendered
            # hasunrenderedspace = (len(self.cs)>0 and self.cs[-1].c==' ')
                
            for w in self.ws:
                minx = min([w.pts_ut[ii][0] for ii in range(4)]);
                maxx = max([w.pts_ut[ii][0] for ii in range(4)]);
                
                if w.unrenderedspace and self.cs[-1] in w.cs:
                    maxx -= w.cs[-1].cw/w.cs[-1].sf;
                
                dxl = [c.dx for c in self.cs];
                if len(dxl)==0: dxl=[0];
                if newanch=='middle':
                    newx = (minx+maxx)/2-dxl[0]/2;
                elif newanch=='end':
                    newx = maxx;
                else:
                    newx = minx-dxl[0];
                
                if len(w.cs)>0:
                    newxv = self.x; newxv[self.cs.index(w.cs[0])] = newx;
                    self.change_pos(newxv)
                    dh.Set_Style_Comp(w.cs[0].loc.el,'text-anchor',newanch)
                    alignd = {'start': 'start', 'middle': 'center', 'end': 'end'}
                    dh.Set_Style_Comp(w.cs[0].loc.el,'text-align',alignd[newanch]);
                    
                self.anchor = newanch;
                w.x = newx; w.calcprops();
    
    @staticmethod            
    def writev(v):
        if v==[]:
            return None
        else:
            return ' '.join([str(w) for w in v])
    
    # Disable sodipodi:role = line
    def disablesodipodi(self):
        if self.nominalspr=='line':
            self.el.set('sodipodi:role',None)
            self.nominalspr = None
            self.xsrc = self.el;                    # change position source
            self.ysrc = self.el;
            self.el.set('x',tline.writev(self.x))   # fuse position to new source
            self.el.set('y',tline.writev(self.y))
            self.sprl = False;
    
    # Update the line's position in the document, accounting for inheritance
    # Never change x/y directly, always call this function
    def change_pos(self,newx=None,newy=None,reparse=False):
        if newx is not None:
            sibsrc = [ln for ln in self.ll.lns if ln.xsrc==self.xsrc]
            if len(sibsrc)>1:
                for ln in reversed(sibsrc):
                    ln.disablesodipodi()             # Disable sprl when lines share an xsrc
                    
            if all([v is None for v in newx[1:]]) and len(newx)>0:
                newx = [newx[0]]
            oldx = self.x
            self.x = newx;
            self.xsrc.set('x',tline.writev(newx))
            
            if len(oldx)>1 and len(self.x)==1 and self.nominalspr=='line': # would re-enable sprl
                self.disablesodipodi()
                
        if newy is not None:
            sibsrc = [ln for ln in self.ll.lns if ln.ysrc==self.ysrc]
            if len(sibsrc)>1:
                for ln in reversed(sibsrc):
                    ln.disablesodipodi()             # Disable sprl when lines share a ysrc
            
            if all([v is None for v in newy[1:]]) and len(newy)>0:
                newy = [newy[0]]
            oldy = self.y
            self.y = newy;
            self.ysrc.set('y',tline.writev(newy))
            
            if len(oldy)>1 and len(self.y)==1 and self.nominalspr=='line': # would re-enable sprl
                self.disablesodipodi()
                
        if reparse:
            self.parse_words(); # usually don't want to do this since it generates new words
                
    
# A word (a group of characters with the same assigned anchor)
class tword: 
    def __init__(self,ii,x,y,ln):
        c = ln.cs[ii];
        self.cs  = [c];
        self.iis = [ii]; # character index in word
        self.x = x;
        self.y = y;
        self.sf= c.sf; # all letters have the same scale
        self.ln = ln;
        self.transform = ln.transform
        c.w = self;
        self.unrenderedspace = False;
        self.nextw = None;
        # self.orig_pts_t = None; self.orig_pts_ut = None; self.orig_bb = None; # for merging later
    def addc(self,ii):
        c = self.ln.cs[ii];
        self.cs.append(c);
        self.iis.append(ii);
        c.w = self;
    
    # Deletes me from everywhere
    def delw(self):
#        global debug;
#        if debug: dh.debug(self.ln.x)
        for c in reversed(self.cs):
            c.delc();
        if self in self.ln.ws:
            self.ln.ws.remove(self)
#        if debug: dh.debug(self.ln.x)
            
    # Gets all text
    def txt(self):   
        return ''.join([c.c for c in self.cs])
            
    # Add a new character to the end of the word
    def appendc(self,ncv,ncw,ndx,ndy):
        # Add to document
        lc = self.cs[-1]; # last character
        myi = lc.loc.ind+1; # insert after last character
        if lc.loc.tt=='text':
            lc.loc.el.text = lc.loc.el.text[0:myi]+ncv+lc.loc.el.text[myi:]
        else:
            lc.loc.el.tail = lc.loc.el.tail[0:myi]+ncv+lc.loc.el.tail[myi:]
        
        # Make new character as a copy of the last one of the current word
        c = copy.copy(lc)
        c.c  = ncv
        c.cw = ncw
        c.dx = ndx; c.dy = ndy;
        c.pending_style = None;
        c.loc = cloc(c.loc.el,c.loc.tt,c.loc.ind+1) # updated location
        
        # Add to line
        myi = self.ln.cs.index(lc)+1 # insert after last character
        if len(self.ln.x)>0:
            newx = self.ln.x[0:myi]+[None]+self.ln.x[myi:]
            newx = newx[0:len(self.ln.cs)+1]
            self.ln.change_pos(newx)
            
        self.ln.insertc(c,myi)
        for ii in range(myi+1,len(self.ln.cs)):        # need to increment index of subsequent objects with the same parent
            ca = self.ln.cs[ii];
            if ca.loc.tt==c.loc.tt and ca.loc.el==c.loc.el:
                ca.loc.ind += 1
            if ca.w is not None:
                i2 = ca.w.cs.index(ca)
                ca.w.iis[i2] += 1
        # Add to word, recalculate properties
        self.addc(myi)
        # self.calcprops()
        
        # Adding a character causes the word to move if it's center- or right-justified
        # Need to fix this by adjusting position
        if self.ln.anchor=='middle':
            deltax = -self.ln.cs[myi].cw/self.sf / 2;
        elif self.ln.anchor=='end':
            deltax = -self.ln.cs[myi].cw/self.sf;
        else:
            deltax = 0;
        if deltax!=0:
            newx = self.ln.x; newx[self.ln.cs.index(self.cs[0])] -= deltax
            self.ln.change_pos(newx)
            self.x -= deltax
        self.ln.ll.Update_Delta();
        self.calcprops()
        
    # Add a new word (possibly from another line) into the current one
    # Equivalent to typing it in
    def appendw(self,nw,type):
        if len(nw.cs)>0:
            # Store new word data prior to merging
            # if self.orig_pts_t is None:
            #     self.orig_pts_t  = [self.pts_t]
            #     self.orig_pts_ut = [self.pts_ut]
            #     self.orig_bb     = self.bb
            # if nw.orig_pts_t is None:
            #     nw.orig_pts_t  = [nw.pts_t]
            #     nw.orig_pts_ut = [nw.pts_ut]
            #     nw.orig_bb     = nw.bb
                # nw_pput = [c.parsed_pts_ut for c in nw.cs]
                # nw_ppt  = [c.parsed_pts_t for c in nw.cs]
                
    
            # If the last char is a nested Tspan, we will need to delete it and re-add it
            # to prevent the new chars from inheriting its properties
            if len(self.cs)>1:
                ii = len(self.cs)-1;
                isnested = (self.cs[ii].loc.el != self.cs[0].loc.el);
                deleted = [];
                while isnested and ii>0:
                    oldc = self.cs[ii];
                    oldc.delc(); deleted.append(oldc);
                    ii -= 1; isnested = (self.cs[ii].loc.el != self.cs[0].loc.el);
                for delch in reversed(deleted):
                    # dh.debug([delc.c,delc.cw])
                    self.appendc(delch.c,delch.cw,delch.dx,delch.dy);
                    self.cs[-1].pending_style = delch.sty;
                    self.cs[-1].parsed_pts_ut = delch.parsed_pts_ut;
                    self.cs[-1].parsed_pts_t  = delch.parsed_pts_t;
                    
                    # dh.debug(self.cs[-1].c)
            # dh.debug(self.x)
            
            # dh.idebug([self.txt(),nw.txt()])
            
            # Calculate the number of spaces we need to keep the position constant
            # (still need to adjust for anchors)
            # bl2 = (-self.transform).apply_to_point(nw.pts_t[0])
            # br1 = self.pts_ut[3];
            tr1, br1, tl2, bl2 = self.get_orig_pts(nw)
            lc = self.cs[-1]; # last character
            numsp = (bl2.x-br1.x)/(lc.sw/self.sf);
            mytxt = self.txt();
            numsp = max(0,round(numsp));
            if (mytxt is not None and len(mytxt)>0 and mytxt[-1]==' ') \
                or type in ['super','sub']: # no extra spaces for sub/supers or if there's already one
                    numsp=0;
            for ii in range(numsp):
                self.appendc(' ',lc.sw,0,0)
                
            for c in nw.cs:
                notfirst = c!=nw.cs[0]
                c.delc();
                
                ntype = copy.copy(type)
                otype = dh.Get_Style_Comp(c.sty,'baseline-shift');
                if otype in ['super','sub'] and type=='normal':
                    ntype = otype
                self.appendc(c.c,c.cw,c.dx*notfirst,c.dy)
                
                self.cs[-1].parsed_pts_ut = [(-self.transform).apply_to_point(p) for p in c.parsed_pts_t];
                self.cs[-1].parsed_pts_t  = c.parsed_pts_t;
                
                # We cannot yet apply any styles. Instead, add the character and add a pending style
                # that will be applied at the end
                newc = self.cs[-1]; newsty=None;
                if c.nstyc!=newc.nstyc:
                    newsty = c.sty;
                
                
                if ntype in ['super','sub']:
                    if newsty is None:
                        newsty = Style2('');
                    else:
                        newsty = Style2(newsty)
                    sz = round(c.sw/newc.sw*100)
                    
                    # Nativize super/subscripts                
                    newsty['font-size'] = str(sz)+'%';
                    if ntype=='super':
                        newsty['baseline-shift']='super'
                    else:
                        newsty['baseline-shift']='sub'
                    
                    # Leave baseline unchanged (works, but do I want it?)
    #                if nw.orig_pts_ut is not None:
    #                    w2x = [p[0].x for p in nw.orig_pts_ut];
    #                    min2 = min([ii for ii in range(len(w2x)) if min(w2x)==w2x[ii]]);
    #                    bl2 = (-self.transform).apply_to_point(nw.orig_pts_t[min2][0]);
    #                else:
    #                    bl2 = (-self.transform).apply_to_point(nw.pts_t[0])
    #                if self.orig_pts_ut is not None:
    #                    w1x = [p[3].x for p in self.orig_pts_ut];
    #                    max1 = max([ii for ii in range(len(w1x)) if max(w1x)==w1x[ii]]);
    #                    br1 = self.orig_pts_ut[max1][3];
    #                else:
    #                    br1 = self.pts_ut[3];
    #                shft = round(-(bl2.y-br1.y)/self.fs*100*self.sf);
    #                newsty['baseline-shift']= str(shft)+'%';
                    
                    newsty = str(newsty)
                self.cs[-1].pending_style = newsty;
                
            if dh.cascaded_style2(self.ln.xsrc).get('letter-spacing') is not None:
                dh.Set_Style_Comp(self.ln.xsrc,'letter-spacing','0');
                
            # Following the merge, append the new word's data to the orig pts lists
            # self.orig_pts_t  += nw.orig_pts_t
            # self.orig_pts_ut += [[(-self.transform).apply_to_point(p) for p in pts] for pts in nw.orig_pts_t]
            # self.orig_bb = self.orig_bb.union(nw.orig_bb)
            self.parsed_bb = self.parsed_bb.union(nw.parsed_bb)

       
    # For merged text, get the pre-merged coordinates in my coordinate system
    def get_orig_pts(self,w2):
        
        mv = float('inf'); ci=None
        for ii in range(len(w2.cs)):
            if w2.cs[ii].parsed_pts_ut is not None:
                if w2.cs[ii].parsed_pts_ut[0].x<mv:
                    mv = w2.cs[ii].parsed_pts_ut[0].x;
                    ci = ii;
        
        # dh.idebug('"'+w2.txt()+'"')
        # dh.idebug(len(w2.cs))
        # dh.idebug(w2.cs[0].parsed_pts_ut)
        bl2 = (-self.transform).apply_to_point(w2.cs[ci].parsed_pts_t[0])
        tl2 = (-self.transform).apply_to_point(w2.cs[ci].parsed_pts_t[1]);
        
        mv = float('-inf'); ci=None
        for ii in range(len(self.cs)):
            if self.cs[ii].parsed_pts_ut is not None:
                if self.cs[ii].parsed_pts_ut[3].x>mv:
                    mv = self.cs[ii].parsed_pts_ut[3].x;
                    ci = ii;
        
        tr1 = self.cs[ci].parsed_pts_ut[2];
        br1 = self.cs[ci].parsed_pts_ut[3];
        return tr1, br1, tl2, bl2
    
        # if w2.orig_pts_ut is not None:
        #     w2x = [p[0].x for p in w2.orig_pts_ut];
        #     min2 = min([ii for ii in range(len(w2x)) if min(w2x)==w2x[ii]]);
        #     bl2 = (-self.transform).apply_to_point(w2.orig_pts_t[min2][0])
        #     tl2 = (-self.transform).apply_to_point(w2.orig_pts_t[min2][1]);
        # else:
        #     bl2 = (-self.transform).apply_to_point(w2.pts_t[0])
        #     tl2 = (-self.transform).apply_to_point(w2.pts_t[1]);
        # if self.orig_pts_ut is not None:
        #     w1x = [p[3].x for p in self.orig_pts_ut];
        #     max1 = max([ii for ii in range(len(w1x)) if max(w1x)==w1x[ii]]);
        #     tr1 = self.orig_pts_ut[max1][2];
        #     br1 = self.orig_pts_ut[max1][3];
        # else:
        #     tr1 = self.pts_ut[2];
        #     br1 = self.pts_ut[3];
            
        # # if abs((tr1-tr1b).x)>1e-6:
        # #     dh.debug([self.txt(),w2.txt()])
        # #     dh.debug([tr1-tr1b, br1-br1b, tl2-tl2b, bl2-bl2b])
        # #     dh.debug(tr1)
        # #     for c in self.cs:
        # #         dh.debug(c.parsed_pts_ut[2])
        # return tr1, br1, tl2, bl2
    
    # Adjusts the position of merged text to account for small changes in word position that occur
    # This depends on alignment, so it is generally done after the final justification is set
    def fix_merged_position(self):
        
        gcs = [c for c in self.cs if c.c!=' ']
        if len(gcs)>0:
            omaxx = max([c.parsed_pts_ut[3].x for c in gcs])
            ominx = min([c.parsed_pts_ut[0].x for c in gcs])
            newptsut = [c.interp_pts()[0] for c in gcs]
            nmaxx = max([p[3].x for p in newptsut])
            nminx = min([p[0].x for p in newptsut])
            
            # dh.debug([ominx,omaxx,nminx,nmaxx])
            anch_frac = {'start': 0, 'middle': 0.5, 'end': 1}
            xf = anch_frac[self.ln.anchor];
            deltaanch = (nminx*(1-xf)+nmaxx*xf) - (ominx*(1-xf)+omaxx*xf);  # how much the final anchor moved
            # dh.debug(deltaanch)
            if deltaanch!=0:
                newx = self.ln.x; newx[self.ln.cs.index(self.cs[0])] -= deltaanch
                self.ln.change_pos(newx)
                self.x -= deltaanch
            self.ln.ll.Update_Delta();
            self.calcprops()
        # if self.orig_pts_ut is not None:
        #     omaxx = max([p[3].x for p in self.orig_pts_ut])
        #     ominx = min([p[0].x for p in self.orig_pts_ut])
        #     nmaxx = self.pts_ut[3].x;
        #     nminx = self.pts_ut[0].x;
            
        #     # dh.debug([ominx,omaxx,nminx,nmaxx])
        #     anch_frac = {'start': 0, 'middle': 0.5, 'end': 1}
        #     xf = anch_frac[self.ln.anchor];
        #     deltaanch = (nminx*(1-xf)+nmaxx*xf) - (ominx*(1-xf)+omaxx*xf);  # how much the final anchor moved
        #     # dh.debug(deltaanch)
        #     if deltaanch!=0:
        #         newx = self.ln.x; newx[self.ln.cs.index(self.cs[0])] -= deltaanch
        #         self.ln.change_pos(newx)
        #         self.x -= deltaanch
        #     self.ln.ll.Update_Delta();
        #     self.calcprops() 
    
    # Calculate the properties of a word that depend on its characters       
    def calcprops(self): # calculate properties inherited from characters
        w = self;
        dxl = [c.dx for c in self.cs];
        if len(dxl)==0: dxl=[0];
#        dh.debug(w.txt())
#        dh.debug(dxl)
        wadj = [0 for c in self.cs];
        if KERN_TABLE:
            for ii in range(1,len(self.cs)):
                dk = self.cs[ii].dkerns.get((self.cs[ii-1].c,self.cs[ii].c));
                if dk is None: dk=0;                  # for chars of different style
                wadj[ii] = dk
        if len(w.cs)>0:
            dx0 = [0]+dxl[1:];
            tmp = [w.cs[ii].cw + dx0[ii]*w.sf + wadj[ii] for ii in range(len(w.cs))];
            w.cumw = [sum(tmp[:ii+1]) for ii in range(len(tmp))];    # cumulative width up to and including the iith char
            w.ww = sum([c.cw  for c in w.cs])+sum(dxl[1:])*w.sf + sum(wadj);
            w.fs = max([c.fs          for c in w.cs])
            w.sw = max([c.sw for c in w.cs])
            w.ch = max([c.ch   for c in w.cs])
        w.angle = w.ln.angle
        
        if len(w.cs)>0:
            ymin = min([w.y+c.dy-c.ch/w.sf   for c in w.cs]);
            ymax = max([w.y+c.dy             for c in w.cs]);
        else:
            ymin = w.y-w.ch/w.sf; ymax = w.y;
            
        # If last char of a multichar line is a space, is not rendered
        wwo = w.ww;
        w.unrenderedspace =len(w.cs)>1 and w.cs[-1]==self.ln.cs[-1] and w.cs[-1].c==' '
        if w.unrenderedspace:
            wwo -= w.cs[-1].cw;           # ww for offset calculations  
        
        if self.ln.anchor=='middle':
            w.offx = dxl[0]*w.sf/2-wwo/2;
        elif self.ln.anchor=='end':
            w.offx = -wwo;
        else:
            w.offx = dxl[0]*w.sf;
            
        # dh.debug([self.txt(),sum(wadj)])
            
        w.pts_ut = [Vector2d(w.x + w.offx/w.sf,      ymax), Vector2d(w.x+ w.offx/w.sf,       ymin),\
                    Vector2d(w.x+(w.ww+w.offx)/w.sf, ymin), Vector2d(w.x+(w.ww+w.offx)/w.sf, ymax)];
        # w.pts_t=[];
        # for p in w.pts_ut:
        #     w.pts_t.append(w.transform.apply_to_point(p))
        w.pts_t = [w.transform.apply_to_point(p) for p in w.pts_ut]
        w.bb = bbox([min([p.x for p in w.pts_t]),\
                min([p.y for p in w.pts_t]),\
                max([p.x for p in w.pts_t])-min([p.x for p in w.pts_t]),\
                max([p.y for p in w.pts_t])-min([p.y for p in w.pts_t])]);
            
        c_pts_ut = [Vector2d(w.x + w.offx/w.sf,      ymax), Vector2d(w.x+ w.offx/w.sf,       ymin),\
                    Vector2d(w.x+(w.ww+w.offx)/w.sf, ymin), Vector2d(w.x+(w.ww+w.offx)/w.sf, ymax)]
            
        
        
# A single character and its style
class tchar:
    def __init__(self, c,fs,sf,prop,sty,nsty,loc):
        self.c = c;
        self.fs = fs;     # nominal font size
        self.sf = sf;     # how much it is scaled to get to the actual width
        self.prop = prop;
        self.cw = prop.charw;     # actual character width in user units
        self.sty  = sty;  # actual style
        self.nsty = nsty; # normalized style
        self.nstyc = dh.Set_Style_Comp(nsty,'fill',dh.Get_Style_Comp(sty,'fill')) # with color
        self.loc = loc;   # true location: [parent, 'text' or 'tail', index]
        self.ch = prop.caph;     # cap height (height of flat capitals like T)
        # self.dr = dr;     # descender (length of p/q descender))
        self.sw = prop.spacew;     # space width for style
        self.ln = None;   # my line (to be assigned)
        self.w  = None;   # my word (to be assigned)
        self.type=None;   # 'normal','super', or 'sub' (to be assigned)
        self.ofs = fs;    # original character width (never changed, even if character is updated later)
        self.dx = 0;      # get later
        self.dy = 0;      # get later
        self.deltanum = None;      # get later
        self.dkerns = prop.dkerns;
        self.pending_style = None; # assign later (maybe)
        self.parsed_pts_t = None; self.parsed_pts_ut = None; # for merging later
        
    def delc(self): # deletes me from document (and from my word/line)
        # Deleting a character causes the word to move if it's center- or right-justified. Adjust position to fix
        cwo = self.cw;
        if self.w.unrenderedspace and self.w.cs[-1]==self:
            if len(self.w.cs)>1 and self.w.cs[-2].c!=' ':
                cwo = 0; # deletion will not affect position
                
        if self==self.w.cs[0]:              # from beginning of line
            if self.ln.anchor=='middle':
                deltax = -cwo/self.sf / 2;
            elif self.ln.anchor=='end':
                deltax = 0;
            else:
                deltax = -cwo/self.sf;
        else:                               # assume end of line
            if self.ln.anchor=='middle':
                deltax = cwo/self.sf / 2;
            elif self.ln.anchor=='end':
                deltax = cwo/self.sf;
            else:
                deltax = 0;
        if deltax!=0:
            newx = self.ln.x; 
            nnii = [ii for ii in range(len(self.ln.x)) if self.ln.x[ii] is not None]; # non-None
            newx[nnii[self.ln.ws.index(self.w)]] -= deltax;
            
#            dh.debug(self.ln.x)
            self.ln.change_pos(newx)
            self.w.x -= deltax
    
        # Delete from document
        if self.loc.tt=='text':
            self.loc.el.text = del2(self.loc.el.text,self.loc.ind)
        else:
            self.loc.el.tail = del2(self.loc.el.tail,self.loc.ind)
        myi = self.ln.cs.index(self) # index in line
        if len(self.ln.x)>1:
            if myi<len(self.ln.x):
                if myi<len(self.ln.x)-1 and self.ln.x[myi] is not None and self.ln.x[myi+1] is None: 
                    newx = del2(self.ln.x,myi+1) # next x is None, delete that instead
                elif myi==len(self.ln.x)-1 and len(self.ln.cs)>len(self.ln.x):
                    newx = self.ln.x; # last x, characters still follow
                else:
                    newx = del2(self.ln.x,myi)
                newx = newx[:len(self.ln.cs)-1];  # we haven't deleted the char yet, so make it len-1 long
                self.ln.change_pos(newx);
                    
        # Delete from line
        for ii in range(myi+1,len(self.ln.cs)):         # need to decrement index of subsequent objects with the same parent
            ca = self.ln.cs[ii];
            if ca.loc.tt==self.loc.tt and ca.loc.el==self.loc.el:
                ca.loc.ind -= 1
            if ca.w is not None:
                i2 = ca.w.cs.index(ca)
                ca.w.iis[i2] -= 1
        self.ln.cs = del2(self.ln.cs,myi)
        oldll = self.ln.ll;
        if len(self.ln.cs)==0: # line now empty
            self.ln.dell();
        self.ln = None
        
        
        # Delete from word
        myi = self.w.cs.index(self)
        self.w.cs = del2(self.w.cs ,myi)
        self.w.iis= del2(self.w.iis,myi)
        self.w.calcprops()
        if len(self.w.cs)==0: # word now empty
            self.w.delw();
        self.w = None

        # Update the dx/dy value in the LineList
        oldll.Update_Delta();
        # dh.debug([[ln.x for ln in oldll.lns],[ln.xsrc.get('x') for ln in oldll.lns]])
        
    def add_style(self,sty):
    # Adds a style to an existing character by wrapping it in a new Tspan
        t = Tspan();
        t.text = self.c;
        t.style = str(sty);
        
        prt = self.loc.el;
        if self.loc.tt=='text':
            tbefore = prt.text[0:self.loc.ind];
            tafter  = prt.text[self.loc.ind+1:];
            prt.text = tbefore;
            prt.insert(0,t);
            t.tail = tafter;
        else:
            tbefore = prt.tail[0:self.loc.ind];
            tafter  = prt.tail[self.loc.ind+1:];
            prt.tail = tbefore
            gp =prt.getparent();                # parent is a Tspan, so insert it into the grandparent
            pi = (gp.getchildren()).index(prt);   
            gp.insert(pi+1,t); # above the parent
            t.tail =  tafter
            
        myi = self.ln.cs.index(self)
        for ii in range(myi+1,len(self.ln.cs)):  # for characters after, update location
            ca = self.ln.cs[ii];
            ca.loc = cloc(t,'tail',ii-myi-1)
        self.loc = cloc(t,'text',0)                  # update my own location
        
    def makesubsuper(self,sz=65):
        if self.type=='super':
            sty = 'font-size:'+str(sz)+'%;baseline-shift:super';
        else: #sub
            sty = 'font-size:'+str(sz)+'%;baseline-shift:sub';
        self.add_style(sty);   
        
    def applypending(self):
        self.add_style(self.pending_style);
        
    def interp_pts(self):
        """  Interpolate the pts of a word to get a specific character's pts"""
        myi = self.w.cs.index(self)
        
        fracl = 0;
        if myi>0:
            fracl = self.w.cumw[myi-1]/self.w.ww
        fracr = self.w.cumw[myi]/self.w.ww;
        ret_pts_ut = [(self.w.pts_ut[3]-self.w.pts_ut[0])*fracl+self.w.pts_ut[0],\
                      (self.w.pts_ut[2]-self.w.pts_ut[1])*fracl+self.w.pts_ut[1],\
                      (self.w.pts_ut[2]-self.w.pts_ut[1])*fracr+self.w.pts_ut[1],\
                      (self.w.pts_ut[3]-self.w.pts_ut[0])*fracr+self.w.pts_ut[0]]
            
        ret_pts_t  = [(self.w.pts_t[3]-self.w.pts_t[0])*fracl+self.w.pts_t[0],\
                      (self.w.pts_t[2]-self.w.pts_t[1])*fracl+self.w.pts_t[1],\
                      (self.w.pts_t[2]-self.w.pts_t[1])*fracr+self.w.pts_t[1],\
                      (self.w.pts_t[3]-self.w.pts_t[0])*fracr+self.w.pts_t[0]]
        return ret_pts_ut, ret_pts_t
    
    # def changex(self,newx):
    #     self.ln.x[self.ln.cs.index(self)] = newx
    #     if self.ln.x==[]: self.ln.xsrc.set('x',None)
    #     else:             self.ln.xsrc.set('x',' '.join([str(v) for v in self.ln.x]))
        

# A modified bounding box class
class bbox:
    def __init__(self, bb):
        self.x1 = bb[0];
        self.x2 = bb[0]+bb[2];
        self.y1 = bb[1];
        self.y2 = bb[1]+bb[3];
        self.xc = (self.x1+self.x2)/2;
        self.yc = (self.y1+self.y2)/2;
        self.w  = bb[2];
        self.h  = bb[3];
    def intersect(self,bb2):
        return (abs(self.xc - bb2.xc) * 2 < (self.w + bb2.w)) and \
               (abs(self.yc - bb2.yc) * 2 < (self.h + bb2.h));
    def union(self,bb2):
        minx = min([self.x1,self.x2,bb2.x1,bb2.x2]);
        maxx = max([self.x1,self.x2,bb2.x1,bb2.x2]);
        miny = min([self.y1,self.y2,bb2.y1,bb2.y2]);
        maxy = max([self.y1,self.y2,bb2.y1,bb2.y2]);
        return bbox([minx,miny,maxx-minx,maxy-miny]);

def del2(x,ind): # deletes an index from a list
    return x[:ind]+x[ind+1:]

def extendind(x,ind,val,default=None): # indexes a matrix, extending it if necessary
    if ind>=len(x):
        x+=[default]*(ind+1-len(x));
    x[ind] = val;
    return x

def sortnone(x): # sorts an x with Nones (skip Nones)
    rem = list(range(len(x)))
    minxrem = min([x[r] for r in rem if x[r] is not None]);
    ii = min([r for r in rem if x[r]==minxrem]);
    so = [ii]; rem.remove(ii);
    while len(rem)>0:
        if ii==len(x)-1 or x[ii+1] is not None:
            minxrem = min([x[r] for r in rem if x[r] is not None]);
            ii = min([r for r in rem if x[r]==minxrem]);
            so+=[ii]; 
        else:
            ii+=1
        rem.remove(ii);
    return so

# A class representing the properties of a single character
class cprop():
    def __init__(self, char,cw,sw,xo,ch,dr,dkerns):
        self.char = char;
        self.charw = cw;    # character width
        self.spacew = sw;   # space width
        self.xoffset = xo;  # x offset from anchor
        self.caph = ch;     # cap height
        self.descrh = dr;   # descender height
        self.dkerns = dkerns# table of how much extra width a preceding character adds to me
    def __mul__(self, scl):
        dkern2 = dict();
        for c in self.dkerns.keys():
            dkern2[c] = self.dkerns[c]*scl;
        return cprop(self.char,self.charw*scl,self.spacew*scl,self.xoffset*scl,self.caph*scl,self.descrh*scl,dkern2)
# A class indicating a single character's location in the SVG
class cloc():
    def __init__(self, el,tt,ind):
        self.el = el;  # the element it belongs to
        self.tt = tt;  # 'text' or 'tail'
        self.ind= ind; # its index
        
        tmp = el;
        if isinstance(tmp.getparent(),(TextElement,Tspan)):
            tmp = tmp.getparent()
        self.textel = tmp; # parent TextElement

# A class representing the properties of a collection of characters
class Character_Table():
    def __init__(self, els,caller):
        self.caller = caller;
        self.ctable, self.bbs = self.measure_character_widths2(els)
        
    def get_prop(self,char,sty):
        if sty in list(self.ctable.keys()):
            return self.ctable[sty][char]
            # matches = [jj for jj in range(len(self.ctable[sty])) if self.ctable[sty][jj].char==char]
            # if len(matches)>0:
            #     return self.ctable[sty][matches[0]]
            # else:
            #     dh.debug('No character matches!');
            #     dh.debug('Character: '+char)
            #     dh.debug('Style: '+sty);
            #     dh.debug('Existing characters: '+str(list([self.ctable[sty][jj].char for jj in range(len(self.ctable[sty]))])))
            #     quit()
        else:
            dh.debug('No style matches!');
            dh.debug('Character: '+char)
            dh.debug('Style: '+sty);
            dh.debug('Existing styles: '+str(list(self.ctable.keys())))

    def generate_character_table(self,els,ctable):
        if isinstance(els,list):
            for el in els:
                ctable = self.generate_character_table(el,ctable);
        else:
            el=els;
            ks=el.getchildren();
            for k in ks:
                ctable = self.generate_character_table(k,ctable);
                    
            if ctable is None:
                ctable = dict();
            if isinstance(el,(TextElement,Tspan)) and el.getparent() is not None: # textelements not deleted
                if el.text is not None:
                    # sty = str(el.composed_style());
                    sty = str(dh.selected_style_local(el));
                    sty = self.normalize_style(sty)    
                    if sty in list(ctable.keys()):
                        ctable[sty] = list(set(ctable[sty]+list(el.text)));
                    else:
                        ctable[sty] = list(set(list(el.text)));
                if isinstance(el,Tspan) and el.tail is not None and el.tail!='':
                    # sty = str(el.getparent().composed_style());
                    sty = str(dh.selected_style_local(el.getparent()));
                    sty = self.normalize_style(sty)   
#                    dh.debug(el.tail)
#                    dh.debug(el.get_id())
#                    dh.debug(str(dh.selected_style_local(el.getparent())))
#                    dh.debug(sty)
                    if sty in list(ctable.keys()):
                        ctable[sty] = list(set(ctable[sty]+list(el.tail)));
                    else:
                        ctable[sty] = list(set(list(el.tail)));
        for sty in list(ctable.keys()): # make sure they have NBSPs
            ctable[sty] = list(set(ctable[sty]+[' ']))
        return ctable
    
    def measure_character_widths(self,els):
        # Measure the width of all characters of a given style by generating copies with two and three extra spaces.
        # We take the difference to get the width of a space, then subtract that to get the character's full width.
        # This includes any spaces between characters as well.
        # The width will be the width of a character whose composed font size is 1 uu.
        ct = self.generate_character_table(els,None);
        docscale = self.caller.svg.scale;
        # dh.debug(self.caller.svg.scale)
                            
        pI1 = 'pI  ';        # pI with 2 spaces
        pI2 = 'pI   ';       # pI with 3 spaces
        # We add pI as test characters because p gives the font's descender (how much the tail descends)
        # and I gives its cap height (how tall capital letters are).
        
        # txts = dict();
        # for s in list(ct.keys()):
        #     nt = TextElement();
        #     nt.set('style',s)
        #     nt.set('xml:space','preserve'); # needed to prevent spaces from collapsing
        #     self.caller.svg.append(nt);
        #     dh.get_id2(nt); # assign id now
        #     txts[s] = nt;
        # def Make_Character(c,sty):
        #     nt = Tspan();
        #     nt.text = c;
        #     nt.set('x','0')
        #     txts[sty].append(nt);
        #     dh.get_id2(nt); # assign id now
        #     return nt
        
        global cnt
        cnt = 0;
        
        def Make_Character(c,sty):
            nt = TextElement();
            nt.text = c;
            nt.set('style',sty)
            nt.set('xml:space','preserve'); # needed to prevent spaces from collapsing
            self.caller.svg.append(nt);
            dh.get_id2(nt); # assign id now
            global cnt
            cnt += 1;
            return nt
                        
        ct2 = dict();
        for s in list(ct.keys()):
            ct2[s]=dict();
            for ii in range(len(ct[s])):
                t = Make_Character(ct[s][ii]+'  ',s);    # character with 2 spaces (last space not rendered)
                myc = ct[s][ii];
                dkern = dict();
                if KERN_TABLE:
                    for jj in range(len(ct[s])):
                        pc = ct[s][jj];
                        t2 = Make_Character(pc+myc+'  ',s); # precede by all chars of the same style
                        dkern[ct[s][jj]] = [ct[s][jj],t2,t2.get_id()];
                ct2[s][myc]=[myc,t,t.get_id(),dkern];     
            t = Make_Character(pI1,s);              
            ct2[s][pI1]=[pI1,t,t.get_id(),dict()];             
            t = Make_Character(pI2,s);        
            ct2[s][pI2]=[pI2,t,t.get_id(),dict()]; 
        ct = ct2;

            
        nbb = dh.Get_Bounding_Boxes(self.caller,True);  
        dkern = dict();
        for s in list(ct.keys()):
            for ii in ct[s].keys():
                # dh.debug(nbb)
                bb=nbb[ct[s][ii][2]]
                wdth = bb[0]+bb[2]
                caphgt = -bb[1]
                bbstrt = bb[0]
                dscnd = bb[1]+bb[3]
                ct[s][ii][1].delete();
                
                if KERN_TABLE:
                    precwidth = dict();
                    for jj in ct[s][ii][-1].keys():
                        bb=nbb[ct[s][ii][-1][jj][2]];
                        wdth2 = bb[0]+bb[2];
                        precwidth[jj] = wdth2;         # width including the preceding character and extra kerning
                        ct[s][ii][-1][jj][1].delete();
                    ct[s][ii] = [ct[s][ii][0],wdth,bbstrt,caphgt,dscnd,precwidth]
                else:                        
                    ct[s][ii] = [ct[s][ii][0],wdth,bbstrt,caphgt,dscnd]
                    
            if KERN_TABLE:
                dkern[s] = dict();
                for ii in ct[s].keys():
                    sw = ct[s][pI2][1] - ct[s][pI1][1];
                    mcw = ct[s][ii][1] - sw;      # my character width
                    if ii==' ': mcw = sw;
                    for jj in ct[s][ii][-1].keys():
                        # myi = mycs.index(jj);
                        pcw = ct[s][jj][1] - sw; # preceding char width
                        if ct[s][jj][0]==' ': pcw = sw;
                        bcw = ct[s][ii][-1][jj] - sw; # both char widths
                        dkern[s][jj,ct[s][ii][0]] = bcw - pcw - mcw;          # preceding char, then next char
                        
                
        for s in list(ct.keys()):
            sw = ct[s][pI2][1] - ct[s][pI1][1] # space width is the difference in widths of the last two
            ch = ct[s][pI2][3]                # cap height
            dr = ct[s][pI2][4]                # descender
            for ii in ct[s].keys():
                cw = ct[s][ii][1] - sw;  # character width (full, including extra space on each side)
                xo = ct[s][ii][2]        # x offset: how far it starts from the left anchor
                if ct[s][ii][0]==' ':
                    cw = sw;
                    xo = 0;
                    
                # dh.debug([ii,cw,sw])
                
                dkernscl = dict();
                if KERN_TABLE:    
                    for k in dkern[s].keys():
                        dkernscl[k] = dkern[s][k]/docscale;
                # dh.debug([ct[s][ii][0],dkern])
                ct[s][ii] = cprop(ct[s][ii][0],cw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale,dkernscl);
                # Because a nominal 1 px font is docscale px tall, we need to divide by the docscale to get the true width
                
            
            # dh.debug(dkernscl)    
            # ct[s] = ct[s][0:Nl]
            
        
        # for s in list(ct.keys()):
        #     txts[s].delete();
        # dh.debug(ct)
        return ct, nbb

    
    def measure_character_widths2(self,els):
        # Measure the width of all characters of a given style by generating copies with two and three extra spaces.
        # We take the difference to get the width of a space, then subtract that to get the character's full width.
        # This includes any spaces between characters as well.
        # The width will be the width of a character whose composed font size is 1 uu.
        ct = self.generate_character_table(els,None);
        # docscale = dh.vscale(self.caller.svg);           
        
        pI1 = 'pI  ';        # pI with 2 spaces
        pI2 = 'pI   ';       # pI with 3 spaces
        # We add pI as test characters because p gives the font's descender (how much the tail descends)
        # and I gives its cap height (how tall capital letters are).
        
        # In this version, a new document is generated instead of using the existing one. This can be much
        # faster as we are not parsing an entire element tree
        pxinuu = inkex.units.convert_unit('1px','mm');  # test document has uu = 1 mm (210 mm / 210)
        docscale = 1; # test doc has no scale
        svgstart = '<svg width="210mm" height="297mm" viewBox="0 0 210 297" id="svg60386" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg"> <defs id="defs60383" /> <g id="layer1">'
        svgstop  = '</g> </svg>';
        txt1 = '<text xml:space="preserve" style="';
        txt2 = '" id="text';
        txt3 = '">';
        txt4 = '</text>'
        svgtexts = ''; cnt=0;
        tmpname = self.caller.options.input_file+'_tmp'
        f = open(tmpname, "wb");
        f.write(svgstart.encode("utf8"));
        from xml.sax.saxutils import escape
        def Make_Character2(c,sty):
            nonlocal svgtexts, cnt
            cnt+=1
            svgtexts += txt1+sty+txt2+str(cnt)+txt3+escape(c)+txt4
            if cnt % 1000 == 0:
                f.write(svgtexts.encode("utf8"));
                svgtexts = '';
            return 'text'+str(cnt)
                        
        ct2 = dict();
        for s in list(ct.keys()):
            ct2[s]=dict();
            for ii in range(len(ct[s])):
                t = Make_Character2(ct[s][ii]+'  ',s);    # character with 2 spaces (last space not rendered)
                myc = ct[s][ii];
                dkern = dict();
                if KERN_TABLE:
                    for jj in range(len(ct[s])):
                        pc = ct[s][jj];
                        t2 = Make_Character2(pc+myc+'  ',s); # precede by all chars of the same style
                        dkern[ct[s][jj]] = [ct[s][jj],0,t2];
                ct2[s][myc]=[myc,0,t,dkern];     
            t = Make_Character2(pI1,s);              
            ct2[s][pI1]=[pI1,0,t,dict()];             
            t = Make_Character2(pI2,s);        
            ct2[s][pI2]=[pI2,0,t,dict()]; 
        ct = ct2;
        f.write((svgtexts+svgstop).encode("utf8"));
        f.close();
            
        nbb = dh.Get_Bounding_Boxes(filename=tmpname,pxinuu=pxinuu)
        import os; os.remove(tmpname);
        
        dkern = dict();
        for s in list(ct.keys()):
            for ii in ct[s].keys():
                # dh.debug(nbb)
                bb=nbb[ct[s][ii][2]]
                wdth = bb[0]+bb[2]
                caphgt = -bb[1]
                bbstrt = bb[0]
                dscnd = bb[1]+bb[3]
                
                if KERN_TABLE:
                    precwidth = dict();
                    for jj in ct[s][ii][-1].keys():
                        bb=nbb[ct[s][ii][-1][jj][2]];
                        wdth2 = bb[0]+bb[2];
                        precwidth[jj] = wdth2;         # width including the preceding character and extra kerning
#                        ct[s][ii][-1][jj][1].delete();
                    ct[s][ii] = [ct[s][ii][0],wdth,bbstrt,caphgt,dscnd,precwidth]
                else:                        
                    ct[s][ii] = [ct[s][ii][0],wdth,bbstrt,caphgt,dscnd]
                    
            if KERN_TABLE:
                dkern[s] = dict();
                for ii in ct[s].keys():
                    sw = ct[s][pI2][1] - ct[s][pI1][1];
                    mcw = ct[s][ii][1] - sw;      # my character width
                    if ii==' ': mcw = sw;
                    for jj in ct[s][ii][-1].keys():
                        # myi = mycs.index(jj);
                        pcw = ct[s][jj][1] - sw; # preceding char width
                        if ct[s][jj][0]==' ': pcw = sw;
                        bcw = ct[s][ii][-1][jj] - sw; # both char widths
                        dkern[s][jj,ct[s][ii][0]] = bcw - pcw - mcw;          # preceding char, then next char
                        
                
        for s in list(ct.keys()):
            sw = ct[s][pI2][1] - ct[s][pI1][1] # space width is the difference in widths of the last two
            ch = ct[s][pI2][3]                # cap height
            dr = ct[s][pI2][4]                # descender
            for ii in ct[s].keys():
                cw = ct[s][ii][1] - sw;  # character width (full, including extra space on each side)
                xo = ct[s][ii][2]        # x offset: how far it starts from the left anchor
                if ct[s][ii][0]==' ':
                    cw = sw;
                    xo = 0;
                    
                # dh.debug([ii,cw,sw])
                
                dkernscl = dict();
                if KERN_TABLE:    
                    for k in dkern[s].keys():
                        dkernscl[k] = dkern[s][k]/docscale;
                # dh.debug([ct[s][ii][0],dkern])
                # dh.debug([ct[s][ii][0],cw,docscale])
                ct[s][ii] = cprop(ct[s][ii][0],cw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale,dkernscl);
                # Because a nominal 1 px font is docscale px tall, we need to divide by the docscale to get the true width
                
            
            # dh.debug(dkernscl)    
            # ct[s] = ct[s][0:Nl]
            
        
        # for s in list(ct.keys()):
        #     txts[s].delete();
        # dh.debug(ct)
        return ct, nbb
    
    
    # For generating test characters, we want to normalize the style so that we don't waste time
    # generating a bunch of identical characters whose font-sizes are different. A style is generated
    # with a 1px font-size, and only with presentation attributes that affect character shape.
    textshapeatt = ['font-family','font-size-adjust','font-stretch',\
                    'font-style','font-variant','font-weight',\
                    'text-decoration','text-rendering','font-size']
    # 'stroke','stroke-width' do not affect kerning at all
    @staticmethod
    def normalize_style(sty):
        sty  = Style2(sty); stykeys = list(sty.keys());
        sty2 = Style2('')
        for a in Character_Table.textshapeatt:
            if a in stykeys:
                styv = sty.get(a);
                # if styv is not None and styv.lower()=='none':  
                #     styv=None # actually don't do this because 'none' might be overriding inherited styles
                if styv is not None:
                    sty2[a]=styv;
        
        nones = [None,'none','None'];
        sty2['font-size']='1px'
        if not(sty2.get('font-family') in nones):
            sty2['font-family']=','.join([v.strip().strip('\'') for v in sty2['font-family'].split(',')]); # strip spaces b/t styles
        # if sty2.get('font-style').lower()=='normal':
        #     sty2['font-style']=None;

        tmp = Style2('');
        for k in sorted(sty2.keys()): # be sure key order is alphabetical
            tmp[k]=sty2[k];
        sty2 = tmp;

        # dh.debug([sty2.get('stroke'),sty2.get('stroke-width')])

        return str(sty2)
    
# Recursively delete empty elements
# Tspans are deleted if they're totally empty, TextElements are deleted if they contain only whitespace
def deleteempty(el):
    for k in el.getchildren():
        deleteempty(k)
    txt = el.text;
    tail = el.tail;
    if (txt is None or len((txt))==0) and (tail is None or len((tail))==0) and len(el.getchildren())==0:
        el.delete();                    # delete anything empty
        # dh.debug(el.get_id())
    elif isinstance(el, (TextElement)):    
        def wstrip(txt): # strip whitespaces
             return txt.translate({ord(c):None for c in ' \n\t\r'}); 
        if all([(d.text is None or len(wstrip(d.text))==0) and (d.tail is None or len(wstrip(d.tail))==0) for d in dh.descendants2(el)]):
            el.delete(); # delete any text elements that are just white space