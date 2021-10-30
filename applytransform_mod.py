#!/usr/bin/env python3
#
# License: GPL2
# Copyright Mark "Klowner" Riedesel
# https://github.com/Klowner/inkscape-applytransforms
# Modified by David Burghoff

import inkex
import math
from inkex.paths import CubicSuperPath, Path
from inkex.transforms import Transform
from inkex.styles import Style
from inkex import (Line, Rectangle,Polygon,Polyline,Ellipse,Circle)
import dhelpers as dh
import copy

NULL_TRANSFORM = Transform([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
from lxml import etree

class ApplyTransform(inkex.EffectExtension):
    def __init__(self):
        super(ApplyTransform, self).__init__()

    def effect(self):
        if self.svg.selected:
            for (_, shape) in self.svg.selected.items():
                self.recursiveFuseTransform(shape)
        else:
            self.recursiveFuseTransform(self.document.getroot())
 
    @staticmethod
    def remove_attrs(node):
        if node.tag == inkex.addNS('g', 'svg'):
            return node
        if node.tag == inkex.addNS('path', 'svg') or node.tag == 'path':
            for attName in node.attrib.keys():
                if ("sodipodi" in attName) or ("inkscape" in attName) \
                    and attName!='inkscape-academic-combined-by-color':
                    del node.attrib[attName]
            return node
        return node

    def scaleStrokeWidth(self, node, transf):
        if 'style' in node.attrib:
            style = node.attrib.get('style')
            style = dict(Style.parse_str(style))
            update = False
            if 'stroke-width' in style:
                try:
                    stroke_width = float(style.get('stroke-width').strip().replace("px", ""))
                    # Modification by David Burghoff: corrected to use determinant
#                    stroke_width *= math.sqrt(abs(transf.a * transf.d))
                    stroke_width *= math.sqrt(abs(transf.a * transf.d - transf.b * transf.c))
                    style['stroke-width'] = str(stroke_width)
                    update = True
                except AttributeError:
                    pass
            if update:
                node.attrib['style'] = Style(style).to_str()
    

    def recursiveFuseTransform(self, node, transf=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],irange=None,trange=None):
        # Modification by David Burghoff:
        # Since transforms apply to an object's clips, before applying the transform
        # we will need to duplicate the clip path and transform it
        clippathurl = node.get('clip-path')
        if clippathurl is not None and node.get("transform") is not None:
            myn = node
            while not(myn.getparent()==None):  # get svg handle
                myn = myn.getparent();
            svg = myn;
            clippath = svg.getElementById(clippathurl[5:-1]);
            if clippath is not None:
                d = clippath.duplicate();
                clippathurl = "url(#" + d.get("id") + ")"
                node.set("clip-path", clippathurl);
                for k in d.getchildren():
                    if k.get('transform') is not None:
                        tr = Transform(node.get("transform"))*Transform(k.get('transform'));
                    else:
                        tr = Transform(node.get("transform"));
                    k.set('transform',tr);
        
        transf = Transform(transf) * Transform(node.get("transform", None))


        if 'transform' in node.attrib:
            del node.attrib['transform']
        node = ApplyTransform.remove_attrs(node)
        
        if not(transf.b==0 and transf.c==0) and isinstance(node,(Rectangle,Ellipse,Circle)):
            # Rectangles, Ellipses, and Circles need to be converted to paths if there is shear/rotation
            dh.object_to_path(node)

        if transf == NULL_TRANSFORM and irange is None and trange is None:
            # Don't do anything if there is effectively no transform applied (reduces alerts for unsupported nodes)
            pass
        elif 'd' in node.attrib:
            d = node.get('d')
            p = CubicSuperPath(d);
            if irange is None:
                p = Path(p).to_absolute().transform(transf, True)
            if irange is not None:
                p = Path(p).to_absolute(); pnew=[]
                for ii in range(len(irange)):
                    xf = trange[ii] * Transform(node.get("transform", None))
                    pnew += Path(p[irange[ii][0]:irange[ii][1]]).transform(xf, True)
                p = pnew
            node.set('d', str(Path(CubicSuperPath(p).to_path())))
            self.scaleStrokeWidth(node, transf)
        elif isinstance(node,(Polygon,Polyline)): # node.tag in [inkex.addNS('polygon', 'svg'), inkex.addNS('polyline', 'svg')]:
            points = node.get('points')
            points = points.strip().split(' ')
            for k, p in enumerate(points):
                if ',' in p:
                    p = p.split(',')
                    p = [float(p[0]), float(p[1])]
                    p = transf.apply_to_point(p)
                    p = [str(p[0]), str(p[1])]
                    p = ','.join(p)
                    points[k] = p
            points = ' '.join(points)
            node.set('points', points)
            self.scaleStrokeWidth(node, transf)
        elif isinstance(node,(Ellipse,Circle)): #node.tag in [inkex.addNS("ellipse", "svg"), inkex.addNS("circle", "svg")]:
            def isequal(a, b):
                return abs(a - b) <= transf.absolute_tolerance
            if node.TAG == "ellipse":
                rx = float(node.get("rx"))
                ry = float(node.get("ry"))
            else:
                rx = float(node.get("r"))
                ry = rx
            cx = float(node.get("cx"))
            cy = float(node.get("cy"))
            sqxy1 = (cx - rx, cy - ry)
            sqxy2 = (cx + rx, cy - ry)
            sqxy3 = (cx + rx, cy + ry)
            newxy1 = transf.apply_to_point(sqxy1)
            newxy2 = transf.apply_to_point(sqxy2)
            newxy3 = transf.apply_to_point(sqxy3)
            node.set("cx", (newxy1[0] + newxy3[0]) / 2)
            node.set("cy", (newxy1[1] + newxy3[1]) / 2)
            edgex = math.sqrt(
                abs(newxy1[0] - newxy2[0]) ** 2 + abs(newxy1[1] - newxy2[1]) ** 2
            )
            edgey = math.sqrt(
                abs(newxy2[0] - newxy3[0]) ** 2 + abs(newxy2[1] - newxy3[1]) ** 2
            )
            if node.TAG == "ellipse":
                node.set("rx", edgex / 2)
                node.set("ry", edgey / 2)
            else:
                node.set("r", edgex / 2)
                
        # Modficiations by David Burghoff: Added support for lines, rectangles, polylines
        elif isinstance(node, Line):  
            x1=node.get('x1')
            x2=node.get('x2')
            y1=node.get('y1')
            y2=node.get('y2')
            p1 = transf.apply_to_point([x1,y1]);
            p2 = transf.apply_to_point([x2,y2]);
            node.set('x1',str(p1[0]))
            node.set('y1',str(p1[1]))
            node.set('x2',str(p2[0]))
            node.set('y2',str(p2[1]))
            self.scaleStrokeWidth(node, transf)

        elif isinstance(node,Rectangle):  
            x = float(node.get('x'));
            y = float(node.get('y'));
            w = float(node.get('width'));
            h = float(node.get('height'));
            pts = [[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]];
            xs = []; ys = [];
            for p in pts:
                p = transf.apply_to_point(p);
                xs.append(p.x)
                ys.append(p.y)
            node.set('x',str(min(xs)))
            node.set('y',str(min(ys)))
            node.set('width',str(max(xs)-min(xs)))
            node.set('height',str(max(ys)-min(ys)))
            self.scaleStrokeWidth(node, transf)
            
        else:
            # e.g. <g style="...">
            self.scaleStrokeWidth(node, transf)

        for child in node.getchildren():
            self.recursiveFuseTransform(child, transf)
            

if __name__ == '__main__':
    ApplyTransform().run()
