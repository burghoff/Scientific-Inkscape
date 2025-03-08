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

EXTENT = 0.5
# how far the rectangle should extend from the text, in units of font size
OPACITY = 0.75
# how opaque it is (0.0-1.0)
STDDEV = 0.5
# standard deviation of the Gaussian blur as fraction of EXTENT

import dhelpers as dh
import inkex
dispprofile = False


class TextGhoster(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")

    def effect(self):
        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey

            pr = cProfile.Profile()
            pr.enable()

        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        # should work with both v1.0 and v1.1
        gs = []
        oldts = dict()
        for el in sel:
            # Add el to a group
            g = inkex.Group()
            gs.append(g)
            # myi=el.getparent().index(el);
            el.getparent().insert(len(el.getparent().getchildren()), g)
            g.insert(0, el)
            # Transfer transform to group
            # g.set("transform", el.get("transform"))
            g.ctransform = el.ctransform
            # el.set("transform", None)
            el.ctransform = None
            # Remove transform
            oldts[g.get_id()] = g.ccomposed_transform
            try:
                dh.global_transform(g, -oldts[g.get_id()])
            except ZeroDivisionError:
                gs.remove(g)

        # dh.idebug(sel)

        # dh.idebug(dir(sel[0]))
        bbs = dh.BB2(
            self.svg, sel, forceupdate=True
        )  # need to investigate why sel didn't work

        for g in gs:
            el = g.getchildren()[0]
            f = inkex.Filter()
            el.root.defs.insert(0, f)
            gb = inkex.Filter.GaussianBlur()
            f.insert(0, gb)
            fid = f.get_id()

            r = inkex.Rectangle()
            g.insert(0, r)

            bb = bbs[el.get_id()]
            ct = el.ccomposed_transform
            # bb = [v / (self.svg.cscale) for v in bb]

            fss = []
            for d in el.descendants2():
                sty = d.cspecified_style
                fs = sty.get("font-size")
                if fs is not None:
                    fss.append(dh.composed_width(d, "font-size")[0])
            if len(fss) > 0:
                fs = max(fss)
            else:
                fs = dh.ipx("8pt")
            border = fs * EXTENT
            # / (self.svg.cscale)

            gb.set("stdDeviation", border * STDDEV)
            pts = [
                [bb[0] - border, bb[1] - border],
                [bb[0] + bb[2] + border, bb[1] - border],
                [bb[0] + bb[2] + border, bb[1] + bb[3] + border],
                [bb[0] - border, bb[1] + bb[3] + border],
                [bb[0] - border, bb[1] - border],
            ]
            xs = []
            ys = []
            for p in pts:
                p = (-ct).apply_to_point(p)
                xs.append(p.x)
                ys.append(p.y)
            r.set("x", str(min(xs)))
            r.set("y", str(min(ys)))
            r.set("width", str(max(xs) - min(xs)))
            r.set("height", str(max(ys) - min(ys)))
            r.set("rx", str(border))
            # r.set('style','fill:#ffffff;filter:url(#'+fid+')')
            r.cstyle = "fill:#ffffff;stroke:none;filter:url(#{0})".format(fid)
            r.cstyle["opacity"] = str(OPACITY)

            dh.global_transform(g, oldts[g.get_id()])

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())


if __name__ == "__main__":
    dh.Run_SI_Extension(TextGhoster(), "Text ghoster")
