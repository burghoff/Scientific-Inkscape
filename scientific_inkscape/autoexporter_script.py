# Inkscape Auto-Exporter, by David Burghoff
# Service that checks a folder for changes in svg files, and then exports them
# automatically to another folder in multiple formats.

DEBUG = False
WHILESLEEP = 0.5
MAXTHREADS = 1000

WINDOW_WIDTH = 450
MARGIN = 10
LABEL_WIDTH = 16

import sys, platform, os, threading, time, copy, pickle, re, tempfile

systmpdir = os.path.abspath(tempfile.gettempdir())
aes = os.path.join(systmpdir, "si_ae_settings.p")

with open(aes, "rb") as f:
    input_options = pickle.load(f)
os.remove(aes)
bfn = input_options.inkscape_bfn
sys.path.extend([p for p in input_options.syspath if p not in sys.path])
bfn_dir = os.path.dirname(bfn)
if bfn_dir not in sys.path:
    sys.path.append(bfn_dir)
guitype = input_options.guitype
if sys.stderr is None:
    sys.stdout = open(input_options.logfile, "w", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout

import dhelpers as dh  # noqa
import inkex
import inkex.text.parser  # noqa # needed to prevent GTK crashing

import autoexporter
from autoexporter import Exporter

global mprint
def mprint(*args, **kwargs):
    print(*args, **kwargs)

def ln_is_file(ln):
    excludes = ["Scientific Inkscape Autoexporter",
                "Python interpreter","Inkscape binary","Python"]
    if any(ln.startswith(v) for v in excludes) or  ": " not in ln:
        return False
    return True

# Get svg files in directory
def get_files(dirin):
    try:
        return [
            os.path.join(os.path.abspath(dirin), f.name)
            for f in os.scandir(dirin)
            if is_target_file(f.name)
        ]
    except: # (FileNotFoundError, OSError):
        return None
    

def is_target_file(file_name):
    flower = os.path.split(file_name)[1].lower()
    excludes = ["_portable.svg", "_plain.svg"," finalized.pptx"," finalized.docx"]
    if any(file_name.endswith(ex) for ex in excludes) or flower.startswith('~$'):
        return False
    if input_options.finalizermode>1 and  (flower.endswith(".pptx") or flower.endswith(".docx")):
        return True
    pattern = r"\.(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}\.\d{1,6})\.svg$"
    if re.search(pattern, file_name):
        return False
    return flower.endswith(".svg")

import warnings
from threading import Timer
warnings.filterwarnings(
    "ignore", message="Failed to import fsevents. Fall back to kqueue"
)
mydir = os.path.dirname(os.path.abspath(__file__))
packages = os.path.join(mydir, "packages")
if packages not in sys.path:
    sys.path.append(packages)
import os, uuid
from watchdog.observers import Observer as NativeObserver
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler


def make_observer_auto(dir_path: str):
    """
    Probe dir_path for reliable native filesystem events.
    If create/modify/delete are all detected within 2.5s,
    return a NativeObserver(); otherwise return PollingObserver(timeout=0.5).
    """
    class ProbeHandler(FileSystemEventHandler):
        def __init__(self, path):
            super().__init__()
            self.path = os.path.abspath(path)
            self.got_create = threading.Event()
            self.got_modify = threading.Event()
            self.got_delete = threading.Event()
        def _match(self, p): return os.path.abspath(p) == self.path
        def on_created(self, e): 
            if not e.is_directory and self._match(e.src_path): self.got_create.set()
        def on_modified(self, e): 
            if not e.is_directory and self._match(e.src_path): self.got_modify.set()
        def on_deleted(self, e): 
            if not e.is_directory and self._match(e.src_path): self.got_delete.set()

    os.makedirs(dir_path, exist_ok=True)
    dummy = os.path.join(dir_path, f".probe_{uuid.uuid4().hex}.tmp")
    handler = ProbeHandler(dummy)
    obs = NativeObserver()
    ok = False
    try:
        obs.schedule(handler, dir_path, recursive=False)
        obs.start()
        time.sleep(0.25)  # let backend initialize
        # create → modify → delete
        with open(dummy, "w") as f: f.write("x")
        time.sleep(0.15)
        with open(dummy, "a") as f: f.write("y")
        time.sleep(0.15)
        os.remove(dummy)
        # wait for all three events
        deadline = time.time() + 2.5
        while time.time() < deadline:
            if handler.got_create.is_set() and handler.got_modify.is_set() and handler.got_delete.is_set():
                ok = True
                break
            time.sleep(0.05)
    except Exception:
        ok = False
    finally:
        try:
            obs.stop(); obs.join(1)
        except Exception:
            pass
        if os.path.exists(dummy):
            try: os.remove(dummy)
            except Exception: pass
    if ok or not PollingObserver:
        # mprint("[watcher] using native Observer")
        return NativeObserver()
    else:
        # mprint("[watcher] using PollingObserver(timeout=1.0)")
        return PollingObserver(timeout=0.5)

class Watcher(FileSystemEventHandler):
    """Class that watches a folder for changes to SVGs"""

    def __init__(self, directory_to_watch, createfcn=None, modfcn=None, deletefcn=None):
        super().__init__()

        self.directory_to_watch = directory_to_watch
        self.createfcn = createfcn
        self.modfcn = modfcn
        self.deletefcn = deletefcn

        self.debounce_timers = {}
        self.last_event = {}
        self.file_mod_times = {}

        self.observer = make_observer_auto(directory_to_watch)
        self.start()
        self.tstart = time.time()

    def start(self):
        self.initialize_mod_times(self.directory_to_watch)
        self.observer.schedule(self, self.directory_to_watch, recursive=False)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()

    @staticmethod
    def get_mod_time(file_path):
        try:
            return os.path.getmtime(file_path)
        except FileNotFoundError:
            return None

    def initialize_mod_times(self, directory):
        for file in os.listdir(directory):
            file_path = os.path.join(directory, file)
            if os.path.isfile(file_path) and is_target_file(file_path):
                mod_time = self.get_mod_time(file_path)
                if mod_time:
                    self.file_mod_times[file_path] = mod_time

    def debounce(self, event):
        if event.event_type == "created":
            if self.createfcn:
                self.createfcn(event.src_path)
        elif event.event_type == "modified":
            if self.modfcn:
                # mprint('Go '+str(time.time()-self.tstart))
                self.modfcn(event.src_path)
        elif event.event_type == "deleted":
            if self.deletefcn:
                self.deletefcn(event.src_path)

    def handle_event(self, event):
        if event.is_directory:
            return
        if is_target_file(event.src_path):
            if event.src_path in self.debounce_timers:
                self.debounce_timers[event.src_path].cancel()
                # mprint('Cancel')
            self.last_event[event.src_path] = event
            self.debounce_timers[event.src_path] = Timer(1.0, self.debounce, [event])
            self.debounce_timers[event.src_path].start()

    def on_created(self, event):
        # mprint('Created '+event.src_path)
        self.handle_event(event)

    def on_modified(self, event):
        # mprint('Modified '+event.src_path)
        if event.is_directory:
            return
        if is_target_file(event.src_path):
            new_mod_time = self.get_mod_time(event.src_path)
            old_mod_time = self.file_mod_times.get(event.src_path)
            if new_mod_time and new_mod_time != old_mod_time:
                self.file_mod_times[event.src_path] = new_mod_time
                self.handle_event(event)

    def on_deleted(self, event):
        # mprint('Deleted '+event.src_path)
        if event.src_path in self.file_mod_times:
            del self.file_mod_times[event.src_path]
        self.handle_event(event)
        
    def on_moved(self, event):
        # mprint('Moved '+event.src_path)
        if event.is_directory:
            return
        # Treat destination as a ‘modified’ event
        class _E:
            def __init__(self, p):
                self.is_directory = False
                self.src_path = p
                self.event_type = "modified"
        self.handle_event(_E(event.dest_path))


# Threading class
class FileCheckerThread(threading.Thread):
    def __init__(self, watchdir, writedir):
        threading.Thread.__init__(self)
        self.stopped = False
        self.nf = True  # new folder
        self.ea = False  # export all
        self.es = False  # export selected
        self.dm = False  # debug mode
        self.promptpending = True
        self.watcher = None
        self.watchdir = input_options.watchdir
        self.writedir = input_options.writedir
        self.thread_queue = []
        self.running_threads = []
        self.finished_threads = []

    def queue_thread(self, f):
        for t in self.thread_queue + self.running_threads:
            if t.file == f:
                t.stopped = True
        fthr = AutoExporterThread()
        fthr.file = f
        fthr.outtemplate = autoexporter.joinmod(self.writedir, os.path.split(f)[1])
        self.thread_queue.append(fthr)

    def start_watcher(self):
        if self.watcher is not None:  # Stop existing watcher
            self.watcher.stop()
        mfcn = lambda x: self.queue_thread(os.path.abspath(x))
        self.watcher = Watcher(self.watchdir, createfcn=mfcn, modfcn=mfcn)

    def run(self):
        self.start_watcher()
        while not self.stopped:
            self.checkongoing = True
            if self.nf:
                if guitype == "terminal":
                    mprint(
                        "Export formats: "
                        + ", ".join([v.upper() for v in input_options.formats])
                    )
                    mprint("Rasterization DPI: " + str(input_options.dpi))
                    mprint("Watch directory: " + self.watchdir)
                    mprint("Write directory: " + self.writedir)
                self.nf = False

            if self.watcher.directory_to_watch != self.watchdir:
                self.start_watcher()

            if self.ea:  # export all
                self.ea = False
                updatefiles = get_files(self.watchdir)
                if updatefiles is None:
                    mprint("Cannot access watch directory.")
                    updatefiles = []
            elif self.es:
                self.es = False
                updatefiles = [self.selectedfile]
            else:
                updatefiles = []

            loopme = True
            while loopme:
                for f in sorted(updatefiles):
                    self.queue_thread(f)

                while (
                    len(self.thread_queue) > 0
                    and len(self.running_threads) < MAXTHREADS
                    and not self.stopped
                ):
                    self.thread_queue[0].start()
                    self.running_threads.append(self.thread_queue[0])
                    self.thread_queue.remove(self.thread_queue[0])
                    time.sleep(WHILESLEEP)

                for thr in reversed(self.running_threads):
                    if not thr.is_alive():
                        self.running_threads.remove(thr)
                        self.finished_threads.append(thr)
                        self.promptpending = True

                while self.dm and any([thr.is_alive() for thr in self.running_threads]):
                    time.sleep(WHILESLEEP)
                loopme = self.dm

            if self.promptpending and len(self.running_threads) + len(self.thread_queue) == 0:
                if guitype == "terminal":
                    mprint(promptstring)
                self.promptpending = False
            time.sleep(WHILESLEEP)

        self.watcher.stop()
        for t in self.running_threads:
            t.stopped = True
        while any([thr.is_alive() for thr in self.running_threads]):
            time.sleep(WHILESLEEP)
        for thr in reversed(self.running_threads):
            self.running_threads.remove(thr)
            self.finished_threads.append(thr)

class PromptThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.ui = None  # user input

    def run(self):
        self.ui = input("")


class AutoExporterThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.file = None
        self.outtemplate = None
        self.stopped = False

    def run(self):
        opts = copy.copy(input_options)
        opts.formats = [
            fmt
            for fmt, use in zip(
                ["pdf", "png", "emf", "eps", "psvg"],
                [opts.usepdf, opts.usepng, opts.useemf, opts.useeps, opts.usepsvg],
            )
            if use
        ]
        fname = os.path.split(self.file)[1]
        try:
            offset = round(os.get_terminal_size().columns / 2)
        except:
            offset = 40
        fname = fname + " " * max(0, offset - len(fname))
        if self.file.lower().endswith(".svg"):
            if not opts.formats: # finalization only
                return
            mprint(fname + ": Beginning export")
        else:
            mprint(fname + ": Beginning finalization")
        
        opts.debug = DEBUG
        opts.prints = mprint
        opts.aeThread = self
        opts.original_file = self.file
        opts.outtemplate = self.outtemplate
        opts.bfn = bfn
        try:
            if self.file.lower().endswith(".svg"):
                Exporter(self.file, opts).export_all()
            else: # non-svg: finalizing
                Exporter(self.file, opts).finalize()
        except SystemExit:
            pass
        except:
            import traceback
            error_message = f"Exception in {fname}\n"
            error_message += traceback.format_exc()
            mprint(error_message)
            
init_prints = ["Scientific Inkscape Autoexporter"]
init_prints.append("\nPython interpreter: " + sys.executable)
init_prints.append("Inkscape binary: " + bfn + "")
import image_helpers as ih
init_prints.append("Python does not have PIL, images will not be cropped"
       " or converted to JPG\n" if not ih.hasPIL else "Python has PIL\n")

fc = FileCheckerThread(input_options.watchdir,input_options.writedir)

if guitype == 'gtk3.0':  
    with warnings.catch_warnings():
        # Ignore ImportWarning for Gtk
        warnings.simplefilter("ignore")
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib, Gdk

    class AutoexporterWindow(Gtk.Window):
        def __init__(self, ct):
            Gtk.Window.__init__(self, title="Autoexporter")
            self.set_default_size(WINDOW_WIDTH, -1)
            self.set_position(Gtk.WindowPosition.CENTER)
        
            self.notebook = Gtk.Notebook()
            self.notebook.set_margin_start(MARGIN)
            self.notebook.set_margin_end(MARGIN)
            self.notebook.set_margin_top(MARGIN)
            self.notebook.set_margin_bottom(MARGIN)
            self.add(self.notebook)
        
            # Tab 1: Controls
            tab1_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.notebook.append_page(tab1_box, Gtk.Label(label="Controls"))
        
            # Top message window
            self.selected_file_label = Gtk.TextView()
            self.selected_file_label.set_editable(False)
            self.selected_file_label.set_wrap_mode(Gtk.WrapMode.CHAR)
            self.selected_file_label.get_buffer().set_text("No file selected.")
            self.message_scrolled_window = Gtk.ScrolledWindow()  # Renamed for clarity
            self.message_scrolled_window.set_size_request(WINDOW_WIDTH-2*MARGIN, 150)
            self.message_scrolled_window.set_hexpand(True)
            self.message_scrolled_window.set_vexpand(True)
            self.message_scrolled_window.add(self.selected_file_label)
            tab1_box.pack_start(self.message_scrolled_window, True, True, 0)
        
            # Bottom file log window
            self.filelogstore = Gtk.ListStore(str, str)
            self.treeview = Gtk.TreeView(model=self.filelogstore)
            renderer_text = Gtk.CellRendererText()
            column_text = Gtk.TreeViewColumn("Filename", renderer_text, text=0)
            column_text.set_fixed_width((WINDOW_WIDTH-2*MARGIN)*0.49)  # Set your desired fixed width
            self.treeview.append_column(column_text)
            renderer_text = Gtk.CellRendererText()
            column_text = Gtk.TreeViewColumn("Message", renderer_text, text=1)
            self.treeview.append_column(column_text)
            self.file_log_scrolled_window = Gtk.ScrolledWindow()  # Renamed for clarity
            self.file_log_scrolled_window.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
            )
            self.file_log_scrolled_window.set_size_request(WINDOW_WIDTH-2*MARGIN, 350)
            self.file_log_scrolled_window.set_vexpand(True)
            self.file_log_scrolled_window.add(self.treeview)
            self.filelogstore.connect("row-inserted", self.on_row_inserted)
            self.maxlsrows = 100
            self.treeview.connect("size-allocate", self.on_treeview_size_allocate)
            tab1_box.pack_start(self.file_log_scrolled_window, True, True, 0)
        
            # Separator
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            tab1_box.pack_start(separator, False, True, 0)
        
            # Watch directory
            watch_file_chooser_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            watch_file_chooser_label = Gtk.Label(label="Watch directory", xalign=0.5)  # Center text
            watch_file_chooser_label.set_width_chars(LABEL_WIDTH)  # Set fixed width
            self.watch_file_chooser_button = Gtk.FileChooserButton(title="Choose watch directory", action=Gtk.FileChooserAction.SELECT_FOLDER)
            self.watch_file_chooser_button.set_filename(input_options.watchdir)  # Set the initial folder here
            self.watch_file_chooser_button.connect("file-set", self.watch_folder_button_clicked)
            self.watch_file_chooser_button.set_hexpand(True)
            self.watch_file_chooser_button.set_halign(Gtk.Align.FILL)
            watch_file_chooser_box.pack_start(watch_file_chooser_label, False, False, 0)
            watch_file_chooser_box.pack_start(self.watch_file_chooser_button, True, True, 0)
            tab1_box.pack_start(watch_file_chooser_box, False, False, 0)
            
            # Write directory
            write_file_chooser_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            write_file_chooser_label = Gtk.Label(label="Write directory", xalign=0.5)  # Center text
            write_file_chooser_label.set_width_chars(LABEL_WIDTH)  # Set fixed width
            self.write_file_chooser_button = Gtk.FileChooserButton(title="Choose write directory", action=Gtk.FileChooserAction.SELECT_FOLDER)
            self.write_file_chooser_button.set_filename(input_options.writedir)  # Set the initial folder here
            self.write_file_chooser_button.connect("file-set", self.write_folder_button_clicked)
            self.write_file_chooser_button.set_hexpand(True)
            self.write_file_chooser_button.set_halign(Gtk.Align.FILL)
            write_file_chooser_box.pack_start(write_file_chooser_label, False, False, 0)
            write_file_chooser_box.pack_start(self.write_file_chooser_button, True, True, 0)
            tab1_box.pack_start(write_file_chooser_box, False, False, 0)
        
            # Export all button
            self.ea_button = Gtk.Button(label="Export all")
            self.ea_button.connect("clicked", self.export_all_clicked)
            tab1_box.pack_start(self.ea_button, False, False, 0)
        
            # Export file button
            self.ef_button = Gtk.Button(label="Export file")
            self.ef_button.connect("clicked", self.export_file_clicked)
            tab1_box.pack_start(self.ef_button, False, False, 0)
        
            # Exit button
            self.exit_button = Gtk.Button(label="Exit")
            self.exit_button.connect("clicked", self.exit_clicked)
            tab1_box.pack_start(self.exit_button, False, False, 0)
            


            # Tab 2: Options
            tab2_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            tab2_box.set_margin_start(10)
            tab2_box.set_margin_end(10)
            tab2_box.set_margin_top(10)
            tab2_box.set_margin_bottom(10)
            self.notebook.append_page(tab2_box, Gtk.Label(label="Options"))
        
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(b".label-bold { font-weight: bold; }")
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
            # Formats to export
            export_label = Gtk.Label(label="Formats to export", xalign=0)
            export_label.get_style_context().add_class("label-bold")
            tab2_box.pack_start(export_label, False, False, 5)
            export_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            tab2_box.pack_start(export_box, False, False, 10)
            vbox_formats = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            export_box.pack_start(vbox_formats, True, True, 0)
            self.pdf_check = Gtk.CheckButton(label="PDF")
            self.png_check = Gtk.CheckButton(label="PNG")
            self.emf_check = Gtk.CheckButton(label="EMF")
            self.eps_check = Gtk.CheckButton(label="EPS")
            self.svg_check = Gtk.CheckButton(label="Plain SVG")
            vbox_formats.pack_start(self.pdf_check, False, False, 0)
            vbox_formats.pack_start(self.png_check, False, False, 0)
            vbox_formats.pack_start(self.emf_check, False, False, 0)
            vbox_formats.pack_start(self.eps_check, False, False, 0)
            vbox_formats.pack_start(self.svg_check, False, False, 0)
        
            # Rasterization DPI
            dpi_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            export_box.pack_start(dpi_box, False, False, 0)
            dpi_label = Gtk.Label(label="Rasterization DPI")
            adj = Gtk.Adjustment(value=1.0, lower=1, upper=10000, step_increment=1,
                                 page_increment=10, page_size=0)
            self.dpi_spin = Gtk.SpinButton(adjustment=adj, digits=0)
            dpi_box.pack_start(dpi_label, False, False, 0)
            dpi_box.pack_start(self.dpi_spin, False, False, 0)
        
            # Embedded image handling options
            image_handling_label = Gtk.Label(label="Embedded image handling", xalign=0)
            image_handling_label.get_style_context().add_class("label-bold")
            tab2_box.pack_start(image_handling_label, False, False, 5)
            self.crop_check = Gtk.CheckButton(label="Crop and resample images?")
            tab2_box.pack_start(self.crop_check, False, False, 5)
        
            # Other options
            other_options_label = Gtk.Label(label="Other options", xalign=0)
            other_options_label.get_style_context().add_class("label-bold")
            tab2_box.pack_start(other_options_label, False, False, 5)
            other_options_box = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL, spacing=10
            )
            tab2_box.pack_start(other_options_box, False, False, 10)
            vbox_other_options = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=5
            )
            other_options_box.pack_start(vbox_other_options, True, True, 0)
            self.convert_text_check = Gtk.CheckButton(label="Convert text to paths")
            self.prevent_thin_lines_check = Gtk.CheckButton(
                label="Prevent thin line enhancement"
            )
            self.convert_strokes_check = Gtk.CheckButton(
                label="Convert all strokes to paths"
            )
            self.transparent_back_check = Gtk.CheckButton(
                label="Add transparent backing rectangle"
            )
            vbox_other_options.pack_start(self.convert_text_check, False, False, 0)
            vbox_other_options.pack_start(
                self.prevent_thin_lines_check, False, False, 0
            )
            vbox_other_options.pack_start(self.convert_strokes_check, False, False, 0)
            vbox_other_options.pack_start(self.transparent_back_check, False, False, 0)
            extra_margin_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            other_options_box.pack_start(extra_margin_box, False, False, 0)
            self.extra_margin_label = Gtk.Label(label="Extra margin (mm)")
            adj = Gtk.Adjustment(value=1.0, lower=0, upper=10, step_increment=0.1, page_increment=1, page_size=0)
            self.extra_margin_spin = Gtk.SpinButton(adjustment=adj, digits=1)
            extra_margin_box.pack_start(self.extra_margin_label, False, False, 0)
            extra_margin_box.pack_start(self.extra_margin_spin, False, False, 0)
        
            # PDF options
            pdf_options_label = Gtk.Label(label="PDF options", xalign=0)
            pdf_options_label.get_style_context().add_class("label-bold")
            tab2_box.pack_start(pdf_options_label, False, False, 5)
            self.omit_text_check = Gtk.CheckButton(
                label="Omit text in PDF and create LaTeX file"
            )
            tab2_box.pack_start(self.omit_text_check, False, False, 5)
            
            # Finalizer options
            finalizer_label = Gtk.Label(label="Document finalizer", xalign=0)
            finalizer_label.get_style_context().add_class("label-bold")
            tab2_box.pack_start(finalizer_label, False, False, 0)
            self.finalizer_combo = Gtk.ComboBoxText()
            self.finalizer_combo.append("1", "Do not finalize")
            self.finalizer_combo.append("2", "Embed linked images")
            self.finalizer_combo.append("3", "Embed and convert SVGs to PNGs")
            self.finalizer_combo.append("4", "Embed and delete backup PNGs")
            self.finalizer_combo.append("5", "Convert to PDF using Microsoft Office")
            self.finalizer_combo.append("6", "Convert to PDF using LibreOffice")
            self.finalizer_combo.set_active(int(getattr(input_options, "finalizermode", 1)) - 1)
            self.finalizer_combo.connect("changed", self.on_finalizer_changed)
            tab2_box.pack_start(self.finalizer_combo, False, False, 1)

        
            # Initialize from input_options
            self.pdf_check.set_active(input_options.usepdf)
            self.png_check.set_active(input_options.usepng)
            self.emf_check.set_active(input_options.useemf)
            self.eps_check.set_active(input_options.useeps)
            self.svg_check.set_active(input_options.usepsvg)
            self.dpi_spin.set_value(float(input_options.dpi))
            
            self.crop_check.set_active(input_options.imagemode2)
            self.convert_text_check.set_active(input_options.texttopath)
            self.prevent_thin_lines_check.set_active(input_options.thinline)
            self.convert_strokes_check.set_active(input_options.stroketopath)
            self.transparent_back_check.set_active(input_options.backingrect)
            self.extra_margin_spin.set_value(float(input_options.margin))
            self.omit_text_check.set_active(input_options.latexpdf)
        
            # Connect options buttons to callbacks
            self.pdf_check.connect("toggled", self.on_pdf_toggled)
            self.png_check.connect("toggled", self.on_png_toggled)
            self.emf_check.connect("toggled", self.on_emf_toggled)
            self.eps_check.connect("toggled", self.on_eps_toggled)
            self.svg_check.connect("toggled", self.on_svg_toggled)
            self.dpi_spin.connect("value-changed", self.on_dpi_changed)
            self.crop_check.connect("toggled", self.on_crop_toggled)
            self.convert_text_check.connect("toggled", self.on_convert_text_toggled)
            self.prevent_thin_lines_check.connect(
                "toggled", self.on_prevent_thin_lines_toggled
            )
            self.convert_strokes_check.connect(
                "toggled", self.on_convert_strokes_toggled
            )
            self.transparent_back_check.connect(
                "toggled", self.on_transparent_back_toggled
            )
            self.extra_margin_spin.connect("value-changed", self.on_margin_changed)
            self.omit_text_check.connect("toggled", self.on_omit_text_toggled)
        
            self.ct = ct
            self.connect("destroy", self.quit_and_close)
                            
            def print_fn(*args, **kwargs):
                GLib.idle_add(self.print_text, args[0])
            global mprint
            mprint = print_fn
            for p in init_prints:
                mprint(p)
            
        
            
        def on_finalizer_changed(self, widget):
            input_options.finalizermode = int(widget.get_active_id())
            # mprint("Finalizer mode changed:", input_options.finalizermode)


        def on_treeview_size_allocate(self, widget, allocation):
            ''' 
            Scroll to end after file inserted to File Log window
            Seems to sometimes cause GTK to crash
            '''
            if len(self.filelogstore)>0:
                path = Gtk.TreePath.new_from_string(str(len(self.filelogstore)-1))
                column = None
                self.treeview.scroll_to_cell(path, column, False, 0.0, 1.0)

        # def on_text_buffer_insert_text(self, buffer, iter, text, length):
        #     # Scroll to end after text printed
        #     mark = buffer.get_insert()
        #     self.selected_file_label.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

        def on_row_inserted(self, store, path, iter):
            # Count the number of rows currently in the store
            num_rows = len(self.filelogstore)

            # If the number of rows exceeds 100, remove the oldest rows
            if num_rows > self.maxlsrows:
                for i in range(num_rows - self.maxlsrows):
                    self.filelogstore.remove(self.filelogstore.get_iter_first())

        def print_text(self, text):
            lns = text.split("\n")
            tor = []
            for ln in lns:
                if text.startswith("Exception") or not ln_is_file(ln):
                    continue
                ln2 = [v.strip(" ") for v in ln.split(":")]
                self.filelogstore.append(ln2)
                tor.append(ln)
            lns = [item for item in lns if item not in tor]
            text = "\n".join(lns)

            if len(text) > 0:
                buffer = self.selected_file_label.get_buffer()
                self.selected_file_label.get_buffer()
                start, end = buffer.get_bounds()
                if buffer.get_text(start, end, False) == "No file selected.":
                    buffer.set_text("")
                buffer.insert(buffer.get_end_iter(), text + "\n")

        def exit_clicked(self, widget):
            self.destroy()
            
        def watch_folder_button_clicked(self, widget):
            selected_file = self.watch_file_chooser_button.get_filename()
            # Check if selected_file is None, which indicates the user clicked 'Cancel'
            if selected_file is not None:
                self.ct.watchdir = selected_file
                self.ct.nf = True
            
        def write_folder_button_clicked(self, widget):
            selected_file = self.write_file_chooser_button.get_filename()
            # Check if selected_file is None, which indicates the user clicked 'Cancel'
            if selected_file is not None:
                self.ct.writedir = selected_file
                self.ct.nf = True

        def export_all_clicked(self, widget):
            self.ct.ea = True
            # self.ct.dm = True

        def export_file_clicked(self, widget):
            native = Gtk.FileChooserNative.new(
                "Please choose a file", self, Gtk.FileChooserAction.OPEN, None, None
            )
            filter_ppt = Gtk.FileFilter()
            filter_ppt.set_name("SVG files")
            filter_ppt.add_pattern("*.svg")
            filter_ppt.add_pattern("*.docx")
            filter_ppt.add_pattern("*.pptx")
            native.add_filter(filter_ppt)
            response = native.run()
            if response == Gtk.ResponseType.ACCEPT:
                selected_file = native.get_filename()
                self.ct.selectedfile = selected_file
                self.ct.es = True
            native.destroy()

        def on_pdf_toggled(self, widget):
            input_options.usepdf = widget.get_active()
            print("PDF option toggled:", widget.get_active())

        def on_png_toggled(self, widget):
            input_options.usepng = widget.get_active()
            print("PNG option toggled:", widget.get_active())

        def on_emf_toggled(self, widget):
            input_options.useemf = widget.get_active()
            print("EMF option toggled:", widget.get_active())

        def on_eps_toggled(self, widget):
            input_options.useeps = widget.get_active()
            print("EPS option toggled:", widget.get_active())

        def on_svg_toggled(self, widget):
            input_options.usepsvg = widget.get_active()
            print("SVG option toggled:", widget.get_active())

        def on_dpi_changed(self, widget):
            input_options.dpi = widget.get_value_as_int()
            print("Rasterization DPI changed:", widget.get_value_as_int())

        def on_crop_toggled(self, widget):
            input_options.imagemode2 = widget.get_active()
            print("Crop and resample images option toggled:", widget.get_active())

        def on_convert_text_toggled(self, widget):
            input_options.texttopath = widget.get_active()
            print("Convert text to paths option toggled:", widget.get_active())

        def on_prevent_thin_lines_toggled(self, widget):
            input_options.thinline = widget.get_active()
            print("Prevent thin line enhancement option toggled:", widget.get_active())

        def on_convert_strokes_toggled(self, widget):
            input_options.stroketopath = widget.get_active()
            print("Convert all strokes to paths option toggled:", widget.get_active())

        def on_transparent_back_toggled(self, widget):
            input_options.backingrect = widget.get_active()
            print(
                "Add transparent backing rectangle option toggled:", widget.get_active()
            )

        def on_margin_changed(self, widget):
            input_options.margin = widget.get_value()
            print("Extra margin changed:", widget.get_value())

        def on_omit_text_toggled(self, widget):
            input_options.latexpdf = widget.get_active()
            print(
                "Omit text in PDF and create LaTeX file option toggled:",
                widget.get_active(),
            )
        def quit_and_close(self, *args):   # or (self, widget)
            self.ct.stopped = True
            Gtk.main_quit()

    win = AutoexporterWindow(fc)
    win.set_keep_above(True)
    fc.start()
    win.show_all()
    win.set_keep_above(False)
    Gtk.main()
    
elif guitype=='gtk4.0':
    import gi
    gi.require_version("Gtk", "4.0") # Lock to GTK 4
    from gi.repository import Gtk, GLib, Gdk, Gio, GObject, Pango
    
    class AutoExporterApp(Gtk.Application):
        def __init__(self,ct):
            super().__init__(application_id="org.scientific_inkscape.AutoExporter")
            self._win = None
            self.ct = ct
            self.watch_dir_path = None
            self.write_dir_path = None

        def do_activate(self):
            if not self._win:
                self.make_win()
            self._win.present()
            
        def make_win(self):
            self._win = Gtk.ApplicationWindow(application=self)
            self._win.set_title("Autoexporter (GTK 4.0)")
            self._win.set_default_size(WINDOW_WIDTH, -1)
            
            self.notebook = Gtk.Notebook()
            self.notebook.set_margin_start(MARGIN)
            self.notebook.set_margin_end(MARGIN)
            self.notebook.set_margin_top(MARGIN)
            self.notebook.set_margin_bottom(MARGIN)
            self._win.set_child(self.notebook)
            
            # Tab 1: Controls
            tab1_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.notebook.append_page(tab1_box, Gtk.Label(label="Controls"))
            
            # Top message window
            self.selected_file_label = Gtk.TextView()
            self.selected_file_label.set_editable(False)
            self.selected_file_label.set_wrap_mode(Gtk.WrapMode.CHAR)
            self.selected_file_label.get_buffer().set_text("No file selected.")
            self.selected_file_label.set_hexpand(True)
            self.selected_file_label.set_vexpand(True)  # so it can grow inside the scroller
            self.message_scrolled_window = Gtk.ScrolledWindow()
            self.message_scrolled_window.set_min_content_height(150)
            self.message_scrolled_window.set_hexpand(True)
            self.message_scrolled_window.set_vexpand(True)
            self.message_scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            self.message_scrolled_window.set_child(self.selected_file_label)  # (no .add in GTK4)
            tab1_box.append(self.message_scrolled_window)
            
            # Bottom file log window (GTK4 ColumnView)
            class LogEntry(GObject.GObject):
                filename = GObject.Property(type=str, default="")
                message  = GObject.Property(type=str, default="")
                def __init__(self, filename="", message=""):
                    super().__init__(); self.filename, self.message = filename, message
            def _text_col(title, getter, *, fixed_width=None, wrap=False):
                fac = Gtk.SignalListItemFactory()
                fac.connect("setup", lambda f, li: li.set_child(Gtk.Label(xalign=0)))
                def bind(f, li):
                    lbl = li.get_child(); it = li.get_item()
                    txt = "" if it is None else getter(it)
                    lbl.set_text(txt)
                    if wrap:
                        lbl.set_wrap(True); lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR); lbl.set_ellipsize(Pango.EllipsizeMode.NONE); lbl.set_hexpand(True)
                    else:
                        lbl.set_wrap(False); lbl.set_ellipsize(Pango.EllipsizeMode.END)
                fac.connect("bind", bind)
                col = Gtk.ColumnViewColumn(title=title, factory=fac); col.set_resizable(True)
                if fixed_width is not None: col.set_fixed_width(int(fixed_width))
                return col
            self.LogEntry = LogEntry
            self.filelogstore = Gio.ListStore(item_type=LogEntry)
            selection = Gtk.SingleSelection(model=self.filelogstore)
            self.treeview = Gtk.ColumnView(model=selection)
            fn_col = _text_col("Filename", lambda it: it.filename, wrap=False)
            msg_col = _text_col("Message",  lambda it: it.message,  wrap=True)
            self.treeview.append_column(fn_col)
            self.treeview.append_column(msg_col)
            fn_col.set_expand(True)
            msg_col.set_expand(True)
            self.file_log_scrolled_window = Gtk.ScrolledWindow()
            self.file_log_scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            self.file_log_scrolled_window.set_min_content_height(350)
            self.file_log_scrolled_window.set_hexpand(True); self.file_log_scrolled_window.set_vexpand(True)
            self.file_log_scrolled_window.set_child(self.treeview)
            self.maxlsrows = 100
            def _on_items_changed(model, pos, removed, added):
                n = model.get_n_items()
                if n > self.maxlsrows:
                    for _ in range(n - self.maxlsrows): model.remove(0)
                vadj = self.file_log_scrolled_window.get_vadjustment()
                if vadj: vadj.set_value(vadj.get_upper() - vadj.get_page_size())
            self.filelogstore.connect("items-changed", _on_items_changed)
            tab1_box.append(self.file_log_scrolled_window)

            # Separator
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            tab1_box.append(separator)
            
            # Watch directory
            watch_file_chooser_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            watch_file_chooser_label = Gtk.Label(label="Watch directory", xalign=10)
            watch_file_chooser_label.set_width_chars(LABEL_WIDTH)
            self.watch_dir_button = Gtk.Button()
            self.watch_dir_button.set_hexpand(True)
            self.watch_dir_button.set_halign(Gtk.Align.FILL)
            self.watch_dir_button.add_css_class("path-button")  # CSS class for min-width override
            self._watch_dir_lbl = Gtk.Label(xalign=0.0)
            self._watch_dir_lbl.set_single_line_mode(True)
            self._watch_dir_lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            self._watch_dir_lbl.set_wrap(False)
            self._watch_dir_lbl.set_width_chars(12)       # minimum hint
            self._watch_dir_lbl.set_max_width_chars(60)   # natural width cap
            self.watch_dir_button.set_child(self._watch_dir_lbl)
            self.watch_dir_path = input_options.watchdir
            self._watch_dir_lbl.set_text(self.watch_dir_path or "Choose watch directory")
            self.watch_dir_button.connect("clicked", self.watch_dir_clicked)
            watch_file_chooser_box.append(watch_file_chooser_label)
            watch_file_chooser_box.append(self.watch_dir_button)
            tab1_box.append(watch_file_chooser_box)


            # Write directory
            write_file_chooser_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            write_file_chooser_label = Gtk.Label(label="Write directory", xalign=10.0)
            write_file_chooser_label.set_width_chars(LABEL_WIDTH)
            self.write_dir_button = Gtk.Button()               # no 'label=' here
            self.write_dir_button.set_hexpand(True)
            self.write_dir_button.set_halign(Gtk.Align.FILL)
            self.write_dir_button.add_css_class("path-button") # we'll use CSS below
            self._write_dir_lbl = Gtk.Label(xalign=0.0)
            self._write_dir_lbl.set_single_line_mode(True)
            self._write_dir_lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)  # better for long paths
            self._write_dir_lbl.set_wrap(False)
            self._write_dir_lbl.set_width_chars(12)    # minimum it should try to keep
            self._write_dir_lbl.set_max_width_chars(60) # cap natural width
            self.write_dir_button.set_child(self._write_dir_lbl)
            self.write_dir_path = input_options.writedir
            self._write_dir_lbl.set_text(self.write_dir_path or "Choose write directory")
            self.write_dir_button.connect("clicked", self.write_dir_clicked)
            write_file_chooser_box.append(write_file_chooser_label)
            write_file_chooser_box.append(self.write_dir_button)
            tab1_box.append(write_file_chooser_box)
            
            # Export all button
            self.ea_button = Gtk.Button(label="Export all")
            self.ea_button.connect("clicked", self.export_all_clicked)
            tab1_box.append(self.ea_button)
            
            # Export file button
            self.ef_button = Gtk.Button(label="Export file")
            self.ef_button.connect("clicked", self.export_file_clicked)
            tab1_box.append(self.ef_button)
            
            # Exit button
            self.exit_button = Gtk.Button(label="Exit")
            self.exit_button.connect("clicked", self.exit_clicked)
            tab1_box.append(self.exit_button)
            self._win.connect("close-request", self.close_requested)
            
            # Tab 2: Options (GTK 4)
            tab2_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            tab2_box.set_margin_start(10)
            tab2_box.set_margin_end(10)
            tab2_box.set_margin_top(10)
            tab2_box.set_margin_bottom(10)
            self.notebook.append_page(tab2_box, Gtk.Label(label="Options"))
            self._build_options_tab(tab2_box)
            
            def print_fn(*args, **kwargs):
                self.print_text(args[0])
            global mprint
            mprint = print_fn
            for p in init_prints:
                mprint(p)

        def exit_clicked(self, *_args):
            self.close_requested()
            self._win.close()             # closes the window
        
        def close_requested(self, *args):
            self.ct.stopped = True
            return False

        def watch_dir_clicked(self, _btn):
            dlg = Gtk.FileDialog(title="Choose watch directory")
            if self.watch_dir_path:
                try:
                    dlg.set_initial_folder(Gio.File.new_for_path(self.watch_dir_path))
                except Exception:
                    pass
            def _done(dialog, result):
                try:
                    folder = dialog.select_folder_finish(result)
                except GLib.Error:
                    return
                if not folder:
                    return
                self.watch_dir_path = folder.get_path()
                if getattr(self, "_watch_dir_lbl", None):
                    self._watch_dir_lbl.set_text(self.watch_dir_path or "Choose watch directory")
                # inline apply
                self.ct.watchdir = self.watch_dir_path
                self.ct.nf = True
            dlg.select_folder(self._win, None, _done)
    
        def write_dir_clicked(self, _btn):
            dlg = Gtk.FileDialog(title="Choose write directory")
            if self.write_dir_path:
                try:
                    dlg.set_initial_folder(Gio.File.new_for_path(self.write_dir_path))
                except Exception:
                    pass
            def _done(dialog, result):
                try:
                    folder = dialog.select_folder_finish(result)
                except GLib.Error:
                    return
                if not folder:
                    return
                self.write_dir_path = folder.get_path()
                if getattr(self, "_write_dir_lbl", None):
                    self._write_dir_lbl.set_text(self.write_dir_path or "Choose write directory")
                self.ct.writedir = self.write_dir_path
                self.ct.nf = True
            dlg.select_folder(self._win, None, _done)
        
        def export_all_clicked(self, _btn):
            self.ct.ea = True
        
        def export_file_clicked(self, _btn):
            # GTK 4: use FileDialog (async) instead of FileChooserNative
            dlg = Gtk.FileDialog(title="Please choose a file")
            start_dir = getattr(self, "watch_dir_path", None)
            if start_dir:
                try:
                    dlg.set_initial_folder(Gio.File.new_for_path(start_dir))
                except Exception:
                    pass
            def _on_done(dialog, result):
                try:
                    gfile = dialog.open_finish(result)
                except GLib.Error:
                    return  # cancelled or error
                if not gfile:
                    return
                path = gfile.get_path()
                if not path:
                    return
                if path.lower().endswith(".svg") or path.lower().endswith(".docx") or path.lower().endswith(".pptx"):
                    self.ct.selectedfile = path
                    self.ct.es = True
                else:
                    # Optional: show a simple info dialog/toast if non-SVG selected
                    pass
            dlg.open(self._win, None, _on_done)
            
        def print_text(self, text):
            def _do():
                lns = text.splitlines()
                tor = [] 
                for ln in lns:
                    if text.startswith("Exception") or not ln_is_file(ln):
                        continue
                    key, val = [v.strip() for v in ln.split(":", 1)]
                    if key or val:
                        # Append to GTK4 model (Gio.ListStore of LogEntry)
                        self.filelogstore.append(self.LogEntry(filename=key, message=val))
                        tor.append(ln)
                # Remaining text goes to the top TextView
                rem = [item for item in lns if item not in tor]
                txt = "\n".join(rem)
                if txt:
                    buf = self.selected_file_label.get_buffer()
                    start, end = buf.get_bounds()
                    if buf.get_text(start, end, False) == "No file selected.":
                        buf.set_text("")
                    buf.insert(buf.get_end_iter(), txt + "\n")
                return False  # stop idle
            GLib.idle_add(_do)
            
        def _build_options_tab(self, parent: Gtk.Box):
            css = Gtk.CssProvider()
            css.load_from_data(b".label-bold { font-weight: bold; }")
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        
            def _hdr(text):
                lbl = Gtk.Label(label=text, xalign=0.0)
                lbl.add_css_class("label-bold")
                return lbl
        
            # Generic binders to consolidate callbacks
            def _bind_check(btn: Gtk.CheckButton, attr: str):
                btn.set_active(bool(getattr(input_options, attr)))
                btn.connect("toggled", lambda b: setattr(input_options, attr, b.get_active()))
        
            def _bind_spin(spin: Gtk.SpinButton, attr: str, *, as_int: bool = False):
                # initialize from model
                val = getattr(input_options, attr)
                spin.set_value(float(val))
                def _on_change(s):
                    v = s.get_value_as_int() if as_int else s.get_value()
                    setattr(input_options, attr, v)
                spin.connect("value-changed", _on_change)
        
            def _bind_combo_active_id(combo: Gtk.ComboBoxText, attr: str, *, to_int: bool = True):
                # assumes IDs are strings like "1", "2", ...
                cur = getattr(input_options, attr, 1)
                try:
                    combo.set_active_id(str(int(cur)))
                except Exception:
                    combo.set_active(0)
                def _on_change(c):
                    val = c.get_active_id()
                    if val is None:
                        return
                    setattr(input_options, attr, int(val) if to_int else val)
                combo.connect("changed", _on_change)
        
            # --- Formats to export ---
            parent.append(_hdr("Formats to export"))
            export_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            parent.append(export_row)
        
            # left column: format checkboxes
            fmt_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            export_row.append(fmt_col)
        
            self.pdf_check = Gtk.CheckButton(label="PDF")
            self.png_check = Gtk.CheckButton(label="PNG")
            self.emf_check = Gtk.CheckButton(label="EMF")
            self.eps_check = Gtk.CheckButton(label="EPS")
            self.svg_check = Gtk.CheckButton(label="Plain SVG")
        
            for w in (self.pdf_check, self.png_check, self.emf_check, self.eps_check, self.svg_check):
                fmt_col.append(w)
        
            _bind_check(self.pdf_check, "usepdf")
            _bind_check(self.png_check, "usepng")
            _bind_check(self.emf_check, "useemf")
            _bind_check(self.eps_check, "useeps")
            _bind_check(self.svg_check, "usepsvg")
        
            # right column: DPI
            dpi_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            export_row.append(dpi_col)
            dpi_col.append(Gtk.Label(label="Rasterization DPI", xalign=0.0))
        
            dpi_adj = Gtk.Adjustment(
                value=float(getattr(input_options, "dpi", 300)),
                lower=1, upper=10000, step_increment=1, page_increment=10, page_size=0
            )
            self.dpi_spin = Gtk.SpinButton(adjustment=dpi_adj, digits=0)
            dpi_col.append(self.dpi_spin)
            _bind_spin(self.dpi_spin, "dpi", as_int=True)
        
            # --- Embedded image handling ---
            parent.append(_hdr("Embedded image handling"))
            self.crop_check = Gtk.CheckButton(label="Crop and resample images?")
            parent.append(self.crop_check)
            _bind_check(self.crop_check, "imagemode2")
        
            # --- Other options ---
            parent.append(_hdr("Other options"))
            other_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            parent.append(other_row)
        
            left_other = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            other_row.append(left_other)
        
            self.convert_text_check = Gtk.CheckButton(label="Convert text to paths")
            self.prevent_thin_lines_check = Gtk.CheckButton(label="Prevent thin line enhancement")
            self.convert_strokes_check = Gtk.CheckButton(label="Convert all strokes to paths")
            self.transparent_back_check = Gtk.CheckButton(label="Add transparent backing rectangle")
        
            for w in (
                self.convert_text_check,
                self.prevent_thin_lines_check,
                self.convert_strokes_check,
                self.transparent_back_check,
            ):
                left_other.append(w)
        
            _bind_check(self.convert_text_check, "texttopath")
            _bind_check(self.prevent_thin_lines_check, "thinline")
            _bind_check(self.convert_strokes_check, "stroketopath")
            _bind_check(self.transparent_back_check, "backingrect")
        
            right_other = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            other_row.append(right_other)
            right_other.append(Gtk.Label(label="Extra margin (mm)", xalign=0.0))
        
            margin_adj = Gtk.Adjustment(
                value=float(getattr(input_options, "margin", 0.0)),
                lower=0.0, upper=10.0, step_increment=0.1, page_increment=1.0, page_size=0
            )
            self.extra_margin_spin = Gtk.SpinButton(adjustment=margin_adj, digits=1)
            right_other.append(self.extra_margin_spin)
            _bind_spin(self.extra_margin_spin, "margin", as_int=False)
        
            # --- PDF options ---
            parent.append(_hdr("PDF options"))
            self.omit_text_check = Gtk.CheckButton(label="Omit text in PDF and create LaTeX file")
            parent.append(self.omit_text_check)
            _bind_check(self.omit_text_check, "latexpdf")
        
            # --- Finalizer options ---
            parent.append(_hdr("Document finalizer"))
            self.finalizer_combo = Gtk.ComboBoxText()
            # IDs match stored int values for simple binding
            self.finalizer_combo.append("1", "Do not finalize")
            self.finalizer_combo.append("2", "Embed linked images")
            self.finalizer_combo.append("3", "Embed and convert SVGs to PNGs")
            self.finalizer_combo.append("4", "Embed and delete backup PNGs")
            self.finalizer_combo.append("5", "Convert to PDF using Microsoft Office")
            self.finalizer_combo.append("6", "Convert to PDF using LibreOffice")
            _bind_combo_active_id(self.finalizer_combo, "finalizermode", to_int=True)
            parent.append(self.finalizer_combo)

    app = AutoExporterApp(fc)
    fc.start()
    app.run()

else:
    try:
        import tkinter

        promptstring = ("\nEnter D to change directories, R to change DPI, F to"
        " export a file, A to export all now, and Q to quit: ")
        hastkinter = True
    except:
        promptstring = "\nEnter A to export all now, R to change DPI, and Q to quit: "
        hastkinter = False

    if platform.system().lower() == "darwin":
        mprint(" ")
    elif platform.system().lower() == "windows":
        # Disable QuickEdit, which I think causes the occasional freezes
        # From https://stackoverflow.com/questions/37500076/
        #      how-to-enable-windows-console-quickedit-mode-from-python
        def quickedit(enabled=1):
            import ctypes

            """
            Enable or disable quick edit mode to prevent system hangs,
            sometimes when using remote desktop
            Param (Enabled)
            enabled = 1(default), enable quick edit mode in python console
            enabled = 0, disable quick edit mode in python console
            """
            # -10 is input handle => STD_INPUT_HANDLE (DWORD) -10 | 
            # https://docs.microsoft.com/en-us/windows/console/getstdhandle
            # default = (0x4|0x80|0x20|0x2|0x10|0x1|0x40|0x200)
            # 0x40 is quick edit, #0x20 is insert mode
            # 0x8 is disabled by default
            # https://docs.microsoft.com/en-us/windows/console/setconsolemode
            kernel32 = ctypes.windll.kernel32
            if enabled:
                kernel32.SetConsoleMode(
                    kernel32.GetStdHandle(-10),
                    (0x4 | 0x80 | 0x20 | 0x2 | 0x10 | 0x1 | 0x40 | 0x100),
                )
                # mprint("Console Quick Edit Enabled")
            else:
                kernel32.SetConsoleMode(
                    kernel32.GetStdHandle(-10),
                    (0x4 | 0x80 | 0x20 | 0x2 | 0x10 | 0x1 | 0x00 | 0x100),
                )
                # mprint("Console Quick Edit Disabled")

        quickedit(0)  # Disable quick edit in terminal
   
    for p in init_prints:
        mprint(p)

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
        writedir = tkinter.filedialog.askdirectory(
            title="Select a directory to write to"
        )
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


    if fc.watchdir is None or fc.writedir is None:
        fc.watchdir, fc.writedir = Get_Directories()
    fc.start()
    while fc.nf:  # wait until it's done initializing
        pass
    t2 = PromptThread()
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
                t2 = PromptThread()
                t2.start()
                fc.promptpending = True
        time.sleep(WHILESLEEP)

    # On macOS close the terminal we opened
    # https://superuser.com/questions/158375/
    # how-do-i-close-the-terminal-in-osx-from-the-command-line
    if platform.system().lower() == "darwin":
        os.system(
            "osascript -e 'tell application \"Terminal\" to close first window' & exit"
        )