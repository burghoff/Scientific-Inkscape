# Inkscape Auto-Exporter, by David Burghoff
# Service that checks a folder for changes in svg files, and then exports them
# automatically to another folder in multiple formats.

DEBUG = False

import sys, platform, subprocess, os, threading, datetime, time, copy, pickle
import numpy as np

mypath = os.path.dirname(os.path.realpath(sys.argv[0]))
f = open(os.path.join(mypath, "ae_settings.p"), "rb")
input_options = pickle.load(f)
f.close()
os.remove(os.path.join(mypath, "ae_settings.p"))

watchdir  = input_options.watchdir
writedir  = input_options.writedir
bfn       = input_options.inkscape_bfn
sys.path += input_options.syspath

import inkex
from inkex import Vector2d, Transform
import dhelpers as dh

try:
    import tkinter
    from tkinter import filedialog

    promptstring = "\nEnter D to change directories, R to change DPI, F to export a file, A to export all now, and Q to quit: "
    hastkinter = True
except:
    promptstring = "\nEnter A to export all now, R to change DPI, and Q to quit: "
    hastkinter = False


if platform.system().lower() == "darwin":
    print(" ")
elif platform.system().lower()=='windows':
    # Disable QuickEdit, which I think causes the occasional freezes
    # From https://stackoverflow.com/questions/37500076/how-to-enable-windows-console-quickedit-mode-from-python
    def quickedit(enabled=1): # This is a patch to the system that sometimes hangs
        import ctypes
        '''
        Enable or disable quick edit mode to prevent system hangs, sometimes when using remote desktop
        Param (Enabled)
        enabled = 1(default), enable quick edit mode in python console
        enabled = 0, disable quick edit mode in python console
        '''
        # -10 is input handle => STD_INPUT_HANDLE (DWORD) -10 | https://docs.microsoft.com/en-us/windows/console/getstdhandle
        # default = (0x4|0x80|0x20|0x2|0x10|0x1|0x40|0x200)
        # 0x40 is quick edit, #0x20 is insert mode
        # 0x8 is disabled by default
        # https://docs.microsoft.com/en-us/windows/console/setconsolemode
        kernel32 = ctypes.windll.kernel32
        if enabled:
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), (0x4|0x80|0x20|0x2|0x10|0x1|0x40|0x100))
            # print("Console Quick Edit Enabled")
        else:
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), (0x4|0x80|0x20|0x2|0x10|0x1|0x00|0x100))
            # print("Console Quick Edit Disabled")
    quickedit(0) # Disable quick edit in terminal
    
    
print("Scientific Inkscape Autoexporter")
print("\nPython interpreter: " + sys.executable)
print("Inkscape binary: " + bfn + "")

import image_helpers as ih

if not (ih.hasPIL):
    print("Python does not have PIL, images will not be cropped or converted to JPG\n")
else:
    print("Python has PIL\n")


def Get_Directories():
    root = tkinter.Tk()
    root.geometry("1x1")
    root.lift()
    root.overrideredirect(1)
    print("Select a directory to watch")
    watchdir = tkinter.filedialog.askdirectory(title="Select a directory to watch")
    root.destroy()
    if watchdir == "":
        raise
    root = tkinter.Tk()
    root.geometry("1x1")
    root.lift()
    root.overrideredirect(1)
    print("Select a directory to write to")
    writedir = tkinter.filedialog.askdirectory(title="Select a directory to write to")
    root.destroy()
    if writedir == "":
        raise
    return watchdir, writedir


def Get_File(initdir):
    root = tkinter.Tk()
    root.geometry("1x1")
    root.lift()
    root.overrideredirect(1)
    print("Select a file to export")
    selectedfile = tkinter.filedialog.askopenfile(title="Select a file")
    root.destroy()
    selectedfile.close()
    return selectedfile.name


def get_defs(svg):
    for k in list(svg):
        if isinstance(k, (inkex.Defs)):
            return k
    d = inkex.Defs()
    # no Defs, make one
    svg.insert(len(list(svg)), d)
    return d


# Get svg files in directory
def get_files(dirin):
    fs = []
    try:
        for f in os.scandir(dirin):
            exclude = '_portable.svg'
            if f.name[-4:] == ".svg" and f.name[-len(exclude):] != exclude:
                fs.append(os.path.join(os.path.abspath(dirin), f.name))
        return fs
    except FileNotFoundError:
        return None  # directory missing (cloud drive error?)


# Threading class
class myThread(threading.Thread):
    def __init__(self, threadID):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.stopped = False
        self.ui = None  # user input
        self.nf = True
        # new folder
        self.ea = False
        # export all
        self.es = False
        # export selected
        self.dm = False
        # debug mode

    def run(self):
        if self.threadID == 1:
            # Main thread
            ltm = time.time()
            genfiles = []
            while not (self.stopped):
                if self.nf:
                    print("Export formats: " + ", ".join([v.upper() for v in input_options.formats]))
                    print("Rasterization DPI: " + str(input_options.dpi))
                    print("Watch directory: " + self.watchdir)
                    print("Write directory: " + self.writedir)
                    files = get_files(self.watchdir)
                    lastmod = [os.path.getmtime(f) for f in files]
                    self.nf = False
                if time.time() > ltm + 0.25:
                    ltm = time.time()
                    # newfiles = [fn for fn in os.listdir(watchdir) if fn[-3:]=='svg']
                    newfiles = get_files(self.watchdir)
                    if newfiles is not None:
                        newlastmod = [0 for f in newfiles]
                        for ii in range(len(newfiles)):
                            try:
                                newlastmod[ii] = os.path.getmtime(newfiles[ii])
                            except FileNotFoundError:
                                newlastmod[ii] = lastmod[ii]

                        updatefiles = []
                        if any([not (f in newfiles) for f in files]):
                            pass
                            # deleted files;
                        elif any([not (n in files) for n in newfiles]):
                            updatefiles += [n for n in newfiles if not (n in files)]
                            # new files
                        elif any(
                            [
                                newlastmod[ii] > lastmod[ii] + 1
                                for ii in range(len(files))
                            ]
                        ):  # updated files
                            updatefiles += [
                                newfiles[ii]
                                for ii in range(len(files))
                                if not (lastmod[ii] == newlastmod[ii])
                            ]
                            # for ii in range(len(files)):
                            # if newlastmod[ii]>lastmod[ii]+1:
                            # print(newlastmod[ii]-lastmod[ii])
                            # print(files[ii])
                        files = newfiles
                        lastmod = newlastmod

                    if self.ea:  # export all
                        self.ea = False
                        updatefiles = files
                    elif self.es:
                        self.es = False
                        updatefiles = [self.selectedfile]

                    # Exclude any files I made
                    for fn in genfiles:
                        if fn in updatefiles:
                            updatefiles.remove(fn)

                    loopme = True
                    genfiles
                    while loopme:
                        for f in sorted(updatefiles):
                            # while not(self.stopped):
                            print("\nExporting " + f + "")

                            import autoexporter
                            from autoexporter import AutoExporter

                            input_options.debug = DEBUG
                            input_options.prints = True

                            outtemplate = autoexporter.joinmod(
                                self.writedir, os.path.split(f)[1]
                            )
                            nfs = AutoExporter().export_all(
                                self.bfn, f, outtemplate, input_options.formats, input_options
                            )
                            genfiles += nfs

                        loopme = len(updatefiles) > 0 and self.dm
                    if len(updatefiles) > 0:
                        print(promptstring)

        if self.threadID == 2:
            self.ui = input(promptstring)

    def stop(self):
        self.stopped = True


# Main loop
t1 = myThread(1)
t1.bfn = bfn
t1.watchdir = watchdir
t1.writedir = writedir
if t1.watchdir is None or t1.writedir is None:
    t1.watchdir, t1.writedir = Get_Directories()


t1.start()
while t1.nf:  # wait until it's done initializing
    pass
t2 = myThread(2)
t2.start()
keeprunning = True
while keeprunning:
    if not (t2.is_alive()):
        if t2.ui in ["Q", "q"]:
            t1.stop()
            keeprunning = False
        elif t2.ui in ["D", "d"]:
            if hastkinter:
                try:
                    t1.watchdir, t1.writedir = Get_Directories()
                    t1.nf = True
                except:
                    pass
            t2 = myThread(2)
            t2.start()
        elif t2.ui in ["R", "r"]:
            input_options.dpi = int(input("Enter new rasterization DPI: "))
            t2 = myThread(2)
            t2.start()
        elif t2.ui in ["A", "a"]:
            t1.ea = True
            t2 = myThread(2)
            t2.start()
        elif t2.ui in ["F", "f"]:
            if hastkinter:
                try:
                    t1.selectedfile = Get_File(t1.watchdir)
                    t1.es = True
                except:
                    pass
            t2 = myThread(2)
            t2.start()
        elif t2.ui in ["#"]:
            t1.dm = True
            # entering # starts an infinite export loop in the current dir
            t1.ea = True
            t2 = myThread(2)
            t2.start()
        else:
            print("Invalid input!")
            t2 = myThread(2)
            t2.start()

# On macOS close the terminal we opened
# https://superuser.com/questions/158375/how-do-i-close-the-terminal-in-osx-from-the-command-line
if platform.system().lower() == "darwin":
    os.system(
        "osascript -e 'tell application \"Terminal\" to close first window' & exit"
    )
