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
    TextElement, FlowRoot, FlowPara, FlowSpan, Tspan, TextPath, Rectangle, \
        addNS, Transform, Style, ClipPath, Use, NamedView, Defs, \
        Metadata, ForeignObject, Vector2d, Path, Line, PathElement,command,\
        SvgDocumentElement,Image,Group,Polyline,Anchor,Switch,ShapeElement, BaseElement,FlowRegion)
from applytransform_mod import ApplyTransform
import TextParser as tp
import lxml, simpletransform, math
from lxml import etree  


It = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]);

def descendants2(el):
    # Like descendants(), but avoids recursion to avoid recursion depth issues
    cel = el;
    keepgoing = True; childrendone = False;
    descendants = [];
    while keepgoing:
        keepgoing = False;
        if not(childrendone):
            descendants.append(cel); 
            # if isinstance(cel, (str)):
            #     debug(type(cel))
            ks = cel.getchildren();
            if len(ks)>0: # try children
                cel = ks[0];
                keepgoing = True; childrendone = False; continue;
        
        if cel==el:
            keepgoing = False; continue;
        else:
            sibs = cel.getparent().getchildren();
            myi = [ii for ii in range(len(sibs)) if sibs[ii]==cel][0];
            if myi!=len(sibs)-1: # try younger siblings
                cel = sibs[myi+1];
                keepgoing = True; childrendone = False; continue;
            else:
                cel = cel.getparent();
                keepgoing = True; childrendone = True; continue;
    descendants = [v for v in descendants if isinstance(v, (BaseElement, str))]
    return descendants;

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
        sty = [v.strip(';') for v in sty if v!=''];
        sty = ';'.join(sty)
        el.set('style',sty);
    else:
        if val is not None:
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
        sty = [v.strip(';') for v in sty if v!=''];
        sty = ';'.join(sty)
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
            a=sty[ii].split(':');
            if comp.lower()==a[0].lower():
                val=a[1];
    return val

# A temporary version of the new selected_style until it's officially released.
# Maybe replace later (but it's currently way faster, so maybe not)
def selected_style_local(el):
    parent = el.getparent();
    if parent is not None and isinstance(parent, (ShapeElement,SvgDocumentElement)):
        return selected_style_local(parent) + cascaded_style2(el) 
    return cascaded_style2(el)

svgpres = ['alignment-baseline','baseline-shift','clip','clip-path','clip-rule','color','color-interpolation','color-interpolation-filters','color-profile','color-rendering','cursor','direction','display','dominant-baseline','enable-background','fill','fill-opacity','fill-rule','filter','flood-color','flood-opacity','font-family','font-size','font-size-adjust','font-stretch','font-style','font-variant','font-weight','glyph-orientation-horizontal','glyph-orientation-vertical','image-rendering','kerning','letter-spacing','lighting-color','marker-end','marker-mid','marker-start','mask','opacity','overflow','pointer-events','shape-rendering','stop-color','stop-opacity','stroke','stroke-dasharray','stroke-dashoffset','stroke-linecap','stroke-linejoin','stroke-miterlimit','stroke-opacity','stroke-width','text-anchor','text-decoration','text-rendering','transform','transform-origin','unicode-bidi','vector-effect','visibility','word-spacing','writing-mode']
excludes = ['clip','clip-path','mask','transform','transform-origin']
global cssdict
cssdict = None;
def cascaded_style2(el):
# Object's style including any CSS
    global cssdict
    if cssdict is None:
        # Generate a dictionary of styles at least once so we don't have to do constant lookups
        # If elements change, will need to rerun by setting cssdict to None
        generate_cssdict(get_parent_svg(el));
#        svg = get_parent_svg(el)
#        cssdict= dict();
#        for sheet in svg.root.stylesheets:
#            for style in sheet:
#                for elem in svg.xpath(style.to_xpath()):
#                    elid = elem.get('id',None);
#                    if elid is not None and style!=Style():
#                        if cssdict.get(elid) is None:
#                            cssdict[elid] = Style() + style;
#                        else:
#                            cssdict[elid] += style;
    csssty = cssdict.get(el.get_id());
    locsty = el.style;
    
    # Add any presentation attributes to local style
    attr = list(el.keys());
    attsty = Style('');
    for a in attr:
        if a in svgpres and not(a in excludes) and locsty.get(a) is None and el.get(a) is not None:
            attsty[a] = el.get(a)
#            debug(el.get(a))

    if csssty is None:
        return attsty+locsty
    else:
        # Any style specified locally takes priority, followed by CSS,
        # followed by any attributes that the element has
        return attsty+csssty+locsty
def dupe_in_cssdict(oldid,newid):
    # duplicate a style in cssdict
    global cssdict
    if cssdict is not None:
        csssty = cssdict.get(oldid);
        if csssty is not None:
            cssdict[newid]=csssty;
def generate_cssdict(svg):
    global cssdict
    cssdict= dict();
    for sheet in svg.root.stylesheets:
        for style in sheet:
            for elem in svg.xpath(style.to_xpath()):
                elid = elem.get('id',None);
                if elid is not None and style!=Style():
                    if cssdict.get(elid) is None:
                        cssdict[elid] = Style() + style;
                    else:
                        cssdict[elid] += style;

# For style components that represent a size (stroke-width, font-size, etc), calculate
# the true size reported by Inkscape in user units, inheriting any styles/transforms/document scaling
def Get_Composed_Width(el,comp,nargout=1):
    # cs = el.composed_style();
    cs = selected_style_local(el);
    ct = el.composed_transform();
    if nargout==4:
        ang = math.atan2(ct.c,ct.d)*180/math.pi;
    svg = get_parent_svg(el)
    docscale = svg.scale;
    sc = Get_Style_Comp(cs,comp);
    # debug(sc)
    if sc is not None:
        if '%' in sc: # relative width, get parent width
            sc = float(sc.strip('%'))/100;
            fs, sf, ct, ang = Get_Composed_Width(el.getparent(),comp,4)
            if nargout==4:
                ang = math.atan2(ct.c,ct.d)*180/math.pi;
                return fs*sc,sf,ct,ang
            else:
                return fs*sc
            # sc = sc*Get_Composed_Width(el.getparent(),comp)
            # sc = str(sc)+'px'
        else:
            # sw = float(sc.strip().replace("px", ""))
            sw = implicitpx(sc)
            sf = math.sqrt(abs(ct.a*ct.d - ct.b*ct.c))*docscale # scale factor
            if nargout==4:
                return sw*sf, sf, ct, ang
            else:
                return sw*sf
    else:
        if comp=='font-size':
            sf = math.sqrt(abs(ct.a*ct.d - ct.b*ct.c))*docscale # scale factor
            returnval = 12*sf; # default font is 12 uu
        else:
            returnval = None;
            sf = None;
            
        if nargout==4:
            return returnval,sf,ct,ang
        else:
            return returnval
    
# Get line-height in user units
def Get_Composed_LineHeight(el):    # cs = el.composed_style();
    cs = selected_style_local(el);
    sc = Get_Style_Comp(cs,'line-height');
    if sc is not None:
        if '%' in sc: # relative width, get parent width
            sc = float(sc.strip('%'))/100;
        elif sc.lower()=='normal':
            sc = 1.25
        else:
            sc = float(sc);
    if sc is None:
        sc = 1.25;   # default line-height is 12 uu
    fs = Get_Composed_Width(el,'font-size')
    return sc*fs
    
# For style components that are a list (stroke-dasharray), calculate
# the true size reported by Inkscape, inheriting any styles/transforms
def Get_Composed_List(el,comp):
    # cs = el.composed_style();
    cs = selected_style_local(el);
    ct = el.composed_transform();
    sc = Get_Style_Comp(cs,comp);
    docscale = get_parent_svg(el).scale;
    if sc=='none':
        return 'none'
    elif sc is not None:
        sw = sc.strip().replace("px", "").split(',')
        sw = [implicitpx(x)*math.sqrt(abs(ct.a*ct.d - ct.b*ct.c))*docscale for x in sw];
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
    
def implicitpx(str):
    # For many properties, a size specification of '1px' actually means '1uu'
    # Even if the size explicitly says '1mm' and the user units are mm, this will be
    # first converted to px and then interpreted to mean user units. (So '1mm' would
    # up being bigger than 1 mm). This returns the size as Inkscape will interpret it (in uu)
    return inkex.units.convert_unit(str.lower().strip(), 'px', default='px')

# Get points of a path, element, or rectangle in the global coordinate system
def get_points(el,irange=None):
    if isinstance(el,Line): #el.typename=='Line':
        pts = [Vector2d(el.get('x1'),el.get('y1')),\
               Vector2d(el.get('x2'),el.get('y2'))];
    elif isinstance(el,(PathElement,Polyline)): # el.typename=='PathElement':
        pth=Path(el.get_path()).to_absolute();
        if irange is not None:
            pnew = Path();
            for ii in range(irange[0],irange[1]):
                pnew.append(pth[ii])
            pth = pnew
        pts = list(pth.control_points);
    elif isinstance(el,Rectangle):  # el.typename=='Rectangle':
        x = (el.get('x'));
        y = (el.get('y'));
        w = (el.get('width'));
        h = (el.get('height'));
        if x is not None and y is not None and w is not None and h is not None:
            x = float(x);
            y = float(y);
            w = float(w);
            h = float(h);
            pts = [Vector2d(x,y),Vector2d(x+w,y),Vector2d(x+w,y+h),Vector2d(x,y+h),Vector2d(x,y)];
        else:
            pts = [];
    ct = el.composed_transform();
    docscale = get_parent_svg(el).scale;
    xs = []; ys = [];
    for p in pts:
        p = ct.apply_to_point(p);
        xs.append(p.x*docscale)
        ys.append(p.y*docscale)
    return xs, ys

import time
global tic
tic = time.time();
global ncalls
ncalls = 0
def ungroup(groupnode):
    # Pops a node out of its group, unless it's already in a layer or the base
    # Unlink any clones
    # Remove any comments
    # Preserves style, clipping, and masking
    global tic
    global ncalls
    ncalls+=1
        
    node_index = list(groupnode.getparent()).index(groupnode)   # parent's location in grandparent
    node_transform = Transform(groupnode.get("transform")).matrix;
    node_clippathurl = groupnode.get('clip-path')
    node_maskurl     = groupnode.get('mask')
            
    els = groupnode.getchildren();
    for el in list(reversed(els)):
        
        unlinkclone = False;
        if isinstance(el,Use):
            useid = el.get('xlink:href');
            if useid is not None:
                useel = getElementById2(get_parent_svg(el),useid[1:]);
                unlinkclone = not(isinstance(useel,(inkex.Symbol)));
        
        if unlinkclone:                   # unlink clones
            p=el.unlink();
            tx = el.get('x'); ty=el.get('y')
            if tx is None: tx = 0;
            if ty is None: ty = 0;
            p.set('transform',Transform('translate('+str(tx)+','+str(ty)+')')*Transform(p.get('transform')))
            el.delete(); el=p; el.set('unlinked_clone',True); #wasuse=True;
        elif isinstance(el,lxml.etree._Comment): # remove comments
            groupnode.remove(el)
        if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject, lxml.etree._Comment))):
            recursive_merge_clipmask(el, node_clippathurl)          # transform applies to clip, so do clip first
            recursive_merge_clipmask(el, node_maskurl, mask=True)   # also mask
            _merge_transform(el, node_transform)
            el.style = shallow_composed_style(el)
            
            # If the element had clipping/masking specified in a stylesheet, this will override any attributes
            # Fix by creating a style specific to my id that includes the new clipping/masking
#            global cssdict
#            mycss = cssdict.get(el.get_id());
#            if mycss is not None:
#                if mycss.get('clip-path') is not None and mycss.get('clip-path')!=el.get('clip-path'):
#                    get_parent_svg(el).stylesheet.add('#'+el.get_id(),'clip-path:'+el.get('clip-path'));
#                    mycss['clip-path']=el.get('clip-path');
#                if mycss.get('mask') is not None and mycss.get('mask')!=el.get('mask'):
#                    get_parent_svg(el).stylesheet.add('#'+el.get_id(),'mask:'+el.get('mask'));
#                    mycss.set['mask']=el.get('mask');
#            if el.style.get('clip-path') is not None: # also clear local style
#                Set_Style_Comp(el,'clip-path',None);
#            if el.style.get('mask') is not None:
#                Set_Style_Comp(el,'mask',None);
#                
            fix_css_clipmask(el,mask=True);
            fix_css_clipmask(el,mask=False);
                
            groupnode.getparent().insert(node_index+1,el); # places above
        if isinstance(el, Group) and unlinkclone: # if Use was a group, ungroup it
            ungroup(el)
    if len(groupnode.getchildren())==0:
        groupnode.delete();
        
         
# Same as composed_style(), but no recursion and with some tweaks
def shallow_composed_style(el):
    parent = el.getparent();
    if parent.get('opacity') is not None:                          # make sure style includes opacity
        Set_Style_Comp(parent,'opacity',parent.get('opacity'));
    if Get_Style_Comp(parent.style,'stroke-linecap') is not None:  # linecaps not currently inherited, so don't include in composition
        Set_Style_Comp(parent,'stroke-linecap',None);
    if parent is not None and isinstance(parent, ShapeElement):
        return cascaded_style2(parent) + cascaded_style2(el)
    return cascaded_style2(el)

def _merge_transform(node, transform):
    # From Deep Ungroup
    # Originally from https://github.com/nikitakit/svg2sif/blob/master/synfig_prepare.py#L370
    def _get_dimension(s="1024"):
        """Convert an SVG length string from arbitrary units to pixels"""
        if s == "":
            return 0
        try:               last = int(s[-1])
        except:            last = None

        if type(last) == int: return float(s)
        elif s[-1] == "%":    return 1024
        elif s[-2:] == "px":  return float(s[:-2])
        elif s[-2:] == "pt":  return float(s[:-2]) * 1.25
        elif s[-2:] == "em":  return float(s[:-2]) * 16
        elif s[-2:] == "mm":  return float(s[:-2]) * 3.54
        elif s[-2:] == "pc":  return float(s[:-2]) * 15
        elif s[-2:] == "cm":  return float(s[:-2]) * 35.43
        elif s[-2:] == "in":  return float(s[:-2]) * 90
        else:                 return 1024

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
    # node.set("transform",str(this_transform))
    node.transform = this_transform


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

# If an element has clipping/masking specified in a stylesheet, this will override any attributes
# I think this is an Inkscape 
# Fix by creating a style specific to my id that includes the new clipping/masking
def fix_css_clipmask(el,mask=False):
    if not(mask): cm = 'clip-path'
    else:         cm = 'mask'
    global cssdict
    if cssdict is None:
        generate_cssdict(get_parent_svg(el));
    mycss = cssdict.get(el.get_id());
    if mycss is not None:
        if mycss.get(cm) is not None and mycss.get(cm)!=el.get(cm):
            get_parent_svg(el).stylesheet.add('#'+el.get_id(),cm+':'+el.get(cm));
            mycss[cm]=el.get(cm);
    if el.style.get(cm) is not None: # also clear local style
        Set_Style_Comp(el,cm,None);

# Like duplicate, but randomly sets the id of all descendants also
# Normal duplicate does not
# Second argument disables duplication (for children, whose ids only need to be set)
def duplicate2(el,disabledup=False):
    if not(disabledup):
        # d = el.duplicate();
        d = duplicate_fixed(el);
        dupe_in_cssdict(el.get_id(),d.get_id())
        add_to_iddict(d);
    else:
        d = el;
    for k in d.getchildren():
        oldid = k.get_id();
        set_random_id2(k);
        dupe_in_cssdict(oldid,k.get_id())
        add_to_iddict(k);
        duplicate2(k,True)
    return d
def duplicate_fixed(el): # fixes duplicate's set_random_id
    """Like copy(), but the copy stays in the tree and sets a random id"""
    elem = el.copy()
    el.addnext(elem)
    set_random_id2(elem)
    return elem

def recursive_merge_clipmask(node,clippathurl,mask=False):
    # Modified from Deep Ungroup
    if clippathurl is not None:
        svg = get_parent_svg(node);
        if not(mask):
            cmstr1 = 'clipPath'
            cmstr2 = 'clip-path'
        else:
            cmstr1 = cmstr2 = 'mask'
            
            
        if node.transform is not None:
            # Clip-paths on nodes with a transform have the transform
            # applied to the clipPath as well, which we don't want.  So, we
            # create new clipPath element with references to all existing
            # clippath subelements, but with the inverse transform applied 
            new_clippath = etree.SubElement(
                svg.getElement('//svg:defs'), cmstr1,
                {cmstr1+'Units': 'userSpaceOnUse',
                  'id': get_unique_id2(svg,cmstr1)})
            add_to_iddict(new_clippath);
            
            clippath = getElementById2(svg,clippathurl[5:-1])
            if clippath is not None:
                for c in clippath.iterchildren():
                    newuse = etree.SubElement(
                            new_clippath, 'use',
                            {inkex.addNS('href', 'xlink'): '#' + c.get("id"),
                              'transform': str(-node.transform),
                              'id': get_unique_id2(svg,"use")})
                    add_to_iddict(newuse);
                clippathurl = "url(#" + new_clippath.get("id") + ")"
        myclip = node.get(cmstr2);
        if myclip is not None:
            # Existing clip is replaced by a duplicate, then apply new clip to children of duplicate
            # clipnode = svg.getElementById(myclip[5:-1]);
            clipnode = getElementById2(svg,myclip[5:-1]);
            d = duplicate2(clipnode); # very important to use dup2 here
            node.set(cmstr2,"url(#" + d.get("id") + ")");
#            add_to_iddict(d);
            ks = d.getchildren();
            for k in ks:
                recursive_merge_clipmask(k,clippathurl);
        else:
            node.set(cmstr2,clippathurl)
#            debug(node.get_id())
#            debug(cmstr2)
#            debug(clippathurl)
#            debug(node.get(cmstr2))

# Repeated getElementById lookups can be really slow, so instead create a dict that can be used to 
# speed this up. When an element is created that may be needed later, it MUST be added. 
global iddict
iddict = None;
def getElementById2(svg,elid):
    global iddict
    if iddict is None:
        generate_iddict(svg)
    return iddict.get(elid);
def generate_iddict(svg):
    global iddict
    iddict = dict();
    for el in descendants2(svg):
        iddict[el.get_id()] = el;
def add_to_iddict(el):
    global iddict
    if iddict is None:
        generate_iddict(get_parent_svg(el))
    iddict[el.get("id")] = el;
    
# The built-in get_unique_id gets stuck if there are too many elements. Instead use an adaptive
# size based on the current number of ids
import random
def get_unique_id2(svg, prefix):
    ids = svg.get_ids()
    new_id = None
    size = math.ceil(math.log10(len(ids)))+1
    _from = 10 ** size - 1
    _to = 10 ** size
    while new_id is None or new_id in ids:
        # Do not use randint because py2/3 incompatibility
        new_id = prefix + str(int(random.random() * _from - _to) + _to)
    svg.ids.add(new_id)
    return new_id
def set_random_id2(el, prefix=None, size=4, backlinks=False):
    """Sets the id attribute if it is not already set."""
    prefix = str(el) if prefix is None else prefix
    el.set_id(get_unique_id2(el.root,prefix), backlinks=backlinks)
    
# Like get_id(), but calls set_random_id2
def get_id2(el, as_url=0):
    """Get the id for the element, will set a new unique id if not set.

    as_url - If set to 1, returns #{id} as a string
             If set to 2, returns url(#{id}) as a string
    """
    if 'id' not in el.attrib:
        set_random_id2(el,el.TAG)
    eid = el.get('id')
    if as_url > 0:
        eid = '#' + eid
    if as_url > 1:
        eid = f'url({eid})'
    return eid

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
        key = str(d).split(',')[0];
        if key[0:2]=='b\'': # pre version 1.1
            key = key[2:];
        if str(d)[2:52]=='WARNING: Requested update while update in progress':
            continue;                       # skip warnings (version 1.0 only?)
        data = [float(x.strip('\''))*s.svg.unittouu('1px') for x in str(d).split(',')[1:]]
        bbs[key] = data;
    return bbs

def debug(x):
    inkex.utils.debug(x);

def get_parent_svg(el):
    # slightly faster than el.root
    myn = el
    while myn.getparent() is not None:
        myn = myn.getparent();
    if isinstance(myn,SvgDocumentElement):    
        return myn;
    else:
        return None

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




# When non-ascii characters are detected, replace all non-letter characters with the specified font
# Mainly for fonts like Avenir
def Replace_Non_Ascii_Font(el,newfont,*args):
    def nonletter(c):
        return not((ord(c)>=65 and ord(c)<=90) or (ord(c)>=97 and ord(c)<=122))
    def nonascii(c):
        return ord(c)>=128
    def alltext(el):
        astr = el.text;
        if astr is None: astr='';
        for k in el.getchildren():
            if isinstance(k,(Tspan,FlowPara,FlowSpan)):
                astr+=alltext(k)
                tl=k.tail;
                if tl is None: tl=''
                astr+=tl
        return astr
    
    forcereplace = (len(args)>0 and args[0]);
    if forcereplace or any([nonascii(c) for c in alltext(el)]):
        alltxt = [el.text]; el.text=''
        for k in el.getchildren():
            if isinstance(k,(Tspan,FlowPara,FlowSpan)):
                alltxt.append(k)
                alltxt.append(k.tail); k.tail=''
                el.remove(k)
        lstspan = None;
        for t in alltxt:
            if t is None:
                pass
            elif isinstance(t,str):
                ws = []; si=0;
                for ii in range(1,len(t)): # split into words based on whether unicode or not
                    if nonletter(t[ii-1])!=nonletter(t[ii]):
                        ws.append(t[si:ii]);
                        si=ii
                ws.append(t[si:]);
                sty = 'baseline-shift:0%;';
                for w in ws:
                    if any([nonletter(c) for c in w]):
                        w=w.replace(' ','\u00A0'); # spaces can disappear, replace with NBSP
                        ts = Tspan(w,style=sty+'font-family:'+newfont)
                        el.append(ts);
                        lstspan = ts;
                    else:
                        if lstspan is None: el.text = w
                        else:               lstspan.tail = w;
            elif isinstance(t,(Tspan,FlowPara,FlowSpan)):
                Replace_Non_Ascii_Font(t,newfont,True)
                el.append(t);
                lstspan = t;
            
            
                
            
def global_transform(el,trnsfrm,irange=None,trange=None):
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
        if trange is not None:
            for ii in range(len(trange)):
                trange[ii] = (-prt)*trange[ii]*prt
    else:
        newtr=(-prt)*trnsfrm*prt*Transform(myt)
        if trange is not None:
            for ii in range(len(trange)):
                trange[ii] = (-prt)*trange[ii]*prt*Transform(myt)
    
    sw = Get_Composed_Width(el,'stroke-width');
    sd = Get_Composed_List(el, 'stroke-dasharray');
    el.set('transform',newtr); # Add the new transform
    if not(isinstance(el, (TextElement,Image,Group,Tspan,FlowRoot,FlowPara,FlowRegion,FlowSpan))): # not(el.typename in ['TextElement','Image','Group']):
        ApplyTransform().recursiveFuseTransform(el,irange=irange,trange=trange);
        if sw is not None:
#            if Get_Style_Comp(el.get('style'),'stroke-width') is None:
#                debug(el.get_id())
            nw = float(Get_Style_Comp(el.get('style'),'stroke-width'))
            sw = nw*sw/Get_Composed_Width(el,'stroke-width');
            Set_Style_Comp(el,'stroke-width',str(sw)); # fix width
        if not(sd in [None,'none']): #not(sd==None) and not(sd=='none'):
            nd = Get_Style_Comp(el.get('style'),'stroke-dasharray').split(',');
            cd = Get_Composed_List(el,'stroke-dasharray');
            for ii in range(len(sd)):
                sd[ii] = implicitpx(nd[ii])*sd[ii]/cd[ii];
            Set_Style_Comp(el,'stroke-dasharray',str(sd).strip('[').strip(']')); # fix width
            
def get_path2(el):
# Like get_path, but correctly calculates path for rectangles and ellipses
    class MiniRect():
        def __init__(self,el):
            self.left = implicitpx(el.get('x', '0'))
            self.top = implicitpx(el.get('y', '0'))
            self.width = implicitpx(el.get('width', '0'))
            self.height = implicitpx(el.get('height', '0'))
            self.rx = implicitpx(el.get('rx', el.get('ry', '0')))
            self.ry = implicitpx(el.get('ry', el.get('rx', '0')))
            self.right = self.left+self.width
            self.bottom = self.top+self.height
        def get_path(self):
            """Calculate the path as the box around the rect"""
            if self.rx:
                rx, ry = self.rx, self.ry # pylint: disable=invalid-name
                return 'M {1},{0.top}'\
                       'L {2},{0.top}    A {0.rx},{0.ry} 0 0 1 {0.right},{3}'\
                       'L {0.right},{4}  A {0.rx},{0.ry} 0 0 1 {2},{0.bottom}'\
                       'L {1},{0.bottom} A {0.rx},{0.ry} 0 0 1 {0.left},{4}'\
                       'L {0.left},{3}   A {0.rx},{0.ry} 0 0 1 {1},{0.top} z'\
                    .format(self, self.left + rx, self.right - rx, self.top + ry, self.bottom - ry)
            return 'M {0.left},{0.top} h{0.width}v{0.height}h{1} z'.format(self, -self.width)
    class MiniEllipse():
        def __init__(self,el):
            self.cx = implicitpx(el.get('cx', '0'))
            self.cy = implicitpx(el.get('cy', '0'))
            if isinstance(el,(inkex.Ellipse)): # ellipse
                self.rx = implicitpx(el.get('rx', '0'))
                self.ry = implicitpx(el.get('ry', '0'))
            else: # circle
                self.rx = implicitpx(el.get('r', '0'))
                self.ry = implicitpx(el.get('r', '0'))
        def get_path(self):
            return ('M {cx},{y} '
                    'a {rx},{ry} 0 1 0 {rx}, {ry} '
                    'a {rx},{ry} 0 0 0 -{rx}, -{ry} z'
                    ).format(cx=self.cx, y=self.cy-self.ry, rx=self.rx, ry=self.ry)
    if isinstance(el,(inkex.Rectangle)):
        pth = MiniRect(el).get_path()
    elif isinstance(el,(inkex.Circle,inkex.Ellipse)):
        pth = MiniEllipse(el).get_path();
    else:
        pth = el.get_path();
    return pth

def object_to_path(el):
    if not(isinstance(el,inkex.PathElement)):
        pth = get_path2(el);
        el.tag = '{http://www.w3.org/2000/svg}path';
        el.set('d',str(pth));