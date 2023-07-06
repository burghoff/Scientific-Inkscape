#!/usr/bin/env python
# coding=utf-8
# Copyright (c) 2023 David Burghoff <dburghoff@nd.edu>
# Functions modified from Inkex were made by
#                    Martin Owens <doctormo@gmail.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Thomas Holder <thomas.holder@schrodinger.com>
#                    Jonathan Neuhauser <jonathan.neuhauser@outlook.com>
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# A collection of functions that provide caching of certain Inkex properties. 
# Most provide the same functionality as the regular properties,
# but with a 'c' in front of the name. For example,
#   Style: cstyle, cspecified_style, ccascaded_style
#   Transform: ctransform, ccomposed_transform
#   Miscellaneous: croot, cdefs, ctag
# Most are invalidated by setting to None (except ctransform).
#
# Also gives SvgDocumentElements some dictionaries that are used to speed up
# various lookups:
#   svg.iddict: elements by their ID
#   svg.cssdict: CSS styles by ID
# 
# Lastly, several core Inkex functions are overwritten with versions that
# use the cache. For example, getElementById uses svg.iddict to avoid xpath
# calls.


import inkex
from Style0 import Style0
from inkex import BaseElement, SvgDocumentElement
import lxml, re
EBget = lxml.etree.ElementBase.get;
EBset = lxml.etree.ElementBase.set;



# Adds ctag to the inkex classes, which holds each class's corresponding tag
# Checking the tag is usually much faster than instance checking, which can
# substantially speed up low-level functions.
try:
    lt = dict(inkex.elements._parser.NodeBasedLookup.lookup_table)
except:
    lt = dict(inkex.elements._base.NodeBasedLookup.lookup_table)
shapetags = set();
for k,v in lt.items():
    for v2 in v:
        v2.ctag = inkex.addNS(k[1],k[0])
        if issubclass(v2, inkex.ShapeElement):
            shapetags.add(v2.ctag)

# Cached specified style property
cstytags = shapetags | {SvgDocumentElement.ctag}
def get_cspecified_style(el):
    if not (hasattr(el, "_cspecified_style")):
        parent = el.getparent()
        if parent is not None and parent.tag in cstytags:
            ret = parent.cspecified_style + el.ccascaded_style
        else:
            ret = el.ccascaded_style
        el._cspecified_style = ret
    return el._cspecified_style
def set_cspecified_style(el, si):
    if si is None:
        try:  
            delattr(el, "_cspecified_style")
            for k in list(el):
                k.cspecified_style = None # invalidate children
        except:
            pass
BaseElement.cspecified_style = property(
    get_cspecified_style, set_cspecified_style
)

# Cached cascaded style property
svgpres = {'alignment-baseline', 'baseline-shift', 'clip', 'clip-path', 'clip-rule', 'color', 'color-interpolation', 'color-interpolation-filters', 'color-profile', 'color-rendering', 'cursor', 'direction', 'display', 'dominant-baseline', 'enable-background', 'fill', 'fill-opacity', 'fill-rule', 'filter', 'flood-color', 'flood-opacity', 'font-family', 'font-size', 'font-size-adjust', 'font-stretch', 'font-style', 'font-variant', 'font-weight', 'glyph-orientation-horizontal', 'glyph-orientation-vertical', 'image-rendering', 'kerning', 'letter-spacing', 'lighting-color', 'marker-end', 'marker-mid', 'marker-start', 'mask', 'opacity', 'overflow', 'pointer-events', 'shape-rendering', 'stop-color', 'stop-opacity', 'stroke', 'stroke-dasharray', 'stroke-dashoffset', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'stroke-opacity', 'stroke-width', 'text-anchor', 'text-decoration', 'text-rendering', 'transform', 'transform-origin', 'unicode-bidi', 'vector-effect', 'visibility', 'word-spacing', 'writing-mode'}
excludes = {"clip", "clip-path", "mask", "transform", "transform-origin"}
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

        csssty = cssdict.get(el.get_id())
        locsty = el.cstyle

        # Add any presentation attributes to local style
        attsty = Style0.__new__(Style0)
        for a in el.attrib:
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
    if si is None:
        try:  
            delattr(el, "_ccascaded_style")
        except:
            pass
BaseElement.ccascaded_style = property(get_cascaded_style, set_ccascaded_style)


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
        vstr = str(value)
        if vstr=='':
            if 'style' in el.attrib:
               del el.attrib['style']
        else:
            EBset(el,'style',vstr)
            
        if not isinstance(value, CStyle):
            value = CStyle(value,el)
        el._cstyle = value
        el.ccascaded_style = None
        el.cspecified_style = None
BaseElement.cstyle = CStyleDescriptor()


# Returns non-comment children
comment_tag = lxml.etree.Comment
def list2(el):
    return [k for k in list(el) if not(k.tag == comment_tag)]

# Cached composed_transform, which can be invalidated by changes to
# transform of any ancestor.
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
        for k in list2(el):
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


# Cached root property
svgtag = SvgDocumentElement.ctag
def get_croot(el):
    try:
        return el._croot
    except:
        myn = el
        while myn.getparent() is not None:
            myn = myn.getparent()
        if myn.tag == svgtag:
            el._croot = myn
        else:
            el._croot = None
        return el._croot
def set_croot(el, ri):
    el._croot = ri
BaseElement.croot = property(get_croot, set_croot)

# Version of get_ids that uses iddict
def get_ids_func(svg):
    """Returns a set of unique document ids"""
    if not svg.ids:
        if hasattr(svg,"_iddict"): # don't use iddict, get_iddict calls this
            svg.ids = set(svg._iddict.keys())
        else:
            svg.ids = set(svg.xpath("//@id"))
    return svg.ids
inkex.SvgDocumentElement.get_ids = get_ids_func

# Version of get_unique_id that removes randomness by keeping a running count
from typing import Optional, List
def get_unique_id_fcn(
    svg,
    prefix: str,
    size: Optional[int] = None,
    blacklist: Optional[List[str]] = None,
):
    ids = svg.get_ids()
    if blacklist is not None:
        ids.update(blacklist)
    new_id = None
    if not hasattr(svg,'_prefixcounter'):
        svg._prefixcounter = dict()
    cnt = svg._prefixcounter.get(prefix,0)
    while new_id is None or new_id in ids:
        new_id = prefix + str(cnt)
        cnt+=1
    svg._prefixcounter[prefix]=cnt
    svg.ids.add(new_id)
    return new_id
inkex.SvgDocumentElement.get_unique_id = get_unique_id_fcn

# Version of set_random_id that uses cached root
def set_random_id_fcn(
        el,
        prefix: Optional[str] = None,
        size: Optional[int] = None,
        backlinks: bool = False,
        blacklist: Optional[List[str]] = None,
    ):
        prefix = str(el) if prefix is None else prefix
        el.set_id(
            el.croot.get_unique_id(prefix, size=size, blacklist=blacklist),
            backlinks=backlinks,
        )
inkex.BaseElement.set_random_id = set_random_id_fcn

# Version of get_id that uses the low-level get
def get_id_func(el, as_url=0):
    if "id" not in el.attrib:
        el.set_random_id(el.TAG)
    eid = EBget(el,'id')
    if as_url > 0:
        eid = "#" + eid
        if as_url > 1:
            eid = f"url({eid})"
    return eid
BaseElement.get_id  = get_id_func

# Repeated getElementById lookups can be slow, so instead create a cached iddict property.
# When an element is created that may be needed later, it must be added using svg.iddict.add.
urlpat = re.compile(r'^url\(#(.*)\)$|^#')
def getElementById_func(svg, eid: str, elm="*", literal=False):
    if eid is not None and not literal:
        eid = urlpat.sub(r'\1', eid.strip())
    return svg.iddict.get(eid)
inkex.SvgDocumentElement.getElementById = getElementById_func;


# Add iddict, which keeps track of the IDs in a document
class iddict(inkex.OrderedDict):
    def __init__(self,svg):
        self.svg = svg
        toassign = []
        for el in svg.descendants2():
            if "id" in el.attrib:
                self[EBget(el,'id')] = el
            else:
                toassign.append(el)
            el.croot = svg  # do now to speed up later
        for el in toassign:
            el.set_random_id(el.TAG)
            self[EBget(el,'id')] = el
    def add(self,el):
        elid = el.get_id() # fine since el should have a croot to get called here
        if elid in self and not self[elid]==el:
            # Make a new id when there's a conflict
            el.set_random_id(el.TAG)
            elid = el.get_id()
        self[elid] = el
    @property
    def ds(self):  # all svg descendants, not necessarily in order
        return list(self.values())
    def remove(self,el):
        elid = el.get_id()
        if elid in self:
            del self[elid]
def get_iddict(svg):
    if not (hasattr(svg, "_iddict")):
        svg._iddict = iddict(svg)
    return svg._iddict
inkex.SvgDocumentElement.iddict = property(get_iddict)

# A dict that keeps track of the CSS style for each element
estyle = Style0()
estyle2 = inkex.Style()  # still using Inkex's Style here since from stylesheets
class cssdict(inkex.OrderedDict):
    def __init__(self,svg):
        self.svg = svg
        
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
                xp = style.to_xpath()
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
            ds = svg.iddict.ds

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
                idel = svg.getElementById(sid)
                if idel is not None:
                    knownxpaths[xp].append(idel)

        # Now run any necessary xpaths and get the element styles
        super().__init__()
        for sheet in svg.croot.stylesheets:
            for style in sheet:
                try:
                    # els = svg.xpath(style.to_xpath())  # original code
                    xp = style.to_xpath()
                    style0v = Style0(style)
                    if xp in knownxpaths:
                        els = knownxpaths[xp]
                    else:
                        els = svg.xpath(xp)
                    for elem in els:
                        elid = elem.get("id", None)
                        if elid is not None and style != estyle2: 
                            if self.get(elid) is None:
                                self[elid] = style0v.copy()
                            else:
                                self[elid] += style
                except (lxml.etree.XPathEvalError, TypeError):
                    pass
    def dupe_entry(self,oldid, newid):
        csssty = self.get(oldid)
        if csssty is not None:
            self[newid] = csssty
def get_cssdict(svg):
    try:
        return svg._cssdict
    except:
        svg._cssdict = cssdict(svg)
        return svg._cssdict
inkex.SvgDocumentElement.cssdict = property(get_cssdict)


# A version of descendants that also returns a list of elements whose tails
# precede each element. (This is helpful for parsing text.)
def descendants2(el, return_tails=False):
    descendants = [el]
    precedingtails = [[]]
    endsat = [(el,None)]
    for d in el.iterdescendants():
        if not(d.tag == comment_tag):
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
        
## Bookkeeping functions
# When BaseElements are deleted, created, or moved, the caches need to be
# updated or invalidated. These functions do that while preserving the original
# base functionality

# Deletion
inkexdelete = inkex.BaseElement.delete
def delete_func(el):
    svg = el.croot
    for d in reversed(el.descendants2()):
        did = d.get_id()
        if svg is not None:
            try:
                svg.ids.remove(did)
            except (KeyError,AttributeError):
                pass
            svg.iddict.remove(d)
        d.croot = None
    if hasattr(svg, "_cd2"):
        svg.cdescendants2.delel(el)
    inkexdelete(el)
BaseElement.delete  = delete_func

# Insertion
BEinsert = inkex.BaseElement.insert 
def insert_func(g, index, el):
    oldroot = el.croot
    newroot = g.croot
    
    BEinsert(g,index, el)
    el.ccascaded_style = None
    el.cspecified_style = None
    el.ccomposed_transform = None
    
    # When the root is changing, removing from old dicts and add to new
    # Note that most new elements have their IDs assigned here or in append
    if not oldroot==newroot or el.get('id') is None:
        css = None
        if oldroot is not None:
            oldroot.iddict.remove(el)
            css = oldroot.cssdict.pop(el.get_id(),None)
        el.croot = newroot
        if newroot is not None:
            newroot.iddict.add(el) # generates an ID if needed
            if css is not None:
                newroot.cssdict[el.get_id()]=css
inkex.BaseElement.insert = insert_func

# Appending
BEappend = inkex.BaseElement.append 
def append_func(g, el):
    oldroot = el.croot
    newroot = g.croot
    
    BEappend(g, el)
    el.ccascaded_style = None
    el.cspecified_style = None
    el.ccomposed_transform = None
    
    # When the root is changing, removing from old dicts and add to new
    # Note that most new elements have their IDs assigned here or in insert
    if not oldroot==newroot or el.get('id') is None:
        css = None
        if oldroot is not None:
            oldroot.iddict.remove(el)
            css = oldroot.cssdict.pop(el.get_id(),None)
        el.croot = newroot
        if newroot is not None:
            newroot.iddict.add(el) # generates an ID if needed
            if css is not None:
                newroot.cssdict[el.get_id()]=css
inkex.BaseElement.append = append_func

# Duplication
clipmasktags = {inkex.addNS('mask','svg'), inkex.ClipPath.ctag}
def duplicate_func(el):
    svg = el.croot
    svg.iddict
    svg.cssdict
    # need to generate now to prevent problems in duplicate_fixed (el.addnext(elem) line, no idea why)

    eltail = el.tail;
    if eltail is not None:
        el.tail = None;
    d = el.copy()
    el.addnext(d)
    d.set_random_id();
    if eltail is not None:
        el.tail = eltail
    # Fix tail bug: https://gitlab.com/inkscape/extensions/-/issues/480
    
    d.croot = svg          # set now for speed
    el.croot.cssdict.dupe_entry(el.get_id(), d.get_id())
    svg.iddict.add(d)

    for k in descendants2(d)[1:]:
        if not k.tag == comment_tag:
            oldid = k.get_id()
            k.croot = svg  # set now for speed
            k.set_random_id()
            k.croot.cssdict.dupe_entry(oldid, k.get_id())
            svg.iddict.add(k)

    if d.tag in clipmasktags:
        # Clip duplications can cause weird issues if they are not appended to the end of Defs
        d.croot.cdefs.append(d)
    return d
BaseElement.duplicate = duplicate_func