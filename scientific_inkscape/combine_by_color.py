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

import inkex
from inkex import (
    Path,\
    NamedView, Defs, Metadata, ForeignObject, Group, MissingGlyph
)
import math
import os,sys
sys.path.append(os.path.dirname(os.path.realpath(sys.argv[0]))) # make sure my directory is on the path
import dhelpers as dh


class ScalePlots(inkex.EffectExtension):
#    def document_path(self):
#        return 'test'
    
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--lightnessth", type=float, default=15, help="Lightness threshold");

    def effect(self):
        # v1 = all([isinstance(el,(str)) for el in self.svg.selection]); # version 1.0 of Inkscape
        # if v1:
        #     inkex.utils.errormsg('Academic-Inkscape requires version 1.1 of Inkscape or higher. Please install the latest version and try again.');
        #     return
        #     # gpe= dh.get_mod(self.svg.selection)
        #     # sel =[gpe[k] for k in gpe.id_dict().keys()];
        # else:
        #     els = [v for el in self.svg.selection for v in dh.descendants2(el)];
        lightness_threshold = self.options.lightnessth/100;
        
        
        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]; # should work with both v1.0 and v1.1
        sel = [v for el in sel for v in dh.descendants2(el)];
        
        allel = [v for v in dh.descendants2(self.svg)];
        elord = [allel.index(v) for v in sel];                      # order of selected elements in svg

        
        els = [el for el in sel if not(isinstance(el, (NamedView, Defs, Metadata, \
               ForeignObject,Group,MissingGlyph))) and (el.get('d') is not None or \
                                                        el.get('points') is not None or \
                                                        el.get('x1') is not None)]
        
        merged = [False for el in els]
        stys = [dh.selected_style_local(el) for el in els]
        sfs  = [stroke_fill_prop(els[ii],stys[ii]) for ii in range(len(els))]
        # dh.debug(lightness_threshold)
        for ii in reversed(range(len(els))): # reversed so that order is preserved
            strk1,fill1,sw1,sd1,sl1,fl1,ms1,mm1,me1 = sfs[ii]
            if strk1 is not None and sl1>=lightness_threshold:
                merges = [ii]; merged[ii]=True
                for jj in range(ii):
                    if not(merged[jj]):
                        strk2,fill2,sw2,sd2,sl2,fl2,ms2,mm2,me2 = sfs[jj]
                        samesw   = (sw1 is None and sw2 is None) or \
                                   (sw1 is not None and sw2 is not None and abs(sw1-sw2)<.001);
                        samestrk = (strk1 is None and strk2 is None) or \
                                   (strk1 is not None and strk2 is not None and \
                                    strk1.red==strk2.red and strk1.blue==strk2.blue and \
                                    strk1.green==strk2.green and abs(strk1.alpha-strk2.alpha)<.001); # RGB are 0-255, alpha are 0-1
                        samefill = (fill1 is None and fill2 is None) or \
                                   (fill1 is not None and fill2 is not None and \
                                    fill1.red==fill2.red and fill1.blue==fill2.blue and \
                                    fill1.green==fill2.green and abs(fill1.alpha-fill2.alpha)<.001)
                        if samestrk and samefill and samesw and sd1==sd2 and \
                           ms1==ms2 and mm1==mm2 and me1==me2:
                            merges.append(jj); merged[jj]=True
                if len(merges)>1:
                    ords = [elord[kk] for kk in merges]; ords.sort()
                    medord = ords[math.floor((len(ords)-1)/2)]
                    topord = ords[-1]
                    mergeii = [kk for kk in range(len(merges)) if elord[merges[kk]]==topord][0] # use the median
                    dh.combine_paths([els[kk] for kk in merges],mergeii)
        
        # dh.debug(len(els))


def stroke_fill_prop(el,sty):
    strk = sty.get('stroke',None)
    fill = sty.get('fill',None)
    op     = float(sty.get('opacity',1.0))
    nones = [None,'none','None'];
    if not(strk in nones):    
        strk   = inkex.Color(strk)
        strkl  = strk.lightness
        strkop = float(sty.get('stroke-opacity',1.0))
        strk.alpha = strkop*op
        strkl  = strk.alpha * strkl/255 + (1-strk.alpha)*1; # effective lightness frac with a white bg
    else:
        strk = None
        strkl = None
    if not(fill in nones):
        fill   = inkex.Color(fill)
        filll  = fill.lightness
        fillop = float(sty.get('fill-opacity',1.0))
        fill.alpha = fillop*op
        filll  = fill.alpha * filll/255 + (1-fill.alpha)*1;  # effective lightness frac with a white bg
    else:
        fill = None
        filll = None
        
    sw = dh.Get_Composed_Width(el, 'stroke-width',styin=sty)
    sd = dh.Get_Composed_List(el, 'stroke-dasharray',styin=sty)
    if sd in nones: sd = None
    if sw in nones or sw==0 or strk is None:
        sw  = None;
        strk= None;
        sd  = None;
        
    ms = sty.get('marker-start',None);
    mm = sty.get('marker-mid',None);
    me = sty.get('marker-end',None);
    
    return (strk,fill,sw,sd,strkl,filll,ms,mm,me)

if __name__ == '__main__':
    dh.Version_Check('Combine by color')
    ScalePlots().run()
