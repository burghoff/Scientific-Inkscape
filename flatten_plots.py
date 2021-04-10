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
from inkex import (TextElement, FlowRoot, FlowPara, Tspan, TextPath, Rectangle,\
                   addNS, Transform, Style, PathElement, Line, Rectangle, Path,\
                   NamedView, Defs, Metadata, ForeignObject,Group)

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
        # pars.add_argument("-b", "--removerectb", type=inkex.Boolean, default=False,\
        #     help="Remove black rectangles")
    

    def effect(self):   
        starttime = time.time();
        sel = self.svg.selection;                     # an ElementList
        # inkex.utils.debug(sel)
        els=[sel[k] for k in sel.id_dict().keys()];
        
        poptext = self.options.poptext
        poprest = self.options.poprest
        removerectw = self.options.removerectw
        # removerectb = self.options.removerectb
        
        gpe= sel.get()
        els =[gpe[k] for k in gpe.id_dict().keys()];
        gs = [el for el in els if isinstance(el,Group)]
        os = [el for el in els if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject,Group)))]
        
        # inkex.utils.debug(self.svg.get_selected_bbox().width)
#        dh.ungroup(gs[0]); 
        if poprest:        
            for g in list(reversed(gs)):
                dh.ungroup(g);    
        
        for el in list(reversed(os)):
            if isinstance(el,TextElement) and poptext:
                dh.split_distant(el)
                dh.pop_tspans(el)
                 
        if removerectw:
            for el in os:
                if isinstance(el, (PathElement, Rectangle, Line)):
                    xs,ys = dh.get_points(el);
                    if len(xs)==5 and len(set(xs))==2 and len(set(ys))==2: # is a rectangle
                        sty=el.composed_style();
                        fill = sty.get('fill');
                        strk = sty.get('stroke');
                        # if (removerectw and fill in ['#ffffff','white'] and strk in [None,'none'])\
                        #     or (removerectb and fill in ['#000000','black'] and strk in [None,'none']):
                        #     el.delete()
                        if (removerectw and fill in ['#ffffff','white'] and strk in [None,'none']):
                            el.delete()
        
        # removedupes = True
        # if removedupes:
        #     dels=dict();
        #     for ii in range(len(os)):
        #         el = os[ii];
        #         dels[el.get_id()]=False
        #         elsty = el.composed_style()
        #         for jj in range(ii+1,len(os)):
        #             cel = os[jj];
        #             if el.typename==cel.typename:
        #                 if elsty==cel.composed_style():
        #                     if isinstance(el, (PathElement, Rectangle, Line)):
        #                         xs,ys   = dh.get_points(el);
        #                         cxs,cys = dh.get_points(cel);
        #                         dh.debug(xs)
        #                         dh.debug(cxs)
        #                         dh.debug(ys)
        #                         dh.debug(cys)
        #                         if max([abs(d[0]-d[1]) for d in zip(xs,cxs)])<.01 and\
        #                             max([abs(d[0]-d[1]) for d in zip(ys,cys)])<.01:
        #                             dels[el.get_id()]=True;
        #     for el in os:
        #         if dels[el.get_id()]:
        #             el.delete();
                             
        # linestotop = True
        # if linestotop:
        #     for el in os:
        #         if isinstance(el, (PathElement, Rectangle, Line)):
        #             xs,ys = dh.get_points(el);
        #             if (len(xs)==5 and len(set(xs))==2 and len(set(ys))==2) \
        #                 or len(set(xs))==1 or len(set(ys))==1:        # horizontal or vertical line
        #                 strk = el.composed_style().get('stroke');
        #                 sdsh = el.composed_style().get('stroke-dasharray');
        #                 if not(strk in [None,'none']) and sdsh in [None,'none']:
        #                     el.getparent().insert(len(el.getparent()),el); # pop me to the top
                    
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
