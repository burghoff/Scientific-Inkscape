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
    Transform, PathElement, Line, Rectangle, Path,Vector2d, \
    Use, NamedView, Defs, Metadata, ForeignObject, Group, FontFace, FlowSpan, MissingGlyph,Polyline
)

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
            
        # sel = self.svg.selection;                     # an ElementList
        # sel = dh.get_mod(sel)
        # els = [sel[k] for k in sel.id_dict().keys()];
        # els = [v for el in self.svg.selection for v in dh.descendants2(el)]
        
        els = [el for el in sel if not(isinstance(el, (NamedView, Defs, Metadata, \
               ForeignObject,Group,MissingGlyph))) and (el.get('d') is not None or \
                                                        el.get('points') is not None or \
                                                        el.get('x1') is not None)]
        
        merged = [False for el in els]
        stys = [dh.selected_style_local(el) for el in els]
        sfs  = [stroke_fill_prop(els[ii],stys[ii]) for ii in range(len(els))]
        # dh.debug(lightness_threshold)
        for ii in reversed(range(len(els))): # reversed so that order is preserved
            el1 = els[ii];
            # strk = stys[ii].get('stroke');
            # if strk is not None and not(strk.lower() in ['#000000','#262626']):
            strk1,fill1,sw1,sd1,sl1,fl1,ms1,mm1,me1 = sfs[ii]
            if strk1 is not None and sl1>=lightness_threshold:
                merges = [el1]; merged[ii]=True
                for jj in range(ii):
                    el2 = els[jj];
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
                            merges.append(el2); merged[jj]=True
                if len(merges)>1:
                    self.combine_paths(merges)
                    # dh.debug(merges[0].get('clip-path'))
                    # dh.debug(merges)
        
        # dh.debug(len(els))
    def combine_paths(self,els):
        pnew = Path();
        fp = None; # first path
        sp = [];   # subsequent paths
        si = [];  # start indices
        for ii in range(len(els)):
            el = els[ii];
            if fp is None:
                fp=ii;
            else:
                sp.append(ii)
            pth = Path(el.get_path()).to_absolute().transform(el.composed_transform());
            if el.get('inkscape-academic-combined-by-color') is None:
                si.append(len(pnew))
            else:
                cbc = el.get('inkscape-academic-combined-by-color') # take existing ones and weld them
                cbc = [int(v) for v in cbc.split()]
                si += [v+len(pnew) for v in cbc[0:-1]]
            for p in pth:
                pnew.append(p)
        si.append(len(pnew))
        if fp is not None:
            if els[fp].get('d') is not None:
                els[fp].set_path(pnew.transform(-els[fp].composed_transform()));
            else:
                # Polylines and lines have to be replaced with a new path
                dh.object_to_path(els[fp])
                els[fp].set('d',str(pnew.transform(-els[fp].composed_transform())));
                
            # Release clips/masks    
            els[fp].set('clip-path','none'); # release any clips
            els[fp].set('mask'     ,'none'); # release any masks
            dh.fix_css_clipmask(els[fp],mask=False) # fix CSS bug
            dh.fix_css_clipmask(els[fp],mask=True)
            
            els[fp].set('inkscape-academic-combined-by-color',' '.join([str(v) for v in si]))
            for s in sp:
                deleteup(els[s])

# Delete and prune empty ancestor groups       
def deleteup(el):
    myp = el.getparent();
    el.delete()
    if myp is not None:
        myc = myp.getchildren();
        if myc is not None and len(myc)==0:
            deleteup(myp)

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
