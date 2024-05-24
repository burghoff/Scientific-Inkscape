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
#

import dhelpers as dh
import inkex
from inkex import NamedView, Defs, Metadata, ForeignObject, Group, MissingGlyph
import math

class CombineByColor(inkex.EffectExtension):
    #    def document_path(self):
    #        return 'test'

    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument(
            "--lightnessth", type=float, default=15, help="Lightness threshold"
        )

    def effect(self):
        lightness_threshold = self.options.lightnessth / 100

        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
        # should work with both v1.0 and v1.1
        sel = [v for el in sel for v in el.descendants2()]

        allel = [v for v in self.svg.descendants2()]
        elord = [allel.index(v) for v in sel]
        # order of selected elements in svg

        els = [
            el
            for el in sel
            if not (
                isinstance(
                    el, (NamedView, Defs, Metadata, ForeignObject, Group, MissingGlyph)
                )
            )
            and (
                el.get("d") is not None
                or el.get("points") is not None
                or el.get("x1") is not None
            )
        ]

        merged = [False for el in els]
        # stys = [(el.cspecified_style) for el in els]
        sfs = [dh.get_strokefill(els[ii]) for ii in range(len(els))]
        # dh.debug(lightness_threshold)
        for ii in reversed(range(len(els))):  # reversed so that order is preserved
            sf1 = sfs[ii]
            # if (
            #     sf1.stroke is not None
            #     and sf1.stroke.efflightness >= lightness_threshold
            # ):
            if (
                sf1.stroke is None or sf1.stroke.efflightness >= lightness_threshold
            ) and (sf1.fill is None or sf1.fill.efflightness >= lightness_threshold):
                merges = [ii]
                merged[ii] = True
                for jj in range(ii):
                    if not (merged[jj]):
                        sf2 = sfs[jj]
                        samesw = (
                            sf1.strokewidth is None and sf2.strokewidth is None
                        ) or (
                            sf1.strokewidth is not None
                            and sf2.strokewidth is not None
                            and abs(sf1.strokewidth - sf2.strokewidth) < 0.001
                        )
                        samestrk = (sf1.stroke is None and sf2.stroke is None) or (
                            sf1.stroke is not None
                            and sf2.stroke is not None
                            and sf1.stroke.red == sf2.stroke.red
                            and sf1.stroke.blue == sf2.stroke.blue
                            and sf1.stroke.green == sf2.stroke.green
                            and abs(sf1.stroke.alpha - sf2.stroke.alpha) < 0.001
                        )
                        # RGB are 0-255, alpha are 0-1
                        samefill = (sf1.fill is None and sf2.fill is None) or (
                            sf1.fill is not None
                            and sf2.fill is not None
                            and sf1.fill.red == sf2.fill.red
                            and sf1.fill.blue == sf2.fill.blue
                            and sf1.fill.green == sf2.fill.green
                            and abs(sf1.fill.alpha - sf2.fill.alpha) < 0.001
                        )
                        if (
                            samestrk
                            and samefill
                            and samesw
                            and sf1.strokedasharray == sf2.strokedasharray
                            and sf1.markerstart == sf2.markerstart
                            and sf1.markermid == sf2.markermid
                            and sf1.markerend == sf2.markerend
                        ):
                            merges.append(jj)
                            merged[jj] = True
                if len(merges) > 1:
                    ords = [elord[kk] for kk in merges]
                    ords.sort()
                    medord = ords[math.floor((len(ords) - 1) / 2)]
                    topord = ords[-1]
                    mergeii = [
                        kk for kk in range(len(merges)) if elord[merges[kk]] == topord
                    ][
                        0
                    ]  # use the median
                    dh.combine_paths([els[kk] for kk in merges], mergeii)
        # dh.flush_stylesheet_entries(self.svg)  # since we removed clips


if __name__ == "__main__":
    dh.Run_SI_Extension(CombineByColor(), "Combine by color")
