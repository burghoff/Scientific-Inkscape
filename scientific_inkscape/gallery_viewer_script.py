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
# os.remove(aes)

bfn = input_options.inkscape_bfn
sys.path.extend([p for p in input_options.syspath if p not in sys.path])
bfn_dir = os.path.dirname(bfn)
if bfn_dir not in sys.path:
    sys.path.append(bfn_dir)
PORTNUMBER = input_options.portnum
sys.stdout = open(input_options.logfile, "w")
sys.stderr = sys.stdout

import sys, subprocess, threading, time, copy, pickle, chardet
import random
import webbrowser, urllib, pathlib
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
import xml.etree.ElementTree as ET
from dhelpers import si_tmp
from autoexporter import ORIG_KEY
from autoexporter import DUP_KEY
from autoexporter import hash_file

WHILESLEEP = 0.25
IMAGE_WIDTH = 175
IMAGE_HEIGHT = IMAGE_WIDTH * 0.7

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
    file_uri_parsed = urllib.parse.urlparse(file_uri)
    file_uri_path_unquoted = urllib.parse.unquote(file_uri_parsed.path)
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

global refreshapp
refreshapp = False

def trigger_refresh():
    global refreshapp
    refreshapp = True
    
def show_in_file_browser(path):
    import time
    if not os.path.exists(path):
        raise FileNotFoundError(f"The path {path} does not exist.")

    # Resolve the absolute path
    path = os.path.abspath(path)

    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes

        # Define necessary Windows types and constants
        LPCTSTR = wintypes.LPCWSTR
        HWND = wintypes.HWND
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



def Make_Flask_App():
    warnings.simplefilter("ignore", DeprecationWarning)
    # prevent warning that process is open
    from flask import Flask, request, url_for, jsonify, send_from_directory, render_template, abort

    app = Flask(__name__, template_folder='.')

    global truepath, truepath_lock
    truepath = dict()
    truepath_lock = threading.Lock();
    

    @app.route("/images/<folder>/<path:path>")
    def send_image(folder, path):
        global truepath, truepath_lock
        truepath_lock.acquire()
        tp = truepath.get(folder)
        truepath_lock.release()
        if tp is None:
            abort(404)  # Sends a 404 response
        return send_from_directory(os.path.abspath(tp), path)

    @app.route("/")
    def index():
        global PORTNUMBER
        # Render the gallery page (without data, which will be fetched via AJAX)
        return render_template("gallery_viewer_template.html", image_width=IMAGE_WIDTH, image_height=IMAGE_HEIGHT, port=PORTNUMBER)


    @app.route("/gallery_data")
    def gallery_data():
        global temp_dir, truepath, watcher_threads
    
        # Collect the gallery data to be sent dynamically
        gallery_data = []
        for wt in watcher_threads:
            files_data = []
            for ii, svg in enumerate(wt.files):
                svg_file_uri = pathlib.Path(svg).as_uri()
                embed_uri = pathlib.Path(wt.embeds[ii]).as_uri() if wt.embeds[ii] else None
                if wt.slidenums[ii] is not None:
                    label = f"Slide {wt.slidenums[ii]}" 
                else:
                    pn = (
                            " ({0})".format(wt.pagenums[ii])
                            if wt.pagenums[ii] is not None
                            else ""
                        )
                    label = os.path.split(svg)[-1] + pn
    
                # Determine currenttype accurately
                if os.path.isdir(wt.fof):
                    currenttype = "Current"
                elif wt.islinked[ii]:
                    currenttype = "Linked"
                else:
                    currenttype = "Embedded"
    
                # Get the folder key and corresponding URL path for the SVG file
                truepath_lock.acquire()
                svg_folder, svg_file_name = os.path.split(svg)
                if svg_folder not in truepath.values():
                    svg_folder_key = os.path.split(temp_dir)[-1] + "-dir" + str(len(truepath))
                    truepath[svg_folder_key] = svg_folder
                else:
                    svg_folder_key = next(key for key, value in truepath.items() if value == svg_folder)
    
                file_url = url_for("send_image", path=svg_file_name, folder=svg_folder_key)
    
                # Get the folder key and URL for the thumbnail
                thumbnail = wt.thumbnails[ii]
                thumbnail_folder, thumbnail_file_name = os.path.split(thumbnail)
                if thumbnail_folder not in truepath.values():
                    thumbnail_folder_key = os.path.split(temp_dir)[-1] + "-dir" + str(len(truepath))
                    truepath[thumbnail_folder_key] = thumbnail_folder
                else:
                    thumbnail_folder_key = next(key for key, value in truepath.items() if value == thumbnail_folder)
    
                thumbnail_url = url_for("send_image", path=thumbnail_file_name, folder=thumbnail_folder_key)
                truepath_lock.release()
    
                # Add file data
                files_data.append({
                    "file_url": file_url,
                    "thumbnail_url": thumbnail_url,
                    "file_uri": svg_file_uri,
                    "label": label,
                    "currenttype": currenttype,
                    "embed": embed_uri,
                })
            processing = not wt.run_on_fof_done or any(not t.done for t in wt.cthreads)
            gallery_data.append({
                "header": wt.header,
                "files": files_data,
                "processing": processing
            })
    
        # Return gallery data as JSON
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

            if str(svg_file).endswith(".emf") or str(svg_file).endswith(".wmf"):
                subprocess.Popen([bfn,svg_file])
                return f"The parameter received is: {param}"

            with OpenWithEncoding(svg_file) as f:
                file_content = f.read()
                if DUP_KEY in file_content:
                    global temp_dir
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
    return app

global temp_dir
temp_dir = si_tmp(dirbase="gv")
global conv_number, conv_lock, running_cthreads
conv_number = 0
conv_lock = threading.Lock()
running_cthreads = []



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
    
class ConversionThread(threading.Thread):
    # Converts an EMF/WMF to PNG to be used as a thumbnail
    def __init__(self, filein, index, parent_watcher, fileout):
        super().__init__()
        self.filein = filein
        self.thumbnails = parent_watcher.thumbnails
        self.index = index
        self.parent = parent_watcher  # Reference to the parent class instance
        self.done = False
        self.fileout = fileout

    def run(self):
        filein = self.filein
        # fileout = self.thumbnails[self.index]

        # Read and hash the input file to check for duplicates
        with open(filein, "rb") as file:
            file_content = file.read()
            hashed = hashlib.sha256(file_content).hexdigest()
            
        global converted_files, temp_dir, conv_number, conv_lock

        # Check if the file has already been converted
        if hashed not in converted_files:
            notdone = True
            nattempts = 0
            while notdone and nattempts < 5:
                try:
                    print("Starting export of "+filein+' (attempt no. '+str(nattempts)+')')

                    # Ensure the conversions directory exists
                    conv_lock.acquire()
                    conversions_dir = os.path.join(temp_dir, "conversions")
                    if not os.path.exists(conversions_dir):
                        os.mkdir(conversions_dir)

                    # Generate a unique conversion path
                    conversion_path = os.path.join(conversions_dir, f"{conv_number}.png")
                    conv_number += 1
                    conv_lock.release()

                    # Remove existing output file if it exists
                    if os.path.exists(self.fileout):
                        os.remove(self.fileout)
                        
                    from image_helpers import hasPIL
                    if nattempts>2 or not hasPIL:
                        # Prepare the command arguments
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
                            conversion_path,
                            filein,
                        ]
    
                        # Execute the conversion command
                        dh.subprocess_repeat(args)
                        print('Inkscape export of '+filein)
                    else:
                        from PIL import Image
                        with open(filein, "rb") as file:
                            with Image.open(file) as im:
                                width, height = im.size
                                new_width = 400
                                
                                if filein.endswith('.wmf'):
                                    DEFAULT_DPI = 72
                                    new_dpi = max(10,int(new_width / width * DEFAULT_DPI))
                                    im.load(dpi=new_dpi)
                                    width, height = im.size
                                
                                new_height = int((new_width / width) * height)
                                if 'info' in im.__dict__ and "dpi" in im.info and isinstance(im.info["dpi"],tuple) and len(im.info["dpi"]) == 2:
                                    print(im.info['dpi'])
                                    new_height = int((new_width / width * im.info["dpi"][0]/im.info["dpi"][1]) * height)
                                resized_image = im.resize((new_width, new_height), Image.LANCZOS)
                                resized_image.save(conversion_path)
                                print('PIL export of '+filein + ' originally '+str(width)+' x '+str(height))

                    # Move the converted file to the final destination
                    shutil.move(conversion_path, self.fileout)

                    notdone = False
                    print("Finished export...")
                except Exception as e:
                    print(f"Error during export: {e}")
                    nattempts += 1

            # Trigger a refresh and update the converted files dictionary
            converted_files[hashed] = self.fileout
        else:
            # If already converted, copy the existing file
            shutil.copy2(converted_files[hashed], self.fileout)
        if os.path.exists(self.fileout):
            self.thumbnails[self.index] = self.fileout
            trigger_refresh()
        self.done = True
    

class WatcherThread(threading.Thread):
    # A thread that generates an SVG gallery of files, then watches
    # it for changes
    def __init__(self, file_or_folder, opened=True):
        threading.Thread.__init__(self)
        self.fof = file_or_folder
        self.stopped = False
        self.open_at_load = opened
        self.run_on_fof_done = False
        
        self.files = []
        self.thumbnails = []
        self.header = self.fof
        self.slidenums = []
        self.islinked = []
        self.embeds = []
        self.pagenums = []
        self.can_display = False
        
        self.cthreads = []  # conversion threads

    def get_image_slidenums(self, dirin):
        relsdir = os.path.join(dirin, "ppt", "slides", "_rels")
        numslides = len(os.listdir(relsdir))
        slide_filenames = []
        for slide_num in range(1, numslides + 1):
            tree = ET.parse(
                os.path.join(
                    dirin, "ppt", "slides", "_rels", f"slide{slide_num}.xml.rels"
                )
            )
            root = tree.getroot()
            image_filenames = []
            for elem in root.iter(
                "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
            ):
                if (
                    elem.attrib["Type"]
                    == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
                ):
                    image_filenames.append(elem.attrib["Target"])
            slide_filenames.append(image_filenames)
        slide_lookup = {}
        for index, filenames in enumerate(slide_filenames):
            for filename in filenames:
                slide_lookup[filename] = slide_lookup.get(filename, []) + [
                    index + 1
                ]
        return slide_lookup
    
    def get_linked_images_word(self,dirin):
        rels_path = os.path.join(dirin, "word", "_rels", "document.xml.rels")
        
        # Parse the relationships file
        tree = ET.parse(rels_path)
        root = tree.getroot()
        
        linked_images = []
        for elem in root.iter("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
            # Check if the relationship is an image and has an external TargetMode
            if elem.attrib["Type"] == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image":
                if elem.attrib.get("TargetMode") == "External":
                    linked_images.append(elem.attrib["Target"])
        
        return linked_images
    
    def get_images_onenote(self,target_file,outputdir):
        ''' Extracts OneNote files to the output directory '''
        pkg_dir = os.path.join(dh.si_dir,'packages')
        if pkg_dir not in sys.path:
            sys.path.append(pkg_dir)
        from onenoteextractor.one import OneNoteExtractor
        from pathlib import Path
        with Path(target_file).open("rb") as infile:
            data = infile.read()
        document = OneNoteExtractor(data=data, password=None)
        import struct
        def is_emf(file_data: bytes) -> bool:
            """Check if the file_data represents an EMF file by inspecting the header."""
            if len(file_data) < 88:
                return False  # EMF header should be at least 88 bytes
            # Unpack the first 4 bytes to get the Record Type
            record_type, = struct.unpack('<I', file_data[0:4])
            # Unpack bytes 40 to 44 to get the Signature
            signature, = struct.unpack('<I', file_data[40:44])
            # EMF specific values
            EMR_HEADER = 0x00000001
            EMF_SIGNATURE = 0x464D4520 # ' EMF' in ASCII (note the leading space)
            
            return record_type == EMR_HEADER and signature == EMF_SIGNATURE
        def is_wmf(file_data: bytes) -> bool:
            """Check if the file_data represents a WMF file by inspecting the header."""
            if len(file_data) < 4:
                return False  # WMF header should be at least 4 bytes
            # Check for Placeable WMF magic number
            if file_data.startswith(b'\xD7\xCD\xC6\x9A'):
                return True
            # For non-placeable WMF files, check the Type and Header Size
            if len(file_data) < 18:  # Minimum WMF header size
                return False
            try:
                type_, header_size, version = struct.unpack('<HHH', file_data[0:6])
                if type_ in (1, 2) and header_size == 9 and version in (0x0300, 0x0100):
                    return True
            except struct.error:
                pass
            return False
        def is_png(file_data: bytes) -> bool:
            """Check if the file_data represents a PNG file by inspecting the header."""
            return file_data.startswith(b'\x89PNG\r\n\x1a\n')

        def is_jpeg(file_data: bytes) -> bool:
            """Check if the file_data represents a JPEG file by inspecting the header."""
            return file_data.startswith(b'\xFF\xD8\xFF')
        for index, file_data in enumerate(document.extract_files()):
            bn = Path(target_file).stem  # Use stem to get filename without extension
            if is_emf(file_data):
                extension = '.emf'
            elif is_wmf(file_data):
                extension = '.wmf'
            elif is_png(file_data):
                extension = '.png'
            elif is_jpeg(file_data):
                extension = '.jpg'
            else:
                extension = '.bin'  # Default extension for unknown types
            target_path = Path(outputdir) / f"{bn}_{index}{extension}"
            print(f"Writing extracted file to: {target_path}")
            with target_path.open("wb") as outf:
                outf.write(file_data)


    def run_on_fof(self):
        print("Running on file: " + self.fof)
        global temp_dir

        contentsmade = False
        while not (contentsmade):
            contents = os.path.join(
                temp_dir, "contents" + str(random.randint(1, 100000))
            )
            if not (os.path.exists(contents)):
                os.mkdir(contents)
                contentsmade = True

        def get_svgs(dirin):
            svg_filenames = []
            for file in os.listdir(dirin):
                if file.endswith(".svg") or file.endswith(".emf") or file.endswith(".wmf"):
                    svg_filenames.append(os.path.join(dirin, file))
            svg_filenames.sort()
            return svg_filenames

        self.tndir = os.path.join(contents, "thumbnails")
        if not os.path.exists(self.tndir):
            os.makedirs(self.tndir)
        self.numtns = len(os.listdir(self.tndir))
        
        if os.path.isfile(self.fof):
            # Unzip the ppt file to the temp directory, allowing for multiple
            # attempts in case the file was not originally found (which can 
            # happen in cloud drives)
            if self.fof.endswith(".pptx"):
                ftype = "ppt"
            elif self.fof.endswith(".one"):
                ftype = "onenote"
            else:
                ftype = "word"

            
            
            if ftype == "onenote":
                media_dir = os.path.join(contents, ftype)
                os.mkdir(media_dir)
                self.get_images_onenote(self.fof,media_dir)
            else:
                media_dir = os.path.join(contents, ftype, "media")
                attempts = 0
                max_attempts = 3
                while attempts < max_attempts:
                    try:
                        with zipfile.ZipFile(self.fof, "r") as zip_ref:
                            zip_ref.extractall(contents)
                        break  # Exit the loop if successful
                    except zipfile.BadZipFile:
                        attempts += 1
                        if attempts == max_attempts:
                            self.can_display = True
                            self.run_on_fof_done = True
                            print(f'Could not unzip {self.fof} after {max_attempts} attempts.')
                            return
                        else:
                            print(f'Attempt {attempts} to unzip {self.fof} failed. Retrying...')

            if os.path.exists(media_dir):
                self.files = get_svgs(media_dir)
            else:
                self.files = []
            if ftype == "ppt":
                image_slides = self.get_image_slidenums(contents)

                # Add linked images to self.files
                linked = [
                    str(file_uri_to_path(k))
                    for k in image_slides.keys()
                    if "file:" in k
                ]
                self.files += linked
                self.slidenums = {
                    os.path.join(contents, "ppt", "media", os.path.basename(k))
                    if "file:" not in k
                    else str(file_uri_to_path(k)): v
                    for k, v in image_slides.items()
                }

                # Sort the files by slide number and make slidenums a corresponding list
                # Duplicates filenames if on multiple slides
                new_files = []
                new_slidenums = []
                for file in self.files:
                    slides = self.slidenums.get(file, [float("inf")])
                    for slide in slides:
                        new_files.append(file)
                        new_slidenums.append(slide)
                if len(new_files)>0:
                    new_files_and_slidenums = sorted(
                        zip(new_files, new_slidenums), key=lambda x: (x[1], x[0])
                    )
                    self.files, self.slidenums = zip(*new_files_and_slidenums)
                    self.files = list(self.files)
                    self.slidenums = list(self.slidenums)
                else:
                    self.files = []
                    self.slidenums = []
                self.slidenums = [
                    v if v != float("inf") else "?" for v in self.slidenums
                ]
                self.islinked = [f in linked for f in self.files]
            else:
                if ftype=='word':
                    linked = [str(file_uri_to_path(k)) for k in self.get_linked_images_word(contents)]
                else:
                    linked = []
                self.islinked= [False]*len(self.files) + [True]*len(linked)
                self.files   = self.files + linked
                self.slidenums = [None] * len(self.files)
                self.embeds = [None] * len(self.files)

            self.thumbnails = copy.copy(self.files)
            self.header = self.fof
            print("Temp dir: " + temp_dir)

            self.embeds = [None] * len(self.files)
            self.pagenums = [None] * len(self.files)
            subfiles = None
            for ii, fn in enumerate(self.files):
                ev = False
                if fn.endswith(".svg") and os.path.exists(fn):
                    with OpenWithEncoding(fn) as f:
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
                                if os.path.exists(orig_file):
                                    ev = os.path.abspath(orig_file)
                                else:
                                    # Check subdirectories of the file's location in case it was moved

                                    def list_all_files(directory):
                                        for dirpath, dirs, files in os.walk(
                                            directory
                                        ):
                                            for filename in files:
                                                yield os.path.join(
                                                    dirpath, filename
                                                )

                                    fndir = os.path.split(self.fof)[0]
                                    subfiles = (
                                        list(list_all_files(fndir))
                                        if subfiles is None
                                        else subfiles
                                    )

                                    for tryfile in subfiles:
                                        if os.path.split(orig_file)[
                                            -1
                                        ] == os.path.split(tryfile)[-1] and (
                                            orig_hash is None
                                            or hash_file(tryfile) == orig_hash
                                        ):
                                            ev = os.path.abspath(tryfile)
                                            break

                self.embeds[ii]=ev
            self.can_display = True

        elif os.path.isdir(self.fof):
            self.files = get_svgs(self.fof)
            self.thumbnails = copy.copy(self.files)
            self.header = self.fof
            self.slidenums = [None] * len(self.files)
            self.islinked  = [None] * len(self.files)
            self.embeds    = [None] * len(self.files)
            self.pagenums  = [None] * len(self.files)
            
            self.can_display = True

            ii = 0
            while ii < len(self.files):
                fn = self.files[ii]
                tns = []
            
                # Check if the file is an SVG file
                if fn.endswith(".svg"):
                    with OpenWithEncoding(fn) as f:
                        contents = f.read()
                        match = re.search(r"<\s*inkscape:page[\s\S]*?>", contents)
                        if match:
                            svg = dh.svg_from_file(fn)
                            pgs = svg.cdocsize.pgs
                            haspgs = inkex.installed_haspages

            
                            # If the file has multiple pages, split it
                            if haspgs and len(pgs) > 1:
                                vbs = [svg.cdocsize.pxtouu(pg.bbpx) for pg in pgs]
                                for vb in vbs:
                                    svg.set_viewbox(vb)
                                    tnsvg = os.path.join(self.tndir, str(self.numtns) + ".svg")
                                    self.numtns += 1
                                    dh.overwrite_svg(svg, tnsvg)
                                    tns.append(tnsvg)
            
                # If thumbnails were created (multiple pages), update files and thumbnails lists
                if len(tns) > 0:
                    self.files[ii:ii + 1] = [fn] * len(tns)  # Replace with repeated file name
                    self.thumbnails[ii:ii + 1] = tns         # Replace with generated thumbnails
                    self.pagenums[ii:ii + 1] = list(range(1, len(tns) + 1))  # Page numbers from 1 onward
                    self.slidenums[ii:ii + 1] = [None]* len(tns)
                    self.islinked[ii:ii + 1]  = [None]* len(tns)
                    self.embeds[ii:ii + 1]    = [None]* len(tns)
                else:
                    self.files[ii:ii + 1] = [self.files[ii]]  # Keep as a single file
                    self.thumbnails[ii:ii + 1] = [self.thumbnails[ii]]  # Single thumbnail
                    self.pagenums[ii:ii + 1] = [None]  # Single file, no page numbers needed
                    self.slidenums[ii:ii + 1] = [None]
                    self.islinked[ii:ii + 1]  = [None]
                    self.embeds[ii:ii + 1]    = [None]
                trigger_refresh()
            
                # Move ii to the next set of files
                ii += max(len(tns),1)
        
        for ii, tn in enumerate(self.thumbnails):
            if tn.endswith(".emf"):
                self.thumbnails[ii] = os.path.join(dh.si_dir,'pngs','converting_emf.svg')
            elif tn.endswith(".wmf"):
                self.thumbnails[ii] = os.path.join(dh.si_dir,'pngs','converting_wmf.svg')
            elif tn.endswith(".svg") and not os.path.exists(self.files[ii]):
                self.thumbnails[ii] = os.path.join(dh.si_dir,'pngs','missing_svg.svg')
                
        
        self.run_on_fof_done = True

    def convert_emfs(self):    
        for ii, f in enumerate(self.files):
            if f.endswith(".emf") or f.endswith(".wmf"):
                tnpng = os.path.join(self.tndir, str(self.numtns) + ".png")
                self.numtns += 1
                thread = ConversionThread(f, ii, self, tnpng)
                self.cthreads.append(thread)
                
        global running_cthreads
        running_cthreads = [t for t in running_cthreads if t.is_alive()]
        for thread in self.cthreads:
            # Limit the number of concurrent threads to 10
            while len([t for t in running_cthreads if t.is_alive()]) > 10:
                time.sleep(0.1)
            print(f"Making thumbnail {self.thumbnails[thread.index]}")
            running_cthreads.append(thread)
            thread.start()
                

    def run(self):
        global myapp
        if myapp is None:
            myapp = True
            myapp = Make_Flask_App()
            time.sleep(1)
            # wait to see if check_for_refresh called
            global openedgallery
            if not (openedgallery):
                webbrowser.open("http://localhost:{}".format(str(PORTNUMBER)))
                openedgallery = True
        self.run_on_fof()
        trigger_refresh()
        self.convert_emfs() # already refreshes

        def get_modtimes():
            modtimes = dict()
            if os.path.isfile(self.fof):
                modtimes[self.fof] = os.path.getmtime(self.fof)
            elif os.path.isdir(self.fof):
                fs = []
                for f in os.scandir(self.fof):
                    if f.name.endswith(".svg") or f.name.endswith(".emf") or f.name.endswith(".wmf"):
                        fs.append(os.path.join(os.path.abspath(self.fof), f.name))
                for f in fs:
                    try:
                        modtimes[f] = os.path.getmtime(f)
                    except FileNotFoundError:
                        modtimes[f] = None
            return modtimes

        lmts = get_modtimes()
        while not (self.stopped):
            time.sleep(1)
            mts = get_modtimes()
            if lmts != mts:
                print("Update " + self.fof)
                self.run_on_fof()
                trigger_refresh()
            lmts = mts
        trigger_refresh()

global myapp, converted_files, watcher_threads, openedgallery
myapp = None
converted_files = dict()
lastupdate = time.time()
watcher_threads = []
openedgallery = False

def process_selection(file, opened=True):
    if os.path.isdir(file) and os.path.isfile(os.path.join(file, "Gallery.cfg")):
        with open(os.path.join(file, "Gallery.cfg"), "r") as f:
            lines = f.readlines()
            lines = [line.strip() for line in lines]
            for ii, ln in enumerate(lines):
                # process_selection(os.path.join(file, ln), opened=(ii == 0))
                process_selection(os.path.join(file, ln), True)
            return

    global watcher_threads
    for wt in watcher_threads:
        if file == wt.fof:
            wt.stopped = True
            watcher_threads.remove(wt)
    print("About to start")
    wt = WatcherThread(file, opened=opened)
    wt.win = win
    watcher_threads.append(wt)
    wt.start()

def quitnow():
    requests.get(
        "http://localhost:{}/stop".format(str(PORTNUMBER))
    )  # kill Flask app

    for wt in watcher_threads:
        wt.stopped = True

    global temp_dir
    attempts = 0
    while os.path.exists(temp_dir) and attempts < 5:
        shutil.rmtree(temp_dir)
        attempts += 1
        time.sleep(5)

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
            global watcher_threads
            for wt in reversed(watcher_threads):
                wt.stopped = True
                watcher_threads.remove(wt)
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
