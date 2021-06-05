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
from inkex import (
    TextElement, FlowRoot, FlowPara, Tspan, TextPath ,Vector2d, Rectangle)

def GetXY(el,xy):
    if xy=='y':
        val = el.get('y');
    else:
        val = el.get('x');
    if val is None:   
        val = [None]
    else:             
        val = [float(x) for x in val.split()];
    return val

# A text element that has been parsed into a list of lines
class LineList():
    def __init__(self, el, ctable):
        self.ctable = ctable
        self.lns = self.Parse_Lines(el);
        self.parent = el;
        
    # Seperate a text element into a group of lines
    def Parse_Lines(self,el,lns=None):
        tlvlcall = (lns is None);
        # sty = el.composed_style();
        sty = dh.selected_style_local(el);
        fs,sf,ct,ang = dh.Get_Composed_Width(el,'font-size',4);
        nsty=Character_Table.normalize_style(sty);
        tv = el.text;
        
        xv = GetXY(el,'x')
        yv = GetXY(el,'y')
        # myx = el.get('x');
        # myy = el.get('y');
        # if myx is None:   xv = [None]
        # else:             xv = [float(x) for x in myx.split()];
        # if myy is None:   yv = [None]
        # else:             yv = [float(y) for y in myy.split()];
        
        # Detect effective sodipodi:role line (overridden by multiple x values)
        nspr = el.get('sodipodi:role'); spr = False;
        if nspr=='line':
            if len(xv)==0 or xv[0] is None or len(xv)<=1:
                spr = True;
        
        # Determine if new line
        myi = el.getparent().getchildren().index(el)
        newline = (isinstance(el,Tspan) and isinstance(el.getparent(),TextElement)) or isinstance(el,TextElement); # new line if a top-level tspan
        if newline and spr and myi==0: # if sodipodi role is on and it's the first, consider part of previous line
            newline = False
        if newline:
            if lns is None:  
                lns=[];
            elif spr:                    # if spr is enabled, inherit x from previous line
                xv = [lns[-1].x[0]]; 
            anch = sty.get('text-anchor')    
            if len(lns)!=0 and nspr!='line':
                anch = lns[-1].anchor    # non-spr lines inherit the previous line's anchor
            
            # If x is still none, hopefully parent has it...
            if xv[0] is None:
                xv = GetXY(el.getparent(),'x');
                el.set('x',' '.join([str(v) for v in xv]))
            if yv[0] is None:
                yv = GetXY(el.getparent(),'y');
                el.set('y',' '.join([str(v) for v in yv]))
            lns.append(tline(xv,yv,spr,nspr,anch,ct,ang,el))
        else:
            if lns is not None:   # if we're continuing, make sure we have a valid x and y
                if len(lns[-1].x)==0 or lns[-1].x[0] is None: lns[-1].x = xv
                if len(lns[-1].y)==0 or lns[-1].y[0] is None: lns[-1].y = yv
            
        ctable = self.ctable    
        if tv is not None and tv!='':
            for ii in range(len(tv)):
                myi = [jj for jj in range(len(ctable[nsty])) if ctable[nsty][jj][0]==tv[ii]][0]
                if fs is None: return None # bail if there is text without font
                cw = ctable[nsty][myi][1]*fs;
                sw = ctable[nsty][myi][2]*fs;
                ch = ctable[nsty][myi][4]*fs;
                dr = ctable[nsty][myi][5]*fs;
                lns[-1].addc(tchar(tv[ii],fs,sf,cw,sty,nsty,[el,'text',ii],ch,dr,sw));
        
        ks = el.getchildren();
        for k in ks:
            lns = self.Parse_Lines(k,lns);
            tv = k.tail;
            if tv is not None and tv!='':
                for ii in range(len(tv)):
                    myi = [jj for jj in range(len(ctable[nsty])) if ctable[nsty][jj][0]==tv[ii]][0]
                    if fs is None: return None # bail if there is text without font
                    cw = ctable[nsty][myi][1]*fs;
                    sw = ctable[nsty][myi][2]*fs;
                    ch = ctable[nsty][myi][4]*fs;
                    dr = ctable[nsty][myi][5]*fs;
                    lns[-1].addc(tchar(tv[ii],fs,sf,cw,sty,nsty,[k,'tail',ii],ch,dr,sw));
                    
        if tlvlcall: # finished recursing
            if lns is not None:
                for ln in lns:                
                    ln.parse_words()
        return lns
    
    # For debugging only: make a rectange at all of the line's words' nominal bboxes
    def Position_Check(self):
        if len(self.lns)>0:
            svg = dh.get_parent_svg(self.lns[0].prt)
            xs = []; ys = []; x2s = []; y2s = [];
            for ln in self.lns:          
                for w in ln.ws:
                    ap  = w.pts_t[0];
                    ap2 = w.pts_t[2];  
                        
                    xs.append(ap.x); #dh.debug(ap.x/self.svg.scale)
                    ys.append(ap.y);
                    x2s.append(ap2.x);
                    y2s.append(ap2.y);
                
            for ii in range(len(xs)):
                r = Rectangle();
                r.set('x',min(xs[ii],x2s[ii]))
                r.set('y',min(ys[ii],y2s[ii]))
                r.set('height',abs(ys[ii]-y2s[ii]))
                r.set('width', abs(xs[ii]-x2s[ii]))
                r.set('style','fill-opacity:0.5')
                svg.append(r)
    
# A single line, which represents a list of characters. Typically a top-level Tspan or TextElement.
# This is further subdivided into a list of words
class tline:
    def __init__(self, x, y, spr, nspr, anch, xform,ang,prt):
        self.x = x;
        self.y = y;
        self.sodipodirole = spr;    # effective sodipodirole
        self.nsodipodirole = nspr;  # nominal value
        self.anchor = anch
        self.cs = [];
        self.ws = [];
        self.transform = xform;
        self.angle = ang;
        self.prt = prt;
    def addc(self,c):
        self.cs.append(c)
        c.ln = self;
    def insertc(self,c,ec): # insert below
        self.cs = self.cs[0:ec]+[c]+self.cs[ec:]
        c.ln = self;
    def addw(self,w): # Add a complete word and calculate its properties
        self.ws.append(w)
        w.calcprops();
        w.prt = self.prt
    def parse_words(self):
        w=None;
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
        
    # Add a new character to the end of the word
    def appendc(self,ncv,ncw,type=None,osw=None):
        # Add to document
        lc = self.cs[-1]; # last character
        myi = lc.loc[2]+1; # insert after last character
        if lc.loc[1]=='text':
            lc.loc[0].text = lc.loc[0].text[0:myi]+ncv+lc.loc[0].text[myi:]
        else:
            lc.loc[0].tail = lc.loc[0].tail[0:myi]+ncv+lc.loc[0].tail[myi:]
        
        # Make new character as a copy of the last one of the current word
        c = copy.copy(lc)
        c.c  = ncv
        c.cw = ncw
        c.reduction_factor = osw/c.sw  # how much the font was reduced, for subscript/superscript calcs
        if type is not None:
            c.type = type
        c.loc = [c.loc[0],c.loc[1],c.loc[2]+1] # updated location
        
        # Add to line
        myi = self.ln.cs.index(lc)+1 # insert after last character
        if len(self.ln.x)>0:
            self.ln.x = self.ln.x[0:myi]+[None]+self.ln.x[myi:]
            self.ln.x = self.ln.x[0:len(self.ln.cs)+1]
            if all([v is None for v in self.ln.x[1:]]):
                self.ln.x = [self.ln.x[0]]
            self.ln.prt.set('x',' '.join([str(v) for v in self.ln.x]))
            if len(self.ln.x)==1 and self.ln.nsodipodirole=='line': # would re-enable spr
                self.ln.prt.set('sodipodi:role',None)
                self.ln.nsodipodirole = None;
        self.ln.insertc(c,myi)
        for ii in range(myi+1,len(self.ln.cs)):        # need to increment index of subsequent objects with the same parent
            ca = self.ln.cs[ii];
            if ca.loc[1]==c.loc[1] and ca.loc[0]==c.loc[0]:
                ca.loc[2] += 1
            if ca.w is not None:
                i2 = ca.w.cs.index(ca)
                ca.w.iis[i2] += 1
        # Add to word, recalculate properties
        self.addc(myi)
        self.calcprops()
        
    # Add a new word (possibly from another line) into the current one
    def appendw(self,nw,type):
        # Calculate the number of spaces we need to keep the position constant
        # (still need to adjust for anchors)
        bl2 = (-self.transform).apply_to_point(nw.pts_t[0])
        br1 = self.pts_ut[3];
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
#            dh.debug(ntype)
            self.appendc(c.c,c.cw,type=ntype,osw=c.sw)
    
    # Calculate the properties of a word that depend on its characters       
    def calcprops(self): # calculate properties inherited from characters
        w = self;
        if len(w.cs)>0:
            w.ww = sum([c.cw for c in w.cs])
            w.fs = max([c.fs for c in w.cs])
            w.sw = max([c.sw for c in w.cs])
            w.ch = max([c.ch for c in w.cs])
            w.dr = max([c.dr for c in w.cs])
        w.angle = w.ln.angle
        
        w.offx = 0;
        if self.ln.anchor=='middle':
            w.offx = -w.ww/2;
        elif self.ln.anchor=='end':
            w.offx = -w.ww;
        w.pts_ut = [Vector2d(w.x + w.offx/w.sf, w.y), Vector2d(w.x+ w.offx/w.sf, w.y-w.ch/w.sf),\
                    Vector2d(w.x+(w.ww+w.offx)/w.sf, w.y-w.ch/w.sf), Vector2d(w.x+(w.ww+w.offx)/w.sf, w.y)];
            # untransformed pts: bottom-left, top-left (cap height), top-right, bottom right
        w.pts_t=[];
        for p in w.pts_ut:
            w.pts_t.append(w.transform.apply_to_point(p))
        w.bb = bbox([min([p.x for p in w.pts_t]),\
                min([p.y for p in w.pts_t]),\
                max([p.x for p in w.pts_t])-min([p.x for p in w.pts_t]),\
                max([p.y for p in w.pts_t])-min([p.y for p in w.pts_t])]);
                # bounding box that begins at the anchor and stops at the cap height
        w.txt = ''.join([c.c for c in w.cs])
        
        
# A single character and its style
class tchar:
    def __init__(self, c,fs,sf,cw,sty,nsty,loc,ch,dr,sw):
        self.c = c;
        self.fs = fs;     # nominal font size
        self.sf = sf;     # how much it is scaled to get to the actual width
        self.cw = cw;     # actual character width in user units
        self.sty  = sty;  # actual style
        self.nsty = nsty; # normalized style
        self.nstyc = dh.Set_Style_Comp2(nsty,'fill',dh.Get_Style_Comp(sty,'fill')) # with color
        self.loc = loc;   # true location: [parent, 'text' or 'tail', index]
        self.ch = ch;     # cap height (height of flat capitals)
        self.dr = dr;     # descender (length of p/q descender))
        self.sw = sw;     # space width for style
        self.ln = None;   # my line (to be assigned)
        self.w  = None;   # my word (to be assigned)
        self.type=None;   # 'normal','super', or 'sub' (to be assigned)
        self.ofs = fs;    # original character width (never changed, even if character is updated later)
    def delc(self): # deletes me from document (and from my word/line)
        # Delete from document
        if self.loc[1]=='text':
            self.loc[0].text = del2(self.loc[0].text,self.loc[2])
        else:
            self.loc[0].tail = del2(self.loc[0].tail,self.loc[2])
        myi = self.ln.cs.index(self) # index in line
        if len(self.ln.x)>0:
            if myi<len(self.ln.x):
                self.ln.x = del2(self.ln.x,myi)
                self.ln.x = self.ln.x[0:len(self.ln.cs)-1]
                self.ln.prt.set('x',' '.join([str(v) for v in self.ln.x]))
                if len(self.ln.x)==1 and self.ln.nsodipodirole=='line': # would re-enable spr
                    self.ln.prt.set('sodipodi:role',None)
                    self.ln.nsodipodirole = None;
        # Delete from line
        for ii in range(myi+1,len(self.ln.cs)):         # need to decrement index of subsequent objects with the same parent
            ca = self.ln.cs[ii];
            if ca.loc[1]==self.loc[1] and ca.loc[0]==self.loc[0]:
                ca.loc[2] -= 1
            if ca.w is not None:
                i2 = ca.w.cs.index(ca)
                ca.w.iis[i2] -= 1
        self.ln.cs = del2(self.ln.cs,myi)
        self.ln = None
        # Delete from word
        myi = self.w.cs.index(self)
        self.w.cs = del2(self.w.cs ,myi)
        self.w.iis= del2(self.w.iis,myi)
        self.w.calcprops()
        self.w = None
        
    def makesubsuper(self,sz=65):
        t = Tspan();
        t.text = self.c;
        if self.type=='super':
            t.style = 'font-size:'+str(sz)+'%;baseline-shift:super';
        else: #sub
            t.style = 'font-size:'+str(sz)+'%;baseline-shift:sub';
        
        prt = self.loc[0];
        if self.loc[1]=='text':
            tbefore = prt.text[0:self.loc[2]];
            tafter  = prt.text[self.loc[2]+1:];
            prt.text = tbefore;
            prt.insert(0,t);
            t.tail = tafter;
        else:
            tbefore = prt.tail[0:self.loc[2]];
            tafter  = prt.tail[self.loc[2]+1:];
            prt.tail = tbefore
            gp =prt.getparent();                # parent is a Tspan, so insert it into the grandparent
            pi = (gp.getchildren()).index(prt);   
            gp.insert(pi+1,t); # above the parent
            t.tail =  tafter
            
        myi = self.ln.cs.index(self)
        for ii in range(myi+1,len(self.ln.cs)):  # for characters after, update location
            ca = self.ln.cs[ii];
            ca.loc = [t,'tail',ii-myi-1]
        self.loc = [t,'text',0]                  # update my own location
    

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

# A class representing the properties of a collection of characters
class Character_Table():
    def __init__(self, els,caller):
        self.caller = caller;
        self.ctable, self.bbs = self.measure_character_widths(els)

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
                    if sty in list(ctable.keys()):
                        ctable[sty] = list(set(ctable[sty]+list(el.tail)));
                    else:
                        ctable[sty] = list(set(list(el.tail)));
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
            nt.get_id(); # assign id now
            return nt
                            
        for s in list(ct.keys()):
            for ii in range(len(ct[s])):
                t = Make_Character(ct[s][ii]+'\u00A0\u00A0',s); # character with 2 nb spaces (last space not rendered)
                ct[s][ii] = [ct[s][ii],t,t.get_id()]; 
            t = Make_Character('pI\u00A0\u00A0',s);              # pI with 2 nb spaces
            ct[s].append([ct[s][ii],t,t.get_id()]);             
            t = Make_Character('pI\u00A0\u00A0\u00A0',s);        # pI with 3 nb spaces
            ct[s].append([ct[s][ii],t,t.get_id()]); 
            
        nbb = dh.Get_Bounding_Boxes(self.caller,True);  
        for s in list(ct.keys()):
            for ii in range(len(ct[s])):
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
                ct[s][ii] = [ct[s][ii][0],cw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale];
                # Because a nominal 1 px font is docscale px tall, we need to divide by the docscale to get the true width
            ct[s] = ct[s][0:Nl]
        return ct, nbb
    
    @staticmethod
    def normalize_style(sty):
        sty = dh.Set_Style_Comp2(str(sty),'font-size','1px');
        sty = dh.Set_Style_Comp2(sty,'fill',None)         
        sty = dh.Set_Style_Comp2(sty,'text-anchor',None)
        sty = dh.Set_Style_Comp2(sty,'baseline-shift',None)
        strk = dh.Get_Style_Comp(sty,'stroke');
        if strk is None or strk.lower()=='none':
            sty = dh.Set_Style_Comp2(sty,'stroke',None)
            sty = dh.Set_Style_Comp2(sty,'stroke-width',None)
        return sty