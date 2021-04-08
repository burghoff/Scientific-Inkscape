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
        addNS, Transform, Style, ClipPath, Use, NamedView, Defs, Metadata, ForeignObject, Vector2d, Path
)
import simplestyle
import simpletransform
#import str

global ncall
ncall=0

def split_distant(el):
    # Fix distant words that have been spread out in a PDF
    # Recursively run on children first
    oldsodipodi = el.get('sodipodi:role');
    el.set('sodipodi:role',None)
    ks=el.getchildren();
    for k in ks:
        if k.typename=='Tspan' or k.typename=='TextElement':
            split_distant(k);
    myx = el.get('x');
    if not(myx==None):
        myx = myx.split();
        myx =[float(x) for x in myx];
        if len(myx)>1:
            sty = el.composed_style();
            fs = float(sty.get('font-size').strip('px'));
            starti = 0;
            for ii in range(1,len(myx)):
                if abs(myx[ii]-myx[ii-1])>3.0*fs*0.5:
                    word = el.text[starti:ii]
                    ts = el.duplicate();
                    ts.text = word;
                    ts.set('x',' '.join(str(x) for x in myx[starti:ii]));
                    ts.set('y',el.get('y'));
                    el.getparent().append(ts);
                    starti = ii;
            word = el.text[starti:]
            ts = el.duplicate();
            ts.text = word;
            ts.set('x',' '.join(str(x) for x in myx[starti:]));
            ts.set('y',el.get('y'));
            
            el.getparent().append(ts);
            el.delete();
    el.set('sodipodi:role',oldsodipodi)

def pop_tspans(el):
    # Pop out text from different tspans
    oldsodipodi = el.get('sodipodi:role');
    el.set('sodipodi:role',None);
    
    ks=el.getchildren();
    ks=[t for t in ks if t.typename=='Tspan'];
    node_index = list(el.getparent()).index(el);
    for k in ks:
        k.style = k.composed_style();
        k.set('sodipodi:role',None)
        el.getparent().insert(node_index,k); # pop everything out   
    for k in ks:
        dp = el.duplicate();             # make dupes of the empty
        dp.insert(0,k)                   # fill with individual tspans
        dp.set('sodipodi:role',oldsodipodi)
    el.set('sodipodi:role',oldsodipodi)
    if (el.getchildren()==None or len(el.getchildren())==0) and (el.text==None or len(el.text)==0):
        # original now empty, safe to delete
        el.delete();
     
# sets a style property     
def Set_Style_Comp(el,comp,val):
    sty = el.get('style');
    if not(sty==None):
        sty = sty.split(';');
        fillfound=False;
        for ii in range(len(sty)):
            if comp in sty[ii]:
                sty[ii] = comp+':'+val;
                fillfound=True;
        if not(fillfound):
            sty.append(comp+':'+val);
        sty = ';'.join(sty);
        el.set('style',sty);

# gets a style property (return None if none)
def Get_Style_Comp(sty,comp):
    sty=str(sty);
    val=None;
    if not(sty==None):
        sty = sty.split(';');
        for ii in range(len(sty)):
            if comp in sty[ii]:
                a=sty[ii].split(':');
                val=a[1];
    return val

# For elements that represent a size (stroke-width, font-size, etc), calculate
# the true size reported by Inkscape, inheriting any styles/transforms
import math
def Get_Composed_Width(el,comp):
    cs = el.composed_style();
    ct = el.composed_transform();
    sc = Get_Style_Comp(cs,comp);
    if sc is not None:
        sw = float(sc.strip().replace("px", ""))
        sw *= math.sqrt(abs(ct.a*ct.d - ct.b*ct.c))
        return sw
    else:
        return None
    

def Get_Composed_List(el,comp):
    cs = el.composed_style();
    ct = el.composed_transform();
    sc = Get_Style_Comp(cs,comp);
    if sc=='none':
        return 'none'
    elif sc is not None:
        sw = sc.strip().replace("px", "").split(',')
        sw = [float(x)*math.sqrt(abs(ct.a*ct.d - ct.b*ct.c)) for x in sw];
        return sw
    else:
        return None

def get_points(el):
    if el.typename=='Line':
        pts = [Vector2d(el.get('x1'),el.get('y1')),\
               Vector2d(el.get('x2'),el.get('y2'))];
    elif el.typename=='PathElement':
        pth=Path(el.get_path());
        pts = list(pth.control_points);
    elif el.typename=='Rectangle':
        x = float(el.get('x'));
        y = float(el.get('y'));
        w = float(el.get('width'));
        h = float(el.get('height'));
        pts = [Vector2d(x,y),Vector2d(x+w,y),Vector2d(x+w,y+h),Vector2d(x,y+h),Vector2d(x,y)];
    
    ct = el.composed_transform();
    xs = []; ys = [];
    for p in pts:
        p = ct.apply_to_point(p);
        xs.append(p.x)
        ys.append(p.y)
    return xs, ys
        
def ungroup(groupnode):
    # Pops a node out of its group, unless it's already in a layer or the base
    # Preserves style and clipping
#    inkex.utils.debug(groupnode.typename)
    global ncall
    ncall+=1;
    node_index = list(groupnode.getparent()).index(groupnode)   # parent's location in grandparent
#        node_style = simplestyle.parseStyle(node_parent.get("style")) # deprecated
    node_style = dict(Style.parse_str(groupnode.get("style")))
#        node_transform = simpletransform.parseTransform(node_parent.get("transform"))  # deprecated
    node_transform = Transform(groupnode.get("transform")).matrix;
    node_clippathurl = groupnode.get('clip-path')
        
    els = groupnode.getchildren();
    for el in list(reversed(els)):
        if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject))):
            _merge_transform(el, node_transform)  
            _merge_style(el, node_style)    
            _merge_clippath(el, node_clippathurl)
            groupnode.getparent().insert(node_index+1,el); # places above
            # node_parent.getparent().insert(node_index,node);   # places below
    if len(groupnode.getchildren())==0:
        groupnode.delete();
         

def _merge_transform(node, transform):
    """Propagate style and transform to remove inheritance
    Originally from
    https://github.com/nikitakit/svg2sif/blob/master/synfig_prepare.py#L370
    """
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
    Originally from
    https://github.com/nikitakit/svg2sif/blob/master/synfig_prepare.py#L370
    """

    # Compose the style attribs
#    this_style = simplestyle.parseStyle(node.get("style", ""))
    this_style = dict(inkex.Style.parse_str(node.get("style", "")));
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

    if (node.tag == addNS("svg", "svg")
        or node.tag == addNS("g", "svg")
        or node.tag == addNS("a", "svg")
        or node.tag == addNS("switch", "svg")):
        # Leave only non-propagating style attributes
        if len(remaining_style) == 0:
            if "style" in node.keys():
                del node.attrib["style"]
        else:
            node.set("style", simplestyle.formatStyle(remaining_style))

    else:
        # This element is not a container
        # Merge remaining_style into this_style
        this_style.update(remaining_style)

        # Set the element's style attribs
#        node.set("style", simplestyle.formatStyle(this_style))  # deprecated
        node.set("style", str(inkex.Style(this_style)));


from lxml import etree
def _merge_clippath(node, clippathurl):
    if clippathurl:
#        inkex.utils.debug(clippathurl)
        # node_transform = node.transformmyn = node
        myn = node
        while not(myn.getparent()==None):  # get svg handle
            myn = myn.getparent();
        svg = myn;
        if node.get('transform') is not None:
            node_transform = Transform(node.get('transform'));
            # Clip-paths on nodes with a transform have the transform
            # applied to the clipPath as well, which we don't want.  So, we
            # create new clipPath element with references to all existing
            # clippath subelements, but with the inverse transform applied
            
            new_clippath = etree.SubElement(
                svg.getElement('//svg:defs'), 'clipPath',
                {'clipPathUnits': 'userSpaceOnUse',
                 'id': svg.get_unique_id("clipPath")})
            clippath = svg.getElementById(clippathurl[5:-1])
            for c in clippath.iterchildren():
                etree.SubElement(
                        new_clippath, 'use',
                        {inkex.addNS('href', 'xlink'): '#' + c.get("id"),
                         'transform': str(-node_transform),
                         'id': svg.get_unique_id("use")})
    
            # Set the clippathurl to be the one with the inverse transform
            clippathurl = "url(#" + new_clippath.get("id") + ")"
    
        # Reference the parent clip-path to keep clipping intersection
        # Find end of clip-path chain and add reference there        
        node_clippathurl = node.get("clip-path")
        while node_clippathurl:
            node = svg.getElementById(node_clippathurl[5:-1])
            node_clippathurl = node.get("clip-path")
        node.set("clip-path", clippathurl)


# e.g., bbs = dh.Get_Bounding_Boxes(self.options.input_file);
def Get_Bounding_Boxes(s):
# Gets all of a document's bounding boxes (by ID)
# Note that this uses the command line, so it will only get the values before the extension is called
    import sys, copy     
    sys.path.append('/usr/share/inkscape/extensions')
    import subprocess
    
    tProc = subprocess.run( 'inkscape --query-all "%s"' % s.options.input_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tFStR = tProc.stdout  # List of all SVG objects in tFile
    tErrM = tProc.stderr
    # inkex.utils.debug(tFStR)
    tBBLi = tFStR.splitlines()
    x=[[float(x.strip('\'')) for x in str(d).split(',')[1:]] for d in tBBLi]
#    debug(tBBLi)
    bbs=dict();
    for d in tBBLi:
        key = str(d).split(',')[0][2:];
        data = [float(x.strip('\''))*s.svg.unittouu('1px') for x in str(d).split(',')[1:]]
        bbs[key] = data;
    return bbs
    # inkex.utils.debug(bbs['tspan2524'])

def debug(x):
    inkex.utils.debug(x);


import math    
def fontsize(el):
    # Get true font size in pt
    myn = el
    while not(myn.getparent()==None):  # get svg handle
        myn = myn.getparent();
    svg = myn;
    ptsize = svg.unittouu('1pt');
    ct=el.composed_transform();
    tnorm = math.sqrt(abs(ct.a*ct.d-ct.b*ct.c));
    # if it's text it is (hopefully) only rotated and scaled, so its transform is the sqrt of the det
    cs=el.composed_style(); 
    fs=float(Get_Style_Comp(cs,'font-size').strip('px'));
    return fs*tnorm/ptsize