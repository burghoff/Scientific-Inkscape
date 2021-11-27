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

import dhelpers as dh
import copy
import inkex
from inkex import (TextElement, Tspan ,Vector2d,Transform,Style)


def GetXY(el,xy):
    val = el.get(xy)
    # if xy=='y':
    #     val = el.get('y');
    # else:
    #     val = el.get('x');
        
    if val is None:   
        val = [None]; # None forces inheritance
    else:             
#        dh.debug(val);
#        dh.debug(val.lower()=='None')
        tmp = [];
        for x in val.split():
            if x.lower()=='none':  tmp.append(0);
            else:                  tmp.append(float(x));
        val = tmp;
        # val = [float(x) for x in val.split()];
        # if dval is not None:
        #     dval = [float(x) for x in dval.split()];
        #     # dval2 = [dval[0]];
        #     # for ii in range(1,len(dval)):
        #     #     dval2.append(dval2[ii-1]+dval[ii]); # cumulative sum
        #     # dh.debug(dval2)
        #     if len(dval)<=len(val):
        #         for ii in range(len(dval)):  # dx shorter than x
        #             val[ii] = val[ii]+dval[ii];
        #     else:
        #         for ii in range(len(val)):  # x shorter than dx
        #             dval[ii] = val[ii]+dval[ii];
        #         val = dval;
    # dh.debug(val)
    return val

def GetdXY(el,xy):
    eld = GetXY(el,xy); tmp=el;
    while eld[0] is None and isinstance(tmp.getparent(),(Tspan,TextElement)):
        tmp = tmp.getparent();
        eld = GetXY(el,xy);
    return [eld,tmp]

# A text element that has been parsed into a list of lines
class LineList():
    def __init__(self, el, ctable,debug=False):
        self.ctable = ctable
        self.lns = self.Parse_Lines(el,debug=debug);
        self.textel = el;
        if self.lns is not None:
            for ln in self.lns:
                ln.ll = self;
                
        tlvllns = [ln for ln in self.lns if ln.tlvlno is not None and ln.tlvlno>0]; # top-level lines after 1st
        self.isinkscape = all([ln.inheritx for ln in tlvllns]); # probably made in Inkscape
        # self.Get_Delta(el,'dx');
        # self.Get_Delta(el,'dy');
        # dh.debug([c.c for ln in self.lns for c in ln.cs])
        # dh.debug([c.dx for ln in self.lns for c in ln.cs])
    def txt(self):
        return [v.txt() for v in self.lns]
        
    # Seperate a text element into a group of lines
    def Parse_Lines(self,el,lns=None,debug=False):
        tlvlcall = (lns is None);
        # sty = el.composed_style();
        sty = dh.selected_style_local(el);
        fs,sf,ct,ang = dh.Get_Composed_Width(el,'font-size',4); #dh.debug(el.get_id()); dh.debug(el.composed_transform())
        # if sf is None:
        #     dh.debug(el.get_id())
        # lh = dh.selected_style_local(el).get('line-height');
        # lh2 = dh.Get_Composed_Width(el,'line-height');
        lh = dh.Get_Composed_LineHeight(el);
        # dh.debug(lh)
        # if lh is None: lh=1.25;
#        dh.debug(fs)
        # ct = el.composed_transform();
        nsty=Character_Table.normalize_style(sty);
        tv = el.text;
        
        xv = GetXY(el,'x'); xsrc = el;
        yv = GetXY(el,'y'); ysrc = el;
        # dxv = GetXY(el,'dx'); dxsrc = el;
        # dyv = GetXY(el,'dy'); dysrc = el;
        
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

        # dh.debug(el.get_id())
        # dh.debug(inheritx)
#        if el.get_id()=='tspan7885':
#            dh.debug(nspr)
#            dh.debug(inheritx)
        
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
                                yv   = [lastln.y[0]+offs];
                            else: yv = [None];
                            ysrc = lastln.ysrc;
                        else:                       # continuing previous line
                            yv   = [lns[-1].y[0]];
                            ysrc = lns[-1].ysrc;
                            
            anch = sty.get('text-anchor') 
            if len(lns)!=0 and nspr!='line':
                if lns[-1].anchor is not None:
                    anch = lns[-1].anchor    # non-spr lines inherit the previous line's anchor
            lns.append(tline(xv,yv,inheritx,nspr,anch,ct,ang,el,xsrc,ysrc,continuex,tlvlno,sty))
        
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
                    
        if tlvlcall: # finished recursing, finish lines
            if lns is not None:
                self.Get_Delta(lns,el,'dx');
                self.Get_Delta(lns,el,'dy');
#                for ln in reversed(lns): 
#                    if ln.x[0] is None: # no x ever assigned
#                        ln.x[0] = 0;
#                    if ln.y[0] is None: # no y ever assigned
#                        ln.y[0] = 0;
#                    ln.parse_words()
#                    if len(ln.cs)==0:
#                        lns.remove(ln); # prune empty lines
                for ii in range(len(lns)):
                    ln = lns[ii];
                    if ln.x[0] is None: # no x ever assigned
                        if ln.continuex and ii>0 and len(lns[ii-1].ws)>0:
                            lns[ii-1].ws[-1].calcprops();
                            ln.x[0] = lns[ii-1].ws[-1].pts_ut[3].x
                        else:
                            ln.x[0] = 0;
                    if ln.y[0] is None: # no y ever assigned
                        ln.y[0] = 0;
                    ln.parse_words()
                for ln in reversed(lns): 
                    if len(ln.cs)==0:
                        lns.remove(ln); # prune empty lines
#                    dh.debug(ln.txt())
        return lns
    
    # For debugging only: make a rectange at all of the line's words' nominal bboxes
    def Position_Check(self):
        if self.lns is not None and len(self.lns)>0:
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
                    # dh.debug(w.pts_ut[0][0])
                    # dh.debug(w.pts_ut[2][0])
                
            for ii in range(len(xs)):
                r = inkex.Rectangle();
                r.set('x',min(xs[ii],x2s[ii]))
                r.set('y',min(ys[ii],y2s[ii]))
                r.set('height',abs(ys[ii]-y2s[ii]))
                r.set('width', abs(xs[ii]-x2s[ii]))
                r.set('style','fill-opacity:0.5')
                svg.append(r)
    
    
    # Traverse the element tree to find dx/dy values and apply them to the chars
    def Get_Delta(self,lns,el,xy,dxin=None,cntin=None,dxysrc=None):
        if dxin is None:
            dxy = GetXY(el,xy); dxysrc=el;
            # dh.debug(el.get_id())
            # dh.debug(dxy)
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
                        if xy=='dx': thec[0].dx = dxy[cnt]; thec[0].dxloc = cloc(dxysrc,None,cnt);
                        if xy=='dy': thec[0].dy = dxy[cnt]; thec[0].dyloc = cloc(dxysrc,None,cnt);
                        cnt+=1
#            dh.debug(cnt)
            for k in el.getchildren():
                cnt = self.Get_Delta(lns,k,xy,dxy,cnt,dxysrc);
                if k.get('sodipodi:role')=='line' and isinstance(k,Tspan) and isinstance(k.getparent(),TextElement):
                    cnt += 1; # top-level Tspans have an implicit CR
                if k.tail is not None:
                    for ii in range(len(k.tail)):
                        thec = [c for c in allcs if c.loc.el==k and c.loc.tt=='tail' and c.loc.ind==ii];
                        if cnt < len(dxy):
                            # if dxy[cnt]==30: dh.debug(dxysrc.get_id())
                            if xy=='dx': thec[0].dx = dxy[cnt]; thec[0].dxloc = cloc(dxysrc,None,cnt);
                            if xy=='dy': thec[0].dy = dxy[cnt]; thec[0].dyloc = cloc(dxysrc,None,cnt);
                            cnt+=1
                        
        if toplevel:
            for k in el.getchildren():
                self.Get_Delta(lns,k,xy);
                    
        return cnt
    
#     def Change_Deltas(self,alldx,alldy):
#         cnt = 0;
#         dxdict = dict();
#         for ln in self.lns:
#             for c in self.cs:
#                 elid = c.loc.el.get_id();
#                 if elid in dxdict.keys():
#                     if c.loc.el.tt=='text:
#                 eldict[] = eldict()
#         
#         
#         dxdict = dic
#         for d in descendants2(self.textel):
#             d.
#         
#         
#         self.Get_Delta(self.lns,self.textel,'dx');
#         self.Get_Delta(self.lns,self.textel,'dy');
#         for ln in self.lns:
#             ln.parse_words();
#             for w in ln.ws:
#                 w.calcprops()
                
    # def change_deltas(self,newdx,newdy):
        
        
    
# A single line, which represents a list of characters. Typically a top-level Tspan or TextElement.
# This is further subdivided into a list of words
class tline:
    def __init__(self, x, y, inheritx, nspr, anch, xform,ang,el,xsrc,ysrc,continuex,tlvlno,sty):
        self.x = x; 
        self.y = y;
        self.inheritx = inheritx;    # inheriting position
        self.nsodipodirole = nspr;  # nominal value
        self.anchor = anch
        self.cs = [];
        self.ws = [];
        if xform is None:
            self.transform = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]);
        else:
            self.transform = xform;
        if ang is None:
            self.angle = 0;
        else:
            self.angle = ang; 
        self.xsrc = xsrc; # element from which we derive our x value
        self.ysrc = ysrc; # element from which we derive our x value
        self.continuex = continuex;  # when enabled, x of a line is the endpoint of the previous line
        self.tlvlno = tlvlno;        # which number Tspan I am if I'm top-level (otherwise None)
        self.style = sty;
        self.el = el;
        # self.dx = dx;
        # self.dy = dy;
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
            elif ii<len(self.x): 
                self.addw(w)                  # close previous word
                w = tword(ii,self.x[ii],self.y[0],self);   # open new word
            else:
                w.addc(ii);                  # add to existing word
        if w is not None:
            self.addw(w)
            
        if len(self.x)>1:
            sws = [x for _, x in sorted(zip(self.x, self.ws), key=lambda pair: pair[0])] # words sorted in ascending x
            for ii in range(len(sws)-1):
                sws[ii].nextw = sws[ii+1]
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
            if self.nsodipodirole == 'line' and (self.tlvlno is not None and self.tlvlno>0):
                # Need to disable sodipodi to change alignment of one line
                # Note that it's impossible to change one line without affecting the others
                self.el.set('sodipodi:role',None);   
                self.xsrc = self.el;
                
            for w in self.ws:
                minx = min([w.pts_ut[ii][0] for ii in range(4)]);
                maxx = max([w.pts_ut[ii][0] for ii in range(4)]);
                
                dxl = [c.dx for c in self.cs];
                if len(dxl)==0: dxl=[0];
                if newanch=='middle':
                    newx = (minx+maxx)/2-dxl[0]/2;
                elif newanch=='end':
                    newx = maxx;
                else:
                    newx = minx-dxl[0];
                
                # dh.debug(min([w.pts_ut[ii][0] for ii in range(4)]))
                # dh.debug(min([w.pts_ut[ii][0] for ii in range(4)]))
                # if w.txt()=='0.4':
                #     dh.debug(w.txt())
                #     dh.debug(GetXY(w.cs[0].loc.el,'x'))
                
                if len(w.cs)>0:
                    self.x[self.cs.index(w.cs[0])] = newx
                    self.xsrc.set('x',' '.join([str(v) for v in self.x]));
                    dh.Set_Style_Comp(w.cs[0].loc.el,'text-anchor',newanch)
                    alignd = {'start': 'start', 'middle': 'center', 'end': 'end'}
                    dh.Set_Style_Comp(w.cs[0].loc.el,'text-align',alignd[newanch]);
                    # dh.debug(self.el.get_id())
                    
                self.anchor = newanch;
                w.x = newx; w.calcprops();
    
    # Update the position everywhere
    def change_pos(self,newx,newy):
        self.x = newx;
        self.y = newy;
        self.xsrc.set('x',' '.join([str(v) for v in newx]))
        self.ysrc.set('y',' '.join([str(v) for v in newy]))
        self.parse_words();
    # def change_d(self,dx,dy)
                
    
# A word (a group of characters with the same assigned anchor)
class tword: 
    def __init__(self,ii,x,y,ln):
        c = ln.cs[ii];
        self.cs  = [c];
        self.iis = [ii]; # index in word
        self.x = x;
        self.y = y;
        self.sf= c.sf; # all letters have the same scale
        self.ln = ln;
        self.transform = ln.transform
        c.w = self;
        self.nextw = None;
    def addc(self,ii):
        c = self.ln.cs[ii];
        self.cs.append(c);
        self.iis.append(ii);
        c.w = self;
    
    # Deletes me from everywhere
    def delw(self):
        for c in reversed(self.cs):
            c.delc();
        if self in self.ln.ws:
            self.ln.ws.remove(self)
            
    # Gets all text
    def txt(self):   
        return ''.join([c.c for c in self.cs])
            
    # Add a new character to the end of the word
    def appendc(self,ncv,ncw,type=None,osw=None):
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
        c.reduction_factor = osw/c.sw  # how much the font was reduced, for subscript/superscript calcs
        if type is not None:
            c.type = type
        c.loc = cloc(c.loc.el,c.loc.tt,c.loc.ind+1) # updated location
        
        # Add to line
        myi = self.ln.cs.index(lc)+1 # insert after last character
        if len(self.ln.x)>0:
            self.ln.x = self.ln.x[0:myi]+[None]+self.ln.x[myi:]
            self.ln.x = self.ln.x[0:len(self.ln.cs)+1]
            if all([v is None for v in self.ln.x[1:]]):
                self.ln.x = [self.ln.x[0]]
            self.ln.xsrc.set('x',' '.join([str(v) for v in self.ln.x]))
            if len(self.ln.x)==1 and self.ln.nsodipodirole=='line': # would re-enable spr
                self.ln.xsrc.set('sodipodi:role',None)
                self.ln.nsodipodirole = None;
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
            self.ln.x[self.ln.cs.index(self.cs[0])] -= deltax
            self.x -= deltax
            self.ln.xsrc.set('x',' '.join([str(v) for v in self.ln.x]));
        self.calcprops()
        
    # Add a new word (possibly from another line) into the current one
    def appendw(self,nw,type):
        # Calculate the number of spaces we need to keep the position constant
        # (still need to adjust for anchors)
        bl2 = (-self.transform).apply_to_point(nw.pts_t[0])
        # br1 = (-self.transform).apply_to_point(self.premerge_br); self.premerge_br = nw.premerge_br
        br1 = self.pts_ut[3];                                      # this is usually more accurate than the premerge
        lc = self.cs[-1]; # last character
        numsp = max(0,round((bl2.x-br1.x)/(lc.sw/self.sf)));
        for ii in range(numsp):
            self.appendc('\u00A0',lc.sw,osw=lc.sw)
        for c in nw.cs:
            c.delc();
            ntype = copy.copy(type)
            otype = dh.Get_Style_Comp(c.sty,'baseline-shift');
            if otype in ['super','sub'] and type=='normal':
                ntype = otype
            self.appendc(c.c,c.cw,type=ntype,osw=c.sw)
        if dh.cascaded_style2(self.ln.xsrc).get('letter-spacing') is not None:
            dh.Set_Style_Comp(self.ln.xsrc,'letter-spacing','0');
    
    # Calculate the properties of a word that depend on its characters       
    def calcprops(self): # calculate properties inherited from characters
        w = self;
        dxl = [c.dx for c in self.cs];
        if len(dxl)==0: dxl=[0];
#        dh.debug(w.txt())
#        dh.debug(dxl)
        if len(w.cs)>0:
            w.ww = sum([c.cw  for c in w.cs])+sum(dxl[1:])*w.sf
            w.fs = max([c.fs          for c in w.cs])
            w.sw = max([c.sw for c in w.cs])
            w.ch = max([c.ch   for c in w.cs])
            # w.dr = max([c.prop.descrh for c in w.cs])
        w.angle = w.ln.angle
        
        if len(w.cs)>0:
            ymin = min([w.y+c.dy-c.ch/w.sf   for c in w.cs]);
            ymax = max([w.y+c.dy             for c in w.cs]);
        else:
            ymin = w.y-w.ch/w.sf; ymax = w.y;
        
        if self.ln.anchor=='middle':
            w.offx = dxl[0]*w.sf/2-w.ww/2;
        elif self.ln.anchor=='end':
            w.offx = -w.ww;
        else:
            w.offx = dxl[0]*w.sf;
            
        w.pts_ut = [Vector2d(w.x + w.offx/w.sf,      ymax), Vector2d(w.x+ w.offx/w.sf,       ymin),\
                    Vector2d(w.x+(w.ww+w.offx)/w.sf, ymin), Vector2d(w.x+(w.ww+w.offx)/w.sf, ymax)];
            # untransformed pts: bottom-left, top-left (cap height), top-right, bottom right
        w.pts_t=[];
        for p in w.pts_ut:
            w.pts_t.append(w.transform.apply_to_point(p))
        w.bb = bbox([min([p.x for p in w.pts_t]),\
                min([p.y for p in w.pts_t]),\
                max([p.x for p in w.pts_t])-min([p.x for p in w.pts_t]),\
                max([p.y for p in w.pts_t])-min([p.y for p in w.pts_t])]);
            
        
        
# A single character and its style
class tchar:
    def __init__(self, c,fs,sf,prop,sty,nsty,loc):
        self.c = c;
        self.fs = fs;     # nominal font size
        self.sf = sf;     # how much it is scaled to get to the actual width
        # self.prop = prop;
        self.cw = prop.charw;     # actual character width in user units
        self.sty  = sty;  # actual style
        self.nsty = nsty; # normalized style
        self.nstyc = dh.Set_Style_Comp2(nsty,'fill',dh.Get_Style_Comp(sty,'fill')) # with color
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
        self.dxloc = None;      # get later
        self.dyloc = None;      # get later
        
    def delc(self): # deletes me from document (and from my word/line)
        # Delete from document
        if self.loc.tt=='text':
            self.loc.el.text = del2(self.loc.el.text,self.loc.ind)
        else:
            self.loc.el.tail = del2(self.loc.el.tail,self.loc.ind)
        myi = self.ln.cs.index(self) # index in line
        if len(self.ln.x)>1:
            if myi<len(self.ln.x):
                # oldx = self.ln.x
                self.ln.x = del2(self.ln.x,myi)
                self.ln.x = self.ln.x[0:len(self.ln.cs)-1]
                if self.ln.x==[]: self.ln.xsrc.set('x',None);
                else:             self.ln.xsrc.set('x',' '.join([str(v) for v in self.ln.x]))
                if len(self.ln.x)==1 and self.ln.nsodipodirole=='line': # would enable inheritance
                    self.ln.xsrc.set('sodipodi:role',None)
                    self.ln.nsodipodirole = None;
        # Delete from line
        for ii in range(myi+1,len(self.ln.cs)):         # need to decrement index of subsequent objects with the same parent
            ca = self.ln.cs[ii];
            if ca.loc.tt==self.loc.tt and ca.loc.el==self.loc.el:
                ca.loc.ind -= 1
            if ca.w is not None:
                i2 = ca.w.cs.index(ca)
                ca.w.iis[i2] -= 1
        self.ln.cs = del2(self.ln.cs,myi)
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
        # Delete from dx/dy (not currently used because you also need to detect sodipodi:role lines before it...)
        # if self.dxloc is not None:
        #     olddx = [float(v) for v in self.dxloc.el.get('dx').split()]
        #     newdx = del2(olddx,self.dxloc.ind);
        #     newdx = ' '.join([str(v) for v in newdx])
        #     self.dxloc.el.set('dx',newdx);
        #     dh.debug(self.dxloc.el.get('dx'))
        # if self.dyloc is not None:
        #     olddy = [float(v) for v in self.dyloc.el.get('dy').split()]
        #     newdy = del2(olddy,self.dyloc.ind);
        #     newdy = ' '.join([str(v) for v in newdy])
        #     self.dyloc.el.set('dy',newdy);
        
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
               (abs(self.yc - bb2.yc) * 2 < (self.h + bb2.h))

def del2(x,ind): # deletes an index from a list
    return x[:ind]+x[ind+1:]

# A class representing the properties of a single character
class cprop():
    def __init__(self, char,cw,sw,xo,ch,dr):
        self.char = char;
        self.charw = cw;    # character width
        self.spacew = sw;   # space width
        self.xoffset = xo;  # x offset from anchor
        self.caph = ch;     # cap height
        self.descrh = dr;   # descender height
    def __mul__(self, scl):
        return cprop(self.char,self.charw*scl,self.spacew*scl,self.xoffset*scl,self.caph*scl,self.descrh*scl)
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
        self.ctable, self.bbs = self.measure_character_widths(els)
        
    def get_prop(self,char,sty):
        if sty in list(self.ctable.keys()):
            matches = [jj for jj in range(len(self.ctable[sty])) if self.ctable[sty][jj].char==char]
            if len(matches)>0:
                return self.ctable[sty][matches[0]]
            else:
                dh.debug('No character matches!');
                dh.debug('Character: '+char)
                dh.debug('Style: '+sty);
                dh.debug('Existing characters: '+str(list([self.ctable[sty][jj].char for jj in range(len(self.ctable[sty]))])))
                quit()
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
            ctable[sty] = list(set(ctable[sty]+['\u00A0']))
        return ctable
    
    def measure_character_widths(self,els):
        # Measure the width of all characters of a given style by generating copies with two and three extra spaces.
        # We take the difference to get the width of a space, then subtract that to get the character's full width.
        # This includes any spaces between characters as well.
        # The width will be the width of a character whose composed font size is 1 uu.
        ct = self.generate_character_table(els,None);
        docscale = self.caller.svg.scale;
        
        def Make_Character(c,sty):
            nt = TextElement();
            nt.text = c;
            nt.set('style',sty)
            self.caller.svg.append(nt);
            # nt.get_id(); # assign id now
            dh.get_id2(nt); # assign id now
            return nt
                            
        for s in list(ct.keys()):
            for ii in range(len(ct[s])):
                t = Make_Character(ct[s][ii]+'\u00A0\u00A0',s); # character with 2 nb spaces (last space not rendered)
                ct[s][ii] = [ct[s][ii],t,t.get_id()]; 
            t = Make_Character('pI\u00A0\u00A0',s);              # pI with 2 nb spaces
            ct[s].append([ct[s][ii],t,t.get_id()]);             
            t = Make_Character('pI\u00A0\u00A0\u00A0',s);        # pI with 3 nb spaces
            ct[s].append([ct[s][ii],t,t.get_id()]); 
            # We add pI as test characters because p gives the font's descender (how much the tail descends)
            # and I gives its cap height (how tall capital letters are).
            
        nbb = dh.Get_Bounding_Boxes(self.caller,True);  
        for s in list(ct.keys()):
            for ii in range(len(ct[s])):
                # dh.debug(nbb)
                bb=nbb[ct[s][ii][2]]
                wdth = bb[0]+bb[2]
                caphgt = -bb[1]
                bbstrt = bb[0]
                dscnd = bb[1]+bb[3]
                ct[s][ii][1].delete();
                ct[s][ii] = [ct[s][ii][0],wdth,bbstrt,caphgt,dscnd]
        for s in list(ct.keys()):
            Nl = len(ct[s])-2;
            sw = ct[s][-1][1] - ct[s][-2][1] # space width is the difference in widths of the last two
            ch = ct[s][-1][3]                # cap height
            dr = ct[s][-1][4]                # descender
            for ii in range(Nl):
                cw = ct[s][ii][1] - sw;  # character width (full, including extra space on each side)
                xo = ct[s][ii][2]        # x offset: how far it starts from the left anchor
                if ct[s][ii][0]==' ':
                    cw = sw;
                    xo = 0;
                ct[s][ii] = cprop(ct[s][ii][0],cw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale);
                # Because a nominal 1 px font is docscale px tall, we need to divide by the docscale to get the true width
            ct[s] = ct[s][0:Nl]
            # ct[s].append(cprop(' ',sw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale));
            # ct[s].append(cprop('\u00A0',sw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale));
        return ct, nbb
    
    
    # For generating test characters, we want to normalize the style so that we don't waste time
    # generating a bunch of identical characters whose font-sizes are different. A style is generated
    # with a 1px font-size, and only with presentation attributes that affect character shape.
    textshapeatt = ['font-family','font-size-adjust','font-stretch',\
                    'font-style','font-variant','font-weight','stroke','stroke-width',\
                    'text-decoration','text-rendering','font-size']
    @staticmethod
    def normalize_style(sty):
        sty  = Style(sty); stykeys = list(sty.keys());
        sty2 = Style('')
        for a in Character_Table.textshapeatt:
            if a in stykeys:
                styv = sty.get(a);
                # if styv is not None and styv.lower()=='none':  
                #     styv=None # actually don't do this because 'none' might be overriding inherited styles
                if styv is not None:
                    sty2[a]=styv;
        
        sty2['font-size']='1px'
        if sty2.get('stroke') is None:
            sty2['stroke-width']=None;
        if sty2.get('font-family') is not None:
            sty2['font-family']=','.join([v.strip().strip('\'') for v in sty2['font-family'].split(',')]); # strip spaces b/t styles

        tmp = Style('');
        for k in sorted(sty2.keys()): # be sure key order is alphabetical
            tmp[k]=sty2[k];
        sty2 = tmp;

        return str(sty2)