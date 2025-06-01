# Inkscape Gallery Viewer, by David Burghoff
# Copyright (c) 2023 David Burghoff <burghoff@utexas.edu>
# Prints written to [temp]/si_gv_output.txt

# Load the settings file
import tempfile, os, pickle, sys
settings = os.path.join(
    os.path.abspath(tempfile.gettempdir()), "si_gv_settings.p"
)
with open(settings, "rb") as f:
    input_options = pickle.load(f)

bfn = input_options.inkscape_bfn
sys.path.extend([p for p in input_options.syspath if p not in sys.path])
bfn_dir = os.path.dirname(bfn)
if bfn_dir not in sys.path:
    sys.path.append(bfn_dir)
PORTNUMBER = input_options.portnum
sys.stdout = open(input_options.logfile, "w", encoding="utf-8", errors="replace")
sys.stderr = sys.stdout

import sys, subprocess, threading, time, chardet
import random
import webbrowser, pathlib
from urllib import parse
import warnings
import re
from threading import Thread
import zipfile
import shutil
import hashlib
import requests
import builtins

import dhelpers as dh
import inkex
from autoexporter import ORIG_KEY
from autoexporter import DUP_KEY
from autoexporter import hash_file

WHILESLEEP = 0.25
IMAGE_WIDTH = 175
IMAGE_HEIGHT = IMAGE_WIDTH * 0.7
MAXATTEMPTS = 1

original_print = print


def mprint(*args, **kwargs):
    original_print(*args, **kwargs, flush=True)


builtins.print = mprint

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    guitype = "gtk"
except:
    try:
        import tkinter as tk
        from tkinter import filedialog

        guitype = "tkinter"
    except:
        guitype = "terminal"

current_script_directory = os.path.dirname(os.path.abspath(__file__))
sys.path += [os.path.join(current_script_directory, "packages")]

def file_uri_to_path(file_uri, path_class=pathlib.PurePath):
    # https://stackoverflow.com/questions/5977576/is-there-a-convenient-way-to-map-a-file-uri-to-os-path
    """
    This function returns a pathlib.PurePath object for the supplied file URI.

    :param str file_uri: The file URI ...
    :param class path_class: The type of path in the file_uri. By default it uses
        the system specific path pathlib.PurePath, to force a specific type of path
        pass pathlib.PureWindowsPath or pathlib.PurePosixPath
    :returns: the pathlib.PurePath object
    :rtype: pathlib.PurePath
    """
    windows_path = isinstance(path_class(), pathlib.PureWindowsPath)
    file_uri_parsed = parse.urlparse(file_uri)
    file_uri_path_unquoted = parse.unquote(file_uri_parsed.path)
    if windows_path and file_uri_path_unquoted.startswith("/"):
        result = path_class(file_uri_path_unquoted[1:])
    else:
        result = path_class(file_uri_path_unquoted)
    if result.is_absolute() == False:
        raise ValueError(
            "Invalid file uri {} : resulting path {} not absolute".format(
                file_uri, result
            )
        )
    return result

refreshapp = False

def trigger_refresh():
    global refreshapp
    refreshapp = True
    
def show_in_file_browser(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"The path {path} does not exist.")

    # Resolve the absolute path
    path = os.path.abspath(path)

    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes

        # Define necessary Windows types and constants
        LPCTSTR = wintypes.LPCWSTR
        # HWND = wintypes.HWND
        UINT = wintypes.UINT
        LPVOID = ctypes.c_void_p

        # Define the functions
        SHOpenFolderAndSelectItems = ctypes.windll.shell32.SHOpenFolderAndSelectItems
        ILCreateFromPathW = ctypes.windll.shell32.ILCreateFromPathW
        ILFree = ctypes.windll.shell32.ILFree

        # Create an ITEMIDLIST for the path
        ILCreateFromPathW.restype = LPVOID
        ILCreateFromPathW.argtypes = [LPCTSTR]
        pidl = ILCreateFromPathW(path)

        if not pidl:
            raise FileNotFoundError(f"Unable to get PIDL for path: {path}")

        # Open the folder and select the item
        SHOpenFolderAndSelectItems.restype = ctypes.HRESULT
        SHOpenFolderAndSelectItems.argtypes = [LPVOID, UINT, LPVOID, UINT]
        res = SHOpenFolderAndSelectItems(pidl, 0, None, 0)

        # Free the ITEMIDLIST
        ILFree.argtypes = [LPVOID]
        ILFree(pidl)

        if res != 0:
            raise OSError(f"Failed to open folder and select item. HRESULT: {res}")

    elif sys.platform == "darwin":  # macOS
        # Use AppleScript to bring Finder to the front
        script = f'''
        tell application "Finder"
            activate
            reveal POSIX file "{path}"
        end tell
        '''
        subprocess.run(['osascript', '-e', script])

    elif sys.platform.startswith("linux"):
        directory, file = os.path.split(path)
        # Open the directory and select the file using Nautilus or default file manager
        subprocess.Popen(['xdg-open', directory])

    else:
        raise OSError(f"Unsupported OS: {sys.platform}")

truepath = dict()
truepath_lock = threading.Lock();

app = None
app_lock = threading.Lock();
def Make_Flask_App():
    warnings.simplefilter("ignore", DeprecationWarning)
    # prevent warning that process is open
    from flask import Flask, request, url_for, jsonify, send_from_directory, render_template, abort

    global app
    app = Flask(__name__, template_folder='.')

    @app.route("/images/<folder>/<path:path>")
    def send_image(folder, path):
        with truepath_lock:
            tp = truepath.get(folder)
        if tp is None:
            abort(404)  # Sends a 404 response
        return send_from_directory(os.path.abspath(tp), path)

    @app.route("/")
    def index():
        # Render the gallery page (without data, which will be fetched via AJAX)
        return render_template("gallery_viewer_template.html", image_width=IMAGE_WIDTH, image_height=IMAGE_HEIGHT, port=PORTNUMBER)


    def get_folder_key(folder):
        with truepath_lock:
            temp_dir_name = os.path.split(temp_dir)[-1]
            if folder not in truepath.values():
                key = temp_dir_name + "-dir" + str(random.randint(1, 100000))
                while key in truepath:
                    key = temp_dir_name + "-dir" + str(random.randint(1, 100000))
                truepath[key] = folder
            else:
                key = next(key for key, value in truepath.items() if value == folder)
        return key
    
    
    from functools import lru_cache
    @lru_cache(maxsize=None)
    def cached_url(path):
        folder, filename = os.path.split(path)
        return url_for("send_image", path=filename, folder=get_folder_key(folder))

    @app.route("/gallery_data")
    def gallery_data():
        # Collect the gallery data to be sent dynamically
        gallery_data = []
        tic = time.time()
        for fp in processors:
            files_data = []
            for ii, f in enumerate(fp.files):
                if fp.files[ii].slidename not in [None,"Document"]:
                    label = fp.files[ii].slidename
                else:
                    pn = (
                            " ({0})".format(fp.files[ii].pagenum)
                            if fp.files[ii].pagenum is not None
                            else ""
                        )
                    label = os.path.split(f.name)[-1] + pn
    
                # Determine currenttype accurately
                base, ext = os.path.splitext(f.name)
                ext = ext.upper().strip('.')
                if fp.isdir:
                    currenttype = "Current"
                elif fp.files[ii].islinked:
                    currenttype = f"Linked {ext}"
                else:
                    currenttype = f"Embedded {ext}"
                
                file_url = cached_url(f.name)
                thumbnail_url = cached_url(fp.files[ii].thumbnail)
    
                embed_val = f.original_uri if f.original_present else (None if f.original is None else 'Missing: '+f.original)
    
                # Add file data
                files_data.append({
                    "file_url": file_url,
                    "thumbnail_url": thumbnail_url,
                    "file_uri": f.name_uri,
                    "label": label,
                    "currenttype": currenttype,
                    "embed": embed_val,
                })
            processing = not fp.run_on_fof_done or any(not t.done for t in fp.cthreads)
            gallery_data.append({
                "header": fp.header,
                "files": files_data,
                "processing": processing
            })
    
        # Return gallery data as JSON
        print(f'Done jsonifying in {time.time()-tic}')
        return jsonify(gallery_data=gallery_data)



    @app.route("/stop")
    def stop():
        func = request.environ.get("werkzeug.server.shutdown")
        if func is None:
            raise RuntimeError("Not running with the Werkzeug Server")
        func()
        return "Server shutting down..."

    @app.route("/process", methods=["GET"])
    def process():
        param = request.args.get("param")
        svg_file = file_uri_to_path(param)
        if svg_file is not None:
            print("Opening " + str(svg_file))
            warnings.simplefilter("ignore", ResourceWarning) # prevent process open warning
            if str(svg_file).endswith(".emf") or str(svg_file).endswith(".wmf"):
                subprocess.Popen([bfn,svg_file])
                return f"The parameter received is: {param}"

            with OpenWithEncoding(svg_file) as f:
                file_content = f.read()
                
                if DUP_KEY in file_content:
                    deembedsmade = False
                    while not (deembedsmade):
                        deembeds = os.path.join(temp_dir, "deembeds")
                        deembedsmade = os.path.exists(deembeds)
                        if not (deembedsmade):
                            os.mkdir(deembeds)

                    tsvg = os.path.join(
                        deembeds, "tmp_" + str(len(os.listdir(deembeds))) + ".svg"
                    )
                    svg = dh.svg_from_file(svg_file)

                    for d in svg.descendants2():
                        if (
                            isinstance(d, inkex.TextElement)
                            and d.text is not None
                            and DUP_KEY in d.text
                        ):
                            dupid = d.text[len(DUP_KEY + ": ") :]
                            dup = svg.getElementById(dupid)
                            if dup is not None:
                                dup.delete()
                            g = d.getparent()
                            d.delete()
                            if g is not None and len(g)==1:
                                g.set("display", None)  # office converts to att
                                g.cstyle["display"] = None
                                list(g)[0].set_id(dupid)
                                dh.ungroup(g)

                    dh.overwrite_svg(svg, tsvg)
                    subprocess.Popen([bfn, tsvg])
                else:
                    subprocess.Popen([bfn, svg_file])

        return f"The parameter received is: {param}"
    
    @app.route("/show_file", methods=["GET"])
    def show_file():
        param = request.args.get("param")
        svg_file = file_uri_to_path(param)
        if svg_file is not None:
            print("Showing in file browser: " + str(svg_file))
            show_in_file_browser(str(svg_file))
        return f"The parameter received is: {param}"

    @app.route("/check_for_refresh")
    def check_for_refresh():
        global refreshapp, lastupdate, openedgallery
        openedgallery = True
        if refreshapp:
            refreshapp = False
            lastupdate = time.time()
        return jsonify(lastupdate=lastupdate)

    def run_flask():
        app.run(port=PORTNUMBER)

    thread = Thread(target=run_flask)
    thread.start()

temp_dir, temp_head = dh.shared_temp("gv")
temp_base = os.path.join(temp_dir,temp_head)
MAXTHREADS = 10
conv_sema = threading.Semaphore(MAXTHREADS)

# Opens a file with unknown encoding, trying utf-8 first
# chardet can be slow
class OpenWithEncoding:
    def __init__(self, filename, mode="r"):
        self.filename = filename
        self.mode = mode
        self.file = None

    def __enter__(self):
        try:
            self.file = open(self.filename, self.mode, encoding="utf-8")
        except UnicodeDecodeError:
            with open(self.filename, "rb") as f:
                raw_data = f.read()
                result = chardet.detect(raw_data)
                encoding = result["encoding"]

            self.file = open(self.filename, self.mode, encoding=encoding)

        return self.file

    def __exit__(self, exc_type, exc_value, traceback):
        if self.file is not None:
            self.file.close()
        return False  # Don't suppress exceptions

cthread_no = 0
cthread_lock = threading.Lock()
class ConversionThread(threading.Thread):
    # Converts an EMF/WMF to PNG to be used as a thumbnail
    def __init__(self, filein, parent_watcher, fileout):
        super().__init__()
        self.file = filein
        self.parent = parent_watcher  # Reference to the parent class instance
        self.done = False
        self.fileout = fileout
        
        global cthread_no
        with cthread_lock:
            self.no = cthread_no
            cthread_no += 1

    def run(self):
        fname = self.file.name

        # Read and hash the input file to check for duplicates
        with open(fname, "rb") as file:
            file_content = file.read()
            hashed = hashlib.sha256(file_content).hexdigest()


        # Check if the file has already been converted
        if hashed not in converted_files:
            print("Starting export of "+fname)

            # Generate a unique conversion path
            conv_path = os.path.join(temp_dir, f"{temp_head}_conv{self.no}.png")

            # Remove existing output file if it exists
            if os.path.exists(self.fileout):
                os.remove(self.fileout)
                
            try:
                from PIL import Image
                with open(fname, "rb") as file:
                    with Image.open(file) as im:
                        width, height = im.size
                        new_width = 400
                        
                        if fname.endswith('.wmf'):
                            DEFAULT_DPI = 72
                            new_dpi = max(10,int(new_width / width * DEFAULT_DPI))
                            im.load(dpi=new_dpi)
                            width, height = im.size
                        
                        new_height = int((new_width / width) * height)
                        if 'info' in im.__dict__ and "dpi" in im.info and isinstance(im.info["dpi"],tuple) and len(im.info["dpi"]) == 2:
                            # print(im.info['dpi'])
                            new_height = int((new_width / width * im.info["dpi"][0]/im.info["dpi"][1]) * height)
                        resized_image = im.resize((new_width, new_height), Image.LANCZOS)
                        resized_image.save(conv_path)
                        print('PIL export of '+fname + ' originally '+str(width)+' x '+str(height))
            except Exception as e:
                print(f"Failed export: {e}")
                args = [
                    bfn,
                    "--export-area-drawing",
                    "--export-background",
                    "#ffffff",
                    "--export-background-opacity",
                    "1.0",
                    "--export-width",
                    "400",
                    "--export-filename",
                    conv_path,
                    fname,
                ]
                # Execute the conversion command
                with conv_sema:
                    print('Inkscape export of '+fname)
                    try:
                        dh.subprocess_repeat(args)
                    except subprocess.CalledProcessError:
                        ws = os.path.join(dh.si_dir,'pngs','cannot_display.png')
                        shutil.copy(ws, conv_path)
                    
                    if not os.path.exists(conv_path):
                        # Still no png, probably a blank file
                        ws = os.path.join(dh.si_dir,'pngs','white_square.png')
                        shutil.copy(ws, conv_path)

            # Move the converted file to the final destination
            shutil.move(conv_path, self.fileout)
            print("Finished export...")

            # Trigger a refresh and update the converted files dictionary
            converted_files[hashed] = self.fileout
        else:
            # If already converted, copy the existing file
            shutil.copy2(converted_files[hashed], self.fileout)
        if os.path.exists(self.fileout):
            self.file.thumbnail = self.fileout
            trigger_refresh()
        self.done = True

class DisplayedFile():
    """ Represents a single file we are displaying """
    def __init__(self,val):
        self.name = str(val); # actual file
        if self.name.endswith(".emf"):
            self.thumbnail = os.path.join(dh.si_dir,'pngs','converting_emf.svg')
        elif self.name.endswith(".wmf"):
            self.thumbnail = os.path.join(dh.si_dir,'pngs','converting_wmf.svg')
        else:
            self.thumbnail = self.name
        self.name_uri = pathlib.Path(self.name).as_uri()
        self.slidename = None
        self.islinked = False
        self.original = None
        self.original_uri = None
        self.original_present = False
        self.pagenum = None
        
    def __str__(self):
        return self.name
    
    def __lt__(self, other):
        if isinstance(other, DisplayedFile):
            return self.name < other.name
        return self.name < other  # Fallback for comparing with strings

wthread_no = 0
wthread_lock = threading.Lock()
class Processor(threading.Thread):
    """ Creates a gallery for a single selection, either a file or folder """
    def __init__(self, file_or_folder, opened=True):
        threading.Thread.__init__(self)
        self.fof = file_or_folder
        self.isdir = not os.path.isfile(self.fof)
        
        self.open_at_load = opened
        self.run_on_fof_done = False
        
        self.files = []
        self.header = self.fof
        self.cthreads = []  # conversion threads
        
        global wthread_no
        with wthread_lock:
            self.no = wthread_no
            wthread_no += 1
        
    def create_fcn(self,path):
        print(f"Created: {path}")
        self.run_on_fof()
    def mod_fcn(self,path):
        print(f"Modified: {path}")
        self.run_on_fof()
    def delete_fcn(self,path):
        print(f"Deleted: {path}")
        # self.run_on_fof()

    def run_on_file(self, contents):
        # Unzip the ppt file to the temp directory, allowing for multiple
        # attempts in case the file was not originally found (which can 
        # happen in cloud drives)
        if self.fof.endswith(".pptx") or self.fof.endswith(".pptm"):
            ftype = "ppt"
        elif self.fof.endswith(".one"):
            ftype = "onenote"
        else:
            ftype = "word"

        print(f'Unzipping {self.fof}')
        if ftype == "onenote":
            media_dir = os.path.join(contents, ftype)
            os.mkdir(media_dir)
            from office import get_images_onenote
            get_images_onenote(self.fof,media_dir)
        else:
            from office import Unzipped_Office
            media_dir = os.path.join(contents, ftype, "media")
            attempts = 0
            max_attempts = 3
            while attempts < max_attempts:
                try:
                    uzo = Unzipped_Office(self.fof,contents)
                    break  # Exit the loop if successful
                except zipfile.BadZipFile:
                    attempts += 1
                    if attempts == max_attempts:
                        self.run_on_fof_done = True
                        print(f'Could not unzip {self.fof} after {max_attempts} attempts.')
                        return
                    else:
                        print(f'Attempt {attempts} to unzip {self.fof} failed. Retrying...')
        self.files = []
        if os.path.exists(media_dir):
            self.files += Processor.get_svgs(media_dir)
        trigger_refresh()
            
        if ftype in ['ppt','word']:
            tidx = uzo.get_target_index()
            
            # Flatten and sort
            sorted_items = sorted(
                [(abs_path, slide_name, mode) for abs_path, slides in tidx.items() for slide_name, mode in slides],
                key=lambda x: (
                    re.match(r'^(.*?)[\s_]?(\d+)?$', x[1]).group(1).strip().lower(),  # word portion
                    int(re.match(r'^(.*?)[\s_]?(\d+)?$', x[1]).group(2)) if re.match(r'^(.*?)[\s_]?(\d+)?$', x[1]).group(2) else float('inf'),  # numeric portion, inf if absent
                    os.path.basename(x[0]).lower(),  # filename
                    x[2] == "embed"  # embed comes after link
                )
            )
            
            self.files = []
            for abs_path, slide_name, mode in sorted_items:
                if should_display(abs_path):
                    f = DisplayedFile(abs_path)
                    f.slidename = slide_name
                    f.islinked = (mode == "link")
                    self.files.append(f)
        trigger_refresh()

        subfiles = None
        for ii, fv in enumerate(self.files):
            ev = False
            orig_file = None
            if fv.name.endswith(".svg") and os.path.exists(fv.name):
                with OpenWithEncoding(fv.name) as f:
                    file_content = f.read()
                    if ORIG_KEY in file_content:
                        key = ORIG_KEY + r":\s*(.+?)<"
                        match = re.search(key, file_content)
                        if match:
                            orig_file = match.group(1)
                            orig_hash = None
                            if (
                                ", hash: " in orig_file
                            ):  # introduced hashing later than ORIG_KEY
                                orig_file, orig_hash = orig_file.split(
                                    ", hash: "
                                )
                                
                            # Gather directory names we consider identical
                            # from the config file
                            idir_groups = dh.si_config.identical_dirs_gv
                            ipaths = []
                            of_abs = os.path.abspath(orig_file)
                            for idirg in idir_groups:
                                for idir in idirg:
                                    id_abs = os.path.abspath(idir)
                                    if id_abs in of_abs:
                                        for idir2 in idirg:
                                            if not idir==idir2:
                                                ipaths.append(of_abs.replace(id_abs,os.path.abspath(idir2)))
                                                
                            subdirs = dh.si_config.subdirs_gv
                            for ipth in ipaths[:]:
                                for sd in subdirs:
                                    dn = os.path.dirname(ipth)
                                    bn = os.path.basename(ipth)
                                    ipaths.append(os.path.join(dn,sd,bn))
                                    
                            if 'EOSAM' in of_abs:
                                print(ipaths)
                                                
                            ipaths = [of_abs] + ipaths
                                
                            if any(os.path.exists(p) for p in ipaths):
                                ev = [p for p in ipaths if os.path.exists(p)][0]
                            # else:
                            #     # Check subdirectories of the file's location in case it was moved

                            #     def list_all_files(directory):
                            #         for dirpath, dirs, files in os.walk(
                            #             directory
                            #         ):
                            #             for filename in files:
                            #                 yield os.path.join(
                            #                     dirpath, filename
                            #                 )

                            #     fndir = os.path.split(self.fof)[0]
                            #     subfiles = (
                            #         list(list_all_files(fndir))
                            #         if subfiles is None
                            #         else subfiles
                            #     )

                            #     for tryfile in subfiles:
                            #         if os.path.split(orig_file)[
                            #             -1
                            #         ] == os.path.split(tryfile)[-1] and (
                            #             orig_hash is None
                            #             or hash_file(tryfile) == orig_hash
                            #         ):
                            #             ev = os.path.abspath(tryfile)
                            #             break

            if ev and orig_file is not None:
                self.files[ii].original=ev
                self.files[ii].original_uri = pathlib.Path(ev).as_uri()
                self.files[ii].original_present = True
            elif orig_file is not None:
                self.files[ii].original=orig_file
        
    def run_on_folder(self):
        self.files = Processor.get_svgs(self.fof)
        trigger_refresh()

        ii = 0
        while ii < len(self.files):
            fn = self.files[ii].name
            svg_pgs = []
        
            # Check if the file is an SVG file
            if fn.endswith(".svg"):
                with OpenWithEncoding(fn) as f:
                    try:
                        contents = f.read()
                    except OSError:
                        raise(f'Could not open {fn}')
                    if re.search(r"<\s*inkscape:page[\s\S]*?>", contents):
                        svg = dh.svg_from_file(fn)
                        pgs = svg.cdocsize.pgs
                        haspgs = inkex.installed_haspages
                        # If the file has multiple pages, split it
                        if haspgs and len(pgs) > 0:
                            vbs = [svg.cdocsize.pxtouu(pg.bbpx) for pg in pgs]
                            for vb in vbs:
                                svg.set_viewbox(vb)
                                tnsvg = os.path.join(self.tndir, str(self.numtns) + ".svg")
                                self.numtns += 1
                                dh.overwrite_svg(svg, tnsvg)
                                svg_pgs.append(tnsvg)
        
            # If thumbnails were created (multiple pages), update files and thumbnails lists
            if len(svg_pgs) > 0:
                nfiles = [DisplayedFile(fn) for t in svg_pgs]
                for i, n in enumerate(nfiles):
                    n.thumbnail = svg_pgs[i]
                    n.pagenum = i+1
                self.files[ii:ii + 1] = nfiles
                trigger_refresh()
                ii += len(nfiles)
            else:
                ii += 1

    @staticmethod
    def get_svgs(dirin):
        svg_filenames = []
        for file in os.listdir(dirin):
            if should_display(file):
                svg_filenames.append(DisplayedFile(os.path.join(dirin, file)))
        svg_filenames.sort()
        return svg_filenames

    def run_on_fof(self):
        print("Running on file: " + self.fof)

        contents = os.path.join(
            temp_dir, f"{temp_head}_cont{self.no}"
        )
        if not (os.path.exists(contents)):
            os.mkdir(contents)

        self.tndir = os.path.join(contents, "thumbnails")
        if not os.path.exists(self.tndir):
            os.makedirs(self.tndir)
        self.numtns = len(os.listdir(self.tndir))

        if not self.isdir:
            self.run_on_file(contents)
        else:
            self.run_on_folder()
        
        for ii, f in enumerate(self.files):
            if f.islinked and f.thumbnail.endswith(".svg") and not os.path.exists(self.files[ii].name):
                f.thumbnail = os.path.join(dh.si_dir,'pngs','missing_svg.svg')
                
        self.convert_emfs() # start ConversionThreads
        self.run_on_fof_done = True
        trigger_refresh()

    def convert_emfs(self):
        for ii, f in enumerate(self.files):
            if f.name.endswith(".emf") or f.name.endswith(".wmf"):
                tnpng = os.path.join(self.tndir, str(self.numtns) + ".png")
                self.numtns += 1
                thread = ConversionThread(f, self, tnpng)
                self.cthreads.append(thread)
                thread.start()                

    def run(self):
        with app_lock:
            if app is None:
                Make_Flask_App()
                time.sleep(1)
                # wait to see if check_for_refresh called
                global openedgallery
                if not (openedgallery):
                    webbrowser.open("http://localhost:{}".format(str(PORTNUMBER)))
                    openedgallery = True
        self.run_on_fof()
        watcher.add_watch(self)

def should_display(file):
    """ Criteron for whether a file should be displayed in the gallery """
    valid_exts = ['svg','emf','wmf','png','gif','jpg','jpeg']
    return any(file.lower().endswith('.'+ext) for ext in valid_exts)


warnings.filterwarnings(
    "ignore", message="Failed to import fsevents. Fall back to kqueue"
)
mydir = os.path.dirname(os.path.abspath(__file__))
packages = os.path.join(mydir, "packages")
if packages not in sys.path:
    sys.path.append(packages)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from collections import defaultdict
class Watcher(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.observer = Observer()
        self.dir_processors = defaultdict(list)  # dirpath -> list of Processor
        self.dir_refs = defaultdict(int)       # dirpath -> number of watchers
        self.dir_watches = {}                  # dirpath -> Watch object
        self.debounce_timers = {}              # (watcher, path) -> timer
        self.file_mod_times = {}               # full file path -> last mtime
        self.observer.start()

    def add_watch(self, fp):
        path = os.path.abspath(fp.fof)
        dir_path = path if fp.isdir else os.path.dirname(path)

        # Initialize mod times since watchdog sometimes does modifier events
        # that don't seem to be real
        if fp.isdir:
            cfiles = [os.path.join(fp.fof, f) for f in os.listdir(fp.fof)]
        else:
            cfiles = [fp.fof]
        for f in cfiles:
            if os.path.isfile(f) and self.is_target_file(f,fp):
                mtime = self.get_mod_time(f)
                if mtime:
                    self.file_mod_times[os.path.abspath(f)] = mtime

        if self.dir_refs[dir_path] == 0:
            watch = self.observer.schedule(self, dir_path, recursive=False)
            self.dir_watches[dir_path] = watch
            print(f"Scheduled observer for {dir_path}")

        self.dir_processors[dir_path].append(fp)
        self.dir_refs[dir_path] += 1

    def remove_watch(self, fp):
        path = os.path.abspath(fp.fof)
        dir_path = path if fp.isdir else os.path.dirname(path)

        if fp in self.dir_processors[dir_path]:
            self.dir_processors[dir_path].remove(fp)
            self.dir_refs[dir_path] -= 1

        if self.dir_refs[dir_path] <= 0:
            print(f"Unscheduling observer for {dir_path}")
            watch = self.dir_watches.pop(dir_path, None)
            if watch:
                self.observer.unschedule(watch)
            self.dir_processors.pop(dir_path, None)
            self.dir_refs.pop(dir_path, None)

    def stop(self):
        self.observer.stop()
        self.observer.join()

    @staticmethod
    def get_mod_time(path):
        try:
            return os.path.getmtime(path)
        except FileNotFoundError:
            return None

    def is_target_file(self, file_path, watcher):
        file_name = os.path.basename(file_path)
        if not watcher.isdir:
            return os.path.abspath(file_path) == os.path.abspath(watcher.fof)
        return should_display(file_name)

    def handle_event(self, event):
        if event.is_directory:
            return
        dir_path = os.path.dirname(event.src_path)
        for watcher in self.dir_processors.get(dir_path, []):
            if not self.is_target_file(event.src_path, watcher):
                continue
            key = (watcher, event.src_path)
            
            if key in self.debounce_timers:
                self.debounce_timers[key].cancel()
            self.debounce_timers[key] = threading.Timer(
                0.5, self.run_callback, [watcher, event]
            )
            self.debounce_timers[key].start()
            

    def run_callback(self, watcher, event):
        if event.event_type == "created" and watcher.create_fcn:
            watcher.create_fcn(event.src_path)
        elif event.event_type == "modified" and watcher.mod_fcn:
            watcher.mod_fcn(event.src_path)
        elif event.event_type == "deleted" and watcher.delete_fcn:
            watcher.delete_fcn(event.src_path)

    def on_created(self, event):
        self.handle_event(event)

    def on_deleted(self, event):
        self.file_mod_times.pop(event.src_path, None)
        self.handle_event(event)

    def on_modified(self, event):
        if event.is_directory:
            return
        new_mtime = self.get_mod_time(os.path.abspath(event.src_path))
        old_mtime = self.file_mod_times.get(os.path.abspath(event.src_path))

        if new_mtime and new_mtime != old_mtime:
            self.file_mod_times[event.src_path] = new_mtime
            self.handle_event(event)
watcher = Watcher()

converted_files = dict()
lastupdate = time.time()
processors = []
openedgallery = False

def process_selection(file, opened=True):
    if os.path.isdir(file) and os.path.isfile(os.path.join(file, "Gallery.cfg")):
        with open(os.path.join(file, "Gallery.cfg"), "r") as f:
            lines = f.readlines()
            lines = [line.strip() for line in lines]
            for ii, ln in enumerate(lines):
                process_selection(os.path.join(file, ln), True)
            return

    for fp in processors:
        if file == fp.fof:
            processors.remove(fp)
            watcher.remove_watch(fp)
    print("About to start")
    fp = Processor(file, opened=opened)
    fp.win = win
    processors.append(fp)
    fp.start()

def quitnow():
    requests.get(
        "http://localhost:{}/stop".format(str(PORTNUMBER))
    )  # kill Flask app


    # remove temp files
    tmps = []
    for t in os.listdir(temp_dir):
        tmp = os.path.join(temp_dir, t)
        try:
            one_day_ago = time.time() - 24 * 60 * 60
            if os.path.getmtime(tmp) < one_day_ago:
                tmps.append(tmp)
        except FileNotFoundError:  # already deleted
            pass
        if tmp.startswith(temp_base):
            tmps.append(tmp)
    
    for tmp in tmps:
        if os.path.exists(tmp):
            deleted = False
            nattempts = 0
            while not deleted and nattempts < MAXATTEMPTS:
                try:
                    if os.path.isdir(tmp):
                        shutil.rmtree(tmp)
                    else:
                        os.remove(tmp)
                    deleted = True
                except PermissionError:
                    time.sleep(1)
                    nattempts += 1

    for fp in processors:
        watcher.remove_watch(fp)
        
    watcher.stop()

    pid = os.getpid()
    import signal

    os.kill(pid, signal.SIGINT)  # or signal.SIGTERM

if guitype == "gtk":
    import gi

    gi.require_version("Gtk", "3.0")

    class GalleryViewerServer(Gtk.Window):
        def __init__(self):
            Gtk.Window.__init__(self, title="Gallery Viewer")
            self.set_default_size(
                400, -1
            )  # set width to 400 pixels, height can be automatic
            self.set_position(Gtk.WindowPosition.CENTER)

            self.containing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.containing_box.set_valign(Gtk.Align.CENTER)
            self.containing_box.set_margin_top(20)
            self.containing_box.set_margin_bottom(20)

            self.file_button = Gtk.Button(label="View contents of files (.pptx, .docx, .one)")
            self.file_button.connect("clicked", self.on_file_button_clicked)
            self.folder_button = Gtk.Button(label="View contents of folders")
            self.folder_button.connect("clicked", self.on_folder_button_clicked)
            self.clear_button = Gtk.Button(label="Clear selections")
            self.clear_button.connect("clicked", self.clear_clicked)
            self.gallery_button = Gtk.Button(label="Display gallery")
            self.gallery_button.connect("clicked", self.gallery_button_clicked)
            self.exit_button = Gtk.Button(label="Exit")
            self.exit_button.connect("clicked", self.on_button_clicked)

            # Create a list store to hold the file information
            self.liststore = Gtk.ListStore(str, str)
            self.treeview = Gtk.TreeView(model=self.liststore)
            renderer_text = Gtk.CellRendererText()
            column_text = Gtk.TreeViewColumn("Name", renderer_text, text=0)
            self.treeview.append_column(column_text)
            renderer_text = Gtk.CellRendererText()
            column_text = Gtk.TreeViewColumn("Location", renderer_text, text=1)
            self.treeview.append_column(column_text)
            self.scrolled_window_files = Gtk.ScrolledWindow()
            self.scrolled_window_files.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
            )
            self.scrolled_window_files.set_size_request(600, 200)
            self.scrolled_window_files.set_vexpand(True)
            self.scrolled_window_files.add(self.treeview)

            self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            # self.box.pack_start(self.containing_box, True, True, 0)
            self.box.pack_start(self.scrolled_window_files, True, True, 0)
            self.box.pack_start(self.file_button, False, False, 0)
            self.box.pack_start(self.folder_button, False, False, 0)
            self.box.pack_start(self.clear_button, False, False, 0)
            self.box.pack_start(self.gallery_button, False, False, 0)
            self.box.pack_start(self.exit_button, False, False, 0)
            self.add(self.box)

        def print_text(self, text):
            buffer = self.selected_file_label.get_buffer()
            start, end = buffer.get_bounds()
            if buffer.get_text(start, end, False) == "No file selected.":
                buffer.set_text("")
            buffer.insert(buffer.get_end_iter(), text + "\n")
            end_iter = buffer.get_end_iter()
            buffer.move_mark(buffer.get_insert(), end_iter)
            self.selected_file_label.scroll_to_mark(
                buffer.get_insert(), 0, True, 0, 0
            )

        def on_button_clicked(self, widget):
            self.destroy()

        def on_file_button_clicked(self, widget):
            native = Gtk.FileChooserNative.new(
                "Please choose one or more files", self, Gtk.FileChooserAction.OPEN, None, None
            )
            native.set_select_multiple(True)
            filter_ppt = Gtk.FileFilter()
            filter_ppt.set_name("Office files")
            filter_ppt.add_pattern("*.docx")
            filter_ppt.add_pattern("*.pptx")
            filter_ppt.add_pattern("*.pptm")
            filter_ppt.add_pattern("*.one")
            native.add_filter(filter_ppt)
            response = native.run()
            if response == Gtk.ResponseType.ACCEPT:
                selected_files = native.get_filenames()
                for selected_file in selected_files:
                    file_name = os.path.basename(selected_file)
                    file_dir = os.path.dirname(selected_file)
                    self.liststore.append([file_name, file_dir])
                    process_selection(selected_file)
            native.destroy()

        def on_folder_button_clicked(self, widget):
            native = Gtk.FileChooserNative.new(
                "Please choose one or more directories",
                self,
                Gtk.FileChooserAction.SELECT_FOLDER,
                None,
                None,
            )
            native.set_select_multiple(True)
            response = native.run()
            if response == Gtk.ResponseType.ACCEPT:
                selected_files = native.get_filenames()
                for selected_file in selected_files:
                    file_name = os.path.basename(selected_file)
                    file_dir = os.path.dirname(selected_file)
                    self.liststore.append([file_name, file_dir])
                    process_selection(selected_file)
                    
                    if os.path.exists(selected_file):
                        for fnm in os.listdir(selected_file):
                            if fnm.endswith('.docx') or fnm.endswith('.pptx') or fnm.endswith('.one'):
                                if not fnm.startswith('~$'): # temp files
                                    file_name = fnm
                                    file_dir = selected_file
                                    self.liststore.append([file_name, file_dir])
                                    process_selection(os.path.join(file_dir,file_name))
            native.destroy()

        def gallery_button_clicked(self, widget):
            webbrowser.open("http://localhost:{}".format(str(PORTNUMBER)))

        def clear_clicked(self, widget):
            for fp in reversed(processors):
                processors.remove(fp)
                watcher.remove_watch(fp)
            self.liststore.clear()

    win = GalleryViewerServer()
    win.set_keep_above(True)

    # win.connect("destroy", quitnow)
    def quit_and_close(self):
        Gtk.main_quit()
        quitnow()

    win.connect("destroy", quit_and_close)
    win.show_all()
    win.set_keep_above(False)
    Gtk.main()
elif guitype == "tkinter":
    root = tk.Tk()
    root.title("Gallery Viewer")
    root.attributes("-topmost", True)
    root.wm_minsize(width=350, height=-1)

    def open_file():
        file = filedialog.askopenfilename()
        file_label.config(text=file)
        process_selection(file)

    def end_program():
        print("Quitting")
        root.destroy()
        quitnow()

    file_label = tk.Label(root, text="No file selected.")
    file_label.pack()
    select_button = tk.Button(root, text="Select File", command=open_file)
    select_button.pack()
    end_button = tk.Button(root, text="End Program", command=end_program)
    end_button.pack()
    root.protocol("WM_DELETE_WINDOW", end_program)
    root.mainloop()

print("Finishing")
