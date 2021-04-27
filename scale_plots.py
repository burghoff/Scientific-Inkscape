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
    Use, NamedView, Defs, Metadata, ForeignObject, Group, SvgDocumentElement, Image
)

import lxml
import dhelpers as dh
from applytransform_mod import ApplyTransform
import copy


#import warnings
#warnings.filterwarnings("ignore", category=DeprecationWarning) 

class ScalePlots(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--hscale", type=float, default=100, help="Horizontal scaling");
        pars.add_argument("--vscale", type=float, default=100, help="Vertical scaling");
        pars.add_argument("--hdrag", type=int, default=1, help="Horizontal scaling");
        pars.add_argument("--vdrag", type=int, default=1, help="Vertical scaling");
        
        pars.add_argument("--hmatch", type=inkex.Boolean, default=100, help="Match width of first selected object?");
        pars.add_argument("--vmatch", type=inkex.Boolean, default=100, help="Match height of first selected object?");
        pars.add_argument("--hdrag2", type=int, default=1, help="Horizontal scaling");
        pars.add_argument("--vdrag2", type=int, default=1, help="Vertical scaling");
        
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--tickcorrect", type=inkex.Boolean, default=True,help="Auto tick correct?")
        pars.add_argument("--tickthreshold", type=int, default=10, help="Tick threshold");
        pars.add_argument("--layerfix", type=str, default='None',help="Layer whose elements should not be scaled")


    def effect(self):   
        # starttime = time.time();
        sel = self.svg.selection;                     # an ElementList
        # inkex.utils.debug(sel)
        sels=[sel[k] for k in sel.id_dict().keys()];
        sels=[k for k in sels if not(isinstance(k, (Tspan,\
                NamedView, Defs, Metadata, ForeignObject)))]; # regular selectable objects only
         
        
        tickcorrect = self.options.tickcorrect
        tickthreshold = self.options.tickthreshold
        layerfix = self.options.layerfix
        if self.options.tab=='scaling':
            hscale = self.options.hscale
            vscale = self.options.vscale
            hdrag = self.options.hdrag
            vdrag = self.options.vdrag
            scalex = hscale/100;
            scaley = vscale/100;
            matchingmode = False;
        elif self.options.tab=='matching':
            hdrag = self.options.hdrag2
            vdrag = self.options.vdrag2
            hmatch = self.options.hmatch;
            vmatch = self.options.vmatch;
            matchingmode = True;
        else:
            inkex.utils.errormsg('Select Scaling or Matching mode'); return;
            
        
        sfgs = []; sfels = [];
        if not(layerfix=='None'): # find scale-free objects
            ls = [t.strip() for t in layerfix.split(',')]
            for el in ls:
                lyr = self.svg.getElementByName(el);
                if lyr is None:
                    lyr = self.svg.getElementById(el);
                if lyr is not None:
                    sfgs.append(lyr)
                    sfels=sfels+lyr.getchildren()
        
        fbbs=dh.Get_Bounding_Boxes(self,False); # full visual bbs
        firstsel = sels[0];
        if matchingmode:
            sels=sels[1:];    
        groupedmode = all([isinstance(k,Group) for k in sels]);
        if not(groupedmode):
            asels = [sels];
        else:
            asels = [list(s.getchildren()) for s in sels];
        
        for sels in asels:
            # Calculate bounding boxes of selected items
            sels = [k for k in sels if k.get_id() in list(fbbs.keys())]; # only work on objects with a BB
            bbs=dict();  # geometric (tight) bounding boxes
            for el in [firstsel]+sels+sfels:
#                if isinstance(el,TextElement):
##                    for k in el.getchildren():
##                        if isinstance(k,Tspan):
##                            dh.debug(dh.fontsize(k))
                if el.get_id() in list(fbbs.keys()):
                    bbs[el.get_id()] = copy.copy(fbbs[el.get_id()]);
                    if isinstance(el,(PathElement,Rectangle,Line)):   # if path-like, use nodes instead
                        xs, ys = dh.get_points(el);
                        bbs[el.get_id()] = [min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)]
#                    dh.debug(str(bbs[el.get_id()][2]/fbbs[el.get_id()][2])+'   '+str(bbs[el.get_id()][3]/fbbs[el.get_id()][3]))
                
            # Find horizontal and vertical lines (to within .001 rad), elements to be used in plot area calculations
            vl = dict(); hl = dict(); boxes = dict(); solids = dict();
            vels = dict(); hels = dict();
            for el in list(reversed(sels)):
                isrect = False;
                if isinstance(el,(PathElement,Rectangle,Line)): #el.typename in ['PathElement','Rectangle','Line']:
                    bb=bbs[el.get_id()];
                    xs, ys = dh.get_points(el);
                    if (max(xs)-min(xs))<.001*bb[3]: # vertical line
                        vl[el.get_id()]=bb[3];
                        vels[el.get_id()]=bb[3];
                    if (max(ys)-min(ys))<.001*bb[2]: # horizontal line
                        hl[el.get_id()]=bb[2];
                        hels[el.get_id()]=bb[2];
                    
                    if len(xs)==5 and len(set(xs))==2 and len(set(ys))==2:
                        isrect = True;
                if isrect or isinstance(el,(Rectangle)): #el.typename=='Rectangle':
                    strk = el.composed_style().get('stroke');
                    fill = el.composed_style().get('fill');
                    nones = [None,'none','white','#ffffff'];
                    if not(fill in nones) and (strk in nones or strk==fill): # solid rectangle
                        solids[el.get_id()]=[bb[2],bb[3]];
                    elif not(strk in nones):                                 # framed box
                        boxes[el.get_id()]=[bb[2],bb[3]];
                        vels[el.get_id()]=bb[3];
                        hels[el.get_id()]=bb[2];
            
            # Display error message            
            if len(vels)==0:
                inkex.utils.errormsg('No vertical lines detected in selection! Make a vertical line or box to define the plot area. (If you think there is one, it may actually be a line-like rectangle.)\n');
            if len(hels)==0:
                inkex.utils.errormsg('No horizontal lines detected in selection! Make a horizontal line or box to define the plot area. (If you think there is one, it may actually be a line-like rectangle.)\n');
            if len(vels)==0 or len(hels)==0:
                return;
            lvl = max(vels, key=vels.get); # largest vertical
            lhl = max(hels, key=hels.get); # largest horizontal
                
            # Determine the bounding box of the whole selection and the plot area
            minx = miny = minxp = minyp = fminxp = fminyp = float('inf');
            maxx = maxy = maxxp = maxyp = fmaxxp = fmaxyp = float('-inf');
            for el in sels:
                bb=bbs[el.get_id()];
                minx = min(minx,bb[0]);
                miny = min(miny,bb[1]);
                maxx = max(maxx,bb[0]+bb[2]);
                maxy = max(maxy,bb[1]+bb[3]);
                if el.get_id() in [lvl,lhl]:
                    minyp = min(minyp,bb[1]);
                    maxyp = max(maxyp,bb[1]+bb[3]);
                    minxp = min(minxp,bb[0]);
                    maxxp = max(maxxp,bb[0]+bb[2]);
                    fbb=fbbs[el.get_id()];
                    fminyp = min(fminyp,fbb[1]);
                    fmaxyp = max(fmaxyp,fbb[1]+fbb[3]);
                    fminxp = min(fminxp,fbb[0]);
                    fmaxxp = max(fmaxxp,fbb[0]+fbb[2]);
                    
            if self.options.tab=='matching':
                bbfirst = bbs[firstsel.get_id()];
                if hmatch:
                    scalex = bbfirst[2]/(maxxp-minxp);
                else:
                    scalex = 1;
                if vmatch:
                    scaley = bbfirst[3]/(maxyp-minyp);
                else:
                    scaley = 1;
            
            # Compute global transformation        
            if hdrag==1: # right
                refx = minx;
            else:        # left
                refx = maxx;
            if vdrag==1: # bottom
                refy = miny;
            else:        # top
                refy = maxy;
            trl = Transform('translate('+str(refx)+', '+str(refy)+')');
            scl = Transform('scale('+str(scalex)+', '+str(scaley)+')');
            gtr = trl*scl*(-trl); # global transformation
    
            trul = gtr.apply_to_point([minxp,minyp]) # transformed upper-left
            trbr = gtr.apply_to_point([maxxp,maxyp]) # transformed bottom-right
            
            # Apply the global transform to all selected regular elements
            cdict=dict();
            for el in list(reversed(sels)):
                dh.addtransform(el,gtr)
                cdict[el.get_id()]=False;
                for k in el.getchildren():
                    cdict[k.get_id()]=False;
            
            # Correct text and group scaling
            iscl = Transform('scale('+str(1/scalex)+', '+str(1/scaley)+')');
            for el in list(reversed(sels)):
                bb=bbs[el.get_id()];
                fbb=fbbs[el.get_id()];   
                outsideplot = fbb[0]>fmaxxp or fbb[0]+fbb[2]<fminxp \
                        or fbb[1]>fmaxyp or fbb[1]+fbb[3]<fminyp;
                
                # if el.get_id()=='text2811':
                #     dh.debug(bbs['text2811'])  
                #     dh.debug(fbbs['text2811']) 
                if (isinstance(el, (TextElement,Group)) or outsideplot) and not(el in sfgs): #el.typename in ['TextElement','Group'] or outsideplot:
                    # Invert the transformation for any text/groups  or anything outside the plot
                    bb1 = gtr.apply_to_point([bb[0],bb[1]]);
                    bb2 = gtr.apply_to_point([bb[0]+bb[2],bb[1]+bb[3]]);
                    cx = (bb1[0]+bb2[0])/2;
                    cy = (bb1[1]+bb2[1])/2;
    
                    trl = Transform('translate('+str(cx)+', '+str(cy)+')');
                    tr1 = trl*iscl*(-trl);
                    
                    # For elements outside the plot area, adjust position to maintain the distance to the plot
                    dx = 0; dy = 0;
                    if cx < trul[0]:
                        ox = bb[0]+bb[2]/2 - minxp;
                        dx = ox - (cx-trul[0]);
                    if cx > trbr[0]:
                        ox = bb[0]+bb[2]/2 - maxxp;
                        dx = ox - (cx-trbr[0]);
                    if cy < trul[1]:
                        oy = bb[1]+bb[3]/2 - minyp;
                        dy = oy - (cy-trul[1]);
                    if cy > trbr[1]:
                        oy = bb[1]+bb[3]/2 - maxyp;
                        dy = oy - (cy-trbr[1]);
                    tr2 = Transform('translate('+str(dx)+', '+str(dy)+')');
                    
                    dh.addtransform(el,tr2*tr1);
                    cdict[el.get_id()]=True;
                    
            
            tickthr = tickthreshold/100;
            # Tick detection and correction
            if tickcorrect:
                for el in list(reversed(sels)):
                    isvert = (el.get_id() in list(vl.keys()));
                    ishorz = (el.get_id() in list(hl.keys()));
                    if isvert or ishorz:
                        bb=bbs[el.get_id()];
                        vtickt = vtickb = htickl = htickr = False;
                        
                        if isvert and bb[3]<tickthr*(maxyp-minyp): # vertical tick
                            if bb[1]+bb[3]<minyp+tickthr*(maxyp-minyp):
                                vtickt = True;
                            elif bb[1]>maxyp-tickthr*(maxyp-minyp):
                                vtickb = True;
                        if ishorz and bb[2]<tickthr*(maxxp-minxp): # horizontal tick
                            if bb[0]+bb[2]<minxp+tickthr*(maxxp-minxp):
                                htickl = True;
                            elif bb[0]>maxxp-tickthr*(maxxp-minxp):
                                htickr = True;
                                        
                        if any([vtickt,vtickb,htickl,htickr]):
                            bb1 = gtr.apply_to_point([bb[0],bb[1]]);
                            bb2 = gtr.apply_to_point([bb[0]+bb[2],bb[1]+bb[3]]);
                            cx = (bb1[0]+bb2[0])/2;
                            cy = (bb1[1]+bb2[1])/2;
                            
                            if vtickt:
                                if cy>trul[1]: # inner tick
                                    trl = Transform('translate('+str(cx)+', '+str(bb1[1])+')');
                                else: # outer tick
                                    trl = Transform('translate('+str(cx)+', '+str(bb2[1])+')');
                            elif vtickb: 
                                if cy<trbr[1]: # inner tick
                                    trl = Transform('translate('+str(cx)+', '+str(bb2[1])+')');
                                else: # outer tick
                                    trl = Transform('translate('+str(cx)+', '+str(bb1[1])+')');
                            elif htickl:
                                if cx>trul[0]: # inner tick
                                    trl = Transform('translate('+str(bb1[0])+', '+str(cy)+')');
                                else:
                                    trl = Transform('translate('+str(bb2[0])+', '+str(cy)+')');
                            elif htickr:
                                if cx<trbr[0]: # inner tick
                                    trl = Transform('translate('+str(bb2[0])+', '+str(cy)+')');
                                else:
                                    trl = Transform('translate('+str(bb1[0])+', '+str(cy)+')');
                            
                            tr1 = trl*iscl*(-trl);
                            if not(cdict[el.get_id()]):
                                dh.addtransform(el,tr1);
                            cdict[el.get_id()]=True;
            
            # Correct anything in scale-free groups                    
            if not(layerfix=='None'):
                for lyr in sfgs:
                    ks=lyr.getchildren();
                    for el in list(reversed(ks)):
                        if el.get_id() in list(cdict.keys()) and cdict[el.get_id()]==False:
                            bb = bbs[el.get_id()];
                            bb1 = gtr.apply_to_point([bb[0],bb[1]]);
                            bb2 = gtr.apply_to_point([bb[0]+bb[2],bb[1]+bb[3]]);
                            cx = (bb1[0]+bb2[0])/2;
                            cy = (bb1[1]+bb2[1])/2;
            
                            trl = Transform('translate('+str(cx)+', '+str(cy)+')');
                            tr1 = trl*iscl*(-trl);
                            dh.addtransform(el,tr1);
                            cdict[el.get_id()]=True

if __name__ == '__main__':
    try:
        ScalePlots().run()
    except lxml.etree.XMLSyntaxError:
        inkex.utils.errormsg('Error parsing XML! Extensions can only run on SVG files. If this is a file imported from another format, try saving as an SVG or pasting the contents into a new SVG.');
