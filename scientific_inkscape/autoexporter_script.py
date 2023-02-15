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
guitype   = input_options.guitype

import inkex
import dhelpers as dh
import autoexporter
from autoexporter import AutoExporter

def mprint(*args,**kwargs):
    if guitype=='gtk':
        global pt
        pt.buffer.append(args[0])
    else:
        print(*args,**kwargs)

# Get svg files in directory
def get_files(dirin):
    fs = []
    try:
        for f in os.scandir(dirin):
            exclude = '_portable.svg'
            if f.name[-4:] == ".svg" and f.name[-len(exclude):] != exclude:
                fs.append(os.path.join(os.path.abspath(dirin), f.name))
        return fs
    except:# (FileNotFoundError, OSError):
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
                    mprint("Export formats: " + ", ".join([v.upper() for v in input_options.formats]))
                    mprint("Rasterization DPI: " + str(input_options.dpi))
                    mprint("Watch directory: " + self.watchdir)
                    mprint("Write directory: " + self.writedir)
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
                            mprint('Cannot access watch directory.')
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
                        if guitype=='terminal':
                            mprint(promptstring)
                        self.promptpending = False
                            
                time.sleep(WHILESLEEP)
                
        if self.threadID == 'prompt':
            self.ui = input('')
            
        if self.threadID == 'autoexporter':
            fname = os.path.split(self.file)[1];
            try:
                offset = round(os.get_terminal_size().columns/2);
            except:
                offset = 40;
            fname = fname + ' '*max(0,offset-len(fname))
            mprint(fname+": Beginning export")
            opts = copy.copy(input_options)
            opts.debug = DEBUG
            opts.prints = mprint;
            opts.mythread = self;
            opts.original_file = self.file;
            ftd = AutoExporter().export_all(
                bfn, self.file, self.outtemplate, opts.formats, opts
            )
            if ftd is not None:
                leftover_temps.append(ftd)

if guitype=='gtk':   
    import warnings
    with warnings.catch_warnings():
        # Ignore ImportWarning for Gtk
        warnings.simplefilter('ignore')      
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
    
    class AutoexporterWindow(Gtk.Window):
        def __init__(self,ct):
            Gtk.Window.__init__(self, title="Autoexporter")
            self.set_default_size(500, -1)  # set width to 400 pixels, height can be automatic
            self.set_position(Gtk.WindowPosition.CENTER)
            
            self.selected_file_label = Gtk.TextView()
            self.selected_file_label.set_editable(False)
            self.selected_file_label.set_wrap_mode(Gtk.WrapMode.CHAR)
            self.selected_file_label.get_buffer().set_text('No file selected.')
    
            # Adding a scrolled window to the TextView
            self.scrolled_window = Gtk.ScrolledWindow()
            self.scrolled_window.set_size_request(500, 200)
            self.scrolled_window.set_hexpand(True)
            self.scrolled_window.set_vexpand(True)
            self.scrolled_window.add(self.selected_file_label)
            
            self.containing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.containing_box.set_valign(Gtk.Align.CENTER)
            self.containing_box.set_margin_top(20)
            self.containing_box.set_margin_bottom(20)
            self.containing_box.pack_start(self.scrolled_window, True, True, 0)
            # self.containing_box.pack_start(self.svg_image, False, False, 0)
    
            self.file_button = Gtk.Button(label="Select watch directory")
            self.file_button.connect("clicked", self.watch_folder_button_clicked)
            
            self.folder_button = Gtk.Button(label="Select write directory")
            self.folder_button.connect("clicked", self.write_folder_button_clicked)
            
            self.ea_button = Gtk.Button(label="Export all")
            self.ea_button.connect("clicked", self.export_all_clicked)
            
            
            self.ef_button = Gtk.Button(label="Export file")
            self.ef_button.connect("clicked", self.export_file_clicked)
            
            self.exit_button = Gtk.Button(label="Exit")
            self.exit_button.connect("clicked", self.exit_clicked)
                    
            self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.box.pack_start(self.containing_box, True, True, 0)
            self.box.pack_start(self.file_button, False, False, 0)
            self.box.pack_start(self.folder_button, False, False, 0)
            self.box.pack_start(self.ea_button, False, False, 0)
            self.box.pack_start(self.ef_button, False, False, 0)
            self.box.pack_start(self.exit_button, False, False, 0)
            self.add(self.box)
            
            self.ct = ct;
            
        def print_text(self, text):
            # buffer = self.selected_file_label.get_buffer()
            # # sz = buffer.get_char_count()
            # start, end = buffer.get_bounds()
            # if buffer.get_text(start, end, False)=='No file selected.':
            #     buffer.set_text('')
            # buffer.insert(buffer.get_end_iter(), text+'\n')
            # # end_iter = buffer.get_end_iter()
            # # buffer.move_mark(buffer.get_insert(), end_iter)
            # self.selected_file_label.scroll_to_mark(buffer.get_insert(), 0, True, 0, 0)
            
            buffer = self.selected_file_label.get_buffer()
            self.selected_file_label.get_buffer()
            start, end = buffer.get_bounds()
            if buffer.get_text(start, end, False)=='No file selected.':
                buffer.set_text('')
            buffer.insert(buffer.get_end_iter(), text+'\n')
            # bei = buffer.get_end_iter();
            # self.selected_file_label.scroll_to_iter(bei, 0.0, True, 0.0, 1.0)
            # self.selected_file_label.scroll_to_mark(buffer.get_insert(), 0.0, True, 0.0, 1.0)
            
            # bi = buffer.get_insert();
            
            # start, end = buffer.get_bounds()
            # self.selected_file_label.get_buffer().place_cursor(end)
            # self.selected_file_label.scroll_mark_onscreen(buffer.get_insert())


        def exit_clicked(self, widget):
            self.destroy()
            
        def watch_folder_button_clicked(self, widget):
            native = Gtk.FileChooserNative.new("Please choose a file or directory", self, Gtk.FileChooserAction.SELECT_FOLDER, None, None)
            response = native.run()
            if response == Gtk.ResponseType.ACCEPT:
                selected_file = native.get_filename()
                # self.print_text(selected_file)
                self.ct.watchdir = selected_file
                self.ct.nf = True;
                # process_selection(selected_file)
            native.destroy()
            
        def write_folder_button_clicked(self, widget):
            native = Gtk.FileChooserNative.new("Please choose a file or directory", self, Gtk.FileChooserAction.SELECT_FOLDER, None, None)
            response = native.run()
            if response == Gtk.ResponseType.ACCEPT:
                selected_file = native.get_filename()
                # self.print_text(selected_file)
                self.ct.writedir = selected_file
                self.ct.nf = True;
            native.destroy()
            
        
        def export_all_clicked(self, widget):
            self.ct.ea = True;
            
        def export_file_clicked(self, widget):
            native = Gtk.FileChooserNative.new("Please choose a file", self, Gtk.FileChooserAction.OPEN, None, None)
            filter_ppt = Gtk.FileFilter()
            filter_ppt.set_name("SVG files")
            filter_ppt.add_pattern("*.svg")
            native.add_filter(filter_ppt)
            response = native.run()
            if response == Gtk.ResponseType.ACCEPT:
                selected_file = native.get_filename()
                self.ct.selectedfile = selected_file
                self.ct.es = True;
            native.destroy()
    
    t1 = myThread('filechecker')
    t1.watchdir = watchdir
    t1.writedir = writedir
    win = AutoexporterWindow(t1)
    win.set_keep_above(True)
    
    class printThread(threading.Thread):
        def __init__(self, win):
            threading.Thread.__init__(self)
            self.win = win;
            self.stopped = False;
            self.buffer = [];
        def run(self):
            while not(self.stopped):
                if len(self.buffer)>0:
                    self.win.print_text('\n'.join(self.buffer));
                    self.buffer = [];
                time.sleep(0.5)
    global pt
    pt = printThread(win);
    pt.start();
    
    mprint("Scientific Inkscape Autoexporter")
    mprint("\nPython interpreter: " + sys.executable)
    mprint("Inkscape binary: " + bfn + "")
    
    import image_helpers as ih
    
    if not (ih.hasPIL):
        mprint("Python does not have PIL, images will not be cropped or converted to JPG\n")
    else:
        mprint("Python has PIL\n")
    t1.start();
    
    def quit_and_close(self):
        Gtk.main_quit();
        t1.stopped = True;
        pt.stopped = True;
        pid = os.getpid()
        import signal
        os.kill(pid, signal.SIGINT) # or signal.SIGTERM
        
    win.connect("destroy", quit_and_close)
    win.show_all()
    win.set_keep_above(False)
    Gtk.main()
else:
    try:
        import tkinter
        from tkinter import filedialog
    
        promptstring = "\nEnter D to change directories, R to change DPI, F to export a file, A to export all now, and Q to quit: "
        hastkinter = True
    except:
        promptstring = "\nEnter A to export all now, R to change DPI, and Q to quit: "
        hastkinter = False
    
    
    if platform.system().lower() == "darwin":
        mprint(" ")
    elif platform.system().lower()=='windows':
        # Disable QuickEdit, which I think causes the occasional freezes
        # From https://stackoverflow.com/questions/37500076/how-to-enable-windows-console-quickedit-mode-from-python
        def quickedit(enabled=1): # This is a patch to the system that sometimes hang
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
                # mprint("Console Quick Edit Enabled")
            else:
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), (0x4|0x80|0x20|0x2|0x10|0x1|0x00|0x100))
                # mprint("Console Quick Edit Disabled")
        quickedit(0) # Disable quick edit in terminal
        
        
    mprint("Scientific Inkscape Autoexporter")
    mprint("\nPython interpreter: " + sys.executable)
    mprint("Inkscape binary: " + bfn + "")
    
    import image_helpers as ih
    
    if not (ih.hasPIL):
        mprint("Python does not have PIL, images will not be cropped or converted to JPG\n")
    else:
        mprint("Python has PIL\n")
    
    
    def Get_Directories():
        root = tkinter.Tk()
        root.geometry("1x1")
        root.lift()
        root.overrideredirect(1)
        mprint("Select a directory to watch")
        watchdir = tkinter.filedialog.askdirectory(title="Select a directory to watch")
        root.destroy()
        if watchdir == "":
            raise
        root = tkinter.Tk()
        root.geometry("1x1")
        root.lift()
        root.overrideredirect(1)
        mprint("Select a directory to write to")
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
        mprint("Select a file to export")
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
                mprint("Invalid input!")
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