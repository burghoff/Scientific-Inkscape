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

# Note that this function modifies its own .inx file by editing the options in the "template"
# parameter and the "template_rem" parameter.

# dflt = {'Arrow': [[{'style': 'overflow:visible', 'id': 'Arrow2Lstart', 'refX': '0.0', 'refY': '0.0', 'orient': 'auto', '{http://www.inkscape.org/namespaces/inkscape}stockid': 'Arrow2Lstart', '{http://www.inkscape.org/namespaces/inkscape}isstock': 'true'}, [{'transform': 'matrix(1.1 0 0 1.1 1.1 0)', 'd': 'M 8.7185878,4.0337352 L -2.2072895,0.016013256 L 8.7185884,-4.0017078 C 6.9730900,-1.6296469 6.9831476,1.6157441 8.7185878,4.0337352 z ', 'style': 'stroke:context-stroke;fill-rule:evenodd;fill:context-stroke;stroke-width:0.62500000;stroke-linejoin:round', 'id': 'path1068'}]], [{'style': 'overflow:visible', 'id': 'Arrow2Lend', 'refX': '0.0', 'refY': '0.0', 'orient': 'auto', '{http://www.inkscape.org/namespaces/inkscape}stockid': 'Arrow2Lend', '{http://www.inkscape.org/namespaces/inkscape}isstock': 'true'}, [{'transform': 'matrix(-1.1 1.34707e-16 -1.34707e-16 -1.1 -1.1 1.34707e-16)', 'd': 'M 8.7185878,4.0337352 L -2.2072895,0.016013256 L 8.7185884,-4.0017078 C 6.9730900,-1.6296469 6.9831476,1.6157441 8.7185878,4.0337352 z ', 'style': 'stroke:context-stroke;fill-rule:evenodd;fill:context-stroke;stroke-width:0.62500000;stroke-linejoin:round', 'id': 'path1071'}]], [{'style': 'overflow:visible', 'id': 'marker1328', 'refX': '0.0', 'refY': '0.0', 'orient': 'auto', '{http://www.inkscape.org/namespaces/inkscape}stockid': 'Arrow2Lend', '{http://www.inkscape.org/namespaces/inkscape}isstock': 'true'}, [{'transform': 'matrix(-1.1 1.34707e-16 -1.34707e-16 -1.1 -1.1 1.34707e-16)', 'd': 'M 8.7185878,4.0337352 L -2.2072895,0.016013256 L 8.7185884,-4.0017078 C 6.9730900,-1.6296469 6.9831476,1.6157441 8.7185878,4.0337352 z ', 'style': 'stroke:context-stroke;fill-rule:evenodd;fill:context-stroke;stroke-width:0.62500000;stroke-linejoin:round', 'id': 'path1326'}]]], 'Triangle': [[{'style': 'overflow:visible', 'id': 'TriangleInL', 'refX': '0.0', 'refY': '0.0', 'orient': 'auto', '{http://www.inkscape.org/namespaces/inkscape}stockid': 'TriangleInL', '{http://www.inkscape.org/namespaces/inkscape}isstock': 'true'}, [{'transform': 'scale(-0.8, -0.8)', 'style': 'fill-rule:evenodd;fill:context-stroke;stroke:context-stroke;stroke-width:1.0pt', 'd': 'M 5.77,0.0 L -2.88,5.0 L -2.88,-5.0 L 5.77,0.0 z ', 'id': 'path1183'}]], [{'style': 'overflow:visible', 'id': 'marker1395', 'refX': '0.0', 'refY': '0.0', 'orient': 'auto', '{http://www.inkscape.org/namespaces/inkscape}stockid': 'TriangleOutL', '{http://www.inkscape.org/namespaces/inkscape}isstock': 'true'}, [{'transform': 'scale(0.8, 0.8)', 'style': 'fill-rule:evenodd;fill:context-stroke;stroke:context-stroke;stroke-width:1.0pt', 'd': 'M 5.77,0.0 L -2.88,5.0 L -2.88,-5.0 L 5.77,0.0 z ', 'id': 'path1393'}]], [{'style': 'overflow:visible', 'id': 'TriangleOutL', 'refX': '0.0', 'refY': '0.0', 'orient': 'auto', '{http://www.inkscape.org/namespaces/inkscape}stockid': 'TriangleOutL', '{http://www.inkscape.org/namespaces/inkscape}isstock': 'true'}, [{'transform': 'scale(0.8, 0.8)', 'style': 'fill-rule:evenodd;fill:context-stroke;stroke:context-stroke;stroke-width:1.0pt', 'd': 'M 5.77,0.0 L -2.88,5.0 L -2.88,-5.0 L 5.77,0.0 z ', 'id': 'path1192'}]]]}
dflt = {
    "Arrow": [
        [
            {
                "style": "overflow:visible",
                "refX": "0.0",
                "refY": "0.0",
                "orient": "auto",
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "Arrow2Mstart",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "transform": "scale(0.6, 0.6)",
                    "d": "M 8.7185878,4.0337352 L -2.2072895,0.016013256 L 8.7185884,-4.0017078 C 6.9730900,-1.6296469 6.9831476,1.6157441 8.7185878,4.0337352 z ",
                    "style": "stroke:context-stroke;fill-rule:evenodd;fill:context-stroke;stroke-width:0.62500000;stroke-linejoin:round",
                    "id": "path961",
                }
            ],
        ],
        [
            {
                "style": "overflow:visible",
                "refX": "0.0",
                "refY": "0.0",
                "orient": "auto",
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "Arrow2Mend",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "transform": "scale(-0.6, -0.6)",
                    "d": "M 8.7185878,4.0337352 L -2.2072895,0.016013256 L 8.7185884,-4.0017078 C 6.9730900,-1.6296469 6.9831476,1.6157441 8.7185878,4.0337352 z ",
                    "style": "stroke:context-stroke;fill-rule:evenodd;fill:context-stroke;stroke-width:0.62500000;stroke-linejoin:round",
                    "id": "path964",
                }
            ],
        ],
        [
            {
                "style": "overflow:visible",
                "refX": "0.0",
                "refY": "0.0",
                "orient": "auto",
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "Arrow2Mend",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "transform": "scale(-0.6, -0.6)",
                    "d": "M 8.7185878,4.0337352 L -2.2072895,0.016013256 L 8.7185884,-4.0017078 C 6.9730900,-1.6296469 6.9831476,1.6157441 8.7185878,4.0337352 z ",
                    "style": "stroke:context-stroke;fill-rule:evenodd;fill:context-stroke;stroke-width:0.62500000;stroke-linejoin:round",
                    "id": "path1354",
                }
            ],
        ],
    ],
    "Triangle": [
        [
            {
                "style": "overflow:visible",
                "refX": "0.0",
                "refY": "0.0",
                "orient": "auto",
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "TriangleInM",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "transform": "scale(-0.4, -0.4)",
                    "style": "fill-rule:evenodd;fill:context-stroke;stroke:context-stroke;stroke-width:1.0pt",
                    "d": "M 5.77,0.0 L -2.88,5.0 L -2.88,-5.0 L 5.77,0.0 z ",
                    "id": "path1073",
                }
            ],
        ],
        [
            {
                "style": "overflow:visible",
                "refX": "0.0",
                "refY": "0.0",
                "orient": "auto",
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "TriangleOutM",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "transform": "scale(0.4, 0.4)",
                    "style": "fill-rule:evenodd;fill:context-stroke;stroke:context-stroke;stroke-width:1.0pt",
                    "d": "M 5.77,0.0 L -2.88,5.0 L -2.88,-5.0 L 5.77,0.0 z ",
                    "id": "path1082",
                }
            ],
        ],
        [
            {
                "style": "overflow:visible",
                "refX": "0.0",
                "refY": "0.0",
                "orient": "auto",
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "TriangleOutM",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "transform": "scale(0.4, 0.4)",
                    "style": "fill-rule:evenodd;fill:context-stroke;stroke:context-stroke;stroke-width:1.0pt",
                    "d": "M 5.77,0.0 L -2.88,5.0 L -2.88,-5.0 L 5.77,0.0 z ",
                    "id": "path1213",
                }
            ],
        ],
    ],
    "Distance": [
        [
            {
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "DistanceStart",
                "orient": "auto",
                "refY": "0.0",
                "refX": "0.0",
                "id": "DistanceStart",
                "style": "overflow:visible",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "id": "path2306",
                    "d": "M 0,0 L 2,0",
                    "style": "fill:none;stroke:context-fill;stroke-width:1.15;stroke-linecap:square",
                },
                {
                    "id": "path2302",
                    "d": "M 0,0 L 13,4 L 9,0 13,-4 L 0,0 z ",
                    "style": "fill:context-stroke;fill-rule:evenodd;stroke:none",
                },
                {
                    "id": "path2304",
                    "d": "M 0,-4 L 0,40",
                    "style": "fill:none;stroke:context-stroke;stroke-width:1;stroke-linecap:square",
                },
            ],
        ],
        [
            {
                "style": "overflow:visible",
                "id": "StopL",
                "refX": "0.0",
                "refY": "0.0",
                "orient": "auto",
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "StopL",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "transform": "scale(0.8, 0.8)",
                    "style": "fill:none;fill-opacity:0.75000000;fill-rule:evenodd;stroke:context-stroke;stroke-width:1.0pt",
                    "d": "M 0.0,5.65 L 0.0,-5.65",
                    "id": "path2127",
                }
            ],
        ],
        [
            {
                "{http://www.inkscape.org/namespaces/inkscape}stockid": "DistanceEnd",
                "orient": "auto",
                "refY": "0.0",
                "refX": "0.0",
                "id": "DistanceEnd",
                "style": "overflow:visible",
                "{http://www.inkscape.org/namespaces/inkscape}isstock": "true",
            },
            [
                {
                    "id": "path2316",
                    "d": "M 0,0 L -2,0",
                    "style": "fill:none;stroke:context-fill;stroke-width:1.15;stroke-linecap:square",
                },
                {
                    "id": "path2312",
                    "d": "M 0,0 L -13,4 L -9,0 -13,-4 L 0,0 z ",
                    "style": "fill:context-stroke;fill-rule:evenodd;stroke:none",
                },
                {
                    "id": "path2314",
                    "d": "M 0,-4 L 0,40",
                    "style": "fill:none;stroke:context-stroke;stroke-width:1;stroke-linecap:square",
                },
            ],
        ],
    ],
}

import dhelpers as dh
import inkex
from inkex import (
    TextElement,
    FlowRoot,
    FlowPara,
    Tspan,
    TextPath,
    Rectangle,
    addNS,
    Transform,
    PathElement,
    Line,
    Rectangle,
    Path,
    Vector2d,
    Use,
    NamedView,
    Defs,
    Metadata,
    ForeignObject,
    Group,
    FontFace,
    StyleElement,
    StyleSheets,
    SvgDocumentElement,
    ShapeElement,
    BaseElement,
    FlowSpan,
    Ellipse,
    Circle,
)

import os, sys

def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))


dispprofile = False


class FavoriteMarkers(inkex.EffectExtension):
    #    def document_path(self):
    #        return 'test'

    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--template", type=int, default=1, help="Template")

        pars.add_argument(
            "--smarker", type=inkex.Boolean, default=False, help="Start marker?"
        )
        pars.add_argument(
            "--mmarker", type=inkex.Boolean, default=False, help="Mid marker?"
        )
        pars.add_argument(
            "--emarker", type=inkex.Boolean, default=False, help="End marker?"
        )
        pars.add_argument("--size", type=float, default=100, help="Size (%)")

        pars.add_argument(
            "--addt", type=inkex.Boolean, default=True, help="Add template?"
        )
        pars.add_argument(
            "--template_name", type=str, default="untitled", help="New template name"
        )
        pars.add_argument(
            "--remt", type=inkex.Boolean, default=True, help="Remove template?"
        )
        pars.add_argument(
            "--template_rem", type=int, default=1, help="Template to remove"
        )

    def get_marker_props(self, murl):
        if murl is not None and murl != "" and murl != "none":
            mkr = self.svg.getElementById(murl.strip("#url(").strip(")"))
            mkratt = dict()
            for att in mkr.attrib:
                if att != "id":
                    mkratt[att] = mkr.get(att)
            patts = []
            if len(mkr.getchildren()) > 0:
                if isinstance(mkr.getchildren()[0], (Group)):
                    pparent = mkr.getchildren()[0]
                else:
                    pparent = mkr
                for k in pparent.getchildren():
                    if isinstance(k, (PathElement)):
                        patt = dict()
                        for att in k.attrib:
                            patt[att] = k.get(att)
                        patts.append(patt)
                return [mkratt, patts]
            else:
                return None
        else:
            return None

    def set_marker_props(self, el, mkrname, mtype, mkrdat):
        if mkrdat is not None:
            newname = (mkrname + mtype).translate({ord(c): None for c in " \n\t\r"})
            # strip white space
            mysize = self.options.size / 100
            existing = [
                v for v in self.svg.defs.descendants2() if newname in v.get_id()
            ]
            previousmkr = None
            for eel in existing:
                if len(eel.getchildren()) > 0 and isinstance(
                    eel.getchildren()[0], (Group)
                ):
                    trn = Transform(eel.getchildren()[0].get("transform"))
                    if abs(trn.a - mysize) < 0.01 and abs(trn.d - mysize) < 0.01:
                        previousmkr = eel

            if previousmkr is None:
                mkratt = mkrdat[0]
                patt = mkrdat[1]
                m = inkex.elements._groups.Marker()

                for att in mkratt.keys():
                    if att != "id":
                        m.set(att, mkratt[att])
                g = Group()
                m.append(g)
                g.set("transform", "scale(" + str(mysize) + ")")
                for ii in range(len(patt)):
                    p = PathElement()
                    for att in patt[ii].keys():
                        if att != "id":
                            p.set(att, patt[ii][att])
                    g.append(p)
                self.svg.defs.append(m)
                m.set_random_id(prefix=newname)
            else:
                m = previousmkr
            el.cstyle["marker-" + mtype] = "url(#" + m.get_id() + ")"
        else:
            el.cstyle["marker-" + mtype] = None

        # dh.debug(mkrname+mtype)
        # dh.debug(mkrdat)

    def effect(self):
        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey

            pr = cProfile.Profile()
            pr.enable()

        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        # should work with both v1.0 and v1.1
        sel = [v for el in sel for v in el.descendants2()]
        import pickle, os

        fmsettings = os.path.abspath(
            os.path.join(get_script_path(), "favorite_markers.settings")
        )
        try:
            f = open(fmsettings, "rb")
        except:
            f = open(fmsettings, "wb")
            pickle.dump(dflt, f)
            f.close()
            f = open(fmsettings, "rb")
        s = pickle.load(f)
        f.close()

        # dh.debug(s)
        if self.options.tab == "addremove":
            if self.options.addt:
                sel = [
                    x
                    for x in sel
                    if isinstance(
                        x,
                        (
                            inkex.PathElement,
                            inkex.Line,
                            inkex.Polyline,
                            inkex.Rectangle,
                            inkex.Circle,
                            inkex.Ellipse,
                        ),
                    )
                ]
                sty = sel[0].cspecified_style

                ms = self.get_marker_props(sty.get("marker-start"))
                mm = self.get_marker_props(sty.get("marker-mid"))
                me = self.get_marker_props(sty.get("marker-end"))
                s[self.options.template_name] = [ms, mm, me]
            if self.options.remt:
                templates = list(s.keys())
                if self.options.template_rem < len(templates):
                    del s[templates[self.options.template_rem]]
            f = open(fmsettings, "wb")
            pickle.dump(s, f)
            f.close()

            fminx = os.path.abspath(
                os.path.join(get_script_path(), "favorite_markers.inx")
            )
            f = open(fminx)
            inxd = f.read()
            f.close()

            opts = ""
            ts = list(s.keys())
            for ii in range(len(ts)):
                opts += '\n<option value="' + str(ii) + '">' + ts[ii] + "</option>"
            ss1 = '<param name="template" type="optiongroup" appearance="combo" gui-text="Template">'
            ss1loc = inxd.find(ss1)
            ss1srt = ss1loc + len(ss1)
            ss1end = inxd[ss1loc:].find("</param>") + ss1loc
            ss2 = '<param name="template_rem" type="optiongroup" appearance="combo" gui-text="Template to remove">'
            ss2loc = inxd.find(ss2)
            ss2srt = ss2loc + len(ss2)
            ss2end = inxd[ss2loc:].find("</param>") + ss2loc
            newinx = inxd[0:ss1srt] + opts + inxd[ss1end:ss2srt] + opts + inxd[ss2end:]
            f = open(fminx, "w")
            inxd = f.write(newinx)
            f.close()

            dh.idebug(
                "Templates successfully updated! Update will take effect when Inkscape is restarted."
            )
        else:
            for el in sel:
                if isinstance(
                    el,
                    (
                        inkex.PathElement,
                        inkex.Line,
                        inkex.Polyline,
                        inkex.Rectangle,
                        inkex.Circle,
                        inkex.Ellipse,
                    ),
                ):
                    ts = list(s.keys())
                    tname = ts[self.options.template]
                    tval = s[tname]
                    if self.options.smarker:
                        self.set_marker_props(el, "FM" + tname, "start", tval[0])
                    else:
                        self.set_marker_props(el, "FM" + tname, "start", None)
                    if self.options.mmarker:
                        self.set_marker_props(el, "FM" + tname, "mid", tval[1])
                    else:
                        self.set_marker_props(el, "FM" + tname, "mid", None)
                    if self.options.emarker:
                        self.set_marker_props(el, "FM" + tname, "end", tval[2])
                    else:
                        self.set_marker_props(el, "FM" + tname, "end", None)

        # pickle.dump(s,open(os.path.join(get_script_path(),'ae_settings.p'),'wb'));

        # for el in sela:
        #     if
        #     dh.debug(el.get_id())
        #     dh.debug(bb[el.get_id()]);

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())


if __name__ == "__main__":
    dh.Run_SI_Extension(FavoriteMarkers(), "Favorite markers")
