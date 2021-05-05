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

import inkex
from inkex import (
    TextElement, FlowRoot, FlowPara, Tspan, TextPath, Rectangle, \
        addNS, Transform, Style, ClipPath, Use, NamedView, Defs, \
        Metadata, ForeignObject, Vector2d, Path, Line, PathElement,command,\
        SvgDocumentElement,Image,Group,Polyline,Anchor,Switch,ShapeElement)
import simpletransform
import math
from applytransform_mod import ApplyTransform
import lxml
from lxml import etree  

It = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]);

def inkscape_editable(el):
    ks=el.getchildren();
    for k in ks:
        if isinstance(k, (Tspan,TextElement)):
            inkscape_editable(k)
    if isinstance(el,TextElement):
        el.set('xml:space','preserve')      # enable so we can add spaces
    elif isinstance(el,Tspan):
        if len(el.getparent().getchildren())==1: # only child
            tx = el.get('x'); ty=el.get('y');
            myp = el.getparent();
            myp.set('x',tx)      # enabling sodipodi causes it to move to the parent's x and y
            myp.set('y',ty)
            el.set('sodipodi:role','line'); # reenable sodipodi so we can insert returns
#            Set_Style_Comp(el,'text-anchor','middle');
#            Set_Style_Comp(el,'text-align','center') # one day...
#            Set_Style_Comp(myp,'text-anchor','middle');
#            Set_Style_Comp(myp,'text-align','center') # one day...
        
    

def split_distant(el,ctable):
    # In PDFs, distant text is often merged together into a single word whose letters are positioned.
    # This makes it hard to modify / adjust it. This splits text separated by more than 1.5 spaces.
    # Recursively run on children first
#    oldsodipodi = el.get('sodipodi:role');
    el.set('sodipodi:role',None);
    ks=el.getchildren();
    newtxt = [];
    for k in ks:
        if isinstance(k, (Tspan,TextElement)):
            newtxt += split_distant(k,ctable);
    myx = el.get('x');
    if myx is not None:#not(myx==None):
        myx = myx.split();
        myx =[float(x) for x in myx];
        if len(myx)>1:
            docscale = get_parent_svg(el).scale;
            sty = el.composed_style();
            fs = float(sty.get('font-size').strip('px'));
            sty = Set_Style_Comp2(str(sty),'font-size','1px');
            sty = Set_Style_Comp2(sty,'fill','#000000')      
            stxt = [x for _, x in sorted(zip(myx, el.text), key=lambda pair: pair[0])] # text sorted in ascending x
            sx   = [x for _, x in sorted(zip(myx, myx)    , key=lambda pair: pair[0])] # x sorted in ascending x
            stxt = "".join(stxt) # back to string
            
            starti = 0;
            for ii in range(1,min(len(sx),len(stxt))):
                myi = [jj for jj in range(len(ctable[sty])) if ctable[sty][jj][0]==stxt[ii-1]][0]
                sw = ctable[sty][myi][2]/docscale*fs
                cw = ctable[sty][myi][1]/docscale*fs
                if abs(sx[ii]-sx[ii-1])>=1.5*sw+cw:
                    word = stxt[starti:ii]
                    ts = el.duplicate();
                    ts.text = word;
                    ts.set('x',' '.join(str(x) for x in sx[starti:ii]));
                    ts.set('y',el.get('y'));
                    el.getparent().append(ts);
                    starti = ii;
                    newtxt.append(ts);
            word = stxt[starti:]
            ts = el.duplicate();
            ts.text = word;
            ts.set('x',' '.join(str(x) for x in sx[starti:]));
            ts.set('y',el.get('y'));
            newtxt.append(ts);
            
            el.getparent().append(ts);
            el.delete();
    return newtxt

def pop_tspans(el):
    # Pop out text from different tspans
    el.set('sodipodi:role',None);
    ks=el.getchildren();
    ks=[t for t in ks if isinstance(t, Tspan)]; # ks=[t for t in ks if t.typename=='Tspan'];
    node_index = list(el.getparent()).index(el);
    newtxt = [];
    for k in ks:
        k.style = k.composed_style();
        k.set('sodipodi:role',None)
        el.getparent().insert(node_index,k); # pop everything out   
    for k in ks:
        dp = el.duplicate();             # make dupes of the empty
        dp.insert(0,k)                   # fill with individual tspans
        newtxt.append(dp)
    if (el.getchildren()==None or len(el.getchildren())==0) and (el.text==None or len(el.text)==0):
        # original now empty, safe to delete
        el.delete();
    return newtxt

def generate_character_table(els,ctable):
    if isinstance(els,list):
        for el in els:
            ctable = generate_character_table(el,ctable);
    else:
        el=els;
        ks=el.getchildren();
        for k in ks:
            ctable = generate_character_table(k,ctable);
                
        if ctable is None:
            ctable = dict();
        if isinstance(el,(TextElement,Tspan)) and el.getparent() is not None: # textelements not deleted
            if el.text is not None:
                sty = str(el.composed_style());
                sty = Set_Style_Comp2(sty,'font-size','1px') # so we don't have to check too many styles, set sizes and color to be identical
                sty = Set_Style_Comp2(sty,'fill','#000000')    
                if sty in list(ctable.keys()):
                    ctable[sty] = list(set(ctable[sty]+list(el.text)));
                else:
                    ctable[sty] = list(set(list(el.text)));
    return ctable

def measure_character_widths(els,slf):
    # Measure the width of all characters of a given style by generating copies with two and three extra spaces
    # We take the difference to get the width of a space, then subtract that to get the character's full width
    # This includes any spaces between characters as well
    ct = generate_character_table(els,None);
    
    def Make_Character(c,sty):
        nt = TextElement();
        nt.text = c;
        nt.set('style',sty)
        slf.svg.append(nt);
        nt.get_id(); # assign id now
        return nt
                        
    for s in list(ct.keys()):
        for ii in range(len(ct[s])):
            t = Make_Character(ct[s][ii]+'\u00A0\u00A0',s); # character with 2 nb spaces (last space not rendered)
            ct[s][ii] = [ct[s][ii],t,t.get_id()]; 
        t = Make_Character('A\u00A0\u00A0',s);              # A with 2 nb spaces
        ct[s].append([ct[s][ii],t,t.get_id()]);             
        t = Make_Character('A\u00A0\u00A0\u00A0',s);        # A with 3 nb spaces
        ct[s].append([ct[s][ii],t,t.get_id()]); 
        
    nbb = Get_Bounding_Boxes(slf,True);  
    for s in list(ct.keys()):
        for ii in range(len(ct[s])):
            bb=nbb[ct[s][ii][2]]
            wdth = bb[0]+bb[2]
            ct[s][ii][1].delete();
            ct[s][ii] = [ct[s][ii][0],wdth]
    for s in list(ct.keys()):
        Nl = len(ct[s])-2;
        sw = ct[s][-1][1] - ct[s][-2][1] # space width is the difference in widths of the last two
        for ii in range(Nl):
            cw = ct[s][ii][1] - sw;
            if ct[s][ii][0]==' ':
                cw = sw;
            ct[s][ii] = [ct[s][ii][0],cw,sw];
        ct[s] = ct[s][0:Nl]
    return ct, nbb

def reverse_shattering(el,ctable):
    # In PDFs, text is often positioned by letter.
    # This makes it hard to modify / adjust it. This fixes that.
    # Recursively run on children first
    el.set('sodipodi:role',None);
    ks=el.getchildren();
    for k in ks:
        if isinstance(k, (Tspan,TextElement)):    # k.typename=='Tspan' or k.typename=='TextElement':
            reverse_shattering(k,ctable);
    myx = el.get('x');
    if myx is not None:#not(myx==None):
        myx = myx.split();
        myx =[float(x) for x in myx];
        if len(myx)>1:
            docscale = get_parent_svg(el).scale;
            sty = el.composed_style();
            fs = float(sty.get('font-size').strip('px'));
            sty = Set_Style_Comp2(str(sty),'font-size','1px');
            sty = Set_Style_Comp2(sty,'fill','#000000')                              
            
            # We sometimes need to add non-breaking spaces to keep letter positioning similar
            stxt = [x for _, x in sorted(zip(myx, el.text), key=lambda pair: pair[0])] # text sorted in ascending x
            sx   = [x for _, x in sorted(zip(myx, myx)    , key=lambda pair: pair[0])] # x sorted in ascending x
            stxt = "".join(stxt) # back to string
            spaces_before = []; cpos=sx[0];
            for ii in range(len(stxt)): # advance the cursor to figure out how many spaces are needed
                myi = [jj for jj in range(len(ctable[sty])) if ctable[sty][jj][0]==stxt[ii]][0]
                myw  = ctable[sty][myi][1]/docscale*fs
                mysw = ctable[sty][myi][2]/docscale*fs
                spaces_needed = round((sx[ii]-cpos)/mysw)
                spaces_before.append(max(0,spaces_needed - sum(spaces_before)))
                cpos += myw # advance the cursor
            for ii in reversed(range(len(stxt)-1)): 
                if spaces_before[ii+1]>0:
                    stxt = stxt[0:ii+1]+('\u00A0'*spaces_before[ii+1])+stxt[ii+1:]; # NBSPs don't collapse
            el.text = stxt
            el.set('x',str(sx[0]));

# sets a style property (of an element)  
def Set_Style_Comp(el,comp,val):
    sty = el.get('style');
    if sty is not None:#not(sty==None):
        sty = sty.split(';');
        fillfound=False;
        for ii in range(len(sty)):
            if comp in sty[ii]:
                if val is not None:
                    sty[ii] = comp+':'+val;
                else:
                    sty[ii] = ''
                fillfound=True;
        if not(fillfound):
            if val is not None:
                sty.append(comp+':'+val);
            else: pass
        sty = ';'.join(sty);
        el.set('style',sty);
    else:
        sty = comp+':'+val
    el.set('style',sty);
    
# sets a style property (of a style string) 
def Set_Style_Comp2(sty,comp,val):
    if sty is not None:#not(sty==None):
        sty = sty.split(';');
        fillfound=False;
        for ii in range(len(sty)):
            if comp in sty[ii]:
                if val is not None:
                    sty[ii] = comp+':'+val;
                else:
                    sty[ii] = ''
                fillfound=True;
        if not(fillfound):
            if val is not None:
                sty.append(comp+':'+val);
            else: pass
        sty = ';'.join(sty);
    else:
        sty = comp+':'+val
    return sty

# gets a style property (return None if none)
def Get_Style_Comp(sty,comp):
    sty=str(sty);
    val=None;
    if sty is not None:#not(sty==None):
        sty = sty.split(';');
        for ii in range(len(sty)):
            if comp in sty[ii]:
                a=sty[ii].split(':');
                val=a[1];
    return val

# For style components that represent a size (stroke-width, font-size, etc), calculate
# the true size reported by Inkscape, inheriting any styles/transforms/document scaling
def Get_Composed_Width(el,comp):
    cs = el.composed_style();
    ct = el.composed_transform();
    svg = get_parent_svg(el)
    docscale = svg.scale;
    sc = Get_Style_Comp(cs,comp);
    if sc is not None:
        if '%' in sc: # relative width, get parent width
            sc = float(sc.strip('%'))/100;
            sc = sc*Get_Composed_Width(el.getparent(),comp)
            sc = str(sc)+'px'
#        sw = svg.unittouu(sc);
        sw = float(sc.strip().replace("px", ""))
        sw *= math.sqrt(abs(ct.a*ct.d - ct.b*ct.c))
        return sw*docscale
    else:
        return None
    
# For style components that are a list (stroke-dasharray), calculate
# the true size reported by Inkscape, inheriting any styles/transforms
def Get_Composed_List(el,comp):
    cs = el.composed_style();
    ct = el.composed_transform();
    sc = Get_Style_Comp(cs,comp);
    docscale = get_parent_svg(el).scale;
    if sc=='none':
        return 'none'
    elif sc is not None:
        sw = sc.strip().replace("px", "").split(',')
        sw = [float(x)*math.sqrt(abs(ct.a*ct.d - ct.b*ct.c))*docscale for x in sw];
        return sw
    else:
        return None

# Unit parser and renderer
def uparse(str):
    if str is not None:
        uv = inkex.units.parse_unit(str,default_unit=None);
        return uv[0],uv[1]
    else:
        return None, None
def urender(v,u):
    if v is not None:
        if u is not None:
            return inkex.units.render_unit(v,u);
        else:
            return str(v)
    else:
        return None

# Get points of a path, element, or rectangle in the global coordinate system
def get_points(el):
    if isinstance(el,Line): #el.typename=='Line':
        pts = [Vector2d(el.get('x1'),el.get('y1')),\
               Vector2d(el.get('x2'),el.get('y2'))];
    elif isinstance(el,(PathElement,Polyline)): # el.typename=='PathElement':
        pth=Path(el.get_path()).to_absolute();
        pts = list(pth.control_points);
    elif isinstance(el,Rectangle):  # el.typename=='Rectangle':
        x = float(el.get('x'));
        y = float(el.get('y'));
        w = float(el.get('width'));
        h = float(el.get('height'));
        pts = [Vector2d(x,y),Vector2d(x+w,y),Vector2d(x+w,y+h),Vector2d(x,y+h),Vector2d(x,y)];
    
    ct = el.composed_transform();
    docscale = get_parent_svg(el).scale;
    xs = []; ys = [];
    for p in pts:
        p = ct.apply_to_point(p);
        xs.append(p.x*docscale)
        ys.append(p.y*docscale)
    return xs, ys

def ungroup(groupnode):
    # Pops a node out of its group, unless it's already in a layer or the base
    # Unlink any clones
    # Remove any comments
    # Preserves style and clipping
    node_index = list(groupnode.getparent()).index(groupnode)   # parent's location in grandparent
#    node_style = dict(Style.parse_str(groupnode.get("style")))
    node_transform = Transform(groupnode.get("transform")).matrix;
    node_clippathurl = groupnode.get('clip-path')
        
    els = groupnode.getchildren();
    for el in list(reversed(els)):
        wasuse = False;
        if isinstance(el,Use):                   # unlink clones
            p=el.unlink();
            tx = el.get('x'); ty=el.get('y')
            if tx is None: tx = 0;
            if ty is None: ty = 0;
            p.set('transform',Transform('translate('+str(tx)+','+str(ty)+')')*Transform(p.get('transform')))
            el.delete(); el=p; el.set('unlinked_clone',True); wasuse=True;
        elif isinstance(el,lxml.etree._Comment): # remove comments
            groupnode.remove(el)
        if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject, lxml.etree._Comment))):
            recursive_merge_clip(el, node_clippathurl) # transform applies to clip, so do clip first
            _merge_transform(el, node_transform)
            el.style = shallow_composed_style(el)
#            _merge_style(el, node_style)    
            groupnode.getparent().insert(node_index+1,el); # places above
        if isinstance(el, Group) and wasuse: # if Use was a group, ungroup it
            ungroup(el)
    if len(groupnode.getchildren())==0:
        groupnode.delete();
         
# Same as composed_style(), but no recursion
def shallow_composed_style(el):
    parent = el.getparent();
    if parent is not None and isinstance(parent, ShapeElement):
        return parent.style + el.style
    return el.style

def _merge_transform(node, transform):
    # From Deep Ungroup
    # Originally from https://github.com/nikitakit/svg2sif/blob/master/synfig_prepare.py#L370
    def _get_dimension(s="1024"):
        """Convert an SVG length string from arbitrary units to pixels"""
        if s == "":
            return 0
        try:
            last = int(s[-1])
        except:
            last = None

        if type(last) == int:
            return float(s)
        elif s[-1] == "%":
            return 1024
        elif s[-2:] == "px":
            return float(s[:-2])
        elif s[-2:] == "pt":
            return float(s[:-2]) * 1.25
        elif s[-2:] == "em":
            return float(s[:-2]) * 16
        elif s[-2:] == "mm":
            return float(s[:-2]) * 3.54
        elif s[-2:] == "pc":
            return float(s[:-2]) * 15
        elif s[-2:] == "cm":
            return float(s[:-2]) * 35.43
        elif s[-2:] == "in":
            return float(s[:-2]) * 90
        else:
            return 1024

    # Compose the transformations
    if node.tag == addNS("svg", "svg") and node.get("viewBox"):
        vx, vy, vw, vh = [_get_dimension(x)
            for x in node.get("viewBox").split()]
        dw = _get_dimension(node.get("width", vw))
        dh = _get_dimension(node.get("height", vh))
        t = ("translate(%f, %f) scale(%f, %f)" %
            (-vx, -vy, dw / vw, dh / vh))
        this_transform = simpletransform.parseTransform(t, transform)
        this_transform = simpletransform.parseTransform(node.get("transform"), this_transform)
        del node.attrib["viewBox"]
    else:
        this_transform = Transform(transform)*Transform(node.get("transform"))
#                this_transform = simpletransform.parseTransform(node.get("transform"), transform)    # deprecated, https://inkscape.gitlab.io/inkscape/doxygen-extensions/simpletransform_8py_source.html

    # Set the node's transform attrib
#            node.set("transform", simpletransform.formatTransform(this_transform)) # deprecated
    node.set("transform",str(this_transform))


def _merge_style(node, style):
    """Propagate style and transform to remove inheritance
    # From Deep Ungroup
    https://github.com/nikitakit/svg2sif/blob/master/synfig_prepare.py#L370
    """
    # Compose the style attribs
    this_style = node.style
    remaining_style = {}  # Style attributes that are not propagated

    # Filters should remain on the top ancestor
    non_propagated = ["filter"]
    for key in non_propagated:
        if key in this_style.keys():
            remaining_style[key] = this_style[key]
            del this_style[key]

    # Create a copy of the parent style, and merge this style into it
    parent_style_copy = style.copy()
    parent_style_copy.update(this_style)
    this_style = parent_style_copy

    # Merge in any attributes outside of the style
    style_attribs = ["fill", "stroke"]
    for attrib in style_attribs:
        if node.get(attrib):
            this_style[attrib] = node.get(attrib)
            del node.attrib[attrib]

    if isinstance(node, (SvgDocumentElement, Anchor, Group, Switch)):
        # Leave only non-propagating style attributes
        if not remaining_style:
            if "style" in node.keys():
                del node.attrib["style"]
        else:
            node.style = remaining_style

    else:
        # This element is not a container
        # Merge remaining_style into this_style
        this_style.update(remaining_style)
        # Set the element's style attribs
        node.style = this_style
      
def recursive_merge_clip(node,clippathurl):
    # Modified from Deep Ungroup
    if clippathurl is not None:
        if node.transform is not None:
                # Clip-paths on nodes with a transform have the transform
                # applied to the clipPath as well, which we don't want.  So, we
                # create new clipPath element with references to all existing
                # clippath subelements, but with the inverse transform applied   
                myn = node
                while myn.getparent() is not None:  # get svg handle
                    myn = myn.getparent();
                svg = myn;
                new_clippath = etree.SubElement(
                    svg.getElement('//svg:defs'), 'clipPath',
                    {'clipPathUnits': 'userSpaceOnUse',
                      'id': svg.get_unique_id("clipPath")})
                clippath = svg.getElementById(clippathurl[5:-1])
                for c in clippath.iterchildren():
                    etree.SubElement(
                            new_clippath, 'use',
                            {inkex.addNS('href', 'xlink'): '#' + c.get("id"),
                              'transform': str(-node.transform),
                              'id': svg.get_unique_id("use")})
                # Set the clippathurl to be the one with the inverse transform
                clippathurl = "url(#" + new_clippath.get("id") + ")"  
        
        myclip = node.get('clip-path');
        if myclip is not None:
            # Existing clip is replaced by a duplicate, then apply new clip to children of duplicate
            clipnode = svg.getElementById(myclip[5:-1]);
            d = clipnode.duplicate();
            node.set('clip-path',"url(#" + d.get("id") + ")")
            ks = d.getchildren();
            for k in ks:
                recursive_merge_clip(k,clippathurl);
        else:
            node.set('clip-path',clippathurl)

# e.g., bbs = dh.Get_Bounding_Boxes(self.options.input_file);
def Get_Bounding_Boxes(s,getnew):
# Gets all of a document's bounding boxes (by ID)
# Note that this uses a command line call, so by default it will only get the values from BEFORE the extension is called
# Set getnew to True to make a temporary copy of the file that is then read. This gets the new boxes but is slower

    if not(getnew):
        tFStR = command.inkscape(s.options.input_file,'--query-all');
    else:
        tmpname = s.options.input_file+'_tmp';
        command.write_svg(s.svg,tmpname);
        tFStR = command.inkscape(tmpname,'--query-all');
        import os; os.remove(tmpname)

    tBBLi = tFStR.splitlines()
#    x=[[float(x.strip('\'')) for x in str(d).split(',')[1:]] for d in tBBLi]
    bbs=dict();
    for d in tBBLi:
        key = str(d).split(',')[0][2:];
        data = [float(x.strip('\''))*s.svg.unittouu('1px') for x in str(d).split(',')[1:]]
        bbs[key] = data;
       
#    docscale = s.svg.scale
#    if not(docscale==1):
#        for ii in list(bbs.keys()):
#            for jj in range(len(bbs[ii])):
#                bbs[ii][jj] *= 1/docscale;
    return bbs

def debug(x):
    inkex.utils.debug(x);

def get_parent_svg(el):
    myn = el
    while myn.getparent() is not None:
        myn = myn.getparent();
    return myn;

def get_mod(slf, *types):
    """Originally from _selected.py in inkex, doesn't fail on comments"""
    def _recurse(elem):
        if (not types or isinstance(elem, types)):
            yield elem
        for child in elem:
            for item in _recurse(child):
                yield item
    return inkex.elements._selected.ElementList(slf.svg, [r for e in slf.values() for r in _recurse(e) \
                                              if not(isinstance(r,lxml.etree._Comment))])
 
            
def global_transform(el,trnsfrm):
    # Transforms an object and fuses it to any paths, preserving stroke
   
    # If parent layer is transformed, need to rotate out of its coordinate system
    myp = el.getparent();
    if isinstance(myp,SvgDocumentElement):
        prt=Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]);
    else:
        prt=myp.composed_transform(); 
    prt = Transform('scale('+str(get_parent_svg(el).scale)+')')*prt;  # also include document scaling
    
    myt = el.get('transform');
    if myt==None:
        newtr=(-prt)*trnsfrm*prt;
    else:
        newtr=(-prt)*trnsfrm*prt*Transform(myt)
    
    sw = Get_Composed_Width(el,'stroke-width');
    sd = Get_Composed_List(el, 'stroke-dasharray');
    el.set('transform',newtr); # Add the new transform
    if not(isinstance(el, (TextElement,Image,Group,FlowRoot))): # not(el.typename in ['TextElement','Image','Group']):
        ApplyTransform().recursiveFuseTransform(el);
        if sw is not None:
            nw = float(Get_Style_Comp(el.get('style'),'stroke-width'))
            sw = nw*sw/Get_Composed_Width(el,'stroke-width');
            Set_Style_Comp(el,'stroke-width',str(sw)); # fix width
        if not(sd in [None,'none']): #not(sd==None) and not(sd=='none'):
            nd = Get_Style_Comp(el.get('style'),'stroke-dasharray').split(',');
            cd = Get_Composed_List(el,'stroke-dasharray');
            for ii in range(len(sd)):
                sd[ii] = float(nd[ii])*sd[ii]/cd[ii];
            Set_Style_Comp(el,'stroke-dasharray',str(sd).strip('[').strip(']')); # fix width