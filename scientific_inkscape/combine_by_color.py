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
import numpy as np

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

        sfs = [dh.get_strokefill(els[ii]) for ii in range(len(els))]
        # Candidates grouped by what must match exactly: stroke and fill
        # colors, dash array and markers. Paths painted with a gradient or
        # pattern are left alone. Stroke width and alphas are compared
        # within a tolerance inside each group.
        groups = {}
        for ii, sf in enumerate(sfs):
            if sf.strk_isurl or sf.fill_isurl:
                continue
            key = (
                None if sf.stroke is None else (sf.stroke.red, sf.stroke.green, sf.stroke.blue),
                None if sf.fill is None else (sf.fill.red, sf.fill.green, sf.fill.blue),
                tuple(sf.strokedasharray) if isinstance(sf.strokedasharray, list) else sf.strokedasharray,
                sf.markerstart,
                sf.markermid,
                sf.markerend,
            )
            groups.setdefault(key, []).append(ii)
        # RGB are 0-255, alpha are 0-1
        for idx in groups.values():
            gsf = [sfs[ii] for ii in idx]
            sw = np.array([0.0 if sf.strokewidth is None else sf.strokewidth for sf in gsf])
            sa = np.array([0.0 if sf.stroke is None else sf.stroke.alpha for sf in gsf])
            fa = np.array([0.0 if sf.fill is None else sf.fill.alpha for sf in gsf])
            merged = np.zeros(len(idx), dtype=bool)
            for kk in reversed(range(len(idx))):  # reversed so that order is preserved
                sf1 = gsf[kk]
                if (
                    sf1.stroke is None or sf1.stroke.efflightness >= lightness_threshold
                ) and (sf1.fill is None or sf1.fill.efflightness >= lightness_threshold):
                    merged[kk] = True
                    same = (
                        ~merged[:kk]
                        & (np.abs(sw[:kk] - sw[kk]) < 0.001)
                        & (np.abs(sa[:kk] - sa[kk]) < 0.001)
                        & (np.abs(fa[:kk] - fa[kk]) < 0.001)
                    )
                    js = np.flatnonzero(same)
                    merged[js] = True
                    merges = [idx[kk]] + [idx[jj] for jj in js.tolist()]
                    if len(merges) > 1:
                        ords = [elord[kk] for kk in merges]
                        ords.sort()
                        topord = ords[-1]
                        mergeii = [
                            kk for kk in range(len(merges)) if elord[merges[kk]] == topord
                        ][0]
                        dh.combine_paths([els[kk] for kk in merges], mergeii)
        # dh.flush_stylesheet_entries(self.svg)  # since we removed clips


if __name__ == "__main__":
    dh.Run_SI_Extension(CombineByColor(), "Combine by color")
