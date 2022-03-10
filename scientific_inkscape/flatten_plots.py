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
                   addNS, Transform, Style, PathElement, Line, Path,\
                   NamedView, Defs, Metadata, ForeignObject,Group,Use)

import os,sys
sys.path.append(os.path.dirname(os.path.realpath(sys.argv[0]))) # make sure my directory is on the path
import dhelpers as dh

import lxml, os
import RemoveKerning


# dispprofile = True;
dispprofile = False;
lprofile = False;
#lprofile = True;

class FlattenPlots(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--deepungroup", type=inkex.Boolean, default=True,help="Deep ungroup")
        pars.add_argument("--fixtext", type=inkex.Boolean, default=True, help="Text fixes")
        pars.add_argument("--removerectw", type=inkex.Boolean, default=True, help="Remove white rectangles")
        pars.add_argument("--splitdistant", type=inkex.Boolean, default=True, help="Split distant text")
        pars.add_argument("--mergenearby", type=inkex.Boolean, default=True, help="Merge nearby text")
        pars.add_argument("--fixshattering", type=inkex.Boolean, default=True, help="Fix text shattering")
        pars.add_argument("--mergesubsuper", type=inkex.Boolean, default=True, help="Import superscripts and subscripts")
        pars.add_argument("--setreplacement", type=inkex.Boolean, default=False, help="Replace missing fonts")
        pars.add_argument("--replacement", type=str, default='Arial', help="Missing font replacement");
        pars.add_argument("--justification", type=int, default=1, help="Text justification");

    def runflatten(self):
        poprest = self.options.deepungroup
        removerectw = self.options.removerectw
        splitdistant = self.options.splitdistant and self.options.fixtext
        fixshattering = self.options.fixshattering and self.options.fixtext
        mergesubsuper = self.options.mergesubsuper and self.options.fixtext
        mergenearby = self.options.mergenearby and self.options.fixtext
        setreplacement = self.options.setreplacement and self.options.fixtext
        replacement = self.options.replacement
        
        sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]; # should work with both v1.0 and v1.1
        sel = [v for el in sel for v in dh.descendants2(el)];
        
        gs = [el for el in sel if isinstance(el,Group)]
        obs = [el for el in sel if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject,Group)))]
        
        if len(gs)==0 and len(obs)==0:
            inkex.utils.errormsg('No objects selected!'); return;
        
        if poprest:       
            for g in list(reversed(gs)):
                ks = g.getchildren()
                if any([isinstance(k,lxml.etree._Comment) for k in ks]) and \
                   all([isinstance(k,(lxml.etree._Comment,Defs)) or k.get('unlinked_clone')=='True' for k in ks]):
                    # Leave Matplotlib text glyphs grouped together 
                    cmnt = ';'.join([str(k).strip('<!-- ').strip(' -->') for k in ks if isinstance(k,lxml.etree._Comment)]);
                    g.set('mpl_comment',cmnt)
                    [g.remove(k) for k in ks if isinstance(k,lxml.etree._Comment)]; # remove comment, but leave grouped
                elif g.get('mpl_comment') is not None: pass
                else:
                    dh.ungroup(g);    
                    
            # dh.debug(self.svg.get_ids())
            # dh.debug(len(self.svg.get_ids()))
            # x=asdf
#        
#        for el in obs:
#            dh.debug(el.get_id());
#            dh.debug(el.get('clip-path'));
        
        if self.options.fixtext:
            # spd = dict()
            # for el in list(reversed(obs)):
            #     if isinstance(el,(TextElement,Tspan)):
            #         spd[el.get_id()] = el.get('sodipodi:role');
                    # el.set('sodipodi:role',None);
            if setreplacement:
                for el in obs:
                    if isinstance(el,(TextElement,Tspan)) and el.getparent() is not None: # textelements not deleted
#                        ff = dh.Get_Style_Comp(el.get('style'),'font-family');
                        ff = dh.selected_style_local(el).get('font-family');
                        dh.Set_Style_Comp(el,'-inkscape-font-specification',None)
                        if ff==None or ff=='none' or ff=='':
                            dh.Set_Style_Comp(el,'font-family',replacement)
                        elif ff==replacement:
                            pass
                        else:
                            ff = [x.strip('\'').strip() for x in ff.split(',')]
                            if not(ff[-1].lower()==replacement.lower()):
                                ff.append(replacement)
                            dh.Set_Style_Comp(el,'font-family',','.join(ff))   
                            
            if fixshattering or mergesubsuper or splitdistant or mergenearby:
                if self.options.justification==1:
                    justification = 'middle';
                elif self.options.justification==2:
                    justification = 'start';
                elif self.options.justification==3:
                    justification = 'end';
                elif self.options.justification==4:
                    justification = None;
                obs = RemoveKerning.remove_kerning(self,obs,fixshattering,mergesubsuper,splitdistant,mergenearby,justification) 

        
        if removerectw:
            for el in obs:
                if isinstance(el, (PathElement, Rectangle, Line)):
                    xs,ys = dh.get_points(el);
                    if len(xs)==5 and len(set(xs))==2 and len(set(ys))==2: # is a rectangle
                        # sty=el.composed_style();
                        sty=dh.selected_style_local(el);
                        fill = sty.get('fill');
                        strk = sty.get('stroke');
                        opacity = sty.get('opacity')
                        if opacity is None: opacity = 1;
                        if (removerectw and fill in ['#ffffff','white'] and \
                            strk in [None,'none'] and \
                            opacity==1):
                            el.delete()
    
#        dh.debug(time.time()-tic)


    def effect(self):   
        # import random
        # random.seed(a=1)
#        tic = time.time();
        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey
            pr = cProfile.Profile()
            pr.enable()
        
        if lprofile:
            from line_profiler import LineProfiler
            import io
            lp = LineProfiler()
            
            
            import TextParser
            fns = [RemoveKerning.remove_kerning,RemoveKerning.Remove_Manual_Kerning,\
                   RemoveKerning.External_Merges,TextParser.LineList.Parse_Lines,TextParser.LineList.Split_Off_Words,\
                   dh.Get_Composed_LineHeight,dh.Get_Composed_Width,dh.ungroup,dh.selected_style_local,\
                   dh.cascaded_style2,dh.shallow_composed_style,dh.generate_cssdict,dh.descendants2,\
                   dh.getElementById2,dh.add_to_iddict,dh.get_id2,\
                   inkex.elements._base.ShapeElement.composed_transform,inkex.elements._use.Use.unlink]
            for fn in fns:
                lp.add_function(fn)
            lpw = lp(self.runflatten)
            lpw()
            
            stdouttrap = io.StringIO()
            lp.print_stats(stdouttrap);
            
            ppath = os.path.abspath(os.path.join(dh.get_script_path(),'Profile.csv'))
            result=stdouttrap.getvalue()
    #        prefix = result.split('ncalls')[0];
    #        # chop the string into a csv-like buffer
    #        result='ncalls'+result.split('ncalls')[-1]
    #        result='\n'.join([','.join(line.rstrip().split(None,5)) for line in result.split('\n')])
    #        result=prefix+'\n'+result;
            f=open(ppath,'w');
            f.write(result); f.close();
        else:
            self.runflatten()
        
        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            ppath = os.path.abspath(os.path.join(dh.get_script_path(),'Profile.csv'))
            result=s.getvalue()
            prefix = result.split('ncalls')[0];
            # chop the string into a csv-like buffer
            result='ncalls'+result.split('ncalls')[-1]
            result='\n'.join([','.join(line.rstrip().split(None,5)) for line in result.split('\n')])
            result=prefix+'\n'+result;
            f=open(ppath,'w');
            f.write(result); f.close();
                            
            
        
#        for el in obs:
#            dh.debug(el.get_id());
#            dh.debug(el.get('clip-path'));
#        self.svg.selection = inkex.elements._selected.ElementList([el for el in gs + obs + newobs \
#                                if not(isinstance(el, (NamedView, Defs, Metadata, ForeignObject,Tspan)))])
        # removedupes = True
        # if removedupes:
        #     dels=dict();
        #     for ii in range(len(obs)):
        #         el = obs[ii];
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
    dh.Version_Check('Flattener')
    try:
        FlattenPlots().run()
    except lxml.etree.XMLSyntaxError:
        inkex.utils.errormsg('Error parsing XML! Extensions can only run on SVG files. If this is a file imported from another format, try saving as an SVG or pasting the contents into a new SVG.');