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



dispprofile = False;

import subprocess
import inkex
from inkex import (
    TextElement, FlowRoot, FlowPara, Tspan, TextPath, Rectangle, addNS, \
    Transform, Style, PathElement, Line, Rectangle, Path,Vector2d, \
    Use, NamedView, Defs, Metadata, ForeignObject, Group, FontFace, StyleElement,\
        StyleSheets,SvgDocumentElement, ShapeElement,BaseElement,FlowSpan,Ellipse,Circle
)

import os,sys
sys.path.append(os.path.dirname(os.path.realpath(sys.argv[0]))) # make sure my directory is on the path
import dhelpers as dh
        

class ScalePlots(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--watchdir", help="Watch directory")
        pars.add_argument("--writedir", help="Write directory")
        pars.add_argument("--usepdf", help="Export PDF?")
        pars.add_argument("--usepng", help="Export PNG?")
        pars.add_argument("--useemf", help="Export EMF?")
        pars.add_argument("--useeps", help="Export EPS?")
        pars.add_argument("--usesvg", help="Export SVG?")
        pars.add_argument("--dpi", help="Rasterization DPI")
        pars.add_argument("--dpi_im", help="Resampling DPI")
        pars.add_argument("--imagemode",  type=int, default=1, help="Embedded image handling");
        pars.add_argument("--thinline",   type=inkex.Boolean, help="Prevent thin line enhancement")
        pars.add_argument("--texttopath", type=inkex.Boolean, help="Prevent thin line enhancement")

    def effect(self):   
        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey
            pr = cProfile.Profile()
            pr.enable()
        
        formats = [self.options.usepdf,self.options.usepng,self.options.useemf,self.options.useeps,self.options.usesvg]
        formats = '_'.join([str(v) for v in formats])
        dpi = self.options.dpi;
        
        imagedpi = self.options.dpi_im
        reduce_images = self.options.imagemode==1 or self.options.imagemode==2
        tojpg = self.options.imagemode==2
        text_to_paths = self.options.texttopath
        thinline_dehancement = self.options.thinline;
        
        
        bfn, tmp = dh.Get_Binary_Loc(self.options.input_file)
        bloc, bnm = os.path.split(bfn)
        pyloc,pybin = os.path.split(sys.executable)
        
        aepy = os.path.abspath(os.path.join(dh.get_script_path(),'autoexporter_script.py'))
        
        # Pass settings using a config file. Include the current path so Inkex can be called if needed.
        import pickle
        s=[self.options.watchdir,self.options.writedir,bfn,formats,sys.path,dpi,\
           imagedpi,reduce_images,tojpg,text_to_paths,thinline_dehancement];
        pickle.dump(s,open(os.path.join(dh.get_script_path(),'ae_settings.p'),'wb'));
        # dh.debug([pybin,aepy])
                
        
        def escp(x):
            return x.replace(' ','\\\\ ');
        import platform
        if platform.system().lower()=='darwin':
            # https://stackoverflow.com/questions/39840632/launch-python-script-in-new-terminal
            os.system("osascript -e 'tell application \"Terminal\" to do script \""+\
                        escp(sys.executable)+' '+escp(aepy)+"\"' >/dev/null")
        elif platform.system().lower()=='windows':
            if pybin=='pythonw.exe': pybin='python.exe'
            subprocess.Popen([pybin,aepy],shell=False,cwd=pyloc); 
        else:
            if sys.executable[0:4]=='/tmp':
                inkex.utils.errormsg('This appears to be an AppImage of Inkscape, which the Autoexporter cannot support since AppImages are sandboxed.');
                return;
            elif sys.executable[0:5]=='/snap':
                inkex.utils.errormsg('This appears to be an Snap installation of Inkscape, which the Autoexporter cannot support since Snap installations are sandboxed.');
                return;
            else:
                shpath = os.path.abspath(os.path.join(dh.get_script_path(),'FindTerminal.sh'));
                os.system('sh '+escp(shpath));
                f=open('tmp','rb'); terms=f.read(); f.close(); os.remove('tmp')
                terms = terms.split();
                for t in reversed(terms):
                    if t==b'x-terminal-emulator':
                        LINUX_TERMINAL_CALL = 'x-terminal-emulator -e bash -c \'%CMD\'';
                    elif t==b'gnome-terminal':
                        LINUX_TERMINAL_CALL = 'gnome-terminal -- bash -c \"%CMD; exec bash\"';
                os.system(LINUX_TERMINAL_CALL.replace('%CMD',escp(sys.executable)+' '+escp(aepy)+' >/dev/null'))

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())
                        
        
if __name__ == '__main__':
    dh.Version_Check('Autoexporter')
    import warnings
    warnings.filterwarnings("ignore")
    ScalePlots().run()
