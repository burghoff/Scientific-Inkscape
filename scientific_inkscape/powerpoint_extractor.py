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
    DEVNULL = dh.si_tmp(filename='si_ppe_output.txt')
    # dh.idebug(DEVNULL)
    with open(DEVNULL, 'w') as devnull:
        subprocess.Popen([python_bin, python_script], stdout=devnull, stderr=devnull)
        
        
        # if 'pythonw.exe' in python_bin:
        #     python_bin = python_bin.replace('pythonw.exe', 'python.exe')
        # DETACHED_PROCESS = 0x08000000
        # subprocess.Popen([python_bin, python_script, 'standalone'], creationflags=DETACHED_PROCESS)
        # subprocess.run([python_bin, python_script], stdout=devnull, stderr=devnull)
        # subprocess.call([python_bin, python_script], stdout=devnull, stderr=devnull)
        # import os
        # os.system(f"{python_bin} {python_script} &> nul")

        # subprocess.Popen([python_bin, python_script], shell=False)
        
    # def escp(x):
    #     return x.replace(" ", "\\\\ ")
    # import platform
    # if not(interminal):
    #     if platform.system().lower() == "darwin":
    #         # dh.idebug('osascript -e \'tell application "Terminal" to do script "{0} {1}"\' >/dev/null'.format(escp(sys.executable),escp(python_script)))
    #         os.system(
    #             'osascript -e \'tell application "Terminal" to do script "{0} {1} &! exit"\' >/dev/null'.format(escp(sys.executable),escp(python_script))
    #         )
    #     elif platform.system().lower() == "windows":
    #         if python_bin == "pythonw.exe":
    #             python_bin = "python.exe"
    #         subprocess.Popen([python_bin, python_script], shell=False, cwd=python_wd, creationflags=subprocess.CREATE_NO_WINDOW)
    #     else:
    #         if sys.executable[0:4] == "/tmp":
    #             inkex.utils.errormsg("This appears to be an AppImage of Inkscape, which the Autoexporter cannot support since AppImages are sandboxed.")
    #             return
    #         elif sys.executable[0:5] == "/snap":
    #             with open('/dev/null', 'w') as DEVNULL:
    #                 subprocess.Popen(["python", "your_gtk_code.py"], stdout=DEVNULL, stderr=DEVNULL)
    #             # inkex.utils.errormsg("This appears to be an Snap installation of Inkscape, which the Autoexporter cannot support since Snap installations are sandboxed.")
    #             return
    #         else:
    #             os.system(sys.executable + " " + python_script + " >/dev/null")
    # else:
    #     if platform.system().lower() == "darwin":
    #         # https://stackoverflow.com/questions/39840632/launch-python-script-in-new-terminal
    #         os.system(
    #             'osascript -e \'tell application "Terminal" to do script "'
    #             + escp(sys.executable)
    #             + " "
    #             + escp(python_script)
    #             + "\"' >/dev/null"
    #         )
    #     elif platform.system().lower() == "windows":
    #         if python_bin == "pythonw.exe":
    #             python_bin = "python.exe"
    #         subprocess.Popen([python_bin, python_script], shell=False, cwd=python_wd)
    #     else:
    #         if sys.executable[0:4] == "/tmp":
    #             inkex.utils.errormsg(
    #                 "This appears to be an AppImage of Inkscape, which the Autoexporter cannot support since AppImages are sandboxed."
    #             )
    #             return
    #         elif sys.executable[0:5] == "/snap":
    #             dh.idebug(sys.executable)
    #             inkex.utils.errormsg(
    #                 "This appears to be an Snap installation of Inkscape, which the Autoexporter cannot support since Snap installations are sandboxed."
    #             )
    #             return
    #         else:
    #             # shpath = os.path.abspath(
    #             #     os.path.join(dh.get_script_path(), "FindTerminal.sh")
    #             # )
    #             # os.system("sh " + escp(shpath))
    #             # f = open("tmp", "rb")
    #             # terms = f.read()
    #             # f.close()
    #             # os.remove("tmp")
    #             # terms = terms.split()
    #             terminals = ["x-terminal-emulator", "mate-terminal", "gnome-terminal", "terminator", "xfce4-terminal", "urxvt", "rxvt", "termit", "Eterm", "aterm", "uxterm", "xterm", "roxterm", "termite", "lxterminal", "terminology", "st", "qterminal", "lilyterm", "tilix", "terminix", "konsole", "kitty", "guake", "tilda", "alacritty", "hyper", "terminal", "iTerm", "mintty", "xiterm", "terminal.app", "Terminal.app", "terminal-w", "terminal.js", "Terminal.js", "conemu", "cmder", "powercmd", "terminus", "termina", "terminal-plus", "iterm2", "terminus-terminal", "terminal-tabs"]
    #             terms = []
    #             for terminal in terminals:
    #                 result = subprocess.run(['which', terminal], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #                 if result.returncode == 0:
    #                     terms.append(terminal)
                
    #             dh.idebug(terms)
    #             for t in reversed(terms):
    #                 if t == "x-terminal-emulator":
    #                     LINUX_TERMINAL_CALL = (
    #                         "x-terminal-emulator -e bash -c '%CMD'"
    #                     )
    #                 elif t == "gnome-terminal":
    #                     LINUX_TERMINAL_CALL = (
    #                         'gnome-terminal -- bash -c "%CMD; exec bash"'
    #                     )
    #             os.system(
    #                 LINUX_TERMINAL_CALL.replace(
    #                     "%CMD",
    #                     escp(sys.executable) + " " + escp(python_script) + " >/dev/null",
    #                 )
    #             )

class PowerpointExtractor(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")

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

        aepy = os.path.join(dh.si_dir, "powerpoint_extractor_script.py")
        

        # Pass settings using a config file. Include the current path so Inkex can be called if needed.
        import pickle
        optcopy.inkscape_bfn = bfn;
        optcopy.syspath = sys.path;
        optcopy.inshell = False;
        

        # import tempfile
        # aes = os.path.join(os.path.abspath(tempfile.gettempdir()), "si_ae_settings.p")
        # aes = 
        with open(dh.si_tmp(filename="si_ppe_settings.p"), "wb") as f:
            pickle.dump(optcopy, f)
        import warnings
        warnings.simplefilter("ignore", ResourceWarning); # prevent warning that process is open

        
        # gloc = os.path.join(os.path.split(aepy)[0],'Test.html')
        # with open('Test.html', 'w') as f:
        #     f.write('<!DOCTYPE html>\n')
        #     f.write('<html>\n')
        #     f.write('<body>\n')
        #     f.write('<p>Hello!</p>\n')
        #     f.write('</body>\n')
        #     f.write('</html>\n')
        # # import platform
        # # if platform.system().lower() == "windows":
        # #     os.system("open "+gloc)
        # # else:
        
            
        # import webbrowser, pathlib
        # webbrowser.open(pathlib.Path(gloc).as_uri())
        
        run_python(pybin,aepy,pyloc,optcopy.inshell)

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())


if __name__ == "__main__":
    dh.Run_SI_Extension(PowerpointExtractor(),"Autoexporter")

