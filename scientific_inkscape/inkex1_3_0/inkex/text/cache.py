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

import re
from typing import Optional, List
import inkex
from inkex import Style
from inkex import BaseElement, SvgDocumentElement
from text.utils import shapetags, tags, ipx, list2, default_style_atts  # pylint: disable=import-error
import lxml

EBget = lxml.etree.ElementBase.get
EBset = lxml.etree.ElementBase.set
BE_set_id = BaseElement.set_id

# Fast empty Style initialization
if len(Style().__dict__) == 0:

    def empty_style():
        """Instantiates an empty Style object."""
        return Style.__new__(Style)
else:
    bstyle_dict = Style().__dict__

    def empty_style():
        """Instantiates an empty Style object."""
        ret = Style.__new__(Style)
        ret.__dict__ = bstyle_dict
        return ret


xlinkhref = inkex.addNS("href", "xlink")
linkmap = {"clip-path": "clips", "mask": "masks", xlinkhref: "linked_by"}
patmap = {
    "clip-path": re.compile(r"url\(#([^)]+)\)"),
    "mask": re.compile(r"url\(#([^)]+)\)"),
    xlinkhref: re.compile(r"^#([A-Za-z_][\w\-]*)$"),
}
xmlspace = inkex.addNS("space", "xml")


# pylint:disable=attribute-defined-outside-init
hrefs = {"xlink:href","href"}
class BaseElementCache(BaseElement):
    """Adds caching of style and transformation properties of base elements."""

    def get_link(self, typestr, svg=None, llget=False):
        """
        Function that references URLs, returning the referenced element
        Returns None if it does not exist or is invalid
        Accepts both elements and styles as inputs
        """
        if llget:
            urlv = EBget(self, typestr)
            # fine for 'clip-path' & 'mask'
        else:
            urlv = self.get(typestr)
        if urlv is not None:
            if svg is None:
                svg = self.croot  # need to specify svg for Styles but not BaseElements
                if svg is None:
                    return None
            if typestr in hrefs:
                urlel = svg.getElementById(urlv[1:])
            elif urlv.startswith("url"):
                urlel = svg.getElementById(urlv[5:-1])
            else:
                urlel = None
            return urlel
        return None

    def set_link(self, att, val):
        """Sets a linky attribute (currently clip-path, mask, xlink:href)
        while updating the iddicts"""
        if att == "xlink:href":
            att = xlinkhref

        if self.croot is not None:
            self.croot.iddict.remove_from_linkdict(self, att)
        if val is None:
            self.attrib.pop(att, None)  # pylint: disable=no-member
        else:
            EBset(self, att, val)
            if self.croot is not None:
                self.croot.iddict.add_to_linkdict(self, att)

    class CStyle(Style):
        """
        Cached style attribute that invalidates the cached cascaded / specified
        style whenever the style is changed. Always use this when setting styles.
        """

        # Delete key when value set to None
        def __init__(self, val, elem):
            self.elem = elem
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
                    self.elem.cstyle = self

    class CStyleDescriptor:
        """Descriptor for caching and managing style changes."""

        def __get__(self, elem, owner):
            if not hasattr(elem, "_cstyle") and elem is not None:
                elem._cstyle = BaseElementCache.CStyle(EBget(elem, "style"), elem)
            return elem._cstyle

        def __set__(self, elem, value):
            if value:
                EBset(elem, "style", str(value))
            else:
                elem.attrib.pop("style", None)

            try:
                elem._cstyle = BaseElementCache.CStyle(value.copy(), elem)
            except AttributeError: # strings
                elem._cstyle = BaseElementCache.CStyle(value, elem)
            elem.ccascaded_style = None
            elem.cspecified_style = None

    cstyle = CStyleDescriptor()

    # Cached specified style property
    cstytags = shapetags | {SvgDocumentElement.ctag}

    def get_cspecified_style(self):
        """Returns the cached specified style, calculating it if not cached."""
        if not (hasattr(self, "_cspecified_style")):
            parent = self.getparent()
            if parent is not None and parent.tag in BaseElementCache.cstytags:
                ret = parent.cspecified_style + self.ccascaded_style
            else:
                ret = self.ccascaded_style
            if "font" in ret:
                ret = ret + BaseElementCache.font_shorthand(ret["font"])
                ret.pop('font',None) # once applied, don't override font atts on children
            self._cspecified_style = ret
        return self._cspecified_style

    def set_cspecified_style(self, svi):
        """Invalidates the cached specified style."""
        if svi is None:
            if hasattr(self, "_cspecified_style"):
                for d in self.iter('*'):
                    d.__dict__.pop("_cspecified_style", None)
        else:
            # Set the specified style by setting the local style
            # Change local style only as needed
            ssty = self.cspecified_style
            for att in svi:
                if svi[att] != ssty.get(att):
                    self.cstyle[att] = svi[att]     
            for att in self.cstyle:
                if att not in svi:
                    del self.cstyle[att]
            
            # If there are still attributes in the specified style not in
            # the one we just applied, we are inheriting something we don't
            # want and need to counter using the default
            for att in self.cspecified_style:
                if att not in svi:
                    self.cstyle[att] = default_style_atts.get(att)

            # self.cstyle.update({k: default_style_atts.get(k) for k in self.cspecified_style if k not in svi})

    cspecified_style = property(get_cspecified_style, set_cspecified_style)

    shorthand_font_pattern = re.compile(
        r"^(?:(italic|oblique|normal)\s+)?"  # font-style
        r"(?:(small-caps)\s+)?"  # font-variant
        r"(?:(bold|bolder|lighter|\d{3})\s+)?"  # font-weight
        r"(?:(ultra-condensed|extra-condensed|condensed|semi-condensed|normal|semi-expanded|expanded|extra-expanded|ultra-expanded)\s+)?"  # font-stretch
        r"([0-9]+(?:\.[0-9]+)?(?:px|pt|em|rem|%)?)"  # font-size (with optional decimal)
        r"(?:/([0-9]+(?:\.[0-9]+)?(?:px|pt|em|rem|%)?))?"  # optional line-height
        r"\s+"  # one or more spaces
        r"(.+)$"  # the rest is font-family
    )

    @staticmethod
    def font_shorthand(fontstr):
        """Parses a font shorthand into relevant properties"""
        match = BaseElementCache.shorthand_font_pattern.match(fontstr)
        if match:
            (
                font_style,
                font_variant,
                font_weight,
                font_stretch,
                font_size,
                line_height,
                font_family,
            ) = match.groups()
            font_data = {
                "font-style": font_style,
                "font-variant": font_variant,
                "font-weight": font_weight,
                "font-stretch": font_stretch,
                "font-size": font_size,
                # "line-height": line_height, # Inkscape doesn't recognize this
                "font-family": font_family.strip() if font_family else None,
            }
            ret = {k: v for k, v in font_data.items() if v is not None}
        else:
            ret = dict()  # Invalid or unsupported font string
        return ret

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
        """Returns the cached cascaded (CSS) style, calculating it if not cached."""
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

    def set_ccascaded_style(self, svi):
        """Invalidates the cached cascaded style."""
        if svi is None:
            self.__dict__.pop("_ccascaded_style", None)

    ccascaded_style = property(get_cascaded_style, set_ccascaded_style)

    def get_ccomposed_transform(self):
        """
        Cached composed_transform, which can be invalidated by changes to
        transform of any ancestor.
        """
        if not (hasattr(self, "_ccomposed_transform")):
            myp = self.getparent()
            if myp is None:
                self._ccomposed_transform = self.ctransform
            else:
                self._ccomposed_transform = myp.ccomposed_transform @ self.ctransform
        return self._ccomposed_transform

    def set_ccomposed_transform(self, svi):
        """Invalidates the cached composed transform."""
        if svi is None and hasattr(self, "_ccomposed_transform"):
            delattr(self, "_ccomposed_transform")  # invalidate
            for k in list2(self):
                k.ccomposed_transform = None  # invalidate descendants

    ccomposed_transform = property(get_ccomposed_transform, set_ccomposed_transform)

    def get_ctransform(self):
        """
        Cached transform property
        Note: Can be None
        """
        if not (hasattr(self, "_ctransform")):
            self._ctransform = self.transform
        return self._ctransform

    def set_ctransform(self, newt):
        """Sets and caches a new transform, invalidating composed transforms."""
        self.transform = newt
        self._ctransform = newt
        self.ccomposed_transform = None

    ctransform = property(get_ctransform, set_ctransform)

    rect_tag = inkex.Rectangle.ctag
    round_tags = tags((inkex.Circle, inkex.Ellipse))
    line_tag = inkex.Line.ctag
    path_tag = inkex.PathElement.ctag

    def get_path2(self):
        """
        Cached get_path, modified to correctly calculate path for rectangles
        and ellipses. Caches Path of an object (set elem.cpath to None to reset)
        """
        if not hasattr(self, "_cpath"):
            # mostly from inkex.elements._polygons
            if self.tag == BaseElementCache.path_tag:
                ret = inkex.Path(self.get("d"))
            elif self.tag == BaseElementCache.rect_tag:
                left, top, width, height = self.xywh()
                rx = ipx(self.get("rx", self.get("ry", "0")))
                ry = ipx(self.get("ry", self.get("rx", "0")))
                right = left + width
                bottom = top + height

                # Calculate the path as the box around the rect
                if rx or ry:
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
                if isinstance(self, (inkex.Ellipse)):
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

    def set_cpath_fcn(self, svi):
        """Invalidates the cached path."""
        if svi is None:
            self.__dict__.pop("_cpath",None)

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
    otp_support_prop = property(lambda x: BaseElementCache.otp_support_tags)
    ptag = inkex.PathElement.ctag

    def object_to_path(self):
        """
        Converts specified elements to paths if supported. Adjusts the 'd'
        attribute and changes the element tag to a path.
        Only operates on elements within the `otp_support_tags` list.
        """
        if (
            self.tag in BaseElementCache.otp_support_tags
            and not self.tag == BaseElementCache.ptag
        ):
            self.set("d", str(self.cpath))  # do this first so cpath is correct
            self.tag = BaseElementCache.ptag

    # Cached root property
    svgtags = {SvgDocumentElement.ctag,'svg'}

    def xywh(self, att=None):
        """
        For rectangle-like attributes, get x, y, width values
        Can handle percentages that inherit from the viewbox
        """
        if not att:
            return (
                self.xywh("x"),
                self.xywh("y"),
                self.xywh("width"),
                self.xywh("height"),
            )
        val = self.get(att, "0")
        try:
            return ipx(val)
        except KeyError:
            if "%" in val and att in ["x", "width"]:
                return self.croot.cdocsize.rawvb[2] * float(val.strip("%")) / 100
            elif "%" in val and att in ["y", "height"]:
                return self.croot.cdocsize.rawvb[3] * float(val.strip("%")) / 100
            else:
                return ipx(val)  # not handled, re-raise

    def get_croot(self):
        """Returns the cached root of the SVG document."""
        try:
            return self._croot
        except AttributeError:
            if self.getparent() is not None:
                self._croot = self.getparent().croot
            elif self.tag in BaseElementCache.svgtags:
                self._croot = self
                self.tag = SvgDocumentElement.ctag
            else:
                self._croot = None
            return self._croot

    def set_croot(self, svi):
        """Sets the cached root of the SVG document."""
        self._croot = svi

    croot = property(get_croot, set_croot)
    
    def get_cxmlspace(self):
        try:
            return self._cxmlspace
        except AttributeError:
            self._cxmlspace = EBget(self,xmlspace)
            if self._cxmlspace is None:
                try:
                    self._cxmlspace = self.getparent().cxmlspace
                except AttributeError: # parent is None
                    self._cxmlspace = None
            return self._cxmlspace
    
    
    def set_cxmlspace(self, svi):
        self._cxmlspace = svi
    
    cxmlspace = property(get_cxmlspace, set_cxmlspace)
                

    # Version of set_random_id that uses cached root
    def set_random_id(
        self,
        prefix: Optional[str] = None,
        size: Optional[int] = None,
        backlinks: bool = False,
        blacklist: Optional[List[str]] = None,
    ):
        """Assigns a unique ID to the element, using the cached root."""
        prefix = str(self) if prefix is None else prefix
        self.set_id(
            self.croot.get_unique_id(prefix, size=size, blacklist=blacklist),
            backlinks=backlinks,
        )

    def get_id(self, as_url=0):
        """
        Version of get_id that uses the low-level get
        """
        if "id" not in self.attrib:
            if hasattr(self.croot,'_iddict'):
                # Inline version of self.set_random_id(self.TAG)
                # Includes set_random_id → get_unique_id → set_id
                new_id = None
                cnt = self.croot.iddict.prefixcounter.get(self.TAG, 0)
                while (
                    new_id is None
                    or new_id in self.croot.iddict
                    or new_id in self.croot.iddict.clips
                    or new_id in self.croot.iddict.masks
                ):
                    new_id = self.TAG + str(cnt)
                    cnt += 1
                self.croot.iddict.prefixcounter[self.TAG] = cnt
                self.croot.iddict[new_id] = self
                EBset(self, "id", new_id)
            else:
                # iddict initialization sets ID (prevents double assignment)
                self.croot.iddict
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
        if backlinks:
            BE_set_id(self, new_id, backlinks=backlinks)
        else:
            EBset(self,'id',new_id)

    comment_tag = lxml.etree.Comment("").tag

    def descendants2(self, return_tails=False, tag='*'):
        """
        A version of descendants that also returns a list of elements whose tails
        precede each element. (This is helpful for parsing text.)
        """
        if not return_tails:
            return list(self.iter(tag))
            # starts with self, gets Elements only (excludes comments)
        descendants = [self]
        precedingtails = [[]]
        endsat = [(self, None)]
        for ddv in self.iterdescendants(tag):
            precedingtails.append([])
            while endsat[-1][1] == ddv:
                precedingtails[-1].append(endsat.pop()[0])
            nsib = ddv.getnext()
            if nsib is None:
                endsat.append((ddv, endsat[-1][1]))
            else:
                endsat.append((ddv, nsib))
            descendants.append(ddv)

        precedingtails.append([])
        while endsat:
            precedingtails[-1].append(endsat.pop()[0])
        return descendants, precedingtails

    def ancestors2(self, includeme=False, stopbefore=None, stopafter=None):
        """Version of ancestors that can stop before/after encountering an element"""
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
        """Deletes the element and optionally cleans up empty parent groups."""
        svg = self.croot
        for ddv in reversed(list(self.iter('*'))):
            did = ddv.get_id()
            if svg is not None:
                try:
                    svg.ids.remove(did)
                except (KeyError, AttributeError):
                    pass
                svg.iddict.remove(ddv)

                # Remove any clips/masks that refer to this element so as not
                # to leave behind orphan references
                if did in svg.iddict.clips:
                    for el in svg.iddict.clips[did]:
                        el.set_link("clip-path", None)
                if did in svg.iddict.masks:
                    for el in svg.iddict.masks[did]:
                        el.set_link("mask", None)

            ddv.croot = None
        if hasattr(svg, "_cd2"):
            svg.cdescendants2.delel(self)

        if deleteup:
            # If set, remove empty ancestor groups
            myp = self.getparent()
            BaseElementCache.BE_delete(self)
            if myp is not None and len(myp) == 0:
                BaseElementCache.delete(myp, True)
        else:
            BaseElementCache.BE_delete(self)

    # Insertion
    BE_insert = lxml.etree.ElementBase.insert

    def insert(self, index, elem):
        """Inserts an element at a specified index, managing caching."""
        oldroot = elem.croot
        newroot = self.croot

        BaseElementCache.BE_insert(self, index, elem)
        elem.ccascaded_style = None
        elem.cspecified_style = None
        elem.ccomposed_transform = None

        if EBget(elem, "id") is None:
            # Make sure all elements have an ID (most assigned here)
            elem.croot = newroot
            if newroot is not None:
                newroot.iddict.add(elem)  # generates an ID if needed
            for k in list2(elem):
                elem.append(k)  # update children
        elif oldroot != newroot:
            # When the root is changing, remove from old dicts and add to new
            css = None
            if oldroot is not None:
                oldroot.iddict.remove(elem)
                css = oldroot.cssdict.pop(elem.get_id(), None)
            elem.croot = newroot
            if newroot is not None:
                newroot.iddict.add(elem)  # generates an ID if needed
                if css is not None:
                    newroot.cssdict[elem.get_id()] = css
            for k in list2(elem):
                elem.append(k)  # update children

    # Appending
    BE_append = lxml.etree.ElementBase.append
    
    def append(self, elem):
        """Appends an element, managing caching and ID conflicts."""
        oldroot = elem.croot
        newroot = self.croot

        BaseElementCache.BE_append(self, elem)
        elem.ccascaded_style = None
        elem.cspecified_style = None
        elem.ccomposed_transform = None

        for d in elem.iter('*'):  # includes elem itself
            if EBget(d, "id") is None:
                d.croot = newroot
                if newroot is not None:
                    newroot.iddict.add(d)  # generates an ID if needed
            elif oldroot != newroot:
                css = None
                if oldroot is not None:
                    oldroot.iddict.remove(d)
                    css = oldroot.cssdict.pop(d.get_id(), None)
                d.croot = newroot
                if newroot is not None:
                    newroot.iddict.add(d)
                    if css is not None:
                        newroot.cssdict[d.get_id()] = css

    # addnext
    BE_addnext = lxml.etree.ElementBase.addnext
    
    def addnext(self, elem):
        """Adds an element next to the specified element, managing caching (non-recursive)."""
        oldroot = elem.croot
        newroot = self.croot
    
        BaseElementCache.BE_addnext(self, elem)
        elem.ccascaded_style = None
        elem.cspecified_style = None
        elem.ccomposed_transform = None
    
        for d in elem.iter('*'):  # includes elem itself
            if EBget(d, "id") is None:
                d.croot = newroot
                if newroot is not None:
                    newroot.iddict.add(d)  # generates an ID if needed
            elif oldroot != newroot:
                css = None
                if oldroot is not None:
                    oldroot.iddict.remove(d)
                    css = oldroot.cssdict.pop(d.get_id(), None)
                d.croot = newroot
                if newroot is not None:
                    newroot.iddict.add(d)
                    if css is not None:
                        newroot.cssdict[d.get_id()] = css

       
    BE_extend = lxml.etree.ElementBase.extend
    def extend(self, elems):
        """Appends multiple elements, managing caching and ID conflicts."""
        oldroots = [elem.croot for elem in elems]
        newroot = self.croot

        BaseElementCache.BE_extend(self, elems)
        for elem, oldroot in zip(elems,oldroots):
            elem.ccascaded_style = None
            elem.cspecified_style = None
            elem.ccomposed_transform = None
    
            if EBget(elem, "id") is None:
                # Make sure all elements have an ID (most assigned here)
                elem.croot = newroot
                if newroot is not None:
                    newroot.iddict.add(elem)  # generates an ID if needed
                for k in list2(elem):
                    elem.append(k)  # update children
            elif oldroot != newroot:
                # When the root is changing, remove from old dicts and add to new
                css = None
                if oldroot is not None:
                    oldroot.iddict.remove(elem)
                    css = oldroot.cssdict.pop(elem.get_id(), None)
                elem.croot = newroot
                if newroot is not None:
                    newroot.iddict.add(elem)  # generates an ID if needed
                    if css is not None:
                        newroot.cssdict[elem.get_id()] = css
                for k in list2(elem):
                    elem.append(k)  # update children

    # Duplication
    clipmasktags = {inkex.addNS("mask", "svg"), inkex.ClipPath.ctag}

    def duplicate(self):
        """Creates a duplicate of the element, managing ID and caching."""
        eltail = self.tail
        if eltail is not None:
            self.tail = None
        dup = self.copy()

        # After copying, duplicates have the original ID. Remove prior to insertion
        origids = dict()
        for dupd in dup.iter('*'):
            origids[dupd] = dupd.pop("id", None)
            dupd.croot = self.croot  # set now for speed

        self.addnext(dup)
        if eltail is not None:
            self.tail = eltail
        # Fix tail bug: https://gitlab.com/inkscape/extensions/-/issues/480

        css = self.croot.cssdict
        newids = {
            EBget(k, "id"): css.get(origids[k])
            for k in dup.iter('*')
            if origids[k] in css
        }
        dup.croot.cssdict.update(newids)

        if dup.tag in BaseElementCache.clipmasktags:
            # Clip duplications can cause weird issues if they are not appended
            # to the end of Defs
            dup.croot.cdefs.append(dup)
        return dup

    def get_parsed_text(self):
        """Add parsed_text property to text, which is used to get the
        properties of text"""
        if not (hasattr(self, "_parsed_text")):
            from inkex.text.parser import ParsedText
            self._parsed_text = ParsedText(self, self.croot.char_table)
        return self._parsed_text

    def set_parsed_text(self, svi):
        """Invalidates the cached parsed text."""
        if hasattr(self, "_parsed_text") and svi is None:
            delattr(self, "_parsed_text")

    parsed_text = property(get_parsed_text, set_parsed_text)


class SvgDocumentElementCache(SvgDocumentElement):
    """Adds caching for SVG document elements."""

    def cdefs_func(self):
        """Cached def directly under root"""
        if not (hasattr(self, "_cdefs")):
            for k in list(self):
                if isinstance(k, (inkex.Defs)):
                    self._cdefs = k
                    return self._cdefs
            defel = inkex.Defs()
            self.insert(0, defel)
            self._cdefs = defel
        return self._cdefs

    cdefs = property(cdefs_func)

    styletag = inkex.addNS("style", "svg")

    def crootsty_func(self):
        """Cached style element directly under root"""
        if not hasattr(self, "_crootsty"):
            rootstys = [
                sty for sty in list(self) if sty.tag == SvgDocumentElementCache.styletag
            ]
            if not rootstys:
                self._crootsty = inkex.StyleElement()
                self.insert(0, self._crootsty)
            else:
                self._crootsty = rootstys[0]
        return self._crootsty

    crootsty = property(crootsty_func)

    def get_ids(self):
        """Version of get_ids that uses iddict"""
        return set(self.iddict.keys())

    def get_unique_id(
        self,
        prefix: str,
        size: Optional[int] = None,
        blacklist: Optional[List[str]] = None,
    ):
        """Version of get_unique_id that removes randomness by keeping a
        running count"""
        new_id = None
        cnt = self.iddict.prefixcounter.get(prefix, 0)

        while new_id is None or (
            new_id in self.iddict
            or new_id in self.iddict.clips
            or new_id in self.iddict.masks
            or (blacklist is not None and new_id in blacklist)
        ):
            new_id = prefix + str(cnt)
            cnt += 1

        self.iddict.prefixcounter[prefix] = cnt
        return new_id

    # Repeated getElementById lookups can be slow, so instead create a cached
    # iddict property. When an element is created that may be needed later,
    # it should be added using self.iddict.add.
    urlpat = re.compile(r"^url\(#(.*)\)$|^#")

    def getElementById(self, eid: str, elm="*", literal=False):
        """Returns an element by ID using cached data for efficiency."""
        if eid is not None and not literal:
            eid = SvgDocumentElementCache.urlpat.sub(r"\1", eid.strip())
        return self.iddict.get(eid)

    class IDDict(dict):
        """Keeps track of the IDs in a document"""

        def __init__(self, svg):
            super().__init__()
            self.svg = svg
            self.prefixcounter = dict()
            self.clips = dict()
            self.masks = dict()
            self.linked_by = dict()
            toassign = []
            for elem in svg.iter('*'):
                if "id" in elem.attrib:
                    self[EBget(elem, "id")] = elem
                else:
                    toassign.append(elem)
                elem.croot = svg  # do now to speed up later
                if '{' not in elem.tag:
                    # Make sure tags have a namespace
                    elem.tag = elem.ctag

                # While we're iterating, we gather clips/masks/links
                self.add_to_linkdict(elem, "clip-path")
                self.add_to_linkdict(elem, "mask")
                self.add_to_linkdict(elem, xlinkhref)

            for elem in toassign:
                # Reduced version of get_unique_id_fcn
                # Cannot call it since it relies on iddict
                prefix = elem.TAG
                new_id = None
                cnt = self.prefixcounter.get(prefix, 0)
                while new_id is None or new_id in self:
                    new_id = prefix + str(cnt)
                    cnt += 1
                self.prefixcounter[prefix] = cnt
                # Reduced version of set_id
                self[new_id] = elem
                # BE_set_id(elem, new_id)
                EBset(elem,'id',new_id) # can use low-level here

        def add(self, elem):
            """Add an element to the ID dict"""
            elid = elem.get_id()
            # fine since elem should have a croot to get called here
            if elid in self and not self[elid] == elem:
                # Make a new id when there's a conflict
                elem.set_random_id(elem.TAG)
                elid = elem.get_id()
            self[elid] = elem
            self.add_to_linkdict(elem, "clip-path")
            self.add_to_linkdict(elem, "mask")
            self.add_to_linkdict(elem, xlinkhref)

        @property
        def descendants(self):
            """all svg descendants, not necessarily in order"""
            return list(self.values())

        def remove(self, elem):
            """Remove from ID dict"""
            elid = elem.get_id()
            if elid in self:
                del self[elid]
            self.remove_from_linkdict(elem, "clip-path")
            self.remove_from_linkdict(elem, "mask")
            self.remove_from_linkdict(elem, xlinkhref)

        def add_to_linkdict(self, elem, att):
            """
            Maintain a dictionary of linky attributes like clip-path, mask, etc.
            Keys are ids that are referenced, whether or not they actually exist.
            Values are a list of nodes linking to that id.
            """
            linkdict = self.__dict__[linkmap[att]]
            cid = EBget(elem, att)
            if cid:
                match = patmap[att].search(cid)
                if match:
                    linkdict.setdefault(match.group(1), set()).add(elem)

        def remove_from_linkdict(self, elem, att):
            linkdict = self.__dict__[linkmap[att]]
            cid = EBget(elem, att)
            if cid:
                match = patmap[att].search(cid)
                if match:
                    cid = match.group(1)
                    if cid in linkdict and elem in linkdict[cid]:
                        linkdict[cid].remove(elem)
                        if len(linkdict[cid]) == 0:
                            del linkdict[cid]

    @property
    def iddict(self):
        """Returns the ID dictionary that caches all elements by ID."""
        if not (hasattr(self, "_iddict")):
            self._iddict = SvgDocumentElementCache.IDDict(self)
        return self._iddict

    estyle = Style()  # keep separate in case Style was overridden

    # Check if v1.4 or later
    hasmatches = hasattr(inkex.styles.ConditionalStyle, "matches")

    class CSSDict(dict):
        """A dict that keeps track of the CSS style for each element"""

        def __init__(self, svg):
            self.svg = svg

            # For certain xpaths such as classes, we can avoid xpath calls
            # by checking the class attributes on a document's descendants directly.
            # This is much faster for large documents.
            hasall = False
            simpleclasses = dict()
            simpleids = dict()
            patcls = re.compile(r"\.([-\w]+)")
            patid = re.compile(r"#(\w+)")

            for sheet in svg.stylesheets:
                for style in sheet:
                    rules = tuple(str(r) for r in style.rules)
                    # inkex.utils.debug(rules)
                    if rules == ("*",):
                        hasall = True
                    elif all(patcls.fullmatch(r) for r in rules):
                        # all rules are classes
                        simpleclasses[rules] = [patcls.sub(r"\1", r) for r in rules]
                    elif all(patid.match(r) for r in rules):
                        # all rules are ids
                        simpleids[rules] = [patid.sub(r"\1", r) for r in rules]

            # Now, we make a dictionary of rules / xpaths we can do easily
            knownrules = dict()
            if hasall or len(simpleclasses) > 0:
                dds = svg.iddict.descendants
                if hasall:
                    knownrules[("*",)] = dds
                cvs = [EBget(d, "class") for d in dds]
                c2s = [(i, c) for (i, c) in enumerate(cvs) if c is not None]
                cmatches = dict()
                for i, clsval in c2s:
                    for c in clsval.split(" "):
                        cmatches[c] = cmatches.get(c, []) + [dds[i]]
                kxp2 = {
                    rules: list(
                        dict.fromkeys(
                            [d for c in clslist if c in cmatches for d in cmatches[c]]
                        )
                    )
                    for rules, clslist in simpleclasses.items()
                }
                knownrules.update(kxp2)

            for rules, ids in simpleids.items():
                knownrules[rules] = []
                for idv in ids:
                    idel = svg.getElementById(idv)
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
                            # Technically we should copy stylev, but as long as
                            # styles in cssdict are only used in
                            # get_cascaded_style, this is fine since that
                            # function adds (creating copies)
                            self.update(newstys)
                    except (lxml.etree.XPathEvalError,):
                        pass

        def dupe_entry(self, oldid, newid):
            """Duplicate entry in cssdict"""
            csssty = self.get(oldid)
            if csssty is not None:
                self[newid] = csssty

    def get_cssdict(self):
        """Returns the CSS dictionary that caches styles by element ID."""
        try:
            return self._cssdict
        except AttributeError:
            self._cssdict = SvgDocumentElementCache.CSSDict(self)
            return self._cssdict

    cssdict = property(get_cssdict)

    def document_size(self):
        """Calculates and caches the size of the SVG document in various units."""
        if not (hasattr(self, "_cdocsize")):
            rvb = self.get_viewbox()
            wstr = self.get("width")
            hstr = self.get("height")

            if rvb == [0, 0, 0, 0]:
                wval = ipx(wstr) if "%" not in wstr else 300
                hval = ipx(hstr) if "%" not in hstr else 150
                vbx = [0, 0, wval, hval]
            else:
                vbx = [float(v) for v in rvb]  # just in case
            rawvb = vbx[:]

            # Get document width and height in pixels
            wvl, wun = (
                inkex.units.parse_unit(wstr) if wstr is not None else (vbx[2], "px")
            )
            hvl, hun = (
                inkex.units.parse_unit(hstr) if hstr is not None else (vbx[3], "px")
            )

            def parse_preserve_aspect_ratio(par_str):
                align, meet_or_slice = "xMidYMid", "meet"  # defaults
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
                if par_str:
                    values = par_str.split(" ")
                    if len(values) == 1:
                        if values[0] in valigns:
                            align = values[0]
                        elif values[0] in vmoss:
                            meet_or_slice = values[0]
                    elif len(values) == 2:
                        if values[0] in valigns and values[1] in vmoss:
                            align = values[0]
                            meet_or_slice = values[1]
                return align, meet_or_slice

            align, meet_or_slice = parse_preserve_aspect_ratio(
                self.get("preserveAspectRatio")
            )

            xfr = (
                inkex.units.convert_unit(str(wvl) + " " + wun, "px") / vbx[2]
                if wun != "%"
                else wvl / 100
            )  # width of uu in px pre-stretch
            yfr = (
                inkex.units.convert_unit(str(hvl) + " " + hun, "px") / vbx[3]
                if hun != "%"
                else hvl / 100
            )  # height of uu in px pre-stretch
            if align != "none":
                mfr = min(xfr, yfr) if meet_or_slice == "meet" else max(xfr, yfr)
                xmf = {"xMin": 0, "xMid": 0.5, "xMax": 1}[align[0:4]]
                ymf = {"YMin": 0, "YMid": 0.5, "YMax": 1}[align[4:]]
                vbx[0], vbx[2] = (
                    vbx[0] + vbx[2] * (1 - xfr / mfr) * xmf,
                    vbx[2] / mfr * (xfr if wun != "%" else 1),
                )
                vbx[1], vbx[3] = (
                    vbx[1] + vbx[3] * (1 - yfr / mfr) * ymf,
                    vbx[3] / mfr * (yfr if hun != "%" else 1),
                )
                if wun == "%":
                    wvl, wun = vbx[2] * mfr, "px"
                if hun == "%":
                    hvl, hun = vbx[3] * mfr, "px"
            else:
                if wun == "%":
                    wvl, wun, vbx[2] = vbx[2], "px", vbx[2] / xfr
                if hun == "%":
                    hvl, hun, vbx[3] = vbx[3], "px", vbx[3] / yfr

            wpx = inkex.units.convert_unit(
                str(wvl) + " " + wun, "px"
            )  # document width  in px
            hpx = inkex.units.convert_unit(
                str(hvl) + " " + hun, "px"
            )  # document height in px
            uuw = wpx / vbx[2]  # uu width  in px (px/uu)
            uuh = hpx / vbx[3]  # uu height in px (px/uu)
            uupx = uuw if abs(uuw - uuh) < 0.001 else None  # uu size  in px  (px/uu)
            # should match Scale in Document Properties

            # Get Pages
            nvs = [elem for elem in list(self) if isinstance(elem, inkex.NamedView)]
            pgs = [
                elem
                for nv in nvs
                for elem in list(nv)
                if elem.tag == inkex.addNS("page", "inkscape")
            ]
            for pgv in pgs:
                pgv.bbuu = [
                    ipx(pgv.get("x")),
                    ipx(pgv.get("y")),
                    ipx(pgv.get("width")),
                    ipx(pgv.get("height")),
                ]
                pgv.bbpx = [
                    pgv.bbuu[0] * xfr,
                    pgv.bbuu[1] * yfr,
                    pgv.bbuu[2] * xfr,
                    pgv.bbuu[3] * yfr,
                ]

            class DocSize:
                """Contains the properties relating to document size"""

                def __init__(
                    self,
                    effvb,
                    uuw,
                    uuh,
                    uupx,
                    wunit,
                    hunit,
                    wpx,
                    hpx,
                    xfr,
                    yfr,
                    pgs,
                    rawvb,
                ):
                    self.effvb = effvb
                    self.uuw = uuw
                    self.uuh = uuh
                    self.uupx = uupx
                    self.wunit = wunit
                    self.hunit = hunit
                    self.wpx = wpx
                    self.hpx = hpx
                    self.rawxf = xfr
                    self.rawyf = yfr
                    self.pgs = pgs
                    self.rawvb = rawvb

                def uutopx(self, x):
                    """Converts a bounding box specified in uu to pixels"""
                    ret = [
                        (x[0] - self.effvb[0]) * self.uuw,
                        (x[1] - self.effvb[1]) * self.uuh,
                        x[2] * self.uuw,
                        x[3] * self.uuh,
                    ]
                    return ret

                def pxtouu(self, x):
                    """Converts a bounding box specified in pixels to uu"""
                    ret = [
                        x[0] / self.uuw + self.effvb[0],
                        x[1] / self.uuh + self.effvb[1],
                        x[2] / self.uuw,
                        x[3] / self.uuh,
                    ]
                    return ret

                def unittouu(self, x):
                    """Converts any unit into uu"""
                    return (
                        inkex.units.convert_unit(x, "px") / self.uupx
                        if self.uupx is not None
                        else None
                    )

                def uutopxpgs(self, x):
                    """Version that applies to Pages"""
                    return [
                        x[0] * self.rawxf,
                        x[1] * self.rawyf,
                        x[2] * self.rawxf,
                        x[3] * self.rawyf,
                    ]

                def pxtouupgs(self, x):
                    """Version that applies to Pages"""
                    return [
                        x[0] / self.rawxf,
                        x[1] / self.rawyf,
                        x[2] / self.rawxf,
                        x[3] / self.rawyf,
                    ]

                def __repr__(self):
                    return (
                        f"DocSize(effvb={self.effvb}, uuw={self.uuw}, uuh={self.uuh}, "
                        f"uupx={self.uupx}, wunit='{self.wunit}', hunit='{self.hunit}', "
                        f"wpx={self.wpx}, hpx={self.hpx}, xfr={self.rawxf}, yfr={self.rawyf}, "
                        f"pgs={self.pgs}), rawvb={self.rawvb}"
                    )

            self._cdocsize = DocSize(
                vbx, uuw, uuh, uupx, wun, hun, wpx, hpx, xfr, yfr, pgs, rawvb
            )
        return self._cdocsize

    def set_cdocsize(self, svi):
        """Invalidates the cached document size."""
        if svi is None and hasattr(self, "_cdocsize"):  # invalidate
            delattr(self, "_cdocsize")

    cdocsize = property(document_size, set_cdocsize)

    def set_viewbox(self, newvb):
        """Sets a new viewbox for the SVG, updating dimensions appropriately."""
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
        """Converts viewbox to pixels, removing any non-uniform scaling appropriately"""
        pgbbs = [pgv.bbpx for pgv in self.cdocsize.pgs]
        self.set("viewBox", " ".join([str(v) for v in self.cdocsize.effvb]))
        self.set("width", str(self.cdocsize.wpx))
        self.set("height", str(self.cdocsize.hpx))

        # Update Pages appropriately
        self.cdocsize = None
        for i, pgv in enumerate(self.cdocsize.pgs):
            newbbuu = self.cdocsize.pxtouupgs(pgbbs[i])
            pgv.set("x", str(newbbuu[0]))
            pgv.set("y", str(newbbuu[1]))
            pgv.set("width", str(newbbuu[2]))
            pgv.set("height", str(newbbuu[3]))

    # Add char_table property to SVGs, which are used to collect all of the
    # properties of fonts in the document. Alternatively, calling make_char_table
    # on a subset of elements will cause only those elements to be included.

    def make_char_table(self, els=None):
        """
        Can be called with els argument to examine list of elements only
        (otherwise use entire SVG)
        """
        ttags = tags((inkex.TextElement, inkex.FlowRoot))
        if els is None:
            tels = [d for d in self.iddict.descendants if d.tag in ttags]
        else:
            tels = [d for d in els if d.tag in ttags]
        if not (hasattr(self, "_char_table")) or any(
            t not in getattr(self, "_char_table").els for t in tels
        ): 
            from inkex.text.parser import CharacterTable
            self._char_table = CharacterTable(tels)

    def get_char_table(self):
        """Returns the cached character table, creating it if necessary."""
        if not (hasattr(self, "_char_table")):
            self.make_char_table()
        return self._char_table

    def set_char_table(self, svi):
        """Invalidates the cached character table."""
        if svi is None and hasattr(self, "_char_table"):
            delattr(self, "_char_table")

    char_table = property(get_char_table, set_char_table)


class StyleCache(Style):
    """Caches and manages style data with enhanced functionality."""

    get_link = BaseElementCache.get_link

    def __hash__(self):
        """Generates a hash based on the style items."""
        return hash(tuple(self.items()))  # type: ignore

    # Adds three styles
    def add3_fcn(self, y, z):
        """Adds three style objects together."""
        return self + y + z

    add3 = add3_fcn if not hasattr(Style, "add3") else getattr(Style, "add3")
