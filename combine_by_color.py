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
    Use, NamedView, Defs, Metadata, ForeignObject, Group, FontFace, FlowSpan, MissingGlyph
)

import dhelpers as dh


class ScalePlots(inkex.EffectExtension):
#    def document_path(self):
#        return 'test'
    
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")

    def effect(self):
        v1 = all([isinstance(el,(str)) for el in self.svg.selection]); # version 1.0 of Inkscape
        if v1:
            inkex.utils.errormsg('Academic-Inkscape requires version 1.1 of Inkscape or higher. Please install the latest version and try again.');
            return
            # gpe= dh.get_mod(self.svg.selection)
            # sel =[gpe[k] for k in gpe.id_dict().keys()];
        else:
            els = [v for el in self.svg.selection for v in dh.descendants2(el)];
            
            
        # sel = self.svg.selection;                     # an ElementList
        # sel = dh.get_mod(sel)
        # els = [sel[k] for k in sel.id_dict().keys()];
        # els = [v for el in self.svg.selection for v in dh.descendants2(el)]
        
        els = [el for el in els if not(isinstance(el, (NamedView, Defs, Metadata, \
               ForeignObject,Group,MissingGlyph))) and el.get('d') is not None]
        
        merged = [False for el in els]
        stys = [dh.selected_style_local(el) for el in els]
#        dh.debug(stys)
        for ii in reversed(range(len(els))): # reversed so that order is preserved
            el1 = els[ii];
            strk = stys[ii].get('stroke');
            if strk is not None and strk.lower()!='#000000':
                merges = [el1]; merged[ii]=True
                for jj in range(ii):
                    el2 = els[jj];
                    if not(merged[jj]):
                        if stys[ii]==stys[jj]:
                            merges.append(el2); merged[jj]=True
                if len(merges)>1:
                    self.combine_paths(merges)
#                    dh.debug(merges)
        
        
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
            els[fp].set_path(pnew.transform(-els[fp].composed_transform()));
            els[fp].set('clip-path',None); # release any clips
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
        

if __name__ == '__main__':
    ScalePlots().run()
