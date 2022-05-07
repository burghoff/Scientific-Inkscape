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

DEBUGGING = False;
dispprofile = False

SCOUR_OPTIONS = ('--tab=Options', '--set-precision=5', '--simplify-colors=true', 
        '--style-to-xml=true', '--group-collapsing=true', '--create-groups=true', 
        '--keep-editor-data=false', '--keep-unreferenced-defs=false', '--renderer-workaround=true', 
        '--strip-xml-prolog=false', '--remove-metadata=false', '--enable-comment-stripping=false', 
        '--embed-rasters=true', '--enable-viewboxing=false', '--line-breaks=true', '--indent=space', 
        '--nindent=1', '--strip-xml-space=false', '--enable-id-stripping=true', '--shorten-ids=true', 
        '--protect-ids-noninkscape=true', '--scour-version=0.31', '--scour-version-warn-old=false',)

import subprocess
import inkex
from inkex import (
    TextElement,
    FlowRoot,
    FlowPara,
    Tspan,
    TextPath,
    Rectangle,
    addNS,
    Transform,
    Style,
    PathElement,
    Line,
    Rectangle,
    Path,
    Vector2d,
    Use,
    NamedView,
    Defs,
    Metadata,
    ForeignObject,
    Group,
    FontFace,
    StyleElement,
    StyleSheets,
    SvgDocumentElement,
    ShapeElement,
    BaseElement,
    FlowSpan,
    Ellipse,
    Circle,
)

import os, sys
import numpy as np

sys.path.append(
    os.path.dirname(os.path.realpath(sys.argv[0]))
)  # make sure my directory is on the path
import dhelpers as dh


# Convenience functions
def joinmod(dirc, f):
    return os.path.join(os.path.abspath(dirc), f)


def overwrite_svg(svg, fn):
    try:
        os.remove(fn)
    except:
        pass
    inkex.command.write_svg(svg, fn)


from inkex import load_svg


def get_svg(fin):
    svg = load_svg(fin).getroot()
    # print(svg.iddict)
    # dh.iddict = None # only valid one svg at a time
    return svg


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
            "--usesvg", type=inkex.Boolean, default=False, help="Export SVG?"
        )
        pars.add_argument("--dpi", default=600, help="Rasterization DPI")
        pars.add_argument("--dpi_im", default=300, help="Resampling DPI")
        pars.add_argument(
            "--imagemode", type=int, default=1, help="Embedded image handling"
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
            "--exportnow", type=inkex.Boolean, default=False, help="Export me now"
        )
        pars.add_argument(
            "--testmode", type=inkex.Boolean, default=False, help="Test mode?"
        )
        pars.add_argument("--v", type=str, default="1.2", help="Version for debugging")

    def effect(self):
        # self.options.testmode = True;
        if self.options.testmode:
            self.options.usesvg = True
            self.options.thinline = True
            self.options.imagemode = 1
            self.options.texttopath = True
            self.options.exportnow = True

        # dh.idebug(self.options.output.name)

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
            self.options.usesvg,
        ]
        formats = [
            ["pdf", "png", "emf", "eps", "svg"][ii]
            for ii in range(len(formats))
            if formats[ii]
        ]

        dpi = self.options.dpi
        imagedpi = self.options.dpi_im
        reduce_images = self.options.imagemode == 1 or self.options.imagemode == 2
        tojpg = self.options.imagemode == 2
        text_to_paths = self.options.texttopath
        thinline_dehancement = self.options.thinline
        export_now = self.options.exportnow

        bfn = dh.Get_Binary_Loc()
        bloc, bnm = os.path.split(bfn)
        pyloc, pybin = os.path.split(sys.executable)

        if not (export_now):
            aepy = os.path.abspath(
                os.path.join(dh.get_script_path(), "autoexporter_script.py")
            )

            # Pass settings using a config file. Include the current path so Inkex can be called if needed.
            import pickle

            s = [
                self.options.watchdir,
                self.options.writedir,
                bfn,
                formats,
                sys.path,
                dpi,
                imagedpi,
                reduce_images,
                tojpg,
                text_to_paths,
                thinline_dehancement,
            ]
            pickle.dump(
                s, open(os.path.join(dh.get_script_path(), "ae_settings.p"), "wb")
            )
            # dh.idebug(sys.path)

            def escp(x):
                return x.replace(" ", "\\\\ ")

            import platform

            if platform.system().lower() == "darwin":
                # https://stackoverflow.com/questions/39840632/launch-python-script-in-new-terminal
                os.system(
                    'osascript -e \'tell application "Terminal" to do script "'
                    + escp(sys.executable)
                    + " "
                    + escp(aepy)
                    + "\"' >/dev/null"
                )
            elif platform.system().lower() == "windows":
                if pybin == "pythonw.exe":
                    pybin = "python.exe"
                subprocess.Popen([pybin, aepy], shell=False, cwd=pyloc)
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
                    shpath = os.path.abspath(
                        os.path.join(dh.get_script_path(), "FindTerminal.sh")
                    )
                    os.system("sh " + escp(shpath))
                    f = open("tmp", "rb")
                    terms = f.read()
                    f.close()
                    os.remove("tmp")
                    terms = terms.split()
                    for t in reversed(terms):
                        if t == b"x-terminal-emulator":
                            LINUX_TERMINAL_CALL = (
                                "x-terminal-emulator -e bash -c '%CMD'"
                            )
                        elif t == b"gnome-terminal":
                            LINUX_TERMINAL_CALL = (
                                'gnome-terminal -- bash -c "%CMD; exec bash"'
                            )
                    os.system(
                        LINUX_TERMINAL_CALL.replace(
                            "%CMD",
                            escp(sys.executable) + " " + escp(aepy) + " >/dev/null",
                        )
                    )

        else:
            if not (self.options.testmode):
                pth = dh.Get_Current_File(self)
            else:
                pth = self.options.input_file
            options = (
                DEBUGGING,
                dpi,
                imagedpi,
                reduce_images,
                tojpg,
                text_to_paths,
                thinline_dehancement,
                DEBUGGING,
            )

            AutoExporter().export_all(
                bfn, self.options.input_file, pth, formats, options
            )
            # overwrite_svg(self.svg,pth)

        if dispprofile:
            pr.disable()
            s = io.StringIO()
            sortby = SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            dh.debug(s.getvalue())

        if self.options.testmode:
            nf = os.path.abspath(pth[0:-4] + "_optimized.svg")
            # nf2 = nf[0:-12]+'.pdf';
            stream = self.options.output

            if isinstance(stream, str):
                # Copy the new file
                import shutil

                shutil.copyfile(nf, self.options.output)
            else:
                # Write to the output stream
                
                # nf2 = nf.strip('.svg')+'_copy.svg';
                # arg2 = [bfn, "--export-filename",nf2,nf]
                # dh.idebug(arg2)
                # dh.subprocess_repeat(arg2)
                
                # dh.idebug(os.path.exists(nf2))
                
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
            # if os.path.exists(nf2): os.remove(nf2)
            # dh.idebug((self.options.output))
            # raise TypeError
            # self.options.output = None;
            # for k in list(self.svg):
            #     k.delete();
            # for k in list(svg2):
            #     self.svg.append(k);
            # for a in self.svg.attrib.keys():
            #     del self.svg[a]
            # for a in svg2.attrib.keys():
            #     self.svg[a] = svg2[a]
            # overwrite_svg(svg2, self.options.input_file)
            # self.options.output = 'testoutput'

    def export_all(self, bfn, svgfnin, outtemplate, exp_fmts, options):
        (
            debug,
            PNG_DPI,
            imagedpi,
            reduce_images,
            tojpg,
            text_to_paths,
            thinline_dehancement,
            prints,
        ) = options
        
        # Do png before any preprocessing
        if 'png' in exp_fmts:
            finished, tf, myo = AutoExporter().export_file(
                bfn, svgfnin, outtemplate, 'png', None, options)
        
        
        if (reduce_images or text_to_paths) and any(
            [svgfnin in exp_fmts for svgfnin in ["svg", "pdf", "emf", "eps"]]
        ):
            ppoutput = self.preprocessing(bfn, svgfnin, outtemplate, options)
            tempoutputs = ppoutput[1]
            tempdir = ppoutput[2]
        else:
            ppoutput = None
            tempoutputs = []
            tempdir = None

        newfiles = []
        for fmt in exp_fmts:
            if fmt != "png":
                finished, tf, myo = AutoExporter().export_file(
                    bfn, svgfnin, outtemplate, fmt, ppoutput, options
                )
            if finished:
                newfiles.append(myo)
            tempoutputs += tf

        if not (debug):
            for t in list(set(tempoutputs)):
                os.remove(t)
            if tempdir is not None:
                os.rmdir(tempdir)
        return newfiles

    # Use the Inkscape binary to export the file
    def export_file(self, bfn, fin, fout, fformat, ppoutput, options):
        (
            debug,
            PNG_DPI,
            imagedpi,
            reduce_images,
            tojpg,
            text_to_paths,
            thinline_dehancement,
            prints,
        ) = options
        import os, time, copy

        myoutput = fout[0:-4] + "." + fformat
        if prints:
            print("    To " + fformat + "...", end=" ", flush=True)
        timestart = time.time()

        if ppoutput is not None:
            fin, tmpoutputs, tempdir = ppoutput
        else:
            tmpoutputs = []
            tempdir = None

        # try:
        smallsvg = fformat == "svg"
        notpng = not (fformat == "png")
        if (thinline_dehancement or smallsvg) and notpng:
            if tempdir is None:
                import tempfile

                tempdir = os.path.realpath(tempfile.mkdtemp(prefix="ae-"))
                if debug:
                    if prints:
                        dh.idebug("\n    " + joinmod(tempdir, ""))
            basetemp = joinmod(tempdir, "tmp.svg")
        #            print(basetemp)

        if thinline_dehancement and notpng:
            svg = get_svg(fin)
            self.Thinline_Dehancement(svg, fformat)
            tmp1 = basetemp.replace(".svg", "_tld" + fformat[0] + ".svg")
            overwrite_svg(svg, tmp1)
            fin = copy.copy(tmp1)
            tmpoutputs.append(tmp1)

        if smallsvg:  # Convert to pdf, then to a smaller SVG
            # tmp3 = basetemp.replace(".svg", "_tmp_small.pdf")
            # arg2 = [
            #     bfn,
            #     "--export-background",
            #     "#ffffff",
            #     "--export-background-opacity",
            #     "1.0",
            #     "--export-dpi",
            #     str(PNG_DPI),
            #     "--export-filename",
            #     tmp3,
            #     fin,
            # ]
            # dh.subprocess_repeat(arg2)
            # fin = copy.copy(tmp3)
            # tmpoutputs.append(tmp3)
            myoutput = myoutput.replace(".svg", "_optimized.svg")

        try:
            os.remove(myoutput)
        except:
            pass
        
        
        if not(smallsvg):
            arg2 = [
                bfn,
                "--export-background",
                "#ffffff",
                "--export-background-opacity",
                "1.0",
                "--export-dpi",
                str(PNG_DPI),
                "--export-filename",
                myoutput,
                fin,
            ]
            dh.subprocess_repeat(arg2)
            
        else:
            from output_scour import ScourInkscape                    
            sargs = SCOUR_OPTIONS+(fin,)
            
            
            # def set_stderr(state):
            #     import sys, os
            #     if not(state):
            #         sys.stderr = open(os.devnull, 'w')
            #     else:
            #         sys.stderr.close()
            #         sys.stderr = sys.__stderr__
            
            # set_stderr(False)  # suppresses warnings
            # ScourInkscape().run(sargs,myoutput)
            # set_stderr(True)
            
            try:
                ScourInkscape().run(sargs,myoutput)
            except: # Scour failed
                dh.idebug('\nWarning: Optimizer failed, converting to PDF and back')
                # Convert to PDF
                tmp3 = basetemp.replace(".svg", "_tmp_small.pdf")
                arg2 = [
                    bfn,
                    "--export-background",
                    "#ffffff",
                    "--export-background-opacity",
                    "1.0",
                    "--export-dpi",
                    str(PNG_DPI),
                    "--export-filename",
                    tmp3,
                    fin,
                ]
                dh.subprocess_repeat(arg2)
                fin = copy.copy(tmp3)
                tmpoutputs.append(tmp3)
                # Convert back to SVG
                arg2 = [
                    bfn,
                    "--export-background",
                    "#ffffff",
                    "--export-background-opacity",
                    "1.0",
                    "--export-dpi",
                    str(PNG_DPI),
                    "--export-filename",
                    myoutput,
                    fin,
                ]
                dh.subprocess_repeat(arg2)

        if prints:
            print(
                "done! (" + str(round(1000 * (time.time() - timestart)) / 1000) + " s)"
            )
        return True, tmpoutputs, myoutput
        # except:
        #     print('Error writing to file')
        #     return False, tmpoutputs, None

    # @staticmethod
    def preprocessing(self, bfn, fin, fout, options):
        (
            debug,
            PNG_DPI,
            imagedpi,
            reduce_images,
            tojpg,
            text_to_paths,
            thinline_dehancement,
            prints,
        ) = options
        import os, time, copy

        if prints:
            print("    Preprocessing for vector outputs...", end=" ", flush=True)
            timestart = time.time()
        # try:
        tmpoutputs = []
        import tempfile

        tempdir = os.path.realpath(tempfile.mkdtemp(prefix="ae-"))
        if debug:
            if prints:
                dh.idebug("\n    " + joinmod(tempdir, ""))
        basetemp = joinmod(tempdir, "tmp.svg")

        if reduce_images:
            import image_helpers as ih

            # print(ih.hasPIL)
            svg = get_svg(fin)
            els = [
                el
                for el in dh.visible_descendants(svg)
                if isinstance(el, (inkex.Image))
            ]
            if len(els) > 0:
                bbs = dh.Get_Bounding_Boxes(
                    filename=fin, pxinuu=svg.unittouu("1px"), inkscape_binary=bfn
                )
                imgtype = "png"
                acts = ""
                acts2 = ""
                tis = []
                ti2s = []
                for el in els:
                    tmpimg = basetemp.replace(
                        ".svg", "_im_" + el.get_id() + "." + imgtype
                    )
                    tis.append(tmpimg)
                    tmpimg2 = basetemp.replace(
                        ".svg", "_imbg_" + el.get_id() + "." + imgtype
                    )
                    ti2s.append(tmpimg2)
                    acts += (
                        "export-id:"
                        + el.get_id()
                        + "; export-id-only; export-dpi:"
                        + str(imagedpi)
                        + "; export-filename:"
                        + tmpimg
                        + "; export-do; "
                    )  # export item only
                    acts2 += (
                        "export-id:"
                        + el.get_id()
                        + "; export-dpi:"
                        + str(imagedpi)
                        + "; export-filename:"
                        + tmpimg2
                        + "; export-background-opacity:1.0; export-do; "
                    )  # export all w/background
                arg2 = [bfn, "--actions", acts, fin]
                dh.subprocess_repeat(arg2)
                if tojpg and ih.hasPIL:
                    arg2 = [bfn, "--actions", acts2, fin]
                    dh.subprocess_repeat(arg2)

                for ii in range(len(els)):
                    el = els[ii]
                    tmpimg = tis[ii]
                    tmpimg2 = ti2s[ii]
                    if os.path.exists(tmpimg):
                        tmpoutputs.append(tmpimg)
                        if ih.hasPIL:
                            if tojpg:
                                tmpoutputs.append(tmpimg2)
                                tmpjpg = tmpimg.replace(".png", ".jpg")
                                ret, bbox = ih.to_jpeg(tmpimg, tmpimg2, tmpjpg)

                                tmpoutputs.append(tmpjpg)
                                tmpimg = copy.copy(tmpjpg)
                            else:
                                tmpimg, bbox = ih.crop_image(tmpimg)

                        # Compare size of old and new images
                        islinked, validpath = ih.check_linked(el, os.path.split(fin)[0])
                        if islinked and validpath is not None:
                            osz = os.path.getsize(validpath)
                        else:
                            chkimg = (
                                tmpimg.replace(".png", "")
                                .replace(".jpg", "")
                                .replace("_im_", "_imo_")
                            )
                            chkimg = ih.extract_image_simple(el, chkimg)
                            if chkimg is not None:
                                tmpoutputs.append(chkimg)
                                osz = os.path.getsize(chkimg)
                            else:
                                osz = float("inf")
                        nsz = os.path.getsize(tmpimg)
                        if islinked:
                            embedimg = True
                            # always embed linked
                        else:
                            embedimg = (
                                nsz < osz
                            )  # embed new image if smaller than the old

                        if embedimg:
                            ih.embed_external_image(el, tmpimg)

                            # The exported image has a different size and shape than the original
                            # Correct by putting transform/clip/mask on a new parent group, then fix location, then ungroup
                            g = inkex.Group()
                            myi = list(el.getparent()).index(el)
                            el.getparent().insert(myi + 1, g)
                            # place group above
                            g.insert(0, el)
                            # move image to group
                            g.set("transform", el.get("transform"))
                            el.set("transform", None)
                            g.set("clip-path", el.get("clip-path"))
                            el.set("clip-path", None)
                            g.set("mask", el.get("mask"))
                            el.set("mask", None)

                            # Calculate what transform is needed to preserve the image's location
                            ct = (
                                Transform("scale(" + str((svg.cscale)) + ")")
                                @ el.composed_transform()
                            )
                            bb = bbs[el.get_id()]
                            #                    print(bb)
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

                            myx = dh.implicitpx(el.get("x"))
                            myy = dh.implicitpx(el.get("y"))
                            if myx is None:
                                myx = 0
                            if myy is None:
                                myy = 0
                            myw = dh.implicitpx(el.get("width"))
                            myh = dh.implicitpx(el.get("height"))
                            pgo = [
                                Vector2d(myx, myy),
                                Vector2d(myx + myw, myy),
                                Vector2d(myx + myw, myy + myh),
                                Vector2d(myx, myy + myh),
                            ]
                            # where the image is
                            el.set(
                                "preserveAspectRatio", "none"
                            )  # prevents aspect ratio snapping

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
                            if ih.hasPIL and bbox is not None:
                                el.set("x", str(myx + bbox[0] * myw))
                                el.set("y", str(myy + bbox[1] * myh))
                                el.set("width", str((bbox[2] - bbox[0]) * myw))
                                el.set("height", str((bbox[3] - bbox[1]) * myh))
                            dh.ungroup(g)

                tmp4 = basetemp.replace(".svg", "_eimg.svg")
                overwrite_svg(svg, tmp4)
                fin = copy.copy(tmp4)
                tmpoutputs.append(tmp4)

        # if text_to_paths or thinline_dehancement:
        if text_to_paths or thinline_dehancement:
            # if text_to_paths:
            svg = get_svg(fin)
            ds = dh.visible_descendants(svg)

            tels = [
                el.get_id() for el in ds if isinstance(el, (inkex.TextElement))
            ]  # text-like

            # pels = [el.get_id() for el in ds if isinstance(el,dh.otp_support) or el.get('d') is not None] # path-like
            # stroke to path too buggy for now, don't convert strokes
            convert_els = []
            if text_to_paths:
                convert_els += tels
            # if thinline_dehancement:
            #     convert_els+=pels

            celsj = ",".join(convert_els)
            tmp = basetemp.replace(".svg", "_stp.svg")
            arg2 = [
                bfn,
                "--actions",
                "select:"
                + celsj
                + "; object-to-path; export-filename:"
                + tmp
                + "; export-do",
                fin,
            ]
            dh.subprocess_repeat(arg2)

            if text_to_paths:
                # Text converted to paths are a group of characters. Combine them all
                svg = get_svg(tmp)
                for elid in tels:
                    el = dh.getElementById2(svg, elid)
                    if el is not None and len(list(el)) > 0:
                        dh.combine_paths(list(el))
                overwrite_svg(svg, tmp)
            fin = copy.copy(tmp)
            tmpoutputs.append(tmp)
            
        markerfix = True
        if markerfix:
            svg = get_svg(fin)
            self.Marker_Fix(svg)
            tmp = basetemp.replace(".svg", "_mfix" + ".svg")
            overwrite_svg(svg, tmp)
            fin = copy.copy(tmp)
            tmpoutputs.append(tmp)
            
        if prints:
            print(
                "done! (" + str(round(1000 * (time.time() - timestart)) / 1000) + " s)"
            )
        return (fin, tmpoutputs, tempdir)

    def Thinline_Dehancement(self, svg, fformat):
        # Prevents thin-line enhancement in certain bad PDF renderers (*cough* Adobe Acrobat *cough*)
        # For PDFs, turn any straight lines into a Bezier curve
        # For EMFs, add an extra node to straight lines (only works for fills, not strokes currently)
        # Doing both doesn't work: extra nodes removes the Bezier on conversion to PDF, Beziers removed on EMF
        # fmt off
        pth_commands = ["M","m","L","l","H","h","V","v","C","c","S","s","Q","q","T","t","A","a","Z","z"]
        # fmt on
        for el in dh.descendants2(svg):
            if isinstance(el, dh.otp_support):
                dh.object_to_path(el)
            d = el.get("d")
            if d is not None and any(
                [cv in d for cv in ["h", "v", "l", "H", "V", "L"]]
            ):
                if any([cv in d for cv in ["H", "V", "L"]]):
                    d = str(inkex.Path(d).to_relative())
                # dh.idebug(el.get_id())
                ds = d.replace(",", " ").split(" ")
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
                    elif ds[ii] in pth_commands:
                        nextv = False
                        nexth = False
                        nextl = False
                    else:
                        if nexth:
                            if fformat == "emf":
                                hval = float(ds[ii])
                                ds[ii] = "h " + str(hval / 2) + " " + str(hval / 2)
                                # ds[ii] = 'c '+str(hval/2)+',0 '+str(hval/2)+',0 '+str(hval/2)+',0'
                                # ds[ii] = ds[ii]+' '+ds[ii]
                            else:
                                ds[ii] = (
                                    "c "
                                    + ds[ii]
                                    + ",0 "
                                    + ds[ii]
                                    + ",0 "
                                    + ds[ii]
                                    + ",0"
                                )
                        elif nextv:
                            if fformat == "emf":
                                vval = float(ds[ii])
                                ds[ii] = "v " + str(vval / 2) + " " + str(vval / 2)
                                # ds[ii] = 'c 0,'+str(vval/2)+' 0,'+str(vval/2)+' 0,'+str(vval/2)
                                # ds[ii] = ds[ii]+' '+ds[ii]
                            else:
                                ds[ii] = (
                                    "c 0," + ds[ii] + " 0," + ds[ii] + " 0," + ds[ii]
                                )
                        elif nextl:
                            if fformat == "emf":
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
                                # ds[ii] = 'c '+str(lx/2)+','+str(ly/2)+' '+str(lx/2)+','+str(ly/2)+' '+str(lx/2)+','+str(ly/2);
                                # ds[ii] = ds[ii]+' '+ds[ii]
                            else:
                                ds[ii] = (
                                    "c "
                                    + ds[ii]
                                    + ","
                                    + ds[ii + 1]
                                    + " "
                                    + ds[ii]
                                    + ","
                                    + ds[ii + 1]
                                    + " "
                                    + ds[ii]
                                    + ","
                                    + ds[ii + 1]
                                )
                            ds[ii + 1] = ""
                            ii += 1
                    ii += 1
                newd = " ".join(ds)
                newd = newd.replace("  ", " ")
                el.set("d", newd)

    def Marker_Fix(self, svg):
        # Fixes the marker bug that occurs with context-stroke and context-fill
        for el in dh.descendants2(svg):
            sty = el.cspecified_style;
            mkrs = []
            if 'marker-start' in sty: mkrs.append('marker-start')
            if 'marker-mid'   in sty: mkrs.append('marker-mid')
            if 'marker-end'   in sty: mkrs.append('marker-end')
            for m in mkrs:
                url = sty[m][5:-1]
                mkrel = dh.getElementById2(svg, url)
                if mkrel is not None:
                    mkrds = dh.descendants2(mkrel)
                    anycontext = any([(a=='stroke' or a=='fill') and 'context' in v for d in mkrds for a,v in d.cspecified_style.items()])
                    if anycontext:
                        handled = True;
                        dup = dh.get_duplicate2(mkrel);
                        dupds = dh.descendants2(dup)
                        for d in dupds:
                            dsty = d.cspecified_style;
                            for a,v in dsty.items():
                                if (a=='stroke' or a=='fill') and 'context' in v:
                                    if v=='context-stroke':
                                        dh.Set_Style_Comp(d, a, sty.get('stroke'))
                                    elif v=='context-fill':
                                        dh.Set_Style_Comp(d, a, sty.get('fill'));
                                    else: # I don't know what this is
                                        handled = False
                        if handled:
                            dh.Set_Style_Comp(el,m,dup.get_id2(as_url=2))

if __name__ == "__main__":
    dh.Version_Check("Autoexporter")
    import warnings
    warnings.filterwarnings("ignore")
    AutoExporter().run()
