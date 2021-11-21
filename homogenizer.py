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
    Use, NamedView, Defs, Metadata, ForeignObject, Group, FontFace, FlowSpan, \
    Image, FlowRegion
)
import dhelpers as dh
from applytransform_mod import ApplyTransform
import math

dispprofile = False
class ScalePlots(inkex.EffectExtension):
#    def document_path(self):
#        return 'test'
    
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--setfontsize", type=inkex.Boolean, default=True,help="Set font size?")
        pars.add_argument("--fontsize", type=float, default=8, help="New font size");
        pars.add_argument("--fixtextdistortion", type=inkex.Boolean, default=False,help="Fix distorted text?")
        pars.add_argument("--fontmodes", type=int, default=1, help="Font size options");
        
        pars.add_argument("--setfontfamily", type=inkex.Boolean, default=False,help="Set font family?")
        pars.add_argument("--fontfamily", type=str, default='', help="New font family");
        
#        pars.add_argument("--setreplacement", type=inkex.Boolean, default=False,help="Replace missing fonts?")
#        pars.add_argument("--replacement", type=str, default='', help="Missing fon replacement");
        
        pars.add_argument("--setstroke", type=inkex.Boolean, default=True,help="Set stroke width?")
        pars.add_argument("--setstrokew", type=float, default=1, help="New stroke width");
        pars.add_argument("--strokemodes", type=int, default=1, help="Stroke width options");
        pars.add_argument("--fusetransforms", type=inkex.Boolean, default=1, help="Fuse transforms to paths?");

    def effect(self):
        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey
            pr = cProfile.Profile()
            pr.enable()
            
            
        setfontsize = self.options.setfontsize
        # setfontsize = (self.options.fontmodes>1);
        
        fontsize = self.options.fontsize
        setfontfamily = self.options.setfontfamily
        fontfamily = self.options.fontfamily
        setstroke = self.options.setstroke;
        setstrokew = self.options.setstrokew;
        fixtextdistortion = self.options.fixtextdistortion;
        
        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]; # should work with both v1.0 and v1.1
        sel = [v for el in sel for v in dh.descendants2(el)];
        
        sela= [el for el in sel if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject)))];
        sel = [el for el in sel if isinstance(el,(TextElement,Tspan,FlowRoot,FlowPara,FlowSpan))];
        
        if setfontfamily or setfontsize or fixtextdistortion:
            bbs=dh.Get_Bounding_Boxes(self,False);
        
        
        if setfontsize:
            # Get all font sizes and scale factors
            szd = dict(); sfd = dict();
            for el in sel:
                actualsize, sf, ct, ang = dh.Get_Composed_Width(el,'font-size',nargout=4);
                elid = el.get_id();
                szd[elid] = actualsize; sfd[elid] = sf;    
            # Get font sizes of all root text elements (max size) and convert sub/superscripts to relative size
            szs = []
            for el in sel:
                if isinstance(el,(TextElement,FlowRoot)):
                    maxsz = float('-inf');
                    for d in dh.descendants2(el):
                        if (d.text is not None and len(d.text)>0) or (d.tail is not None and len(d.tail)>0):
                            mysz = szd[d.get_id()];
                            maxsz = max(maxsz,mysz)
                    
                            sty=dh.cascaded_style2(d);
                            bshift = sty.get('baseline-shift')
                            if bshift in ['sub','super']:
                                psz  = szd[d.getparent().get_id()];
                                pct = mysz/psz * 100;
                                dh.Set_Style_Comp(d,'font-size',str(pct)+'%')
                    maxsz = maxsz/self.svg.unittouu('1pt')
                    szs.append(maxsz)
            # Determine scale and/or size
            fixedscale = False;
            if self.options.fontmodes==3:
                fixedscale = True;
            elif self.options.fontmodes==4:
                fixedscale = True;
                fontsize = fontsize/max(szs)*100;
            elif self.options.fontmodes==5:
                from statistics import mean
                fontsize = mean(szs)
            elif self.options.fontmodes==6:
                from statistics import median
                fontsize = median(szs);
            elif self.options.fontmodes==7:
                fontsize = min(szs);
            elif self.options.fontmodes==8:
                fontsize = max(szs);
            # Set the font sizes                
            for el in sel:
                elid = el.get_id();
                actualsize = szd[elid]; sf = sfd[elid];
                if not(fixedscale):
                    newsize = self.svg.unittouu('1pt')*fontsize;
                else:
                    newsize = actualsize*(fontsize/100);
                fs = dh.Get_Style_Comp(el.style,'font-size');
                if fs is None or not('%' in fs): # keep sub/superscripts relative size
                    dh.Set_Style_Comp(el,'font-size',str(newsize/sf)+'px')
        
        if fixtextdistortion:
            # make a new transform that removes bad scaling and shearing (see General_affine_transformation.nb)
            for el in sel:                     
                ct = el.composed_transform();
                detv = ct.a*ct.d-ct.b*ct.c;
                signdet = -1*(detv<0)+(detv>=0);
                sqrtdet = math.sqrt(abs(detv));
                magv = math.sqrt(ct.b**2 + ct.a**2);
                ctnew = Transform([[ct.a*sqrtdet/magv, -ct.b*sqrtdet*signdet/magv, ct.e], \
                                   [ct.b*sqrtdet/magv,  ct.a*sqrtdet*signdet/magv, ct.f]]);
                dh.global_transform(el,ctnew*(-ct)); 
                
        if setfontfamily:
            for el in reversed(sel):
                dh.Set_Style_Comp(el,'font-family',fontfamily)
                dh.Set_Style_Comp(el,'-inkscape-font-specification',None)
                if fontfamily in ['Avenir','Whitney','Whitney Book'] and isinstance(el,(TextElement,FlowRoot)):
                    dh.Replace_Non_Ascii_Font(el,'Avenir Next, Arial')
        
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
            
        if setfontfamily or setfontsize or fixtextdistortion:
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
            szd = dict(); sfd = dict(); szs=[];
            for el in sela:
                sw,sf,ct,ang = dh.Get_Composed_Width(el,'stroke-width',nargout=4)
                elid = el.get_id();
                szd[elid] = sw; sfd[elid] = sf;    
                if sw is not None:
                    szs.append(sw);
                    
            fixedscale = False;
            if self.options.strokemodes==2:
                setstrokew = self.svg.unittouu(str(setstrokew)+'px');
            elif self.options.strokemodes==3:
                fixedscale = True;
            elif self.options.strokemodes==5:
                from statistics import mean
                setstrokew = mean(szs)
            elif self.options.strokemodes==6:
                from statistics import median
                setstrokew = median(szs);
            elif self.options.strokemodes==7:
                setstrokew = min(szs);
            elif self.options.strokemodes==8:
                setstrokew = max(szs);
            
            for el in sela:
                elid = el.get_id();
                if not(szd[elid] is None):
                    if not(fixedscale):
                        newsize = setstrokew;
                    else:
                        newsize = szd[elid]*(setstrokew/100);
                    dh.Set_Style_Comp(el,'stroke-width',str(newsize/sfd[elid])+'px')
            
            # nw = self.svg.unittouu(str(setstrokew)+setstrokeu)
            # for el in sela:
            #     sty = dh.selected_style_local(el);
            #     strk = sty.get('stroke');
            #     if strk is not None:
            #         actw = dh.Get_Composed_Width(el,'stroke-width');
            #         nomw,u = dh.uparse(dh.Get_Style_Comp(el.style,'stroke-width'));
            #         if nomw is None or nomw==0 or actw is None or actw==0: # stroke width unassigned
            #             dh.Set_Style_Comp(el,'stroke-width','1')
            #             actw = dh.Get_Composed_Width(el,'stroke-width');
            #             nomw,u = dh.uparse(dh.Get_Style_Comp(el.style,'stroke-width'));
            #         sw = dh.urender(nw*nomw/actw,u)    
            #         dh.Set_Style_Comp(el,'stroke-width',sw)
                    
                    
        if self.options.fusetransforms:
            for el in sela:
                 if not(isinstance(el, (TextElement,Image,Group,Tspan,FlowRoot,FlowPara,FlowRegion,FlowSpan,Use))): # not(el.typename in ['TextElement','Image','Group']):
                     ApplyTransform().recursiveFuseTransform(el);
        
        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())

if __name__ == '__main__':

    
    ScalePlots().run()
