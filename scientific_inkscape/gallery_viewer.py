#!/usr/bin/env python
# coding=utf-8
#
# Copyright (c) 2023 David Burghoff <burghoff@utexas.edu>
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

import dhelpers as dh
import inkex
import os, sys, copy, subprocess, platform

# Convenience functions
def joinmod(dirc, f):
    return os.path.join(os.path.abspath(dirc), f)


# Runs a Python script using a Python binary in a working directory
# It detaches from Inkscape, allowing it to continue running after the extension has finished
def run_python(python_bin, python_script, python_wd, interminal=False):
    if platform.system() == "Windows":
        DEVNULL = "nul"
    else:
        DEVNULL = "/dev/null"
    # DEVNULL = dh.si_tmp(filename="si_gv_output.txt")
    # dh.idebug(DEVNULL)
    with open(DEVNULL, "w") as devnull:
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

        bfn = inkex.inkscape_system_info.binary_location
        bloc, bnm = os.path.split(bfn)
        pyloc, pybin = os.path.split(sys.executable)

        aepy = os.path.join(dh.si_dir, "gallery_viewer_script.py")

        # Pass settings using a config file. Include the current path so Inkex can be called if needed.
        import pickle

        optcopy.inkscape_bfn = bfn
        optcopy.syspath = sys.path
        optcopy.inshell = False
        optcopy.logfile = dh.shared_temp(filename="si_gv_output.txt")

        import tempfile
        settings = os.path.join(
            os.path.abspath(tempfile.gettempdir()), "si_gv_settings.p"
        )

        with open(settings, "wb") as f:
            pickle.dump(optcopy, f)
        import warnings
        warnings.simplefilter("ignore", ResourceWarning) # prevent process open warning
        run_python(pybin, aepy, pyloc, optcopy.inshell)
        
        # Make a batch file that can run the Gallery Viewer directly on Windows
        # Hardcodes the pickled settings
        if platform.system() == "Windows":
            python_cwd = os.getcwd()
            pickled_file_path = settings
            with open(pickled_file_path, "rb") as f:
                pickled_data = f.read()
            import base64
            pickled_data_base64 = base64.b64encode(pickled_data).decode('utf-8')
            current_script_dir = os.path.dirname(os.path.abspath(__file__))
            batch_file_path = os.path.join(current_script_dir, "Gallery Viewer.bat")
            batch_content = '''@echo off
            cd "{python_cwd}"
            
            SET PYBIN="{pybin}"
            SET AEPY="{aepy}"
            SET PICKLED_FILE="{pickled_file}"
            
            REM Use PowerShell to decode the base64 string and write the binary pickled data
            powershell -Command "[System.IO.File]::WriteAllBytes('%PICKLED_FILE%', [Convert]::FromBase64String('{pickled_data_base64}'))"
            
            REM Start the Python script in a new process without opening a new window
            start "" %PYBIN% %AEPY%
            '''.format(
                python_cwd=python_cwd,  # Add the current working directory
                pybin=sys.executable,
                aepy=aepy,
                pickled_file=pickled_file_path.replace('\\', '\\\\'),
                pickled_data_base64=pickled_data_base64
            )
            with open(batch_file_path, "w") as batch_file:
                batch_file.write(batch_content)


        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())


if __name__ == "__main__":
    dh.Run_SI_Extension(GalleryViewer(), "Gallery Viewer")
