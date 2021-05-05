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
    TextElement, FlowRoot, FlowPara, Tspan, TextPath, Rectangle, addNS, \
    Transform, Style, PathElement, Line, Rectangle, Path,Vector2d, \
    Use, NamedView, Defs, Metadata, ForeignObject, Group, FontFace, FlowSpan
)

import simplepath
import dhelpers as dh
import applytransform_mod
import copy

import os

#import warnings
#warnings.filterwarnings("ignore", category=DeprecationWarning) 

class ScalePlots(inkex.EffectExtension):
#    def document_path(self):
#        return 'test'
    
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--setfontsize", type=inkex.Boolean, default=True,help="Set font size?")
        pars.add_argument("--fontsize", type=float, default=8, help="New font size");
        
        pars.add_argument("--setfontfamily", type=inkex.Boolean, default=False,help="Set font family?")
        pars.add_argument("--fontfamily", type=str, default='', help="New font family");
        
#        pars.add_argument("--setreplacement", type=inkex.Boolean, default=False,help="Replace missing fonts?")
#        pars.add_argument("--replacement", type=str, default='', help="Missing fon replacement");
        
        pars.add_argument("--setstroke", type=inkex.Boolean, default=True,help="Set stroke width?")
        pars.add_argument("--setstrokew", type=float, default=1, help="New stroke width (px)");

    def effect(self):   
        setfontsize = self.options.setfontsize
        fontsize = self.options.fontsize
        setfontfamily = self.options.setfontfamily
        fontfamily = self.options.fontfamily
#        setreplacement = self.options.setreplacement
#        replacement = self.options.replacement
        setstroke = self.options.setstroke;
        setstrokew = self.options.setstrokew;
        setstrokeu = 'px';
        
        sel = dh.get_mod(self.svg.selection)
        # sel = .get()
        sel =[sel[k] for k in sel.id_dict().keys()];
        sela= [el for el in sel if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject)))];
        sel = [el for el in sel if isinstance(el,(TextElement,Tspan,FlowRoot,FlowPara,FlowSpan))];
        
        bbs=dh.Get_Bounding_Boxes(self,False);
        # sel = [k for k in sel if k.get_id() in list(bbs.keys())]; # only work on objects with a BB
        
        if setfontsize:
            for el in sel:
                newsize = self.svg.unittouu('1pt')*fontsize;
                actualsize = dh.Get_Composed_Width(el,'font-size');
                if actualsize is not None:
                    scalef = newsize/actualsize
                    fs = dh.Get_Style_Comp(el.style,'font-size');
                    if fs is not None and not('%' in fs): # keep sub/superscripts relative size
                        us = "".join(filter(      lambda a : not(str.isdigit(a) or a=='.'),fs)) # units
                        fs = float("".join(filter(lambda a :    (str.isdigit(a) or a=='.'),fs)))
                        dh.Set_Style_Comp(el,'font-size',str(fs*scalef)+us)
                else:
                    dh.Set_Style_Comp(el,'font-size',str(newsize))
                
        if setfontfamily:
            for el in sel:
                dh.Set_Style_Comp(el,'font-family',fontfamily)
        
#        if setreplacement:
#            for el in sel:
#                ff = dh.Get_Style_Comp(el.get('style'),'font-family');
#                if ff==None or ff=='none' or ff=='':
#                    dh.Set_Style_Comp(el,'font-family',replacement)
#                elif ff==replacement:
#                    pass
#                else:
#                    ff = ff.split(',');
#                    ff = [x.strip('\'') for x in ff]
#                    ff.append(replacement)
#                    ff = ['\''+x+'\'' for x in ff]
#                    dh.Set_Style_Comp(el,'font-family',','.join(ff))
            
        if setfontfamily or setfontsize:
            bbs2=dh.Get_Bounding_Boxes(self,True);
            for el in sel:
                myid = el.get_id();
                if isinstance(el,(TextElement,FlowRoot)) and myid in list(bbs.keys()) and myid in list(bbs2.keys()):
                    bb=bbs[el.get_id()];
                    bb2=bbs2[el.get_id()];
                    tx = (bb2[0]+bb2[2]/2) - (bb[0]+bb[2]/2)
                    ty = (bb2[1]+bb2[3]/2) - (bb[1]+bb[3]/2)
                    trl = Transform('translate('+str(-tx)+', '+str(-ty)+')');
                    dh.global_transform(el,trl)
        
                        
        if setstroke:
            nw = self.svg.unittouu(str(setstrokew)+setstrokeu)
            for el in sela:
                strk = dh.Get_Style_Comp(el.style,'stroke')
                if strk is not None:
                    actw = dh.Get_Composed_Width(el,'stroke-width');
                    nomw,u = dh.uparse(dh.Get_Style_Comp(el.style,'stroke-width'));
                    if nomw is None or nomw==0 or actw is None or actw==0: # stroke width unassigned
                        dh.Set_Style_Comp(el,'stroke-width','1')
                        actw = dh.Get_Composed_Width(el,'stroke-width');
                        nomw,u = dh.uparse(dh.Get_Style_Comp(el.style,'stroke-width'));
                    sw = dh.urender(nw*nomw/actw,u)    
                    dh.Set_Style_Comp(el,'stroke-width',sw)
        

if __name__ == '__main__':
    ScalePlots().run()
