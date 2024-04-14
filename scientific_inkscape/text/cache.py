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

# A collection of functions that provide caching of certain Inkex properties.
# Most provide the same functionality as the regular properties,
# but with a 'c' in front of the name. For example,
#   Style: cstyle, cspecified_style, ccascaded_style
#   Transform: ctransform, ccomposed_transform
#   Miscellaneous: croot, cdefs, ctag
# Most are invalidated by setting to None (except ctransform, which is set to identity).
# xpath calls are avoided at all costs
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
from inkex import Style
from inkex import BaseElement, SvgDocumentElement
import lxml, re

EBget = lxml.etree.ElementBase.get
EBset = lxml.etree.ElementBase.set

# Adds ctag to the inkex classes, which holds each class's corresponding tag
# Checking the tag is usually much faster than instance checking, which can
# substantially speed up low-level functions.
try:
    lt = dict(inkex.elements._parser.NodeBasedLookup.lookup_table)
except:
    lt = dict(inkex.elements._base.NodeBasedLookup.lookup_table)
shapetags = set()
for k, v in lt.items():
    for v2 in v:
        if isinstance(k, tuple):
            # v1.0-1.3
            v2.ctag = inkex.addNS(k[1], k[0])
        else:
            # v1.4+
            v2.ctag = k
        if issubclass(v2, inkex.ShapeElement):
            shapetags.add(v2.ctag)
tags = lambda x: set([v.ctag for v in x])  # converts class tuple to set of tags


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
                k.cspecified_style = None  # invalidate children
        except:
            pass


BaseElement.cspecified_style = property(get_cspecified_style, set_cspecified_style)

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
bstyle = Style("")


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
        # attsty = Style.__new__(Style)
        attsty = Style()
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
class CStyle(Style):
    # Modifies Style to delete key when value set to None
    def __init__(self, val, el):
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
            el._cstyle = CStyle(EBget(el, "style"), el)
        return el._cstyle

    def __set__(self, el, value):
        vstr = str(value)
        if vstr == "":
            if "style" in el.attrib:
                del el.attrib["style"]
        else:
            EBset(el, "style", vstr)

        if not isinstance(value, CStyle):
            value = CStyle(value, el)
        el._cstyle = value
        el.ccascaded_style = None
        el.cspecified_style = None


BaseElement.cstyle = CStyleDescriptor()


# Returns non-comment children
comment_tag = lxml.etree.Comment


def list2(el):
    return [k for k in list(el) if not (k.tag == comment_tag)]


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


def set_ccomposed_transform(el, si):
    if si is None and hasattr(el, "_ccomposed_transform"):
        delattr(el, "_ccomposed_transform")  # invalidate
        for k in list2(el):
            k.ccomposed_transform = None  # invalidate descendants


BaseElement.ccomposed_transform = property(
    get_ccomposed_transform, set_ccomposed_transform
)


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


# Parsed Inkex version, with extension back to v0.92.4
if not hasattr(inkex, "__version__"):
    try:
        tmp = BaseElement.unittouu  # introduced in 1.1
        inkex.__version__ = "1.1.0"
    except:
        try:
            from inkex.paths import Path, CubicSuperPath  # noqa

            inkex.__version__ = "1.0.0"
        except:
            inkex.__version__ = "0.92.4"
inkex.vparse = lambda x: [int(v) for v in x.split(".")]  # type: ignore
inkex.ivp = inkex.vparse(inkex.__version__)  # type: ignore
# pre1p2 = inkex.ivp[0] <= 1 and inkex.ivp[1] < 2
# pre1p1 = ivp[0] <= 1 and ivp[1] < 1


# Implicit pixel function
# For many properties, a size specification of '1px' actually means '1uu'
# Even if the size explicitly says '1mm' and the user units are mm, this will be
# first converted to px and then interpreted to mean user units. (So '1mm' would
# up being bigger than 1 mm). This returns the size as Inkscape will interpret it (in uu).
#   No unit: Assumes 'px'
#   Invalid unit: Returns None (used to return 0, changed 2023.04.18)
from inkex.units import CONVERSIONS, BOTH_MATCH

conv2 = {k: CONVERSIONS[k] / CONVERSIONS["px"] for k, v in CONVERSIONS.items()}
from functools import lru_cache


@lru_cache(maxsize=None)
def ipx(strin):
    try:
        ret = BOTH_MATCH.match(strin)
        value = float(ret.groups()[0])
        from_unit = ret.groups()[-1] or "px"
        return value * conv2[from_unit]
    except:
        return None


# Cached get_path, modified to correctly calculate path for rectangles and ellipses
# Caches Path of an object (set el.cpath to None to reset)
rect_tag = inkex.Rectangle.ctag
round_tags = tags((inkex.Circle, inkex.Ellipse))
line_tag = inkex.Line.ctag
path_tag = inkex.PathElement.ctag


def get_path2(el):
    if not hasattr(el, "_cpath"):
        # mostly from inkex.elements._polygons
        if el.tag == path_tag:
            ret = inkex.Path(el.get("d"))
        elif el.tag == rect_tag:
            left = ipx(el.get("x", "0"))
            top = ipx(el.get("y", "0"))
            width = ipx(el.get("width", "0"))
            height = ipx(el.get("height", "0"))
            rx = ipx(el.get("rx", el.get("ry", "0")))
            ry = ipx(el.get("ry", el.get("rx", "0")))
            right = left + width
            bottom = top + height
            # if rx:
            #     return inkex.Path((
            #         "M {lft2},{topv}"
            #         "L {rgt2},{topv}  A {rxv},{ryv} 0 0 1 {rgtv},{top2}"
            #         "L {rgtv},{btm2}  A {rxv},{ryv} 0 0 1 {rgt2},{btmv}"
            #         "L {lft2},{btmv}  A {rxv},{ryv} 0 0 1 {lftv},{btm2}"
            #         "L {lftv},{top2}  A {rxv},{ryv} 0 0 1 {lft2},{topv} z".format(
            #             topv=top, btmv=bottom, lftv=left,rgtv=right, rxv=rx, ryv=ry,
            #             lft2=left+rx, rgt2=right-rx, top2=top+ry, btm2=bottom-ry
            #         ))
            #     )
            # ret = inkex.Path("M {lftv},{topv} h {wdtv} v {hgtv} h {wdt2} z".format(
            #     topv=top, lftv=left, wdtv=width, hgtv=height,
            #     wdt2=-width)
            # )

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

        elif el.tag in round_tags:
            cx = ipx(el.get("cx", "0"))
            cy = ipx(el.get("cy", "0"))
            if isinstance(el, (inkex.Ellipse)):  # ellipse
                rx = ipx(el.get("rx", "0"))
                ry = ipx(el.get("ry", "0"))
            else:  # circle
                rx = ipx(el.get("r", "0"))
                ry = ipx(el.get("r", "0"))
            ret = inkex.Path(
                (
                    "M {cx},{y} "
                    "a {rx},{ry} 0 1 0 {rx}, {ry} "
                    "a {rx},{ry} 0 0 0 -{rx}, -{ry} z"
                ).format(cx=cx, y=cy - ry, rx=rx, ry=ry)
            )

        elif el.tag == line_tag:  # updated in v1.2
            x1 = ipx(el.get("x1", "0"))
            y1 = ipx(el.get("y1", "0"))
            x2 = ipx(el.get("x2", "0"))
            y2 = ipx(el.get("y2", "0"))
            ret = inkex.Path(f"M{x1},{y1} L{x2},{y2}")
        else:
            ret = el.get_path()
            # inkex.utils.debug(el.tag)
            if isinstance(ret, str):
                ret = inkex.Path(ret)
        el._cpath = ret

    return el._cpath


def set_cpath_fcn(el, sv):
    if sv is None and hasattr(el, "_cpath"):
        delattr(el, "_cpath")  # invalidate


BaseElement.cpath = property(get_path2, set_cpath_fcn)
cpath_support = (
    inkex.Rectangle,
    inkex.Ellipse,
    inkex.Circle,
    inkex.Polygon,
    inkex.Polyline,
    inkex.Line,
    inkex.PathElement,
)


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


# Cached defs that avoids xpath. Looks for a defs under the svg
def cdefs_func(svg):
    if not (hasattr(svg, "_cdefs")):
        for k in list(svg):
            if isinstance(k, (inkex.Defs)):
                svg._cdefs = k
                return svg._cdefs
        d = inkex.Defs()
        svg.insert(0, d)
        svg._cdefs = d
    return svg._cdefs


inkex.SvgDocumentElement.cdefs = property(cdefs_func)


# Version of get_ids that uses iddict
def get_ids_func(svg):
    """Returns a set of unique document ids"""
    return set(svg.iddict.keys())


inkex.SvgDocumentElement.get_ids = get_ids_func  # type: ignore

# Version of get_unique_id that removes randomness by keeping a running count
from typing import Optional, List


def get_unique_id_fcn(
    svg,
    prefix: str,
    size: Optional[int] = None,
    blacklist: Optional[List[str]] = None,
):
    new_id = None
    cnt = svg.iddict.prefixcounter.get(prefix, 0)
    if blacklist is None:
        while new_id is None or new_id in svg.iddict:
            new_id = prefix + str(cnt)
            cnt += 1
    else:
        while new_id is None or new_id in svg.iddict or new_id in blacklist:
            new_id = prefix + str(cnt)
            cnt += 1
    svg.iddict.prefixcounter[prefix] = cnt
    return new_id


inkex.SvgDocumentElement.get_unique_id = get_unique_id_fcn  # type: ignore


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


inkex.BaseElement.set_random_id = set_random_id_fcn  # type: ignore


# Version of get_id that uses the low-level get
def get_id_func(el, as_url=0):
    if "id" not in el.attrib:
        el.set_random_id(el.TAG)
    eid = EBget(el, "id")
    if as_url > 0:
        eid = "#" + eid
        if as_url > 1:
            eid = f"url({eid})"
    return eid


BaseElement.get_id = get_id_func  # type: ignore

# Repeated getElementById lookups can be slow, so instead create a cached iddict property.
# When an element is created that may be needed later, it must be added using svg.iddict.add.
urlpat = re.compile(r"^url\(#(.*)\)$|^#")


def getElementById_func(svg, eid: str, elm="*", literal=False):
    if eid is not None and not literal:
        eid = urlpat.sub(r"\1", eid.strip())
    return svg.iddict.get(eid)


inkex.SvgDocumentElement.getElementById = getElementById_func  # type: ignore


# Add iddict, which keeps track of the IDs in a document
class iddict(inkex.OrderedDict):
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
            inkex_set_id(el, new_id)

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


def get_iddict(svg):
    if not (hasattr(svg, "_iddict")):
        svg._iddict = iddict(svg)
    return svg._iddict


inkex.SvgDocumentElement.iddict = property(get_iddict)

inkex_set_id = inkex.BaseElement.set_id


def set_id_mod(self, new_id, backlinks=False):
    """Set the id and update backlinks to xlink and style urls if needed"""
    if self.croot is not None:
        self.croot.iddict[new_id] = self
    # old_id = self.get('id')
    inkex_set_id(self, new_id, backlinks=backlinks)
    # Deleting the old value doesn't currently work properly (abandoned references?)
    # if old_id is not None and old_id in self.croot.iddict:
    #     del self.croot.iddict[old_id]


inkex.BaseElement.set_id = set_id_mod  # type:ignore

# A dict that keeps track of the CSS style for each element
estyle = Style()  # keep separate in case Style was overridden

# Check if v1.4 or later
hasmatches = hasattr(inkex.styles.ConditionalStyle, "matches")
if hasmatches:
    import warnings


# try:
#     estyle2 = inkex.origStyle()
# except:
#     estyle2 = inkex.Style()  # still using Inkex's Style here since from stylesheets
# estyle2 = inkex.Style()
class cssdict(inkex.OrderedDict):
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
                if not hasmatches:
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
                else:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", category=DeprecationWarning)
                        xp = style.to_xpath()
                    if xp == "//*":
                        hasall = True
                    elif all(
                        [
                            c1.sub(r"IAMCLASS", style._rules[ii].strip()) == "IAMCLASS"
                            for ii, r in enumerate(style.rules)
                        ]
                    ):  # all rules are classes
                        simpleclasses[xp] = [
                            c1.sub(r"\1", style._rules[ii].strip())
                            for ii, r in enumerate(style.rules)
                        ]
                    elif all(
                        [
                            c2.sub(r"IAMID", style._rules[ii].strip()) == "IAMID"
                            for ii, r in enumerate(style.rules)
                        ]
                    ):  # all rules are ids
                        simpleids[xp] = [
                            c1.sub(r"\1", style._rules[ii].strip())[1:]
                            for ii, r in enumerate(style.rules)
                        ]

        knownxpaths = dict()
        if hasall or len(simpleclasses) > 0:
            ds = svg.iddict.ds

            cs = [EBget(d, "class") for d in ds]
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
                    if hasmatches:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", category=DeprecationWarning)
                            xp = style.to_xpath()
                    else:
                        xp = style.to_xpath()
                    stylev = Style(style)
                    if xp in knownxpaths:
                        els = knownxpaths[xp]
                    else:
                        els = svg.xpath(xp)
                    for elem in els:
                        elid = elem.get("id", None)
                        if elid is not None and style != estyle:
                            if self.get(elid) is None:
                                self[elid] = stylev.copy()
                            else:
                                self[elid] += style
                except (lxml.etree.XPathEvalError, TypeError):
                    pass

    def dupe_entry(self, oldid, newid):
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
    endsat = [(el, None)]
    for d in el.iterdescendants():
        if not (d.tag == comment_tag):
            if return_tails:
                precedingtails.append([])
                while endsat[-1][1] == d:
                    precedingtails[-1].append(endsat.pop()[0])
                nsib = d.getnext()
                if nsib is None:
                    endsat.append((d, endsat[-1][1]))
                else:
                    endsat.append((d, nsib))
            descendants.append(d)

    if not return_tails:
        return descendants
    else:
        precedingtails.append([])
        while len(endsat) > 0:
            precedingtails[-1].append(endsat.pop()[0])
        return descendants, precedingtails


BaseElement.descendants2 = descendants2


# Version of ancestors that can stop before/after encountering an element
def get_ancestors(el, includeme=False, stopbefore=None, stopafter=None):
    anc = []
    cel = el if includeme else el.getparent()
    while cel is not None and cel != stopbefore:
        anc.append(cel)
        if cel == stopafter:
            break
        cel = cel.getparent()
    return anc


BaseElement.ancestors2 = get_ancestors


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


BaseElement.get_link = get_link_fcn
Style.get_link = get_link_fcn  # type: ignore


# A modified bounding box class
class bbox:
    __slots__ = ("isnull", "x1", "x2", "y1", "y2", "xc", "yc", "w", "h", "sbb")

    def __init__(self, bb):
        self.isnull = bb is None
        if not (self.isnull):
            if len(bb) == 2:  # allow tuple of two points ((x1,y1),(x2,y2))
                bb = [
                    min(bb[0][0], bb[1][0]),
                    min(bb[0][1], bb[1][1]),
                    abs(bb[0][0] - bb[1][0]),
                    abs(bb[0][1] - bb[1][1]),
                ]
            self.x1 = bb[0]
            self.x2 = bb[0] + bb[2]
            self.y1 = bb[1]
            self.y2 = bb[1] + bb[3]
            self.xc = (self.x1 + self.x2) / 2
            self.yc = (self.y1 + self.y2) / 2
            self.w = bb[2]
            self.h = bb[3]
            self.sbb = [self.x1, self.y1, self.w, self.h]  # standard bbox

    def copy(self):
        ret = bbox.__new__(bbox)
        ret.isnull = self.isnull
        if not self.isnull:
            ret.x1 = self.x1
            ret.x2 = self.x2
            ret.y1 = self.y1
            ret.y2 = self.y2
            ret.xc = self.xc
            ret.yc = self.yc
            ret.w = self.w
            ret.h = self.h
            ret.sbb = self.sbb[:]
        return ret

    def transform(self, xform):
        if not (self.isnull) and xform is not None:
            tr1 = xform.apply_to_point([self.x1, self.y1])
            tr2 = xform.apply_to_point([self.x2, self.y2])
            tr3 = xform.apply_to_point([self.x1, self.y2])
            tr4 = xform.apply_to_point([self.x2, self.y1])
            return bbox(
                [
                    min(tr1[0], tr2[0], tr3[0], tr4[0]),
                    min(tr1[1], tr2[1], tr3[1], tr4[1]),
                    max(tr1[0], tr2[0], tr3[0], tr4[0])
                    - min(tr1[0], tr2[0], tr3[0], tr4[0]),
                    max(tr1[1], tr2[1], tr3[1], tr4[1])
                    - min(tr1[1], tr2[1], tr3[1], tr4[1]),
                ]
            )
        else:
            return bbox(None)

    def intersect(self, bb2):
        return (abs(self.xc - bb2.xc) * 2 < (self.w + bb2.w)) and (
            abs(self.yc - bb2.yc) * 2 < (self.h + bb2.h)
        )

    def union(self, bb2):
        if isinstance(bb2, list):
            bb2 = bbox(bb2)
        if not (self.isnull) and not bb2.isnull:
            minx = min([self.x1, self.x2, bb2.x1, bb2.x2])
            maxx = max([self.x1, self.x2, bb2.x1, bb2.x2])
            miny = min([self.y1, self.y2, bb2.y1, bb2.y2])
            maxy = max([self.y1, self.y2, bb2.y1, bb2.y2])
            return bbox([minx, miny, abs(maxx - minx), abs(maxy - miny)])
        elif self.isnull and not bb2.isnull:
            return bbox(bb2.sbb)
        elif not self.isnull and bb2.isnull:
            return bbox(self.sbb)
        else:
            return bbox(None)

    def intersection(self, bb2):
        if isinstance(bb2, list):
            bb2 = bbox(bb2)
        if not (self.isnull):
            minx = max([self.x1, bb2.x1])
            maxx = min([self.x2, bb2.x2])
            miny = max([self.y1, bb2.y1])
            maxy = min([self.y2, bb2.y2])
            return bbox([minx, miny, abs(maxx - minx), abs(maxy - miny)])
        else:
            return bbox(bb2.sbb)

    def __mul__(self, scl):
        return bbox([self.x1 * scl, self.y1 * scl, self.w * scl, self.h * scl])


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
    (inkex.SvgDocumentElement, inkex.Group, inkex.Layer, inkex.ClipPath, inkex.Symbol)
)
grouplike_tags.add(mask_tag)


def bounding_box2(
    el, dotransform=True, includestroke=True, roughpath=False, parsed=False
):
    if not (hasattr(el, "_cbbox")):
        el._cbbox = dict()
    if (dotransform, includestroke, roughpath, parsed) not in el._cbbox:
        try:
            ret = bbox(None)
            if el.tag in ttags:
                ret = el.parsed_text.get_full_extent(parsed=parsed)
            elif el.tag in cpath_support_tags:
                pth = el.cpath
                if len(pth) > 0:
                    sw = ipx(el.cspecified_style.get("stroke-width", "0px"))
                    if el.cspecified_style.get("stroke") is None or not (includestroke):
                        sw = 0

                    if el.tag == line_tag:
                        xs = [ipx(el.get("x1", "0")), ipx(el.get("x2", "0"))]
                        ys = [ipx(el.get("y1", "0")), ipx(el.get("y2", "0"))]
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
                        pth = inkex.Path(inkex.CubicSuperPath(pth)) if anyarc else pth
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

            elif el.tag in grouplike_tags:
                for d in list2(el):
                    dbb = bounding_box2(
                        d,
                        dotransform=False,
                        includestroke=includestroke,
                        roughpath=roughpath,
                        parsed=parsed,
                    )
                    if not (dbb.isnull):
                        ret = ret.union(dbb.transform(d.ctransform))
            elif isinstance(el, (inkex.Image)):
                ret = bbox([ipx(el.get(v, "0")) for v in ["x", "y", "width", "height"]])
            elif isinstance(el, (inkex.Use,)):
                lel = el.get_link("xlink:href")
                if lel is not None:
                    ret = bounding_box2(
                        lel, dotransform=False, roughpath=roughpath, parsed=parsed
                    )

                    # clones have the transform of the link, followed by any xy transform
                    xyt = inkex.Transform(
                        "translate({0},{1})".format(
                            ipx(el.get("x", "0")), ipx(el.get("y", "0"))
                        )
                    )
                    ret = ret.transform(xyt @ lel.ctransform)

            if not (ret.isnull):
                for cm in ["clip-path", "mask"]:
                    clip = el.get_link(cm, llget=True)
                    if clip is not None:
                        cbb = bounding_box2(
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
                        ret = ret.transform(el.ccomposed_transform)
        except:
            # For some reason errors are occurring silently
            import traceback

            inkex.utils.debug(traceback.format_exc())
        el._cbbox[(dotransform, includestroke, roughpath, parsed)] = ret
    return el._cbbox[(dotransform, includestroke, roughpath, parsed)]


def set_cbbox(el, val):
    if val is None and hasattr(el, "_cbbox"):
        delattr(el, "_cbbox")


inkex.BaseElement.cbbox = property(bounding_box2, set_cbbox)
inkex.SvgDocumentElement.cbbox = property(bounding_box2, set_cbbox)

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


# Cached document size function
def document_size(svg):
    if not (hasattr(svg, "_cdocsize")):
        rvb = svg.get_viewbox()
        wstr = svg.get("width")
        hstr = svg.get("height")

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

        align, meetOrSlice = parse_preserve_aspect_ratio(svg.get("preserveAspectRatio"))

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
        nvs = [el for el in list(svg) if isinstance(el, inkex.NamedView)]
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
                self, rawvb, effvb, uuw, uuh, uupx, wunit, hunit, wpx, hpx, xf, yf, pgs
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

            def uutopx(self, v):  # Converts a bounding box specified in uu to pixels
                vo = [
                    (v[0] - self.effvb[0]) * self.uuw,
                    (v[1] - self.effvb[1]) * self.uuh,
                    v[2] * self.uuw,
                    v[3] * self.uuh,
                ]
                return vo

            def pxtouu(self, v):  # Converts a bounding box specified in pixels to uu
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

        svg._cdocsize = DocSize(rvb, vb, uuw, uuh, uupx, wu, hu, wpx, hpx, xf, yf, pgs)
    return svg._cdocsize


def set_cdocsize(svg, si):
    if si is None and hasattr(svg, "_cdocsize"):  # invalidate
        delattr(svg, "_cdocsize")


inkex.SvgDocumentElement.cdocsize = property(document_size, set_cdocsize)


def set_viewbox_fcn(svg, newvb):
    # svg.set_viewbox(vb)
    uuw, uuh, wunit, hunit = (
        svg.cdocsize.uuw,
        svg.cdocsize.uuh,
        svg.cdocsize.wunit,
        svg.cdocsize.hunit,
    )
    svg.set(
        "width",
        str(inkex.units.convert_unit(str(newvb[2] * uuw) + "px", wunit)) + wunit,
    )
    svg.set(
        "height",
        str(inkex.units.convert_unit(str(newvb[3] * uuh) + "px", hunit)) + hunit,
    )
    svg.set("viewBox", " ".join([str(v) for v in newvb]))
    svg.cdocsize = None


inkex.SvgDocumentElement.set_viewbox = set_viewbox_fcn


def standardize_viewbox(svg):
    # Converts viewbox to pixels, removing any non-uniform scaling appropriately
    pgbbs = [pg.bbpx for pg in svg.cdocsize.pgs]
    svg.set("viewBox", " ".join([str(v) for v in svg.cdocsize.effvb]))
    svg.set("width", str(svg.cdocsize.wpx))
    svg.set("height", str(svg.cdocsize.hpx))

    # Update Pages appropriately
    svg.cdocsize = None
    for ii, pg in enumerate(svg.cdocsize.pgs):
        newbbuu = svg.cdocsize.pxtouupgs(pgbbs[ii])
        pg.set("x", str(newbbuu[0]))
        pg.set("y", str(newbbuu[1]))
        pg.set("width", str(newbbuu[2]))
        pg.set("height", str(newbbuu[3]))


inkex.SvgDocumentElement.standardize_viewbox = standardize_viewbox

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
            except (KeyError, AttributeError):
                pass
            svg.iddict.remove(d)
        d.croot = None
    if hasattr(svg, "_cd2"):
        svg.cdescendants2.delel(el)
    inkexdelete(el)


BaseElement.delete = delete_func  # type: ignore

# Insertion
BEinsert = inkex.BaseElement.insert


def insert_func(g, index, el):
    oldroot = el.croot
    newroot = g.croot

    BEinsert(g, index, el)
    el.ccascaded_style = None
    el.cspecified_style = None
    el.ccomposed_transform = None

    # When the root is changing, removing from old dicts and add to new
    # Note that most new elements have their IDs assigned here or in append
    if not oldroot == newroot or el.get("id") is None:
        css = None
        if oldroot is not None:
            oldroot.iddict.remove(el)
            css = oldroot.cssdict.pop(el.get_id(), None)
        el.croot = newroot
        if newroot is not None:
            newroot.iddict.add(el)  # generates an ID if needed
            if css is not None:
                newroot.cssdict[el.get_id()] = css


inkex.BaseElement.insert = insert_func  # type: ignore

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
    if not oldroot == newroot or el.get("id") is None:
        css = None
        if oldroot is not None:
            oldroot.iddict.remove(el)
            css = oldroot.cssdict.pop(el.get_id(), None)
        el.croot = newroot
        if newroot is not None:
            newroot.iddict.add(el)  # generates an ID if needed
            if css is not None:
                newroot.cssdict[el.get_id()] = css


inkex.BaseElement.append = append_func  # type: ignore

# Duplication
clipmasktags = {inkex.addNS("mask", "svg"), inkex.ClipPath.ctag}


def duplicate_func(self):
    # type: (BaseElement) -> BaseElement
    svg = self.croot
    svg.iddict
    svg.cssdict
    # need to generate now to prevent problems in duplicate_fixed (self.addnext(elem) line, no idea why)

    eltail = self.tail
    if eltail is not None:
        self.tail = None
    d = self.copy()
    self.addnext(d)
    d.set_random_id()
    if eltail is not None:
        self.tail = eltail
    # Fix tail bug: https://gitlab.com/inkscape/extensions/-/issues/480

    d.croot = svg  # set now for speed
    self.croot.cssdict.dupe_entry(self.get_id(), d.get_id())
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


BaseElement.duplicate = duplicate_func  # type: ignore

# inkexBaseElement = inkex.BaseElement
# class BaseElementCached(inkexBaseElement):
#     append = append_func
#     duplicate = duplicate_func
# import inspect
# for name, cls in inspect.getmembers(inkex):
#     if inspect.isclass(cls) and inkexBaseElement in cls.__bases__:
#         cls.__bases__ = tuple(BaseElementCached if base is inkexBaseElement else base for base in cls.__bases__)
