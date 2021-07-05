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
        val = [None];
    else:             
        val = [float(x) for x in val.split()];
    return val

# A text element that has been parsed into a list of lines
class LineList():
    def __init__(self, el, ctable,debug=False):
        self.ctable = ctable
        self.lns = self.Parse_Lines(el,debug=debug);
        self.textel = el;
        if self.lns is not None:
            for ln in self.lns:
                ln.ll = self;
    def txt(self):
        return [v.txt() for v in self.lns]
        
    # Seperate a text element into a group of lines
    def Parse_Lines(self,el,lns=None,debug=False):
        tlvlcall = (lns is None);
        # sty = el.composed_style();
        sty = dh.selected_style_local(el);
        fs,sf,ct,ang = dh.Get_Composed_Width(el,'font-size',4);
        nsty=Character_Table.normalize_style(sty);
        tv = el.text;
        
        xv = GetXY(el,'x'); xsrc = el;
        yv = GetXY(el,'y'); ysrc = el;
        
        # Notes on sodipodi:role line
        # If a Tspan has sodipodi:role set to line, its position is inherited based on the previous line.
        # The x value is taken from the previous line's x value.
        # The y value is taken by adding [something] to the previous y value.
        # However, inheritance is disabled by the presence of multiple x values or multiple y values.
        # If sodipodi:role is not line, its anchoring/alignment will be inherited from the previous line.
        
        # Detect if inheriting position
        nspr = el.get('sodipodi:role');
        # dh.debug(el.get('x'))
        inheritpos = (nspr=='line' and len(xv)<=1) or (xv[0] is None)
        
        # Determine if new line
        newline = False;            
        if isinstance(el,TextElement):
            newline = True
        elif isinstance(el,Tspan) and isinstance(el.getparent(),TextElement):
            myi = el.getparent().getchildren().index(el)
            if inheritpos and myi==0: # if the first Tspan inherits, continue previous line
                newline = False
            else:
                newline = True;
        
        # dh.debug(el.get_id() + str(inheritpos))
        
        if debug:
            dh.debug(el.get_id())
            dh.debug(tv)
            dh.debug(newline)
            dh.debug(fs)
            # dh.debug(inheritpos)
        
        if newline:
            if lns is None:  
                lns=[];
            elif inheritpos:                # if inheriting
                if len(lns)==0 or len(lns[-1].x)==0: return None
                else:
                    xv = [lns[-1].x[0]]; 
                    xsrc = lns[-1].xsrc;
            anch = sty.get('text-anchor') 
            if len(lns)!=0 and nspr!='line':
                anch = lns[-1].anchor    # non-spr lines inherit the previous line's anchor
            lns.append(tline(xv,yv,inheritpos,nspr,anch,ct,ang,el,xsrc))
        else:
            if lns is not None:   # if we're continuing, make sure we have a valid x and y
                if lns[-1].x[0] is None: lns[-1].x = xv; lns[-1].xsrc = xsrc;
                if lns[-1].y[0] is None: lns[-1].y = yv
        
        
        # if debug:
        #     dh.debug(tv)
        
        ctable = self.ctable    
        if tv is not None and tv!='' and len(tv)>0:
            # if debug:
            #     dh.debug(tv)
            for ii in range(len(tv)):
                myi = [jj for jj in range(len(ctable[nsty])) if ctable[nsty][jj].char==tv[ii]][0]
                if fs is None: return None # bail if there is text without font
                prop = ctable[nsty][myi]*fs;
                lns[-1].addc(tchar(tv[ii],fs,sf,prop,sty,nsty,cloc(el,'text',ii)));
        
        ks = el.getchildren();
        # if debug:
        #     dh.debug(ks)
        for k in ks:
            lns = self.Parse_Lines(k,lns,debug=debug);
            tv = k.tail;
            if tv is not None and tv!='':
                for ii in range(len(tv)):
                    myi = [jj for jj in range(len(ctable[nsty])) if ctable[nsty][jj].char==tv[ii]][0]
                    if fs is None: return None # bail if there is text without font
                    prop = ctable[nsty][myi]*fs;
                    lns[-1].addc(tchar(tv[ii],fs,sf,prop,sty,nsty,cloc(k,'tail',ii)));
                    
        if tlvlcall: # finished recursing
            if lns is not None:
                for ln in reversed(lns):                
                    ln.parse_words()
                    if len(ln.cs)==0:
                        lns.remove(ln); # prune empty lines
        return lns
    
    # For debugging only: make a rectange at all of the line's words' nominal bboxes
    def Position_Check(self):
        if len(self.lns)>0:
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
    def __init__(self, x, y, inheritpos, nspr, anch, xform,ang,el,xsrc):
        self.x = x;
        self.y = y;
        self.inheritpos = inheritpos;    # inheriting position
        self.nsodipodirole = nspr;  # nominal value
        self.anchor = anch
        self.cs = [];
        self.ws = [];
        self.transform = xform;
        self.angle = ang;
        self.xsrc = xsrc; # element where we derive our x value
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
    def dell(self): # deletes the whole line
        for c in reversed(self.cs):
            c.delc();
        if self.ll is not None:
            self.ll.lns.remove(self)
        self.ll = None;
    def txt(self):   
        return ''.join([c.c for c in self.cs])
                
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
            self.appendc(c.c,c.cw,type=ntype,osw=c.sw)
    
    # Calculate the properties of a word that depend on its characters       
    def calcprops(self): # calculate properties inherited from characters
        w = self;
        if len(w.cs)>0:
            w.ww = sum([c.cw  for c in w.cs])
            w.fs = max([c.fs          for c in w.cs])
            w.sw = max([c.sw for c in w.cs])
            w.ch = max([c.ch   for c in w.cs])
            # w.dr = max([c.prop.descrh for c in w.cs])
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
        # w.txt = ''.join([c.c for c in w.cs])
        
        
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
        self.ch = prop.caph;     # cap height (height of flat capitals)
        # self.dr = dr;     # descender (length of p/q descender))
        self.sw = prop.spacew;     # space width for style
        self.ln = None;   # my line (to be assigned)
        self.w  = None;   # my word (to be assigned)
        self.type=None;   # 'normal','super', or 'sub' (to be assigned)
        self.ofs = fs;    # original character width (never changed, even if character is updated later)
    def delc(self): # deletes me from document (and from my word/line)
        # Delete from document
        if self.loc.tt=='text':
            self.loc.el.text = del2(self.loc.el.text,self.loc.ind)
        else:
            self.loc.el.tail = del2(self.loc.el.tail,self.loc.ind)
        myi = self.ln.cs.index(self) # index in line
        if len(self.ln.x)>0:
            if myi<len(self.ln.x):
                oldx = self.ln.x
                self.ln.x = del2(self.ln.x,myi)
                self.ln.x = self.ln.x[0:len(self.ln.cs)-1]
                if self.ln.x==[]: self.ln.xsrc.set('x',None)
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
        
    def makesubsuper(self,sz=65):
        t = Tspan();
        t.text = self.c;
        if self.type=='super':
            t.style = 'font-size:'+str(sz)+'%;baseline-shift:super';
        else: #sub
            t.style = 'font-size:'+str(sz)+'%;baseline-shift:sub';
        
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
# A class indicating a single character's location
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
                ct[s][ii] = cprop(ct[s][ii][0],cw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale);
                # Because a nominal 1 px font is docscale px tall, we need to divide by the docscale to get the true width
            ct[s] = ct[s][0:Nl]
            # ct[s].append(cprop(' ',sw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale));
            # ct[s].append(cprop('\u00A0',sw/docscale,sw/docscale,xo/docscale,ch/docscale,dr/docscale));
        return ct, nbb
    
    @staticmethod
    # Return a style that doesn't have extraneous information
    def normalize_style(sty):
        sty = dh.Set_Style_Comp2(str(sty),'font-size','1px');
        sty = dh.Set_Style_Comp2(sty,'fill',None)         
        sty = dh.Set_Style_Comp2(sty,'text-anchor',None)
        sty = dh.Set_Style_Comp2(sty,'baseline-shift',None)
        sty = dh.Set_Style_Comp2(sty,'line-height',None)
        sty = dh.Set_Style_Comp2(sty,'writing-mode',None)
        strk = dh.Get_Style_Comp(sty,'stroke');
        if strk is None or strk.lower()=='none':
            sty = dh.Set_Style_Comp2(sty,'stroke',None)
            sty = dh.Set_Style_Comp2(sty,'stroke-width',None)
        return sty