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

import os
import sys
import subprocess
import inkex
from inkex import (
    TextElement, FlowRoot, FlowPara, Tspan, TextPath, Rectangle, addNS, \
    Transform, Style, PathElement, Line, Rectangle, Path,Vector2d, \
    Use, NamedView, Defs, Metadata, ForeignObject, Group, FontFace, StyleElement,\
        StyleSheets,SvgDocumentElement, ShapeElement,BaseElement,FlowSpan,Ellipse,Circle
)
import dhelpers as dh

# Gets the location of the Inkscape binary
# Functions copied from command.py
def Get_Binary_Loc(fin):
    from lxml.etree import ElementTree
    INKSCAPE_EXECUTABLE_NAME = os.environ.get('INKSCAPE_COMMAND')
    if INKSCAPE_EXECUTABLE_NAME == None:
        if sys.platform == 'win32':
            # prefer inkscape.exe over inkscape.com which spawns a command window
            INKSCAPE_EXECUTABLE_NAME = 'inkscape.exe'
        else:
            INKSCAPE_EXECUTABLE_NAME = 'inkscape'
    class CommandNotFound(IOError):
        pass
    class ProgramRunError(ValueError):
        pass
    def which(program):
        if os.path.isabs(program) and os.path.isfile(program):
            return program
        try:
            # Python2 and python3, but must have distutils and may not always
            # work on windows versions (depending on the version)
            from distutils.spawn import find_executable
            prog = find_executable(program)
            if prog:
                return prog
        except ImportError:
            pass
        try:
            # Python3 only version of which
            from shutil import which as warlock
            prog = warlock(program)
            if prog:
                return prog
        except ImportError:
            pass # python2
        raise CommandNotFound(f"Can not find the command: '{program}'")
    def write_svg(svg, *filename):
        filename = os.path.join(*filename)
        if os.path.isfile(filename):
            return filename
        with open(filename, 'wb') as fhl:
            if isinstance(svg, SvgDocumentElement):
                svg = ElementTree(svg)
            if hasattr(svg, 'write'):
                # XML document
                svg.write(fhl)
            elif isinstance(svg, bytes):
                fhl.write(svg)
            else:
                raise ValueError("Not sure what type of SVG data this is.")
        return filename
    def to_arg(arg, oldie=False):
        if isinstance(arg, (tuple, list)):
            (arg, val) = arg
            arg = '-' + arg
            if len(arg) > 2 and not oldie:
                arg = '-' + arg
            if val is True:
                return arg
            if val is False:
                return None
            return f"{arg}={str(val)}"
        return str(arg)
    def to_args(prog, *positionals, **arguments):
        args = [prog]
        oldie = arguments.pop('oldie', False)
        for arg, value in arguments.items():
            arg = arg.replace('_', '-').strip()    
            if isinstance(value, tuple):
                value = list(value)
            elif not isinstance(value, list):
                value = [value]    
            for val in value:
                args.append(to_arg((arg, val), oldie))
        args += [to_arg(pos, oldie) for pos in positionals if pos is not None]
        # Filter out empty non-arguments
        return [arg for arg in args if arg is not None]
    def _call(program, *args, **kwargs):
        stdin = kwargs.pop('stdin', None)
        if isinstance(stdin, str):
            stdin = stdin.encode('utf-8')
        return to_args(which(program), *args, **kwargs)
    def call(program, *args, **kwargs):
        return _call(program, *args, **kwargs)
    def inkscape2(svg_file, *args, **kwargs):
        return call(INKSCAPE_EXECUTABLE_NAME, svg_file, *args, **kwargs)
    return inkscape2(fin)
    

# Gets the caller's location
def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))
        

class ScalePlots(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--watchdir", help="Watch directory")
        pars.add_argument("--writedir", help="Write directory")
        pars.add_argument("--usepdf", help="Export PDF?")
        pars.add_argument("--usepng", help="Export PNG?")
        pars.add_argument("--useemf", help="Export EMF?")
        pars.add_argument("--useeps", help="Export EPS?")

    def effect(self):   
        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey
            pr = cProfile.Profile()
            pr.enable()
        
        formats = [self.options.usepdf,self.options.usepng,self.options.useemf,self.options.useeps]
        formats = '_'.join([str(v) for v in formats])
        
        bfn, tmp = Get_Binary_Loc(self.options.input_file)
        bloc, bnm = os.path.split(bfn)
        pyloc,pybin = os.path.split(sys.executable)
        
        aepy = os.path.abspath(os.path.join(get_script_path(),'autoexporter_script.py'))
        
        # Pass settings using a config file. Include the current path so Inkex can be called if needed.
        import pickle
        s=[self.options.watchdir,self.options.writedir,bfn,formats,sys.path];
        pickle.dump(s,open(os.path.join(get_script_path(),'ae_settings.p'),'wb'));
                
        
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
                shpath = os.path.abspath(os.path.join(get_script_path(),'FindTerminal.sh'));
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
    import warnings
    warnings.filterwarnings("ignore")
    ScalePlots().run()
