#!/usr/bin/env python 
# coding=utf-8
#
# Copyright (c) 2020 David Burghoff <dburghoff@nd.edu>
#
# Functions modified from Inkex were made by
#                    Martin Owens <doctormo@gmail.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Thomas Holder <thomas.holder@schrodinger.com>
#                    Jonathan Neuhauser <jonathan.neuhauser@outlook.com>
# Functions modified from Deep_Ungroup made by Nikita Kitaev
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



import inkex
from inkex import (
    TextElement, FlowRoot, FlowPara, FlowSpan, Tspan, TextPath, Rectangle, \
        addNS, Transform, ClipPath, Use, NamedView, Defs, \
        Metadata, ForeignObject, Vector2d, Path, Line, PathElement,command,\
        SvgDocumentElement,Image,Group,Polyline,Anchor,Switch,ShapeElement, BaseElement,FlowRegion)
from applytransform_mod import ApplyTransform
import lxml, math, re
from lxml import etree  
from Style2 import Style2


import copy
def descendants2(el,return_tails=False):
    # Like Inkex's descendants(), but avoids recursion to avoid recursion depth issues
    cel = el;
    keepgoing = True; childrendone = False;
    descendants = [];
    precedingtails = [];
    
    # To avoid repeated lookups of each element's children and index, make dicts
    # that store them once they've been looked up
    children_dict = dict();
    parent_dict   = dict();
    index_dict = dict();
    pendingtails = [];
    def getchildren_dict(eli):
        if not(eli in children_dict):
            children_dict[eli] = list(eli)               # getchildren deprecated
            for ii in range(len(children_dict[eli])):
                index_dict[children_dict[eli][ii]] = ii; # store index for later
        return children_dict[eli]
    def myindex(eli):   # index amongst siblings
        if not(eli in index_dict):
            index_dict[eli] = getchildren_dict(getparent_dict(eli)).index(eli); # shouldn't need, just in case
        return index_dict[eli]
    def getparent_dict(eli):
        if not(eli in parent_dict):
            parent_dict[eli] = eli.getparent()               
        return parent_dict[eli]
        
    
    while keepgoing:
        keepgoing = False;
        if not(childrendone):
            descendants.append(cel);
            precedingtails.append((pendingtails))
            pendingtails = [];

            ks = getchildren_dict(cel);
            if len(ks)>0: # try children
                cel = ks[0];
                keepgoing = True; childrendone = False; continue;
            else:
                pendingtails.append(cel);
        
        if cel==el:
            keepgoing = False; continue;   # we're finished
        else:
            par  = getparent_dict(cel);
            sibs = getchildren_dict(par)
            myi = myindex(cel)
            if myi!=len(sibs)-1: # try younger siblings
                cel = sibs[myi+1];
                keepgoing = True; childrendone = False; continue;
            else:
                cel = par;
                pendingtails.append(cel); 
                keepgoing = True; childrendone = True; continue;
    descendants = [v for v in descendants if isinstance(v, (BaseElement, str))]
    
    if not(return_tails):
        return descendants;
    else:
        # For each descendants return a list of what element we expect our tails to precede
        precedingtails.append(pendingtails);  # will be one longer than descendants because of the last one
        return descendants, precedingtails, children_dict, parent_dict
inkex.BaseElement.descendants2 = property(descendants2)

# Sets a style property  
def Set_Style_Comp(el_or_sty,comp,val):
    isel = isinstance(el_or_sty,(BaseElement))  # is element
    if isel:
        sty = str(el_or_sty.lstyle)
        # sty = el_or_sty.get('style');
        # sty = getstylelazy(el_or_sty);
    else:
        isstr = isinstance(el_or_sty,(str))
        sty = str(el_or_sty)

    if sty is not None:
        sty = sty.split(';');
        compfound=False;
        for ii in range(len(sty)):
            if comp in sty[ii]:
                if val is not None:
                    sty[ii] = comp+':'+val;
                else:
                    sty[ii] = ''
                compfound=True;
        if not(compfound):
            if val is not None:
                sty.append(comp+':'+val);
            else: pass
        sty = [v.strip(';') for v in sty if v!=''];
        sty = ';'.join(sty)
    else:
        if val is not None:
            sty = comp+':'+val
    
    if isel:
        # el_or_sty.set('style',sty);             # set element style
        el_or_sty.lstyle = sty;             # set element style
    else:
        if isstr:
            return sty                          # return style string
        else:
            return Style2(sty)                  # convert back to Style
    

# gets a style property (return None if none)
def Get_Style_Comp(sty,comp):
    sty=str(sty);
    val=None;
    if sty is not None:
        sty = sty.split(';');
        for ii in range(len(sty)):
            a=sty[ii].split(':');
            if comp.lower()==a[0].lower():
                val=a[1];
    return val

# A temporary version of the new specified_style until it's officially released.
# Maybe replace later (but it's currently way faster, so maybe not)
def specified_style2(el):
    if not(hasattr(el,'spdstyle')):
        parent = el.getparent();
        if parent is not None and isinstance(parent, (ShapeElement,SvgDocumentElement)):
            ret = specified_style2(parent) + cascaded_style2(el) 
        else:
            ret = cascaded_style2(el)
        el.spdstyle = ret
    return el.spdstyle
def selected_style_local(el):
    return specified_style2(el)

svgpres = ['alignment-baseline','baseline-shift','clip','clip-path','clip-rule','color','color-interpolation','color-interpolation-filters','color-profile','color-rendering','cursor','direction','display','dominant-baseline','enable-background','fill','fill-opacity','fill-rule','filter','flood-color','flood-opacity','font-family','font-size','font-size-adjust','font-stretch','font-style','font-variant','font-weight','glyph-orientation-horizontal','glyph-orientation-vertical','image-rendering','kerning','letter-spacing','lighting-color','marker-end','marker-mid','marker-start','mask','opacity','overflow','pointer-events','shape-rendering','stop-color','stop-opacity','stroke','stroke-dasharray','stroke-dashoffset','stroke-linecap','stroke-linejoin','stroke-miterlimit','stroke-opacity','stroke-width','text-anchor','text-decoration','text-rendering','transform','transform-origin','unicode-bidi','vector-effect','visibility','word-spacing','writing-mode']
excludes = ['clip','clip-path','mask','transform','transform-origin']
def cascaded_style2(el):
# Object's style including any CSS
# Modified from Inkex's cascaded_style
    if not(hasattr(el,'csdstyle')):
        svg = get_parent_svg(el);
        if svg is not None:        cssdict = svg.cssdict;
        else:                      cssdict = dict();

        csssty = cssdict.get(el.get_id());
        # locsty = Style2(el.get('style'));
        locsty = el.lstyle
        
        # Add any presentation attributes to local style
        attr = list(el.keys());
        attsty = Style2('');
        for a in attr:
            if a in svgpres and not(a in excludes) and locsty.get(a) is None and el.get(a) is not None:
                attsty[a] = el.get(a)
        if csssty is None:
            ret = attsty+locsty
        else:
            # Any style specified locally takes priority, followed by CSS,
            # followed by any attributes that the element has
            ret = attsty+csssty+locsty
        el.csdstyle = ret
    return el.csdstyle
        
def dupe_in_cssdict(oldid,newid,svg):
    # duplicate a style in cssdict
    if svg is not None:      
        csssty = svg.cssdict.get(oldid);
        if csssty is not None:
            svg.cssdict[newid]=csssty;
            
def get_cssdict(svg):
    if not(hasattr(svg,'_cssdict')):
        # For certain xpaths such as classes, we can avoid xpath calls
        # by checking the class attributes on a document's descendants directly.
        # This is much faster for large documents.
        hasall = False;
        simpleclasses = dict(); simpleids = dict();
        for sheet in svg.stylesheets:
            for style in sheet:
                xp = vto_xpath(style);
                if xp=='//*': hasall = True;
                elif all([re.compile(r'\.([-\w]+)').sub(r"IAMCLASS", r.rule)=='IAMCLASS' for r in style.rules]): # all rules are classes
                    simpleclasses[xp] = [re.compile(r'\.([-\w]+)').sub(r"\1",r.rule) for r in style.rules]
                elif all([re.compile(r'#(\w+)').sub(r"IAMID", r.rule)=='IAMID' for r in style.rules]):           # all rules are ids
                    simpleids[xp] = [re.compile(r'\.([-\w]+)').sub(r"\1",r.rule)[1:] for r in style.rules]

        knownxpaths = dict()
        if hasall or len(simpleclasses)>0:
            ds = svg.ldescendants;
                
            cs = [d.get('class') for d in ds] 
            if hasall: knownxpaths['//*'] = ds;
            for xp in simpleclasses: knownxpaths[xp]=[]
            for ii in range(len(ds)):
                if cs[ii] is not None:
                    cv = cs[ii].split(' ') # only valid delimeter for multiple classes is space
                    for xp in simpleclasses:
                        if any([v in cv for v in simpleclasses[xp]]):
                            knownxpaths[xp].append(ds[ii])
        for xp in simpleids:
            knownxpaths[xp]=[]
            for sid in simpleids[xp]:
                idel = getElementById2(svg, sid);
                if idel is not None:
                    knownxpaths[xp].append(idel)
        
        # Now run any necessary xpaths and get the element styles
        cssdict= dict();
        for sheet in svg.root.stylesheets:
            for style in sheet:
                try:
                    # els = svg.xpath(style.to_xpath())  # original code
                    xp = vto_xpath(style);
                    if xp in knownxpaths: els = knownxpaths[xp]
                    else:                 els = svg.xpath(xp)
                    for elem in els:
                        elid = elem.get('id',None);
                        if elid is not None and style!=inkex.Style():  # still using Inkex's Style here since from stylesheets
                            if cssdict.get(elid) is None:
                                cssdict[elid] = Style2() + style;
                            else:
                                cssdict[elid] += style;
                except (lxml.etree.XPathEvalError,TypeError):
                    pass
        svg._cssdict = cssdict;
    return svg._cssdict;
inkex.SvgDocumentElement.cssdict = property(get_cssdict);

# Give all BaseElements a lazy style attribute that clears the stored cascaded / specified
# style whenever the style is changed. Always use this when setting styles.
def lstyget(el):
    if not(hasattr(el,'_lstyle')):
        el._lstyle = Style2(el.get('style'))        # el.get() is very efficient
    return el._lstyle
def lstyset(el,nsty):
    el.style  = nsty
    el._lstyle = Style2(nsty);
    if hasattr(el,'csdstyle'): delattr(el,'csdstyle');
    if hasattr(el,'spdstyle'): delattr(el,'spdstyle');
inkex.BaseElement.lstyle = property(lstyget,lstyset)

# Lazy composed_transform that stores the value when finished. Could be invalidated by
# changes to transform. Currently is not invalidated when the element is moved, so beware!
def lcomposed_transform(el):
    if not(hasattr(el,'_lcomposed_transform')):
        # ret = el.ltransform
        # cel = el.getparent();
        # while cel is not None:
        #     ret = cel.ltransform @ ret
        #     cel = cel.getparent();
        # el._lcomposed_transform = ret;
        myp = el.getparent();
        if myp is None: el._lcomposed_transform = el.ltransform;
        else:           el._lcomposed_transform = myp.lcomposed_transform @ el.ltransform
    return el._lcomposed_transform
inkex.BaseElement.lcomposed_transform = property(lcomposed_transform)

# Lazy transform 
def docT(t): # version stored to doc (for testing)
    return Transform([float(f"{t.a:.6g}"),float(f"{t.b:.6g}"),float(f"{t.c:.6g}"),float(f"{t.d:.6g}"),float(f"{t.e:.6g}"),float(f"{t.f:.6g}")]);
def ltransform(el):
    if not(hasattr(el,'_ltransform')):
        el._ltransform = el.transform;
    return el._ltransform
def set_ltransform(el,newt):
    el.transform   = newt;
    el._ltransform = newt;
    for d in el.descendants2:
        if hasattr(d,'_lcomposed_transform'): delattr(d,'_lcomposed_transform')  # invalidate descendant cts
inkex.BaseElement.ltransform = property(ltransform,set_ltransform)


# inkex.BaseElement.oldtransform = inkex.BaseElement.transform
    
# For style components that represent a size (stroke-width, font-size, etc), calculate
# the true size reported by Inkscape in user units, inheriting any styles/transforms/document scaling
def Get_Composed_Width(el,comp,nargout=1,styin=None,ctin=None):
    # cs = el.composed_style();
    if styin is None:                   # can pass styin to reduce extra style gets
        cs = specified_style2(el);
    else:
        cs = styin;
    if ctin is None:                    # can pass ctin to reduce extra composed_transforms
        # ct = el.composed_transform();
        ct = el.lcomposed_transform;
    else:
        ct = ctin;
    if nargout==4:
        ang = math.atan2(ct.c,ct.d)*180/math.pi;
    svg = get_parent_svg(el)
    docscale = 1;
    if svg is not None:
        docscale = vscale(svg);
        # idebug(vscale(svg))
    sc = Get_Style_Comp(cs,comp);
    # idebug([el.get_id(),sc])
    if sc is not None:
        if '%' in sc: # relative width, get parent width
            cel = el;
            while sc!=cel.lstyle.get(comp):
                cel = el.getparent();  # figure out ancestor where % is coming from
        
            sc = float(sc.strip('%'))/100;
            fs, sf, ct, ang = Get_Composed_Width(cel.getparent(),comp,4)
            if nargout==4:
                ang = math.atan2(ct.c,ct.d)*180/math.pi;
                return fs*sc,sf,ct,ang
            else:
                return fs*sc
        else:
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
def Get_Composed_LineHeight(el,styin=None,ctin=None):    # cs = el.composed_style();
    if styin is None:
        cs = specified_style2(el);
    else:
        cs = styin;
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
    fs = Get_Composed_Width(el,'font-size',styin=styin,ctin=ctin)
    return sc*fs
    
# For style components that are a list (stroke-dasharray), calculate
# the true size reported by Inkscape, inheriting any styles/transforms
def Get_Composed_List(el,comp,nargout=1,styin=None):
    # cs = el.composed_style();
    if styin is None:
        cs = specified_style2(el);
    else:
        cs = styin
    # ct = el.composed_transform();
    ct = el.lcomposed_transform;
    sc = Get_Style_Comp(cs,comp);
    svg = get_parent_svg(el);
    docscale = 1;
    if svg is not None:
        docscale = vscale(svg);
    if sc=='none':
        return 'none'
    elif sc is not None:
        sw = sc.split(',')
        # sw = sc.strip().replace("px", "").split(',')
        sf = math.sqrt(abs(ct.a*ct.d - ct.b*ct.c))*docscale
        sw = [implicitpx(x)*sf for x in sw];
        if nargout==1:
            return sw
        else:
            return sw,sf
    else:
        if nargout==1:
            return None
        else:
            return None, None

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
    
def implicitpx(strin):
    # For many properties, a size specification of '1px' actually means '1uu'
    # Even if the size explicitly says '1mm' and the user units are mm, this will be
    # first converted to px and then interpreted to mean user units. (So '1mm' would
    # up being bigger than 1 mm). This returns the size as Inkscape will interpret it (in uu)
    if strin is None:
        return None
    else:
        return inkex.units.convert_unit(strin.lower().strip(), 'px');
#    return inkex.units.convert_unit(str.lower().strip(), 'px', default='px') # fails pre-1.1, default is px anyway
        

# Get points of a path, element, or rectangle in the global coordinate system
def get_points(el,irange=None):
    # if isinstance(el,Line): #el.typename=='Line':
    #     pts = [Vector2d(el.get('x1'),el.get('y1')),\
    #            Vector2d(el.get('x2'),el.get('y2'))];
    # elif isinstance(el,(PathElement,Polyline)): # el.typename=='PathElement':
    #     pth=Path(el.get_path()).to_absolute();
    #     if irange is not None:
    #         pnew = Path();
    #         for ii in range(irange[0],irange[1]):
    #             pnew.append(pth[ii])
    #         pth = pnew
    #     pts = list(pth.control_points);
    # elif isinstance(el,Rectangle):  # el.typename=='Rectangle':
    #     x = (el.get('x'));
    #     y = (el.get('y'));
    #     w = (el.get('width'));
    #     h = (el.get('height'));
    #     if x is not None and y is not None and w is not None and h is not None:
    #         x = float(x);
    #         y = float(y);
    #         w = float(w);
    #         h = float(h);
    #         pts = [Vector2d(x,y),Vector2d(x+w,y),Vector2d(x+w,y+h),Vector2d(x,y+h),Vector2d(x,y)];
    #     else:
    #         pts = [];
    pth=Path(get_path2(el)).to_absolute();
    if irange is not None:
        pnew = Path();
        for ii in range(irange[0],irange[1]):
            pnew.append(pth[ii])
        pth = pnew
    pts = list(pth.end_points);
            
    # ct = el.composed_transform();
    ct = el.lcomposed_transform;
    
    mysvg = get_parent_svg(el);
    docscale = 1;
    if mysvg is not None:
        docscale = vscale(mysvg);
        
    xs = []; ys = [];
    for p in pts:
        p = ct.apply_to_point(p);
        xs.append(p.x*docscale)
        ys.append(p.y*docscale)
    return xs, ys

# def isRectanglePath(el):
#     isrect = False;
#     if isinstance(el,(PathElement,Rectangle,Line,Polyline)): 
#         xs, ys = get_points(el);
        
#         if 3<=len(xs)<=5 and len(set(xs))==2 and len(set(ys))==2:
#             isrect = True;
#     return isrect

# Unlinks clones and composes transform/clips/etc, along with descendants
def unlink2(el):
    if isinstance(el,(Use)):
        useid = el.get('xlink:href');
        useel = getElementById2(get_parent_svg(el),useid[1:]);
        if useel is not None:         
            d = duplicate2(useel)

            # xy translation treated as a transform (applied first, then clip/mask, then full xform)
            tx = el.get('x'); ty=el.get('y')
            if tx is None: tx = 0;
            if ty is None: ty = 0;
            # order: x,y translation, then clip/mask, then transform
            compose_all(d,None,None,Transform('translate('+str(tx)+','+str(ty)+')'),None)
            compose_all(d,el.get('clip-path'),el.get('mask'),Transform(el.get('transform')),cascaded_style2(el))
            replace_element(el, d);
            d.set('unlinked_clone',True);
            for k in descendants2(d)[1:]:
                unlink2(k)
            return d
        else:
            return el
    else:
        return el
    
unungroupable = (NamedView, Defs, Metadata, ForeignObject, lxml.etree._Comment)
def ungroup(groupnode):
    # Pops a node out of its group, unless it's already in a layer or the base
    # Unlink any clones that aren't glyphs
    # Remove any comments, Preserves style, clipping, and masking
    
    gparent = groupnode.getparent()
    gindex  = list(gparent).index(groupnode)   # group's location in parent
    gtransform = groupnode.ltransform
    gclipurl   = groupnode.get('clip-path')
    gmaskurl   = groupnode.get('mask')
    gstyle =  cascaded_style2(groupnode)
            
    els = list(groupnode);
    for el in list(reversed(els)):
        
        unlinkclone = False;
        if isinstance(el,Use):
            useid = el.get('xlink:href');
            if useid is not None:
                useel = getElementById2(get_parent_svg(el),useid[1:]);
                unlinkclone = not(isinstance(useel,(inkex.Symbol)));
        
        if unlinkclone:                                         # unlink clones
            el = unlink2(el);
        elif isinstance(el,lxml.etree._Comment):                # remove comments
            groupnode.remove(el)
            
        if not(isinstance(el, unungroupable)): 
            clippedout = compose_all(el,gclipurl,gmaskurl,gtransform,gstyle)
            if clippedout:
                el.delete2()
            else:
                gparent.insert(gindex+1,el); # places above
                
        if isinstance(el, Group) and unlinkclone: # if was a clone, may need to ungroup
            ungroup(el)
    if len(groupnode.getchildren())==0:
        groupnode.delete2();

# For composing a group's properties onto its children (also group-like objects like Uses)        
Itmat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0));
def compose_all(el,clipurl,maskurl,transform,style):
    if style is not None:                                                         # style must go first since we may change it with CSS
        mysty = cascaded_style2(el);
        compsty = style + mysty                
        compsty['opacity']=str(float(mysty.get('opacity','1'))*float(style.get('opacity','1')))  # opacity accumulates at each layer
        el.lstyle = compsty;                                                       
    
    if clipurl is not None:   cout = merge_clipmask(el, clipurl)        # clip applied before transform, fix first
    if maskurl is not None:   merge_clipmask(el, maskurl, mask=True)
    if clipurl is not None:   fix_css_clipmask(el);
    if maskurl is not None:   fix_css_clipmask(el,mask=True);
    
    # t1 = el.ltransform;
    # t2 = el.transform;
    # if abs(t1.a-t2.a)>.001 or abs(t1.b-t2.b)>.001 or abs(t1.c-t2.c)>.001 or abs(t1.d-t2.d)>.001 or abs(t1.e-t2.e)>.001 or abs(t1.f-t2.f)>.001:
    #     idebug([t1.a,t1.b,t1.c,t1.d,t1.e,t1.f])
    #     idebug([t2.a,t2.b,t2.c,t2.d,t2.e,t2.f])
    #     idebug('\n')
    if transform is not None: el.ltransform = transform @ el.ltransform
    
    
    
    # if transform.matrix!=Itmat:
    #     myt = el.transform
    #     if myt.matrix==Itmat: el.transform = transform
    #     else:                 el.transform = vmult(transform,myt)
    
    # if [el2.get_id()=='tspan6056' for el2 in descendants2(el.root)]:
    #     debug(el.get_id())
    
    if clipurl is None:
        return False
    else:
        return cout

        


# If an element has clipping/masking specified in a stylesheet, this will override any attributes
# I think this is an Inkscape bug
# Fix by creating a style specific to my id that includes the new clipping/masking
def fix_css_clipmask(el,mask=False):
    if not(mask): cm = 'clip-path'
    else:         cm = 'mask'
    
    svg = get_parent_svg(el);
    if svg is not None:        cssdict = svg.cssdict;
    else:                      cssdict = dict();

    mycss = cssdict.get(el.get_id());
    if mycss is not None:
        if mycss.get(cm) is not None and mycss.get(cm)!=el.get(cm):
            svg = get_parent_svg(el)
            if not(hasattr(svg,'stylesheet_entries')):
                svg.stylesheet_entries = dict();
            svg.stylesheet_entries['#'+el.get_id()]=cm+':'+el.get(cm);
            mycss[cm]=el.get(cm);
    if el.lstyle.get(cm) is not None: # also clear local style
        Set_Style_Comp(el,cm,None);

# Adding to the stylesheet is slow, so as a workaround we only do this once
# There is no good way to do many entries at once, so we do it after we're finished 
def flush_stylesheet_entries(svg):
    if hasattr(svg,'stylesheet_entries'):
        ss = ''
        for k in svg.stylesheet_entries.keys():
            ss += k + '{'+svg.stylesheet_entries[k]+'}\n';
        svg.stylesheet_entries = dict()
        
        stys = svg.xpath('svg:style')
        if len(stys)>0:
            stys[0].text +='\n'+ss+'\n'

# Like duplicate, but randomly sets the id of all descendants also
# Normal duplicate does not
def duplicate2(el):
    svg = get_parent_svg(el);
    svg.iddict; svg.cssdict; # need to generate now to prevent problems in duplicate_fixed (el.addnext(elem) line, no idea why)
    
    d = duplicate_fixed(el);
    dupe_in_cssdict(el.get_id2(),d.get_id2(),get_parent_svg(el))
    add_to_iddict(d);
    
    for k in descendants2(d)[1:]:
        if not(isinstance(k,lxml.etree._Comment)):
            oldid = k.get_id2();
            set_random_id2(k);
            dupe_in_cssdict(oldid,k.get_id2(),get_parent_svg(k))
            add_to_iddict(k);
    return d

def duplicate_fixed(el): # fixes duplicate's set_random_id
    """Like copy(), but the copy stays in the tree and sets a random id"""
    elem = el.copy()
    el.addnext(elem)
    set_random_id2(elem)
    return elem

# Makes a new object and adds it to the dicts, inheriting CSS dict entry from another element
def new_element(genin,inheritfrom):
    g = genin();                            # e.g Rectangle
    inheritfrom.root.append(g);             # add to the SVG so we can assign an id
    dupe_in_cssdict(get_id2(inheritfrom),get_id2(g),inheritfrom.root)
    add_to_iddict(g);
    return g

# Replace an element with another one
# Puts it in the same location, update the ID dicts
def replace_element(el1,el2):
    # replace el1 with el2
    myp = el1.getparent();
    myi = list(myp).index(el1);
    myp.insert(myi+1,el2);
    
    newid = get_id2(el1);
    oldid = get_id2(el2);
    
    el1.delete2();
    el2.set_id(newid)
    add_to_iddict(el2,todel=oldid);
    dupe_in_cssdict(oldid,newid,el2.root)

def intersect_paths(ptha,pthb):
    # Intersect two rectangular paths. Could be generalized later
    ptsa = list(ptha.end_points);
    ptsb = list(pthb.end_points);
    x1c = max(min([p.x for p in ptsa]),min([p.x for p in ptsb]))
    x2c = min(max([p.x for p in ptsa]),max([p.x for p in ptsb]))
    y1c = max(min([p.y for p in ptsa]),min([p.y for p in ptsb]))
    y2c = min(max([p.y for p in ptsa]),max([p.y for p in ptsb]))
    w = x2c-x1c; h=y2c-y1c;
    
    if w>0 and h>0:
        return Path('M '+str(x1c)+','+str(y1c)+' h '+str(w)+' v '+str(h)+' h '+str(-w)+' Z');
    else:
        return Path('')

# Like uniquetol in Matlab
import numpy as np
def uniquetol(A,tol):
    Aa = np.array(A);
    ret = Aa[~(np.triu(np.abs(Aa[:,None] - Aa) <= tol,1)).any(0)]
    return type(A)(ret)

def merge_clipmask(node,newclipurl,mask=False):
# Modified from Deep Ungroup
    def isrectangle(el):
        isrect = False;
        if isinstance(el,(PathElement,Rectangle,Line,Polyline)):
            pth = Path(get_path2(el)).to_absolute();
            pth = pth.transform(el.ltransform)
            
            pts = list(pth.control_points);
            xs = []; ys = [];
            for p in pts:
                xs.append(p.x); ys.append(p.y)
                
            maxsz = max(max(xs)-min(xs),max(ys)-min(ys))
            tol=1e-3*maxsz;
            if 4<=len(xs)<=5 and len(uniquetol(xs,tol))==2 and len(uniquetol(ys,tol))==2:
                isrect = True;
        if isrect:
            return True,pth
        else:
            return False,None
    def compose_clips(el,ptha,pthb):
        newpath = intersect_paths(ptha,pthb);
        isempty = (str(newpath)=='');
        
        if not(isempty):
            myp = el.getparent();
            p=new_element(PathElement,el); myp.append(p)
            p.set('d',newpath);
        el.delete2()
        return isempty # if clipped out, safe to delete element

    if newclipurl is not None:
        svg = get_parent_svg(node);
        cmstr   = 'clip-path'
        if mask: cmstr='mask'
            
        if node.ltransform is not None:
            # Clip-paths on nodes with a transform have the transform
            # applied to the clipPath as well, which we don't want. 
            # Duplicate the new clip and apply node's inverse transform to its children.
            clippath = getElementById2(svg,newclipurl[5:-1])
            if clippath is not None:    
                d = duplicate2(clippath); 
                svg.defs2.append(d)
                # idebug([d.get_id(),d.getparent().get_id()])
                if not(hasattr(svg,'newclips')):
                    svg.newclips = []
                svg.newclips.append(d)            # for later cleanup
                for k in list(d):
                    compose_all(k,None,None,-node.ltransform,None)
                newclipurl = get_id2(d,2)
        
        newclipnode = getElementById2(svg,newclipurl[5:-1]);
        if newclipnode is not None:
            for k in list(newclipnode):
                if isinstance(k,(Use)): k = unlink2(k)

        oldclipurl = node.get(cmstr);
        clipinvalid = True;
        if oldclipurl is not None:
            # Existing clip is replaced by a duplicate, then apply new clip to children of duplicate
            oldclipnode = getElementById2(svg,oldclipurl[5:-1]);
            if oldclipnode is not None:
                clipinvalid = False;
                for k in list(oldclipnode):
                    if isinstance(k,(Use)): k = unlink2(k)
                    
                d = duplicate2(oldclipnode); # very important to use dup2 here
                if not(hasattr(svg,'newclips')):
                    svg.newclips = []
                svg.newclips.append(d)            # for later cleanup
                svg.defs2.append(d);               # move to defs
                node.set(cmstr,get_id2(d,2));
                
                newclipisrect = False
                if len(list(newclipnode))==1:
                    newclipisrect,newclippth = isrectangle(list(newclipnode)[0])
                
                couts = [];
                for k in reversed(list(d)): # may be deleting, so reverse
                    oldclipisrect,oldclippth = isrectangle(k)
                    if newclipisrect and oldclipisrect and mask==False:
                        # For rectangular clips, we can compose them easily
                        # Since most clips are rectangles this semi-fixes the PDF clip export bug 
                        cout = compose_clips(k,newclippth,oldclippth); 
                    else:
                        cout = merge_clipmask(k,newclipurl,mask);
                    couts.append(cout)
                cout = all(couts)
        
        if clipinvalid:
            node.set(cmstr,newclipurl)
            cout = False
                
        return cout


# Repeated getElementById lookups can be really slow, so instead create a lazy iddict property.
# When an element is created that may be needed later, it must be added using add_to_iddict. 
def getElementById2(svg,elid):
    return svg.iddict.get(elid);   
def add_to_iddict(el,todel=None):
    svg = get_parent_svg(el);
    svg.iddict[get_id2(el)] = el;
    if todel is not None:
        del svg.iddict[todel];
def getiddict(svg):
    if not(hasattr(svg,'_iddict')):
        svg._iddict = dict();
        for el in descendants2(svg):
            svg._iddict[get_id2(el)] = el;
    return svg._iddict
inkex.SvgDocumentElement.iddict = property(getiddict)

# A lazy list of all descendants of an svg (not necessarily in order)
def getldescendants(svg):
    # if 'image7824' not in svg.iddict.keys():
    #     idebug('Error')
    # else:
    #     idebug('yay')
    #     idebug([elid for elid in set(list(svg.iddict.keys()))])
    #     idebug([el.get_id() for el in set(list(svg.iddict.values()))])
    # if not(hasattr(svg,'_iddict')):
    #     getiddict(svg)
    return list(svg.iddict.values())
inkex.SvgDocumentElement.ldescendants = property(getldescendants)

# Deletes an element from lazy dicts on deletion
def delete2(el):
    svg = get_parent_svg(el);
    if svg is not None:
        try:             del svg.iddict[get_id2(el)]
        except KeyError: pass
    el.delete();
inkex.BaseElement.delete2 = delete2

def defs2(svg):
# Defs get that avoids xpath. Looks for a defs under the svg
    if not(hasattr(svg,'_defs2')):
        for k in list(svg):
            if isinstance(k,(inkex.Defs)):
                svg._defs2 = k;
                return svg._defs2
        d = new_element(inkex.Defs, svg)
        svg.insert(0,d)
        svg._defs2 = d;
    return svg._defs2
inkex.SvgDocumentElement.defs2 = property(defs2)
            

# The built-in get_unique_id gets stuck if there are too many elements. Instead use an adaptive
# size based on the current number of ids
# Modified from Inkex's get_unique_id
import random
# random.seed(1)
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
    debug(new_id)
    return new_id
# Version that is non-random, useful for debugging
# global idcount
# idcount = 1;
# def get_unique_id2(svg, prefix):
#     ids = svg.get_ids()
#     new_id = None; global idcount
#     while new_id is None or new_id in ids:
#         # Do not use randint because py2/3 incompatibility
#         new_id = prefix + str(idcount); idcount+=1
#     svg.ids.add(new_id)
#     return new_id
def set_random_id2(el, prefix=None, size=4, backlinks=False):
    """Sets the id attribute if it is not already set."""
    prefix = str(el) if prefix is None else prefix
    el.set_id(get_unique_id2(el.root,prefix), backlinks=backlinks)
    
# Like get_id(), but calls set_random_id2
# Modified from Inkex's get_id
def get_id2(el, as_url=0):
    """Get the id for the element, will set a new unique id if not set.
    as_url - If set to 1, returns #{id} as a string
             If set to 2, returns url(#{id}) as a string
    """
    if 'id' not in el.attrib:
        set_random_id2(el,el.TAG)
        # idebug('unassigned '+el.getparent().get_id())
    eid = el.get('id')
    if as_url > 0:
        eid = '#' + eid
    if as_url > 1:
        eid = f'url({eid})'
    return eid
inkex.BaseElement.get_id2 = get_id2

# e.g., bbs = dh.Get_Bounding_Boxes(self.options.input_file);
def Get_Bounding_Boxes(s=None,getnew=False,filename=None,pxinuu=None,inkscape_binary=None):
# Gets all of a document's bounding boxes (by ID), in user units
# Note that this uses a command line call, so by default it will only get the values from BEFORE the extension is called
# Set getnew to True to make a temporary copy of the file that is then read. 
    if filename is None:
        filename = s.options.input_file;
    if pxinuu is None:
        pxinuu = s.svg.unittouu('1px');
    
    # Query Inkscape
    if not(getnew):
        tFStR = commandqueryall(filename,inkscape_binary=inkscape_binary);
    else:
        tmpname = filename+'_tmp';
        command.write_svg(s.svg,tmpname);
        tFStR = commandqueryall(tmpname,inkscape_binary=inkscape_binary);
        import os; os.remove(tmpname);

    # Parse the output
    tBBLi = tFStR.splitlines()
    bbs=dict();
    for d in tBBLi:
        key = str(d).split(',')[0];
        if key[0:2]=='b\'': # pre version 1.1
            key = key[2:];
        if str(d)[2:52]=='WARNING: Requested update while update in progress':
            continue;                       # skip warnings (version 1.0 only?)
        data = [float(x.strip('\''))*pxinuu for x in str(d).split(',')[1:]]
        bbs[key] = data;
    return bbs

# 2022.02.03: I think the occasional hangs come from the call to command.
# I think this is more robust. Make a tally below if it freezes:
def commandqueryall(fn,inkscape_binary=None):
    if inkscape_binary is None:
        bfn = Get_Binary_Loc();
    else:
        bfn = inkscape_binary
    arg2 = [bfn, '--query-all',fn]

    p=subprocess_repeat(arg2);
    tFStR = p.stdout
    return tFStR

# In the event of a timeout, repeat subprocess call several times    
def subprocess_repeat(argin):
    BASE_TIMEOUT = 60
    NATTEMPTS = 4
    
    import subprocess
    nfails = 0; ntime = 0;
    for ii in range(NATTEMPTS):
        timeout = BASE_TIMEOUT*(ii+1);
        try:
            p=subprocess.run(argin, shell=False,timeout=timeout,stdout=subprocess.PIPE, stderr=subprocess.DEVNULL);
            break;
        except subprocess.TimeoutExpired:
            nfails+=1; ntime+=timeout;
    if nfails==NATTEMPTS:
        inkex.utils.errormsg('Error: The call to the Inkscape binary timed out '+str(NATTEMPTS)+\
                             ' times in '+str(ntime)+' seconds.\n\n'+\
                             'This may be a temporary issue; try running the extension again.');
        quit()
    else:
        return p
        
global debugs
debugs = ''
def debug(x):
    # inkex.utils.debug(x);
    global debugs
    if debugs!='': debugs += '\n'
    debugs += str(x)
def write_debug():
    global debugs
    if debugs!='':
        debugname = 'Debug.txt'
        f = open(debugname, 'w',encoding="utf-8");
        f.write(debugs);
        f.close();
def idebug(x):
    inkex.utils.debug(x);

def get_parent_svg(el):
    if not(hasattr(el,'svg')):
        # slightly faster than el.root
        myn = el
        while myn.getparent() is not None:
            myn = myn.getparent();
        if isinstance(myn,SvgDocumentElement):    
            el.svg = myn;
        else:
            el.svg = None
    return el.svg
    


# Modified from Inkex's get function
# Does not fail on comments
def get_mod(slf, *types):
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
                        # ts = new_element(Tspan,el);
                        # ts.text = w; ts.lstyle=sty+'font-family:'+newfont
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
    if myp is None: prt=Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]);
    else:           prt=myp.lcomposed_transform;   
    prt = (Transform('scale('+str(vscale(get_parent_svg(el)))+')') @ prt);  # also include document scaling
    
    myt = el.get('transform');
    if myt==None:
        newtr=(-prt) @ trnsfrm @ prt;
        if trange is not None:
            for ii in range(len(trange)):
                trange[ii] = ((-prt) @ trange[ii] @ prt)
    else:
        newtr=(-prt) @ trnsfrm @ prt @ Transform(myt)
        if trange is not None:
            for ii in range(len(trange)):
                trange[ii] = (-prt) @ trange[ii] @ prt @ Transform(myt)
    
    sw = Get_Composed_Width(el,'stroke-width');
    sd = Get_Composed_List(el, 'stroke-dasharray');
    
    # t1 = el.composed_transform(); t2 =el.lcomposed_transform;
    # if abs(t1.a-t2.a)>.001 or abs(t1.b-t2.b)>.001 or abs(t1.c-t2.c)>.001 or abs(t1.d-t2.d)>.001 or abs(t1.e-t2.e)>.001 or abs(t1.f-t2.f)>.001:
    #     idebug(el.get_id2())
    #     idebug(t1)
    #     idebug(t2)
    #     raise TypeError
    
    el.ltransform = newtr;
    # el.set('transform',newtr); # Add the new transform
    
    # t1 = el.composed_transform(); t2 =el.lcomposed_transform;
    # if abs(t1.a-t2.a)>.001 or abs(t1.b-t2.b)>.001 or abs(t1.c-t2.c)>.001 or abs(t1.d-t2.d)>.001 or abs(t1.e-t2.e)>.001 or abs(t1.f-t2.f)>.001:
    #     idebug(el.get_id2())
    #     idebug(t1)
    #     idebug(t2)
    #     raise TypeError
    
    ApplyTransform().recursiveFuseTransform(el,irange=irange,trange=trange);
    
    if sw is not None:
        neww, sf, ct, ang = Get_Composed_Width(el,'stroke-width',nargout=4);
        Set_Style_Comp(el,'stroke-width',str(sw/sf));                                            # fix width
    if not(sd in [None,'none']):
        nd,sf = Get_Composed_List(el,'stroke-dasharray',nargout=2);
        Set_Style_Comp(el,'stroke-dasharray',str([sdv/sf for sdv in sd]).strip('[').strip(']')); # fix dash


# Modified from Inkex's get_path          
# Correctly calculates path for rectangles and ellipses  
def get_path2(el):
    class MiniRect(): # mostly from inkex.elements._polygons
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
    class MiniEllipse():  # mostly from inkex.elements._polygons
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
otp_support = (inkex.Rectangle,inkex.Ellipse,inkex.Circle,inkex.Polygon,inkex.Polyline,inkex.Line);
def object_to_path(el):
    if not(isinstance(el,(inkex.PathElement,inkex.TextElement))):
        pth = get_path2(el);
        el.tag = '{http://www.w3.org/2000/svg}path';
        el.set('d',str(pth));


# Delete and prune empty ancestor groups       
def deleteup(el):
    myp = el.getparent();
    el.delete2()
    if myp is not None:
        myc = myp.getchildren();
        if myc is not None and len(myc)==0:
            deleteup(myp)

# Combines a group of path-like elements
def combine_paths(els,mergeii=0):
    pnew = Path();
    si = [];  # start indices
    for el in els:
        pth = Path(el.get_path()).to_absolute().transform(el.lcomposed_transform);
        if el.get('inkscape-academic-combined-by-color') is None:
            si.append(len(pnew))
        else:
            cbc = el.get('inkscape-academic-combined-by-color') # take existing ones and weld them
            cbc = [int(v) for v in cbc.split()]
            si += [v+len(pnew) for v in cbc[0:-1]]
        for p in pth:
            pnew.append(p)
    si.append(len(pnew))
    
    # Set the path on the mergeiith element
    mel  = els[mergeii]
    if mel.get('d') is None: # Polylines and lines have to be converted to a path
        object_to_path(mel)
    mel.set('d',str(pnew.transform(-mel.lcomposed_transform)));
    
    # Release clips/masks    
    mel.set('clip-path','none'); # release any clips
    mel.set('mask'     ,'none'); # release any masks
    fix_css_clipmask(mel,mask=False) # fix CSS bug
    fix_css_clipmask(mel,mask=True)
    
    mel.set('inkscape-academic-combined-by-color',' '.join([str(v) for v in si]))
    for s in range(len(els)):
        if s!=mergeii:
            deleteup(els[s])    
            
# Gets all of the stroke and fill properties from a style
def get_strokefill(el,styin=None):
    if styin is None:
        sty = specified_style2(el)
    else:
        sty = styin
    strk = sty.get('stroke',None)
    fill = sty.get('fill',None)
    op     = float(sty.get('opacity',1.0))
    nones = [None,'none','None'];
    if not(strk in nones):    
        try:
            strk   = inkex.Color(strk).to_rgb()
            strkl  = strk.lightness
            strkop = float(sty.get('stroke-opacity',1.0))
            strk.alpha = strkop*op
            strkl  = strk.alpha * strkl/255 + (1-strk.alpha)*1; # effective lightness frac with a white bg
            strk.efflightness = strkl
        except:# inkex.colors.ColorIdError:
            strk  = None
            strkl = None
    else:
        strk = None
        strkl = None
    if not(fill in nones):
        try:
            fill   = inkex.Color(fill).to_rgb()
            filll  = fill.lightness
            fillop = float(sty.get('fill-opacity',1.0))
            fill.alpha = fillop*op
            filll  = fill.alpha * filll/255 + (1-fill.alpha)*1;  # effective lightness frac with a white bg
            fill.efflightness = filll
        except:# inkex.colors.ColorIdError:
            fill   = None
            filll  = None
    else:
        fill = None
        filll = None
        
    sw = Get_Composed_Width(el, 'stroke-width'   ,styin=sty)
    sd = Get_Composed_List(el, 'stroke-dasharray',styin=sty)
    if sd in nones: sd = None
    if sw in nones or sw==0 or strk is None:
        sw  = None;
        strk= None;
        sd  = None;
        
    ms = sty.get('marker-start',None);
    mm = sty.get('marker-mid',None);
    me = sty.get('marker-end',None);
    
    class StrokeFill():
        def __init__(self,*args):
            (self.stroke,self.fill,self.strokewidth,self.strokedasharray,\
             self.markerstart,self.markermid,self.markerend)=args
    return StrokeFill(strk,fill,sw,sd,ms,mm,me)
        
# Gets the caller's location
import os, sys
def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))

# Return a document's visible descendants not in Defs/Metadata/etc
def visible_descendants(svg):
    ndefs = [el for el in list(svg) if not(isinstance(el,((inkex.NamedView, inkex.Defs, \
                                                           inkex.Metadata,  inkex.ForeignObject))))]; 
    return [v for el in ndefs for v in descendants2(el)];

# Gets the location of the Inkscape binary
# Functions copied from command.py
# Copyright (C) 2019 Martin Owens
def Get_Binary_Loc():
    from lxml.etree import ElementTree
    INKSCAPE_EXECUTABLE_NAME = os.environ.get('INKSCAPE_COMMAND')
    if INKSCAPE_EXECUTABLE_NAME == None:
        if sys.platform == 'win32':
            # prefer inkscape.exe over inkscape.com which spawns a command window
            INKSCAPE_EXECUTABLE_NAME = 'inkscape.exe'
        else:
            INKSCAPE_EXECUTABLE_NAME = 'inkscape'
    class CommandNotFound(IOError):
        pass
    def which(program):
        if os.path.isabs(program) and os.path.isfile(program):
            return program
        try:
            # Python2 and python3, but must have distutils and may not always
            # work on windows versions (depending on the version)
            from distutils.spawn import find_executable
            prog = find_executable(program)
            if prog:
                return prog
        except ImportError:
            pass
        try:
            # Python3 only version of which
            from shutil import which as warlock
            prog = warlock(program)
            if prog:
                return prog
        except ImportError:
            pass # python2
        try:
            import sys
            for sp in sys.path:
                prog = find_executable(program,path=sp)
                if prog:
                    return prog
        except ImportError:
            pass
        raise CommandNotFound(f"Can not find the command: '{program}'")
    return which(INKSCAPE_EXECUTABLE_NAME)

# Get document location or prompt
def Get_Current_File(ext):
    tooearly = (ivp[0]<=1 and ivp[1]<1);
    if not(tooearly):
        myfile = ext.document_path()
    else:
        myfile = None
        
    if myfile is None or myfile=='':
        if tooearly:
            msg = 'Direct export requires version 1.1.0 of Inkscape or higher.'
        else:
            msg = 'Direct export requires the SVG be saved first. Please save and retry.'
        inkex.utils.errormsg(msg);
        quit()
        return None
    else:
        import os
        return myfile


# Version checking
try:
    inkex_version = inkex.__version__; # introduced in 1.1.2
except:
    try:
        tmp=inkex.BaseElement.unittouu # introduced in 1.1
        inkex_version = '1.1.0'
    except:
        try:
            from inkex.paths import Path, CubicSuperPath
            inkex_version = '1.0.0';
        except:
            inkex_version = '0.92.4';

def vparse(vstr):
    return [int(v) for v in vstr.split('.')]
ivp = vparse(inkex_version);

# Version-specific document scale
def vscale(svg):
    try:
        return svg.oldscale                 # I never change doc size, so it's fine to store it for unnecessary lookups
    except:
        if ivp[0]<=1 and ivp[1]<2:          # pre-1.2: return scale
            svg.oldscale = svg.scale
        else:                               # post-1.2: return old scale          
            scale_x = float((svg.unittouu(svg.get('width' ))) or (svg.get_viewbox()[2]))  / float(svg.get_viewbox()[2])
            scale_y = float((svg.unittouu(svg.get('height'))) or (svg.get_viewbox()[3]))  / float(svg.get_viewbox()[3])
            svg.oldscale = max([scale_x, scale_y])
            return svg.oldscale
        return svg.oldscale

# Add @ multiplication to old versions of Inkex
It = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]);
try:                tmp = It@It
except TypeError:   inkex.transforms.Transform.__matmul__ = lambda a,b : a*b

    
# Version-specific multiplication
# def vmult(*args):
#     outval = args[-1];
#     for ii in reversed(range(0,len(args)-1)):
#         if ivp[0]<=1 and ivp[1]<2:      # pre-1.2: use asterisk
#             outval = args[ii]*outval;
#         else:                           # post-1.2: use @
#             outval = args[ii]@outval;
#     return outval

def isMask(el):
    if ivp[0]<=1 and ivp[1]<2:          # pre-1.2: check tag
        return (el.tag[-4:]=='mask')
    else:               
        return isinstance(el, (inkex.Mask))
    
def vto_xpath(sty):
    if ivp[0]<=1 and ivp[1]<2:      # pre-1.2: use v1.1 version of to_xpath from inkex.Style
        import re
        step_to_xpath = [
            (re.compile(r'\[(\w+)\^=([^\]]+)\]'), r'[starts-with(@\1,\2)]'), # Starts With
            (re.compile(r'\[(\w+)\$=([^\]]+)\]'), r'[ends-with(@\1,\2)]'), # Ends With
            (re.compile(r'\[(\w+)\*=([^\]]+)\]'), r'[contains(@\1,\2)]'), # Contains
            (re.compile(r'\[([^@\(\)\]]+)\]'), r'[@\1]'), # Attribute (start)
            (re.compile(r'#(\w+)'), r"[@id='\1']"), # Id Match
            (re.compile(r'\s*>\s*([^\s>~\+]+)'), r'/\1'), # Direct child match
            #(re.compile(r'\s*~\s*([^\s>~\+]+)'), r'/following-sibling::\1'),
            #(re.compile(r'\s*\+\s*([^\s>~\+]+)'), r'/following-sibling::\1[1]'),
            (re.compile(r'\s*([^\s>~\+]+)'), r'//\1'), # Decendant match
            (re.compile(r'\.([-\w]+)'), r"[contains(concat(' ', normalize-space(@class), ' '), ' \1 ')]"),
            (re.compile(r'//\['), r'//*['), # Attribute only match
            (re.compile(r'//(\w+)'), r'//svg:\1'), # SVG namespace addition
        ]
        def style_to_xpath(styin):
            return '|'.join([rule_to_xpath(rule) for rule in styin.rules])
        def rule_to_xpath(rulein):
            ret = rulein.rule
            for matcher, replacer in step_to_xpath:
                ret = matcher.sub(replacer, ret)
            return ret
        return style_to_xpath(sty)
    else:
        return sty.to_xpath();
    
    
def Version_Check(caller):
    siv = 'v1.4.16'         # Scientific Inkscape version
    maxsupport = '1.2.0';
    minsupport = '1.1.0';
    
    logname = 'Log.txt'
    NFORM = 200;
    
    maxsupp = vparse(maxsupport);
    minsupp = vparse(minsupport);
    
    try:
        f = open(logname,'r');
        d = f.readlines(); f.close();
    except:
        d = [];    
    
    displayedform = False;
    if len(d)>0:
        displayedform = d[-1]=='Displayed form screen'
        if displayedform:
            d=d[:len(d)-1];
    
    # idebug(ivp)
    prevvp = [vparse(dv[-6:]) for dv in d]
    if (ivp[0]<minsupp[0] or ivp[1]<minsupp[1]) and not(ivp in prevvp):
        msg = 'Scientific Inkscape requires Inkscape version '+minsupport+' or higher. '+\
              'You are running a less-recent version—it might work, it might not.\n\nThis is a one-time message.\n\n';
        inkex.utils.errormsg(msg);
    if (ivp[0]>maxsupp[0] or ivp[1]>maxsupp[1]) and not(ivp in prevvp):
        msg = 'Scientific Inkscape requires Inkscape version '+maxsupport+' or lower. '+\
              'You are running a more-recent version—you must be from the future!\n\n'+\
              'It might work, it might not. Check if there is a more recent version of Scientific Inkscape available. \n\nThis is a one-time message.\n\n';
        inkex.utils.errormsg(msg);
    
    from datetime import datetime
    dt = datetime.now().strftime("%Y.%m.%d, %H:%M:%S")
    d.append(dt+' Running '+caller+' '+siv+', Inkscape v'+inkex_version+'\n');
    
    if len(d)>NFORM:
        d = d[-NFORM:];
        if not(displayedform):
            sif3 = 'dt9mt3Br6';
            sif1 = 'https://forms.gle/'
            sif2 = 'RS6HythP';
            msg = 'You have run Scientific Inkscape extensions over '+\
                str(NFORM)+' times! Thank you for being such a dedicated user!'+\
                '\n\nBuilding and maintaining Scientific Inkscape is a time-consuming job,'+\
                ' and I have no real way of tracking the number of active users. For reporting purposes, I would greatly '+\
                "appreciate it if you could sign my guestbook to indicate that you use Scientific Inkscape. "+\
                'It is located at\n\n'+sif1+sif2+sif3+'\n\nPlease note that this is a one-time message. '+\
                'You will never get this message again, so please copy the URL before you click OK.\n\n';
            inkex.utils.errormsg(msg);
        d.append('Displayed form screen')

    try:        
        f = open(logname, 'w');
        f.write(''.join(d));
        f.close();
    except:
        inkex.utils.errormsg('Error: You do not have write access to the directory where the Scientific Inkscape '+\
                             'extensions are installed. You may have not installed them in the correct location. '+\
                             '\n\nMake sure you install them in the User Extensions directory, not the Inkscape Extensions '+\
                             'directory.');
        quit();
    
