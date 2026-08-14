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
def run_python(python_bin, python_script, python_wd, opts_blob, interminal=False):
    if platform.system() == "Windows":
        DEVNULL = "nul"
    else:
        DEVNULL = "/dev/null"
    # DEVNULL = dh.si_tmp(filename="si_gv_output.txt")
    # dh.idebug(DEVNULL)
    with open(DEVNULL, "w") as devnull:
        subprocess.Popen([python_bin, python_script, opts_blob], stdout=devnull, stderr=devnull)


def default_opts_blob():
    """A complete, shippable settings blob containing no user or machine
    data: options come from the extension's argparse defaults with the
    machine fields set to neutral values."""
    import pickle, base64

    opts = GalleryViewer().arg_parser.parse_args([])
    for k in ("output", "input_file"):
        if hasattr(opts, k):
            delattr(opts, k)
    if not opts.portnum:
        opts.portnum = 5001  # the .inx default
    opts.inkscape_bfn = r"C:\Program Files\Inkscape\bin\inkscape.exe"
    opts.syspath = []
    opts.inshell = False
    return base64.urlsafe_b64encode(pickle.dumps(opts)).decode()


def write_gallery_viewer_bat(opts_blob=None, batch_path=None):
    """Create or update Gallery Viewer.bat. Pass opts_blob=None to write a
    shippable bootstrap bat that carries only default settings and no user
    or machine data: it discovers Inkscape, its Python, and the script
    folder at run time, so it works on machines this extension has never
    run on. With a blob (normal operation) the actual paths are baked in
    as always."""
    if not platform.system() == "Windows":
        return
    bootstrap = opts_blob is None
    if bootstrap:
        opts_blob = default_opts_blob()
    if batch_path:
        batch_file_path = os.path.abspath(batch_path)
    else:
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        batch_file_path = os.path.join(current_script_dir, "Gallery Viewer.bat")
    script_name = "gallery_viewer_script.py"
    if bootstrap:
        preamble = '@echo off\n' + dh.si_bat_discovery(script_name)
        launcher = '"%SIPY%"'
    else:
        # The bat and gallery_viewer_script.py live in the same folder, so cd
        # to the bat's own location and launch the script by name.
        preamble = ('@echo off\n'
                    'cd /d "%~dp0"\n')
        launcher = f'"{sys.executable}"'
    batch_content = (
        preamble +
        '\nSET SI_GV_READY=%TEMP%\\si_gv_ready.flag\n\n'
        'REM Launch detached (settings passed as a base64 arg), then keep\n'
        'REM this window as a loading indicator until the GUI is up.\n'
        'del "%SI_GV_READY%" 2>nul\n'
        'echo Loading Scientific Inkscape Gallery Viewer...\n'
        f'start "" {launcher} "{script_name}" "{opts_blob}"\n'
        'set /a _si_tries=0\n'
        ':si_wait\n'
        'if exist "%SI_GV_READY%" goto si_ready\n'
        'set /a _si_tries+=1\n'
        'if %_si_tries% GEQ 120 goto si_ready\n'
        'ping -n 2 127.0.0.1 >nul\n'
        'goto si_wait\n'
        ':si_ready\n'
        'del "%SI_GV_READY%" 2>nul\n'
    )
    with open(batch_file_path, "w") as batch_file:
        batch_file.write(batch_content)


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

        import base64
        opts_blob = base64.urlsafe_b64encode(pickle.dumps(optcopy)).decode()
        import warnings
        warnings.simplefilter("ignore", ResourceWarning) # prevent process open warning
        run_python(pybin, aepy, pyloc, opts_blob, optcopy.inshell)

        # Make a batch file that can run the Gallery Viewer directly on Windows
        # (settings passed as a base64 command-line arg)
        if platform.system() == "Windows":
            write_gallery_viewer_bat(opts_blob)


        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())


if __name__ == "__main__":
    dh.Run_SI_Extension(GalleryViewer(), "Gallery Viewer")
