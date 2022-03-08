#!/usr/bin/env python 
# coding=utf-8
#
# Copyright (c) 2020 David Burghoff <dburghoff@nd.edu>
#
# Functions modified from Inkex were made by
#                    Martin Owens <doctormo@gmail.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Thomas Holder <thomas.holder@schrodinger.com>
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

TIMEOUT = 60;


import inkex
from inkex import (
    TextElement, FlowRoot, FlowPara, FlowSpan, Tspan, TextPath, Rectangle, \
        addNS, Transform, ClipPath, Use, NamedView, Defs, \
        Metadata, ForeignObject, Vector2d, Path, Line, PathElement,command,\
        SvgDocumentElement,Image,Group,Polyline,Anchor,Switch,ShapeElement, BaseElement,FlowRegion)
from applytransform_mod import ApplyTransform
import lxml, math
from lxml import etree  
from Style2 import Style2



def descendants2(el):
    # Like Inkex's descendants(), but avoids recursion to avoid recursion depth issues
    cel = el;
    keepgoing = True; childrendone = False;
    descendants = [];
    
    # To avoid repeated lookups of each element's children and index, make dicts
    # that store them once they've been looked up
    children_dict = dict();
    index_dict = dict();
    def getchildren_dict(eli):
        if not(eli in children_dict):
            children_dict[eli] = list(eli)               # getchildren deprecated
            for ii in range(len(children_dict[eli])):
                index_dict[children_dict[eli][ii]] = ii; # store index for later
        return children_dict[eli]
    def myindex(eli):   # index amongst siblings
        if not(eli in index_dict):
            index_dict[eli] = getchildren_dict(eli.getparent()).index(eli); # shouldn't need, just in case
        return index_dict[eli]
    
    while keepgoing:
        keepgoing = False;
        if not(childrendone):
            descendants.append(cel); 
            ks = getchildren_dict(cel);
            if len(ks)>0: # try children
                cel = ks[0];
                keepgoing = True; childrendone = False; continue;
        
        if cel==el:
            keepgoing = False; continue;
        else:
            par  = cel.getparent();
            sibs = getchildren_dict(par)
            myi = myindex(cel)
            if myi!=len(sibs)-1: # try younger siblings
                cel = sibs[myi+1];
                keepgoing = True; childrendone = False; continue;
            else:
                cel = par;
                keepgoing = True; childrendone = True; continue;
    descendants = [v for v in descendants if isinstance(v, (BaseElement, str))]
    return descendants;

# Sets a style property  
def Set_Style_Comp(el_or_sty,comp,val):
    isel = isinstance(el_or_sty,(BaseElement))  # is element
    if isel:
        sty = el_or_sty.get('style');
    else:
        isstr = isinstance(el_or_sty,(str))
        if not(isstr):                          # is style string
            sty = str(el_or_sty)
        else:                                   # is Style element
            sty = el_or_sty

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
        el_or_sty.set('style',sty);             # set element style
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
# Modified from Inkex's cascaded_style
    global cssdict
    if cssdict is None:
        # Generate a dictionary of styles at least once so we don't have to do constant lookups
        # If elements change, will need to rerun by setting cssdict to None
        generate_cssdict(get_parent_svg(el));
    csssty = cssdict.get(el.get_id());
    # locsty = el.style;
    locsty = Style2(el.get('style'));
    
    # Add any presentation attributes to local style
    attr = list(el.keys());
    attsty = Style2('');
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
                if elid is not None and style!=inkex.Style():  # still using Inkex's Style here since from stylesheets
                    if cssdict.get(elid) is None:
                        cssdict[elid] = Style2() + style;
                    else:
                        cssdict[elid] += style;

# For style components that represent a size (stroke-width, font-size, etc), calculate
# the true size reported by Inkscape in user units, inheriting any styles/transforms/document scaling
def Get_Composed_Width(el,comp,nargout=1,styin=None,ctin=None):
    # cs = el.composed_style();
    if styin is None:                   # can pass styin to reduce extra style gets
        cs = selected_style_local(el);
    else:
        cs = styin;
    if ctin is None:                    # can pass ctin to reduce extra composed_transforms
        ct = el.composed_transform();
    else:
        ct = ctin;
    if nargout==4:
        ang = math.atan2(ct.c,ct.d)*180/math.pi;
    svg = get_parent_svg(el)
    docscale = vscale(svg);
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
        cs = selected_style_local(el);
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
        cs = selected_style_local(el);
    else:
        cs = styin
    ct = el.composed_transform();
    sc = Get_Style_Comp(cs,comp);
    docscale = vscale(get_parent_svg(el));
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
    mysvg = get_parent_svg(el);
    if mysvg is not None:
        docscale = vscale(get_parent_svg(el));
    else:
        docscale = 1;
    xs = []; ys = [];
    for p in pts:
        p = ct.apply_to_point(p);
        xs.append(p.x*docscale)
        ys.append(p.y*docscale)
    return xs, ys



def ungroup(groupnode):
    # Pops a node out of its group, unless it's already in a layer or the base
    # Unlink any clones that aren't glyphs
    # Remove any comments, Preserves style, clipping, and masking
    
    gparent = groupnode.getparent()
    gindex  = list(gparent).index(groupnode)   # group's location in parent
    gtransform = groupnode.transform
    gclipurl   = groupnode.get('clip-path')
    gmaskurl   = groupnode.get('mask')
            
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
            p.set('transform',vmult(Transform('translate('+str(tx)+','+str(ty)+')'),Transform(p.get('transform'))))
            el.delete(); el=p; el.set('unlinked_clone',True); #wasuse=True;
        elif isinstance(el,lxml.etree._Comment): # remove comments
            groupnode.remove(el)
        if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject, lxml.etree._Comment))):
            recursive_merge_clipmask(el, gclipurl)              # transform applies to clip, so do clip first
            recursive_merge_clipmask(el, gmaskurl, mask=True)   # also mask
            
            el.transform = vmult(gtransform,el.transform)
            el.style = shallow_composed_style(el)
            
            fix_css_clipmask(el,mask=True);
            fix_css_clipmask(el,mask=False);
                
            gparent.insert(gindex+1,el); # places above
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


# If an element has clipping/masking specified in a stylesheet, this will override any attributes
# I think this is an Inkscape bug
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


# Repeated getElementById lookups can be really slow, so instead create a dict that can be used to 
# speed this up. When an element is created that may be needed later, it MUST be added. 
def getElementById2(svg,elid):
    if hasattr(svg,'iddict'):
        iddict = svg.iddict
    else:
        generate_iddict(svg);
        iddict = svg.iddict
    return iddict.get(elid);    
def generate_iddict(svg):
    svg.iddict = dict();
    for el in descendants2(svg):
        svg.iddict[get_id2(el)] = el;
def add_to_iddict(el):
    svg = get_parent_svg(el);
    if hasattr(svg,'iddict'):
        iddict = svg.iddict
    else:
        generate_iddict(svg)
        iddict = svg.iddict
    iddict[get_id2(el)] = el;
def new_element(typein):
    ret = typein();
    add_to_iddict(ret)
    return ret
    
# The built-in get_unique_id gets stuck if there are too many elements. Instead use an adaptive
# size based on the current number of ids
# Modified from Inkex's get_unique_id
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
    eid = el.get('id')
    if as_url > 0:
        eid = '#' + eid
    if as_url > 1:
        eid = f'url({eid})'
    return eid

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
    import subprocess
    if inkscape_binary is None:
        bfn, tmp = Get_Binary_Loc(fn);
    else:
        bfn = inkscape_binary
    arg2 = [bfn, '--query-all',fn]
    # try:
    #     p=subprocess.run(arg2, shell=False,timeout=TIMEOUT,stdout=subprocess.PIPE, stderr=subprocess.DEVNULL);
    # except subprocess.TimeoutExpired:
    #     inkex.utils.errormsg('Error: The call to the Inkscape binary timed out after '+str(TIMEOUT)+' seconds.\n\n'+\
    #                          'This is usually a temporary issue; try running the extension again.');
    #     quit()
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
    prt = vmult(Transform('scale('+str(vscale(get_parent_svg(el)))+')'),prt);  # also include document scaling
    
    myt = el.get('transform');
    if myt==None:
        newtr=vmult((-prt),trnsfrm,prt);
        if trange is not None:
            for ii in range(len(trange)):
                trange[ii] = vmult((-prt),trange[ii],prt)
    else:
        newtr=vmult((-prt),trnsfrm,prt,Transform(myt))
        if trange is not None:
            for ii in range(len(trange)):
                trange[ii] = vmult((-prt),trange[ii],prt,Transform(myt))
    
    sw = Get_Composed_Width(el,'stroke-width');
    sd = Get_Composed_List(el, 'stroke-dasharray');
    
    el.set('transform',newtr); # Add the new transform
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


# Combines a group of path-like elements
def combine_paths(els,mergeii=0):
    # Delete and prune empty ancestor groups       
    def deleteup(el):
        myp = el.getparent();
        el.delete()
        if myp is not None:
            myc = myp.getchildren();
            if myc is not None and len(myc)==0:
                deleteup(myp)
                
    pnew = Path();
    si = [];  # start indices
    for el in els:
        pth = Path(el.get_path()).to_absolute().transform(el.composed_transform());
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
    mel.set('d',str(pnew.transform(-mel.composed_transform())));
    
    # Release clips/masks    
    mel.set('clip-path','none'); # release any clips
    mel.set('mask'     ,'none'); # release any masks
    fix_css_clipmask(mel,mask=False) # fix CSS bug
    fix_css_clipmask(mel,mask=True)
    
    mel.set('inkscape-academic-combined-by-color',' '.join([str(v) for v in si]))
    for s in range(len(els)):
        if s!=mergeii:
            deleteup(els[s])        
        
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
def Get_Binary_Loc(fin):
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
    class ProgramRunError(ValueError):
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
        raise CommandNotFound(f"Can not find the command: '{program}'")
    def write_svg(svg, *filename):
        filename = os.path.join(*filename)
        if os.path.isfile(filename):
            return filename
        with open(filename, 'wb') as fhl:
            if isinstance(svg, SvgDocumentElement):
                svg = ElementTree(svg)
            if hasattr(svg, 'write'):
                # XML document
                svg.write(fhl)
            elif isinstance(svg, bytes):
                fhl.write(svg)
            else:
                raise ValueError("Not sure what type of SVG data this is.")
        return filename
    def to_arg(arg, oldie=False):
        if isinstance(arg, (tuple, list)):
            (arg, val) = arg
            arg = '-' + arg
            if len(arg) > 2 and not oldie:
                arg = '-' + arg
            if val is True:
                return arg
            if val is False:
                return None
            return f"{arg}={str(val)}"
        return str(arg)
    def to_args(prog, *positionals, **arguments):
        args = [prog]
        oldie = arguments.pop('oldie', False)
        for arg, value in arguments.items():
            arg = arg.replace('_', '-').strip()    
            if isinstance(value, tuple):
                value = list(value)
            elif not isinstance(value, list):
                value = [value]    
            for val in value:
                args.append(to_arg((arg, val), oldie))
        args += [to_arg(pos, oldie) for pos in positionals if pos is not None]
        # Filter out empty non-arguments
        return [arg for arg in args if arg is not None]
    def _call(program, *args, **kwargs):
        stdin = kwargs.pop('stdin', None)
        if isinstance(stdin, str):
            stdin = stdin.encode('utf-8')
        return to_args(which(program), *args, **kwargs)
    def call(program, *args, **kwargs):
        return _call(program, *args, **kwargs)
    def inkscape2(svg_file, *args, **kwargs):
        return call(INKSCAPE_EXECUTABLE_NAME, svg_file, *args, **kwargs)
    return inkscape2(fin)

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
            scale_x = float(svg.unittouu(svg.get('width')))/ float(svg.get_viewbox()[2])
            scale_y = float(svg.unittouu(svg.get('height'))) / float(svg.get_viewbox()[3])
            svg.oldscale = max([scale_x, scale_y])
            return svg.oldscale
        return svg.oldscale
    
# Version-specific multiplication
def vmult(*args):
    outval = args[-1];
    for ii in reversed(range(0,len(args)-1)):
        if ivp[0]<=1 and ivp[1]<2:      # pre-1.2: use asterisk
            outval = args[ii]*outval;
        else:                           # post-1.2: use @
            outval = args[ii]@outval;
    return outval


    
def Version_Check(caller):
    siv = 'v1.4.9'         # Scientific Inkscape version
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
        
    f = open(logname, 'w');
    f.write(''.join(d));
    f.close();
    
