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
    TextElement, FlowRoot, FlowPara, Tspan, TextPath, Rectangle, addNS, Transform, Style, PathElement, Line, Rectangle, Path
)

import simplepath
import dhelpers as dh

#import warnings
#warnings.filterwarnings("ignore", category=DeprecationWarning) 

class FlattenPlots(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("-s", "--splittype", default="word", help="type of split")
        pars.add_argument("-p", "--poptext", type=inkex.Boolean, default=True,\
            help="Pop out text to layer")
        pars.add_argument("-f", "--poprest", type=inkex.Boolean, default=True,\
            help="Pop out lines to layer")
        pars.add_argument("-w", "--removerectw", type=inkex.Boolean, default=True,\
            help="Remove white rectangles")
        pars.add_argument("-b", "--removerectb", type=inkex.Boolean, default=False,\
            help="Remove black rectangles")
    

    def effect(self):   
        starttime = time.time();
        sel = self.svg.selection;                     # an ElementList
        # inkex.utils.debug(sel)
        els=[sel[k] for k in sel.id_dict().keys()];
        
        poptext = self.options.poptext
        poprest = self.options.poprest
        removerectw = self.options.removerectw
        removerectb = self.options.removerectb
        
        
        gpe= sel.get()
        els =[gpe[k] for k in gpe.id_dict().keys()];
        gs = [el for el in els if el.typename=='Group']
        os = [el for el in els if not(el.typename=='Group')]
        
        # inkex.utils.debug(self.svg.get_selected_bbox().width)
#        dh.ungroup(gs[0]); 
        if poprest:        
            for g in list(reversed(gs)):
                dh.ungroup(g);    
        
        for el in list(reversed(os)):
            if el.typename=='TextElement' and poptext:
                dh.split_distant(el)
                dh.pop_tspans(el)
                
        if removerectb or removerectw:
            for el in os:
                isrect = False;
                if el.typename=='Rectangle':
                    isrect = True;
                elif el.typename=='PathElement':
                    pth=Path(el.get_path());
                    pts = list(pth.control_points);
                    xs = [p.x for p in pts]
                    ys = [p.y for p in pts]
                    if len(pts)==5 and len(set(xs))==2 and len(set(ys))==2:
                        isrect = True; # if path has 2 unique x, 2 unique y, and exactly 5 pts
#                inkex.utils.debug(el.get_id()+el.typename+str(isrect))
                if isrect:
                    sty=el.composed_style();
                    fill = sty.get('fill');
                    strk = sty.get('stroke');
                    if (removerectw and fill in ['#ffffff','white'] and strk in [None,'none'])\
                        or (removerectb and fill in ['#000000','black'] and strk in [None,'none']):
                        el.delete()
        
        # selected = self.svg
        # if scope == "selection_only":
        #     selected = self.svg.selected.values()

        # for item in selected:
        #     inkex.utils.debug(item) 
                

if __name__ == '__main__':
    import time
    global timestart
    timestart = time.time();
    FlattenPlots().run()
