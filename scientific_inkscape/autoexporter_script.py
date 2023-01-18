# Inkscape Auto-Exporter, by David Burghoff
# Service that checks a folder for changes in svg files, and then exports them
# automatically to another folder in multiple formats.

DEBUG = False
WHILESLEEP = 0.25;

import sys, platform, subprocess, os, threading, datetime, time, copy, pickle
import numpy as np

import tempfile
systmpdir = os.path.abspath(tempfile.gettempdir());
aes = os.path.join(systmpdir, "si_ae_settings.p")
f = open(aes, "rb")
input_options = pickle.load(f)
f.close()
os.remove(aes)

# mypath = os.path.dirname(os.path.realpath(sys.argv[0]))
# f = open(os.path.join(mypath, "ae_settings.p"), "rb")
# input_options = pickle.load(f)
# f.close()
# os.remove(os.path.join(mypath, "ae_settings.p"))

# Clear out leftover temp files from the last time we ran
# mypath = os.path.dirname(os.path.realpath(sys.argv[0]))
lftover_tmp = os.path.join(systmpdir, "si_ae_leftovertemp.p")
leftover_temps = [];
if os.path.exists(lftover_tmp):
    f = open(lftover_tmp, "rb")
    leftover_temps = pickle.load(f)
    f.close()
    os.remove(lftover_tmp)
    for tf in leftover_temps:
        if os.path.exists(tf):
            try:
                os.rmdir(tf)
                leftover_temps.remove(tf)
            except PermissionError:
                pass
        else:
            leftover_temps.remove(tf)

watchdir  = input_options.watchdir
writedir  = input_options.writedir
bfn       = input_options.inkscape_bfn
sys.path += input_options.syspath

import inkex
from inkex import Vector2d, Transform
import dhelpers as dh


import autoexporter
from autoexporter import AutoExporter

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

# Get a dict of the files and their modified times
def get_modtimes(dirin):
    fs = get_files(dirin)
    if fs is not None:
        modtimes = dict()
        for f in fs:
            try:
                modtimes[f] = os.path.getmtime(f);
            except:
                pass
        return modtimes
    else:
        return None

# Threading class
leftover_temps = [];
class myThread(threading.Thread):
    def __init__(self, threadID):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.stopped = False
        self.ui = None  # user input
        self.nf = True  # new folder
        self.ea = False # export all
        self.es = False # export selected
        self.dm = False # debug mode
        self.thread_queue = [];
        self.running_threads = [];
        self.promptpending = True;

    def run(self):
        if self.threadID == 'filechecker':
            # Main thread
            ltm = time.time()
            # genfiles = []
            while not (self.stopped):
                self.checkongoing = True
                if self.nf:
                    print("Export formats: " + ", ".join([v.upper() for v in input_options.formats]))
                    print("Rasterization DPI: " + str(input_options.dpi))
                    print("Watch directory: " + self.watchdir)
                    print("Write directory: " + self.writedir)
                    lastmod = get_modtimes(self.watchdir)
                    self.nf = False
                if time.time() > ltm + WHILESLEEP:
                    ltm = time.time()
                    
                    updatefiles = []
                    if lastmod is not None:
                        newmod = get_modtimes(self.watchdir)
                        if newmod is not None:
                            for n in newmod:
                                if n not in lastmod or newmod[n] > lastmod[n]+1:
                                    updatefiles.append(n)
                            lastmod = newmod
                    else:
                        lastmod = get_modtimes(self.watchdir)

                    if self.ea:  # export all
                        self.ea = False
                        if lastmod is not None:
                            updatefiles = list(lastmod.keys())
                        else:
                            print('Directory appears to be invalid.')
                    elif self.es:
                        self.es = False
                        updatefiles = [self.selectedfile]

                    loopme = True
                    while loopme:
                        for f in sorted(updatefiles):
                            for x in self.thread_queue+self.running_threads:
                                # Stop exports already in progress
                                if x.file == f:
                                    x.stopped = True;
                            fthr = myThread('autoexporter')
                            fthr.file = f;
                            fthr.outtemplate = autoexporter.joinmod(self.writedir, os.path.split(f)[1])
                            self.thread_queue.append(fthr)
                            
                        loopme = len(updatefiles) > 0 and self.dm
                        
                    MAXTHREADS = 10;
                    while len(self.thread_queue)>0 and len(self.running_threads)<=MAXTHREADS:
                        self.thread_queue[0].start();
                        self.running_threads.append(self.thread_queue[0])
                        self.thread_queue.remove(self.thread_queue[0])
                        time.sleep(WHILESLEEP);
                    for thr in reversed(self.running_threads):
                        if not(thr.is_alive()):
                            self.running_threads.remove(thr)
                            self.promptpending = True
                                
                    if self.promptpending and len(self.running_threads)+len(self.thread_queue)==0:
                        print(promptstring)
                        self.promptpending = False
                            
                time.sleep(WHILESLEEP)
                
        if self.threadID == 'prompt':
            self.ui = input('')
            
        if self.threadID == 'autoexporter':
            fname = os.path.split(self.file)[1];
            offset = round(os.get_terminal_size().columns/2);
            fname = fname + ' '*max(0,offset-len(fname))
            print(fname+": Beginning export")
            opts = copy.copy(input_options)
            opts.debug = DEBUG
            opts.prints = True
            opts.mythread = self;
            ftd = AutoExporter().export_all(
                bfn, self.file, self.outtemplate, opts.formats, opts
            )
            if ftd is not None:
                leftover_temps.append(ftd)


# Main loop
t1 = myThread('filechecker')
t1.watchdir = watchdir
t1.writedir = writedir
if t1.watchdir is None or t1.writedir is None:
    t1.watchdir, t1.writedir = Get_Directories()


t1.start()
while t1.nf:  # wait until it's done initializing
    pass
t2 = myThread('prompt');
t2.start()
keeprunning = True
while keeprunning:
    if not (t2.is_alive()):
        if t2.ui in ["Q", "q"]:
            t1.stopped = True
            keeprunning = False
        elif t2.ui in ["D", "d"]:
            if hastkinter:
                try:
                    t1.watchdir, t1.writedir = Get_Directories()
                    t1.nf = True
                except:
                    pass
        elif t2.ui in ["R", "r"]:
            input_options.dpi = int(input("Enter new rasterization DPI: "))
        elif t2.ui in ["A", "a"]:
            t1.ea = True
        elif t2.ui in ["F", "f"]:
            if hastkinter:
                try:
                    t1.selectedfile = Get_File(t1.watchdir)
                    t1.es = True
                except:
                    pass
        elif t2.ui in ["#"]:
            t1.dm = True
            # entering # starts an infinite export loop in the current dir
            t1.ea = True
        else:
            print("Invalid input!")
        if keeprunning:
            t2 = myThread('prompt')
            t2.start()
            t1.promptpending = True
    time.sleep(WHILESLEEP)

# On macOS close the terminal we opened
# https://superuser.com/questions/158375/how-do-i-close-the-terminal-in-osx-from-the-command-line
if platform.system().lower() == "darwin":
    os.system(
        "osascript -e 'tell application \"Terminal\" to close first window' & exit"
    )
    
if len(leftover_temps)>0:
    f = open(lftover_tmp, "wb")
    pickle.dump(leftover_temps, f)
    f.close()