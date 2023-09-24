#!/usr/bin/env python
# coding=utf-8
#
# Copyright (c) 2023 David Burghoff <burghoff@utexas.edu>
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

# For SI we override Inkex's Style with a modified version, Style0
# To do this we import Style0, then replace inkex.Style with it
import Style0
inkex.Style = Style0.Style0

# Next we make sure we have the text submodule. If not, we add it from SI
import sys
if not hasattr(inkex,'text'):
    import importlib
    sys.modules['inkex.text'] = importlib.import_module('text')
    

from inkex import Style
import inkex.text.speedups, inkex.text.cache  # noqa
from inkex.text.cache import tags, grouplike_tags, bb2_support_tags, bounding_box2, bbox, ipx
from inkex.text.utils import (Get_Composed_Width,
                              unique, object_to_path,isrectangle,
                              Get_Binary_Loc,Get_Bounding_Boxes,subprocess_repeat)


from inkex import Tspan, Transform, Path, PathElement, BaseElement
from applytransform_mod import fuseTransform
import lxml, math, re, os, random
from functools import lru_cache

# Returns non-comment children
def list2(el):
    return [k for k in list(el) if not(k.tag == ctag)]

EBget = lxml.etree.ElementBase.get;
EBset = lxml.etree.ElementBase.set;

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
        

# Replace an element with another one
# Puts it in the same location, update the cache dicts
def replace_element(el1, el2):
    # replace el1 with el2
    myp = el1.getparent()
    myi = list(myp).index(el1)
    myp.insert(myi + 1, el2)

    newid = el1.get_id()
    oldid = el2.get_id()

    el1.delete()
    el2.set_id(newid)
    el2.croot.iddict.add(el2)
    el2.croot.cssdict.dupe_entry(oldid, newid)


# For style components that are a list (stroke-dasharray), calculate
# the true size reported by Inkscape, inheriting any styles/transforms
def listsplit(x):
    # split list on commas or spaces
    return [ipx(v) for v in re.split('[ ,]', x) if v]
def Get_Composed_List(el, comp, nargout=1):
    cs = el.cspecified_style
    ct = el.ccomposed_transform
    sc = cs.get(comp)
    if sc == "none":
        return "none"
    elif sc is not None:
        sv = listsplit(sc)
        sf = math.sqrt(abs(ct.a * ct.d - ct.b * ct.c))
        sv = [x * sf for x in sv]
        if nargout == 1:
            return sv
        else:
            return sv, sf
    else:
        if nargout == 1:
            return None
        else:
            return None, None


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


# Get points of a path, element, or rectangle in the global coordinate system
def get_points(el, irange=None):
    pth = el.cpath.to_absolute()
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
    if el.tag == usetag:
        useel = el.get_link("xlink:href")
        if useel is not None:
            d = useel.duplicate()

            # xy translation treated as a transform (applied first, then clip/mask, then full xform)
            tx = EBget(el,"x")
            ty = EBget(el,"y")
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
            for k in d.descendants2()[1:]:
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



# unungroupable = (NamedView, Defs, Metadata, ForeignObject, lxml.etree._Comment)
unungroupable = tags((inkex.NamedView, inkex.Defs, inkex.Metadata, inkex.ForeignObject))
ctag = lxml.etree.Comment
unungroupable.add(ctag)

def ungroup(groupel):
    # Ungroup a group, preserving style, clipping, and masking
    # Remove any comments

    if groupel.croot is not None:
        gparent = groupel.getparent()
        gindex = gparent.index(groupel)  # group's location in parent
        
        gtransform = groupel.ctransform
        gclip = groupel.get_link('clip-path',llget=True)
        gmask = groupel.get_link('mask',llget=True)
        gstyle = groupel.ccascaded_style

        for el in reversed(list(groupel)):
            if el.tag == ctag:  # remove comments
                groupel.remove(el)
            if not (el.tag in unungroupable):
                clippedout = compose_all(el, gclip, gmask, gtransform, gstyle)
                if clippedout:
                    el.delete()
                else:
                    gparent.insert(gindex + 1, el)
                    # places above

        if len(groupel) == 0:
            groupel.delete()

# Group a list of elements, placing the group in the location of the first element            
def group(el_list,moveTCM=False):
    # g = el_list[0].croot.new_element(inkex.Group)
    g = inkex.Group()
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



# For composing a group's properties onto its children (also group-like objects like Uses)
Itmat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
def compose_all(el, clip, mask, transform, style):
    if style is not None:  # style must go first since we may change it with CSS
        mysty = el.ccascaded_style
        compsty = style + mysty
        compsty["opacity"] = str(
            float(mysty.get("opacity", "1")) * float(style.get("opacity", "1"))
        )  # opacity accumulates at each layer
        el.cstyle = compsty

    if clip is not None:
        # idebug([el.get_id(),clipurl])
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

    mycss = cssdict.get(el.get_id())
    if mycss is not None:
        if mycss.get(cm) is not None and mycss.get(cm) != el.get(cm):
            svg = el.croot
            if not (hasattr(svg, "stylesheet_entries")):
                svg.stylesheet_entries = dict()
            svg.stylesheet_entries["#" + el.get_id()] = cm + ":" + el.get(cm)
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
        return Path("M {},{} h {} v {} h {} Z".format(x1c, y1c, w, h, -w))
    else:
        return Path("")


usetag = inkex.Use.ctag
def merge_clipmask(node, newclip, mask=False):
    # Modified from Deep Ungroup
    def compose_clips(el, ptha, pthb):
        newpath = intersect_paths(ptha, pthb)
        isempty = str(newpath) == ""

        if not (isempty):
            myp = el.getparent()
            # p = el.croot.new_element(PathElement, el)
            p = PathElement()
            myp.append(p)
            p.set("d", newpath)
        el.delete()
        return isempty  # if clipped out, safe to delete element

    if newclip is not None:
        svg = node.croot
        cmstr = "mask" if mask else "clip-path"

        if node.ctransform is not None:
            # Clip-paths on nodes with a transform have the transform
            # applied to the clipPath as well, which we don't want.
            # Duplicate the new clip and apply node's inverse transform to its children.
            if newclip is not None:
                d = newclip.duplicate()
                if not (hasattr(svg, "newclips")):
                    svg.newclips = []
                svg.newclips.append(d)  # for later cleanup
                for k in list(d):
                    compose_all(k, None, None, -node.ctransform, None)
                # newclipurl = d.get_id(2)
                newclip = d

        if newclip is not None:
            for k in list(newclip):
                if k.tag == usetag:
                    k = unlink2(k)
        oldclip = node.get_link(cmstr,llget=True)
        if oldclip is not None:
            # Existing clip is replaced by a duplicate, then apply new clip to children of duplicate
            for k in list(oldclip):
                if k.tag == usetag:
                    k = unlink2(k)

            d = oldclip.duplicate()
            if not (hasattr(svg, "newclips")):
                svg.newclips = []
            svg.newclips.append(d)  # for later cleanup
            node.set(cmstr, d.get_id(2))

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
            node.set(cmstr, newclip.get_id(2))
            cout = False

        return cout

            
# A cached list of all descendants of an svg in order
# Currently only handles deletions appropriately
class dtree():
    def __init__(self,svg):
        ds, pts = svg.descendants2(True)
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


masktag = inkex.addNS('mask','svg')
svgtag = inkex.SvgDocumentElement.ctag

unrendered = tags((inkex.NamedView, inkex.Defs, inkex.Metadata, inkex.ForeignObject, inkex.Guide,
              inkex.ClipPath,inkex.StyleElement,Tspan,inkex.FlowRegion,inkex.FlowPara))
unrendered.update({masktag,inkex.addNS('RDF','rdf'),   inkex.addNS('Work','cc'),
                          inkex.addNS('format','dc'), inkex.addNS('type','dc')})
# Determine if object has a bbox
@lru_cache(maxsize=None)    
def hasbbox(el):
    myp = el.getparent();
    if myp is None:
        return el.tag == svgtag
    else:
        return el.tag not in unrendered if hasbbox(myp) else False

# Determine if object itself is drawn
@lru_cache(maxsize=None)     
def isdrawn(el):
    return el.tag not in grouplike_tags and hasbbox(el) and el.cspecified_style.get('display')!='none'

# A wrapper that replaces Get_Bounding_Boxes with Pythonic calls only if possible
def BB2(slf,els=None,forceupdate=False,roughpath=False,parsed=False):
    if els is None:
        els = slf.svg.descendants2();
    if all([d.tag in bb2_support_tags or not(hasbbox(d)) for d in els]):
        # All descendants of all els in the list               
        allds = set()
        for el in els:
            if el not in allds: # so we're not re-descendants2ing
                allds.update(el.descendants2())
        tels = [d for d in unique(allds) if isinstance(d,(inkex.TextElement,inkex.FlowRoot))]
        
        if len(tels)>0:
            if forceupdate:
                if hasattr(slf.svg, '_char_table'):
                    delattr(slf.svg,'_char_table')
                for d in els:
                    d.cbbox = None
                    if hasattr(d, "_parsed_text"):
                        delattr(d,'_parsed_text')
            if not hasattr(slf.svg, '_char_table'):
                from inkex.text import TextParser                    # noqa
                slf.svg.make_char_table(els=tels)
                pts = [TextParser.get_parsed_text(el) for el in tels]
                TextParser.ParsedTextList(pts).precalcs()
        ret = inkex.OrderedDict()
        for d in els:
            if d.tag in bb2_support_tags and hasbbox(d):
                mbbox = bounding_box2(d,roughpath=roughpath,parsed=parsed)
                if not(mbbox.isnull):
                    ret[d.get_id()] = mbbox.sbb
    else:
        import tempfile
        with tempfile.TemporaryFile() as temp:
            tname = os.path.abspath(temp.name);
            overwrite_svg(slf.svg, tname)
            ret = Get_Bounding_Boxes(filename=tname, svg=slf.svg)

    return ret

# For diagnosing BB2
def Check_BB2(slf):
    bb2 = BB2(slf)
    HIGHLIGHT_STYLE = "fill:#007575;fill-opacity:0.4675"  # mimic selection
    for el in slf.svg.descendants2():
        if el.get_id() in bb2 and not el.tag in grouplike_tags:
            bb = bbox(bb2[el.get_id()]);
            # bb = bbox(bb2[el.get_id()])*(1/slf.svg.cscale);
            r = inkex.Rectangle()
            r.set('mysource',el.get_id())
            r.set('x',bb.x1)
            r.set('y',bb.y1)
            r.set('height',bb.h)
            r.set('width', bb.w)
            r.set("style", HIGHLIGHT_STYLE)
            el.croot.append(r)



# Vectorized calculation of bbox intersection bools
# Returns a matrix sized len(bbs) x len(bb2s)
def bb_intersects(bbs,bb2s=None):
    if bb2s is None:
        bb2s = bbs
    import numpy as np
    
    if len(bbs)==0 or len(bb2s)==0:
        return np.zeros((len(bbs), len(bb2s)), dtype=bool)
    else:
        xc1, yc1, wd1, ht1 = np.array([(bb.xc, bb.yc, bb.w, bb.h) for bb in bbs]).T
        xc2, yc2, wd2, ht2 = np.array([(bb.xc, bb.yc, bb.w, bb.h) for bb in bb2s]).T
        return np.logical_and(
            (abs(xc1.reshape(-1, 1) - xc2) * 2 < (wd1.reshape(-1, 1) + wd2)),
            (abs(yc1.reshape(-1, 1) - yc2) * 2 < (ht1.reshape(-1, 1) + ht2)),
        )

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
    # idebug(inkex)
    import inkex.command # needed for a weird bug in v1.1
    inkex.command.write_svg(svg, fileout)

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
                return input_list.get_id()
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
    
    
# style atts that could have urls
urlatts = ["fill", "stroke", "clip-path", "mask", "filter",
            "marker-start", "marker-mid", "marker-end", "marker"]

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
        return el.tag in prune or (el.getparent()==svg.cdefs and el.tag not in exclude)
    
    xlink = [inkex.addNS("href", "xlink"),"href"]
    attids = {sa : dict() for sa in urlatts}
    xlinks = dict()

    def miterdescendants(el):
        yield el
        for d in el.iterdescendants():
            yield d
    
    # Make dicts of all url-containing style atts and xlinks
    for d in svg.cdescendants2.ds:
        for attName in d.attrib.keys():
            if attName in urlatts:
                if d.attrib[attName].startswith('url'):
                    attids[attName][d.get_id()] = d.attrib[attName][5:-1]
            elif attName in xlink:
                if d.attrib[attName].startswith('#'):
                    xlinks[d.get_id()] = d.attrib[attName][1:]
            elif attName=='style':
                if 'url' in d.attrib[attName]:
                    sty = Style(d.attrib[attName])
                    for an2 in sty.keys():
                        if an2 in urlatts:
                            if sty[an2].startswith('url'):
                                attids[an2][d.get_id()] = sty[an2][5:-1] 

    deletedsome = True
    while deletedsome:
        allurls = set([v for sa in urlatts for v in attids[sa].values()] + list(xlinks.values()))
        # sets much faster than lists for membership testing
        deletedsome = False
        for el in svg.cdescendants2.ds:
            if should_prune(el):
                eldids = [dv.get_id() for dv in svg.cdescendants2.iterel(el)]
                if not(any([idv in allurls for idv in eldids])):
                    el.delete()
                    deletedsome = True  
                    for did in eldids:
                        for anm in urlatts:
                            if did in attids[anm]:
                                del attids[anm][did]
                        if did in xlinks:
                            del xlinks[did]

    


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
            el.cstyle["stroke-dasharray"]=str([sdv / sf for sdv in sd]).strip("[").strip("]")
            # fix dash

# Delete and prune empty ancestor groups
def deleteup(el):
    myp = el.getparent()
    el.delete()
    if myp is not None:
        if not len(myp): # faster than getting children
            deleteup(myp)

# Combines a group of path-like elements
def combine_paths(els, mergeii=0):
    pnew = Path()
    si = []
    # start indices
    for el in els:
        pth = el.cpath.to_absolute().transform(el.ccomposed_transform)
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
    ndefs = [el for el in list(svg) if not (el.tag in unungroupable)]
    return [v for el in ndefs for v in el.descendants2()]



# Get document location or prompt
def Get_Current_File(ext,msgstr):
    tooearly = inkex.ivp[0] <= 1 and inkex.ivp[1] < 1
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



masktag = inkex.addNS('mask','svg')
def isMask(el):
    return el.tag == masktag

# cprofile tic and toc
def ctic():
    import cProfile
    global pr
    pr = cProfile.Profile()
    pr.enable()
def ctoc():
    import io, pstats
    global pr
    pr.disable()
    s = io.StringIO()
    sortby = pstats.SortKey.CUMULATIVE
    profiledir = os.path.dirname(os.path.abspath(__file__))
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
    with open(ppath, "w") as f:
        f.write(result)

def Run_SI_Extension(effext,name):
    Version_Check(name)
    
    def run_and_cleanup():
        effext.run()
        flush_stylesheet_entries(effext.svg)
    
    alreadyran = False
    lprofile = os.getenv("LINEPROFILE") == "True"
    batexists = os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),'cprofile open.bat'))
    cprofile = batexists if not lprofile else False
    if cprofile or lprofile:
        profiledir = get_script_path()
        if cprofile:
            ctic()
        if lprofile:
            try:
                from line_profiler import LineProfiler
                lp = LineProfiler()
                from inkex.text import TextParser
                import RemoveKerning
                from inspect import getmembers, isfunction, isclass, getmodule
                import pango_renderer
    
                fns = []
                for m in [sys.modules[__name__], TextParser, RemoveKerning, Style, pango_renderer,
                          inkex.transforms, getmodule(effext), inkex.text.speedups]:
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
                lp.add_function(ipx.__wrapped__)
                lp.add_function(TextParser.Character_Table.true_style.__wrapped__)
                lp.add_function(inkex.text.speedups.transform_to_matrix.__wrapped__)
                   
                lp(run_and_cleanup)()
                import io
                stdouttrap = io.StringIO()
                lp.dump_stats(os.path.abspath(os.path.join(profiledir, "lprofile.prof")))
                lp.print_stats(stdouttrap)
    
                ppath = os.path.abspath(os.path.join(profiledir, "lprofile.csv"))
                result = stdouttrap.getvalue()
                with open(ppath, "w", encoding="utf-8") as f:
                    f.write(result)
                
                # Copy lprofile.csv to the profiles subdirectory
                profiles_dir = os.path.join(os.path.dirname(ppath), 'profiles')
                if not os.path.exists(profiles_dir):
                    os.makedirs(profiles_dir)
                from datetime import datetime
                import shutil
                timestamp = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
                new_filename = f'lprofile_{timestamp}.csv'
                dst_path = os.path.join(profiles_dir, new_filename)
                shutil.copy2(ppath, dst_path)
                
                alreadyran = True
            except ImportError:
                pass

    if not(alreadyran):
        try:
            run_and_cleanup()
        except lxml.etree.XMLSyntaxError:
            try:
                # Try getting Inkscape to write a new clean copy
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
                try:
                    run_and_cleanup()
                except lxml.etree.XMLSyntaxError:
                    # Try removing problematic bytes
                    with open(s.options.input_file, 'rb') as f:
                        bytes_content = f.read()
                    cleaned_content = bytes_content.decode('utf-8', errors='ignore')
                    nfin = s.options.input_file.strip('.svg')+'_tmp.svg'
                    with open(nfin, 'w', encoding='utf-8') as f:
                        f.write(cleaned_content)
                    os.remove(s.options.input_file)
                    os.rename(tmpname,s.options.input_file)
                    run_and_cleanup()
            except:
                inkex.utils.errormsg(
                    "Error reading file! Extensions can only run on SVG files.\n\nIf this is a file imported from another format, try saving as an SVG and restarting Inkscape. Alternatively, try pasting the contents into a new document."
                )
    if cprofile:
        ctoc()
    write_debug()   
    
    # Display accumulated caller info if any
    # from inkex.transforms import callinfo
    global callinfo
    try:
        callinfo
    except:
        callinfo = dict();
    sorted_items = sorted(callinfo.items(), key=lambda x: x[1], reverse=True)
    for key, value in sorted_items:
        idebug(f"{key}: {value}")

# Give early versions of Style a .to_xpath function
def to_xpath_func(sty):
    if inkex.ivp[0] <= 1 and inkex.ivp[1] < 2:
    # pre-1.2: use v1.1 version of to_xpath from inkex.Style
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
Style.to_xpath = to_xpath_func
inkex.Style.to_xpath  = to_xpath_func


def Version_Check(caller):
    siv = "v1.3.1"  # Scientific Inkscape version
    maxsupport = "1.3.1"
    minsupport = "1.1.0"

    logname = "Log.txt";
    NFORM = 200

    maxsupp = inkex.vparse(maxsupport)
    minsupp = inkex.vparse(minsupport)

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
    prevvp = [inkex.vparse(dv[-6:]) for dv in d]
    if (inkex.ivp[0] < minsupp[0] or inkex.ivp[1] < minsupp[1]) and not (inkex.ivp in prevvp):
        msg = (
            "For best results, Scientific Inkscape requires Inkscape version "
            + minsupport
            + " or higher. "
            + "You are running an older version—all features may not work as expected.\n\nThis is a one-time message.\n\n"
        )
        inkex.utils.errormsg(msg)
    if (inkex.ivp[0] > maxsupp[0] or inkex.ivp[1] > maxsupp[1]) and not (inkex.ivp in prevvp):
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
        dt + " Running " + caller + " " + siv + ", Inkscape v" + inkex.__version__ + "\n"
    )

    if len(d) > NFORM:
        d = d[-NFORM:]
        if not (displayedform):
            sif3 = "dt9mt3Br6"
            sif1 = "https://forms.gle/"
            sif2 = "RS6HythP"
            msg = (
                f"You have run Scientific Inkscape extensions over {NFORM} times! Thank you for being such a dedicated user!"
                "\n\nBuilding and maintaining Scientific Inkscape is a time-consuming job,"
                " and I have no real way of tracking the number of active users. For reporting purposes, I would greatly "
                "appreciate it if you could sign my guestbook to indicate that you use Scientific Inkscape. "
                f"It is located at\n\n{sif1}{sif2}{sif3}"
                "\n\nPlease note that this is a one-time message. "
                "You will never get this message again, so please copy the URL before you click OK.\n\n"
            )
            inkex.utils.errormsg(msg)
        d.append("Displayed form screen")

    try:
        f = open(logname, "w")
        f.write("".join(d))
        f.close()
    except:
        err_msg = (
            "Error: You do not have write access to the directory where the Scientific Inkscape "
            "extensions are installed. You may have not installed them in the correct location. "
            "\n\nMake sure you install them in the User Extensions directory, not the Inkscape Extensions "
            "directory."
        )
        inkex.utils.errormsg(err_msg)
        quit()
