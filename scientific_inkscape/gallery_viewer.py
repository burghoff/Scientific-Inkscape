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

DEBUGGING = False
dispprofile = False

import inkex
import os, sys, copy, subprocess

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh

# Convenience functions
def joinmod(dirc, f):
    return os.path.join(os.path.abspath(dirc), f)

# Runs a Python script using a Python binary in a working directory
# It detaches from Inkscape, allowing it to continue running after the extension has finished
def run_python(python_bin,python_script,python_wd,interminal=False):
    import platform
    if platform.system() == 'Windows':
        DEVNULL = 'nul'
    else:
        DEVNULL = '/dev/null'
    DEVNULL = dh.si_tmp(filename='si_gv_output.txt')
    # dh.idebug(DEVNULL)
    with open(DEVNULL, 'w') as devnull:
        subprocess.Popen([python_bin, python_script], stdout=devnull, stderr=devnull)
        

class GalleryViewer(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--portnum", help="Port number for server")

    def effect(self):        
        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey

            pr = cProfile.Profile()
            pr.enable()

        # Make an options copy we can pass to the external program
        optcopy = copy.copy(self.options)
        delattr(optcopy, "output")
        delattr(optcopy, "input_file")

        bfn = dh.Get_Binary_Loc()
        bloc, bnm = os.path.split(bfn)
        pyloc, pybin = os.path.split(sys.executable)

        aepy = os.path.join(dh.si_dir, "gallery_viewer_script.py")
        
        # Pass settings using a config file. Include the current path so Inkex can be called if needed.
        import pickle
        optcopy.inkscape_bfn = bfn;
        optcopy.syspath = sys.path;
        optcopy.inshell = False;

        with open(dh.si_tmp(filename="si_gv_settings.p"), "wb") as f:
            pickle.dump(optcopy, f)
        import warnings
        warnings.simplefilter("ignore", ResourceWarning); # prevent warning that process is open


        
        run_python(pybin,aepy,pyloc,optcopy.inshell)

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())


if __name__ == "__main__":
    dh.Run_SI_Extension(GalleryViewer(),"Gallery Viewer")

