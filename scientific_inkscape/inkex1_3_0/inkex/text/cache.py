# coding=utf-8

# Copyright (c) 2023 David Burghoff <burghoff@utexas.edu>
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

"""
A collection of functions that provide caching of certain Inkex properties.
Most provide the same functionality as the regular properties,
but with a 'c' in front of the name. For example,
  Style: cstyle, cspecified_style, ccascaded_style
  Transform: ctransform, ccomposed_transform
  Miscellaneous: croot, cdefs, ctag
Most are invalidated by setting to None (except ctransform, which is set to identity).
xpath calls are avoided at all costs.

Also gives SvgDocumentElements some dictionaries that are used to speed up
various lookups:
  svg.iddict: elements by their ID
  svg.cssdict: CSS styles by ID

Lastly, several core Inkex functions are overwritten with versions that
use the cache. For example, getElementById uses svg.iddict to avoid xpath
calls.
"""

import inkex
from inkex import Style
from inkex import BaseElement, SvgDocumentElement
from text.utils import shapetags, tags, ipx, list2, bbox
import lxml, re

EBget = lxml.etree.ElementBase.get
EBset = lxml.etree.ElementBase.set


# Version of get_unique_id that removes randomness by keeping a running count
from typing import Optional, List


# Function that references URLs, returning the referenced element
# Returns None if it does not exist or is invalid
# Accepts both elements and styles as inputs
def get_link_fcn(el, typestr, svg=None, llget=False):
    if llget:
        tv = EBget(el, typestr)
        # fine for 'clip-path' & 'mask'
    else:
        tv = el.get(typestr)
    if tv is not None:
        if svg is None:
            svg = el.croot  # need to specify svg for Styles but not BaseElements
            if svg is None:
                return None
        if typestr == "xlink:href":
            urlel = svg.getElementById(tv[1:])
        elif tv.startswith("url"):
            urlel = svg.getElementById(tv[5:-1])
        else:
            urlel = None
        return urlel
    return None


BE_set_id = BaseElement.set_id

# Fast empty Style initialization
if len(Style().__dict__) == 0:

    def empty_style():
        return Style.__new__(Style)
else:
    bstyle_dict = Style().__dict__

    def empty_style():
        ret = Style.__new__(Style)
        ret.__dict__ = bstyle_dict
        return ret


class BaseElementCache(BaseElement):
    get_link = get_link_fcn

    # Cached style attribute that invalidates the cached cascaded / specified
    # style whenever the style is changed. Always use this when setting styles.
    class CStyle(Style):
        # Delete key when value set to None
        def __init__(self, val, el):
            self.el = el
            self.init = True
            super().__init__(val)
            self.init = False

        def __setitem__(self, *args):
            # Allows for multiple inputs using
            # __setitem__(key1, value1, key2, value2, ...)
            if self.init:
                # OrderedDict sets items during initialization, use super()
                super().__setitem__(args[0], args[1])
            else:
                changedvalue = False
                for i in range(0, len(args), 2):
                    key = args[i]
                    value = args[i + 1]
                    if value is None:
                        if key in self:
                            del self[key]
                            changedvalue = True
                    else:
                        if key not in self or self[key] != value:
                            super().__setitem__(key, value)
                            changedvalue = True
                if changedvalue:
                    self.el.cstyle = self

    class CStyleDescriptor:
        def __get__(self, el, owner):
            if not hasattr(el, "_cstyle") and el is not None:
                el._cstyle = BaseElementCache.CStyle(EBget(el, "style"), el)
            return el._cstyle

        def __set__(self, el, value):
            if value:
                vstr = str(value)
                EBset(el, "style", vstr)
            else:
                if "style" in el.attrib:
                    del el.attrib["style"]

            if not isinstance(value, BaseElementCache.CStyle):
                if isinstance(value, Style):
                    # Cast to CStyle without reinitializing
                    value.__class__ = BaseElementCache.CStyle
                    value.el = el
                    value.init = False
                else:
                    value = BaseElementCache.CStyle(value, el)
            el._cstyle = value
            el.ccascaded_style = None
            el.cspecified_style = None

    cstyle = CStyleDescriptor()

    # Cached specified style property
    cstytags = shapetags | {SvgDocumentElement.ctag}

    def get_cspecified_style(self):
        if not (hasattr(self, "_cspecified_style")):
            parent = self.getparent()
            if parent is not None and parent.tag in BaseElementCache.cstytags:
                ret = parent.cspecified_style + self.ccascaded_style
            else:
                ret = self.ccascaded_style
            self._cspecified_style = ret
        return self._cspecified_style

    def set_cspecified_style(self, si):
        if si is None:
            try:
                delattr(self, "_cspecified_style")
                for k in list(self):
                    k.cspecified_style = None  # invalidate children
            except:
                pass

    cspecified_style = property(get_cspecified_style, set_cspecified_style)

    # Cached cascaded style property
    svgpres = {
        "alignment-baseline",
        "baseline-shift",
        "clip",
        "clip-path",
        "clip-rule",
        "color",
        "color-interpolation",
        "color-interpolation-filters",
        "color-profile",
        "color-rendering",
        "cursor",
        "direction",
        "display",
        "dominant-baseline",
        "enable-background",
        "fill",
        "fill-opacity",
        "fill-rule",
        "filter",
        "flood-color",
        "flood-opacity",
        "font-family",
        "font-size",
        "font-size-adjust",
        "font-stretch",
        "font-style",
        "font-variant",
        "font-weight",
        "glyph-orientation-horizontal",
        "glyph-orientation-vertical",
        "image-rendering",
        "kerning",
        "letter-spacing",
        "lighting-color",
        "marker-end",
        "marker-mid",
        "marker-start",
        "mask",
        "opacity",
        "overflow",
        "pointer-events",
        "shape-rendering",
        "stop-color",
        "stop-opacity",
        "stroke",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-opacity",
        "stroke-width",
        "text-anchor",
        "text-decoration",
        "text-rendering",
        "transform",
        "transform-origin",
        "unicode-bidi",
        "vector-effect",
        "visibility",
        "word-spacing",
        "writing-mode",
    }
    excludes = {"clip", "clip-path", "mask", "transform", "transform-origin"}
    style_atts = svgpres - excludes

    # raw dict update
    dict_update = Style.__bases__[0].update  # type: ignore

    def get_cascaded_style(self):
        # Object's style including any CSS
        if not (hasattr(self, "_ccascaded_style")):
            # Local style (in "style" attribute)
            locsty = self.cstyle
            # CSS style (from stylesheet)
            csssty = getattr(self.croot, "cssdict", dict()).get(self.get_id())
            # Attribute style (from attributes other than "style")
            attsty = empty_style()
            BaseElementCache.dict_update(
                attsty,
                (
                    {
                        a: EBget(self, a)
                        for a in self.attrib
                        if a in BaseElementCache.style_atts
                    }
                ),
            )

            if csssty is None:
                ret = attsty + locsty
            else:
                # Any style specified locally takes priority, followed by CSS,
                # followed by any attributes that the element has
                ret = attsty.add3(csssty, locsty)
            self._ccascaded_style = ret
        return self._ccascaded_style

    def set_ccascaded_style(self, si):
        if si is None:
            try:
                delattr(self, "_ccascaded_style")
            except:
                pass

    ccascaded_style = property(get_cascaded_style, set_ccascaded_style)

    # Cached composed_transform, which can be invalidated by changes to
    # transform of any ancestor.
    def get_ccomposed_transform(self):
        if not (hasattr(self, "_ccomposed_transform")):
            myp = self.getparent()
            if myp is None:
                self._ccomposed_transform = self.ctransform
            else:
                self._ccomposed_transform = myp.ccomposed_transform @ self.ctransform
        return self._ccomposed_transform

    def set_ccomposed_transform(self, si):
        if si is None and hasattr(self, "_ccomposed_transform"):
            delattr(self, "_ccomposed_transform")  # invalidate
            for k in list2(self):
                k.ccomposed_transform = None  # invalidate descendants

    ccomposed_transform = property(get_ccomposed_transform, set_ccomposed_transform)

    # Cached transform property
    # Note: Can be None
    def get_ctransform(self):
        if not (hasattr(self, "_ctransform")):
            self._ctransform = self.transform
        return self._ctransform

    def set_ctransform(self, newt):
        self.transform = newt
        # wrapped_setattr(self, 'transform', newt)
        self._ctransform = newt
        self.ccomposed_transform = None

    ctransform = property(get_ctransform, set_ctransform)

    # Cached get_path, modified to correctly calculate path for rectangles and ellipses
    # Caches Path of an object (set el.cpath to None to reset)
    rect_tag = inkex.Rectangle.ctag
    round_tags = tags((inkex.Circle, inkex.Ellipse))
    line_tag = inkex.Line.ctag
    path_tag = inkex.PathElement.ctag

    def get_path2(self):
        if not hasattr(self, "_cpath"):
            # mostly from inkex.elements._polygons
            if self.tag == BaseElementCache.path_tag:
                ret = inkex.Path(self.get("d"))
            elif self.tag == BaseElementCache.rect_tag:
                left = ipx(self.get("x", "0"))
                top = ipx(self.get("y", "0"))
                width = ipx(self.get("width", "0"))
                height = ipx(self.get("height", "0"))
                rx = ipx(self.get("rx", self.get("ry", "0")))
                ry = ipx(self.get("ry", self.get("rx", "0")))
                right = left + width
                bottom = top + height

                """Calculate the path as the box around the rect"""
                if rx or ry:
                    # pylint: disable=invalid-name
                    rx = min(rx if rx > 0 else ry, width / 2)
                    ry = min(ry if ry > 0 else rx, height / 2)
                    cpts = [left + rx, right - rx, top + ry, bottom - ry]
                    return inkex.Path(
                        f"M {cpts[0]},{top}"
                        f"L {cpts[1]},{top}    "
                        f"A {rx},{ry} 0 0 1 {right},{cpts[2]}"
                        f"L {right},{cpts[3]}  "
                        f"A {rx},{ry} 0 0 1 {cpts[1]},{bottom}"
                        f"L {cpts[0]},{bottom} "
                        f"A {rx},{ry} 0 0 1 {left},{cpts[3]}"
                        f"L {left},{cpts[2]}   "
                        f"A {rx},{ry} 0 0 1 {cpts[0]},{top} z"
                    )

                return inkex.Path(f"M {left},{top} h{width}v{height}h{-width} z")

            elif self.tag in BaseElementCache.round_tags:
                cx = ipx(self.get("cx", "0"))
                cy = ipx(self.get("cy", "0"))
                if isinstance(self, (inkex.Ellipse)):  # selflipse
                    rx = ipx(self.get("rx", "0"))
                    ry = ipx(self.get("ry", "0"))
                else:  # circle
                    rx = ipx(self.get("r", "0"))
                    ry = ipx(self.get("r", "0"))
                ret = inkex.Path(
                    (
                        "M {cx},{y} "
                        "a {rx},{ry} 0 1 0 {rx}, {ry} "
                        "a {rx},{ry} 0 0 0 -{rx}, -{ry} z"
                    ).format(cx=cx, y=cy - ry, rx=rx, ry=ry)
                )

            elif self.tag == BaseElementCache.line_tag:  # updated in v1.2
                x1 = ipx(self.get("x1", "0"))
                y1 = ipx(self.get("y1", "0"))
                x2 = ipx(self.get("x2", "0"))
                y2 = ipx(self.get("y2", "0"))
                ret = inkex.Path(f"M{x1},{y1} L{x2},{y2}")
            else:
                ret = self.get_path()
                if isinstance(ret, str):
                    ret = inkex.Path(ret)
            self._cpath = ret

        return self._cpath

    def set_cpath_fcn(self, sv):
        if sv is None and hasattr(self, "_cpath"):
            delattr(self, "_cpath")  # invalidate

    cpath = property(get_path2, set_cpath_fcn)
    cpath_support = (
        inkex.Rectangle,
        inkex.Ellipse,
        inkex.Circle,
        inkex.Polygon,
        inkex.Polyline,
        inkex.Line,
        inkex.PathElement,
    )

    otp_support = cpath_support
    otp_support_tags = tags(cpath_support)
    ptag = inkex.PathElement.ctag

    def object_to_path(self):
        """
        Converts specified elements to paths if supported. Adjusts the 'd' attribute and changes the element tag to a path.

        Parameters:
            self (Element): The element to convert to a path.

        Note:
            Only operates on elements within the `otp_support_tags` list.
        """
        if (
            self.tag in BaseElementCache.otp_support_tags
            and not self.tag == BaseElementCache.ptag
        ):
            self.set("d", str(self.cpath))  # do this first so cpath is correct
            self.tag = BaseElementCache.ptag

    # Cached root property
    svgtag = SvgDocumentElement.ctag

    def get_croot(self):
        try:
            return self._croot
        except AttributeError:
            if self.getparent() is not None:
                self._croot = self.getparent().croot
            elif self.tag == BaseElementCache.svgtag:
                self._croot = self
            else:
                self._croot = None
            return self._croot

    def set_croot(self, ri):
        self._croot = ri

    croot = property(get_croot, set_croot)

    # Version of set_random_id that uses cached root
    def set_random_id(
        self,
        prefix: Optional[str] = None,
        size: Optional[int] = None,
        backlinks: bool = False,
        blacklist: Optional[List[str]] = None,
    ):
        prefix = str(self) if prefix is None else prefix
        self.set_id(
            self.croot.get_unique_id(prefix, size=size, blacklist=blacklist),
            backlinks=backlinks,
        )

    # Version of get_id that uses the low-level get
    def get_id(self, as_url=0):
        if "id" not in self.attrib:
            self.set_random_id(self.TAG)
        eid = EBget(self, "id")
        if as_url > 0:
            eid = "#" + eid
            if as_url > 1:
                eid = f"url({eid})"
        return eid

    def set_id(self, new_id, backlinks=False):
        """Set the id and update backlinks to xlink and style urls if needed"""
        if self.croot is not None:
            self.croot.iddict[new_id] = self
        # old_id = self.get('id')
        BE_set_id(self, new_id, backlinks=backlinks)
        # Deleting the old value doesn't currently work properly (abandoned references?)
        # if old_id is not None and old_id in self.croot.iddict:
        #     del self.croot.iddict[old_id]

    # A version of descendants that also returns a list of elements whose tails
    # precede each element. (This is helpful for parsing text.)
    comment_tag = lxml.etree.Comment

    def descendants2(self, return_tails=False):
        if not return_tails:
            return [self] + [
                d
                for d in self.iterdescendants()
                if d.tag != BaseElementCache.comment_tag
            ]
        else:
            descendants = [self]
            precedingtails = [[]]
            endsat = [(self, None)]
            for d in self.iterdescendants():
                if not (d.tag == BaseElementCache.comment_tag):
                    precedingtails.append([])
                    while endsat[-1][1] == d:
                        precedingtails[-1].append(endsat.pop()[0])
                    nsib = d.getnext()
                    if nsib is None:
                        endsat.append((d, endsat[-1][1]))
                    else:
                        endsat.append((d, nsib))
                    descendants.append(d)

            precedingtails.append([])
            while len(endsat) > 0:
                precedingtails[-1].append(endsat.pop()[0])
            return descendants, precedingtails

    # Version of ancestors that can stop before/after encountering an element
    def ancestors2(self, includeme=False, stopbefore=None, stopafter=None):
        anc = []
        cel = self if includeme else self.getparent()
        while cel is not None and cel != stopbefore:
            anc.append(cel)
            if cel == stopafter:
                break
            cel = cel.getparent()
        return anc

    ## Bookkeeping functions
    # When BaseElements are deleted, created, or moved, the caches need to be
    # updated or invalidated. These functions do that while preserving the original
    # base functionality

    # Deletion
    BE_delete = inkex.BaseElement.delete

    def delete(self, deleteup=False):
        svg = self.croot
        for d in reversed(self.descendants2()):
            did = d.get_id()
            if svg is not None:
                try:
                    svg.ids.remove(did)
                except (KeyError, AttributeError):
                    pass
                svg.iddict.remove(d)
            d.croot = None
        if hasattr(svg, "_cd2"):
            svg.cdescendants2.delel(self)

        if deleteup:
            # If set, remove empty ancestor groups
            myp = self.getparent()
            BaseElementCache.BE_delete(self)
            if myp is not None and not len(myp):
                BaseElementCache.delete(myp, True)
        else:
            BaseElementCache.BE_delete(self)

    # Insertion
    # BE_insert = inkex.BaseElement.insert
    BE_insert = lxml.etree.ElementBase.insert

    def insert(g, index, el):
        oldroot = el.croot
        newroot = g.croot

        BaseElementCache.BE_insert(g, index, el)
        el.ccascaded_style = None
        el.cspecified_style = None
        el.ccomposed_transform = None

        if EBget(el, "id") is None:
            # Make sure all elements have an ID (most assigned here)
            el.croot = newroot
            if newroot is not None:
                newroot.iddict.add(el)  # generates an ID if needed
            for k in list2(el):
                el.append(k)  # update children
        elif oldroot != newroot:
            # When the root is changing, remove from old dicts and add to new
            css = None
            if oldroot is not None:
                oldroot.iddict.remove(el)
                css = oldroot.cssdict.pop(el.get_id(), None)
            el.croot = newroot
            if newroot is not None:
                newroot.iddict.add(el)  # generates an ID if needed
                if css is not None:
                    newroot.cssdict[el.get_id()] = css
            for k in list2(el):
                el.append(k)  # update children

    # Appending
    # BE_append = inkex.BaseElement.append
    BE_append = lxml.etree.ElementBase.append

    def append(g, el):
        oldroot = el.croot
        newroot = g.croot

        BaseElementCache.BE_append(g, el)
        el.ccascaded_style = None
        el.cspecified_style = None
        el.ccomposed_transform = None

        if EBget(el, "id") is None:
            # Make sure all elements have an ID (most assigned here)
            el.croot = newroot
            if newroot is not None:
                newroot.iddict.add(el)  # generates an ID if needed
            for k in list2(el):
                el.append(k)  # update children
        elif oldroot != newroot:
            # When the root is changing, remove from old dicts and add to new
            css = None
            if oldroot is not None:
                oldroot.iddict.remove(el)
                css = oldroot.cssdict.pop(el.get_id(), None)
            el.croot = newroot
            if newroot is not None:
                newroot.iddict.add(el)  # generates an ID if needed
                if css is not None:
                    newroot.cssdict[el.get_id()] = css
            for k in list2(el):
                el.append(k)  # update children

    # addnext
    # BE_addnext = inkex.BaseElement.addnext
    BE_addnext = lxml.etree.ElementBase.addnext

    def addnext(g, el):
        oldroot = el.croot
        newroot = g.croot

        BaseElementCache.BE_addnext(g, el)
        el.ccascaded_style = None
        el.cspecified_style = None
        el.ccomposed_transform = None

        if EBget(el, "id") is None:
            # Make sure all elements have an ID (most assigned here)
            el.croot = newroot
            if newroot is not None:
                newroot.iddict.add(el)  # generates an ID if needed
            for k in list2(el):
                el.append(k)  # update children
        elif oldroot != newroot:
            # When the root is changing, remove from old dicts and add to new
            css = None
            if oldroot is not None:
                oldroot.iddict.remove(el)
                css = oldroot.cssdict.pop(el.get_id(), None)
            el.croot = newroot
            if newroot is not None:
                newroot.iddict.add(el)  # generates an ID if needed
                if css is not None:
                    newroot.cssdict[el.get_id()] = css
            for k in list2(el):
                el.append(k)  # update children

    # Duplication
    clipmasktags = {inkex.addNS("mask", "svg"), inkex.ClipPath.ctag}

    def duplicate(self):
        # type: (BaseElement) -> BaseElement
        # svg = self.croot
        # svg.iddict    # disabled 2024-04-29
        # svg.cssdict   # disabled 2024-04-29
        # need to generate now to prevent problems in duplicate_fixed (self.addnext(elem) line, no idea why)

        eltail = self.tail
        if eltail is not None:
            self.tail = None
        d = self.copy()

        # After copying, duplicates have the original ID. Remove prior to insertion
        origids = dict()
        for dd in d.descendants2():
            origids[dd] = dd.pop("id", None)
            dd.croot = self.croot  # set now for speed

        self.addnext(d)
        if eltail is not None:
            self.tail = eltail
        # Fix tail bug: https://gitlab.com/inkscape/extensions/-/issues/480

        css = self.croot.cssdict
        newids = {
            EBget(k, "id"): css.get(origids[k])
            for k in d.descendants2()
            if origids[k] in css
        }
        d.croot.cssdict.update(newids)

        if d.tag in BaseElementCache.clipmasktags:
            # Clip duplications can cause weird issues if they are not appended to the end of Defs
            d.croot.cdefs.append(d)
        return d

    # Cached bounding box that requires no command call
    # Uses extents for text
    # dotransform: whether or not we want the element's bbox or its true transformed bbox
    # includestroke: whether or not to add the stroke to the calculation
    # roughpath: use control points for a path's bbox, which is faster and an upper bound for the true bbox
    ttags = tags((inkex.TextElement, inkex.FlowRoot))
    line_tag = inkex.Line.ctag
    cpath_support_tags = tags(cpath_support)
    mask_tag = inkex.addNS("mask", "svg")
    grouplike_tags = tags(
        (
            inkex.SvgDocumentElement,
            inkex.Group,
            inkex.Layer,
            inkex.ClipPath,
            inkex.Symbol,
        )
    )
    grouplike_tags.add(mask_tag)

    def bounding_box2(
        self, dotransform=True, includestroke=True, roughpath=False, parsed=False
    ):
        if not (hasattr(self, "_cbbox")):
            self._cbbox = dict()
        if (dotransform, includestroke, roughpath, parsed) not in self._cbbox:
            try:
                ret = bbox(None)
                if self.tag in BaseElementCache.ttags:
                    ret = self.parsed_text.get_full_extent(parsed=parsed)
                elif self.tag in BaseElementCache.cpath_support_tags:
                    pth = self.cpath
                    if len(pth) > 0:
                        sw = ipx(self.cspecified_style.get("stroke-width", "0px"))
                        if self.cspecified_style.get("stroke") is None or not (
                            includestroke
                        ):
                            sw = 0

                        if self.tag == BaseElementCache.line_tag:
                            xs = [ipx(self.get("x1", "0")), ipx(self.get("x2", "0"))]
                            ys = [ipx(self.get("y1", "0")), ipx(self.get("y2", "0"))]
                            ret = bbox(
                                [
                                    min(xs) - sw / 2,
                                    min(ys) - sw / 2,
                                    max(xs) - min(xs) + sw,
                                    max(ys) - min(ys) + sw,
                                ]
                            )
                        elif not roughpath:
                            bb = pth.bounding_box()
                            ret = bbox(
                                [
                                    bb.left - sw / 2,
                                    bb.top - sw / 2,
                                    bb.width + sw,
                                    bb.height + sw,
                                ]
                            )
                        else:
                            anyarc = any([s.letter in ["a", "A"] for s in pth])
                            pth = (
                                inkex.Path(inkex.CubicSuperPath(pth)) if anyarc else pth
                            )
                            pts = list(pth.control_points)
                            xs = [p.x for p in pts]
                            ys = [p.y for p in pts]
                            ret = bbox(
                                [
                                    min(xs) - sw / 2,
                                    min(ys) - sw / 2,
                                    max(xs) - min(xs) + sw,
                                    max(ys) - min(ys) + sw,
                                ]
                            )

                elif self.tag in BaseElementCache.grouplike_tags:
                    for d in list2(self):
                        dbb = BaseElementCache.bounding_box2(
                            d,
                            dotransform=False,
                            includestroke=includestroke,
                            roughpath=roughpath,
                            parsed=parsed,
                        )
                        if not (dbb.isnull):
                            ret = ret.union(dbb.transform(d.ctransform))
                elif isinstance(self, (inkex.Image)):
                    ret = bbox(
                        [ipx(self.get(v, "0")) for v in ["x", "y", "width", "height"]]
                    )
                elif isinstance(self, (inkex.Use,)):
                    lel = self.get_link("xlink:href")
                    if lel is not None:
                        ret = BaseElementCache.bounding_box2(
                            lel, dotransform=False, roughpath=roughpath, parsed=parsed
                        )

                        # clones have the transform of the link, followed by any xy transform
                        xyt = inkex.Transform(
                            "translate({0},{1})".format(
                                ipx(self.get("x", "0")), ipx(self.get("y", "0"))
                            )
                        )
                        ret = ret.transform(xyt @ lel.ctransform)

                if not (ret.isnull):
                    for cm in ["clip-path", "mask"]:
                        clip = self.get_link(cm, llget=True)
                        if clip is not None:
                            cbb = BaseElementCache.bounding_box2(
                                clip,
                                dotransform=False,
                                includestroke=False,
                                roughpath=roughpath,
                                parsed=parsed,
                            )
                            if not (cbb.isnull):
                                ret = ret.intersection(cbb)
                            else:
                                ret = bbox(None)

                    if dotransform:
                        if not (ret.isnull):
                            ret = ret.transform(self.ccomposed_transform)
            except:
                # For some reason errors are occurring silently
                import traceback

                inkex.utils.debug(traceback.format_exc())
            self._cbbox[(dotransform, includestroke, roughpath, parsed)] = ret
        return self._cbbox[(dotransform, includestroke, roughpath, parsed)]

    def set_cbbox(self, val):
        if val is None and hasattr(self, "_cbbox"):
            delattr(self, "_cbbox")

    cbbox = property(bounding_box2, set_cbbox)

    bb2_support = (
        inkex.TextElement,
        inkex.FlowRoot,
        inkex.Image,
        inkex.Use,
        inkex.SvgDocumentElement,
        inkex.Group,
        inkex.Layer,
    ) + cpath_support
    bb2_support_tags = tags(bb2_support)

    # Add parsed_text property to text, which is used to get the properties of text
    def get_parsed_text(self):
        from inkex.text.parser import ParsedText  # import only if needed

        if not (hasattr(self, "_parsed_text")):
            self._parsed_text = ParsedText(self, self.croot.char_table)
        return self._parsed_text

    def set_parsed_text(self, sv):
        if hasattr(self, "_parsed_text") and sv is None:
            delattr(self, "_parsed_text")

    parsed_text = property(get_parsed_text, set_parsed_text)


class SvgDocumentElementCache(SvgDocumentElement):
    # Cached def directly under root
    def cdefs_func(self):
        if not (hasattr(self, "_cdefs")):
            for k in list(self):
                if isinstance(k, (inkex.Defs)):
                    self._cdefs = k
                    return self._cdefs
            d = inkex.Defs()
            self.insert(0, d)
            self._cdefs = d
        return self._cdefs

    cdefs = property(cdefs_func)

    # Cached style element directly under root
    styletag = inkex.addNS("style", "svg")

    def crootsty_func(self):
        if not hasattr(self, "_crootsty"):
            rootstys = [
                sty for sty in list(self) if sty.tag == SvgDocumentElementCache.styletag
            ]
            if len(rootstys) == 0:
                self._crootsty = inkex.StyleElement()
                self.insert(0, self._crootsty)
            else:
                self._crootsty = rootstys[0]
        return self._crootsty

    crootsty = property(crootsty_func)

    # Version of get_ids that uses iddict
    def get_ids(self):
        """Returns a set of unique document ids"""
        return set(self.iddict.keys())

    def get_unique_id(
        self,
        prefix: str,
        size: Optional[int] = None,
        blacklist: Optional[List[str]] = None,
    ):
        new_id = None
        cnt = self.iddict.prefixcounter.get(prefix, 0)
        if blacklist is None:
            while new_id is None or new_id in self.iddict:
                new_id = prefix + str(cnt)
                cnt += 1
        else:
            while new_id is None or new_id in self.iddict or new_id in blacklist:
                new_id = prefix + str(cnt)
                cnt += 1
        self.iddict.prefixcounter[prefix] = cnt
        return new_id

    # Repeated getElementById lookups can be slow, so instead create a cached iddict property.
    # When an element is created that may be needed later, it must be added using self.iddict.add.
    urlpat = re.compile(r"^url\(#(.*)\)$|^#")

    def getElementById(self, eid: str, elm="*", literal=False):
        if eid is not None and not literal:
            eid = SvgDocumentElementCache.urlpat.sub(r"\1", eid.strip())
        return self.iddict.get(eid)

    # Add iddict, which keeps track of the IDs in a document
    class iddict_cls(dict):
        def __init__(self, svg):
            self.svg = svg
            self.prefixcounter = dict()
            toassign = []
            for el in svg.descendants2():
                if "id" in el.attrib:
                    self[EBget(el, "id")] = el
                else:
                    toassign.append(el)
                el.croot = svg  # do now to speed up later
            for el in toassign:
                # Reduced version of get_unique_id_fcn
                # Cannot call it since it relies on iddict
                prefix = el.TAG
                new_id = None
                cnt = self.prefixcounter.get(prefix, 0)
                while new_id is None or new_id in self:
                    new_id = prefix + str(cnt)
                    cnt += 1
                self.prefixcounter[prefix] = cnt
                # Reduced version of set_id
                self[new_id] = el
                BE_set_id(el, new_id)

        def add(self, el):
            elid = el.get_id()  # fine since el should have a croot to get called here
            if elid in self and not self[elid] == el:
                # Make a new id when there's a conflict
                el.set_random_id(el.TAG)
                elid = el.get_id()
            self[elid] = el

        @property
        def ds(self):  # all svg descendants, not necessarily in order
            return list(self.values())

        def remove(self, el):
            elid = el.get_id()
            if elid in self:
                del self[elid]

    def get_iddict(self):
        if not (hasattr(self, "_iddict")):
            self._iddict = SvgDocumentElementCache.iddict_cls(self)
        return self._iddict

    iddict = property(get_iddict)

    # A dict that keeps track of the CSS style for each element
    estyle = Style()  # keep separate in case Style was overridden

    # Check if v1.4 or later
    hasmatches = hasattr(inkex.styles.ConditionalStyle, "matches")

    class cssdict_cls(dict):
        def __init__(self, svg):
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
                    rules = tuple(str(r) for r in style.rules)
                    # inkex.utils.debug(rules)
                    if rules == ("*",):
                        hasall = True
                    elif all([c1.match(r) for r in rules]):
                        # all rules are classes
                        simpleclasses[rules] = [c1.sub(r"\1", r) for r in rules]
                    elif all([c2.match(r) for r in rules]):  # all rules are ids
                        simpleids[rules] = [c2.sub(r"\1", r) for r in rules]

            # Now, we make a dictionary of rules / xpaths we can do easily
            knownrules = dict()
            if hasall or len(simpleclasses) > 0:
                ds = svg.iddict.ds
                if hasall:
                    knownrules[("*",)] = ds
                cs = [EBget(d, "class") for d in ds]
                c2 = [(ii, c) for (ii, c) in enumerate(cs) if c is not None]
                cmatches = dict()
                for ii, clsval in c2:
                    for c in clsval.split(" "):
                        cmatches[c] = cmatches.get(c, []) + [ds[ii]]
                kxp2 = {
                    rules: list(
                        dict.fromkeys(
                            [d for c in clslist if c in cmatches for d in cmatches[c]]
                        )
                    )
                    for rules, clslist in simpleclasses.items()
                }
                knownrules.update(kxp2)

            for rules in simpleids:
                knownrules[rules] = []
                for sid in simpleids[rules]:
                    idel = svg.getElementById(sid)
                    if idel is not None:
                        knownrules[rules].append(idel)

            # Now run any necessary xpaths and get the element styles
            super().__init__()
            for sheet in svg.croot.stylesheets:
                for style in sheet:
                    try:
                        # els = svg.xpath(style.to_xpath())  # original code
                        rules = tuple(str(r) for r in style.rules)
                        stylev = Style(style)
                        if rules in knownrules:
                            els = knownrules[rules]
                        else:
                            if SvgDocumentElementCache.hasmatches:
                                els = style.all_matches(svg)
                            else:
                                els = svg.xpath(style.to_xpath())
                                if type(els) == float:
                                    els = []  # v1.0 returns nan when empty

                        if len(stylev) > 0:
                            idvs = [
                                EBget(elem, "id", None)
                                for elem in els
                                if "id" in elem.attrib
                            ]
                            newstys = {
                                elid: stylev
                                if elid not in self
                                else self[elid] + stylev
                                for elid in idvs
                            }
                            # Technically we should copy stylev, but as long as styles in cssdict are only used
                            # in get_cascaded_style, this is fine since that function adds (creating copies)
                            self.update(newstys)
                    except (lxml.etree.XPathEvalError,):
                        pass

        def dupe_entry(self, oldid, newid):
            csssty = self.get(oldid)
            if csssty is not None:
                self[newid] = csssty

    def get_cssdict(self):
        try:
            return self._cssdict
        except:
            self._cssdict = SvgDocumentElementCache.cssdict_cls(self)
            return self._cssdict

    cssdict = property(get_cssdict)

    # Cached document size function
    def document_size(self):
        if not (hasattr(self, "_cdocsize")):
            rvb = self.get_viewbox()
            wstr = self.get("width")
            hstr = self.get("height")

            if rvb == [0, 0, 0, 0]:
                vb = [0, 0, ipx(wstr), ipx(hstr)]
            else:
                vb = [float(v) for v in rvb]  # just in case

            # Get document width and height in pixels
            wn, wu = inkex.units.parse_unit(wstr) if wstr is not None else (vb[2], "px")
            hn, hu = inkex.units.parse_unit(hstr) if hstr is not None else (vb[3], "px")

            def parse_preserve_aspect_ratio(pAR):
                align, meetOrSlice = "xMidYMid", "meet"  # defaults
                valigns = [
                    "xMinYMin",
                    "xMidYMin",
                    "xMaxYMin",
                    "xMinYMid",
                    "xMidYMid",
                    "xMaxYMid",
                    "xMinYMax",
                    "xMidYMax",
                    "xMaxYMax",
                    "none",
                ]
                vmoss = ["meet", "slice"]
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

            align, meetOrSlice = parse_preserve_aspect_ratio(
                self.get("preserveAspectRatio")
            )

            xf = (
                inkex.units.convert_unit(str(wn) + " " + wu, "px") / vb[2]
                if wu != "%"
                else wn / 100
            )  # width  of uu in px pre-stretch
            yf = (
                inkex.units.convert_unit(str(hn) + " " + hu, "px") / vb[3]
                if hu != "%"
                else hn / 100
            )  # height of uu in px pre-stretch
            if align != "none":
                f = min(xf, yf) if meetOrSlice == "meet" else max(xf, yf)
                xmf = {"xMin": 0, "xMid": 0.5, "xMax": 1}[align[0:4]]
                ymf = {"YMin": 0, "YMid": 0.5, "YMax": 1}[align[4:]]
                vb[0], vb[2] = (
                    vb[0] + vb[2] * (1 - xf / f) * xmf,
                    vb[2] / f * (xf if wu != "%" else 1),
                )
                vb[1], vb[3] = (
                    vb[1] + vb[3] * (1 - yf / f) * ymf,
                    vb[3] / f * (yf if hu != "%" else 1),
                )
                if wu == "%":
                    wn, wu = vb[2] * f, "px"
                if hu == "%":
                    hn, hu = vb[3] * f, "px"
            else:
                if wu == "%":
                    wn, wu, vb[2] = vb[2], "px", vb[2] / xf
                if hu == "%":
                    hn, hu, vb[3] = vb[3], "px", vb[3] / yf

            wpx = inkex.units.convert_unit(
                str(wn) + " " + wu, "px"
            )  # document width  in px
            hpx = inkex.units.convert_unit(
                str(hn) + " " + hu, "px"
            )  # document height in px
            uuw = wpx / vb[2]  # uu width  in px (px/uu)
            uuh = hpx / vb[3]  # uu height in px (px/uu)
            uupx = uuw if abs(uuw - uuh) < 0.001 else None  # uu size  in px  (px/uu)
            # should match Scale in Document Properties

            # Get Pages
            nvs = [el for el in list(self) if isinstance(el, inkex.NamedView)]
            pgs = [
                el
                for nv in nvs
                for el in list(nv)
                if el.tag == inkex.addNS("page", "inkscape")
            ]
            for pg in pgs:
                pg.bbuu = [
                    ipx(pg.get("x")),
                    ipx(pg.get("y")),
                    ipx(pg.get("width")),
                    ipx(pg.get("height")),
                ]
                pg.bbpx = [
                    pg.bbuu[0] * xf,
                    pg.bbuu[1] * yf,
                    pg.bbuu[2] * xf,
                    pg.bbuu[3] * yf,
                ]

            class DocSize:
                def __init__(
                    self,
                    rawvb,
                    effvb,
                    uuw,
                    uuh,
                    uupx,
                    wunit,
                    hunit,
                    wpx,
                    hpx,
                    xf,
                    yf,
                    pgs,
                ):
                    self.rawvb = rvb
                    self.effvb = effvb
                    self.uuw = uuw
                    self.uuh = uuh
                    self.uupx = uupx
                    self.wunit = wunit
                    self.hunit = hunit
                    self.wpx = wpx
                    self.hpx = hpx
                    self.rawxf = xf
                    self.rawyf = yf
                    self.pgs = pgs
                    try:
                        inkex.Page
                        self.inkscapehaspgs = True
                    except:
                        self.inkscapehaspgs = False

                def uutopx(
                    self, v
                ):  # Converts a bounding box specified in uu to pixels
                    vo = [
                        (v[0] - self.effvb[0]) * self.uuw,
                        (v[1] - self.effvb[1]) * self.uuh,
                        v[2] * self.uuw,
                        v[3] * self.uuh,
                    ]
                    return vo

                def pxtouu(
                    self, v
                ):  # Converts a bounding box specified in pixels to uu
                    vo = [
                        v[0] / self.uuw + self.effvb[0],
                        v[1] / self.uuh + self.effvb[1],
                        v[2] / self.uuw,
                        v[3] / self.uuh,
                    ]
                    return vo

                def unittouu(self, x):
                    # Converts any unit into uu
                    return (
                        inkex.units.convert_unit(x, "px") / self.uupx
                        if self.uupx is not None
                        else None
                    )

                def uutopxpgs(self, v):  # Version that applies to Pages
                    return [
                        v[0] * self.rawxf,
                        v[1] * self.rawyf,
                        v[2] * self.rawxf,
                        v[3] * self.rawyf,
                    ]

                def pxtouupgs(self, v):  # Version that applies to Pages
                    return [
                        v[0] / self.rawxf,
                        v[1] / self.rawyf,
                        v[2] / self.rawxf,
                        v[3] / self.rawyf,
                    ]

            self._cdocsize = DocSize(
                rvb, vb, uuw, uuh, uupx, wu, hu, wpx, hpx, xf, yf, pgs
            )
        return self._cdocsize

    def set_cdocsize(self, si):
        if si is None and hasattr(self, "_cdocsize"):  # invalidate
            delattr(self, "_cdocsize")

    cdocsize = property(document_size, set_cdocsize)

    def set_viewbox(self, newvb):
        # self.set_viewbox(vb)
        uuw, uuh, wunit, hunit = (
            self.cdocsize.uuw,
            self.cdocsize.uuh,
            self.cdocsize.wunit,
            self.cdocsize.hunit,
        )
        self.set(
            "width",
            str(inkex.units.convert_unit(str(newvb[2] * uuw) + "px", wunit)) + wunit,
        )
        self.set(
            "height",
            str(inkex.units.convert_unit(str(newvb[3] * uuh) + "px", hunit)) + hunit,
        )
        self.set("viewBox", " ".join([str(v) for v in newvb]))
        self.cdocsize = None

    def standardize_viewbox(self):
        # Converts viewbox to pixels, removing any non-uniform scaling appropriately
        pgbbs = [pg.bbpx for pg in self.cdocsize.pgs]
        self.set("viewBox", " ".join([str(v) for v in self.cdocsize.effvb]))
        self.set("width", str(self.cdocsize.wpx))
        self.set("height", str(self.cdocsize.hpx))

        # Update Pages appropriately
        self.cdocsize = None
        for ii, pg in enumerate(self.cdocsize.pgs):
            newbbuu = self.cdocsize.pxtouupgs(pgbbs[ii])
            pg.set("x", str(newbbuu[0]))
            pg.set("y", str(newbbuu[1]))
            pg.set("width", str(newbbuu[2]))
            pg.set("height", str(newbbuu[3]))

    # Add char_table property to SVGs, which are used to collect all of the
    # properties of fonts in the document. Alternatively, calling make_char_table
    # on a subset of elements will cause only those elements to be included.

    def make_char_table(self, els=None):
        # Can be called with els argument to examine list of elements only
        # (otherwise use entire SVG)
        ttags = tags((inkex.TextElement, inkex.FlowRoot))
        if els is None:
            tels = [d for d in self.iddict.ds if d.tag in ttags]
        else:
            tels = [d for d in els if d.tag in ttags]
        if not (hasattr(self, "_char_table")) or any(
            [t not in self._char_table.els for t in tels]
        ):
            from inkex.text.parser import Character_Table  # import if needed

            self._char_table = Character_Table(tels)

    def get_char_table(self):
        if not (hasattr(self, "_char_table")):
            self.make_char_table()
        return self._char_table

    def set_char_table(self, sv):
        if sv is None and hasattr(self, "_char_table"):
            delattr(self, "_char_table")

    char_table = property(get_char_table, set_char_table)


class StyleCache(Style):
    get_link = get_link_fcn

    def __hash__(self):
        return hash(tuple(self.items()))  # type: ignore

    # Adds three styles
    def add3_fcn(x, y, z):
        return x + y + z

    add3 = add3_fcn if not hasattr(Style, "add3") else Style.add3
