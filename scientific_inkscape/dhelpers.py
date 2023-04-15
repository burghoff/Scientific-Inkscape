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
    FlowPara,
    FlowSpan,
    Tspan,
    Rectangle,
    Transform,
    Use,
    NamedView,
    Defs,
    Metadata,
    ForeignObject,
    Path,
    Line,
    PathElement,
    SvgDocumentElement,
    Group,
    Polyline,
    ShapeElement,
    BaseElement,
)
from applytransform_mod import fuseTransform
import lxml, math, re, sys, os
from Style0 import Style0


def descendants2_old(el, return_tails=False):
    # Like Inkex's descendants(), but avoids recursion to avoid recursion depth issues
    # Excludes comments
    cel = el
    keepgoing = True
    childrendone = False
    descendants = []
    precedingtails = []

    # To avoid repeated lookups of each element's children and index, make dicts
    # that store them once they've been looked up
    children_dict = dict()
    parent_dict = dict()
    index_dict = dict()
    pendingtails = []

    def mlist(elv):
        return [v for v in elv if not(isinstance(v,lxml.etree._Comment))]

    def getchildren_dict(eli):
        if not (eli in children_dict):
            children_dict[eli] = mlist(eli)
            for ii, child in enumerate(children_dict[eli]):
                index_dict[child] = ii  # store index for later
        return children_dict[eli]

    def myindex(eli):  # index amongst siblings
        if not (eli in index_dict):
            index_dict[eli] = getchildren_dict(getparent_dict(eli)).index(eli)
            # shouldn't need, just in case
        return index_dict[eli]

    def getparent_dict(eli):
        if not (eli in parent_dict):
            parent_dict[eli] = eli.getparent()
        return parent_dict[eli]

    while keepgoing:
        keepgoing = False
        if not (childrendone):
            descendants.append(cel)
            precedingtails.append(pendingtails)
            pendingtails = []

            ks = getchildren_dict(cel)
            if len(ks) > 0:  # try children
                cel = ks[0]
                keepgoing = True
                childrendone = False
                continue
            else:
                pendingtails.append(cel)

        if cel == el:
            keepgoing = False
            continue
            # we're finished
        else:
            par = getparent_dict(cel)
            sibs = getchildren_dict(par)
            myi = myindex(cel)
            if myi != len(sibs) - 1:  # try younger siblings
                cel = sibs[myi + 1]
                keepgoing = True
                childrendone = False
                continue
            else:
                cel = par
                pendingtails.append(cel)
                keepgoing = True
                childrendone = True
                continue
    # descendants = [v for v in descendants if isinstance(v, (BaseElement, str))]
    # [d.get_id2() for d in descendants]

    if not (return_tails):
        return descendants
    else:
        # For each descendant return a list of elements whose tails 
        # would precede the descendant. There can be multiple tails.
        # Note that it will be one longer than descendants because the final
        # tail(s) will always be outside the descendant tree.
        precedingtails.append(pendingtails)
        return descendants, precedingtails, children_dict, parent_dict

def descendants2(el, return_tails=False):
    descendants = [el]
    precedingtails = [[]]
    endsat = [(el,None)]
    for d in el.iterdescendants():
        if not(isinstance(d,lxml.etree._Comment)):
            if return_tails:
                precedingtails.append([])
                while endsat[-1][1]==d:
                    precedingtails[-1].append(endsat.pop()[0])
                nsib = d.getnext()
                if nsib is None:
                    endsat.append((d,endsat[-1][1]))
                else:
                    endsat.append((d,nsib))
            descendants.append(d)

    if not return_tails:
        return descendants
    else:
        precedingtails.append([])
        while len(endsat)>0:
            precedingtails[-1].append(endsat.pop()[0])
        return descendants, precedingtails

BaseElement.descendants2 = descendants2





def dupe_cssdict_entry(oldid, newid, svg):
    # duplicate a style in cssdict
    if svg is not None:
        csssty = svg.cssdict.get(oldid)
        if csssty is not None:
            svg.cssdict[newid] = csssty


estyle = Style0()
estyle2 = inkex.Style()  # still using Inkex's Style here since from stylesheets
def get_cssdict(svg):
    try:
        return svg._cssdict
    except:
        # For certain xpaths such as classes, we can avoid xpath calls
        # by checking the class attributes on a document's descendants directly.
        # This is much faster for large documents.
        hasall = False
        simpleclasses = dict()
        simpleids = dict()
        c1 = re.compile(r"\.([-\w]+)")
        c2 = re.compile(r"#(\w+)")
        for sheet in svg.stylesheets:
            for style in sheet:
                xp = vto_xpath(style)
                if xp == "//*":
                    hasall = True
                elif all(
                    [c1.sub(r"IAMCLASS", r.rule) == "IAMCLASS" for r in style.rules]
                ):  # all rules are classes
                    simpleclasses[xp] = [c1.sub(r"\1", r.rule) for r in style.rules]
                elif all(
                    [c2.sub(r"IAMID", r.rule) == "IAMID" for r in style.rules]
                ):  # all rules are ids
                    simpleids[xp] = [c1.sub(r"\1", r.rule)[1:] for r in style.rules]

        knownxpaths = dict()
        if hasall or len(simpleclasses) > 0:
            ds = svg.cdescendants

            cs = [EBget(d,"class") for d in ds]
            if hasall:
                knownxpaths["//*"] = ds
            for xp in simpleclasses:
                knownxpaths[xp] = []
            for ii in range(len(ds)):
                if cs[ii] is not None:
                    cv = cs[ii].split(" ") 
                    # only valid delimeter for multiple classes is space
                    for xp in simpleclasses:
                        if any([v in cv for v in simpleclasses[xp]]):
                            knownxpaths[xp].append(ds[ii])
        for xp in simpleids:
            knownxpaths[xp] = []
            for sid in simpleids[xp]:
                idel = getElementById2(svg, sid)
                if idel is not None:
                    knownxpaths[xp].append(idel)

        # Now run any necessary xpaths and get the element styles
        cssdict = dict()
        for sheet in svg.croot.stylesheets:
            for style in sheet:
                try:
                    # els = svg.xpath(style.to_xpath())  # original code
                    xp = vto_xpath(style)
                    style0v = Style0(style)
                    if xp in knownxpaths:
                        els = knownxpaths[xp]
                    else:
                        els = svg.xpath(xp)
                    for elem in els:
                        elid = elem.get("id", None)
                        if elid is not None and style != estyle2: 
                            if cssdict.get(elid) is None:
                                cssdict[elid] = style0v.copy()
                            else:
                                cssdict[elid] += style
                except (lxml.etree.XPathEvalError, TypeError):
                    pass
        svg._cssdict = cssdict
        return svg._cssdict
inkex.SvgDocumentElement.cssdict = property(get_cssdict)


# fmt: off
# A cached specified style property
def get_cspecified_style(el):
    if not (hasattr(el, "_cspecified_style")):
        parent = el.getparent()
        if parent is not None and isinstance(
            parent, (ShapeElement, SvgDocumentElement)
        ):
            ret = parent.cspecified_style + el.ccascaded_style
        else:
            ret = el.ccascaded_style
        el._cspecified_style = ret
    return el._cspecified_style
def set_cspecified_style(el, si):
    # if si is None and hasattr(el, "_cspecified_style"):  # invalidate
    #     delattr(el, "_cspecified_style")
    #     for k in list(el):
    #         k.cspecified_style = None # invalidate children
    if si is None:
        try:  # 50% faster than hasattr check
            delattr(el, "_cspecified_style")
            for k in list(el):
                k.cspecified_style = None # invalidate children
        except:
            pass
BaseElement.cspecified_style = property(
    get_cspecified_style, set_cspecified_style
)

# A cached cascaded style property
svgpres = ['alignment-baseline', 'baseline-shift', 'clip', 'clip-path', 'clip-rule', 'color', 'color-interpolation', 'color-interpolation-filters', 'color-profile', 'color-rendering', 'cursor', 'direction', 'display', 'dominant-baseline', 'enable-background', 'fill', 'fill-opacity', 'fill-rule', 'filter', 'flood-color', 'flood-opacity', 'font-family', 'font-size', 'font-size-adjust', 'font-stretch', 'font-style', 'font-variant', 'font-weight', 'glyph-orientation-horizontal', 'glyph-orientation-vertical', 'image-rendering', 'kerning', 'letter-spacing', 'lighting-color', 'marker-end', 'marker-mid', 'marker-start', 'mask', 'opacity', 'overflow', 'pointer-events', 'shape-rendering', 'stop-color', 'stop-opacity', 'stroke', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'stroke-opacity', 'stroke-width', 'text-anchor', 'text-decoration', 'text-rendering', 'transform', 'transform-origin', 'unicode-bidi', 'vector-effect', 'visibility', 'word-spacing', 'writing-mode']
excludes = ["clip", "clip-path", "mask", "transform", "transform-origin"]
bstyle = Style0("");
def get_cascaded_style(el):
    # Object's style including any CSS
    # Modified from Inkex's cascaded_style
    if not (hasattr(el, "_ccascaded_style")):
        svg = el.croot
        if svg is not None:
            cssdict = svg.cssdict
        else:
            cssdict = dict()

        csssty = cssdict.get(el.get_id2())
        locsty = el.cstyle

        # Add any presentation attributes to local style
        attr = list(el.keys())
        attsty = bstyle.copy();
        for a in attr:
            if (
                a in svgpres
                and not (a in excludes)
                and locsty.get(a) is None
                and el.get(a) is not None
            ):
                attsty[a] = el.get(a)
        if csssty is None:
            ret = attsty + locsty
        else:
            # Any style specified locally takes priority, followed by CSS,
            # followed by any attributes that the element has
            ret = attsty + csssty + locsty
        el._ccascaded_style = ret
    return el._ccascaded_style
def set_ccascaded_style(el, si):
    # if si is None and hasattr(el, "_ccascaded_style"):
    #     delattr(el, "_ccascaded_style")
    if si is None:
        try:  # 50% faster than hasattr check
            delattr(el, "_ccascaded_style")
        except:
            pass
BaseElement.ccascaded_style = property(get_cascaded_style, set_ccascaded_style)

# Cached style attribute that invalidates the cached cascaded / specified
# style whenever the style is changed. Always use this when setting styles.
# def get_cstyle(el):
#     if not (hasattr(el, "_cstyle")):
#         el._cstyle = Style0(el.get("style"))  # el.get() is very efficient
#     return el._cstyle
# def set_cstyle(el, nsty):
#     el.style = nsty
#     if not(isinstance(nsty,Style0)):
#         nsty = Style0(nsty);
#     el._cstyle = nsty
#     el.ccascaded_style = None
#     el.cspecified_style = None
# BaseElement.cstyle = property(get_cstyle, set_cstyle)

# Sets a style property
# def Set_Style_Comp(el, comp, val):
#     sty = el.cstyle
#     if val is None:
#         if sty.get(comp) is not None:
#             del sty[comp]
#     else:
#         sty[comp] = val
#     el.cstyle = sty  # set element style

import inspect
def count_callers():
    caller_frame = inspect.stack()[2]
    filename = caller_frame.filename
    line_number = caller_frame.lineno
    lstr = f"{filename} at line {line_number}"
    global callinfo
    try:
        callinfo
    except:
        callinfo = dict();
    if lstr in callinfo:
        callinfo[lstr]+=1
    else:
        callinfo[lstr]=1

# Cached style attribute that invalidates the cached cascaded / specified
# style whenever the style is changed. Always use this when setting styles.
class CStyle(Style0):
    # Modifies Style0 to delete key when value set to None
    def __init__(self,val,el):
        self.el = el
        self.init = True
        super().__init__(val)
        self.init = False
    def __setitem__(self, key, value):
        if self.init:
            # OrderedDict sets items during initialization, use super()
            super().__setitem__(key, value)
        else:
            if value is None:
                if key in self:
                    del self[key]
            else:
                super().__setitem__(key, value)
            self.el.cstyle = self
class CStyleDescriptor:
    def __get__(self, el, owner):
        if not hasattr(el, "_cstyle"):
            el._cstyle = CStyle(EBget(el,"style"),el)
        return el._cstyle
    def __set__(self, el, value):
        # el.style = value
        
        vstr = str(value)
        if vstr=='':
            if 'style' in el.attrib:
               del el.attrib['style']
        else:
            lxml.etree.ElementBase.set(el,'style',vstr)
            
        if not isinstance(value, CStyle):
            value = CStyle(value,el)
        el._cstyle = value
        el.ccascaded_style = None
        el.cspecified_style = None
BaseElement.cstyle = CStyleDescriptor()

# Cached composed_transform, which can be invalidated by changes to transform of any ancestor.
# Currently is not invalidated when the element is moved, so beware!
def get_ccomposed_transform(el):
    if not (hasattr(el, "_ccomposed_transform")):
        myp = el.getparent()
        if myp is None:
            el._ccomposed_transform = el.ctransform
        else:
            el._ccomposed_transform = myp.ccomposed_transform @ el.ctransform
    return el._ccomposed_transform
def set_ccomposed_transform(el,si):
    if si is None and hasattr(el, "_ccomposed_transform"):
        delattr(el, "_ccomposed_transform")  # invalidate
        for k in list(el):
            k.ccomposed_transform = None     # invalidate descendants
BaseElement.ccomposed_transform = property(get_ccomposed_transform,set_ccomposed_transform)

# Cached transform property
# Note: Can be None
def get_ctransform(el):
    if not (hasattr(el, "_ctransform")):
        el._ctransform = el.transform
    return el._ctransform
def set_ctransform(el, newt):
    el.transform = newt
    # wrapped_setattr(el, 'transform', newt)
    el._ctransform = newt
    el.ccomposed_transform = None
BaseElement.ctransform = property(get_ctransform, set_ctransform)
# fmt: on

# For style components that represent a size (stroke-width, font-size, etc), calculate
# the true size reported by Inkscape in user units, inheriting any styles/transforms/document scaling
def Get_Composed_Width(el, comp, nargout=1):
    cs = el.cspecified_style
    ct = el.ccomposed_transform
    if nargout == 4:
        ang = math.atan2(ct.c, ct.d) * 180 / math.pi
    sc = cs.get(comp)

    # Get default attribute if empty
    if sc is None:
        sc = default_style_atts[comp]

    if "%" in sc:  # relative width, get parent width
        cel = el
        while sc != cel.cstyle.get(comp) and sc != cel.get(comp):
            cel = cel.getparent()
            # figure out ancestor where % is coming from

        sc = float(sc.strip("%")) / 100
        fs, sf, ct, tmp = Get_Composed_Width(cel.getparent(), comp, 4)
        if nargout == 4:
            return fs * sc, sf, ct, ang
        else:
            return fs * sc
    else:
        if comp == "font-size":
            sc = {"small": "10px", "medium": "12px", "large": "14px"}.get(sc, sc)

        sw = ipx(sc)
        sf = math.sqrt(abs(ct.a * ct.d - ct.b * ct.c))  # scale factor
        if nargout == 4:
            return sw * sf, sf, ct, ang
        else:
            return sw * sf


# Get line-height in user units
def Get_Composed_LineHeight(el):
    cs = el.cspecified_style
    sc = cs.get("line-height")
    if sc is not None:
        if "%" in sc:  # relative width, get parent width
            sc = float(sc.strip("%")) / 100
        elif sc.lower() == "normal":
            sc = 1.25
        else:
            sc = float(sc)
    if sc is None:
        sc = 1.25
        # default line-height is 12 uu
    fs = Get_Composed_Width(el, "font-size")
    return sc * fs


# For style components that are a list (stroke-dasharray), calculate
# the true size reported by Inkscape, inheriting any styles/transforms
def Get_Composed_List(el, comp, nargout=1):
    cs = el.cspecified_style
    ct = el.ccomposed_transform
    sc = cs.get(comp)
    if sc == "none":
        return "none"
    elif sc is not None:
        sw = sc.split(",")
        sf = math.sqrt(abs(ct.a * ct.d - ct.b * ct.c))
        sw = [ipx(x) * sf for x in sw]
        if nargout == 1:
            return sw
        else:
            return sw, sf
    else:
        if nargout == 1:
            return None
        else:
            return None, None


# fmt: off
# Modifications to Transform functions for speed

# A simple Vector2d, just a tuple wrapper
class v2d_simple():
    def __init__(self,x,y):
        self.x = x;
        self.y = y;
        
# Applies inverse of transform to point without making a new Transform
def applyI_to_point(obj, pt):
    m = obj.matrix
    det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
    inv_det = 1 / det
    sx = float(pt.x) - m[0][2]  # pt.x is sometimes a numpy float64?
    sy = float(pt.y) - m[1][2]
    x = (m[1][1] * sx - m[0][1] * sy) * inv_det
    y = (m[0][0] * sy - m[1][0] * sx) * inv_det
    return v2d_simple(x, y)
inkex.Transform.applyI_to_point = applyI_to_point

# Faster apply_to_point that gets rid of property calls
def apply_to_point_mod(obj, pt,simple=False):
    if simple:
        return v2d_simple(
            obj.matrix[0][0] * pt.x + obj.matrix[0][1] * pt.y + obj.matrix[0][2],
            obj.matrix[1][0] * pt.x + obj.matrix[1][1] * pt.y + obj.matrix[1][2],
        )
    else:
        if isinstance(pt,(tuple,list)):
            ptx = pt[0]; pty=pt[1];
        else:
            ptx = pt.x;  pty=pt.y
        # idebug(ptx)
        # idebug(pty)
        return inkex.Vector2d(
            obj.matrix[0][0] * ptx + obj.matrix[0][1] * pty + obj.matrix[0][2],
            obj.matrix[1][0] * ptx + obj.matrix[1][1] * pty + obj.matrix[1][2],
        )
        # return old_atp(obj,pt)
old_atp = inkex.Transform.apply_to_point
inkex.Transform.apply_to_point = apply_to_point_mod

 # A faster bool (built-in bool is slow because it initializes multiple Transforms)
# from math import fabs
def Tbool(obj):
    # return any([fabs(v1-v2)>obj.absolute_tolerance for v1,v2 in zip(obj.matrix[0]+obj.matrix[1],Itmat[0]+Itmat[1])])
    # return any([fabs(obj.matrix[0][0]-1)>obj.absolute_tolerance,fabs(obj.matrix[0][1])>obj.absolute_tolerance,fabs(obj.matrix[0][2])>obj.absolute_tolerance,fabs(obj.matrix[1][0])>obj.absolute_tolerance,fabs(obj.matrix[1][1]-1)>obj.absolute_tolerance,fabs(obj.matrix[1][2])>obj.absolute_tolerance])
    return obj.matrix!=Itmat     # exact, not within tolerance. I think this is fine
inkex.Transform.__bool__ = Tbool
# fmt: on


# Unit parser and renderer
def uparse(str):
    if str is not None:
        uv = inkex.units.parse_unit(str, default_unit=None)
        return uv[0], uv[1]
    else:
        return None, None


def urender(v, u):
    if v is not None:
        if u is not None:
            return inkex.units.render_unit(v, u)
        else:
            return str(v)
    else:
        return None


def ipx(strin):
    # Implicit pixel function
    # For many properties, a size specification of '1px' actually means '1uu'
    # Even if the size explicitly says '1mm' and the user units are mm, this will be
    # first converted to px and then interpreted to mean user units. (So '1mm' would
    # up being bigger than 1 mm). This returns the size as Inkscape will interpret it (in uu)
    if strin is None:
        return None
    else:
        return inkex.units.convert_unit(strin.lower().strip(), "px")




# Get points of a path, element, or rectangle in the global coordinate system
def get_points(el, irange=None):
    pth = Path(get_path2(el)).to_absolute()
    if irange is not None:
        pnew = Path()
        for ii in range(irange[0], irange[1]):
            pnew.append(pth[ii])
        pth = pnew
    pts = list(pth.end_points)

    ct = el.ccomposed_transform

    xs = []
    ys = []
    for p in pts:
        p = ct.apply_to_point(p)
        xs.append(p.x)
        ys.append(p.y)
    return xs, ys


# Unlinks clones and composes transform/clips/etc, along with descendants
def unlink2(el):
    if isinstance(el, (Use)):
        useel = el.get_link("xlink:href")
        if useel is not None:
            d = useel.duplicate2()

            # xy translation treated as a transform (applied first, then clip/mask, then full xform)
            tx = el.get("x")
            ty = el.get("y")
            if tx is None:
                tx = 0
            if ty is None:
                ty = 0
            # order: x,y translation, then clip/mask, then transform
            compose_all(
                d,
                None,
                None,
                Transform("translate(" + str(tx) + "," + str(ty) + ")"),
                None,
            )
            compose_all(
                d,
                el.get_link('clip-path',llget=True),
                el.get_link('mask',llget=True),
                el.ctransform,
                el.ccascaded_style,
            )
            replace_element(el, d)
            d.set("unlinked_clone", True)
            for k in descendants2(d)[1:]:
                unlink2(k)
                
            # To match Unlink Clone behavior, convert Symbol to Group
            if isinstance(d,(inkex.Symbol)):
                g = group(list(d))
                ungroup(d)
                d = g;
            return d
        else:
            return el
    else:
        return el

unungroupable = (NamedView, Defs, Metadata, ForeignObject, lxml.etree._Comment)
def ungroup(groupel):
    # Ungroup a group, preserving style, clipping, and masking
    # Remove any comments

    if groupel.croot is not None:
        gparent = groupel.getparent()
        gindex = list(gparent).index(groupel)  # group's location in parent
        gtransform = groupel.ctransform
        # gclipurl = groupel.get("clip-path")
        # gmaskurl = groupel.get("mask")
        
        gclip = groupel.get_link('clip-path',llget=True)
        gmask = groupel.get_link('mask',llget=True)
        
        gstyle = groupel.ccascaded_style

        # els = list(groupel)
        for el in reversed(list(groupel)):

            if isinstance(el, lxml.etree._Comment):  # remove comments
                groupel.remove(el)

            if not (isinstance(el, unungroupable)):
                clippedout = compose_all(el, gclip, gmask, gtransform, gstyle)
                if clippedout:
                    el.delete2()
                else:
                    gparent.insert(gindex + 1, el)
                    # places above

        if len(groupel) == 0:
            groupel.delete2()

# Group a list of elements, placing the group in the location of the first element            
def group(el_list,moveTCM=False):
    g = new_element(inkex.Group, el_list[0], dupecss=False)
    myi = list(el_list[0].getparent()).index(el_list[0])
    el_list[0].getparent().insert(myi + 1, g)
    for el in el_list:
        g.append(el)
        
    # If moveTCM is set and are grouping one element, move transform/clip/mask to group
    # Handy for adding and properly composing transforms/clips/masks
    if moveTCM and len(el_list)==1:
        g.ctransform = el.ctransform;              el.ctransform = None;
        g.set("clip-path", el.get("clip-path"));   el.set("clip-path", None)
        g.set("mask", el.get("mask"))          ;   el.set("mask", None)
    return g


Itmat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))

# For composing a group's properties onto its children (also group-like objects like Uses)
def compose_all(el, clip, mask, transform, style):
    if style is not None:  # style must go first since we may change it with CSS
        mysty = el.ccascaded_style
        compsty = style + mysty
        compsty["opacity"] = str(
            float(mysty.get("opacity", "1")) * float(style.get("opacity", "1"))
        )  # opacity accumulates at each layer
        el.cstyle = compsty

    if clip is not None:
        # idebug([el.get_id2(),clipurl])
        cout = merge_clipmask(el, clip)  # clip applied before transform, fix first
    if mask is not None:
        merge_clipmask(el, mask, mask=True)
    if clip is not None:
        fix_css_clipmask(el)
    if mask is not None:
        fix_css_clipmask(el, mask=True)

    if transform is not None:
        if transform.matrix != Itmat:
            if el.ctransform is None or el.ctransform.matrix == Itmat:
                el.ctransform = transform
            else:
                el.ctransform = transform @ el.ctransform

    if clip is None:
        return False
    else:
        return cout


# If an element has clipping/masking specified in a stylesheet, this will override any attributes
# I think this is an Inkscape bug
# Fix by creating a style specific to my id that includes the new clipping/masking
def fix_css_clipmask(el, mask=False):
    cm = "clip-path" if not mask else "mask"
    svg = el.croot
    if svg is not None:
        cssdict = svg.cssdict
    else:
        cssdict = dict()

    mycss = cssdict.get(el.get_id2())
    if mycss is not None:
        if mycss.get(cm) is not None and mycss.get(cm) != el.get(cm):
            svg = el.croot
            if not (hasattr(svg, "stylesheet_entries")):
                svg.stylesheet_entries = dict()
            svg.stylesheet_entries["#" + el.get_id2()] = cm + ":" + el.get(cm)
            mycss[cm] = el.get(cm)
    if el.cstyle.get(cm) is not None:  # also clear local style
        # Set_Style_Comp(el, cm, None)
        el.cstyle[cm] = None


# Adding to the stylesheet is slow, so as a workaround we only do this once
# There is no good way to do many entries at once, so we do it after we're finished
def flush_stylesheet_entries(svg):
    if hasattr(svg, "stylesheet_entries"):
        ss = ""
        for k in svg.stylesheet_entries.keys():
            ss += k + "{" + svg.stylesheet_entries[k] + "}\n"
        svg.stylesheet_entries = dict()

        stys = svg.xpath("svg:style")
        if len(stys) > 0:
            stys[0].text += "\n" + ss + "\n"


# Like duplicate, but randomly sets the id of all descendants also
# Normal duplicate does not
def get_duplicate2(el):
    svg = el.croot
    svg.iddict
    svg.cssdict
    # need to generate now to prevent problems in duplicate_fixed (el.addnext(elem) line, no idea why)

    d = duplicate_fixed(el);
    dupe_cssdict_entry(el.get_id2(), d.get_id2(), el.croot)
    add_to_iddict(d)

    for k in descendants2(d)[1:]:
        if not (isinstance(k, lxml.etree._Comment)):
            oldid = k.get_id2()
            set_random_id2(k)
            dupe_cssdict_entry(oldid, k.get_id2(), k.croot)
            add_to_iddict(k)

    if isinstance(d, (inkex.ClipPath)) or isMask(d):
        # Clip duplications can cause weird issues if they are not appended to the end of Defs
        d.croot.defs2.append(d)
        # idebug(d.get_id2())
    return d


BaseElement.duplicate2 = (get_duplicate2)


def duplicate_fixed(el):  # fixes duplicate's set_random_id
    # Like copy(), but the copy stays in the tree and sets a random id
    # Does not duplicate tail
    eltail = el.tail;
    if eltail is not None:
        el.tail = None;
        
    elem = el.copy()
    el.addnext(elem)
    set_random_id2(elem)
    
    if eltail is not None:
        el.tail = eltail
    return elem


# Makes a new object and adds it to the dicts, inheriting CSS dict entry from another element
def new_element(classin, inheritfrom,dupecss=True):
    g = classin()                # e.g Rectangle
    inheritfrom.croot.append(g)  # add to the SVG so we can assign an id
    if dupecss:
        dupe_cssdict_entry(inheritfrom.get_id2(), g.get_id2(), inheritfrom.croot)
    add_to_iddict(g)
    return g


# Replace an element with another one
# Puts it in the same location, update the ID dicts
def replace_element(el1, el2):
    # replace el1 with el2
    myp = el1.getparent()
    myi = list(myp).index(el1)
    myp.insert(myi + 1, el2)

    newid = el1.get_id2()
    oldid = el2.get_id2()

    el1.delete2()
    el2.set_id(newid)
    add_to_iddict(el2, todel=oldid)
    dupe_cssdict_entry(oldid, newid, el2.croot)


# Like list(set(lst)), but preserves order
# def unique(lst):
#     lst2 = [];
#     for ii in reversed(range(len(lst))):
#         if lst[ii] not in lst[:ii]:
#             lst2.insert(0,lst[ii]) 
#     if lst2!=unique2(lst):
#         idebug(lst)
#         idebug(lst2)
#         idebug(unique2(lst))
#         quit()
#     return lst2
def unique(lst):
    seen = set()
    seen_add = seen.add
    return [x for x in lst if not (x in seen or seen_add(x))]


def intersect_paths(ptha, pthb):
    # Intersect two rectangular paths. Could be generalized later
    ptsa = list(ptha.end_points)
    ptsb = list(pthb.end_points)
    x1c = max(min([p.x for p in ptsa]), min([p.x for p in ptsb]))
    x2c = min(max([p.x for p in ptsa]), max([p.x for p in ptsb]))
    y1c = max(min([p.y for p in ptsa]), min([p.y for p in ptsb]))
    y2c = min(max([p.y for p in ptsa]), max([p.y for p in ptsb]))
    w = x2c - x1c
    h = y2c - y1c

    if w > 0 and h > 0:
        return Path(
            "M "
            + str(x1c)
            + ","
            + str(y1c)
            + " h "
            + str(w)
            + " v "
            + str(h)
            + " h "
            + str(-w)
            + " Z"
        )
    else:
        return Path("")


# Like uniquetol in Matlab
import numpy as np


def uniquetol(A, tol):
    Aa = np.array(A)
    ret = Aa[~(np.triu(np.abs(Aa[:, None] - Aa) <= tol, 1)).any(0)]
    return type(A)(ret)

# Determines if an element is rectangle-like
# If it is one, also return Path
def isrectangle(el):
    isrect = False
    if isinstance(el, (PathElement, Rectangle, Line, Polyline)):
        pth = Path(get_path2(el)).to_absolute()
        pth = pth.transform(el.ctransform)

        pts = list(pth.end_points)
        cpts = list(pth.control_points)
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]

        if len(xs)>0:
            maxsz = max(max(xs) - min(xs), max(ys) - min(ys))
            tol = 1e-3 * maxsz
            if (
                4 <= len(xs) <= 5 and 4 <= len(cpts) <= 5
                and len(uniquetol(xs, tol)) == 2
                and len(uniquetol(ys, tol)) == 2
            ):
                isrect = True
    
    # if I am clipped I may not be a rectangle
    if isrect:
        if el.get_link('clip-path',llget=True) is not None:
            isrect = False
        if el.get_link('mask',llget=True) is not None:
            isrect = False
            
    if isrect:
        return True, pth
    else:
        return False, None

def merge_clipmask(node, newclip, mask=False):
    # Modified from Deep Ungroup
    def compose_clips(el, ptha, pthb):
        newpath = intersect_paths(ptha, pthb)
        isempty = str(newpath) == ""

        if not (isempty):
            myp = el.getparent()
            p = new_element(PathElement, el)
            myp.append(p)
            p.set("d", newpath)
        el.delete2()
        return isempty  # if clipped out, safe to delete element

    if newclip is not None:
        svg = node.croot
        cmstr = "mask" if mask else "clip-path"

        if node.ctransform is not None:
            # Clip-paths on nodes with a transform have the transform
            # applied to the clipPath as well, which we don't want.
            # Duplicate the new clip and apply node's inverse transform to its children.
            # clippath = getElementById2(svg, newclipurl[5:-1])
            if newclip is not None:
                d = newclip.duplicate2()
                if not (hasattr(svg, "newclips")):
                    svg.newclips = []
                svg.newclips.append(d)  # for later cleanup
                for k in list(d):
                    compose_all(k, None, None, -node.ctransform, None)
                # newclipurl = d.get_id2(2)
                newclip = d

        # newclipnode = getElementById2(svg, newclipurl[5:-1])
        if newclip is not None:
            for k in list(newclip):
                if isinstance(k, (Use)):
                    k = unlink2(k)

        

        oldclip = node.get_link(cmstr,llget=True)
        if oldclip is not None:
            # Existing clip is replaced by a duplicate, then apply new clip to children of duplicate
            for k in list(oldclip):
                if isinstance(k, (Use)):
                    k = unlink2(k)

            d = oldclip.duplicate2()
            if not (hasattr(svg, "newclips")):
                svg.newclips = []
            svg.newclips.append(d)  # for later cleanup
            node.set(cmstr, d.get_id2(2))

            newclipisrect = False
            if newclip is not None and len(newclip) == 1:
                newclipisrect, newclippth = isrectangle(list(newclip)[0])

            couts = []
            for k in reversed(list(d)):  # may be deleting, so reverse
                oldclipisrect, oldclippth = isrectangle(k)
                if newclipisrect and oldclipisrect and mask == False:
                    # For rectangular clips, we can compose them easily
                    # Since most clips are rectangles this semi-fixes the PDF clip export bug
                    cout = compose_clips(k, newclippth, oldclippth)
                else:
                    cout = merge_clipmask(k, newclip, mask)
                couts.append(cout)
            cout = all(couts)

        if oldclip is None:
            node.set(cmstr, newclip.get_id2(2))
            cout = False

        return cout


# Repeated getElementById lookups can be really slow, so instead create a cached iddict property.
# When an element is created that may be needed later, it must be added using add_to_iddict.
# def getElementById2(svg, eid,literal=False):
#     if svg is not None:
#         if not(literal):
#             eid = eid.strip()[4:-1] if eid.startswith("url(") else eid
#             eid = eid.lstrip("#")
#         return svg.iddict.get(eid)
#     else:
#         return None
# inkex.SvgDocumentElement.getElementById2 = getElementById2;

urlpat = re.compile(r'^url\(#(.*)\)$|^#')
def getElementById2(svg, eid: str, elm="*", literal=False):
    if eid is not None and not literal:
        eid = urlpat.sub(r'\1', eid.strip())
    if svg is not None:
        return svg.iddict.get(eid)
    else:
        return None
inkex.SvgDocumentElement.getElementById = getElementById2;
inkex.SvgDocumentElement.getElementById2 = getElementById2;




def add_to_iddict(el, todel=None):
    svg = el.croot
    svg.iddict[el.get_id2()] = el
    if todel is not None:
        del svg.iddict[todel]


# llgetid = lambda x : lxml.etree.ElementBase.get(x,'id',None)
# a low-level get is faster for getting ids
def getiddict(svg):
    if not (hasattr(svg, "_iddict")):
        svg._iddict = dict()
        toassign = []
        for el in svg.descendants2():
            if "id" in el.attrib:
                svg._iddict[EBget(el,'id')] = el
            else:
                toassign.append(el)
        for el in toassign:
            set_random_id2(el, el.TAG)
            svg._iddict[EBget(el,'id')] = el
    return svg._iddict
inkex.SvgDocumentElement.iddict = property(getiddict)

# A cached list of all descendants of an svg (not necessarily in order)
def getcdescendants(svg):
    return list(svg.iddict.values())
inkex.SvgDocumentElement.cdescendants = property(getcdescendants)


NSatts,wrprops = dict(), dict()
inkexget = inkex.BaseElement.get;
EBget = lxml.etree.ElementBase.get;



wrapped_props = {row[0]: (row[-2], row[-1]) for row in inkex.BaseElement.WRAPPED_ATTRS}
wrapped_props_keys = set(wrapped_props.keys())

wrapped_attrs =  {row[-2]: (row[0], row[-1]) for row in inkex.BaseElement.WRAPPED_ATTRS}
wrapped_attrs_keys = set(wrapped_attrs.keys())
        
def fast_getattr(self, name):
    """Get the attribute, but load it if it is not available yet"""
    # if name in wrapped_props_keys:   # always satisfied
    (attr, cls) = wrapped_props[name]
    def _set_attr(new_item):
        if new_item:
            self.set(attr, str(new_item))
        else:
            self.attrib.pop(attr, None)  # pylint: disable=no-member

    # pylint: disable=no-member
    value = cls(self.attrib.get(attr, None), callback=_set_attr)
    if name == "style":
        value.element = self
    fast_setattr(self, name, value)
    return value
    # raise AttributeError(f"Can't find attribute {self.typename}.{name}")

def fast_setattr(self, name, value):
    """Set the attribute, update it if needed"""
    # if name in wrapped_props_keys:   # always satisfied
    (attr, cls) = wrapped_props[name]
    # Don't call self.set or self.get (infinate loop)
    if value:
        if not isinstance(value, cls):
            value = cls(value)
        self.attrib[attr] = str(value)
    else:
        self.attrib.pop(attr, None)  # pylint: disable=no-member
    # else:
    #     lxml.etree.ElementBase.__setattr__(self,name, value)

# _base.py overloads __setattr__ and __getattr__, which adds a lot of overhead
# since they're invoked for all class attributes, not just transform etc.
# We remove the overloading and replicate it using properties. Since there
# are only a few attributes to overload, this is fine.
del inkex.BaseElement.__setattr__
del inkex.BaseElement.__getattr__
for prop in wrapped_props_keys:
    get_func = lambda self, attr=prop: fast_getattr(self, attr)
    set_func = lambda self, value, attr=prop: fast_setattr(self, attr, value)
    setattr(inkex.BaseElement, prop, property(get_func, set_func))


# Inkex's get does a lot of namespace checking that can be cached for speed
# This can be bypassed altogether for known attributes (by using EBget instead)
def fast_get(self, attr, default=None):
    try:
        return EBget(self,NSatts[attr], default)
    except:
        try:
            value = getattr(self, wrprops[attr], None)
            ret = str(value) if value else (default or None)
            return ret
        except:
            if attr in wrapped_attrs_keys:
                (wrprops[attr], _) = wrapped_attrs[attr]
            else:
                NSatts[attr] = inkex.addNS(attr)
            return inkexget(self, attr, default)
inkex.BaseElement.get = fast_get

def fast_set(self, attr, value):
    """Set element attribute named, with addNS support"""
    if attr in wrapped_attrs:
        # Always keep the local wrapped class up to date.
        (prop, cls) = wrapped_attrs[attr]
        setattr(self, prop, cls(value))
        value = getattr(self, prop)
        if not value:
            return
    if value is None:
        self.attrib.pop(inkex.addNS(attr), None)  # pylint: disable=no-member
    else:
        value = str(value)
        lxml.etree.ElementBase.set(self,inkex.addNS(attr), value)
inkex.BaseElement.set = fast_set

# A version of end_points that avoids unnecessary instance checks for speed
zZmM = {'z','Z','m','M'}
def fast_end_points(self):
    prev = inkex.Vector2d()
    first = inkex.Vector2d()
    for seg in self:  
        end_point = seg.end_point(first, prev)
        if seg.letter in zZmM:
            first = end_point
        prev = end_point
        yield end_point
inkex.paths.Path.end_points = property(fast_end_points)


# Optimize init to avoid calls to append, which is unnecessarily slow
ippcmd, ipcspth, ipln = inkex.paths.PathCommand, inkex.paths.CubicSuperPath, inkex.paths.Line
def fast_init(self, path_d=None):
    list.__init__(self)
    ps = isinstance(path_d, str)
    if ps:
        # Returns a generator returning PathCommand objects
        path_d = self.parse_string(path_d)
    elif isinstance(path_d, ipcspth):
        path_d = path_d.to_path()
    for item in path_d or ():
        if ps or isinstance(item, ippcmd):
            list.append(self,item)  # parse_string only yields PathCommands
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            if isinstance(item[1], (list, tuple)):
                list.append(self,ippcmd.letter_to_class(item[0])(*item[1]))
            else:
                list.append(self,ipln(*item))
        else:
            raise TypeError(
                f"Bad path type: {type(path_d).__name__}"
                f"({type(item).__name__}, ...): {item}"
            )
inkex.paths.Path.__init__ = fast_init

            
# A cached list of all descendants of an svg in order
# Currently only handles deletions appropriately
class dtree():
    def __init__(self,svg):
        ds, pts = descendants2(svg, True)
        self.ds = ds;
        self.iids = {d: ii for ii,d in enumerate(ds)} # desc. index by el
        iipts = {ptv: (ii,jj) for ii,pt in enumerate(pts) for jj,ptv in enumerate(pt)}
        self.range = [(ii,iipts[d][0]) for ii,d in enumerate(ds)]
    def iterel(self,el):
        try:
            eli = self.iids[el]
            for ii in range(self.range[eli][0],self.range[eli][1]):
                yield self.ds[ii]
        except:
            pass
    def delel(self,el):
        try:
            eli = self.iids[el]
            strt = self.range[eli][0]
            stop = self.range[eli][1]
            self.ds  = self.ds[:strt]  + self.ds[stop:]
            self.range  = self.range[:strt]  + self.range[stop:]
            N = stop - strt
            self.range  = [(x - N if x > strt else x, y - N if y > strt else y) for x, y in self.range]
            self.iids = {d: ii for ii,d in enumerate(self.ds)} # desc. index by el
        except:
            pass    
def get_cd2(svg):
    if not (hasattr(svg, "_cd2")):
        svg._cd2 = dtree(svg)
    return svg._cd2
def set_cd2(svg,sv):
    if sv is None and hasattr(svg, "_cd2"):
        delattr(svg, "_cd2")
inkex.SvgDocumentElement.cdescendants2 = property(get_cd2,set_cd2)

# Deletes an element from cached dicts on deletion
def delete2(el):
    svg = el.croot
    for d in el.descendants2():
        if svg is not None:
            try:
                del svg.iddict[d.get_id2()]
            except KeyError:
                pass
        d.croot = None
    if hasattr(svg, "_cd2"):
        svg.cdescendants2.delel(el)
    el.delete()
BaseElement.delete2 = delete2

def defs2(svg):
    # Defs get that avoids xpath. Looks for a defs under the svg
    if not (hasattr(svg, "_defs2")):
        for k in list(svg):
            if isinstance(k, (inkex.Defs)):
                svg._defs2 = k
                return svg._defs2
        d = new_element(inkex.Defs, svg)
        svg.insert(0, d)
        svg._defs2 = d
    return svg._defs2
inkex.SvgDocumentElement.defs2 = property(defs2)


# The built-in get_unique_id gets stuck if there are too many elements. Instead use an adaptive
# size based on the current number of ids
# Modified from Inkex's get_unique_id
import random
def get_unique_id2(svg, prefix):
    ids = get_ids2(svg) 
    new_id = None
    size = math.ceil(math.log10(len(ids))) + 1
    _from = 10 ** size - 1
    _to = 10 ** size
    while new_id is None or new_id in ids:
        # Do not use randint because py2/3 incompatibility
        new_id = prefix + str(int(random.random() * _from - _to) + _to)
    svg.ids.add(new_id)
    return new_id

def get_ids2(svg):
    """Returns a set of unique document ids"""
    if not svg.ids:
        if hasattr(svg,"_iddict"): # don't use iddict, called by getiddict
            svg.ids = set(svg._iddict.keys())
        else:
            svg.ids = set(svg.xpath("//@id"))
    return svg.ids

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
    el.set_id(get_unique_id2(el.croot, prefix), backlinks=backlinks)


# Like get_id(), but calls set_random_id2
# Modified from Inkex's get_id
def get_id2_func(el, as_url=0):
    """Get the id for the element, will set a new unique id if not set.
    as_url - If set to 1, returns #{id} as a string
             If set to 2, returns url(#{id}) as a string
    """
    if "id" not in el.attrib:
        set_random_id2(el, el.TAG)
    # eid = el.get("id")
    eid = EBget(el,'id')
    if as_url > 0:
        eid = "#" + eid
        if as_url > 1:
            eid = f"url({eid})"
    return eid
BaseElement.get_id2 = get_id2_func

# Modified from Inkex's get_path
# Correctly calculates path for rectangles and ellipses
# Gets Path object
def get_path2(el):
    # mostly from inkex.elements._polygons
    if isinstance(el, (inkex.Rectangle)):
        left   = ipx(el.get("x", "0"))
        top    = ipx(el.get("y", "0"))
        width  = ipx(el.get("width", "0"))
        height = ipx(el.get("height", "0"))
        rx = ipx(el.get("rx", el.get("ry", "0")))
        ry = ipx(el.get("ry", el.get("rx", "0")))
        right = left + width
        bottom = top + height
        if rx:
            return Path((
                "M {lft2},{topv}"
                "L {rgt2},{topv}  A {rxv},{ryv} 0 0 1 {rgtv},{top2}"
                "L {rgtv},{btm2}  A {rxv},{ryv} 0 0 1 {rgt2},{btmv}"
                "L {lft2},{btmv}  A {rxv},{ryv} 0 0 1 {lftv},{btm2}"
                "L {lftv},{top2}  A {rxv},{ryv} 0 0 1 {lft2},{topv} z".format(
                    topv=top, btmv=bottom, lftv=left,rgtv=right, rxv=rx, ryv=ry,
                    lft2=left+rx, rgt2=right-rx, top2=top+ry, btm2=bottom-ry
                ))
            )
        return Path("M {lftv},{topv} h {wdtv} v {hgtv} h {wdt2} z".format(
            topv=top, lftv=left, wdtv=width, hgtv=height,
            wdt2=-width)
        )
    
    elif isinstance(el, (inkex.Circle, inkex.Ellipse)):
        cx = ipx(el.get("cx", "0"))
        cy = ipx(el.get("cy", "0"))
        if isinstance(el, (inkex.Ellipse)):  # ellipse
            rx = ipx(el.get("rx", "0"))
            ry = ipx(el.get("ry", "0"))
        else:  # circle
            rx = ipx(el.get("r", "0"))
            ry = ipx(el.get("r", "0"))
        return Path((
            "M {cx},{y} "
            "a {rx},{ry} 0 1 0 {rx}, {ry} "
            "a {rx},{ry} 0 0 0 -{rx}, -{ry} z"
        ).format(cx=cx, y=cy-ry, rx=rx, ry=ry))
        
    elif isinstance(el, Line): # updated in v1.2
        x1 = ipx(el.get("x1", "0"))
        y1 = ipx(el.get("y1", "0"))
        x2 = ipx(el.get("x2", "0"))
        y2 = ipx(el.get("y2", "0"))
        pth = Path(f"M{x1},{y1} L{x2},{y2}")
    else:
        pth = el.get_path()
    return pth


otp_support = (
    inkex.Rectangle,
    inkex.Ellipse,
    inkex.Circle,
    inkex.Polygon,
    inkex.Polyline,
    inkex.Line,
    inkex.PathElement,
)
flow_types = (inkex.FlowRoot,inkex.FlowPara,inkex.FlowRegion,inkex.FlowSpan,)


def object_to_path(el):
    if not (isinstance(el, (inkex.PathElement, inkex.TextElement))):
        pth = get_path2(el)
        el.tag = inkex.addNS('path','svg'); #"{http://www.w3.org/2000/svg}path"
        el.set("d", str(pth))

# Alternate bbox function that requires no command call (uses extents for text)
# dotransform: whether or not we want the element's bbox or its true transformed bbox
# includestroke: whether or not to add the stroke to the calculation
def bounding_box2(el,dotransform=True,includestroke=True):
    if not(hasattr(el,'_cbbox')):
        el._cbbox = dict()
        
    if (dotransform,includestroke) not in el._cbbox:
        try:
            ret = bbox(None)
            if isinstance(el, (inkex.TextElement)):
                ret = el.parsed_text.get_full_extent();
            elif isinstance(el, otp_support):
                pth = get_path2(el)
                if len(pth)>0:
                    bb = Path(pth).to_absolute().bounding_box()
                    
                    sw = ipx(el.cspecified_style.get('stroke-width','0px'))
                    if el.cspecified_style.get('stroke') is None or not(includestroke):
                        sw = 0;
                    ret = bbox([bb.left-sw/2, bb.top-sw/2,
                                bb.width+sw,bb.height+sw])
            elif isinstance(el,(SvgDocumentElement,Group,inkex.Layer,inkex.ClipPath)) or isMask(el):
                ks = [d for d in list(el) if not(isinstance(d, (lxml.etree._Comment)))]
                for d in ks:
                    dbb = bounding_box2(d,dotransform=False,includestroke=includestroke);
                    if not(dbb.isnull):
                        ret = ret.union(dbb.transform(d.ctransform))
            elif isinstance(el,(inkex.Image)):
                ret = bbox([ipx(el.get(v, "0")) for v in ['x',"y","width","height"]]);
            elif isinstance(el,(inkex.Use,)):
                lel = el.get_link('xlink:href');
                
                if lel is not None:
                    ret = bounding_box2(lel,dotransform=False)
                    ret = ret.transform(lel.ctransform) # clones have the transform of the link, but not anything above
        
            if not(ret.isnull):
                for cm in ['clip-path','mask']:
                    clip = el.get_link(cm,llget=True)
                    if clip is not None:
                       cbb = bounding_box2(clip,dotransform=False,includestroke=False)
                       if not(cbb.isnull):
                           ret = ret.intersection(cbb)
                       else:
                           ret = bbox(None)
                    
                if dotransform:
                    if not(ret.isnull):
                        ret = ret.transform(el.ccomposed_transform)
        except:
            # For some reason errors are occurring silently
            import traceback
            idebug(traceback.format_exc())
                    
        el._cbbox[(dotransform,includestroke)] = ret
    return el._cbbox[(dotransform,includestroke)]

bb2_support = (inkex.TextElement,inkex.Image,inkex.Use,
               SvgDocumentElement,inkex.Group,inkex.Layer) + otp_support

def set_cbbox(el,val):
    if val is None and hasattr(el,'_cbbox'):
        delattr(el,'_cbbox')
inkex.BaseElement.cbbox = property(bounding_box2,set_cbbox)
inkex.SvgDocumentElement.cbbox = property(bounding_box2,set_cbbox)

# A wrapper that replaces Get_Bounding_Boxes with Pythonic calls only if possible
def BB2(slf,els=None,forceupdate=False):
    if els is None:
        els = descendants2(slf.svg);
    
    render_dict = dict();
    def isrendered(el):
        if el in render_dict:
            return render_dict[el]
        else:
            myp = el.getparent();
            ret = True
            if myp is None or isrendered(myp):
                if el.tag in [inkex.addNS('RDF','rdf'),
                              inkex.addNS('Work','cc'),
                              inkex.addNS('format','dc'),
                              inkex.addNS('type','dc')]:
                    ret=False
                elif isinstance(el,(NamedView, Defs, Metadata, ForeignObject, inkex.Guide,
                                    inkex.ClipPath,inkex.StyleElement,
                                    Tspan,inkex.FlowRegion,inkex.FlowPara)) or isMask(el):
                    ret=False
            else:
                ret = False
            render_dict[el] = ret
            return ret
    
    if all([isinstance(d, bb2_support) or not(isrendered(d)) for d in els]):
        if forceupdate:
            if hasattr(slf.svg, '_char_table'):
                delattr(slf.svg,'_char_table')
            for d in els:
                d.cbbox = None
                
        allds = []
        for el in els:
            if el not in allds: # so we're not re-descendants2ing
                allds += descendants2(el)        
        dtels = [d for d in unique(allds) if isinstance(d,inkex.TextElement)]
        if len(dtels)>0:
            import TextParser
            assert TextParser # optional, disables pyflakes warning
            slf.svg.make_char_table(els=dtels)
        ret = dict()
        for d in els:
            if isinstance(d, bb2_support) and isrendered(d):
                mbbox = d.cbbox; # Attribute Errors here are not actually here usually
                if not(mbbox.isnull):
                    ret[d.get_id2()] = mbbox.sbb
    else:
        import tempfile
        with tempfile.TemporaryFile() as temp:
            tname = os.path.abspath(temp.name);
            overwrite_svg(slf.svg, tname)
            ret = Get_Bounding_Boxes(filename=tname, svg=slf.svg)

    return ret

def Check_BB2(slf):
    bb2 = BB2(slf)
    
    HIGHLIGHT_STYLE = "fill:#007575;fill-opacity:0.4675"  # mimic selection
    for el in descendants2(slf.svg):
        if el.get_id2() in bb2:
            bb = bbox(bb2[el.get_id2()]);
            # bb = bbox(bb2[el.get_id2()])*(1/slf.svg.cscale);
            r = inkex.Rectangle()
            r.set('mysource',el.get_id2())
            r.set('x',bb.x1)
            r.set('y',bb.y1)
            r.set('height',bb.h)
            r.set('width', bb.w)
            r.set("style", HIGHLIGHT_STYLE)
            el.croot.append(r)

# e.g., bbs = dh.Get_Bounding_Boxes(self.options.input_file);
# Gets all of a document's bounding boxes (by ID) using a binary call
# Result in uu
def Get_Bounding_Boxes(filename, inkscape_binary=None,extra_args=[], svg=None):
    tFStR = commandqueryall(filename, inkscape_binary=inkscape_binary,extra_args=extra_args)        
    # Parse the output
    tBBLi = tFStR.splitlines()
    bbs = dict()
    for d in tBBLi:
        key = str(d).split(",")[0]
        if key[0:2] == "b'":  # pre version 1.1
            key = key[2:]
        if str(d)[2:52] == "WARNING: Requested update while update in progress":
            continue
            # skip warnings (version 1.0 only?)
        data = [float(x.strip("'")) for x in str(d).split(",")[1:]]
        if key!="'":  # sometimes happens in v1.3
            bbs[key] = data
    
    # Inkscape always reports a bounding box in pixels, relative to the viewbox
    # Convert to user units for the output
    if svg is None:
        # If SVG not supplied, load from file
        svg = svg_from_file(filename);
    
    ds = svg.cdocsize;
    for k in bbs:
        bbs[k] = ds.pxtouu(bbs[k])
    return bbs


# 2022.02.03: I think the occasional hangs come from the call to command.
# I think this is more robust. Make a tally below if it freezes:
def commandqueryall(fn, inkscape_binary=None,extra_args = []):
    if inkscape_binary is None:
        bfn = Get_Binary_Loc()
    else:
        bfn = inkscape_binary
    arg2 = [bfn, "--query-all"]+extra_args+[fn]

    p = subprocess_repeat(arg2)
    tFStR = p.stdout
    return tFStR

# Get SVG from file
from inkex import load_svg
def svg_from_file(fin):
    svg = load_svg(fin).getroot()
    return svg

def el_from_string(strin):
    prefix = '''
    <svg
       xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
       xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
       xmlns="http://www.w3.org/2000/svg"
       xmlns:svg="http://www.w3.org/2000/svg"
       xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
       xmlns:cc="http://creativecommons.org/ns#"
       xmlns:dc="http://purl.org/dc/elements/1.1/">
      '''
    svgtxt = prefix + strin + '</svg>'
    nsvg = svg_from_file(svgtxt)
    return list(nsvg)[0]

# Write to disk, removing any existing file
def overwrite_svg(svg, fileout):
    try:
        os.remove(fileout)
    except:
        pass
    inkex.command.write_svg(svg, fileout)

# Version of ancestors that works in v1.0
def get_ancestors(el,includeme=False):
    anc = []; cel = el;
    while cel.getparent() is not None:
        cel = cel.getparent()
        anc.append(cel)
    if includeme:
        return [el]+anc;
    else:
        return anc
BaseElement.ancestors2 = get_ancestors

# Reference a URL (return None if does not exist or invalid)
def get_link_fcn(el,typestr,svg=None,llget=False):
    if llget:
        tv = EBget(el,typestr); # fine for 'clip-path' & 'mask'
    else:
        tv = el.get(typestr);
    if tv is not None:
        if svg is None:
            svg = el.croot   # need to specify svg for Styles but not BaseElements
        if typestr=='xlink:href':
            urlel = getElementById2(svg, tv[1:])
        elif tv.startswith('url'):
            urlel = getElementById2(svg, tv[5:-1])
        else:
            urlel = None
        return urlel
    return None
BaseElement.get_link = get_link_fcn
Style0.get_link      = get_link_fcn

# In the event of a timeout, repeat subprocess call several times
def subprocess_repeat(argin):
    BASE_TIMEOUT = 60
    NATTEMPTS = 4

    import subprocess

    nfails = 0
    ntime = 0
    for ii in range(NATTEMPTS):
        timeout = BASE_TIMEOUT * (ii + 1)
        try:
            os.environ["SELF_CALL"] = "true" # seems to be needed for 1.3
            p = subprocess.run(
                argin,
                shell=False,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            break
        except subprocess.TimeoutExpired:
            nfails += 1
            ntime += timeout
    if nfails == NATTEMPTS:
        inkex.utils.errormsg(
            "Error: The call to the Inkscape binary timed out "
            + str(NATTEMPTS)
            + " times in "
            + str(ntime)
            + " seconds.\n\n"
            + "This may be a temporary issue; try running the extension again."
        )
        quit()
    else:
        return p


global debugs
debugs = ""


def debug(x):
    # inkex.utils.debug(x);
    global debugs
    if debugs != "":
        debugs += "\n"
    debugs += str(x)


def write_debug():
    global debugs
    if debugs != "":
        debugname = "Debug.txt"
        f = open(debugname, "w", encoding="utf-8")
        f.write(debugs)
        f.close()


def idebug(x,printids=True):
    def is_nested_list_of_base_elements(x):
        if not isinstance(x, (list,tuple)):
            return False
        for element in x:
            if isinstance(element, (list,tuple)):
                if not is_nested_list_of_base_elements(element):
                    return False
            elif not isinstance(element, BaseElement):
                return False
        return True
    
    if printids and is_nested_list_of_base_elements(x):
        def process_nested_list(input_list):
            if isinstance(input_list, list):
                return [process_nested_list(e) for e in input_list]
            if isinstance(input_list, tuple):
                return tuple([process_nested_list(e) for e in input_list])
            elif isinstance(input_list, BaseElement):
                return input_list.get_id2()
        pv = process_nested_list(x)
    else:
        pv = x
    inkex.utils.debug(pv)

import time
global lasttic
def tic():
    global lasttic
    lasttic = time.time()
def toc():
    global lasttic
    idebug(time.time()-lasttic)
    
# Adds tag2 to the inkex classes, which holds the corresponding tag
# Checking the tag can be much faster than instance checking (about 6x)
try:
    lt = dict(inkex.elements._parser.NodeBasedLookup.lookup_table)
except:
    lt = dict(inkex.elements._base.NodeBasedLookup.lookup_table)
for k,v in lt.items():
    for v2 in v:
        v2.tag2 = inkex.addNS(k[1],k[0])
tags = lambda x : set([v.tag2 for v in x]) # converts class tuple to set of tags
        

# A cached root property
def get_croot(el):
    if not (hasattr(el, "_croot")):
        myn = el
        while myn.getparent() is not None:
            myn = myn.getparent()
        if isinstance(myn, SvgDocumentElement):
            el._croot = myn
        else:
            el._croot = None
    return el._croot
def set_croot(el, ri):
    el._croot = ri
BaseElement.croot = property(get_croot, set_croot)

# Modified from Inkex's get function
# Does not fail on comments
def get_mod(slf, *types):
    def _recurse(elem):
        if not types or isinstance(elem, types):
            yield elem
        for child in elem:
            for item in _recurse(child):
                yield item

    return inkex.elements._selected.ElementList(
        slf.svg,
        [
            r
            for e in slf.values()
            for r in _recurse(e)
            if not (isinstance(r, lxml.etree._Comment))
        ],
    )

# An efficient Pythonic version of Clean Up Document
def clean_up_document(svg):
    # defs types that do nothing unless they are referenced
    prune = ["clipPath", "mask", "linearGradient", "radialGradient", "pattern",
             "symbol", "marker", "filter", "animate", "animateTransform", 
             "animateMotion", "textPath", "font", "font-face"]
    prune = [inkex.addNS(v,'svg') for v in prune]
    
    # defs types that don't need to be referenced
    exclude = [inkex.addNS(v,'svg') for v in ["style","glyph"]]
    
    def should_prune(el):
        return el.tag in prune or (el.getparent()==svg.defs2 and el.tag not in exclude)
    
    # style atts that could have urls
    styleatt = ["fill", "stroke", "clip-path", "mask", "filter",
                "marker-start", "marker-mid", "marker-end", "marker", "font", 
                "font-family", "fill-opacity", "stroke-opacity", "opacity"]
    xlink = [inkex.addNS("href", "xlink"),"href"]
    
    attids = {sa : dict() for sa in styleatt}
    xlinks = dict()

    
    def miterdescendants(el):
        yield el
        for d in el.iterdescendants():
            yield d
    
    # Make dicts of all url-containing style atts and xlinks
    # for d in miterdescendants(svg):
    for d in svg.cdescendants2.ds:
        for attName in d.attrib.keys():
            if attName in styleatt:
                if d.attrib[attName].startswith('url'):
                    attids[attName][d.get_id2()] = d.attrib[attName][5:-1]
            elif attName in xlink:
                if d.attrib[attName].startswith('#'):
                    xlinks[d.get_id2()] = d.attrib[attName][1:]
            elif attName=='style':
                if 'url' in d.attrib[attName]:
                    sty = Style0(d.attrib[attName])
                    for an2 in sty.keys():
                        if an2 in styleatt:
                            if sty[an2].startswith('url'):
                                attids[an2][d.get_id2()] = sty[an2][5:-1] 

    deletedsome = True
    while deletedsome:
        allurls = set([v for sa in styleatt for v in attids[sa].values()] + list(xlinks.values()))
        # sets much faster than lists for membership testing
        deletedsome = False
        # for el in miterdescendants(svg):
        for el in svg.cdescendants2.ds:
            if should_prune(el):
                # eldids = [dv.get_id2() for dv in miterdescendants(el)]
                eldids = [dv.get_id2() for dv in svg.cdescendants2.iterel(el)]
                if not(any([idv in allurls for idv in eldids])):
                    el.delete2()
                    deletedsome = True  
                    for did in eldids:
                        for anm in styleatt:
                            if did in attids[anm]:
                                del attids[anm][did]
                        if did in xlinks:
                            del xlinks[did]         

# When non-ascii characters are detected, replace all non-letter characters with the specified font
# Mainly for fonts like Avenir
def Replace_Non_Ascii_Font(el, newfont, *args):
    def nonletter(c):
        return not ((ord(c) >= 65 and ord(c) <= 90) or (ord(c) >= 97 and ord(c) <= 122))

    def nonascii(c):
        return ord(c) >= 128

    def alltext(el):
        astr = el.text
        if astr is None:
            astr = ""
        for k in list(el):
            if isinstance(k, (Tspan, FlowPara, FlowSpan)):
                astr += alltext(k)
                tl = k.tail
                if tl is None:
                    tl = ""
                astr += tl
        return astr

    forcereplace = len(args) > 0 and args[0]
    if forcereplace or any([nonascii(c) for c in alltext(el)]):
        alltxt = [el.text]
        el.text = ""
        for k in list(el):
            if isinstance(k, (Tspan, FlowPara, FlowSpan)):
                dupe = k.duplicate2();
                alltxt.append(dupe)
                alltxt.append(k.tail)
                k.tail = ""
                k.delete2()
        lstspan = None
        for t in alltxt:
            if t is None:
                pass
            elif isinstance(t, str):
                ws = []
                si = 0
                for ii in range(
                    1, len(t)
                ):  # split into words based on whether unicode or not
                    if nonletter(t[ii - 1]) != nonletter(t[ii]):
                        ws.append(t[si:ii])
                        si = ii
                ws.append(t[si:])
                sty = "baseline-shift:0%;"
                for w in ws:
                    if any([nonletter(c) for c in w]):
                        w = w.replace(" ", "\u00A0")
                        # spaces can disappear, replace with NBSP
                        ts = new_element(Tspan,el);
                        el.append(ts)
                        ts.text = w; ts.cstyle=Style0(sty+'font-family:'+newfont)
                        ts.cspecified_style = None; ts.ccomposed_transform = None;
                        lstspan = ts
                    else:
                        if lstspan is None:
                            el.text = w
                        else:
                            lstspan.tail = w
            elif isinstance(t, (Tspan, FlowPara, FlowSpan)):
                Replace_Non_Ascii_Font(t, newfont, True)
                el.append(t)
                t.cspecified_style = None; t.ccomposed_transform = None;
                lstspan = t
                
    # Inkscape automatically prunes empty text/tails
    # Do the same so future parsing is not affected
    if isinstance(el,inkex.TextElement):
        for d in el.descendants2():
            if d.text is not None and d.text=='':
                d.text = None
            if d.tail is not None and d.tail=='':
                d.tail = None


# A modified bounding box class
class bbox:
    def __init__(self, bb):
        self.isnull = bb is None
        if not(self.isnull):
            if len(bb)==2:       # allow tuple of two points ((x1,y1),(x2,y2))
                bb = [min(bb[0][0],bb[1][0]),min(bb[0][1],bb[1][1]),
                      abs(bb[0][0]-bb[1][0]),abs(bb[0][1]-bb[1][1])]
            self.x1 = bb[0]
            self.x2 = bb[0] + bb[2]
            self.y1 = bb[1]
            self.y2 = bb[1] + bb[3]
            self.xc = (self.x1 + self.x2) / 2
            self.yc = (self.y1 + self.y2) / 2
            self.w = bb[2]
            self.h = bb[3]
            self.sbb = [self.x1, self.y1, self.w, self.h]  # standard bbox

    def transform(self, xform):
        if not(self.isnull):
            tr1 = xform.apply_to_point([self.x1, self.y1])
            tr2 = xform.apply_to_point([self.x2, self.y2])
            tr3 = xform.apply_to_point([self.x1, self.y2])
            tr4 = xform.apply_to_point([self.x2, self.y1])
            return bbox(
                [
                    min(tr1[0], tr2[0], tr3[0], tr4[0]),
                    min(tr1[1], tr2[1], tr3[1], tr4[1]),
                    max(tr1[0], tr2[0], tr3[0], tr4[0]) - min(tr1[0], tr2[0], tr3[0], tr4[0]),
                    max(tr1[1], tr2[1], tr3[1], tr4[1]) - min(tr1[1], tr2[1], tr3[1], tr4[1]),
                ]
            )
        else:
            return bbox(None)
    
    def intersect(self, bb2):
        return (abs(self.xc - bb2.xc) * 2 < (self.w + bb2.w)) and (
            abs(self.yc - bb2.yc) * 2 < (self.h + bb2.h)
        )
    
    def union(self, bb2):
        if isinstance(bb2,list):
            bb2 = bbox(bb2)
        if not(self.isnull):
            minx = min([self.x1, self.x2, bb2.x1, bb2.x2])
            maxx = max([self.x1, self.x2, bb2.x1, bb2.x2])
            miny = min([self.y1, self.y2, bb2.y1, bb2.y2])
            maxy = max([self.y1, self.y2, bb2.y1, bb2.y2])
            return bbox([minx, miny, abs(maxx - minx), abs(maxy - miny)])
        else:
            return bbox(bb2.sbb)
        
    def intersection(self,bb2):
        if isinstance(bb2,list):
            bb2 = bbox(bb2)
        if not(self.isnull):
            minx = max([self.x1, bb2.x1])
            maxx = min([self.x2, bb2.x2])
            miny = max([self.y1, bb2.y1])
            maxy = min([self.y2, bb2.y2])
            return bbox([minx, miny, abs(maxx - minx), abs(maxy - miny)])
        else:
            return bbox(bb2.sbb)
    
    def __deepcopy__(self, memo):
        return bbox([self.x1, self.y1, self.w, self.h])
    
    def __mul__(self, scl):
        return bbox([self.x1*scl, self.y1*scl, self.w*scl, self.h*scl])
    


def global_transform(el, trnsfrm, irange=None, trange=None,preserveStroke=True):
    # Transforms an object and fuses it to any paths
    # If preserveStroke is set the stroke width will be unchanged, otherwise
    # will also be scaled
    
    # If parent layer is transformed, need to rotate out of its coordinate system
    myp = el.getparent()
    if myp is None:
        prt = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    else:
        prt = myp.ccomposed_transform
    # prt = Transform("scale(" + str((el.croot.cscale)) + ")") @ prt
    # also include document scaling

    myt = el.ctransform
    if myt == None:
        newtr = (-prt) @ trnsfrm @ prt
        if trange is not None:
            for ii in range(len(trange)):
                trange[ii] = (-prt) @ trange[ii] @ prt
    else:
        newtr = (-prt) @ trnsfrm @ prt @ Transform(myt)
        if trange is not None:
            for ii in range(len(trange)):
                trange[ii] = (-prt) @ trange[ii] @ prt @ Transform(myt)

    sw = Get_Composed_Width(el, "stroke-width")
    sd = Get_Composed_List(el, "stroke-dasharray")

    el.ctransform = newtr  # Add the new transform
    fuseTransform(el, irange=irange, trange=trange)

    if preserveStroke:
        if sw is not None:
            neww, sf, ct, ang = Get_Composed_Width(el, "stroke-width", nargout=4)
            # Set_Style_Comp(el, "stroke-width", str(sw / sf))
            el.cstyle["stroke-width"]=str(sw / sf)
            # fix width
        if not (sd in [None, "none"]):
            nd, sf = Get_Composed_List(el, "stroke-dasharray", nargout=2)
            # Set_Style_Comp(el, "stroke-dasharray", str([sdv / sf for sdv in sd]).strip("[").strip("]"))
            el.cstyle["stroke-dasharray"]=str([sdv / sf for sdv in sd]).strip("[").strip("]")
            # fix dash

# Delete and prune empty ancestor groups
def deleteup(el):
    myp = el.getparent()
    el.delete2()
    if myp is not None:
        if not len(myp): # faster than getting children
            deleteup(myp)
        # myc = list(myp)
        # if myc is not None and len(myc) == 0:
        #     deleteup(myp)

# Splits a text element into its consituent parts by duplication (deleting original)
# Order is text, child1, child1 tail, child2, child2 tail, etc.
def split_text(el):
    ds = [];
    for ii,s in reversed(list(enumerate(list(el)))):
        # pop out copy with tail
        if s.tail is not None:
            dup = el.duplicate2();
            dup.text = s.tail;
            for jj,s2 in reversed(list(enumerate(list(dup)))):
                delete2(s2)
            ds.append(dup)
        
        # pop out copy with child
        dup = el.duplicate2();
        dup.text = None;
        for jj,s2 in reversed(list(enumerate(list(dup)))):
            if jj!=ii:
                delete2(s2)
            else:
                s2.tail = None
        ds.append(dup)
        s.delete();
        
    if len(list(el))==0 and el.text is not None:
        dup = el.duplicate2();
        ds.append(dup)
    el.delete2();
    return list(reversed(ds))

# Combines a group of path-like elements
def combine_paths(els, mergeii=0):
    pnew = Path()
    si = []
    # start indices
    for el in els:
        pth = Path(el.get_path()).to_absolute().transform(el.ccomposed_transform)
        if el.get("inkscape-scientific-combined-by-color") is None:
            si.append(len(pnew))
        else:
            cbc = el.get(
                "inkscape-scientific-combined-by-color"
            )  # take existing ones and weld them
            cbc = [int(v) for v in cbc.split()]
            si += [v + len(pnew) for v in cbc[0:-1]]
        for p in pth:
            pnew.append(p)
    si.append(len(pnew))

    # Set the path on the mergeiith element
    mel = els[mergeii]
    if mel.get("d") is None:  # Polylines and lines have to be converted to a path
        object_to_path(mel)
    mel.set("d", str(pnew.transform(-mel.ccomposed_transform)))

    # Release clips/masks
    mel.set("clip-path", "none")
    # release any clips
    mel.set("mask", "none")
    # release any masks
    fix_css_clipmask(mel, mask=False)  # fix CSS bug
    fix_css_clipmask(mel, mask=True)

    mel.set("inkscape-scientific-combined-by-color", " ".join([str(v) for v in si]))
    for s in range(len(els)):
        if s != mergeii:
            deleteup(els[s])


# Gets all of the stroke and fill properties from a style
# Alpha is its effective alpha including opacity
# Note to self: inkex.Color inherits from list
def get_strokefill(el):
    sty = el.cspecified_style
    strk = sty.get("stroke", None)
    fill = sty.get("fill", None)
    op = float(sty.get("opacity", 1.0))
    nones = [None, "none", "None"]
    if not (strk in nones):
        try:
            strk = inkex.Color(strk).to_rgb()
            strkl = strk.lightness
            strkop = float(sty.get("stroke-opacity", 1.0))
            strk.alpha = strkop * op
            strkl = strk.alpha * strkl / 255 + (1 - strk.alpha) * 1
            # effective lightness frac with a white bg
            strk.efflightness = strkl
        except:  # inkex.colors.ColorIdError:
            strk = None
            strkl = None
    else:
        strk = None
        strkl = None
    if not (fill in nones):
        try:
            fill = inkex.Color(fill).to_rgb()
            filll = fill.lightness
            fillop = float(sty.get("fill-opacity", 1.0))
            fill.alpha = fillop * op
            filll = fill.alpha * filll / 255 + (1 - fill.alpha) * 1
            # effective lightness frac with a white bg
            fill.efflightness = filll
        except:  # inkex.colors.ColorIdError:
            fill = None
            filll = None
    else:
        fill = None
        filll = None

    sw = Get_Composed_Width(el, "stroke-width")
    sd = Get_Composed_List(el, "stroke-dasharray")
    if sd in nones:
        sd = None
    if sw in nones or sw == 0 or strk is None:
        sw = None
        strk = None
        sd = None

    ms = sty.get("marker-start", None)
    mm = sty.get("marker-mid", None)
    me = sty.get("marker-end", None)

    class StrokeFill:
        def __init__(self, *args):
            (
                self.stroke,
                self.fill,
                self.strokewidth,
                self.strokedasharray,
                self.markerstart,
                self.markermid,
                self.markerend,
            ) = args

    return StrokeFill(strk, fill, sw, sd, ms, mm, me)


# Gets the caller's location
def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))


# Return a document's visible descendants not in Defs/Metadata/etc
def visible_descendants(svg):
    ndefs = [
        el
        for el in list(svg)
        if not (
            isinstance(
                el, ((inkex.NamedView, inkex.Defs, inkex.Metadata, inkex.ForeignObject))
            )
        )
    ]
    return [v for el in ndefs for v in descendants2(el)]


# Gets the location of the Inkscape binary
# Functions copied from command.py
# Copyright (C) 2019 Martin Owens
global bloc
bloc = None
def Get_Binary_Loc():
    global bloc
    if bloc is None:
        INKSCAPE_EXECUTABLE_NAME = os.environ.get("INKSCAPE_COMMAND")
        if INKSCAPE_EXECUTABLE_NAME == None:
            if sys.platform == "win32":
                # prefer inkscape.exe over inkscape.com which spawns a command window
                INKSCAPE_EXECUTABLE_NAME = "inkscape.exe"
            else:
                INKSCAPE_EXECUTABLE_NAME = "inkscape"
        class CommandNotFound(IOError):
            pass
        def which2(program):
            try:
                return inkex.command.which(program)
            except:
                # Search the path as a backup (primarily for testing)
                try:
                    from shutil import which as warlock
                    for sp in sys.path:
                        if sys.platform == "win32":
                            prog = warlock(program, path=os.environ["PATH"] + ";" + sp)
                            if prog:
                                return prog
                except ImportError:
                    pass
                raise CommandNotFound(f"Can not find the command: '{program}'")
        bloc = which2(INKSCAPE_EXECUTABLE_NAME)
    return bloc


# Get document location or prompt
def Get_Current_File(ext,msgstr):
    tooearly = ivp[0] <= 1 and ivp[1] < 1
    if not (tooearly):
        myfile = ext.document_path()
    else:
        myfile = None

    if myfile is None or myfile == "":
        if tooearly:
            msg = msgstr + "Inkscape must be version 1.1.0 or higher."
        else:
            msg = (
                msgstr + "the SVG must first be saved. Please retry after you have done so."
            )
        inkex.utils.errormsg(msg)
        quit()
        return None
    else:
        return myfile


# Version checking
try:
    inkex_version = inkex.__version__  # introduced in 1.1.2
except:
    try:
        tmp = BaseElement.unittouu  # introduced in 1.1
        inkex_version = "1.1.0"
    except:
        try:
            from inkex.paths import Path, CubicSuperPath
            inkex_version = "1.0.0"
        except:
            inkex_version = "0.92.4"


def vparse(vstr):
    return [int(v) for v in vstr.split(".")]


ivp = vparse(inkex_version)

si_dir = os.path.dirname(os.path.realpath(__file__))
# Generate a temporary file or folder in SI's location / tmp
# tempfile does not always work with Linux Snap distributions
def si_tmp(dirbase='',filename=None):
    if sys.executable[0:4] == "/tmp" or sys.executable[0:5] == "/snap":
        si_dir = os.path.dirname(os.path.realpath(__file__)) # in case si_dir is not loaded
        tmp_dir = os.path.join(si_dir,'tmp')
    else:
        import tempfile
        tmp_dir = tempfile.gettempdir()
    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)
    if filename is not None:                 # filename input
        return os.path.join(tmp_dir,filename)
    else:                                    # directory
        subdir_name = dirbase+str(random.randint(1, 100000))
        subdir_path = os.path.join(tmp_dir, subdir_name)
        while os.path.exists(subdir_path):
            subdir_name = dirbase+str(random.randint(1, 100000))
            subdir_path = os.path.join(tmp_dir, subdir_name)
        os.mkdir(subdir_path)
        return subdir_path

# Calculate all of the size properties of SVGs
# Goal is to deprecate all of the other size functions
def document_size(svg):
    if not(hasattr(svg, "_cdocsize")):
        rvb = svg.get_viewbox()
        wstr = svg.get("width" )
        hstr = svg.get("height")
        
        if rvb == [0, 0, 0, 0]: 
            vb = [0, 0, ipx(wstr), ipx(hstr)]
        else:
            vb = [float(v) for v in rvb]  # just in case
            
        # Get document width and height in pixels
        wn, wu = inkex.units.parse_unit(wstr) if wstr is not None else (vb[2],'px')
        hn, hu = inkex.units.parse_unit(hstr) if hstr is not None else (vb[3],'px')
        
        def parse_preserve_aspect_ratio(pAR):
            align, meetOrSlice = "xMidYMid" , "meet"  # defaults
            valigns = ["xMinYMin", "xMidYMin", "xMaxYMin", "xMinYMid", "xMidYMid", "xMaxYMid", "xMinYMax", "xMidYMax", "xMaxYMax", "none"];
            vmoss   = ["meet", "slice"];
            if pAR:
                values = pAR.split(" ")
                if len(values) == 1:
                    if values[0] in valigns:
                        align = values[0]
                    elif values[0] in vmoss:
                        meetOrSlice = values[0]
                elif len(values) == 2:
                    if values[0] in valigns and values[1] in vmoss:
                        align = values[0]
                        meetOrSlice = values[1]
            return align, meetOrSlice
        align, meetOrSlice =  parse_preserve_aspect_ratio(svg.get('preserveAspectRatio'))
        
        
        xf = inkex.units.convert_unit(str(wn)+' '+wu, 'px')/vb[2] if wu!='%' else wn/100 # width  of uu in px pre-stretch
        yf = inkex.units.convert_unit(str(hn)+' '+hu, 'px')/vb[3] if hu!='%' else hn/100 # height of uu in px pre-stretch
        if align!='none':
            f = min(xf,yf) if meetOrSlice=='meet' else max(xf,yf)
            xmf = {"xMin" : 0, "xMid": 0.5, "xMax":1}[align[0:4]]
            ymf = {"YMin" : 0, "YMid": 0.5, "YMax":1}[align[4:]]
            vb[0],vb[2] = vb[0]+vb[2]*(1-xf/f)*xmf, vb[2]/f*(xf if wu!='%' else 1)
            vb[1],vb[3] = vb[1]+vb[3]*(1-yf/f)*ymf, vb[3]/f*(yf if hu!='%' else 1)
            if wu=='%': wn, wu = vb[2]*f, 'px'
            if hu=='%': hn, hu = vb[3]*f, 'px'
        else:
            if wu=='%': wn, wu, vb[2] = vb[2], 'px', vb[2]/xf
            if hu=='%': hn, hu, vb[3] = vb[3], 'px', vb[3]/yf
                
        wpx = inkex.units.convert_unit(str(wn)+' '+wu, 'px')     # document width  in px
        hpx = inkex.units.convert_unit(str(hn)+' '+hu, 'px')     # document height in px
        uuw  = wpx / vb[2]                                       # uu width  in px (px/uu)
        uuh  = hpx / vb[3]                                       # uu height in px (px/uu)
        uupx = uuw if abs(uuw-uuh)<0.001 else None               # uu size  in px  (px/uu)
                                                                 # should match Scale in Document Properties
                      
        # Get Pages  
        nvs = [el for el in list(svg) if isinstance(el,inkex.NamedView)]
        pgs = [el for nv in nvs for el in list(nv) if el.tag==inkex.addNS('page','inkscape')]
        for pg in pgs:
            pg.bbuu = [ipx(pg.get('x')),    ipx(pg.get('y')),
                       ipx(pg.get('width')),ipx(pg.get('height'))]     
            pg.bbpx = [pg.bbuu[0]*xf,pg.bbuu[1]*yf,pg.bbuu[2]*xf,pg.bbuu[3]*yf]                      
                      
        class DocSize:
            def __init__(self,rawvb,effvb,uuw,uuh,uupx,wunit,hunit,wpx,hpx,xf,yf,pgs):
                self.rawvb = rvb;
                self.effvb = effvb;
                self.uuw   = uuw
                self.uuh   = uuh
                self.uupx  = uupx
                self.wunit = wunit
                self.hunit = hunit
                self.wpx   = wpx;
                self.hpx   = hpx;
                self.rawxf = xf; 
                self.rawyf = yf;
                self.pgs   = pgs;
                try:
                    inkex.Page;
                    self.inkscapehaspgs = True;
                except:
                    self.inkscapehaspgs = False;
            def uutopx(self,v):  # Converts a bounding box specified in uu to pixels
                # xpx = (xuu-vb[0])*uuw
                # ypx = (yuu-vb[1])*uuh
                vo = [(v[0]-self.effvb[0])*self.uuw,(v[1]-self.effvb[1])*self.uuh,
                       v[2]*self.uuw,                v[3]*self.uuh]
                return vo
            def pxtouu(self,v):  # Converts a bounding box specified in pixels to uu
                vo = [v[0]/self.uuw+self.effvb[0],v[1]/self.uuh+self.effvb[1],
                      v[2]/self.uuw,              v[3]/self.uuh]
                return vo
            def unittouu(self,x):
                # Converts any unit into uu
                return inkex.units.convert_unit(x,'px')/self.uupx if self.uupx is not None else None
            def uutopxpgs(self,v): # Version that applies to Pages
                return [v[0]*self.rawxf,v[1]*self.rawyf,v[2]*self.rawxf,v[3]*self.rawyf]
            def pxtouupgs(self,v): # Version that applies to Pages
                return [v[0]/self.rawxf,v[1]/self.rawyf,v[2]/self.rawxf,v[3]/self.rawyf]
        svg._cdocsize = DocSize(rvb,vb,uuw,uuh,uupx,wu,hu,wpx,hpx,xf,yf,pgs)
    return svg._cdocsize
def set_cdocsize(svg, si):
    if si is None and hasattr(svg, "_cdocsize"):  # invalidate
        delattr(svg, "_cdocsize")
inkex.SvgDocumentElement.cdocsize = property(document_size,set_cdocsize)

def set_viewbox_fcn(svg,newvb):
    # svg.set_viewbox(vb)
    uuw,uuh,wunit,hunit = svg.cdocsize.uuw,svg.cdocsize.uuh,svg.cdocsize.wunit,svg.cdocsize.hunit
    svg.set('width', str(inkex.units.convert_unit(str(newvb[2]*uuw)+'px', wunit))+wunit)
    svg.set('height',str(inkex.units.convert_unit(str(newvb[3]*uuh)+'px', hunit))+hunit)
    svg.set('viewBox',' '.join([str(v) for v in newvb]))
    svg.cdocsize = None
inkex.SvgDocumentElement.set_viewbox = set_viewbox_fcn

def standardize_viewbox(svg):
    # Converts viewbox to pixels, removing any non-uniform scaling appropriately
    pgbbs = [pg.bbpx for pg in svg.cdocsize.pgs]
    svg.set('viewBox',' '.join([str(v) for v in svg.cdocsize.effvb]))
    svg.set('width', str(svg.cdocsize.wpx))
    svg.set('height',str(svg.cdocsize.hpx))
    
    # Update Pages appropriately
    svg.cdocsize = None
    for ii,pg in enumerate(svg.cdocsize.pgs):
        newbbuu = svg.cdocsize.pxtouupgs(pgbbs[ii])
        pg.set('x',     str(newbbuu[0]))
        pg.set('y',     str(newbbuu[1]))
        pg.set('width', str(newbbuu[2]))
        pg.set('height',str(newbbuu[3]))
inkex.SvgDocumentElement.standardize_viewbox = standardize_viewbox


# Override Transform's __matmul__ to give old versions __matmul__
# Also optimized for speed
def matmul2(obj, matrix):
    if isinstance(matrix, (Transform)):
        othermat = matrix.matrix
    elif isinstance(matrix, (tuple)):
        othermat = matrix
    else:
        othermat = Transform(matrix).matrix
        # I think this is never called
    return Transform(
        (
            obj.matrix[0][0] * othermat[0][0] + obj.matrix[0][1] * othermat[1][0],
            obj.matrix[1][0] * othermat[0][0] + obj.matrix[1][1] * othermat[1][0],
            obj.matrix[0][0] * othermat[0][1] + obj.matrix[0][1] * othermat[1][1],
            obj.matrix[1][0] * othermat[0][1] + obj.matrix[1][1] * othermat[1][1],
            obj.matrix[0][0] * othermat[0][2]
            + obj.matrix[0][1] * othermat[1][2]
            + obj.matrix[0][2],
            obj.matrix[1][0] * othermat[0][2]
            + obj.matrix[1][1] * othermat[1][2]
            + obj.matrix[1][2],
        )
    )
inkex.transforms.Transform.__matmul__ = matmul2

# Get default style attributes
try:
    from inkex.properties import all_properties
except ModuleNotFoundError:
    from properties2 import all_properties
default_style_atts = {a: v[1] for a, v in all_properties.items()}


def isMask(el):
    if ivp[0] <= 1 and ivp[1] < 2:  # pre-1.2: check tag
        return el.tag[-4:] == "mask"
    else:
        return isinstance(el, (inkex.Mask))

def Run_SI_Extension(effext,name):
    Version_Check(name)
    
    def run_and_cleanup():
        effext.run()
        flush_stylesheet_entries(effext.svg)
    
    alreadyran = False
    cprofile = False
    lprofile = os.getenv("LINEPROFILE") == "True"
    if cprofile or lprofile:
        import io
        profiledir = get_script_path()

        if cprofile:
            import cProfile, pstats
            from pstats import SortKey
    
            pr = cProfile.Profile()
            pr.enable()
        if lprofile:
            try:
                from line_profiler import LineProfiler
    
                lp = LineProfiler()
                import TextParser, RemoveKerning, flatten_plots
                from inspect import getmembers, isfunction, isclass, getmodule
                import pango_renderer
    
                fns = []
                for m in [sys.modules[__name__], TextParser, RemoveKerning, Style0, pango_renderer,
                          inkex.transforms, getmodule(effext)]:
                    fns += [v[1] for v in getmembers(m, isfunction)]
                    for c in getmembers(m, isclass):
                        if getmodule(c[1]) is m:
                            fns += [v[1] for v in getmembers(c[1], isfunction)]
                            for p in getmembers(
                                c[1], lambda o: isinstance(o, property)
                            ):
                                if p[1].fget is not None:
                                    fns += [p[1].fget]
                                if p[1].fset is not None:
                                    fns += [p[1].fset]
                for fn in fns:
                    lp.add_function(fn)
                   
                lp(run_and_cleanup)()
                stdouttrap = io.StringIO()
                lp.dump_stats(os.path.abspath(os.path.join(profiledir, "lprofile.prof")))
                lp.print_stats(stdouttrap)
    
                ppath = os.path.abspath(os.path.join(profiledir, "lprofile.csv"))
                result = stdouttrap.getvalue()
                f = open(ppath, "w", encoding="utf-8")
                f.write(result)
                f.close()
                alreadyran = True
            except ImportError:
                pass

    if not(alreadyran):
        try:
            run_and_cleanup()
        except lxml.etree.XMLSyntaxError:
            try:
                s = effext;
                s.parse_arguments(sys.argv[1:])
                if s.options.input_file is None:
                    s.options.input_file = sys.stdin
                elif "DOCUMENT_PATH" not in os.environ:
                    os.environ["DOCUMENT_PATH"] = s.options.input_file
                
                def overwrite_output(filein,fileout):      
                    try:
                        os.remove(fileout)
                    except:
                        pass
                    arg2 = [Get_Binary_Loc(),"--export-filename",fileout,filein,]
                    subprocess_repeat(arg2)
                tmpname=s.options.input_file.strip('.svg')+'_tmp.svg'
                overwrite_output(s.options.input_file,tmpname);
                os.remove(s.options.input_file)
                os.rename(tmpname,s.options.input_file)
                run_and_cleanup()
            except:
                inkex.utils.errormsg(
                    "Error reading file! Extensions can only run on SVG files.\n\nIf this is a file imported from another format, try saving as an SVG and restarting Inkscape. Alternatively, try pasting the contents into a new document."
                )

    if cprofile:
        pr.disable()
        s = io.StringIO()
        sortby = SortKey.CUMULATIVE
        pr.dump_stats(os.path.abspath(os.path.join(profiledir, "cprofile.prof")))
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats()
        ppath = os.path.abspath(os.path.join(profiledir, "cprofile.csv"))

        result = s.getvalue()
        prefix = result.split("ncalls")[0]
        # chop the string into a csv-like buffer
        result = "ncalls" + result.split("ncalls")[-1]
        result = "\n".join(
            [",".join(line.rstrip().split(None, 5)) for line in result.split("\n")]
        )
        result = prefix + "\n" + result
        f = open(ppath, "w")
        f.write(result)
        f.close()
    
    write_debug()   
    
    # Display accumulated caller info if any
    global callinfo
    try:
        callinfo
    except:
        callinfo = dict();
    sorted_items = sorted(callinfo.items(), key=lambda x: x[1], reverse=True)
    for key, value in sorted_items:
        idebug(f"{key}: {value}")


def vto_xpath(sty):
    if (
        ivp[0] <= 1 and ivp[1] < 2
    ):  # pre-1.2: use v1.1 version of to_xpath from inkex.Style
        import re
        step_to_xpath = [
            (
                re.compile(r"\[(\w+)\^=([^\]]+)\]"),
                r"[starts-with(@\1,\2)]",
            ),  # Starts With
            (re.compile(r"\[(\w+)\$=([^\]]+)\]"), r"[ends-with(@\1,\2)]"),  # Ends With
            (re.compile(r"\[(\w+)\*=([^\]]+)\]"), r"[contains(@\1,\2)]"),  # Contains
            (re.compile(r"\[([^@\(\)\]]+)\]"), r"[@\1]"),  # Attribute (start)
            (re.compile(r"#(\w+)"), r"[@id='\1']"),  # Id Match
            (re.compile(r"\s*>\s*([^\s>~\+]+)"), r"/\1"),  # Direct child match
            # (re.compile(r'\s*~\s*([^\s>~\+]+)'), r'/following-sibling::\1'),
            # (re.compile(r'\s*\+\s*([^\s>~\+]+)'), r'/following-sibling::\1[1]'),
            (re.compile(r"\s*([^\s>~\+]+)"), r"//\1"),  # Decendant match
            (
                re.compile(r"\.([-\w]+)"),
                r"[contains(concat(' ', normalize-space(@class), ' '), ' \1 ')]",
            ),
            (re.compile(r"//\["), r"//*["),  # Attribute only match
            (re.compile(r"//(\w+)"), r"//svg:\1"),  # SVG namespace addition
        ]

        def style_to_xpath(styin):
            return "|".join([rule_to_xpath(rule) for rule in styin.rules])

        def rule_to_xpath(rulein):
            ret = rulein.rule
            for matcher, replacer in step_to_xpath:
                ret = matcher.sub(replacer, ret)
            return ret

        return style_to_xpath(sty)
    else:
        return sty.to_xpath()


def Version_Check(caller):
    siv = "v1.2.29"  # Scientific Inkscape version
    maxsupport = "1.3.1"
    minsupport = "1.1.0"

    logname = "Log.txt"
    NFORM = 200

    maxsupp = vparse(maxsupport)
    minsupp = vparse(minsupport)

    try:
        f = open(logname, "r")
        d = f.readlines()
        f.close()
    except:
        d = []

    displayedform = False
    if len(d) > 0:
        displayedform = d[-1] == "Displayed form screen"
        if displayedform:
            d = d[: len(d) - 1]

    # idebug(ivp)
    prevvp = [vparse(dv[-6:]) for dv in d]
    if (ivp[0] < minsupp[0] or ivp[1] < minsupp[1]) and not (ivp in prevvp):
        msg = (
            "For best results, Scientific Inkscape requires Inkscape version "
            + minsupport
            + " or higher. "
            + "You are running an older version—all features may not work as expected.\n\nThis is a one-time message.\n\n"
        )
        inkex.utils.errormsg(msg)
    if (ivp[0] > maxsupp[0] or ivp[1] > maxsupp[1]) and not (ivp in prevvp):
        msg = (
            "For best results, Scientific Inkscape requires Inkscape version "
            + maxsupport
            + " or lower. "
            + "You are running a newer version—you must be from the future!\n\n"
            + "It might work, it might not. Check if there is a more recent version of Scientific Inkscape available. \n\nThis is a one-time message.\n\n"
        )
        inkex.utils.errormsg(msg)

    from datetime import datetime

    dt = datetime.now().strftime("%Y.%m.%d, %H:%M:%S")
    d.append(
        dt + " Running " + caller + " " + siv + ", Inkscape v" + inkex_version + "\n"
    )

    if len(d) > NFORM:
        d = d[-NFORM:]
        if not (displayedform):
            sif3 = "dt9mt3Br6"
            sif1 = "https://forms.gle/"
            sif2 = "RS6HythP"
            msg = (
                "You have run Scientific Inkscape extensions over "
                + str(NFORM)
                + " times! Thank you for being such a dedicated user!"
                + "\n\nBuilding and maintaining Scientific Inkscape is a time-consuming job,"
                + " and I have no real way of tracking the number of active users. For reporting purposes, I would greatly "
                + "appreciate it if you could sign my guestbook to indicate that you use Scientific Inkscape. "
                + "It is located at\n\n"
                + sif1
                + sif2
                + sif3
                + "\n\nPlease note that this is a one-time message. "
                + "You will never get this message again, so please copy the URL before you click OK.\n\n"
            )
            inkex.utils.errormsg(msg)
        d.append("Displayed form screen")

    try:
        f = open(logname, "w")
        f.write("".join(d))
        f.close()
    except:
        inkex.utils.errormsg(
            "Error: You do not have write access to the directory where the Scientific Inkscape "
            + "extensions are installed. You may have not installed them in the correct location. "
            + "\n\nMake sure you install them in the User Extensions directory, not the Inkscape Extensions "
            + "directory."
        )
        quit()
