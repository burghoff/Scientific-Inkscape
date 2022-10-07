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
    command,
    SvgDocumentElement,
    Group,
    Polyline,
    ShapeElement,
    BaseElement,
)
from applytransform_mod import ApplyTransform
import lxml, math, re, sys, os
from Style2 import Style2


def descendants2(el, return_tails=False):
    # Like Inkex's descendants(), but avoids recursion to avoid recursion depth issues
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

    def getchildren_dict(eli):
        if not (eli in children_dict):
            children_dict[eli] = list(eli)
            for ii in range(len(children_dict[eli])):
                index_dict[children_dict[eli][ii]] = ii
                # store index for later
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
    descendants = [v for v in descendants if isinstance(v, (BaseElement, str))]

    if not (return_tails):
        return descendants
    else:
        # For each descendants return a list of what element we expect our tails to precede
        precedingtails.append(pendingtails)
        # will be one longer than descendants because of the last one
        return descendants, precedingtails, children_dict, parent_dict


BaseElement.descendants2 = property(descendants2)

# Sets a style property
def Set_Style_Comp(el_or_sty, comp, val):
    # isel = isinstance(el_or_sty, (BaseElement))  # is element
    # if isel:
    sty = el_or_sty.cstyle
    # else:
    #     isstr = isinstance(el_or_sty, (str))
    #     sty = el_or_sty
    #     if isstr:
    #         sty = Style2(sty)

    # if sty is not None:
    #     sty = sty.split(";")
    #     compfound = False
    #     for ii in range(len(sty)):
    #         if comp in sty[ii]:
    #             if val is not None:
    #                 sty[ii] = comp + ":" + val
    #             else:
    #                 sty[ii] = ""
    #             compfound = True
    #     if not (compfound):
    #         if val is not None:
    #             sty.append(comp + ":" + val)
    #         else:
    #             pass
    #     sty = [v.strip(";") for v in sty if v != ""]
    #     sty = ";".join(sty)
    # else:
    #     if val is not None:
    #         sty = comp + ":" + val

    if val is None:
        if sty.get(comp) is not None:
            del sty[comp]
    else:
        sty[comp] = val

    # if isel:
    el_or_sty.cstyle = sty  # set element style
    # else:
    #     if isstr:
    #         return str(sty)  # return style string
    #     else:
    #         return sty  # convert back to Style


def dupe_cssdict_entry(oldid, newid, svg):
    # duplicate a style in cssdict
    if svg is not None:
        csssty = svg.cssdict.get(oldid)
        if csssty is not None:
            svg.cssdict[newid] = csssty


estyle = Style2()


def get_cssdict(svg):
    if not (hasattr(svg, "_cssdict")):
        # For certain xpaths such as classes, we can avoid xpath calls
        # by checking the class attributes on a document's descendants directly.
        # This is much faster for large documents.
        hasall = False
        simpleclasses = dict()
        simpleids = dict()
        for sheet in svg.stylesheets:
            for style in sheet:
                xp = vto_xpath(style)
                if xp == "//*":
                    hasall = True
                elif all(
                    [
                        re.compile(r"\.([-\w]+)").sub(r"IAMCLASS", r.rule) == "IAMCLASS"
                        for r in style.rules
                    ]
                ):  # all rules are classes
                    simpleclasses[xp] = [
                        re.compile(r"\.([-\w]+)").sub(r"\1", r.rule)
                        for r in style.rules
                    ]
                elif all(
                    [
                        re.compile(r"#(\w+)").sub(r"IAMID", r.rule) == "IAMID"
                        for r in style.rules
                    ]
                ):  # all rules are ids
                    simpleids[xp] = [
                        re.compile(r"\.([-\w]+)").sub(r"\1", r.rule)[1:]
                        for r in style.rules
                    ]

        knownxpaths = dict()
        if hasall or len(simpleclasses) > 0:
            ds = svg.cdescendants

            cs = [d.get("class") for d in ds]
            if hasall:
                knownxpaths["//*"] = ds
            for xp in simpleclasses:
                knownxpaths[xp] = []
            for ii in range(len(ds)):
                if cs[ii] is not None:
                    cv = cs[ii].split(
                        " "
                    )  # only valid delimeter for multiple classes is space
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
                    if xp in knownxpaths:
                        els = knownxpaths[xp]
                    else:
                        els = svg.xpath(xp)
                    for elem in els:
                        elid = elem.get("id", None)
                        if (
                            elid is not None and style != inkex.Style()
                        ):  # still using Inkex's Style here since from stylesheets
                            if cssdict.get(elid) is None:
                                cssdict[elid] = estyle.copy() + style
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
    if si is None and hasattr(el, "_cspecified_style"):  # invalidate
        delattr(el, "_cspecified_style")
        for k in list(el):
            k.cspecified_style = None # invalidate children
BaseElement.cspecified_style = property(
    get_cspecified_style, set_cspecified_style
)

# A cached cascaded style property
svgpres = ['alignment-baseline', 'baseline-shift', 'clip', 'clip-path', 'clip-rule', 'color', 'color-interpolation', 'color-interpolation-filters', 'color-profile', 'color-rendering', 'cursor', 'direction', 'display', 'dominant-baseline', 'enable-background', 'fill', 'fill-opacity', 'fill-rule', 'filter', 'flood-color', 'flood-opacity', 'font-family', 'font-size', 'font-size-adjust', 'font-stretch', 'font-style', 'font-variant', 'font-weight', 'glyph-orientation-horizontal', 'glyph-orientation-vertical', 'image-rendering', 'kerning', 'letter-spacing', 'lighting-color', 'marker-end', 'marker-mid', 'marker-start', 'mask', 'opacity', 'overflow', 'pointer-events', 'shape-rendering', 'stop-color', 'stop-opacity', 'stroke', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'stroke-opacity', 'stroke-width', 'text-anchor', 'text-decoration', 'text-rendering', 'transform', 'transform-origin', 'unicode-bidi', 'vector-effect', 'visibility', 'word-spacing', 'writing-mode']
excludes = ["clip", "clip-path", "mask", "transform", "transform-origin"]
bstyle = Style2("");
def get_cascaded_style(el):
    # Object's style including any CSS
    # Modified from Inkex's cascaded_style
    if not (hasattr(el, "_ccascaded_style")):
        svg = el.croot
        if svg is not None:
            cssdict = svg.cssdict
        else:
            cssdict = dict()

        csssty = cssdict.get(el.get_id())
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
    if si is None and hasattr(el, "_ccascaded_style"):
        delattr(el, "_ccascaded_style")
BaseElement.ccascaded_style = property(get_cascaded_style, set_ccascaded_style)

# Ccached style attribute that invalidates the cached cascaded / specified
# style whenever the style is changed. Always use this when setting styles.
def get_cstyle(el):
    if not (hasattr(el, "_cstyle")):
        el._cstyle = Style2(el.get("style"))  # el.get() is very efficient
    return el._cstyle
def set_cstyle(el, nsty):
    el.style = nsty
    if not(isinstance(nsty,Style2)):
        nsty = Style2(nsty);
    el._cstyle = nsty
    el.ccascaded_style = None
    el.cspecified_style = None
BaseElement.cstyle = property(get_cstyle, set_cstyle)

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

# Cached transform
def get_ctransform(el):
    if not (hasattr(el, "_ctransform")):
        el._ctransform = el.transform
    return el._ctransform
def set_ctransform(el, newt):
    el.transform = newt
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
    svg = el.croot
    docscale = 1
    # if svg is not None:
    #     docscale = svg.cscale
    sc = cs.get(comp)

    # Get default attribute if empty
    if sc is None:
        sc = default_style_atts[comp]

    if "%" in sc:  # relative width, get parent width
        cel = el
        while sc != cel.cstyle.get(comp):
            cel = cel.getparent()
            # figure out ancestor where % is coming from

        sc = float(sc.strip("%")) / 100
        fs, sf, ct, tmp = Get_Composed_Width(cel.getparent(), comp, 4)
        if nargout == 4:
            # ang = math.atan2(ct.c, ct.d) * 180 / math.pi
            return fs * sc, sf, ct, ang
        else:
            return fs * sc
    else:
        if comp == "font-size":
            sc = {"small": "10px", "medium": "12px", "large": "14px"}.get(sc, sc)

        sw = implicitpx(sc)
        sf = math.sqrt(abs(ct.a * ct.d - ct.b * ct.c)) * docscale  # scale factor
        if nargout == 4:
            return sw * sf, sf, ct, ang
        else:
            return sw * sf

    # if sc is not None:
    # else:
    #     if comp == "font-size":
    #         sf = math.sqrt(abs(ct.a * ct.d - ct.b * ct.c)) * docscale  # scale factor
    #         returnval = 12 * sf
    #         # default font is 12 uu
    #     else:
    #         returnval = None
    #         sf = None

    #     if nargout == 4:
    #         return returnval, sf, ct, ang
    #     else:
    #         return returnval


# Get line-height in user units
def Get_Composed_LineHeight(el):  # cs = el.composed_style();
    # if styin is None:
    cs = el.cspecified_style
    # else:
    #     cs = styin
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
    # cs = el.composed_style();
    # if styin is None:
    cs = el.cspecified_style
    # else:
    #     cs = styin
    # ct = el.composed_transform();
    ct = el.ccomposed_transform
    sc = cs.get(comp)
    svg = el.croot
    docscale = 1
    # if svg is not None:
    #     docscale = svg.cscale
    if sc == "none":
        return "none"
    elif sc is not None:
        sw = sc.split(",")
        # sw = sc.strip().replace("px", "").split(',')
        sf = math.sqrt(abs(ct.a * ct.d - ct.b * ct.c)) * docscale
        sw = [implicitpx(x) * sf for x in sw]
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
    det = (obj.matrix[0][0] * obj.matrix[1][1]) - (obj.matrix[0][1] * obj.matrix[1][0])
    return v2d_simple(
        (obj.matrix[1][1]  * (pt.x - obj.matrix[0][2]) + -obj.matrix[0][1] * (pt.y - obj.matrix[1][2])) / det,
        (-obj.matrix[1][0] * (pt.x - obj.matrix[0][2]) +  obj.matrix[0][0] * (pt.y - obj.matrix[1][2])) / det,
    )
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
from math import fabs
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


def implicitpx(strin):
    # For many properties, a size specification of '1px' actually means '1uu'
    # Even if the size explicitly says '1mm' and the user units are mm, this will be
    # first converted to px and then interpreted to mean user units. (So '1mm' would
    # up being bigger than 1 mm). This returns the size as Inkscape will interpret it (in uu)
    if strin is None:
        return None
    else:
        return inkex.units.convert_unit(strin.lower().strip(), "px")


#    return inkex.units.convert_unit(str.lower().strip(), 'px', default='px') # fails pre-1.1, default is px anyway


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

    mysvg = el.croot
    docscale = 1
    # if mysvg is not None:
    #     docscale = mysvg.cscale

    xs = []
    ys = []
    for p in pts:
        p = ct.apply_to_point(p)
        xs.append(p.x * docscale)
        ys.append(p.y * docscale)
    return xs, ys


# Unlinks clones and composes transform/clips/etc, along with descendants
def unlink2(el):
    if isinstance(el, (Use)):
        useid = el.get("xlink:href")
        # idebug([el.croot,el.root])
        useel = getElementById2(el.croot, useid[1:])
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
                el.get("clip-path"),
                el.get("mask"),
                el.ctransform,
                (el.ccascaded_style),
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

# Unlinks a clone, then searches the descendants of the clone to unlink any
# other clones that are found.
# def recursive_unlink2(el):
#     el = unlink2(el)
#     for d in el.descendants2:
#         if isinstance(el, (Use)):
#             recursive_unlink2(el)

unungroupable = (NamedView, Defs, Metadata, ForeignObject, lxml.etree._Comment)
def ungroup(groupel):
    # Ungroup a group, preserving style, clipping, and masking
    # Remove any comments

    if groupel.croot is not None:
        gparent = groupel.getparent()
        gindex = list(gparent).index(groupel)  # group's location in parent
        gtransform = groupel.ctransform
        gclipurl = groupel.get("clip-path")
        gmaskurl = groupel.get("mask")
        gstyle = groupel.ccascaded_style

        els = list(groupel)
        for el in list(reversed(els)):

            if isinstance(el, lxml.etree._Comment):  # remove comments
                groupel.remove(el)

            if not (isinstance(el, unungroupable)):
                clippedout = compose_all(el, gclipurl, gmaskurl, gtransform, gstyle)
                if clippedout:
                    el.delete2()
                else:
                    gparent.insert(gindex + 1, el)
                    # places above

        if len(groupel.getchildren()) == 0:
            groupel.delete2()

# Group a list of elements, placing the group in the location of the first element            
def group(el_list,moveTCM=False):
    g = new_element(inkex.Group, el_list[0], dupecss=False)
    myi = list(el_list[0].getparent()).index(el_list[0])
    el_list[0].getparent().insert(myi + 1, g)
    for el in el_list:
        g.append(el)
        
    # If moveTCM is set and grouping one element, can move transform/clip/mask to group
    # Handy for adding and properly composing transforms/clips/masks
    if moveTCM and len(el_list)==1:
        g.ctransform = el.ctransform;              el.ctransform = None;
        g.set("clip-path", el.get("clip-path"));   el.set("clip-path", None)
        g.set("mask", el.get("mask"))          ;   el.set("mask", None)
    return g


Itmat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))

# For composing a group's properties onto its children (also group-like objects like Uses)
def compose_all(el, clipurl, maskurl, transform, style):
    if style is not None:  # style must go first since we may change it with CSS
        mysty = el.ccascaded_style
        compsty = style + mysty
        compsty["opacity"] = str(
            float(mysty.get("opacity", "1")) * float(style.get("opacity", "1"))
        )  # opacity accumulates at each layer
        el.cstyle = compsty

    if clipurl is not None:
        # idebug([el.get_id2(),clipurl])
        cout = merge_clipmask(el, clipurl)  # clip applied before transform, fix first
    if maskurl is not None:
        merge_clipmask(el, maskurl, mask=True)
    if clipurl is not None:
        fix_css_clipmask(el)
    if maskurl is not None:
        fix_css_clipmask(el, mask=True)

    if transform is not None:
        if transform.matrix != Itmat:
            if el.ctransform.matrix != Itmat:
                el.ctransform = transform @ el.ctransform
            else:
                el.ctransform = transform

    if clipurl is None:
        return False
    else:
        return cout


# If an element has clipping/masking specified in a stylesheet, this will override any attributes
# I think this is an Inkscape bug
# Fix by creating a style specific to my id that includes the new clipping/masking
def fix_css_clipmask(el, mask=False):
    if not (mask):
        cm = "clip-path"
    else:
        cm = "mask"

    svg = el.croot
    if svg is not None:
        cssdict = svg.cssdict
    else:
        cssdict = dict()

    mycss = cssdict.get(el.get_id())
    if mycss is not None:
        if mycss.get(cm) is not None and mycss.get(cm) != el.get(cm):
            svg = el.croot
            if not (hasattr(svg, "stylesheet_entries")):
                svg.stylesheet_entries = dict()
            svg.stylesheet_entries["#" + el.get_id()] = cm + ":" + el.get(cm)
            mycss[cm] = el.get(cm)
    if el.cstyle.get(cm) is not None:  # also clear local style
        Set_Style_Comp(el, cm, None)


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
def unique(lst):
    lst2 = [];
    for ii in reversed(range(len(lst))):
        if lst[ii] not in lst[:ii]:
            lst2.insert(0,lst[ii]) 
    return lst2

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
        if el.get_link('clip-path') is not None:
            isrect = False
        if el.get_link('mask') is not None:
            isrect = False
            
    if isrect:
        return True, pth
    else:
        return False, None

def merge_clipmask(node, newclipurl, mask=False):
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

    if newclipurl is not None:
        svg = node.croot
        cmstr = "clip-path"
        if mask:
            cmstr = "mask"

        if node.ctransform is not None:
            # Clip-paths on nodes with a transform have the transform
            # applied to the clipPath as well, which we don't want.
            # Duplicate the new clip and apply node's inverse transform to its children.
            clippath = getElementById2(svg, newclipurl[5:-1])
            if clippath is not None:
                d = clippath.duplicate2()
                if not (hasattr(svg, "newclips")):
                    svg.newclips = []
                svg.newclips.append(d)  # for later cleanup
                for k in list(d):
                    compose_all(k, None, None, -node.ctransform, None)
                newclipurl = d.get_id2(2)

        newclipnode = getElementById2(svg, newclipurl[5:-1])
        if newclipnode is not None:
            for k in list(newclipnode):
                if isinstance(k, (Use)):
                    k = unlink2(k)

        

        oldclip = node.get_link(cmstr)
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
            if newclipnode is not None and len(list(newclipnode)) == 1:
                newclipisrect, newclippth = isrectangle(list(newclipnode)[0])

            couts = []
            for k in reversed(list(d)):  # may be deleting, so reverse
                oldclipisrect, oldclippth = isrectangle(k)
                if newclipisrect and oldclipisrect and mask == False:
                    # For rectangular clips, we can compose them easily
                    # Since most clips are rectangles this semi-fixes the PDF clip export bug
                    cout = compose_clips(k, newclippth, oldclippth)
                else:
                    cout = merge_clipmask(k, newclipurl, mask)
                couts.append(cout)
            cout = all(couts)

        if oldclip is None:
            node.set(cmstr, newclipurl)
            cout = False

        return cout


# Repeated getElementById lookups can be really slow, so instead create a cached iddict property.
# When an element is created that may be needed later, it must be added using add_to_iddict.
def getElementById2(svg, elid):
    if svg is not None:
        return svg.iddict.get(elid)
    else:
        return None


def add_to_iddict(el, todel=None):
    svg = el.croot
    svg.iddict[el.get_id2()] = el
    if todel is not None:
        del svg.iddict[todel]


def getiddict(svg):
    if not (hasattr(svg, "_iddict")):
        svg._iddict = dict()
        for el in descendants2(svg):
            svg._iddict[el.get_id2()] = el
    return svg._iddict


inkex.SvgDocumentElement.iddict = property(getiddict)

# A cached list of all descendants of an svg (not necessarily in order)
def getcdescendants(svg):
    return list(svg.iddict.values())


inkex.SvgDocumentElement.cdescendants = property(getcdescendants)

# Deletes an element from cached dicts on deletion
def delete2(el):
    svg = el.croot
    if svg is not None:
        try:
            del svg.iddict[el.get_id2()]
        except KeyError:
            pass
    el.croot = None
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
    ids = svg.get_ids()
    new_id = None
    size = math.ceil(math.log10(len(ids))) + 1
    _from = 10 ** size - 1
    _to = 10 ** size
    while new_id is None or new_id in ids:
        # Do not use randint because py2/3 incompatibility
        new_id = prefix + str(int(random.random() * _from - _to) + _to)
    svg.ids.add(new_id)
    # debug(new_id)
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
        # idebug('unassigned '+el.getparent().get_id())
    eid = el.get("id")
    if as_url > 0:
        eid = "#" + eid
    if as_url > 1:
        eid = f"url({eid})"
    return eid


BaseElement.get_id2 = get_id2_func



# Modified from Inkex's get_path
# Correctly calculates path for rectangles and ellipses
def get_path2(el):
    class MiniRect:  # mostly from inkex.elements._polygons
        def __init__(self, el):
            self.left = implicitpx(el.get("x", "0"))
            self.top = implicitpx(el.get("y", "0"))
            self.width = implicitpx(el.get("width", "0"))
            self.height = implicitpx(el.get("height", "0"))
            self.rx = implicitpx(el.get("rx", el.get("ry", "0")))
            self.ry = implicitpx(el.get("ry", el.get("rx", "0")))
            self.right = self.left + self.width
            self.bottom = self.top + self.height

        def get_path(self):
            """Calculate the path as the box around the rect"""
            if self.rx:
                rx, ry = self.rx, self.ry  # pylint: disable=invalid-name
                return (
                    "M {1},{0.top}"
                    "L {2},{0.top}    A {0.rx},{0.ry} 0 0 1 {0.right},{3}"
                    "L {0.right},{4}  A {0.rx},{0.ry} 0 0 1 {2},{0.bottom}"
                    "L {1},{0.bottom} A {0.rx},{0.ry} 0 0 1 {0.left},{4}"
                    "L {0.left},{3}   A {0.rx},{0.ry} 0 0 1 {1},{0.top} z".format(
                        self,
                        self.left + rx,
                        self.right - rx,
                        self.top + ry,
                        self.bottom - ry,
                    )
                )
            return "M {0.left},{0.top} h {0.width} v {0.height} h {1} z".format(
                self, -self.width
            )

    class MiniEllipse:  # mostly from inkex.elements._polygons
        def __init__(self, el):
            self.cx = implicitpx(el.get("cx", "0"))
            self.cy = implicitpx(el.get("cy", "0"))
            if isinstance(el, (inkex.Ellipse)):  # ellipse
                self.rx = implicitpx(el.get("rx", "0"))
                self.ry = implicitpx(el.get("ry", "0"))
            else:  # circle
                self.rx = implicitpx(el.get("r", "0"))
                self.ry = implicitpx(el.get("r", "0"))

        def get_path(self):
            return (
                "M {cx},{y} "
                "a {rx},{ry} 0 1 0 {rx}, {ry} "
                "a {rx},{ry} 0 0 0 -{rx}, -{ry} z"
            ).format(cx=self.cx, y=self.cy - self.ry, rx=self.rx, ry=self.ry)

    if isinstance(el, (inkex.Rectangle)):
        pth = MiniRect(el).get_path()
    elif isinstance(el, (inkex.Circle, inkex.Ellipse)):
        pth = MiniEllipse(el).get_path()
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
        el.tag = "{http://www.w3.org/2000/svg}path"
        el.set("d", str(pth))

# Alternate bbox function that requires no command call
# Uses extents for text, includes stroke width for paths
def bounding_box2(el,dotransform=True,includestroke=True):
    if not(hasattr(el,'_cbbox')):
        el._cbbox = dict()
        
    if (dotransform,includestroke) not in el._cbbox:
        ret = None
        if isinstance(el, (inkex.TextElement)):
            ret = el.parsed_text.get_full_extent();
        elif isinstance(el, otp_support):
            pth = get_path2(el)
            if len(pth)>0:
                bb = Path(pth).to_absolute().bounding_box()
                
                sw = implicitpx(el.cspecified_style.get('stroke-width','0px'))
                if el.cspecified_style.get('stroke') is None or not(includestroke):
                    sw = 0;
                ret = bbox([bb.left-sw/2, bb.top-sw/2,
                               bb.width+sw,bb.height+sw])
        elif isinstance(el,(SvgDocumentElement,Group,inkex.Layer,inkex.ClipPath)) or isMask(el):
            ret = bbox(None)
            for d in list(el):
                dbb = bounding_box2(d,dotransform=False,includestroke=includestroke);
                if dbb is not None:
                    ret = ret.union(dbb.transform(d.ctransform))
            if ret.isnull:
                ret = None
        elif isinstance(el,(inkex.Image)):
            ret = bbox([implicitpx(el.get(v, "0")) for v in ['x',"y","width","height"]]);
        elif isinstance(el,(inkex.Use,)):
            lel = el.get_link('xlink:href');
            
            if lel is not None:
                ret = bounding_box2(lel,dotransform=False)
                ret = ret.transform(lel.ctransform) # clones have the transform of the link, but not anything above
    
        if ret is not None:
            for cm in ['clip-path','mask']:
                clip = el.get_link(cm)
                if clip is not None:
                   cbb = bounding_box2(clip,dotransform=False,includestroke=False)
                   if cbb is not None:
                       ret = ret.intersection(cbb)
                   else:
                       ret = None     
                
            if dotransform:
                if ret is not None:
                    ret = ret.transform(el.ccomposed_transform)
        el._cbbox[(dotransform,includestroke)] = ret
    return el._cbbox[(dotransform,includestroke)]
bb2_support = (inkex.TextElement,inkex.Image,inkex.Use,
               SvgDocumentElement,inkex.Group,inkex.Layer) + otp_support

def set_cbbox(el,val):
    if val is None and hasattr(el,'_cbbox'):
        delattr(el,'_cbbox')
inkex.BaseElement.cbbox = property(bounding_box2,set_cbbox)
inkex.SvgDocumentElement.cbbox = property(bounding_box2,set_cbbox)

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
                if el.tag in ['{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF',
                                  '{http://creativecommons.org/ns#}Work',
                                  '{http://purl.org/dc/elements/1.1/}format',
                                  '{http://purl.org/dc/elements/1.1/}type']:
                    ret=False
                elif isinstance(el,(NamedView, Defs, Metadata, ForeignObject, inkex.Guide,
                              inkex.ClipPath,inkex.StyleElement,
                              Tspan,inkex.FlowRegion,inkex.FlowPara)) or isMask(el):
                    ret=False
            else:
                ret = False
            render_dict[el] = ret
            return ret

    # for d in els:
    #     if not(isinstance(d, bb2_support) or not(isrendered(d))):
    #         dh.idebug((d.typename,d.tag,d.get_id2()))
    
    if all([isinstance(d, bb2_support) or not(isrendered(d)) for d in els]):
        if forceupdate:
            if hasattr(slf.svg, '_char_table'):
                delattr(slf.svg,'_char_table')
            for d in els:
                d.cbbox = None
        if any([isinstance(d, (inkex.TextElement,)) for d in els]):
            import TextParser
            slf.svg.make_char_table(els=els)
        ret = dict()
        for d in els:
            if isinstance(d, bb2_support) and isrendered(d):
                mbbox = d.cbbox;
                if mbbox is not None:
                    ret[d.get_id2()] = mbbox.sbb
                    # ret[d.get_id2()] = (mbbox*slf.svg.cscale).sbb
    else:
        ret = Get_Bounding_Boxes(slf, forceupdate)
        # dh.idebug('fallback')
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
def Get_Bounding_Boxes(
    s=None, getnew=False, filename=None, inkscape_binary=None,extra_args = []
):
    # Gets all of a document's bounding boxes (by ID), in user units
    # Note that this uses a command line call, so by default it will only get the values from BEFORE the extension is called
    # Set getnew to True to make a temporary copy of the file
    if filename is None:
        filename = s.options.input_file
    # if pxinuu is None:
    # pxinuu = s.svg.unittouu("1px")

    # Query Inkscape
    if not (getnew):
        tFStR = commandqueryall(filename, inkscape_binary=inkscape_binary,extra_args=extra_args)
    else:
        tmpname = filename + "_tmp"
        command.write_svg(s.svg, tmpname)
        tFStR = commandqueryall(tmpname, inkscape_binary=inkscape_binary,extra_args=extra_args)
        os.remove(tmpname)
        
    
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
        bbs[key] = data
    
    # Inkscape always reports a bounding box in pixels, relative to the viewbox
    # Convert to user units for the output
    if s is None: svg = svg_from_file(filename);
    else:         svg = s.svg;
    vb = svg.get_viewbox2();
        
    # pxperuu_x = float(inkex.units.convert_unit(svg.get('width' ), 'px')  or vb[2]) / float(vb[2])
    # pxperuu_y = float(inkex.units.convert_unit(svg.get('height'), 'px')  or vb[3]) / float(vb[3])
    # pxperuu = min(pxperuu_x,pxperuu_y)
    # idebug((pxperuu_x,pxperuu_y))
    # effvb = [vb[0]+vb[2]/2*(1-pxperuu_x/pxperuu),
    #          vb[1]+vb[3]/2*(1-pxperuu_y/pxperuu),
    #          vb[2]*pxperuu_x/pxperuu,
    #          vb[3]*pxperuu_y/pxperuu] # bad scaling stretches viewbox
    
    # Viewbox function now automatically corrects non-uniform scale
    pxperuu = float(inkex.units.convert_unit(svg.get('width' ), 'px')  or vb[2]) / float(vb[2])
    
    for k in bbs:
        bbs[k] = [bbs[k][0]/pxperuu+vb[0],bbs[k][1]/pxperuu+vb[1],
                  bbs[k][2]/pxperuu,         bbs[k][3]/pxperuu]
        
        # bbs[k] = [bbs[k][0]*svg.cscale,bbs[k][1]*svg.cscale,
        #           bbs[k][2]*svg.cscale,bbs[k][3]*svg.cscale]
        
    return bbs


# 2022.02.03: I think the occasional hangs come from the call to command.
# I think this is more robust. Make a tally below if it freezes:
def commandqueryall(fn, inkscape_binary=None,extra_args = []):
    if inkscape_binary is None:
        bfn = Get_Binary_Loc()
    else:
        bfn = inkscape_binary
    arg2 = [bfn, "--query-all"]+extra_args+[fn]

    # idebug(arg2)

    p = subprocess_repeat(arg2)
    tFStR = p.stdout
    return tFStR

# Get SVG from file
from inkex import load_svg
def svg_from_file(fin):
    svg = load_svg(fin).getroot()
    return svg

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
def get_link_fcn(el,typestr,svg=None):
    if svg is None:
        svg = el.croot   # need to specify svg for Styles but not BaseElements
    if el.get(typestr) is not None:
        if typestr=='xlink:href':
            urlid = el.get(typestr)[1:]
        else:
            urlid = el.get(typestr)[5:-1]
        urlel = getElementById2(svg, urlid)
        if urlel is not None:
            return urlel
    return None
BaseElement.get_link = get_link_fcn
Style2.get_link      = get_link_fcn

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


def idebug(x):
    inkex.utils.debug(x)

import time
global lasttic
def tic():
    global lasttic
    lasttic = time.time()
def toc():
    global lasttic
    idebug(time.time()-lasttic)

# def get_parent_svg(el):
#     if not (hasattr(el, "svg")):
#         # slightly faster than el.root
#         myn = el
#         while myn.getparent() is not None:
#             myn = myn.getparent()
#         if isinstance(myn, SvgDocumentElement):
#             el.svg = myn
#         else:
#             el.svg = None
#     return el.svg

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
        for k in el.getchildren():
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
        for k in el.getchildren():
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
                        ts.text = w; ts.cstyle=Style2(sty+'font-family:'+newfont)
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
        for d in el.descendants2:
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
    


def global_transform(el, trnsfrm, irange=None, trange=None):
    # Transforms an object and fuses it to any paths, preserving stroke
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
    ApplyTransform().recursiveFuseTransform(el, irange=irange, trange=trange)

    if sw is not None:
        neww, sf, ct, ang = Get_Composed_Width(el, "stroke-width", nargout=4)
        Set_Style_Comp(el, "stroke-width", str(sw / sf))
        # fix width
    if not (sd in [None, "none"]):
        nd, sf = Get_Composed_List(el, "stroke-dasharray", nargout=2)
        Set_Style_Comp(
            el, "stroke-dasharray", str([sdv / sf for sdv in sd]).strip("[").strip("]")
        )
        # fix dash




# Delete and prune empty ancestor groups
def deleteup(el):
    myp = el.getparent()
    el.delete2()
    if myp is not None:
        myc = myp.getchildren()
        if myc is not None and len(myc) == 0:
            deleteup(myp)


# Combines a group of path-like elements
def combine_paths(els, mergeii=0):
    pnew = Path()
    si = []
    # start indices
    for el in els:
        pth = Path(el.get_path()).to_absolute().transform(el.ccomposed_transform)
        if el.get("inkscape-academic-combined-by-color") is None:
            si.append(len(pnew))
        else:
            cbc = el.get(
                "inkscape-academic-combined-by-color"
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

    mel.set("inkscape-academic-combined-by-color", " ".join([str(v) for v in si]))
    for s in range(len(els)):
        if s != mergeii:
            deleteup(els[s])


# Gets all of the stroke and fill properties from a style
# Alpha is its effective alpha including opacity
# Note to self: inkex.Color inherits from list
def get_strokefill(el):
    # if styin is None:
    sty = el.cspecified_style
    # else:
    #     sty = styin
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

# def get_viewbox2(self):
# """Parse and return the document's viewBox attribute"""
# try:
#     ret = [
#         float(unit) for unit in re.split(",\s*|\s+", self.get("viewBox", "0"))
#     ]
# except ValueError:
#     ret = ""
# if len(ret) != 4:
#     return [0, 0, 0, 0]
# return ret

# Cached version-specific document scale
# def get_cscale(svg):
    # if not (hasattr(svg, "_cscale")):
    #     if ivp[0] <= 1 and ivp[1] < 2:  # pre-1.2: return scale
    #         svg._cscale = svg.scale
    #     else:  # post-1.2: return old scale
    #         vb = svg.get_viewbox2()
    #         scale_x = float(
    #             svg.unittouu(svg.get("width")) or vb[2]
    #         ) / float(vb[2])
    #         scale_y = float(
    #             svg.unittouu(svg.get("height")) or vb[3]
    #         ) / float(vb[3])
    #         svg._cscale = max([scale_x, scale_y])
    #         # idebug([scale_x, scale_y])
    #         # idebug([svg.unittouu(svg.get("width")),vb[2],svg.unit])
    # return 1;#svg._cscale  # removed scale on 2022.09.10 (fully remove later)
# inkex.SvgDocumentElement.cscale = property(get_cscale)

# Returns effective viewbox of all documents
def get_viewbox2_fcn(svg):
    vb = svg.get_viewbox()
    if vb == [0, 0, 0, 0]: 
        vb = [0, 0, implicitpx(svg.get("width")), implicitpx(svg.get("height"))]
        
    # When a document has non-uniform scaling, Inkscape automatically stretches
    # the viewbox to make it uniform
    pxperuu_x = float(inkex.units.convert_unit(svg.get('width' ), 'px')  or vb[2]) / float(vb[2])
    pxperuu_y = float(inkex.units.convert_unit(svg.get('height'), 'px')  or vb[3]) / float(vb[3])
    pxperuu = min(pxperuu_x,pxperuu_y)
    effvb = [vb[0]+vb[2]/2*(1-pxperuu_x/pxperuu),
             vb[1]+vb[3]/2*(1-pxperuu_y/pxperuu),
             vb[2]*pxperuu_x/pxperuu,
             vb[3]*pxperuu_y/pxperuu]
    return effvb
inkex.SvgDocumentElement.get_viewbox2 = get_viewbox2_fcn

# Conversion between pixels and user units for a document
def cpxperuu_fcn(svg):
    if not(hasattr(svg, "_cpxperuu")):
        vb = svg.get_viewbox2();
        svg._cpxperuu = float(inkex.units.convert_unit(svg.get('width' ), 'px')  or vb[2]) / float(vb[2])
        # vb function ensures uniform scaling
    return svg._cpxperuu
inkex.SvgDocumentElement.cpxperuu = property(cpxperuu_fcn)

# The original unittouu function did not properly convert to uu when a scale is applied. 
def unittouu2(svg,x):
    return inkex.units.convert_unit(x,'px')/svg.cpxperuu
inkex.SvgDocumentElement.unittouu2 = unittouu2

# Gets the absolute size of a uu in pixels
# Also returns the unit the document width & height are specified in
def get_uusz(svg):
    if not (hasattr(svg, "_ccuuszpx")):
        vb = svg.get_viewbox2()
        wunit = inkex.units.parse_unit(svg.get('width'))
        if wunit is not None:
            wunit = wunit[1]                  # document width unit
        else:
            wunit = 'px'
        hunit = inkex.units.parse_unit(svg.get('height'))
        if hunit is not None:
            hunit = hunit[1]                  # document height unit
        else:
            hunit = 'px'
        uuw = inkex.units.convert_unit(svg.get('width'),'px')/vb[2]    # uu width in px
        uuh = inkex.units.convert_unit(svg.get('height'),'px')/vb[3]   # uu height in px
        svg._ccuuszpx = (uuw,uuh,wunit,hunit)
    return svg._ccuuszpx
inkex.SvgDocumentElement.uusz = property(get_uusz)

# Sets the viewbox of a document, updating its width and height correspondingly
def set_viewbox_fcn(svg,newvb):
    uuw,uuh,wunit,hunit = svg.uusz
    svg.set('width', str(inkex.units.convert_unit(str(newvb[2]*uuw)+'px', wunit))+wunit)
    svg.set('height',str(inkex.units.convert_unit(str(newvb[3]*uuh)+'px', hunit))+hunit)
    svg.set('viewBox',' '.join([str(v) for v in newvb]))
inkex.SvgDocumentElement.set_viewbox = set_viewbox_fcn


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
    try:
        effext.run()
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
            s.run()
        except:
            inkex.utils.errormsg(
                "Error reading file! Extensions can only run on SVG files.\n\nIf this is a file imported from another format, try saving as an SVG and restarting Inkscape. Alternatively, try pasting the contents into a new document."
            )
    write_debug()

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
    siv = "v1.2.27"  # Scientific Inkscape version
    maxsupport = "1.2.0"
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
