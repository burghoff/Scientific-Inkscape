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

with open(aes, "rb") as f:
    input_options = pickle.load(f)
os.remove(aes)
watchdir  = input_options.watchdir
writedir  = input_options.writedir
bfn       = input_options.inkscape_bfn
sys.path += input_options.syspath
guitype   = input_options.guitype

# print('hello')
# sys.exit()

import inkex
import dhelpers as dh
import autoexporter
from autoexporter import AutoExporter, Delete_Dir

def mprint(*args,**kwargs):
    if guitype=='gtk':
        global pt
        pt.buffer.append(args[0])
    else:
        print(*args,**kwargs)

# Get svg files in directory
def get_files(dirin):
    import re
    from datetime import datetime
    def ends_with_date(s):
        pattern = r'\.(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}\.\d{1,6})\.svg$'
        match = re.search(pattern, s)
        if match:
            date_string = match.group(1)
            custom_format = "%Y_%m_%d_%H_%M_%S.%f"
            try:
                datetime.strptime(date_string, custom_format)
                return True
            except ValueError:
                return False
        return False
    
    
    fs = []
    try:
        for f in os.scandir(dirin):
            excludes = ['_portable.svg','_plain.svg']
            if f.name.endswith(".svg") and all([not(f.name.endswith(ex)) for ex in excludes]) and not(ends_with_date(f.name)):
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
class monitorThread(threading.Thread):
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
        self.finished_threads = [];
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
                            fthr = monitorThread('autoexporter')
                            fthr.file = f;
                            fthr.outtemplate = autoexporter.joinmod(self.writedir, os.path.split(f)[1])
                            self.thread_queue.append(fthr)
                        
                        MAXTHREADS = 10;
                        while len(self.thread_queue)>0 and len(self.running_threads)<MAXTHREADS and not(self.stopped):
                            self.thread_queue[0].start();
                            self.running_threads.append(self.thread_queue[0])
                            self.thread_queue.remove(self.thread_queue[0])
                            time.sleep(WHILESLEEP);
                        for thr in reversed(self.running_threads):
                            if not(thr.is_alive()):
                                self.running_threads.remove(thr)
                                self.finished_threads.append(thr)
                                self.promptpending = True
                              
                        # Debug mode: infinite loop
                        while self.dm and any([thr.is_alive() for thr in self.running_threads]):
                            time.sleep(WHILESLEEP)
                        loopme = self.dm
                                
                    if self.promptpending and len(self.running_threads)+len(self.thread_queue)==0:
                        if guitype=='terminal':
                            mprint(promptstring)
                        self.promptpending = False
                time.sleep(WHILESLEEP)
            
            # Stop any threads still running after exit
            for t in self.running_threads:
                t.stopped = True
            while any([thr.is_alive() for thr in self.running_threads]):
                time.sleep(WHILESLEEP) # let threads finish up
            for thr in reversed(self.running_threads):
                self.running_threads.remove(thr)
                self.finished_threads.append(thr)
            
            
            # Clear out leftover temp files from the last time we ran
            leftover_temps = []
            lftover_tmp = os.path.join(systmpdir, "si_ae_leftovertemp.p")
            if os.path.exists(lftover_tmp):
                with open(lftover_tmp, "rb") as f:
                    leftover_temps = pickle.load(f)
                    for tf in reversed(leftover_temps):
                        if os.path.exists(tf):
                            try:
                                os.rmdir(tf)
                                leftover_temps.remove(tf)
                            except:
                                pass
                os.remove(lftover_tmp)
            for thr in self.finished_threads:
                if hasattr(thr,'tempdir'):
                    if os.path.isdir(thr.tempdir):
                        leftover_temps.append(thr.tempdir)
            if len(leftover_temps)>0:
                with open(lftover_tmp, "wb") as f:
                    pickle.dump(leftover_temps, f)
                
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
            opts.aeThread = self;
            opts.original_file = self.file;
            ftd = AutoExporter().export_all(
                bfn, self.file, self.outtemplate, opts.formats, opts
            )

if guitype=='gtk':   
    import warnings
    with warnings.catch_warnings():
        # Ignore ImportWarning for Gtk
        warnings.simplefilter('ignore')      
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib
    
    class AutoexporterWindow(Gtk.Window):
        def __init__(self,ct):
            Gtk.Window.__init__(self, title="Autoexporter")
            self.set_default_size(500, -1)  # set width to 400 pixels, height can be automatic
            self.set_position(Gtk.WindowPosition.CENTER)
            
            self.selected_file_label = Gtk.TextView()
            self.selected_file_label.set_editable(False)
            self.selected_file_label.set_wrap_mode(Gtk.WrapMode.CHAR)
            self.selected_file_label.get_buffer().set_text('No file selected.')
            
            buffer = self.selected_file_label.get_buffer()
            # buffer.connect('insert-text', self.on_text_buffer_insert_text) # auto-scroll
    
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
            
            self.liststore = Gtk.ListStore(str, str)
            self.treeview = Gtk.TreeView(model=self.liststore)
            renderer_text = Gtk.CellRendererText()
            column_text = Gtk.TreeViewColumn("Filename", renderer_text, text=0)
            self.treeview.append_column(column_text)
            renderer_text = Gtk.CellRendererText()
            column_text = Gtk.TreeViewColumn("Message", renderer_text, text=1)
            self.treeview.append_column(column_text)
            self.scrolled_window_files = Gtk.ScrolledWindow()
            self.scrolled_window_files.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            self.scrolled_window_files.set_size_request(600, 300)
            self.scrolled_window_files.set_vexpand(True)
            self.scrolled_window_files.add(self.treeview)
            self.lsvals = [];
            
            self.liststore.connect("row-inserted", self.on_row_inserted)
            self.maxlsrows = 100;            
            # self.treeview.connect('size-allocate', self.on_treeview_size_allocate) # auto-scroll

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
            self.box.pack_start(self.scrolled_window_files, True, True, 0)
            self.box.pack_start(self.file_button, False, False, 0)
            self.box.pack_start(self.folder_button, False, False, 0)
            self.box.pack_start(self.ea_button, False, False, 0)
            self.box.pack_start(self.ef_button, False, False, 0)
            self.box.pack_start(self.exit_button, False, False, 0)
            self.add(self.box)
            
            self.ct = ct;
            
        # def on_treeview_size_allocate(self, widget, allocation):
        #     # Scroll to end after file inserted
        #     if len(self.liststore)>0:
        #         path = Gtk.TreePath.new_from_string(str(len(self.liststore)-1))
        #         column = None
        #         self.treeview.scroll_to_cell(path, column, False, 0.0, 1.0)
        
        # def on_text_buffer_insert_text(self, buffer, iter, text, length):
        #     # Scroll to end after text printed
        #     mark = buffer.get_insert()
        #     self.selected_file_label.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
            
        def on_row_inserted(self, store, path, iter):
            # Count the number of rows currently in the store
            num_rows = len(self.liststore)
    
            # If the number of rows exceeds 100, remove the oldest rows
            if num_rows > self.maxlsrows:
                for i in range(num_rows - self.maxlsrows):
                    self.liststore.remove(self.liststore.get_iter_first())
            
        def print_text(self, text):
            
            lns = text.split('\n')
            tor = []
            for ln in lns:
                if 'Export formats: ' in ln or 'Rasterization DPI: ' in ln:
                    continue
                if ':' in ln and len(ln.split(':'))==2:
                    ln2 = [v.strip(' ') for v in ln.split(':')]
                    self.liststore.append(ln2)
                    # time.sleep(0.25)
                    
                    # ms = [ii for ii in range(len(self.lsvals)) if ln2[0]==self.lsvals[ii][0]]
                    # if len(ms)==0:
                    #     self.liststore.append(ln2)
                    #     self.lsvals.append(ln2)
                    # else:
                    #     for m in reversed(ms):
                    #         nval = [self.lsvals[m][0],self.lsvals[m][1]+'\n'+ln2[1]]
                            
                    #         self.lsvals.remove(self.lsvals[m])
                    #         iterv =self.liststore.get_iter_first()
                    #         for mv in range(m):
                    #             iterv = self.liststore.iter_next(iterv)
                    #         self.liststore.remove(iterv)
                            
                    #         self.lsvals.append(nval)
                    #         self.liststore.append(nval)
                            
                            
                    #         self.liststore.remove(self.liststore.get_iter_first())
                    tor.append(ln)
            lns = [item for item in lns if item not in tor]
            text = '\n'.join(lns)
            
            if len(text)>0:
                buffer = self.selected_file_label.get_buffer()
                self.selected_file_label.get_buffer()
                start, end = buffer.get_bounds()
                if buffer.get_text(start, end, False)=='No file selected.':
                    buffer.set_text('')
                buffer.insert(buffer.get_end_iter(), text+'\n')

        def exit_clicked(self, widget):
            self.destroy()
            
        def watch_folder_button_clicked(self, widget):
            native = Gtk.FileChooserNative.new("Please choose a file or directory", self, Gtk.FileChooserAction.SELECT_FOLDER, None, None)
            response = native.run()
            if response == Gtk.ResponseType.ACCEPT:
                selected_file = native.get_filename()
                self.ct.watchdir = selected_file
                self.ct.nf = True;
            native.destroy()
            
        def write_folder_button_clicked(self, widget):
            native = Gtk.FileChooserNative.new("Please choose a file or directory", self, Gtk.FileChooserAction.SELECT_FOLDER, None, None)
            response = native.run()
            if response == Gtk.ResponseType.ACCEPT:
                selected_file = native.get_filename()
                self.ct.writedir = selected_file
                self.ct.nf = True;
            native.destroy()
            
        
        def export_all_clicked(self, widget):
            self.ct.ea = True;
            # self.ct.dm = True 
            
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
    
    fc = monitorThread('filechecker')
    fc.watchdir = watchdir
    fc.writedir = writedir
    win = AutoexporterWindow(fc)
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
                    GLib.idle_add(self.win.print_text, '\n'.join(self.buffer))
                    time.sleep(0.25)
                    self.buffer = [];
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
    fc.start();
    
    def quit_and_close(self):
        fc.stopped = True;
        pt.stopped = True;
        Gtk.main_quit();
        
    win.connect("destroy", quit_and_close)
    win.show_all()
    win.set_keep_above(False)
    Gtk.main()
else:
    try:
        import tkinter
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
    fc = monitorThread('filechecker')
    fc.watchdir = watchdir
    fc.writedir = writedir
    if fc.watchdir is None or fc.writedir is None:
        fc.watchdir, fc.writedir = Get_Directories()
    
    
    fc.start()
    while fc.nf:  # wait until it's done initializing
        pass
    t2 = monitorThread('prompt');
    t2.start()
    keeprunning = True
    while keeprunning:
        if not (t2.is_alive()):
            if t2.ui in ["Q", "q"]:
                fc.stopped = True
                keeprunning = False
            elif t2.ui in ["D", "d"]:
                if hastkinter:
                    try:
                        fc.watchdir, fc.writedir = Get_Directories()
                        fc.nf = True
                    except:
                        pass
            elif t2.ui in ["R", "r"]:
                input_options.dpi = int(input("Enter new rasterization DPI: "))
            elif t2.ui in ["A", "a"]:
                fc.ea = True
            elif t2.ui in ["F", "f"]:
                if hastkinter:
                    try:
                        fc.selectedfile = Get_File(fc.watchdir)
                        fc.es = True
                    except:
                        pass
            elif t2.ui in ["#"]:
                fc.dm = True
                # entering # starts an infinite export loop in the current dir
                fc.ea = True
            else:
                mprint("Invalid input!")
            if keeprunning:
                t2 = monitorThread('prompt')
                t2.start()
                fc.promptpending = True
        time.sleep(WHILESLEEP)
    
    # On macOS close the terminal we opened
    # https://superuser.com/questions/158375/how-do-i-close-the-terminal-in-osx-from-the-command-line
    if platform.system().lower() == "darwin":
        os.system(
            "osascript -e 'tell application \"Terminal\" to close first window' & exit"
        )
