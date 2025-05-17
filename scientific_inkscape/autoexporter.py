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

# pylint: disable=import-error
"""
AutoExporter for Inkscape

This module provides an extension for Inkscape to automate the export of SVG files
into multiple formats. It supports watching directories, exporting immediately,
and offers various configuration options for exporting to PDF, PNG, EMF, EPS,
and plain SVG. The module handles preprocessing steps to ensure compatibility
and quality of exported files, such as embedding linked images, fixing markers,
scaling text, and more.

Main Features:
- Watches specified directories for changes and exports files automatically.
- Supports exporting to multiple formats with various options.
- Handles preprocessing of SVG files to fix common issues and improve compatibility.
- Provides postprocessing to clean up and adjust SVGs for better rendering in
  different environments.
- Includes utility functions for handling subprocesses, file manipulations,
  and SVG operations.
"""

import os
import sys
import time
import re
import copy
import subprocess
import warnings
import pickle
import math
import shutil
import tempfile
import hashlib
import lxml
import random
import threading

import dhelpers as dh
import inkex
from inkex import TextElement, Transform, Vector2d
from inkex.text.utils import default_style_atts, unique
from inkex.text.cache import BaseElementCache
from inkex.text.parser import ParsedText, xyset

import numpy as np
import image_helpers as ih

otp_support_tags = BaseElementCache.otp_support_tags
peltag = inkex.PathElement.ctag

USE_TERMINAL = False
DEBUGGING = False
DISPPROFILE = False


MAXATTEMPTS = 2
MAX_THREADS = 10;
sema1 = threading.Semaphore(MAX_THREADS)
sema2 = threading.Semaphore(MAX_THREADS)

class AutoExporter(inkex.EffectExtension):
    """Automates exporting of SVG files in multiple formats."""

    def add_arguments(self, pars):  # pylint: disable=no-self-use
        """Add arguments to the parser."""
        pars.add_argument("--tab", help="The selected UI-tab when OK was pressed")
        pars.add_argument("--watchdir", help="Watch directory")
        pars.add_argument("--writedir", help="Write directory")
        pars.add_argument(
            "--usepdf", type=inkex.Boolean, default=False, help="Export PDF?"
        )
        pars.add_argument(
            "--usepng", type=inkex.Boolean, default=False, help="Export PNG?"
        )
        pars.add_argument(
            "--useemf", type=inkex.Boolean, default=False, help="Export EMF?"
        )
        pars.add_argument(
            "--useeps", type=inkex.Boolean, default=False, help="Export EPS?"
        )
        pars.add_argument(
            "--usepsvg", type=inkex.Boolean, default=False, help="Export plain SVG?"
        )
        pars.add_argument("--dpi", default=600, help="Rasterization DPI")
        # pars.add_argument("--dpi_im", default=300, help="Resampling DPI")
        pars.add_argument(
            "--imagemode2",
            type=inkex.Boolean,
            default=True,
            help="Embedded image handling",
        )
        pars.add_argument(
            "--thinline",
            type=inkex.Boolean,
            default=True,
            help="Prevent thin line enhancement",
        )
        pars.add_argument(
            "--texttopath", type=inkex.Boolean, default=False, help="Text to paths?"
        )
        pars.add_argument(
            "--backingrect",
            type=inkex.Boolean,
            default=True,
            help="Add backing rectangle?",
        )
        pars.add_argument(
            "--stroketopath", type=inkex.Boolean, default=False, help="Stroke to paths?"
        )
        pars.add_argument(
            "--latexpdf", type=inkex.Boolean, default=False, help="Make LaTeX PDF?"
        )
        pars.add_argument(
            "--testmode", type=inkex.Boolean, default=False, help="Test mode?"
        )
        pars.add_argument("--testpage", type=int, default=1, help="Test mode page")
        pars.add_argument("--v", type=str, default="1.2", help="Version for debugging")
        pars.add_argument(
            "--rasterizermode", type=int, default=1, help="Mark for rasterization"
        )
        pars.add_argument(
            "--margin", type=float, default=0.5, help="Document margin (mm)"
        )
        pars.add_argument(
            "--exportwhat", type=int, default=1, help="Export what?"
        )

    def effect(self):
        """Start the Autoexporter or initiate export now."""
        if self.options.tab == "rasterizer":
            sel = [self.svg.selection[i] for i in range(len(self.svg.selection))]
            for elem in sel:
                if self.options.rasterizermode == 1:
                    elem.set("autoexporter_rasterize", "png")
                elif self.options.rasterizermode == 2:
                    elem.set("autoexporter_rasterize", "jpg")
                elif self.options.rasterizermode == 3:
                    elem.set("autoexporter_rasterize", "topath")
                else:
                    elem.set("autoexporter_rasterize", None)
            return
        self.options.exportnow = self.options.exportwhat==3
        self.options.watchhere = self.options.exportwhat==2

        # self.options.testmode = True;
        if self.options.testmode:
            self.options.usepsvg = True
            self.options.thinline = True
            self.options.imagemode2 = True
            self.options.texttopath = True
            self.options.stroketopath = True
            self.options.exportnow = True
            self.options.margin = 0.5
            self.options.latexpdf = False

        if DISPPROFILE:
            # pylint: disable=import-outside-toplevel
            import cProfile
            import pstats
            import io
            from pstats import SortKey
            # pylint: enable=import-outside-toplevel

            prf = cProfile.Profile()
            prf.enable()

        formats = [
            self.options.usepdf,
            self.options.usepng,
            self.options.useemf,
            self.options.useeps,
            self.options.usepsvg,
        ]
        formats = [
            ["pdf", "png", "emf", "eps", "psvg"][i]
            for i in range(len(formats))
            if formats[i]
        ]

        # Make an options copy we can pass to the external program
        optcopy = copy.copy(self.options)
        delattr(optcopy, "output")
        delattr(optcopy, "input_file")
        optcopy.reduce_images = self.options.imagemode2

        bfn = inkex.inkscape_system_info.binary_location
        pyloc, pybin = os.path.split(sys.executable)

        if not (self.options.exportnow):
            aepy = os.path.abspath(
                os.path.join(dh.get_script_path(), "autoexporter_script.py")
            )

            if self.options.watchhere:
                pth = dh.Get_Current_File(self, "To watch this document's location, ")
                optcopy.watchdir = os.path.dirname(pth)
                optcopy.writedir = os.path.dirname(pth)

            if not os.path.exists(optcopy.watchdir):
                dh.idebug(
                    "Watch directory could not be found. Please be sure the "
                    "selected location is valid.\n"
                )
                dh.idebug(
                    "Note: Linux AppImage and Snap installations of Inkscape "
                    "cannot see locations outside the installation directory."
                )
                sys.exit()

            # Pass settings using a config file. Include the current path so
            # Inkex can be called if needed.
            optcopy.inkscape_bfn = bfn
            optcopy.formats = formats
            optcopy.syspath = sys.path

            try:
                with warnings.catch_warnings():
                    # Ignore ImportWarning for Gtk/Pango
                    warnings.simplefilter("ignore")
                    # Prevent Gtk-Message: Failed to load module "xapp-gtk3-module"
                    os.environ["GTK_MODULES"] = ""
                    # pylint: disable=import-outside-toplevel, unused-import
                    import gi

                    gi.require_version("Gtk", "3.0")
                    from gi.repository import Gtk  # noqa
                    # pylint: enable=import-outside-toplevel, unused-import
                guitype = "gtk"
            except ImportError:
                guitype = "terminal"
            if USE_TERMINAL:
                guitype = "terminal"
            optcopy.guitype = guitype

            aes = os.path.join(
                os.path.abspath(tempfile.gettempdir()), "si_ae_settings.p"
            )
            with open(aes, "wb") as file:
                pickle.dump(optcopy, file)
            warnings.simplefilter("ignore", ResourceWarning)
            # prevent warning that process is open

            if guitype == "gtk":
                AutoExporter._gtk_call(pybin, aepy)
            else:
                AutoExporter._terminal_call(pybin, aepy, pyloc)

        else:
            if not (self.options.testmode):
                pth = dh.Get_Current_File(self, "To do a direct export, ")
            else:
                pth = self.options.input_file
            optcopy.original_file = pth
            optcopy.debug = DEBUGGING
            optcopy.prints = False
            optcopy.linked_locations = ih.get_linked_locations(self)
            # needed to find linked images in relative directories
            optcopy.formats = formats
            optcopy.outtemplate = pth
            optcopy.bfn = bfn

            Exporter(self.options.input_file, optcopy).export_all()

        if DISPPROFILE:
            prf.disable()
            sio = io.StringIO()
            sortby = SortKey.CUMULATIVE
            pst = pstats.Stats(prf, stream=sio).sort_stats(sortby)
            pst.print_stats()
            dh.debug(sio.getvalue())

        if self.options.testmode:
            nfn = os.path.abspath(pth[0:-4] + "_plain.svg")
            stream = self.options.output

            if isinstance(stream, str):
                # Copy the new file
                shutil.copyfile(nfn, self.options.output)
            else:
                # Write to the output stream
                svg2 = get_svg(nfn)
                newdoc = lxml.etree.tostring(svg2, pretty_print=True)
                try:
                    stream.write(newdoc)
                except TypeError:
                    # we hope that this happens only when document needs to be encoded
                    stream.write(newdoc.encode("utf-8"))  # type: ignore
                self.options.output = None

            os.remove(nfn)
            
    # Runs a Python script using a Python binary in a working directory
    # It detaches from Inkscape, allowing it to continue running after the
    # extension has finished
    @staticmethod
    def _gtk_call(python_bin, python_script):
        """Run a Python script using GTK terminal."""
        devnull_location = dh.shared_temp(filename="si_ae_output.txt")
        with open(devnull_location, "w") as devnull:
            subprocess.Popen(
                [python_bin, python_script], stdout=devnull, stderr=devnull
            )

    @staticmethod
    def _terminal_call(python_bin, python_script, python_wd):
        """Run a Python script using a terminal."""

        def escp(x):
            return x.replace(" ", "\\\\ ")

        if sys.platform == "darwin":
            # https://stackoverflow.com/questions/39840632/launch-python-script-in-new-terminal
            os.system(
                'osascript -e \'tell application "Terminal" to do script "'
                + escp(sys.executable)
                + " "
                + escp(python_script)
                + "\"' >/dev/null"
            )
        elif sys.platform == "win32":
            if "pythonw.exe" in python_bin:
                python_bin = python_bin.replace("pythonw.exe", "python.exe")
            subprocess.Popen([python_bin, python_script], shell=False, cwd=python_wd)

            # if 'pythonw.exe' in python_bin:
            #     python_bin = python_bin.replace('pythonw.exe', 'python.exe')
            # DETACHED_PROCESS = 0x08000000
            # subprocess.Popen([python_bin, python_script, 'standalone'],
            # creationflags=DETACHED_PROCESS)
        else:
            if sys.executable[0:4] == "/tmp":
                inkex.utils.errormsg(
                    "This appears to be an AppImage of Inkscape, which the "
                    "Autoexporter cannot support since AppImages are sandboxed."
                )
                return
            if sys.executable[0:5] == "/snap":
                inkex.utils.errormsg(
                    "This appears to be an Snap installation of Inkscape, which "
                    "the Autoexporter cannot support since Snap installations "
                    "are sandboxed."
                )
                return
            terminals = [
                "x-terminal-emulator",
                "mate-terminal",
                "gnome-terminal",
                "terminator",
                "xfce4-terminal",
                "urxvt",
                "rxvt",
                "termit",
                "Eterm",
                "aterm",
                "uxterm",
                "xterm",
                "roxterm",
                "termite",
                "lxterminal",
                "terminology",
                "st",
                "qterminal",
                "lilyterm",
                "tilix",
                "terminix",
                "konsole",
                "kitty",
                "guake",
                "tilda",
                "alacritty",
                "hyper",
                "terminal",
                "iTerm",
                "mintty",
                "xiterm",
                "terminal.app",
                "Terminal.app",
                "terminal-w",
                "terminal.js",
                "Terminal.js",
                "conemu",
                "cmder",
                "powercmd",
                "terminus",
                "termina",
                "terminal-plus",
                "iterm2",
                "terminus-terminal",
                "terminal-tabs",
            ]
            terms = []
            for terminal in terminals:
                result = subprocess.run(
                    ["which", terminal],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if result.returncode == 0:
                    terms.append(terminal)

            for t in reversed(terms):
                if t == "x-terminal-emulator":
                    linux_terminal_call = "x-terminal-emulator -e bash -c '%CMD'"
                elif t == "gnome-terminal":
                    linux_terminal_call = 'gnome-terminal -- bash -c "%CMD; exec bash"'
                elif t == "konsole":
                    linux_terminal_call = "konsole -e bash -c '%CMD'"
            os.system(
                linux_terminal_call.replace(
                    "%CMD",
                    escp(sys.executable) + " " + escp(python_script) + " >/dev/null",
                )
            )

class Exporter():
    def __init__(self,fin,opts):
        self.filein = fin
        self.__dict__.update(vars(opts))
        
    sema_temp = threading.Semaphore(1)
    def export_all(self):
        """Export all files in specified formats."""
        # Make a temp directory
        self.tempdir, self.temphead = dh.shared_temp('ae')
        self.tempbase = joinmod(self.tempdir,self.temphead)
        

        if self.debug:
            if self.prints:
                self.prints("\n    " + joinmod(self.tempdir, ""))

        # Make sure output directory exists
        outdir = os.path.dirname(self.outtemplate)
        if not os.path.exists(outdir):
            os.makedirs(outdir)

        # Add a document margin
        cfile = self.filein # current file we're working on
        if self.margin != 0:
            svg = get_svg(cfile)
            tmp = self.tempbase + "_marg.svg"
            Exporter.add_margin(svg, self.margin, self.testmode)
            dh.overwrite_svg(svg, tmp)
            cfile = copy.copy(tmp)

        # Do png before any preprocessing
        if "png" in self.formats:
            finished, myo = self.export_file(cfile, "png")

        # Do preprocessing
        if any(fmt in self.formats for fmt in ["pdf", "emf", "eps", "psvg"]):
            cfile = self.preprocessing(cfile)

        # Do vector outputs
        newfiles = []
        for fmt in self.formats:
            if fmt != "png":
                finished, myo = self.export_file(cfile, fmt)
            if finished:
                newfiles.append(myo)

        # Remove temporary outputs and directory
        failed_to_delete = None
        if not (self.debug):
            self.clear_temp()
        else:
            warnings.simplefilter("ignore", ResourceWarning)
            # prevent warning that process is open
            subprocess.Popen(f'explorer "{os.path.realpath(self.tempdir)}"')
        return failed_to_delete

    def clear_temp(self):
        """ Clear any temporary files """
        if not (self.debug):
            tmps = []
            for t in os.listdir(self.tempdir):
                tmp = joinmod(self.tempdir, t)
                try:
                    one_day_ago = time.time() - 24 * 60 * 60
                    if os.path.getmtime(tmp) < one_day_ago:
                        tmps.append(joinmod(self.tempdir, t))
                except FileNotFoundError: # already deleted
                    pass
                if tmp.startswith(self.tempbase):
                    tmps.append(joinmod(self.tempdir, t))
            for tmp in tmps:
                if os.path.exists(tmp):
                    deleted = False
                    nattempts = 0
                    while not (deleted) and nattempts < MAXATTEMPTS:
                        try:
                            os.remove(tmp)
                            deleted = True
                        except PermissionError:
                            time.sleep(1)
                            nattempts += 1

    def preprocessing(self, fin):
        """Modifications that are done prior to conversion to any vector output"""
        if self.prints:
            fname = os.path.split(self.filein)[1]
            try:
                offset = round(os.get_terminal_size().columns / 2)
            except OSError:
                offset = 40
            fname = fname + " " * max(0, offset - len(fname))
            self.prints(fname + ": Preprocessing vector output", flush=True)
            timestart = time.time()

        tempdir = self.tempdir
        temphead = self.temphead

        # SVG modifications that should be done prior to any binary calls
        cfile = fin
        svg = get_svg(cfile)

        # Prune hidden items and remove language switching
        stag = inkex.addNS("switch", "svg")
        todelete, todelang, switches = [], [], []
        for elem in dh.visible_descendants(svg):
            if elem.cspecified_style.get("display") == "none":
                todelete.append(elem)
            if elem.get("systemLanguage") is not None:
                lang = inkex.inkscape_system_info.language
                if elem.get("systemLanguage") == lang:
                    todelang.append(elem)
                    # Remove other languages from switches
                    if elem.getparent().tag == stag:
                        todelete.extend(
                            [
                                k
                                for k in elem.getparent()
                                if k.get("systemLanguage") != lang
                            ]
                        )
                else:
                    # Remove non-matching languages
                    todelete.append(elem)
            if elem.tag == stag:
                switches.append(elem)
        for elem in unique(todelete):
            elem.delete()
        for elem in todelang:
            elem.set("systemLanguage", None)
        for elem in switches:
            if len(elem)==1:
                dh.ungroup(elem)

        # Embed linked images into the SVG. This should be done prior to clone unlinking
        # since some images may be cloned
        if self.exportnow:
            lls = self.linked_locations
        else:
            lls = ih.get_linked_locations_file(cfile, svg)
        for k in lls:
            elem = svg.getElementById(k)
            ih.embed_external_image(elem, lls[k])

        vds = dh.visible_descendants(svg)
        raster_ids, image_ids, jpgs = [], [], []
        for elem in vds:
            # Unlink any clones for the PDF image and marker fixes
            if isinstance(elem, (inkex.Use)) and not (isinstance(elem, (inkex.Symbol))):
                newel = dh.unlink2(elem)
                myi = vds.index(elem)
                vds[myi] = newel
                for ddv in newel.descendants2()[1:]:
                    vds.append(ddv)

            # Remove trivial groups inside masks/transparent objects or clipped groups
            if isinstance(elem, (inkex.Group)):
                ancs = elem.ancestors2(includeme=True)
                masked = any(
                    anc.get_link("mask", svg) is not None
                    or (
                        elem.ccascaded_style.get("opacity") is not None
                        and float(elem.ccascaded_style.get("opacity")) < 1
                    )
                    for anc in ancs
                )
                clipped = any(
                    anc.get_link("clip-path", svg) is not None for anc in ancs
                )
                if (
                    len(list(elem)) == 1
                    and (masked or clipped)
                    and elem.get("autoexporter_rasterize") not in ["png", "jpg", "True"]
                ):
                    dh.ungroup(elem)

            # Remove groups inside clips
            cpth = elem.get_link("clip-path", svg)
            if cpth is not None:
                while any(isinstance(v, inkex.Group) for v in list(cpth)):
                    for grp in list(cpth):
                        if isinstance(grp, inkex.Group):
                            dh.ungroup(grp)

        stps = []
        ttps = []
        for elem in vds:
            elid = elem.get_id()

            # Fix marker export bug for PDFs
            mkrs = Exporter.marker_fix(elem)
            # Convert markers to path for Office
            if len(mkrs) > 0 and self.usepsvg:
                stps.append(elid)

            # Fix opacity bug for Office PDF saving
            if len(mkrs) == 0:  # works poorly with markers
                Exporter.opacity_fix(elem)

            # Disable connectors
            elem.set("inkscape:connector-type", None)

            # Find out which objects need to be rasterized
            sty = elem.cstyle
            # only want the object with the filter
            if sty.get_link("filter", svg) is not None:
                raster_ids.append(elid)  # filtered objects (always rasterized at PDF)
            if (sty.get("fill") is not None and "url" in sty.get("fill")) or (
                sty.get("stroke") is not None and "url" in sty.get("stroke")
            ):
                raster_ids.append(elid)  # gradient objects
            if elem.get_link("mask") is not None:
                raster_ids.append(elid)  # masked objects (always rasterized at PDF)
            if elem.get("autoexporter_rasterize") in ["png", "jpg", "True"]:
                raster_ids.append(elid)
                # rasterizer-marked
                if elem.get("autoexporter_rasterize") == "jpg":
                    jpgs.append(elid)
            if elem.get("autoexporter_rasterize")=='topath':
                ttps.append(elid)
            if isinstance(elem, (inkex.Image)):
                image_ids.append(elid)
                # Inkscape inappropriately clips non-'optimizeQuality' images
                # when generating PDFs and calculating bounding boxes
                elem.cstyle["image-rendering"] = "optimizeQuality"
                # Set image x,y,width,height to standard values to prevent Office
                # from mishandling clips
                Exporter.standardize_image(elem)

            # Remove style attributes with invalid URLs
            # (Office doesn't display the element while Inkscape ignores it)
            for satt in list(sty.keys()):
                if (
                    satt in dh.urlatts
                    and sty.get(satt).startswith("url")
                    and sty.get_link(satt, svg) is None
                ):
                    elem.cstyle[satt] = None

            # Prune single-point paths, which Inkscape doesn't show
            if elem.tag in otp_support_tags:
                pth = elem.cpath
                firstpt = None
                trivial = True
                for pnt in pth.end_points:
                    if firstpt is None:
                        firstpt = (pnt.x, pnt.y)
                    elif (pnt.x, pnt.y) != firstpt:
                        trivial = False
                        break
                if trivial:
                    elem.delete(deleteup=True)

        # Fix Avenir/Whitney
        tetag = inkex.TextElement.ctag
        frtag = inkex.FlowRoot.ctag
        tels = [elem for elem in vds if elem.tag in {tetag, frtag}]

        dh.character_fixer(tels)

        # Strip all sodipodi:role lines from document
        # Conversion to plain SVG does this automatically but poorly
        excludetxtids = []
        self.duplicatelabels = dict()
        # if self.usepsvg:
        if len(tels) > 0:
            svg.make_char_table()
            self.ctable = svg.char_table
            # store for later

        nels = []
        for elem in reversed(tels):
            if elem.parsed_text.isflow:
                nels += elem.parsed_text.flow_to_text()
                tels.remove(elem)
        tels += nels

        for elem in tels:
            elem.parsed_text.strip_text_baseline_shift()
            elem.parsed_text.strip_sodipodi_role_line()
            elem.parsed_text.fuse_fonts()
            Exporter.subsuper_fix(elem)

            # Preserve duplicate of text to be converted to paths
            if self.texttopath and elem.get("display") != "none" and elem.croot is not None:
                dup = elem.duplicate()
                excludetxtids.append(dup.get_id())
                grp = dh.group([dup])
                grp.set("display", "none")

                # tel = svg.new_element(inkex.TextElement, svg)
                tel = inkex.TextElement()
                grp.append(tel)  # Remember the original ID
                tel.text = "{0}: {1}".format(DUP_KEY, elem.get_id())
                tel.set("display", "none")
                excludetxtids.append(tel.get_id())
                self.duplicatelabels[tel.get_id()] = elem.get_id()

                # Make sure nested tspans have fill specified (STP bug)
                for dsd in elem.descendants2()[1:]:
                    if (
                        "fill" in dsd.cspecified_style
                        and dsd.cspecified_style["fill"] != "#000000"
                    ):
                        dsd.cstyle["fill"] = dsd.cspecified_style["fill"]

        tmp = self.tempbase + "_mod.svg"
        dh.overwrite_svg(svg, tmp)
        cfile = tmp
        self.excludetxtids = excludetxtids

        do_rasterizations = len(raster_ids + image_ids) > 0
        do_stroketopaths = self.texttopath or self.stroketopath or len(stps) > 0 or len(ttps)>0

        dpi = self.dpi
        class Act():
            '''
            Represents a single binary call Action. 
            type == 'stp' creates an action that stroke-to-path's a group of objects
            type == 'imgt' exports a PNG copy of an image with a transparent background
            type == 'imgo' exports a PNG copy of an image with an opaque background, and objects above hidden
            '''
            def __init__(self,typ,els,fname=None,overlaps=None):
                self.type = typ
                if isinstance(els,list):
                    self.els = els
                else:
                    self.els = [els]
                if fname is None:
                    elid = self.els[0].get_id()
                    if typ=='imgt':
                        fname = temphead + "_im_" + elid + "." + imgtype
                    else:
                        fname = temphead + "_imbg_" + elid + "." + imgtype
                self.fname = fname;
                self.overlaps = overlaps
            
            if (
                (self.stroketopath or len(stps) > 0)
                and inkex.installed_ivp[0] >= 1
                and inkex.installed_ivp[1] > 0
            ):
                stpact = "object-stroke-to-path"
            else:
                stpact = "object-to-path"
            
            def __str__(self):
                if self.type == 'stp':
                    return "select:{0}; {1}; export-filename:{2}; export-do; unselect:{0}; ".format(
                        ",".join(self.els), Act.stpact, self.fname
                    )
                elif self.type == 'imgt':
                    fmt1 = (
                        "export-id:{0}; export-id-only; export-dpi:{1}; "
                        "export-filename:{2}; export-background-opacity:0.0; "
                        "export-do; "
                    )
                    return fmt1.format(self.els[0].get_id(), int(dpi), self.fname)
                elif self.type == 'imgo':
                    el = self.els[0]
                    fmt2 = (
                        "export-id:{0}; export-dpi:{1}; "
                        "export-filename:{2}; export-background-opacity:1.0; "
                        "export-do; "
                    )
                    actv = fmt2.format(el.get_id(), int(dpi), self.fname)
                    
                    # For export all, hide objects on top
                    displays = {el: el.cstyle.get('display') for el in overlaps[el]}
                    hides = ['select:{0}; object-set-property:display,none; unselect:{0}; '.format(el.get_id()) for el in overlaps[el]]
                    unhides = ['select:{0}; object-set-property:display,{1}; unselect:{0}; '.format(el.get_id(), \
                                displays[el] if displays[el] is not None else '') for el in overlaps[el]]
                    return ''.join(hides) + actv + ''.join(unhides)
                
            def split(self,intermediate_fn):
                ''' Splits a STP act into two sub-acts '''
                spl = math.ceil(len(self.els) / 2)
                act1 = Act('stp',self.els[:spl],intermediate_fn)
                act2 = Act('stp',self.els[spl:],self.fname)
                return act1, act2
                    

        allacts = []
        if do_stroketopaths:
            svg = get_svg(cfile)
            vdd = dh.visible_descendants(svg)

            updatefile = False
            tels = []
            if self.texttopath or len(ttps)>0:
                for elem in vdd:
                    if (elem.get_id() in ttps or self.texttopath) and (elem.tag == tetag and elem.get_id() not in excludetxtids):
                        tels.append(elem.get_id())
                        for dsd in elem.descendants2():
                            # Fuse fill and stroke to account for STP bugs
                            if "fill" in dsd.cspecified_style:
                                dsd.cstyle["fill"] = dsd.cspecified_style["fill"]
                                updatefile = True
                            if "stroke" in dsd.cspecified_style:
                                dsd.cstyle["stroke"] = dsd.cspecified_style["stroke"]
                                updatefile = True

            pels, dgroups = [], []
            if self.stroketopath or len(stps) > 0:
                # Stroke to Path has a number of bugs, try to fix them
                if self.stroketopath:
                    stpels = vdd
                elif len(stps) > 0:
                    stpels = [el for el in vdd if el.get_id() in stps]
                stpels = [el for el in stpels if el.get_id() not in raster_ids]
                pels, dgroups = Exporter.stroke_to_path_fixes(stpels)
                updatefile = True

            if updatefile:
                dh.overwrite_svg(svg, cfile)

            tmpstp = self.tempbase + "_stp.svg"
            allacts += [Act('stp',tels + pels,tmpstp)]
            

        # Rasterizations
        actts, actos  = [], []
        if do_rasterizations:
            svg = get_svg(cfile)

            vds = dh.visible_descendants(svg)
            els = [el for el in vds if el.get_id() in list(set(raster_ids + image_ids))]
            if len(els) > 0:
                imgtype = "png"
                
                overlaps = dh.overlapping_els(svg,els)
                for elem in els:
                    elid = elem.get_id()
                    actts.append(Act('imgt',elem))
                    actos.append(Act('imgo',elem,overlaps=overlaps))
                
                allacts += (actos + actts) if ih.hasPIL else actts
                # export-id-onlys need to go last
                
        imgs_trnp = {act.fname:act.els[0].get_id() for act in actts}
        imgs_opqe = {act.fname:act.els[0].get_id() for act in actos}

        # To reduce the number of binary calls, we collect the stroke-to-path and
        # rasterization actions into a single call that also gets the Bounding Boxes.
        # Skip binary call during testing
        if len(allacts) > 0 and not self.testmode:
            # use relative paths to reduce arg length
            
            bbs = self.split_acts(fnm=cfile, acts=allacts)
            
            imgs = imgs_opqe | imgs_trnp
            missing_images = [t for t in imgs if not os.path.exists(os.path.join(tempdir, t)) and imgs[t] in bbs]
            if missing_images:
                raise TimeoutError(
                    "\nThe Inkscape binary could not generate the temporary images "
                    + ", ".join(missing_images) + ' in ' + tempdir + '.\n\n'
                    + "This may be a temporary issue; try running the extension again."
                )
            if do_stroketopaths:
                cfile = tmpstp

        if do_rasterizations:
            svg = get_svg(cfile)
            vds = dh.visible_descendants(svg)
            els = [el for el in vds if el.get_id() in list(set(raster_ids + image_ids))]
            if len(els) > 0:
                jimgs_trnp = [os.path.join(tempdir, t) for t in imgs_trnp]
                jimgs_opqe = [os.path.join(tempdir, t) for t in imgs_opqe]

                for i, elem in enumerate(els):
                    img_trnp = jimgs_trnp[i]
                    img_opqe = jimgs_opqe[i]

                    if os.path.exists(img_trnp):
                        anyalpha0 = False
                        if ih.hasPIL:
                            bbox = ih.crop_images([img_trnp, img_opqe])
                            anyalpha0 = ih.Set_Alpha0_RGB(img_trnp, img_opqe)
                            if elem.get_id() in jpgs:
                                tmpjpg = img_trnp.replace(".png", ".jpg")
                                ih.to_jpeg(img_opqe, tmpjpg)
                                img_trnp = copy.copy(tmpjpg)
                        else:
                            bbox = None

                        # Compare size of old and new images
                        osz = ih.embedded_size(elem)
                        if osz is None:
                            osz = float("inf")
                        nsz = os.path.getsize(img_trnp)
                        hasmaskclip = (
                            elem.get_link("mask") is not None
                            or elem.get_link("clip-path") is not None
                        )  # clipping and masking
                        embedimg = (nsz < osz) or (anyalpha0 or hasmaskclip)
                        if embedimg:
                            Exporter.replace_with_raster(
                                elem, img_trnp, bbs[elem.get_id()], bbox
                            )

                tmp = self.tempbase + "_eimg.svg"
                dh.overwrite_svg(svg, tmp)
                cfile = tmp

        if do_stroketopaths:
            svg = get_svg(cfile)
            # Remove temporary groups
            if self.stroketopath:
                for elid in dgroups:
                    elem = svg.getElementById(elid)
                    if elem is not None:
                        dh.ungroup(elem)

            tmp = self.tempbase + "_poststp.svg"
            dh.overwrite_svg(svg, tmp)
            cfile = tmp

        if self.prints:
            self.prints(
                fname
                + ": Preprocessing done ("
                + str(round(1000 * (time.time() - timestart)) / 1000)
                + " s)"
            )
        return cfile
    
    def check(self,func, *args, **kwargs):
        """Wraps a binary call with a check if thread has been stopped; if so, clear the temp file and exit"""
        with sema1 if func==dh.wrapped_binary else sema2:
            if hasattr(self, "aeThread") and self.aeThread.stopped is True:
                self.clear_temp()
                sys.exit()
            ret = func(*args, **kwargs)
            if hasattr(self, "aeThread") and self.aeThread.stopped is True:
                self.clear_temp()
                sys.exit()
            return ret

    def split_acts(self, fnm, acts, reserved=None, get_bbs=True):
        """Split actions and run."""
        if reserved is None:
            reserved = set()

        eargs = ["--actions", "".join([str(a) for a in acts])]
        bbs = None
        try:
            bbs = self.check(dh.wrapped_binary,filename=fnm, inkscape_binary=self.bfn, extra_args=eargs, get_bbs = get_bbs, cwd=self.tempdir)
            fnf_err = False
        except FileNotFoundError:
            fnf_err = True
                
                
        missing_exports = []
        missing_fns = []
        found_fns = []
        for i, act in enumerate(acts):
            actfile = act.fname
            if actfile is not None and not os.path.exists(joinmod(self.tempdir,actfile)):
                missing_exports.append(act)
                missing_fns.append(actfile)
            if os.path.exists(joinmod(self.tempdir,actfile)):
                found_fns.append(actfile)
                
        # dh.idebug('Found '+str(found_fns))
        # dh.idebug('FNF: '+str(fnf_err))
        # dh.idebug('Missing ' + str(missing_fns) +'\n')
        
        if fnf_err:
            if len(acts)==1:
                if missing_exports[0].type=='stp':
                    bbs = self.split_stp(
                        fnm, missing_exports, 0, reserved=reserved, get_bbs = get_bbs
                    )
                else:
                    # Already simplified call as much as we can...
                    raise Exception('FileNotFoundError and cannot split:\n'+str(acts))
            elif len(missing_exports)>0:
                acts1 = missing_exports[: math.ceil(len(missing_exports) / 2)]
                acts2 = missing_exports[math.ceil(len(missing_exports) / 2) :]
                bbs = self.split_acts(
                    fnm=fnm, acts=acts1, reserved=reserved, get_bbs = get_bbs
                )
                if len(acts2)>0:
                    self.split_acts(
                        fnm=fnm, acts=acts2, reserved=reserved, get_bbs = False
                    )
        elif any(act.type=='stp' for act in missing_exports):
            stp_idx = [i for i, act in enumerate(missing_exports) if act.type=='stp'][0]
            bbs = self.split_stp(
                fnm, missing_exports, stp_idx, reserved=reserved, get_bbs = get_bbs
            )
        return bbs
    
    
    def split_stp(self,fnm, acts, selii, reserved, get_bbs=True, cwd=None):
        """
        Windows cannot handle arguments that are too long.
        If needed, this can split a stroke-to-path operation into two.
        """
        act = acts[selii]
        actfn = act.fname

        reserved.update({fnm, actfn})
        isreserved = True
        cnt = 0
        while isreserved:
            actfna = actfn.strip(".svg") + str(cnt) + ".svg"
            isreserved = actfna in reserved
            cnt += 1
        reserved.update({actfna})

        if len(act.els) == 1:
            # cannot split, fact that we failed means there is a STP crash
            shutil.copy(fnm, actfn)
            return self.split_acts(
                fnm=fnm,
                acts=acts[:selii] + acts[selii + 1 :],
                reserved=reserved
            )
        act1, act2 = act.split(actfna)
        acts1 = acts[:selii] + [act1] if len(act1.els) > 0 else acts[:selii]
        acts2 = (
            [act2] + acts[selii + 1 :] if len(act2.els) > 0 else acts[selii + 1 :]
        )

        bbs = self.split_acts(
            fnm=fnm, acts=acts1, reserved=reserved, get_bbs=get_bbs
        )
        bbs = self.split_acts(
            fnm=actfna, acts=acts2, reserved=reserved, get_bbs=get_bbs
        )
        return bbs

    def export_file(self, fin, fformat):
        """Use the Inkscape binary to export the file"""
        myoutput = self.outtemplate[0:-4] + "." + fformat
        if self.prints:
            fname = os.path.split(self.filein)[1]
            try:
                offset = round(os.get_terminal_size().columns / 2)
            except OSError:
                offset = 40
            fname = fname + " " * max(0, offset - len(fname))
            self.prints(fname + ": Converting to " + fformat, flush=True)
        timestart = time.time()

        ispsvg = fformat == "psvg"
        notpng = not (fformat == "png")

        cfile = fin
        if self.thinline and notpng:
            svg = get_svg(cfile)
            if fformat in ["pdf", "eps"]:
                Exporter.thinline_dehancement(svg, "bezier")
            else:
                Exporter.thinline_dehancement(svg, "split")
            tmp = self.tempbase + "_tld" + fformat[0] + ".svg"
            dh.overwrite_svg(svg, tmp)
            cfile = copy.copy(tmp)

        if fformat == "psvg":
            myoutput = myoutput.replace(".psvg", "_plain.svg")

        def overwrite_output(filein, fileout):
            if os.path.exists(fileout):
                os.remove(fileout)
            args = [
                self.bfn,
                "--export-background",
                "#ffffff",
                "--export-background-opacity",
                "1.0",
                "--export-dpi",
                str(self.dpi),
                "--export-filename",
                fileout,
                filein,
            ]
            if fileout.endswith(".pdf") and self.latexpdf:
                if os.path.exists(fileout + "_tex"):
                    os.remove(fileout + "_tex")
                args = args[0:5] + ["--export-latex"] + args[5:]
            if fileout.endswith(".svg"):
                args = (
                    [args[0]]
                    + ["--vacuum-defs"]
                    + args[1:5]
                    + ["--export-plain-svg"]
                    + args[5:]
                )
            self.check(dh.subprocess_repeat,args)

        def make_output(filein, fileout):
            if fileout.endswith(".svg"):
                if not (self.testmode):
                    overwrite_output(filein, fileout)
                else:
                    shutil.copy(filein, fileout)  # skip conversion
                self.made_outputs = [fileout]

                osvg = get_svg(filein)

                pgs = osvg.cdocsize.pgs
                haspgs = inkex.installed_haspages
                if (haspgs or self.testmode) and len(pgs) > 0:
                    # bbs = dh.BB2(type("DummyClass", (), {"svg": osvg}))
                    bbs = dh.BB2(osvg)
                    dlbl = self.duplicatelabels
                    outputs = []
                    pgiis = (
                        range(len(pgs)) if not (self.testmode) else [self.testpage - 1]
                    )
                    for i in pgiis:
                        # match the viewbox to each page and delete them
                        psvg = get_svg(fileout)
                        # plain SVG has no pages
                        pgs2 = psvg.cdocsize.pgs

                        Exporter.change_viewbox_to_page(psvg, pgs[i])
                        # Only need to delete other Pages in testmode since
                        # plain SVGs have none
                        if self.testmode:
                            for j in reversed(range(len(pgs2))):
                                pgs2[j].delete()

                        # Delete content not on current page
                        pgbb = dh.bbox(psvg.cdocsize.effvb)
                        for k, bbx in bbs.items():
                            removeme = not (dh.bbox(bbx).intersect(pgbb))
                            if k in dlbl:
                                removeme = not (
                                    dlbl[k] in bbs
                                    and dh.bbox(bbs[dlbl[k]]).intersect(pgbb)
                                )
                            if removeme and psvg.getElementById(k) is not None:
                                psvg.getElementById(k).delete()

                        pname = pgs[i].get("inkscape:label")
                        pname = str(i + 1) if pname is None else pname
                        addendum = (
                            "_page_" + pname
                            if not (self.testmode or len(pgs) == 1)
                            else ""
                        )
                        outparts = fileout.split(".")
                        pgout = ".".join(outparts[:-1]) + addendum + "." + outparts[-1]
                        dh.overwrite_svg(psvg, pgout)
                        outputs.append(pgout)
                    self.made_outputs = outputs
            else:
                svg = get_svg(filein)
                pgs = svg.cdocsize.pgs

                haspgs = inkex.installed_haspages
                if (haspgs or self.testmode) and len(pgs) > 1:
                    outputs = []
                    pgiis = (
                        range(len(pgs)) if not (self.testmode) else [self.testpage - 1]
                    )
                    for i in pgiis:
                        # match the viewbox to each page and delete them
                        svgpg = get_svg(filein)
                        pgs2 = svgpg.cdocsize.pgs
                        Exporter.change_viewbox_to_page(svgpg, pgs[i])
                        for j in reversed(range(len(pgs2))):
                            pgs2[j].delete()

                        pname = pgs[i].get("inkscape:label")
                        pname = str(i + 1) if pname is None else pname
                        addendum = "_page_" + pname if not (self.testmode) else ""
                        svgpgfn = self.tempbase + addendum + ".svg"
                        dh.overwrite_svg(svgpg, svgpgfn)

                        outparts = fileout.split(".")
                        pgout = ".".join(outparts[:-1]) + addendum + "." + outparts[-1]
                        overwrite_output(svgpgfn, pgout)
                        outputs.append(pgout)
                    self.made_outputs = outputs
                else:
                    overwrite_output(filein, fileout)
                    self.made_outputs = [fileout]

        if not (ispsvg):
            make_output(cfile, myoutput)
            finalnames = self.made_outputs
        else:
            tmp = self.tempbase + "_tmp_small.svg"
            make_output(cfile, tmp)

            moutputs = self.made_outputs
            finalnames = []
            for mout in moutputs:
                svg = get_svg(mout)
                self.postprocessing(svg)
                finalname = myoutput
                if len(moutputs) > 1:
                    pnum, _ = os.path.splitext(mout.split("_page_")[-1])
                    finalname = myoutput.replace(
                        "_plain.svg", "_page_" + pnum + "_plain.svg"
                    )
                dh.overwrite_svg(svg, finalname)
                finalnames.append(finalname)

        # Remove any previous outputs that we did not just make
        directory, file_name = os.path.split(myoutput)
        base_name, extension = os.path.splitext(file_name)
        if extension == ".svg" and base_name.endswith("_plain"):
            base_name = base_name[:-6]  # Remove "_plain" from the base name
            pattern = re.compile(
                rf"{re.escape(base_name)}(_page_.*)?_plain{re.escape(extension)}$"
            )
        else:
            pattern = re.compile(
                rf"{re.escape(base_name)}(_page_.*)?{re.escape(extension)}$"
            )
        matching_files = []
        for file in os.listdir(directory):
            if pattern.match(file):
                matching_files.append(os.path.join(directory, file))
        for file in matching_files:
            if file not in finalnames:
                try:
                    os.remove(file)
                except PermissionError:
                    pass

        if self.prints:
            toc = time.time() - timestart
            self.prints(
                fname
                + ": Conversion to "
                + fformat
                + " done ("
                + str(round(1000 * toc) / 1000)
                + " s)"
            )
        return True, myoutput

    def postprocessing(self, svg):
        """Postprocessing of SVGs, mainly for overcoming bugs in Office products"""
        vds = dh.visible_descendants(svg)

        # Shift viewbox corner to (0,0) by translating top-level elements
        evb = svg.cdocsize.effvb
        if not (evb[0] == 0 and evb[1] == 0):
            newtr = Transform("translate(" + str(-evb[0]) + ", " + str(-evb[1]) + ")")
            svg.set_viewbox([0, 0, evb[2], evb[3]])
            ndefs = [el for el in list(svg) if not (el.tag in dh.unungroupable)]
            for elem in ndefs:
                elem.ctransform = newtr @ elem.ctransform

        for dsd in vds:
            if (
                isinstance(dsd, (TextElement))
                and dsd.get_id() not in self.excludetxtids
            ):
                scaleto = 100 if not self.testmode else 10
                # Make 10 px in test mode so that errors are not unnecessarily large
                Exporter.scale_text(dsd, scaleto)
            elif isinstance(dsd, (inkex.Image)):
                if ih.hasPIL:
                    Exporter.merge_mask(dsd)
                # while dsd.getparent()!=dsd.croot and dsd.getparent() is not None
                # and dsd.croot is not None:
                #     # iteratively remove groups containing images
                #     # I don't think it's necessary?
                #     dh.ungroup(dsd.getparent());
            elif isinstance(dsd, (inkex.Group)):
                if len(dsd) == 0:
                    dsd.delete(deleteup=True)

        if self.backingrect:
            r = inkex.Rectangle()
            tlvl = [el for el in list(svg) if not (el.tag in dh.unungroupable)]
            if len(tlvl) > 0:
                svg.insert(svg.index(tlvl[0]), r)
            else:
                svg.append(r)
            r.cstyle["fill"] = "#ffffff"
            r.cstyle["fill-opacity"] = ".00001"
            r.cstyle["stroke"] = "none"
            vbx = svg.cdocsize.effvb
            r.set("x", vbx[0])
            r.set("y", vbx[1])
            r.set("width", vbx[2])
            r.set("height", vbx[3])

        # if self.thinline:
        #     for dsd in vds:
        #         self.Bezier_to_Split(dsd)  # moved to deprecated

        # dh.idebug(self.svgtopdf_vbs)
        # embed_original = False
        # if embed_original:
        #     def main_contents(svg):
        #         ret = list(svg)
        #         for k in reversed(ret):
        #             if k.tag in [inkex.addNS('metadata','svg'),
        #                           inkex.addNS('namedview','sodipodi')]:
        #                 ret.remove(k);
        #         return ret

        #     grp  = dh.group(main_contents(svg))
        #     svgo = get_svg(original_file)
        #     go = dh.group(main_contents(svgo))
        #     svg.append(go)
        #     go.set('style','display:none');
        #     go.set('inkscape:label','SI original');
        #     go.set('inkscape:groupmode','layer');

        #     # Conversion to PDF changes the viewbox to pixels. Convert back to the
        #     # original viewbox by applying a transform
        #     dds = self.svgtopdf_dss[i]
        #     tfmt = 'matrix({0},{1},{2},{3},{4},{5})';
        #     T =inkex.Transform(tfmt.format(dds.uuw,0,0,dds.uuh,
        #                                       -dds.effvb[0]*dds.uuw,
        #                                       -dds.effvb[1]*dds.uuh))
        #     grp.set('transform',str(-T))
        #     svg.set_viewbox(dds.effvb)

        tel = None
        for elem in list(svg):
            if (
                isinstance(elem, (inkex.TextElement,))
                and elem.text is not None
                and ORIG_KEY in elem.text
            ):
                tel = elem
        if tel is None:
            # tel = svg.new_element(inkex.TextElement, svg)
            tel = inkex.TextElement()
            svg.append(tel)
        tel.text = ORIG_KEY + ": {0}, hash: {1}".format(
            self.original_file, hash_file(self.original_file)
        )
        tel.set("style", "display:none")
        dh.clean_up_document(svg)  # Clean up

    PTH_COMMANDS = list("MLHVCSQTAZmlhvcsqtaz")

    @staticmethod
    def thinline_dehancement(svg, mode="split"):
        """
        Prevents thin-line enhancement in certain bad PDF renderers
        'bezier' mode converts h,v,l path commands to trivial Beziers
        'split' mode splits h,v,l path commands into two path commands
        The Office PDF renderer removes trivial Beziers, as does conversion to EMF
        The Inkscape PDF/EPS renderer removes split commands
        Split is more general, so apply it to everything but PDFs/EPS
        """

        command_chars = {"h", "v", "l", "H", "V", "L"}
        split = mode == "split"
        for elem in svg.descendants2():
            if elem.tag in otp_support_tags and not elem.tag == peltag:
                elem.object_to_path()

            pthd = elem.get("d")
            if pthd and any(char in pthd for char in command_chars):
                if any(char in pthd for char in {"H", "V", "L"}):
                    pthd = str(inkex.Path(pthd).to_relative())
                dds = [v for v in pthd.replace(",", " ").split(" ") if v]
                current_command = None
                i = 0
                while i < len(dds):
                    token = dds[i]
                    if token in {"v", "h", "l"}:
                        current_command = token
                        dds[i] = ""
                    elif token in Exporter.PTH_COMMANDS:
                        current_command = None
                    else:
                        if current_command == "h":
                            hval = float(token)
                            dds[i] = (
                                f"h {hval / 2} {hval / 2}"
                                if split
                                else f"c {hval},0 {hval},0 {hval},0"
                            )
                        elif current_command == "v":
                            vval = float(token)
                            dds[i] = (
                                f"v {vval / 2} {vval / 2}"
                                if split
                                else f"c 0,{vval} 0,{vval} 0,{vval}"
                            )
                        elif current_command == "l":
                            lxv = float(token)
                            lyv = float(dds[i + 1])
                            dds[i] = (
                                f"l {lxv / 2},{lyv / 2} {lxv / 2},{lyv / 2}"
                                if split
                                else f"c {lxv},{lyv} {lxv},{lyv} {lxv},{lyv}"
                            )
                            dds[i + 1] = ""
                            i += 1
                    i += 1

                newd = " ".join(v for v in dds if v).replace("  ", " ")
                elem.set("d", newd)

    @staticmethod
    def marker_fix(elem):
        """Fixes the marker bug that occurs with context-stroke and context-fill"""
        mkrs = Exporter.get_markers(elem)
        sty = elem.cspecified_style
        for mtyp, mkrel in mkrs.items():
            dh.get_strokefill(elem)
            mkrds = mkrel.descendants2()
            anycontext = any(
                a in ("stroke", "fill") and "context" in v
                for d in mkrds
                for a, v in d.cspecified_style.items()
            )
            if anycontext:
                handled = True
                dup = mkrel.duplicate()
                dupds = dup.descendants2()
                for dsd in dupds:
                    dsty = dsd.cspecified_style
                    for att, val in dsty.items():
                        if att in ("stroke", "fill") and "context" in val:
                            if val == "context-stroke":
                                dsd.cstyle[att] = sty.get("stroke", "none")
                            elif val == "context-fill":
                                dsd.cstyle[att] = sty.get("fill", "none")
                            else:  # I don't know what this is
                                handled = False
                if handled:
                    elem.cstyle[mtyp] = dup.get_id(as_url=2)
        return mkrs

    @staticmethod
    def opacity_fix(elem):
        """
        Fuse opacity onto fill and stroke for path-like elements
        Helps prevent rasterization-at-PDF for Office products
        """
        sty = elem.cspecified_style
        if (
            sty.get("opacity") is not None
            and float(sty.get("opacity", 1.0)) != 1.0
            and elem.tag in otp_support_tags
        ):
            strf = dh.get_strokefill(elem)  # fuses opacity and
            # stroke-opacity/fill-opacity
            if strf.stroke is not None and strf.fill is None:
                elem.cstyle["stroke-opacity"] = strf.stroke.alpha
                elem.cstyle["opacity"] = 1
            elif strf.fill is not None and strf.stroke is None:
                elem.cstyle["fill-opacity"] = strf.fill.alpha
                elem.cstyle["opacity"] = 1

    @staticmethod
    def subsuper_fix(elem):
        """
        Replace super and sub with numerical values
        Collapse Tspans with 0% baseline-shift, which Office displays incorrectly
        """
        for dsd in elem.descendants2():
            bsh = dsd.ccascaded_style.get("baseline-shift")
            if bsh in ["super", "sub"]:
                sty = dsd.ccascaded_style
                sty["baseline-shift"] = "40%" if bsh == "super" else "-20%"
                dsd.cstyle = sty

        for dsd in reversed(elem.descendants2()):  # all Tspans
            bsh = dsd.ccascaded_style.get("baseline-shift")
            if bsh is not None and bsh.replace(" ", "") == "0%":
                # see if any ancestors with non-zero shift
                anysubsuper = False
                for anc in dsd.ancestors2(stopafter=elem):
                    bsa = anc.ccascaded_style.get("baseline-shift")
                    if bsa is not None and "%" in bsa:
                        anysubsuper = float(bsa.replace(" ", "").strip("%")) != 0

                # split parent
                myp = dsd.getparent()
                if anysubsuper and myp is not None:
                    dds = dh.split_text(myp)
                    for dsd2 in reversed(dds):
                        if (
                            len(list(dsd2)) == 1
                            and list(dsd2)[0].ccascaded_style.get("baseline-shift")
                            == "0%"
                        ):
                            sel = list(dsd2)[0]
                            mys = sel.ccascaded_style
                            if mys.get("baseline-shift") == "0%":
                                mys["baseline-shift"] = dsd2.ccascaded_style.get(
                                    "baseline-shift"
                                )
                            fsz, scf, _ = dh.composed_width(sel, "font-size")
                            mys["font-size"] = str(fsz / scf)
                            dsd2.addprevious(sel)
                            sel.cstyle = mys
                            sel.tail = dsd2.tail
                            dsd2.delete()
                            Exporter.subsuper_fix(
                                elem
                            )  # parent is now gone, so start over
                            return

    @staticmethod
    def scale_text(elem, scaleto):
        """
        Sets all font-sizes to 100 px by moving size into transform
        Office rounds every fonts to the nearest px and then transforms it,
        so this makes text sizes more accurate
        """
        svg = elem.croot
        szs = []
        for dsd in elem.descendants2():  # all Tspan sizes
            fsz = dsd.ccascaded_style.get("font-size")
            fsz = {"small": "10px", "medium": "12px", "large": "14px"}.get(fsz, fsz)
            if fsz is not None and "%" not in fsz:
                szs.append(dh.ipx(fsz))
        if len(szs) == 0:
            maxsz = default_style_atts["font-size"]
            maxsz = {"small": 10, "medium": 12, "large": 14}.get(maxsz, maxsz)
        else:
            maxsz = max(szs)

        scv = 1 / maxsz * scaleto

        # Make a dummy group so we can properly compose the transform
        grp = dh.group([elem], moveTCM=True)

        for dsd in reversed(elem.descendants2()):
            x = ParsedText.get_xy(dsd, "x")
            y = ParsedText.get_xy(dsd, "y")
            dxv = ParsedText.get_xy(dsd, "dx")
            dyv = ParsedText.get_xy(dsd, "dy")

            if x[0] is not None:
                xyset(dsd, "x", [v * scv for v in x])
            if y[0] is not None:
                xyset(dsd, "y", [v * scv for v in y])
            if dxv[0] is not None:
                xyset(dsd, "dx", [v * scv for v in dxv])
            if dyv[0] is not None:
                xyset(dsd, "dy", [v * scv for v in dyv])

            fsz, scf, _ = dh.composed_width(dsd, "font-size")
            if scf==0:
                continue
            dsd.cstyle["font-size"] = "{:.3f}".format(fsz / scf * scv)

            otherpx = [
                "letter-spacing",
                "inline-size",
                "stroke-width",
                "stroke-dasharray",
            ]
            for oth in otherpx:
                othv = dsd.ccascaded_style.get(oth)
                if (
                    othv is None
                    and oth == "stroke-width"
                    and "stroke" in dsd.ccascaded_style
                ):
                    othv = default_style_atts[oth]
                if othv is not None:
                    if "," not in othv:
                        if 'em' not in othv: # scaling not needed for em sizes
                            dsd.cstyle[oth] = str((dh.ipx(othv) or 0) * scv)
                    else:
                        dsd.cstyle[oth] = ",".join(
                            [str((dh.ipx(v) or 0) * scv) for v in othv.split(",")]
                        )

            shape = dsd.ccascaded_style.get_link("shape-inside", svg)
            if shape is not None:
                dup = shape.duplicate()
                svg.cdefs.append(dup)
                dup.ctransform = (
                    inkex.Transform((scv, 0, 0, scv, 0, 0)) @ dup.ctransform
                )
                dsd.cstyle["shape-inside"] = dup.get_id(as_url=2)

        elem.ctransform = inkex.Transform((1 / scv, 0, 0, 1 / scv, 0, 0))
        dh.ungroup(grp)

    @staticmethod
    def merge_mask(elem):
        """
        Office will poorly rasterize masked elements at PDF-time
        Revert alpha masks made by PDFication back to alpha
        """
        mymask = elem.get_link("mask")
        if mymask is not None and len(list(mymask)) == 1:
            # only if one object in mask
            mask = list(mymask)[0]
            if isinstance(mask, inkex.Image):
                if mask.get("height") == "1" and mask.get("width") == "1":
                    im1 = ih.str_to_ImagePIL(elem.get("xlink:href")).convert("RGBA")
                    im2 = ih.str_to_ImagePIL(mask.get("xlink:href")).convert("RGBA")
                    # only if mask the same size
                    if im1.size == im2.size:
                        d1a = np.asarray(im1)
                        d2a = np.asarray(im2)
                        # only if image is opaque
                        if np.where(d1a[:, :, 3] == 255, True, False).all():
                            nda = np.stack(
                                (
                                    d1a[:, :, 0],
                                    d1a[:, :, 1],
                                    d1a[:, :, 2],
                                    d2a[:, :, 0],
                                ),
                                2,
                            )
                            # pylint: disable=import-outside-toplevel
                            from PIL import Image as ImagePIL
                            # pylint: enable=import-outside-toplevel

                            newstr = ih.ImagePIL_to_str(ImagePIL.fromarray(nda))
                            elem.set("xlink:href", newstr)
                            mask.delete()
                            elem.set("mask", None)

    @staticmethod
    def standardize_image(elem):
        """Office has difficulty with clipped images with a nonzero x or y."""
        xv = dh.ipx(elem.get('x','0'))
        yv = dh.ipx(elem.get('y','0'))
        if xv!=0 or yv!=0:
            grp = dh.group([elem], moveTCM=True)
            elem.set('x','0')
            elem.set('y','0')
            elem.ctransform = inkex.Transform(f'translate({xv},{yv})')
            dh.ungroup(grp)

    @staticmethod
    def replace_with_raster(elem, imgloc, bbx, imgbbox):
        """Replace vector elements with raster images."""
        svg = elem.croot
        if svg is None:  # in case we were already rasterized within ancestor
            return
        ih.embed_external_image(elem, imgloc)

        # The exported image has a different size and shape than the original
        # Correct by putting transform/clip/mask on a new parent group, then
        # fix location, then ungroup
        grp = dh.group([elem], moveTCM=True)
        grp.set("clip-path", None)
        # conversion to bitmap already includes clips
        grp.set("mask", None)  # conversion to bitmap already includes masks

        # Calculate what transform is needed to preserve the image's location
        ctf = elem.ccomposed_transform
        pbb = [
            Vector2d(bbx[0], bbx[1]),
            Vector2d(bbx[0] + bbx[2], bbx[1]),
            Vector2d(bbx[0] + bbx[2], bbx[1] + bbx[3]),
            Vector2d(bbx[0], bbx[1] + bbx[3]),
        ]
        # top-left,tr,br,bl
        put = [
            (-ctf).apply_to_point(p) for p in pbb
        ]  # untransformed bbox (where the image needs to go)

        newel = inkex.Image()
        dh.replace_element(elem, newel)
        newel.set("x", 0)
        myx = 0
        newel.set("y", 0)
        myy = 0
        newel.set("width", 1)
        myw = dh.ipx(newel.get("width"))
        newel.set("height", 1)
        myh = dh.ipx(newel.get("height"))
        newel.set("xlink:href", elem.get("xlink:href"))

        # Inkscape inappropriately clips non-'optimizeQuality' images
        # when generating PDFs
        sty = "image-rendering:optimizeQuality"
        elem = newel

        pgo = [
            Vector2d(myx, myy),
            Vector2d(myx + myw, myy),
            Vector2d(myx + myw, myy + myh),
            Vector2d(myx, myy + myh),
        ]  # where the image is
        elem.set("preserveAspectRatio", "none")  # prevents aspect ratio snapping
        elem.set("style", sty)  # override existing styles

        # pylint: disable=invalid-name
        a = np.array(
            [
                [pgo[0].x, 0, pgo[0].y, 0, 1, 0],
                [0, pgo[0].x, 0, pgo[0].y, 0, 1],
                [pgo[1].x, 0, pgo[1].y, 0, 1, 0],
                [0, pgo[1].x, 0, pgo[1].y, 0, 1],
                [pgo[2].x, 0, pgo[2].y, 0, 1, 0],
                [0, pgo[2].x, 0, pgo[2].y, 0, 1],
            ]
        )
        b = np.array(
            [
                [
                    put[0].x,
                    put[0].y,
                    put[1].x,
                    put[1].y,
                    put[2].x,
                    put[2].y,
                ]
            ]
        ).T
        T = np.linalg.solve(a, b)
        T = "matrix(" + ",".join([str(v[0]) for v in T]) + ")"
        elem.set("transform", T)
        # pylint: enable=invalid-name

        # If we cropped, need to modify location according to bbox
        if ih.hasPIL and imgbbox is not None:
            elem.set("x", str(myx + imgbbox[0] * myw))
            elem.set("y", str(myy + imgbbox[1] * myh))
            elem.set("width", str((imgbbox[2] - imgbbox[0]) * myw))
            elem.set("height", str((imgbbox[3] - imgbbox[1]) * myh))
        dh.ungroup(grp)

    @staticmethod
    def add_margin(svg, amt_mm, testmode):
        """Add margin to the document."""
        mrgn = inkex.units.convert_unit(str(amt_mm) + "mm", "px")
        uuw, uuh = svg.cdocsize.uuw, svg.cdocsize.uuh
        # pgs = self.Get_Pages(svg)

        haspgs = inkex.installed_haspages or testmode
        if haspgs and len(svg.cdocsize.pgs) > 0:
            # Has Pages
            for page in svg.cdocsize.pgs:
                newbbuu = svg.cdocsize.pxtouupgs(
                    [
                        page.bbpx[0] - mrgn,
                        page.bbpx[1] - mrgn,
                        page.bbpx[2] + 2 * mrgn,
                        page.bbpx[3] + 2 * mrgn,
                    ]
                )
                page.set("x", str(newbbuu[0]))
                page.set("y", str(newbbuu[1]))
                page.set("width", str(newbbuu[2]))
                page.set("height", str(newbbuu[3]))
            svg.cdocsize = None

        else:
            # If an old version of Inkscape or has no Pages, defined by viewbox
            vbx = svg.cdocsize.effvb
            nvb = [
                vbx[0] - mrgn / uuw,
                vbx[1] - mrgn / uuh,
                vbx[2] + 2 * mrgn / uuw,
                vbx[3] + 2 * mrgn / uuh,
            ]
            svg.set_viewbox(nvb)

    @staticmethod
    def change_viewbox_to_page(svg, page):
        """Change viewbox to match specified page."""
        newvb = page.croot.cdocsize.pxtouu(page.bbpx)
        svg.set_viewbox(newvb)

    @staticmethod
    def get_markers(elem):
        """Returns valid marker keys and corresponding elements"""
        mkrd = dict()
        for mtyp in ["marker", "marker-start", "marker-mid", "marker-end"]:
            mkrel = elem.cstyle.get_link(mtyp, elem.croot)
            if mkrel is not None:
                mkrd[mtyp] = mkrel
        return mkrd

    @staticmethod
    def stroke_to_path_fixes(els):
        """
        Stroke to Path has tons of bugs. Try to preempt them.
        1. STP does not properly handle clips, so move clips and
           masks to a temp parent group.
        2. Densely-spaced nodes can be converted incorrectly, so scale paths up
           to be size 1000 and position corner at (0,0)
        3. Starting markers can be flipped.
        4. Markers on groups cause crashes
        5. Markers are given the wrong size
        """
        dummy_groups = []
        path_els = []
        stroked_els = []
        if len(els) > 0:
            svg = els[0].croot
        for elem in els:
            mkrs = Exporter.get_markers(elem)
            if isinstance(elem, inkex.Group) and len(mkrs) > 0:
                dh.ungroup(elem)
            elif elem.tag in otp_support_tags:
                sty = elem.cspecified_style
                if "stroke" in sty and sty["stroke"] != "none":
                    stroked_els.append((elem, sty, mkrs))

        for elem, sty, mkrs in stroked_els:
            swd = sty.get("stroke-width")
            if dh.ipx(swd) == 0:
                # Fix bug on zero-stroke paths
                sty["stroke"] = "none"
                elem.cstyle = sty
            elif swd is None:
                sty["stroke-width"] = default_style_atts['stroke-width']
            else:
                # Clip and mask issues solved by moving to a dummy parent group
                gndp = dh.group([elem], moveTCM=True)
                # Do it again so we can add transform later without
                # messing up clip
                grp = dh.group([elem], moveTCM=True)

                path_els.append(elem.get_id())
                dummy_groups.extend([gndp.get_id(), grp.get_id()])

                # Scale up most paths to be size 1000 and position corner
                # at (0,0)
                if inkex.addNS("type", "sodipodi") not in elem.attrib:
                    # Object to path doesn't currently support
                    # Inkscape-specific objects
                    elem.object_to_path()
                    bbx = elem.bounding_box2(
                        dotransform=False, includestroke=False, roughpath=False
                    )
                    if len(mkrs) == 0:
                        # scaleby = 1000
                        maxsz = max(bbx.w, bbx.h)
                        scaleby = 1000 / maxsz if maxsz > 0 else 1000
                    else:
                        # For paths with markers, scale to make stroke-width=1
                        # Prevents incorrect marker size
                        # https://gitlab.com/inkscape/inbox/-/issues/10506#note_1931910230
                        scaleby = 1 / dh.ipx(swd) if swd is not None else 1

                    tfm = Transform("scale({0})".format(scaleby)) @ Transform(
                        "translate({0},{1})".format(-bbx.x1, -bbx.y1)
                    )
                    # relative paths seem to have some bugs
                    pth2 = str(elem.cpath.to_absolute().transform(tfm))
                    elem.set("d", pth2)

                    # Put transform on parent group since STP cannot convert
                    # transformed paths correctly if they have dashes
                    # See https://gitlab.com/inkscape/inbox/-/issues/7844
                    grp.ctransform = -tfm

                    csty = elem.cspecified_style
                    if "stroke-width" in csty:
                        swd = dh.ipx(csty["stroke-width"])
                        elem.cstyle["stroke-width"] = str(swd * scaleby)
                    if "stroke-dasharray" in csty:
                        sda = dh.listsplit(csty["stroke-dasharray"])
                        elem.cstyle["stroke-dasharray"] = (
                            str([(sdv or 0) * scaleby for sdv in sda])
                            .strip("[")
                            .strip("]")
                        )

                # Fix bug on start markers where auto-start-reverse
                # oriented markers are inverted by STP
                sty = elem.cspecified_style
                mstrt = sty.get_link("marker-start", svg)
                if mstrt is not None:
                    if mstrt.get("orient") == "auto-start-reverse":
                        dup = mstrt.duplicate()
                        dup.set("orient", "auto")
                        for dkid in list(dup):
                            dkid.ctransform = Transform("scale(-1)") @ dkid.ctransform
                        sty["marker-start"] = dup.get_id(as_url=2)
                        elem.cstyle = sty
        return path_els, dummy_groups


# Convenience functions
def joinmod(dirc, fname):
    """Join directory and file name with absolute path."""
    return os.path.join(os.path.abspath(dirc), fname)

def get_svg(fin):
    """Load an SVG file and return the root svg element."""
    try:
        svg = inkex.load_svg(fin).getroot()
    except lxml.etree.XMLSyntaxError:
        # Try removing problematic bytes
        with open(fin, "rb") as file:
            bytes_content = file.read()
        cleaned_content = bytes_content.decode("utf-8", errors="ignore")
        nfin = dh.shared_temp(filename="cleaned.svg")
        with open(nfin, "w", encoding="utf-8") as file:
            file.write(cleaned_content)
        svg = inkex.load_svg(nfin).getroot()
    return svg


ORIG_KEY = "si_ae_original_filename"
DUP_KEY = "si_ae_original_duplicate"


def hash_file(filename):
    """Calculate hash of a file."""
    hashv = hashlib.sha256()
    with open(filename, "rb") as file:
        chunk = 0
        while chunk != b"":
            chunk = file.read(1024)
            hashv.update(chunk)
    return hashv.hexdigest()


if __name__ == "__main__":
    dh.Run_SI_Extension(AutoExporter(), "Autoexporter")