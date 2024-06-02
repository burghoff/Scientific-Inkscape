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

USE_TERMINAL = False
DEBUGGING = False
dispprofile = False

import dhelpers as dh
import subprocess
import inkex
from inkex import TextElement, Transform, PathElement, Vector2d

import os, sys, time, re, lxml
import numpy as np

import image_helpers as ih
from inkex.text.utils import default_style_atts, unique
from inkex.text.cache import BaseElementCache
otp_support_tags = BaseElementCache.otp_support_tags
import inkex.text.parser  # needed to prevent GTK crashing


# Convenience functions
def joinmod(dirc, f):
    return os.path.join(os.path.abspath(dirc), f)


def subprocess_check(inputargs, input_opts):
    if hasattr(input_opts, "aeThread") and input_opts.aeThread.stopped == True:
        delete_quit(input_opts.aeThread.tempdir)
    dh.subprocess_repeat(inputargs)
    if hasattr(input_opts, "aeThread") and input_opts.aeThread.stopped == True:
        delete_quit(input_opts.aeThread.tempdir)


def get_svg(fin):
    try:
        svg = inkex.load_svg(fin).getroot()
    except lxml.etree.XMLSyntaxError:
        # Try removing problematic bytes
        with open(fin, "rb") as f:
            bytes_content = f.read()
        cleaned_content = bytes_content.decode("utf-8", errors="ignore")
        nfin = dh.si_tmp(filename="cleaned.svg")
        with open(nfin, "w", encoding="utf-8") as f:
            f.write(cleaned_content)
        svg = inkex.load_svg(nfin).getroot()
    return svg


def delete_quit(tempdir):
    Delete_Dir(tempdir)
    sys.exit()


orig_key = "si_ae_original_filename"
dup_key = "si_ae_original_duplicate"


def hash_file(filename):
    import hashlib

    h = hashlib.sha256()
    with open(filename, "rb") as file:
        chunk = 0
        while chunk != b"":
            chunk = file.read(1024)
            h.update(chunk)
    return h.hexdigest()


# Runs a Python script using a Python binary in a working directory
# It detaches from Inkscape, allowing it to continue running after the extension has finished
def gtk_call(python_bin, python_script, python_wd):
    DEVNULL = dh.si_tmp(filename="si_ae_output.txt")
    with open(DEVNULL, "w") as devnull:
        subprocess.Popen([python_bin, python_script], stdout=devnull, stderr=devnull)


def terminal_call(python_bin, python_script, python_wd):
    def escp(x):
        return x.replace(" ", "\\\\ ")

    import platform

    if platform.system().lower() == "darwin":
        # https://stackoverflow.com/questions/39840632/launch-python-script-in-new-terminal
        os.system(
            'osascript -e \'tell application "Terminal" to do script "'
            + escp(sys.executable)
            + " "
            + escp(python_script)
            + "\"' >/dev/null"
        )
    elif platform.system().lower() == "windows":
        if "pythonw.exe" in python_bin:
            python_bin = python_bin.replace("pythonw.exe", "python.exe")
        subprocess.Popen([python_bin, python_script], shell=False, cwd=python_wd)

        # if 'pythonw.exe' in python_bin:
        #     python_bin = python_bin.replace('pythonw.exe', 'python.exe')
        # DETACHED_PROCESS = 0x08000000
        # subprocess.Popen([python_bin, python_script, 'standalone'], creationflags=DETACHED_PROCESS)
    else:
        if sys.executable[0:4] == "/tmp":
            inkex.utils.errormsg(
                "This appears to be an AppImage of Inkscape, which the Autoexporter cannot support since AppImages are sandboxed."
            )
            return
        elif sys.executable[0:5] == "/snap":
            inkex.utils.errormsg(
                "This appears to be an Snap installation of Inkscape, which the Autoexporter cannot support since Snap installations are sandboxed."
            )
            return
        else:
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
                    ["which", terminal], stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                if result.returncode == 0:
                    terms.append(terminal)

            for t in reversed(terms):
                if t == "x-terminal-emulator":
                    LINUX_TERMINAL_CALL = "x-terminal-emulator -e bash -c '%CMD'"
                elif t == "gnome-terminal":
                    LINUX_TERMINAL_CALL = 'gnome-terminal -- bash -c "%CMD; exec bash"'
                elif t == "konsole":
                    LINUX_TERMINAL_CALL = "konsole -e bash -c '%CMD'"
            os.system(
                LINUX_TERMINAL_CALL.replace(
                    "%CMD",
                    escp(sys.executable) + " " + escp(python_script) + " >/dev/null",
                )
            )


# Delete a directory and its contents, trying repeatedly on failure
def Delete_Dir(dirpath):
    MAXATTEMPTS = 2
    for t in list(set(os.listdir(dirpath))):
        deleted = False
        nattempts = 0
        while not (deleted) and nattempts < MAXATTEMPTS:
            try:
                os.remove(joinmod(dirpath, t))
                deleted = True
            except:
                time.sleep(5)
                nattempts += 1
    if dirpath is not None:
        deleted = False
        nattempts = 0
        while not (deleted) and nattempts < MAXATTEMPTS:
            try:
                # print('Attempting to delete '+os.path.split(dirpath)[-1])
                os.rmdir(dirpath)
                deleted = True
            except:
                time.sleep(5)
                nattempts += 1


PTH_COMMANDS = list("MLHVCSQTAZmlhvcsqtaz")


class AutoExporter(inkex.EffectExtension):
    def add_arguments(self, pars):
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
            "--stroketopath", type=inkex.Boolean, default=False, help="Stroke to paths?"
        )
        pars.add_argument(
            "--latexpdf", type=inkex.Boolean, default=False, help="Make LaTeX PDF?"
        )
        pars.add_argument(
            "--watchhere", type=inkex.Boolean, default=False, help="Watch here"
        )
        pars.add_argument(
            "--exportnow", type=inkex.Boolean, default=False, help="Export me now"
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

    def effect(self):
        if self.options.tab == "rasterizer":
            sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
            for el in sel:
                if self.options.rasterizermode == 1:
                    el.set("autoexporter_rasterize", "png")
                elif self.options.rasterizermode == 2:
                    el.set("autoexporter_rasterize", "jpg")
                else:
                    el.set("autoexporter_rasterize", None)
            return

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

        if dispprofile:
            import cProfile, pstats, io
            from pstats import SortKey

            pr = cProfile.Profile()
            pr.enable()

        formats = [
            self.options.usepdf,
            self.options.usepng,
            self.options.useemf,
            self.options.useeps,
            self.options.usepsvg,
        ]
        formats = [
            ["pdf", "png", "emf", "eps", "psvg"][ii]
            for ii in range(len(formats))
            if formats[ii]
        ]

        # Make an options copy we can pass to the external program
        import copy

        optcopy = copy.copy(self.options)
        delattr(optcopy, "output")
        delattr(optcopy, "input_file")
        # optcopy.reduce_images = (
        #     self.options.imagemode == 1 or self.options.imagemode == 2
        # )
        optcopy.reduce_images = self.options.imagemode2
        # optcopy.tojpg = self.options.imagemode == 2

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

            # Pass settings using a config file. Include the current path so Inkex can be called if needed.
            import pickle

            optcopy.inkscape_bfn = bfn
            optcopy.formats = formats
            optcopy.syspath = sys.path

            try:
                import warnings

                with warnings.catch_warnings():
                    # Ignore ImportWarning for Gtk/Pango
                    warnings.simplefilter("ignore")
                    import gi

                    gi.require_version("Gtk", "3.0")
                    from gi.repository import Gtk  # noqa
                guitype = "gtk"
            except:
                guitype = "terminal"
            if USE_TERMINAL:
                guitype = "terminal"
            optcopy.guitype = guitype

            import tempfile

            aes = os.path.join(
                os.path.abspath(tempfile.gettempdir()), "si_ae_settings.p"
            )
            f = open(aes, "wb")

            # f = open(os.path.join(dh.get_script_path(), "ae_settings.p"), "wb");
            pickle.dump(optcopy, f)
            f.close()
            import warnings

            warnings.simplefilter("ignore", ResourceWarning)
            # prevent warning that process is open

            if guitype == "gtk":
                # dh.idebug([f.name for f in os.scandir(optcopy.watchdir)])
                gtk_call(pybin, aepy, pyloc)
            else:
                terminal_call(pybin, aepy, pyloc)

        else:
            if not (self.options.testmode):
                pth = dh.Get_Current_File(self, "To do a direct export, ")
            else:
                pth = self.options.input_file
            optcopy.original_file = pth
            optcopy.debug = DEBUGGING
            optcopy.prints = False
            DEBUGGING
            optcopy.linked_locations = ih.get_linked_locations(self)
            # needed to find linked images in relative directories

            # dh.ctic()
            AutoExporter().export_all(
                bfn, self.options.input_file, pth, formats, optcopy
            )
            # dh.ctoc()

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())

        if self.options.testmode:
            nf = os.path.abspath(pth[0:-4] + "_plain.svg")
            stream = self.options.output

            if isinstance(stream, str):
                # Copy the new file
                import shutil

                shutil.copyfile(nf, self.options.output)
            else:
                # Write to the output stream
                svg2 = get_svg(nf)
                import lxml

                newdoc = lxml.etree.tostring(svg2, pretty_print=True)
                try:
                    stream.write(newdoc)
                except TypeError:
                    # we hope that this happens only when document needs to be encoded
                    stream.write(newdoc.encode("utf-8"))  # type: ignore
                self.options.output = None

            os.remove(nf)

    def export_all(self, bfn, fin, outtemplate, exp_fmts, opts):
        # Make a temp directory
        # import tempfile
        # tempdir = os.path.realpath(tempfile.mkdtemp(prefix="ae-"));
        tempdir = dh.si_tmp(dirbase="ae")
        if opts.debug:
            if opts.prints:
                opts.prints("\n    " + joinmod(tempdir, ""))
        if hasattr(opts, "aeThread"):
            opts.aeThread.tempdir = tempdir

        tempbase = joinmod(tempdir, "t")
        opts.input_file = fin

        # Make sure output directory exists
        outdir = os.path.dirname(outtemplate)
        if not os.path.exists(outdir):
            os.makedirs(outdir)

        # Add a document margin
        if opts.margin != 0:
            svg = get_svg(fin)
            tmp = tempbase + "_marg.svg"
            self.Add_Margin(svg, opts.margin, opts.testmode)
            dh.overwrite_svg(svg, tmp)
            import copy

            fin = copy.copy(tmp)

        # Do png before any preprocessing
        if "png" in exp_fmts:
            finished, myo = AutoExporter().export_file(
                bfn, fin, outtemplate, "png", None, opts, tempbase
            )

        # Do preprocessing
        if any([fmt in exp_fmts for fmt in ["pdf", "emf", "eps", "psvg"]]):
            ppoutput = self.preprocessing(
                bfn, fin, outtemplate, opts, tempbase
            )
        else:
            ppoutput = None

        # Do vector outputs
        newfiles = []
        for fmt in exp_fmts:
            if fmt != "png":
                finished, myo = AutoExporter().export_file(
                    bfn, fin, outtemplate, fmt, ppoutput, opts, tempbase
                )
            if finished:
                newfiles.append(myo)
            # tempoutputs += tf

        # Remove temporary outputs and directory
        failed_to_delete = None
        if not (opts.debug):
            Delete_Dir(tempdir)
        else:
            import warnings

            warnings.simplefilter("ignore", ResourceWarning)
            # prevent warning that process is open
            subprocess.Popen(f'explorer "{os.path.realpath(tempdir)}"')
            # dh.idebug(tempdir)
        return failed_to_delete

    # Modifications that are done prior to conversion to any vector output
    def preprocessing(self, bfn, fin, fout, opts, tempbase):
        import os, time, copy
        import image_helpers as ih

        if opts.prints:
            fname = os.path.split(opts.input_file)[1]
            try:
                offset = round(os.get_terminal_size().columns / 2)
            except:
                offset = 40
            fname = fname + " " * max(0, offset - len(fname))
            opts.prints(fname + ": Preprocessing vector output", flush=True)
            timestart = time.time()

        tempdir = os.path.split(tempbase)[0]
        temphead = os.path.split(tempbase)[1]

        # SVG modifications that should be done prior to any binary calls
        cfile = fin
        svg = get_svg(cfile)

        # Prune hidden items and remove language switching
        stag = inkex.addNS('switch','svg')
        todelete, todelang = [], []
        for el in dh.visible_descendants(svg):
            if el.cspecified_style.get("display") == "none":
                todelete.append(el)
            if el.get('systemLanguage') is not None:
                lang = inkex.inkscape_system_info.language
                if el.get('systemLanguage')==lang:
                    todelang.append(el)
                    # Remove other languages from switches
                    if el.getparent().tag == stag:
                        todelete.extend([k for k in el.getparent() if k.get('systemLanguage')!=lang])
                else:
                    # Remove non-matching languages
                    todelete.append(el)
        for el in unique(todelete):
            el.delete()
        for el in todelang:
            el.set('systemLanguage',None)

        # Embed linked images into the SVG. This should be done prior to clone unlinking
        # since some images may be cloned
        if opts.exportnow:
            lls = opts.linked_locations
        else:
            lls = ih.get_linked_locations_file(cfile, svg)
        for k in lls:
            el = svg.getElementById(k)
            ih.embed_external_image(el, lls[k])

        vds = dh.visible_descendants(svg)
        raster_ids, image_ids, jpgs = [], [], []
        for el in vds:
            # Unlink any clones for the PDF image and marker fixes
            if isinstance(el, (inkex.Use)) and not (isinstance(el, (inkex.Symbol))):
                newel = dh.unlink2(el)
                myi = vds.index(el)
                vds[myi] = newel
                for dv in newel.descendants2()[1:]:
                    vds.append(dv)

            # Remove trivial groups inside masks/transparent objects or clipped groups
            if isinstance(el, (inkex.Group)):
                ancs = el.ancestors2(includeme=True)
                masked = any(
                    [
                        anc.get_link("mask", svg) is not None
                        or (
                            el.ccascaded_style.get("opacity") is not None
                            and float(el.ccascaded_style.get("opacity")) < 1
                        )
                        for anc in ancs
                    ]
                )
                clipped = any(
                    [anc.get_link("clip-path", svg) is not None for anc in ancs]
                )
                if (
                    len(list(el)) == 1
                    and (masked or clipped)
                    and el.get("autoexporter_rasterize") not in ["png", "jpg", "True"]
                ):
                    dh.ungroup(el)

            # Remove groups inside clips
            cp = el.get_link("clip-path", svg)
            if cp is not None:
                while any([isinstance(v, inkex.Group) for v in list(cp)]):
                    for g in list(cp):
                        if isinstance(g, inkex.Group):
                            dh.ungroup(g)

        stps = []
        for el in vds:
            elid = el.get_id()

            # Fix marker export bug for PDFs
            ms = self.Marker_Fix(el)
            # Convert markers to path for Office
            if len(ms) > 0 and opts.usepsvg:
                stps.append(elid)

            # Fix opacity bug for Office PDF saving
            if len(ms)==0: # works poorly with markers
                self.Opacity_Fix(el)

            # Disable connectors
            el.set("inkscape:connector-type", None)

            # Find out which objects need to be rasterized
            sty = el.cstyle
            # only want the object with the filter
            if sty.get_link("filter", svg) is not None:
                raster_ids.append(elid)  # filtered objects (always rasterized at PDF)
            if (sty.get("fill") is not None and "url" in sty.get("fill")) or (
                sty.get("stroke") is not None and "url" in sty.get("stroke")
            ):
                raster_ids.append(elid)  # gradient objects
            if el.get_link("mask") is not None:
                raster_ids.append(elid)  # masked objects (always rasterized at PDF)
            if el.get("autoexporter_rasterize") in ["png", "jpg", "True"]:
                raster_ids.append(elid)
                # rasterizer-marked
                if el.get("autoexporter_rasterize") == "jpg":
                    jpgs.append(elid)
            if isinstance(el, (inkex.Image)):
                image_ids.append(elid)

            # Remove style attributes with invalid URLs
            # (Office doesn't display the element while Inkscape ignores it)
            for satt in list(sty.keys()):
                if (
                    satt in dh.urlatts
                    and sty.get(satt).startswith("url")
                    and sty.get_link(satt, svg) is None
                ):
                    el.cstyle[satt] = None

            # Prune single-point paths, which Inkscape doesn't show
            if el.tag in otp_support_tags:
                pth = el.cpath
                firstpt = None
                trivial = True
                for pt in pth.end_points:
                    if firstpt is None:
                        firstpt = (pt.x,pt.y)
                    elif (pt.x,pt.y)!=firstpt:
                        trivial = False
                        break
                if trivial:
                    el.delete(deleteup=True)
                        
                        

        # Fix Avenir/Whitney
        tetag = inkex.TextElement.ctag
        frtag = inkex.FlowRoot.ctag
        tels = [el for el in vds if el.tag in {tetag,frtag}]
        from inkex.text import parser

        parser.Character_Fixer2(tels)

        # Strip all sodipodi:role lines from document
        # Conversion to plain SVG does this automatically but poorly
        excludetxtids = []
        opts.duplicatelabels = dict()
        if opts.usepsvg:
            if len(tels) > 0:
                svg.make_char_table()
                opts.ctable = svg.char_table
                # store for later

            nels = []
            for el in reversed(tels):
                if el.parsed_text.isflow:
                    nels += el.parsed_text.Flow_to_Text()
                    tels.remove(el)
            tels += nels

            for el in tels:
                el.parsed_text.Strip_Text_BaselineShift()
                el.parsed_text.Strip_Sodipodirole_Line()
                el.parsed_text.Fuse_Fonts()
                self.SubSuper_Fix(el)

                # Preserve duplicate of text to be converted to paths
                if opts.texttopath and el.get("display") != "none":
                    d = el.duplicate()
                    excludetxtids.append(d.get_id())
                    g = dh.group([d])
                    g.set("display", "none")

                    # te = svg.new_element(inkex.TextElement, svg)
                    te = inkex.TextElement()
                    g.append(te)  # Remember the original ID
                    te.text = "{0}: {1}".format(dup_key, el.get_id())
                    te.set("display", "none")
                    excludetxtids.append(te.get_id())
                    opts.duplicatelabels[te.get_id()] = el.get_id()

                    # Make sure nested tspans have fill specified (STP bug)
                    for d in el.descendants2()[1:]:
                        if (
                            "fill" in d.cspecified_style
                            and d.cspecified_style["fill"] != "#000000"
                        ):
                            d.cstyle["fill"] = d.cspecified_style["fill"]

        tmp = tempbase + "_mod.svg"
        dh.overwrite_svg(svg, tmp)
        cfile = tmp
        opts.excludetxtids = excludetxtids

        do_rasterizations = len(raster_ids + image_ids) > 0
        do_stroketopaths = (
            opts.texttopath or opts.stroketopath or len(stps) > 0
        )

        allacts = []
        if do_stroketopaths:
            svg = get_svg(cfile)
            vd = dh.visible_descendants(svg)

            updatefile = False
            tels = []
            if opts.texttopath:
                for el in vd:
                    if el.tag==tetag and el.get_id() not in excludetxtids:
                        tels.append(el.get_id())
                        for d in el.descendants2():
                            # Fuse fill and stroke to account for STP bugs
                            if "fill" in d.cspecified_style:
                                d.cstyle["fill"] = d.cspecified_style["fill"]
                                updatefile = True
                            if "stroke" in d.cspecified_style:
                                d.cstyle["stroke"] = d.cspecified_style["stroke"]
                                updatefile = True

            pels, dgroups = [], []
            if opts.stroketopath or len(stps) > 0:
                # Stroke to Path has a number of bugs, try to fix them
                if opts.stroketopath:
                    stpels = vd
                elif len(stps) > 0:
                    stpels = [el for el in vd if el.get_id() in stps]
                stpels = [el for el in stpels if el.get_id() not in raster_ids]
                pels, dgroups = self.Stroke_to_Path_Fixes(stpels)
                updatefile = True

            if updatefile:
                dh.overwrite_svg(svg, cfile)

            celsj = ",".join(tels + pels)
            tmpstp = tempbase + "_stp.svg"

            if (
                (opts.stroketopath or len(stps) > 0)
                and inkex.installed_ivp[0] >= 1
                and inkex.installed_ivp[1] > 0
            ):
                act = "object-stroke-to-path"
            else:
                act = "object-to-path"

            allacts += [
                "select:{0}; {1}; export-filename:{2}; export-do;".format(
                    celsj, act, tmpstp
                )
            ]

        # Rasterizations
        if do_rasterizations:
            svg = get_svg(cfile)

            vds = dh.visible_descendants(svg)
            els = [el for el in vds if el.get_id() in list(set(raster_ids + image_ids))]
            if len(els) > 0:
                imgtype = "png"
                acts, acts2, imgs_trnp, imgs_opqe = [], [], [], []
                for el in els:
                    elid = el.get_id()
                    tmpimg = temphead + "_im_" + elid + "." + imgtype
                    imgs_trnp.append(tmpimg)
                    tmpimg2 = temphead + "_imbg_" + elid + "." + imgtype
                    imgs_opqe.append(tmpimg2)
                    mydpi = opts.dpi

                    # export item only
                    fmt1 = (
                        "export-id:{0}; export-id-only; export-dpi:{1}; "
                        "export-filename:{2}; export-background-opacity:0.0; export-do; "
                    )
                    acts.append(fmt1.format(el.get_id(), int(mydpi), tmpimg))
                    # export all w/background
                    fmt2 = (
                        "export-id:{0}; export-dpi:{1}; "
                        "export-filename:{2}; export-background-opacity:1.0; export-do; "
                    )
                    acts2.append(fmt2.format(el.get_id(), int(mydpi), tmpimg2))

                if ih.hasPIL:
                    acts = acts2 + acts  # export-id-onlys need to go last
                allacts += acts

        # To reduce the number of binary calls, we collect the stroke-to-path and rasterization
        # actions into a single call that also gets the Bounding Boxes
        # Skip binary call during testing
        if len(allacts) > 0 and not opts.testmode:
            def Split_Select(fn, inkbin, acts, selii, reserved):
                '''
                Windows cannot handle arguments that are too long. If this happens,
                split the actions in half and run on each
                '''
                import math, shutil

                act = acts[selii]

                m1 = re.search(
                    r"export-filename:(.+?); export-background-opacity:", act
                )
                m2 = re.search(r"export-filename:(.+?); export-do;", act)
                if m1:
                    actfn = m1.group(1)
                elif m2:
                    actfn = m2.group(1)
                else:
                    actfn = None

                match = re.search(r"select:(.*?); object-stroke-to-path", act)
                selects = match.group(1).split(",")
                after = re.search(r"; object-stroke-to-path(.*)", act).group(1)
                mp = math.ceil(len(selects) / 2)

                reserved.update({fn, actfn})
                isreserved = True
                cnt = 0
                while isreserved:
                    actfna = actfn.strip(".svg") + str(cnt) + ".svg"
                    isreserved = actfna in reserved
                    cnt += 1
                reserved.update({actfna})

                if len(selects) == 1:
                    # cannot split, fact that we failed means there is a STP crash
                    # dh.idebug('failed: '+str(selects))
                    shutil.copy(fn, actfn)
                    return Split_Acts(
                        fn=fn,
                        inkbin=inkbin,
                        acts=acts[:selii] + acts[selii + 1 :],
                        reserved=reserved,
                    )
                else:
                    act1 = (
                        "select:"
                        + ",".join(selects[:mp])
                        + "; object-stroke-to-path"
                        + after
                    )
                    act1 = act1.replace(actfn, actfna)
                    act2 = (
                        "select:"
                        + ",".join(selects[mp:])
                        + "; object-stroke-to-path"
                        + after
                    )

                    acts1 = (
                        acts[:selii] + [act1] if len(selects[:mp]) > 0 else acts[:selii]
                    )
                    acts2 = (
                        [act2] + acts[selii + 1 :]
                        if len(selects[mp:]) > 0
                        else acts[selii + 1 :]
                    )

                    bbs = Split_Acts(
                        fn=fn, inkbin=inkbin, acts=acts1, reserved=reserved
                    )
                    bbs = Split_Acts(
                        fn=actfna, inkbin=inkbin, acts=acts2, reserved=reserved
                    )
                    return bbs

            def Split_Acts(fn, inkbin, acts, reserved=set()):
                import math

                try:
                    eargs = ["--actions", "".join(acts)]
                    bbs = dh.Get_Bounding_Boxes(
                        filename=fn, inkscape_binary=inkbin, extra_args=eargs
                    )
                    for ii, act in enumerate(acts):
                        if "export-filename" and "export-do" in act:
                            m1 = re.search(
                                r"export-filename:(.+?); export-background-opacity:",
                                act,
                            )
                            m2 = re.search(r"export-filename:(.+?); export-do;", act)
                            if m1:
                                actfn = m1.group(1)
                            elif m2:
                                actfn = m2.group(1)
                            else:
                                actfn = None
                            if actfn is not None and not os.path.exists(actfn):
                                if "select" in act and "object-stroke-to-path" in act:
                                    return Split_Select(
                                        fn, inkbin, acts, ii, reserved=reserved
                                    )
                except FileNotFoundError:
                    if len(acts) == 1:
                        if "select" in acts[0] and "object-stroke-to-path" in acts[0]:
                            return Split_Select(fn, inkbin, acts, 0, reserved=reserved)
                        else:
                            inkex.utils.errormsg("Argument too long and cannot split")
                            quit()
                    else:
                        acts1 = acts[: math.ceil(len(acts) / 2)]
                        acts2 = acts[math.ceil(len(acts) / 2) :]
                    bbs = Split_Acts(
                        fn=fn, inkbin=inkbin, acts=acts1, reserved=reserved
                    )
                    bbs = Split_Acts(
                        fn=fn, inkbin=inkbin, acts=acts2, reserved=reserved
                    )
                return bbs

            oldwd = os.getcwd()
            os.chdir(tempdir)
            # use relative paths to reduce arg length

            bbs = Split_Acts(fn=cfile, inkbin=bfn, acts=allacts)
            try:
                os.chdir(oldwd)
                # return to original dir so no problems in calling function
            except FileNotFoundError:
                pass  # occasionally directory no longer exists (deleted by tempfile?)
            if do_stroketopaths:
                cfile = tmpstp

        if do_rasterizations:
            svg = get_svg(cfile)
            vds = dh.visible_descendants(svg)
            els = [el for el in vds if el.get_id() in list(set(raster_ids + image_ids))]
            if len(els) > 0:
                imgs_trnp = [os.path.join(tempdir, t) for t in imgs_trnp]
                imgs_opqe = [os.path.join(tempdir, t) for t in imgs_opqe]

                for ii, el in enumerate(els):
                    tmpimg = imgs_trnp[ii]
                    tmpimg2 = imgs_opqe[ii]

                    if os.path.exists(tmpimg):
                        anyalpha0 = False
                        if ih.hasPIL:
                            bbox = ih.crop_images([tmpimg, tmpimg2])
                            anyalpha0 = ih.Set_Alpha0_RGB(tmpimg, tmpimg2)
                            if el.get_id() in jpgs:
                                tmpjpg = tmpimg.replace(".png", ".jpg")
                                ih.to_jpeg(tmpimg2, tmpjpg)
                                tmpimg = copy.copy(tmpjpg)
                        else:
                            bbox = None

                        # Compare size of old and new images
                        osz = ih.embedded_size(el)
                        if osz is None:
                            osz = float("inf")
                        nsz = os.path.getsize(tmpimg)
                        hasmaskclip = (
                            el.get_link("mask") is not None
                            or el.get_link("clip-path") is not None
                        )  # clipping and masking
                        embedimg = (nsz < osz) or (anyalpha0 or hasmaskclip)
                        if embedimg:
                            self.Replace_with_Raster(el, tmpimg, bbs[el.get_id()], bbox)

                tmp = tempbase + "_eimg.svg"
                dh.overwrite_svg(svg, tmp)
                cfile = tmp

        if do_stroketopaths:
            svg = get_svg(cfile)
            # Remove temporary groups
            if opts.stroketopath:
                for elid in dgroups:
                    el = svg.getElementById(elid)
                    if el is not None:
                        dh.ungroup(el)

            tmp = tempbase + '_poststp.svg'
            dh.overwrite_svg(svg, tmp)
            cfile = tmp

        if opts.prints:
            opts.prints(
                fname
                + ": Preprocessing done ("
                + str(round(1000 * (time.time() - timestart)) / 1000)
                + " s)"
            )
        return cfile

    # Use the Inkscape binary to export the file
    def export_file(self, bfn, fin, fout, fformat, ppoutput, opts, tempbase):
        import os, time, copy

        # original_file = fin;
        myoutput = fout[0:-4] + "." + fformat
        if opts.prints:
            fname = os.path.split(opts.input_file)[1]
            try:
                offset = round(os.get_terminal_size().columns / 2)
            except:
                offset = 40
            fname = fname + " " * max(0, offset - len(fname))
            opts.prints(fname + ": Converting to " + fformat, flush=True)
        timestart = time.time()

        if ppoutput is not None:
            fin = ppoutput
        # else:
        #     tmpoutputs = []
        # tempdir = None

        # try:
        ispsvg = fformat == "psvg"
        notpng = not (fformat == "png")

        if opts.thinline and notpng:
            svg = get_svg(fin)
            if fformat in ["pdf", "eps", "psvg"]:
                self.Thinline_Dehancement(svg, "bezier")
            else:
                self.Thinline_Dehancement(svg, "split")
            tmp = tempbase + "_tld" + fformat[0] + ".svg"
            dh.overwrite_svg(svg, tmp)
            fin = copy.copy(tmp)

        if fformat == "psvg":
            myoutput = myoutput.replace(".psvg", "_plain.svg")

        def overwrite_output(filein, fileout):
            if os.path.exists(fileout):
                os.remove(fileout)
            args = [
                bfn,
                "--export-background",
                "#ffffff",
                "--export-background-opacity",
                "1.0",
                "--export-dpi",
                str(opts.dpi),
                "--export-filename",
                fileout,
                filein,
            ]
            if fileout.endswith(".pdf") and opts.latexpdf:
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
            subprocess_check(args, opts)

        def make_output(filein, fileout):
            if fileout.endswith(".svg"):
                if not (opts.testmode):
                    overwrite_output(filein, fileout)
                else:
                    import shutil

                    shutil.copy(filein, fileout)  # skip conversion
                opts.made_outputs = [fileout]

                osvg = get_svg(filein)
                # original has pages
                # if hasattr(opts,'ctable'):
                #     osvg._char_table = opts.ctable

                pgs = osvg.cdocsize.pgs
                haspgs = osvg.cdocsize.inkscapehaspgs
                if (haspgs or opts.testmode) and len(pgs) > 0:
                    bbs = dh.BB2(type("DummyClass", (), {"svg": osvg}))
                    dl = opts.duplicatelabels
                    outputs = []
                    pgiis = (
                        range(len(pgs))
                        if not (opts.testmode)
                        else [opts.testpage - 1]
                    )
                    for ii in pgiis:
                        # match the viewbox to each page and delete them
                        psvg = get_svg(fileout)
                        # plain SVG has no pages
                        pgs2 = psvg.cdocsize.pgs

                        self.Change_Viewbox_To_Page(psvg, pgs[ii])
                        # Only need to delete other Pages in testmode since plain SVGs have none
                        if opts.testmode:
                            for jj in reversed(range(len(pgs2))):
                                pgs2[jj].delete()

                        # Delete content not on current page
                        pgbb = dh.bbox(psvg.cdocsize.effvb)
                        for k, v in bbs.items():
                            removeme = not (dh.bbox(v).intersect(pgbb))
                            if k in dl:
                                if (
                                    dl[k] in bbs
                                ):  # remove duplicate label if removing original
                                    removeme = not (dh.bbox(bbs[dl[k]]).intersect(pgbb))
                                else:
                                    removeme = True
                            if removeme:
                                el = psvg.getElementById(k)
                                if el is not None:
                                    el.delete()

                        pname = pgs[ii].get('inkscape:label')
                        pname = str(ii + 1) if pname is None else pname
                        addendum = (
                            "_page_" + pname
                            if not (opts.testmode or len(pgs) == 1)
                            else ""
                        )
                        outparts = fileout.split(".")
                        pgout = ".".join(outparts[:-1]) + addendum + "." + outparts[-1]
                        dh.overwrite_svg(psvg, pgout)
                        outputs.append(pgout)
                    opts.made_outputs = outputs
            else:
                svg = get_svg(filein)
                pgs = svg.cdocsize.pgs

                haspgs = svg.cdocsize.inkscapehaspgs
                if (haspgs or opts.testmode) and len(pgs) > 1:
                    outputs = []
                    pgiis = (
                        range(len(pgs))
                        if not (opts.testmode)
                        else [opts.testpage - 1]
                    )
                    for ii in pgiis:
                        # match the viewbox to each page and delete them
                        svgpg = get_svg(filein)
                        pgs2 = svgpg.cdocsize.pgs
                        self.Change_Viewbox_To_Page(svgpg, pgs[ii])
                        for jj in reversed(range(len(pgs2))):
                            pgs2[jj].delete()

                        pname = pgs[ii].get('inkscape:label')
                        pname = str(ii + 1) if pname is None else pname
                        addendum = (
                            "_page_" + pname if not (opts.testmode) else ""
                        )
                        svgpgfn = tempbase + addendum + ".svg"
                        dh.overwrite_svg(svgpg, svgpgfn)

                        outparts = fileout.split(".")
                        pgout = ".".join(outparts[:-1]) + addendum + "." + outparts[-1]
                        overwrite_output(svgpgfn, pgout)
                        outputs.append(pgout)
                    opts.made_outputs = outputs
                else:
                    overwrite_output(filein, fileout)
                    opts.made_outputs = [fileout]

        if not (ispsvg):
            make_output(fin, myoutput)
            finalnames = opts.made_outputs
        else:
            tmp = tempbase + "_tmp_small.svg"
            make_output(fin, tmp)

            moutputs = opts.made_outputs
            finalnames = []
            for ii, mout in enumerate(moutputs):
                svg = get_svg(mout)
                self.postprocessing(svg, opts)
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
                except:
                    pass

        if opts.prints:
            toc = time.time() - timestart
            opts.prints(
                fname
                + ": Conversion to "
                + fformat
                + " done ("
                + str(round(1000 * toc) / 1000)
                + " s)"
            )
        return True, myoutput

    def postprocessing(self, svg, opts):
        # Postprocessing of SVGs, mainly for overcoming bugs in Office products
        vds = dh.visible_descendants(svg)
        
        # Shift viewbox corner to (0,0) by translating top-level elements
        evb = svg.cdocsize.effvb
        if not(evb[0]==0 and evb[1]==0):
            newtr = Transform("translate(" + str(-evb[0]) + ", " + str(-evb[1]) + ")")
            svg.set_viewbox([0,0,evb[2],evb[3]])
            ndefs = [el for el in list(svg) if not (el.tag in dh.unungroupable)]
            for el in ndefs:
                el.ctransform = newtr @ el.ctransform
        
        for d in vds:
            if (
                isinstance(d, (TextElement))
                and d.get_id() not in opts.excludetxtids
            ):
                scaleto = 100 if not opts.testmode else 10
                # Make 10 px in test mode so that errors are not unnecessarily large
                self.Scale_Text(d, scaleto)
            elif isinstance(d, (inkex.Image)):
                if ih.hasPIL:
                    self.Merge_Mask(d)
                # while d.getparent()!=d.croot and d.getparent() is not None and d.croot is not None:
                #     # iteratively remove groups containing images
                #     # I don't think it's necessary?
                #     dh.ungroup(d.getparent());
            elif isinstance(d, (inkex.Group)):
                if len(d) == 0:
                    d.delete(deleteup=True)

        if opts.thinline:
            for d in vds:
                self.Bezier_to_Split(d)
        # dh.idebug(opts.svgtopdf_vbs)
        # embed_original = False
        # if embed_original:
        #     def main_contents(svg):
        #         ret = list(svg)
        #         for k in reversed(ret):
        #             if k.tag in [inkex.addNS('metadata','svg'),
        #                           inkex.addNS('namedview','sodipodi')]:
        #                 ret.remove(k);
        #         return ret

        #     g  = dh.group(main_contents(svg))
        #     svgo = get_svg(original_file)
        #     go = dh.group(main_contents(svgo))
        #     svg.append(go)
        #     go.set('style','display:none');
        #     go.set('inkscape:label','SI original');
        #     go.set('inkscape:groupmode','layer');

        #     # Conversion to PDF changes the viewbox to pixels. Convert back to the
        #     # original viewbox by applying a transform
        #     ds = opts.svgtopdf_dss[ii]
        #     tfmt = 'matrix({0},{1},{2},{3},{4},{5})';
        #     T =inkex.Transform(tfmt.format(ds.uuw,0,0,ds.uuh,
        #                                       -ds.effvb[0]*ds.uuw,
        #                                       -ds.effvb[1]*ds.uuh))
        #     g.set('transform',str(-T))
        #     svg.set_viewbox(ds.effvb)

        te = None
        for el in list(svg):
            if (
                isinstance(el, (inkex.TextElement,))
                and el.text is not None
                and orig_key in el.text
            ):
                te = el
        if te is None:
            # te = svg.new_element(inkex.TextElement, svg)
            te = inkex.TextElement()
            svg.append(te)
        te.text = orig_key + ": {0}, hash: {1}".format(
            opts.original_file, hash_file(opts.original_file)
        )
        te.set("style", "display:none")
        dh.clean_up_document(svg)  # Clean up

    def Thinline_Dehancement(self, svg, mode="split"):
        # Prevents thin-line enhancement in certain bad PDF renderers
        # 'bezier' mode converts h,v,l path commands to trivial Beziers
        # 'split' mode splits h,v,l path commands into two path commands
        # The Office PDF renderer removes trivial Beziers, as does conversion to EMF
        # The Inkscape PDF renderer removes split commands
        # In general I prefer split, so I do this for everything other than PDF
        for el in svg.descendants2():
            if el.tag in otp_support_tags and not (isinstance(el, (PathElement))):
                el.object_to_path()
            d = el.get("d")
            if d is not None and any(
                [cv in d for cv in ["h", "v", "l", "H", "V", "L"]]
            ):
                if any([cv in d for cv in ["H", "V", "L"]]):
                    d = str(inkex.Path(d).to_relative())
                ds = d.replace(",", " ").split(" ")
                ds = [v for v in ds if v != ""]
                nexth = False
                nextv = False
                nextl = False
                ii = 0
                while ii < len(ds):
                    if ds[ii] == "v":
                        nextv = True
                        nexth = False
                        nextl = False
                        ds[ii] = ""
                    elif ds[ii] == "h":
                        nexth = True
                        nextv = False
                        nextl = False
                        ds[ii] = ""
                    elif ds[ii] == "l":
                        nextl = True
                        nextv = False
                        nexth = False
                        ds[ii] = ""
                    elif ds[ii] in PTH_COMMANDS:
                        nextv = False
                        nexth = False
                        nextl = False
                    else:
                        if nexth:
                            if mode == "split":
                                hval = float(ds[ii])
                                ds[ii] = "h " + str(hval / 2) + " " + str(hval / 2)
                            else:
                                ds[ii] = "c " + " ".join([ds[ii] + ",0"] * 3)
                        elif nextv:
                            if mode == "split":
                                vval = float(ds[ii])
                                ds[ii] = "v " + str(vval / 2) + " " + str(vval / 2)
                            else:
                                ds[ii] = "c " + " ".join(["0," + ds[ii]] * 3)
                        elif nextl:
                            if mode == "split":
                                lx = float(ds[ii])
                                ly = float(ds[ii + 1])
                                ds[ii] = (
                                    "l "
                                    + str(lx / 2)
                                    + ","
                                    + str(ly / 2)
                                    + " "
                                    + str(lx / 2)
                                    + ","
                                    + str(ly / 2)
                                )
                            else:
                                ds[ii] = "c " + " ".join(
                                    [ds[ii] + "," + ds[ii + 1]] * 3
                                )
                            ds[ii + 1] = ""
                            ii += 1
                    ii += 1
                newd = " ".join([v for v in ds if v != ""])
                newd = newd.replace("  ", " ")
                el.set("d", newd)

    def Bezier_to_Split(self, el):
        # Converts the Bezier TLD to split (for the plain SVG)
        if el.tag in otp_support_tags and not (isinstance(el, (PathElement))):
            el.object_to_path()
        d = el.get("d")
        if d is not None and any([cv in d for cv in ["c", "C"]]):
            if any([cv in d for cv in ["C"]]):
                d = str(inkex.Path(d).to_relative())
            ds = d.replace(",", " ").split(" ")
            ds = [v for v in ds if v != ""]
            nextc = False
            ii = 0
            while ii < len(ds):
                if ds[ii] == "c":
                    nextc = True
                    ds[ii] = ""
                elif ds[ii] in PTH_COMMANDS:
                    nextc = False
                else:
                    if nextc:
                        cvs = ds[ii : ii + 6]
                        if cvs[0] == cvs[2] == cvs[4] and cvs[1] == cvs[3] == cvs[5]:
                            lx = float(cvs[0])
                            ly = float(cvs[1])
                            ds[ii] = (
                                "l "
                                + str(lx / 2)
                                + ","
                                + str(ly / 2)
                                + " l "
                                + str(lx / 2)
                                + ","
                                + str(ly / 2)
                            )
                        else:
                            ds[ii] = (
                                "c "
                                + cvs[0]
                                + ","
                                + cvs[1]
                                + " "
                                + cvs[2]
                                + ","
                                + cvs[3]
                                + " "
                                + cvs[4]
                                + ","
                                + cvs[5]
                            )
                        ds[ii + 1 : ii + 6] = [""] * 5
                        ii += 5
                ii += 1
            newd = " ".join([v for v in ds if v != ""])
            newd = newd.replace("  ", " ")
            el.set("d", newd)

    def Marker_Fix(self, el):
        # Fixes the marker bug that occurs with context-stroke and context-fill
        mkrs = self.get_markers(el)
        sty = el.cspecified_style
        for m, mkrel in mkrs.items():
            dh.get_strokefill(el)
            mkrds = mkrel.descendants2()
            anycontext = any(
                [
                    (a == "stroke" or a == "fill") and "context" in v
                    for d in mkrds
                    for a, v in d.cspecified_style.items()
                ]
            )
            if anycontext:
                handled = True
                dup = mkrel.duplicate()
                dupds = dup.descendants2()
                for d in dupds:
                    dsty = d.cspecified_style
                    for a, v in dsty.items():
                        if (a == "stroke" or a == "fill") and "context" in v:
                            if v == "context-stroke":
                                d.cstyle[a] = sty.get("stroke", "none")
                            elif v == "context-fill":
                                d.cstyle[a] = sty.get("fill", "none")
                            else:  # I don't know what this is
                                handled = False
                if handled:
                    el.cstyle[m] = dup.get_id(as_url=2)
        return mkrs

    def Opacity_Fix(self, el):
        # Fuse opacity onto fill and stroke for path-like elements
        # Helps prevent rasterization-at-PDF for Office products
        sty = el.cspecified_style
        if sty.get("opacity") is not None and float(sty.get("opacity", 1.0)) != 1.0 and el.tag in otp_support_tags:
            sf = dh.get_strokefill(el)  # fuses opacity and stroke-opacity/fill-opacity
            if sf.stroke is not None and sf.fill is None:
                el.cstyle["stroke-opacity"] = sf.stroke.alpha
                el.cstyle["opacity"] = 1
            elif sf.fill is not None and sf.stroke is None:
                el.cstyle["fill-opacity"] = sf.fill.alpha
                el.cstyle["opacity"] = 1

    # Replace super and sub with numerical values
    # Collapse Tspans with 0% baseline-shift, which Office displays incorrectly
    def SubSuper_Fix(self, el):
        for d in el.descendants2():
            bs = d.ccascaded_style.get("baseline-shift")
            if bs in ["super", "sub"]:
                sty = d.ccascaded_style
                sty["baseline-shift"] = "40%" if bs == "super" else "-20%"
                d.cstyle = sty

        for d in reversed(el.descendants2()):  # all Tspans
            bs = d.ccascaded_style.get("baseline-shift")
            if bs is not None and bs.replace(" ", "") == "0%":
                # see if any ancestors with non-zero shift
                anysubsuper = False
                for a in d.ancestors2(stopafter=el):
                    bsa = a.ccascaded_style.get("baseline-shift")
                    if bsa is not None and "%" in bsa:
                        anysubsuper = float(bsa.replace(" ", "").strip("%")) != 0

                # split parent
                myp = d.getparent()
                if anysubsuper and myp is not None:
                    from inkex.text import parser

                    ds = parser.split_text(myp)
                    for d in reversed(ds):
                        if (
                            len(list(d)) == 1
                            and list(d)[0].ccascaded_style.get("baseline-shift") == "0%"
                        ):
                            s = list(d)[0]
                            mys = s.ccascaded_style
                            if mys.get("baseline-shift") == "0%":
                                mys["baseline-shift"] = d.ccascaded_style.get(
                                    "baseline-shift"
                                )
                            fs, sf = dh.composed_width(s, "font-size")
                            mys["font-size"] = str(fs / sf)
                            d.addprevious(s)
                            s.cstyle = mys
                            s.tail = d.tail
                            d.delete()
                            self.SubSuper_Fix(el)  # parent is now gone, so start over
                            return

    def Scale_Text(self, el, scaleto):
        # Sets all font-sizes to 100 px by moving size into transform
        # Office rounds every fonts to the nearest px and then transforms it,
        # so this makes text sizes more accurate
        from inkex.text import parser

        svg = el.croot
        szs = []
        for d in el.descendants2():  # all Tspan sizes
            fs = d.ccascaded_style.get("font-size")
            fs = {"small": "10px", "medium": "12px", "large": "14px"}.get(fs, fs)
            if fs is not None and "%" not in fs:
                szs.append(dh.ipx(fs))
        if len(szs) == 0:
            maxsz = default_style_atts["font-size"]
            maxsz = {"small": 10, "medium": 12, "large": 14}.get(maxsz, maxsz)
        else:
            maxsz = max(szs)

        s = 1 / maxsz * scaleto

        # Make a dummy group so we can properly compose the transform
        g = dh.group([el], moveTCM=True)

        for d in reversed(el.descendants2()):
            xv = parser.ParsedText.GetXY(d, "x")
            yv = parser.ParsedText.GetXY(d, "y")
            dxv = parser.ParsedText.GetXY(d, "dx")
            dyv = parser.ParsedText.GetXY(d, "dy")

            if xv[0] is not None:
                parser.xyset(d, "x", [v * s for v in xv])
            if yv[0] is not None:
                parser.xyset(d, "y", [v * s for v in yv])
            if dxv[0] is not None:
                parser.xyset(d, "dx", [v * s for v in dxv])
            if dyv[0] is not None:
                parser.xyset(d, "dy", [v * s for v in dyv])

            fs, sf = dh.composed_width(d, "font-size")
            d.cstyle["font-size"] = "{:.3f}".format(fs / sf * s)

            otherpx = [
                "letter-spacing",
                "inline-size",
                "stroke-width",
                "stroke-dasharray",
            ]
            for oth in otherpx:
                othv = d.ccascaded_style.get(oth)
                if (
                    othv is None
                    and oth == "stroke-width"
                    and "stroke" in d.ccascaded_style
                ):
                    othv = default_style_atts[oth]
                if othv is not None:
                    if "," not in othv:
                        d.cstyle[oth] = str((dh.ipx(othv) or 0) * s)
                    else:
                        d.cstyle[oth] = ",".join(
                            [str((dh.ipx(v) or 0) * s) for v in othv.split(",")]
                        )

            shape = d.ccascaded_style.get_link("shape-inside", svg)
            if shape is not None:
                dup = shape.duplicate()
                svg.cdefs.append(dup)
                dup.ctransform = inkex.Transform((s, 0, 0, s, 0, 0)) @ dup.ctransform
                d.cstyle["shape-inside"] = dup.get_id(as_url=2)

        el.ctransform = inkex.Transform((1 / s, 0, 0, 1 / s, 0, 0))
        dh.ungroup(g)

        # compose_all(el, clipurl, maskurl, transform, style)

    def Merge_Mask(self, el):
        # Office will poorly rasterize masked elements at PDF-time
        # Revert alpha masks made by PDFication back to alpha
        mymask = el.get_link("mask")
        if mymask is not None and len(list(mymask)) == 1:
            # only if one object in mask
            mask = list(mymask)[0]
            if isinstance(mask, inkex.Image):
                if mask.get("height") == "1" and mask.get("width") == "1":
                    im1 = ih.str_to_ImagePIL(el.get("xlink:href")).convert("RGBA")
                    im2 = ih.str_to_ImagePIL(mask.get("xlink:href")).convert("RGBA")
                    # only if mask the same size
                    if im1.size == im2.size:
                        import numpy as np

                        d1 = np.asarray(im1)
                        d2 = np.asarray(im2)
                        # only if image is opaque
                        if np.where(d1[:, :, 3] == 255, True, False).all():
                            nd = np.stack(
                                (d1[:, :, 0], d1[:, :, 1], d1[:, :, 2], d2[:, :, 0]), 2
                            )
                            from PIL import Image as ImagePIL

                            newstr = ih.ImagePIL_to_str(ImagePIL.fromarray(nd))
                            el.set("xlink:href", newstr)
                            mask.delete()
                            el.set("mask", None)

    def Replace_with_Raster(self, el, imgloc, bb, imgbbox):
        svg = el.croot
        if svg is None:  # in case we were already rasterized within ancestor
            return
        ih.embed_external_image(el, imgloc)

        # The exported image has a different size and shape than the original
        # Correct by putting transform/clip/mask on a new parent group, then fix location, then ungroup
        g = dh.group([el], moveTCM=True)
        g.set("clip-path", None)
        # conversion to bitmap already includes clips
        g.set("mask", None)  # conversion to bitmap already includes masks

        # Calculate what transform is needed to preserve the image's location
        ct = el.ccomposed_transform
        # bb = bbs[el.get_id()]
        pbb = [
            Vector2d(bb[0], bb[1]),
            Vector2d(bb[0] + bb[2], bb[1]),
            Vector2d(bb[0] + bb[2], bb[1] + bb[3]),
            Vector2d(bb[0], bb[1] + bb[3]),
        ]
        # top-left,tr,br,bl
        put = [
            (-ct).apply_to_point(p) for p in pbb
        ]  # untransformed bbox (where the image needs to go)

        # newel = el.croot.new_element(inkex.Image, el);
        newel = inkex.Image()
        dh.replace_element(el, newel)
        newel.set("x", 0)
        myx = 0
        newel.set("y", 0)
        myy = 0
        newel.set("width", 1)
        myw = dh.ipx(newel.get("width"))
        newel.set("height", 1)
        myh = dh.ipx(newel.get("height"))
        newel.set("xlink:href", el.get("xlink:href"))

        sty = ""
        ir = el.cstyle.get("image-rendering")
        if ir is not None:
            sty = "image-rendering:" + ir
        el = newel

        pgo = [
            Vector2d(myx, myy),
            Vector2d(myx + myw, myy),
            Vector2d(myx + myw, myy + myh),
            Vector2d(myx, myy + myh),
        ]  # where the image is
        el.set("preserveAspectRatio", "none")  # prevents aspect ratio snapping
        el.set("style", sty)  # override existing styles

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
        el.set("transform", T)

        # If we cropped, need to modify location according to bbox
        if ih.hasPIL and imgbbox is not None:
            el.set("x", str(myx + imgbbox[0] * myw))
            el.set("y", str(myy + imgbbox[1] * myh))
            el.set("width", str((imgbbox[2] - imgbbox[0]) * myw))
            el.set("height", str((imgbbox[3] - imgbbox[1]) * myh))
        dh.ungroup(g)

    def Add_Margin(self, svg, amt_mm, testmode):
        m = inkex.units.convert_unit(str(amt_mm) + "mm", "px")
        uuw, uuh = svg.cdocsize.uuw, svg.cdocsize.uuh
        # pgs = self.Get_Pages(svg)

        haspgs = svg.cdocsize.inkscapehaspgs or testmode
        if haspgs and len(svg.cdocsize.pgs) > 0:
            # Has Pages
            for pg in svg.cdocsize.pgs:
                newbbuu = svg.cdocsize.pxtouupgs(
                    [
                        pg.bbpx[0] - m,
                        pg.bbpx[1] - m,
                        pg.bbpx[2] + 2 * m,
                        pg.bbpx[3] + 2 * m,
                    ]
                )
                pg.set("x", str(newbbuu[0]))
                pg.set("y", str(newbbuu[1]))
                pg.set("width", str(newbbuu[2]))
                pg.set("height", str(newbbuu[3]))
            svg.cdocsize = None

        else:
            # If an old version of Inkscape or has no Pages, defined by viewbox
            vb = svg.cdocsize.effvb
            nvb = [
                vb[0] - m / uuw,
                vb[1] - m / uuh,
                vb[2] + 2 * m / uuw,
                vb[3] + 2 * m / uuh,
            ]
            svg.set_viewbox(nvb)

    def Change_Viewbox_To_Page(self, svg, pg):
        newvb = pg.croot.cdocsize.pxtouu(pg.bbpx)
        svg.set_viewbox(newvb)

    def get_markers(self,el):
        ''' Returns valid marker keys and corresponding elements '''
        md = dict()
        for m in ['marker',"marker-start", "marker-mid", "marker-end"]:
            mv = el.cstyle.get_link(m, el.croot)
            if mv is not None:
                md[m] = mv
        return md

    def Stroke_to_Path_Fixes(self, els):
        # Stroke to Path has tons of bugs. Try to preempt them.
        # 1. STP does not properly handle clips, so move clips and
        #    masks to a temp parent group.
        # 2. Densely-spaced nodes can be converted incorrectly, so scale paths up
        #    to be size 1000 and position corner at (0,0)
        # 3. Starting markers can be flipped.
        # 4. Markers on groups cause crashes
        # 5. Markers are given the wrong size
        dummy_groups = []
        path_els = []
        if len(els) > 0:
            svg = els[0].croot
        for el in els:
            ms = self.get_markers(el)
            if isinstance(el, inkex.Group) and len(ms)>0:
                dh.ungroup(el)
            elif el.tag in otp_support_tags:
                sty = el.cspecified_style
                if "stroke" in sty and sty["stroke"] != "none":
                    sw = sty.get("stroke-width")
                    if dh.ipx(sw) == 0:
                        # Fix bug on zero-stroke paths
                        sty["stroke"] = "none"
                        el.cstyle = sty
                    else:
                        # Clip and mask issues solved by moving to a dummy parent group
                        gp = dh.group([el], moveTCM=True)
                        # Do it again so we can add transform later without messing up clip
                        g = dh.group([el], moveTCM=True)
                        
                        path_els.append(el.get_id())
                        dummy_groups.extend([gp.get_id(),g.get_id()])

                        # Scale up most paths to be size 1000 and position corner at (0,0)
                        if inkex.addNS('type','sodipodi') not in el.attrib:
                            # Object to path doesn't currently support Inkscape-specific objects
                            el.object_to_path()
                            bb = el.bounding_box2(dotransform=False, includestroke=False, roughpath=False)
                            if len(ms)==0:
                                # SCALEBY = 1000
                                maxsz = max(bb.w,bb.h)
                                SCALEBY = 1000 / maxsz if maxsz>0 else 1000
                            else:
                                # For paths with markers, scale to make stroke-width=1
                                # Prevents incorrect marker size
                                # https://gitlab.com/inkscape/inbox/-/issues/10506#note_1931910230
                                SCALEBY = 1/dh.ipx(sw)
                            
                            tr = Transform("scale({0})".format(SCALEBY)) @ Transform("translate({0},{1})".format(-bb.x1,-bb.y1))
                            p2 = str(el.cpath.transform(tr))
                            el.set("d", p2)

                            # Put transform on parent group since STP cannot convert
                            # transformed paths correctly if they have dashes
                            # See https://gitlab.com/inkscape/inbox/-/issues/7844
                            g.ctransform = -tr

                            csty = el.cspecified_style
                            if "stroke-width" in csty:
                                sw = dh.ipx(csty["stroke-width"])
                                el.cstyle["stroke-width"] = str(sw * SCALEBY)
                            if "stroke-dasharray" in csty:
                                sd = dh.listsplit(csty["stroke-dasharray"])
                                el.cstyle["stroke-dasharray"] = (
                                    str([(sdv or 0) * SCALEBY for sdv in sd])
                                    .strip("[")
                                    .strip("]")
                                )

                        # Fix bug on start markers where auto-start-reverse oriented markers
                        # are inverted by STP
                        sty = el.cspecified_style
                        mstrt = sty.get_link("marker-start", svg)
                        if mstrt is not None:
                            if mstrt.get("orient") == "auto-start-reverse":
                                d = mstrt.duplicate()
                                d.set("orient", "auto")
                                for dk in list(d):
                                    dk.ctransform = (
                                        Transform("scale(-1)") @ dk.ctransform
                                    )
                                sty["marker-start"] = d.get_id(as_url=2)
                                el.cstyle = sty
        return path_els, dummy_groups


if __name__ == "__main__":
    dh.Run_SI_Extension(AutoExporter(), "Autoexporter")


# Scour calling
# from output_scour import ScourInkscape


# SCOUR_OPTIONS = (
#     "--tab=Options",
#     "--set-precision=5",
#     "--simplify-colors=true",
#     "--style-to-xml=true",
#     "--group-collapsing=true",
#     "--create-groups=true",
#     "--keep-editor-data=false",
#     "--keep-unreferenced-defs=false",
#     "--renderer-workaround=true",
#     "--strip-xml-prolog=false",
#     "--remove-metadata=false",
#     "--enable-comment-stripping=false",
#     "--embed-rasters=true",
#     "--enable-viewboxing=false",
#     "--line-breaks=true",
#     "--indent=space",
#     "--nindent=1",
#     "--strip-xml-space=false",
#     "--enable-id-stripping=true",
#     "--shorten-ids=true",
#     "--protect-ids-noninkscape=true",
#     "--scour-version=0.31",
#     "--scour-version-warn-old=false",
# )

# sargs = SCOUR_OPTIONS + (fin,)


# if fformat == "svg":
#     try:
#         ScourInkscape().run(sargs, myoutput)
#     except:  # Scour failed
#         dh.idebug("\nWarning: Optimizer failed, making plain SVG instead")
#         if not(opts.usepdf):
#             # Convert to PDF
#             tmp3 = basetemp.replace(".svg", "_tmp_small.pdf")
#             arg2 = [
#                 bfn,
#                 "--export-background",
#                 "#ffffff",
#                 "--export-background-opacity",
#                 "1.0",
#                 "--export-dpi",
#                 str(opts.dpi),
#                 "--export-filename",
#                 tmp3,
#                 fin,
#             ]
#             dh.subprocess_repeat(arg2)
#             fin = copy.copy(tmp3)
#             tmpoutputs.append(tmp3)
#         else:
#             fin = myoutput.replace("_optimized.svg",".pdf")
#         # Convert back to SVG
#         arg2 = [
#             bfn,
#             "--export-background",
#             "#ffffff",
#             "--export-background-opacity",
#             "1.0",
#             "--export-dpi",
#             str(opts.dpi),
#             "--export-filename",
#             myoutput,
#             fin,
#         ]
#         dh.subprocess_repeat(arg2)
