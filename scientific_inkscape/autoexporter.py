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

DEBUGGING = False
dispprofile = False

SCOUR_OPTIONS = (
    "--tab=Options",
    "--set-precision=5",
    "--simplify-colors=true",
    "--style-to-xml=true",
    "--group-collapsing=true",
    "--create-groups=true",
    "--keep-editor-data=false",
    "--keep-unreferenced-defs=false",
    "--renderer-workaround=true",
    "--strip-xml-prolog=false",
    "--remove-metadata=false",
    "--enable-comment-stripping=false",
    "--embed-rasters=true",
    "--enable-viewboxing=false",
    "--line-breaks=true",
    "--indent=space",
    "--nindent=1",
    "--strip-xml-space=false",
    "--enable-id-stripping=true",
    "--shorten-ids=true",
    "--protect-ids-noninkscape=true",
    "--scour-version=0.31",
    "--scour-version-warn-old=false",
)

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
import image_helpers as ih


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

PTH_COMMANDS = [
            "M",
            "m",
            "L",
            "l",
            "H",
            "h",
            "V",
            "v",
            "C",
            "c",
            "S",
            "s",
            "Q",
            "q",
            "T",
            "t",
            "A",
            "a",
            "Z",
            "z",
        ]
    
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
        # pars.add_argument(
        #     "--usesvg", type=inkex.Boolean, default=False, help="Export Optimized SVG?"
        # )
        pars.add_argument(
            "--usepsvg", type=inkex.Boolean, default=False, help="Export Portable SVG?"
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
        # pars.add_argument(
        #     "--svgoptpdf",
        #     type=inkex.Boolean,
        #     default=False,
        #     help="Alternate Optimized SVG?",
        # )
        pars.add_argument(
            "--exportnow", type=inkex.Boolean, default=False, help="Export me now"
        )
        pars.add_argument(
            "--testmode", type=inkex.Boolean, default=False, help="Test mode?"
        )
        pars.add_argument("--v", type=str, default="1.2", help="Version for debugging")
        pars.add_argument(
            "--rasterizermode", type=int, default=1, help="Mark for rasterization"
        )
        pars.add_argument(
            "--margin", type=float, default=0.5, help="Document margin (mm)"
        )

    def effect(self):
        if self.options.tab=='rasterizer':
            sel = [self.svg.selection[ii] for ii in range(len(self.svg.selection))]
            for el in sel:
                if self.options.rasterizermode==1:
                    el.set('autoexporter_rasterize','True')
                else:
                    el.set('autoexporter_rasterize',None)
            return
        
        # self.options.testmode = True;
        if self.options.testmode:
            self.options.usepsvg = True
            self.options.thinline = True
            self.options.imagemode = 1
            self.options.texttopath = True
            self.options.exportnow = True
            self.options.margin = 0.5
            
            import random
            random.seed(1)
            # self.options.svgoptpdf = True

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
            ["pdf", "png", "emf", "eps",'psvg'][ii]
            for ii in range(len(formats))
            if formats[ii]
        ]

        # Make an options copy we can pass to the external program
        import copy

        optcopy = copy.copy(self.options)
        delattr(optcopy, "output")
        delattr(optcopy, "input_file")
        optcopy.reduce_images = (
            self.options.imagemode == 1 or self.options.imagemode == 2
        )
        optcopy.tojpg = self.options.imagemode == 2

        bfn = dh.Get_Binary_Loc()
        bloc, bnm = os.path.split(bfn)
        pyloc, pybin = os.path.split(sys.executable)

        if not (self.options.exportnow):
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
                optcopy,
            ]
            pickle.dump(
                s, open(os.path.join(dh.get_script_path(), "ae_settings.p"), "wb")
            )

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
            optcopy.debug = DEBUGGING
            optcopy.prints = DEBUGGING
            optcopy.linked_locations = ih.get_linked_locations(self); # needed to find linked images in relative directories

            AutoExporter().export_all(
                bfn, self.options.input_file, pth, formats, optcopy
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
            nf = os.path.abspath(pth[0:-4] + "_portable.svg")
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

    def export_all(self, bfn, fin, outtemplate, exp_fmts, input_options):
        # Make a temp directory
        import tempfile
        tempdir = os.path.realpath(tempfile.mkdtemp(prefix="ae-"));
        if input_options.debug:
            if input_options.prints:
                dh.idebug("\n    " + joinmod(tempdir, ""))
        tempbase = joinmod(tempdir, 't')
        

        # Add a document margin
        if input_options.margin!=0:
            svg = get_svg(fin)
            tmp = tempbase+ "_marg.svg"
            self.Add_Margin(svg,input_options.margin)
            overwrite_svg(svg, tmp)
            import copy
            fin = copy.copy(tmp)

        # Do png before any preprocessing
        if "png" in exp_fmts:
            finished, myo = AutoExporter().export_file(
                bfn, fin, outtemplate, "png", None, input_options,tempbase
            )

        # Do preprocessing
        if any([fmt in exp_fmts for fmt in ["pdf", "emf", "eps",'psvg']]):
            ppoutput = self.preprocessing(bfn, fin, outtemplate, input_options,tempbase)
            # tempoutputs = ppoutput[1]
            # tempdir = ppoutput[2]
        else:
            ppoutput = None
            # tempoutputs = []
            # tempdir = None

        # Do vector outputs
        newfiles = []
        for fmt in exp_fmts:
            if fmt != "png":
                finished, myo = AutoExporter().export_file(
                    bfn, fin, outtemplate, fmt, ppoutput, input_options,tempbase
                )
            if finished:
                newfiles.append(myo)
            # tempoutputs += tf
            
        # Remove temporary outputs and directory
        if not (input_options.debug):
            # for t in list(set(tempoutputs)):
            #     os.remove(t)
            for t in list(set(os.listdir(tempdir))):
                os.remove(joinmod(tempdir,t)) 
            if tempdir is not None:
                os.rmdir(tempdir)
        return newfiles

    # Use the Inkscape binary to export the file
    def export_file(self, bfn, fin, fout, fformat, ppoutput, input_options,tempbase):
        import os, time, copy

        myoutput = fout[0:-4] + "." + fformat
        if input_options.prints:
            print("    To " + fformat + "...", end=" ", flush=True)
        timestart = time.time()

        if ppoutput is not None:
            fin = ppoutput
        # else:
        #     tmpoutputs = []
            # tempdir = None

        # try:
        smallsvg = (fformat == "psvg")
        notpng = not (fformat == "png")
        # if (input_options.thinline or smallsvg) and notpng:
        #     if tempdir is None:
        #         import tempfile
        #         tempdir = os.path.realpath(tempfile.mkdtemp(prefix="ae-"))
        #         if input_options.debug:
        #             if input_options.prints:
        #                 dh.idebug("\n    " + joinmod(tempdir, ""))
        #     basetemp = joinmod(tempdir, "tmp.svg")

        if input_options.thinline and notpng:
            svg = get_svg(fin)
            if fformat in ['pdf','eps','psvg']:
                self.Thinline_Dehancement(svg, 'bezier')
            else:
                self.Thinline_Dehancement(svg, 'split')
            tmp = tempbase+ "_tld" + fformat[0] + ".svg"
            overwrite_svg(svg, tmp)
            fin = copy.copy(tmp)
            # tmpoutputs.append(tmp)

        if fformat == "psvg":
            myoutput = myoutput.replace(".psvg", "_portable.svg")
            
  

        try:
            os.remove(myoutput)
        except:
            pass
        
        def make_output(filein,fileout):
            arg2 = [
                bfn,
                "--export-background",
                "#ffffff",
                "--export-background-opacity",
                "1.0",
                "--export-dpi",
                str(input_options.dpi),
                "--export-filename",
                fileout,
                filein,
            ]
            dh.subprocess_repeat(arg2)

        if not (smallsvg):
            make_output(fin,myoutput)
        else:
            # Make PDF if necessary
            if not(input_options.usepdf):
                tmp = tempbase+"_tmp_small.pdf"
                make_output(fin,tmp)
                fin = copy.copy(tmp)
                # tmpoutputs.append(tmp)
            else:
                fin = myoutput.replace("_portable.svg",".pdf")
                
            # Convert back to SVG
            tmp = tempbase+"_fin" + ".svg"
            make_output(fin,tmp)
            fin = copy.copy(tmp)
            # tmpoutputs.append(tmp)
            
            # Post PDFication cleanup for Office products
            svg = get_svg(fin)
            vds = dh.visible_descendants(svg)
            for d in vds:
                if isinstance(d,(TextElement)):
                    self.Scale_Text(d)
                elif isinstance(d,(inkex.Image)):
                    if ih.hasPIL:
                        self.Merge_Mask(d)
                    while d.getparent()!=d.croot and d.getparent() is not None and d.croot is not None: # causes problems and doesn't help
                        dh.ungroup(d.getparent());
                elif isinstance(d,(inkex.Group)):
                    if len(d)==0:
                        dh.deleteup(d)
            
            if input_options.thinline:
                for d in vds:
                    self.Bezier_to_Split(d)   
            overwrite_svg(svg, myoutput)

        if input_options.prints:
            toc = time.time() - timestart;
            print("done! (" + str(round(1000 * toc) / 1000) + " s)")
        return True, myoutput

    def preprocessing(self, bfn, fin, fout, input_options,tempbase):
        import os, time, copy
        import image_helpers as ih

        if input_options.prints:
            print("    Preprocessing vector output...", end=" ", flush=True)
            timestart = time.time()
        # try:
        # tmpoutputs = []
        
        # import tempfile
        # tempdir = os.path.realpath(tempfile.mkdtemp(prefix="ae-"));
        # if input_options.debug:
        #     if input_options.prints:
        #         dh.idebug("\n    " + joinmod(tempdir, ""))
        # temphead = "tmp.svg"
        # basetemp = joinmod(tempdir, temphead)
        tempdir  = os.path.split(tempbase)[0]
        temphead = os.path.split(tempbase)[1]
        
        # SVG modifications that should be done prior to any binary calls
        svg = get_svg(fin)
        
        # Embed linked images into the SVG. This should be done prior to clone unlinking
        # since some images may be cloned
        if input_options.exportnow:
            lls = input_options.linked_locations
        else:
            lls = ih.get_linked_locations_file(fin,svg)
        for k in lls:
            el = dh.getElementById2(svg,k)
            ih.embed_external_image(el, lls[k])
        
        vds = dh.visible_descendants(svg);
        raster_ids = []; image_ids = [];
        for el in vds:
            # Unlink any clones for the PDF image and marker fixes 
            if isinstance(el,(inkex.Use)) and not(isinstance(el, (inkex.Symbol))):
                newel = dh.unlink2(el)
                myi = vds.index(el)
                vds[myi] = newel;
            
            # Remove trivial groups inside masks/transparent objects
            if isinstance(el,(inkex.Group)) and len(list(el))==1 and\
                any([anc.get_link('mask',svg) is not None \
                     or (el.ccascaded_style.get('opacity') is not None and \
                         float(el.ccascaded_style.get('opacity'))<1) \
                         for anc in el.ancestors2(includeme=True)]):
                dh.ungroup(el)
            
        for el in vds:
            elid = el.get_id2();
            # Fix marker export bug for PDFs
            self.Marker_Fix(el)
            
            # Fix opacity bug for Office PDF saving
            self.Opacity_Fix(el)
            
            # Find out which objects need to be rasterized
            sty = el.cstyle; # only want the object with the filter
            if sty.get_link('filter',svg) is not None:                          
                raster_ids.append(elid)               # filtered objects (always rasterized at PDF)
            if (sty.get('fill') is not None   and 'url' in sty.get('fill')) or \
               (sty.get('stroke') is not None and 'url' in sty.get('stroke')):
                raster_ids.append(elid)               # gradient objects  
            if el.get_link('mask') is not None:
                raster_ids.append(elid)               # masked objects (always rasterized at PDF)
            if el.get('autoexporter_rasterize')=='True':
                raster_ids.append(elid);              # rasterizer-marked
            if isinstance(el, (inkex.Image)):
                image_ids.append(elid);
                # dh.idebug(elid)
        if not(input_options.reduce_images):
            input_options.dpi_im = input_options.dpi
                
        
        # dh.idebug(image_ids)
        # dh.idebug(raster_ids)
        # dh.idebug(fin)
        
        dh.flush_stylesheet_entries(svg) # since we ungrouped
        tmp = tempbase+"_mod.svg"
        overwrite_svg(svg, tmp)
        fin = copy.copy(tmp)
        # tmpoutputs.append(tmp)

        # Rasterizations
        if len(raster_ids+image_ids)>0:
            svg = get_svg(fin)

            vds = dh.visible_descendants(svg);
            els = [el for el in vds if el.get_id2() in list(set(raster_ids+image_ids))]
            if len(els) > 0:
                # bbs = dh.Get_Bounding_Boxes(
                #     filename=fin, pxinuu=svg.unittouu("1px"), inkscape_binary=bfn
                # )
                imgtype = "png"
                acts = ""
                acts2 = ""
                tis = []
                ti2s = []
                for el in els:
                    elid = el.get_id2();
                    # dh.idebug([elid,el.croot])
                    tmpimg = temphead+"_im_" + elid + "." + imgtype
                    tis.append(tmpimg)
                    tmpimg2 = temphead+"_imbg_" + elid + "." + imgtype
                    ti2s.append(tmpimg2)
                    
                    # dh.idebug(tmpimg)
                    
                    if elid in raster_ids:
                        mydpi = input_options.dpi
                    else:
                        mydpi = input_options.dpi_im
                    
                    acts += (
                        "export-id:"
                        + el.get_id()
                        + "; export-id-only; export-dpi:"
                        + str(mydpi)
                        + "; export-filename:"
                        + tmpimg
                        + "; export-background-opacity:0.0; export-do; "
                    )  # export item only
                    acts2 += (
                        "export-id:"
                        + el.get_id()
                        + "; export-dpi:"
                        + str(mydpi)
                        + "; export-filename:"
                        + tmpimg2
                        + "; export-background-opacity:1.0; export-do; "
                    )  # export all w/background
                if ih.hasPIL:
                    args = ["--actions", acts2+acts];  # export-id-onlys need to go last
                    # args = [bfn, "--actions", acts2+acts, fin];  
                else:
                    args = ["--actions", acts]
                    # args = [bfn, "--actions", acts, fin];  
                
                
                oldwd = os.getcwd();
                os.chdir(tempdir); # use relative paths to reduce arg length
                bbs = dh.Get_Bounding_Boxes(
                    filename=fin, pxinuu=svg.unittouu("1px"), inkscape_binary=bfn, extra_args = args
                )
                os.chdir(oldwd);
                tis = [os.path.join(tempdir,t)  for t in tis]
                ti2s = [os.path.join(tempdir,t) for t in ti2s]
                    
                # Add any generated images to the temp output list
                # for ii in range(len(els)):
                #     if os.path.exists(tis[ii]):
                #         tmpoutputs.append(tis[ii])
                #     if os.path.exists(ti2s[ii]):
                #         tmpoutputs.append(ti2s[ii])
                  

                for ii in range(len(els)):
                    el = els[ii]
                    tmpimg = tis[ii]
                    tmpimg2 = ti2s[ii]
                    
                    if os.path.exists(tmpimg):
                        anyalpha0 = False
                        if ih.hasPIL:
                            bbox = ih.crop_images([tmpimg,tmpimg2])
                            anyalpha0 = ih.Set_Alpha0_RGB(tmpimg,tmpimg2)
                            if input_options.tojpg:
                                tmpjpg = tmpimg.replace(".png", ".jpg")
                                ih.to_jpeg(tmpimg2,tmpjpg)
                                # tmpoutputs.append(tmpjpg)
                                tmpimg = copy.copy(tmpjpg)
                        else:
                            bbox = None;

                        # Compare size of old and new images
                        osz = ih.embedded_size(el);
                        if osz is None: osz = float("inf")
                        nsz = os.path.getsize(tmpimg)
                        hasmaskclip = el.get_link('mask') is not None or el.get_link('clip-path') is not None  # clipping and masking
                        embedimg = (nsz < osz) or (anyalpha0 or hasmaskclip)

                        
                        # dh.idebug([nsz,osz]) 

                        if embedimg:                 
                            self.Replace_with_Raster(el,tmpimg,bbs[el.get_id2()],bbox)

                
                dh.flush_stylesheet_entries(svg) # since we ungrouped
                tmp = tempbase+"_eimg.svg"
                overwrite_svg(svg, tmp)
                fin = copy.copy(tmp)
                # tmpoutputs.append(tmp)

        # if text_to_paths or thinline_dehancement:
        if input_options.texttopath:
            svg = get_svg(fin)
            vd = dh.visible_descendants(svg)

            tels = [
                el.get_id() for el in vd if isinstance(el, (inkex.TextElement))
            ]  # text-like

            convert_els = tels

            celsj = ",".join(convert_els)
            tmp = tempbase+"_stp.svg"
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

            # Text converted to paths are a group of characters. Combine them all
            svg = get_svg(tmp)
            for elid in tels:
                el = dh.getElementById2(svg, elid)
                if el is not None and len(list(el)) > 0:
                    dh.combine_paths(list(el))
                    
            overwrite_svg(svg, tmp)
            fin = copy.copy(tmp)
            # tmpoutputs.append(tmp)

        if input_options.prints:
            print(
                "done! (" + str(round(1000 * (time.time() - timestart)) / 1000) + " s)"
            )
        return fin


    def Thinline_Dehancement(self, svg, mode='split'):
        # Prevents thin-line enhancement in certain bad PDF renderers (*cough* Adobe Acrobat *cough*)
        # 'bezier' mode converts h,v,l path commands to trivial Beziers
        # 'split' mode splits h,v,l path commands into two path commands
        # The Office PDF renderer removes trivial Beziers, as does conversion to EMF
        # The Inkscape PDF renderer removes split commands
        # In general I prefer split, so I do this for everything other than PDF
        for el in dh.descendants2(svg):
            if isinstance(el, dh.otp_support) and not (isinstance(el, (PathElement))):
                dh.object_to_path(el)
            d = el.get("d")
            if d is not None and any(
                [cv in d for cv in ["h", "v", "l", "H", "V", "L"]]
            ):
                if any([cv in d for cv in ["H", "V", "L"]]):
                    d = str(inkex.Path(d).to_relative())
                ds = d.replace(",", " ").split(" ");
                ds = [v for v in ds if v!='']
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
                                ds[ii] = "c " + ' '.join([ds[ii]+ ",0"]*3)
                        elif nextv:
                            if mode == "split":
                                vval = float(ds[ii])
                                ds[ii] = "v " + str(vval / 2) + " " + str(vval / 2)
                            else:
                                ds[ii] = "c " + ' '.join(["0,"+ ds[ii]]*3);
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
                                ds[ii] = "c "+ ' '.join([ds[ii]+","+ ds[ii + 1]]*3)
                            ds[ii + 1] = ""
                            ii += 1
                    ii += 1
                newd = " ".join([v for v in ds if v!=''])
                newd = newd.replace("  ", " ")
                el.set("d", newd)
                
    def Bezier_to_Split(self, el):
        # Converts the Bezier TLD to split (for the Portable SVG)
        if isinstance(el, dh.otp_support) and not (isinstance(el, (PathElement))):
            dh.object_to_path(el)
        d = el.get("d")
        if d is not None and any(
            [cv in d for cv in ["c", "C"]]
        ):
            if any([cv in d for cv in ["C"]]):
                d = str(inkex.Path(d).to_relative())
            ds = d.replace(",", " ").split(" ");
            ds = [v for v in ds if v!='']
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
                        cvs = ds[ii:ii+6]
                        if cvs[0]==cvs[2]==cvs[4] and cvs[1]==cvs[3]==cvs[5]:
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
                            ds[ii] = 'c '+cvs[0]+','+cvs[1]+' '+cvs[2]+','+cvs[3]+' '+cvs[4]+','+cvs[5]
                        ds[ii+1:ii+6]=['']*5
                        ii+=5
                ii += 1
            newd = " ".join([v for v in ds if v!=''])
            newd = newd.replace("  ", " ")
            el.set("d", newd)


    def Marker_Fix(self, el):
        # Fixes the marker bug that occurs with context-stroke and context-fill
        svg = el.croot
        sty = el.cspecified_style
        mkrs = []
        if "marker-start" in sty:
            mkrs.append("marker-start")
        if "marker-mid" in sty:
            mkrs.append("marker-mid")
        if "marker-end" in sty:
            mkrs.append("marker-end")
        for m in mkrs:
            url = sty[m][5:-1]
            mkrel = dh.getElementById2(svg, url)
            if mkrel is not None:
                mkrds = dh.descendants2(mkrel)
                anycontext = any(
                    [
                        (a == "stroke" or a == "fill") and "context" in v
                        for d in mkrds
                        for a, v in d.cspecified_style.items()
                    ]
                )
                if anycontext:
                    handled = True
                    dup = dh.get_duplicate2(mkrel)
                    dupds = dh.descendants2(dup)
                    for d in dupds:
                        dsty = d.cspecified_style
                        for a, v in dsty.items():
                            if (a == "stroke" or a == "fill") and "context" in v:
                                if v == "context-stroke":
                                    dh.Set_Style_Comp(d, a, sty.get("stroke"))
                                elif v == "context-fill":
                                    dh.Set_Style_Comp(d, a, sty.get("fill"))
                                else:  # I don't know what this is
                                    handled = False
                    if handled:
                        dh.Set_Style_Comp(el, m, dup.get_id2(as_url=2))
                            
    def Opacity_Fix(self, el):
        # Fuse opacity onto fill and stroke for path-like elements
        # Prevents rasterization-at-PDF for Office products
        sty = el.cspecified_style;
        if sty.get('opacity') is not None and isinstance(el,dh.otp_support):
            sf = dh.get_strokefill(el) # fuses opacity and stroke-opacity/fill-opacity
            if sf.stroke is not None:
                dh.Set_Style_Comp(el,'stroke-opacity',sf.stroke.alpha)
            if sf.fill is not None:
                dh.Set_Style_Comp(el,'fill-opacity',sf.fill.alpha)
            dh.Set_Style_Comp(el,'opacity',1);
                
    def Scale_Text(self,el):
        # Sets all font-sizes to 100 px by moving size into transform
        # Office rounds every fonts to the nearest px and then transforms it,
        # so this makes text sizes more accurate
        from TextParser import LineList, tline      
        svg = el.croot;
        szs = []
        for d in el.descendants2: # all Tspan sizes
            fs = d.ccascaded_style.get('font-size')
            fs = {"small": "10px", "medium": "12px", "large": "14px"}.get(fs, fs)
            if fs is not None and '%' not in fs:
                szs.append(dh.implicitpx(fs))
        if len(szs)==0:
            minsz = dh.default_style_atts['font-size']
            minsz = {"small": 10, "medium": 12, "large": 14}.get(minsz, minsz)
        else:
            minsz = min(szs)
            
        s=1/minsz*100
        
        # Make a dummy group so we can properly compose the transform
        # g = dh.new_element(inkex.Group, el)
        # el.getparent().insert(list(el.getparent()).index(el) + 1, g)
        # g.append(el)
        # g.ctransform = el.ctransform; el.ctransform = None;
        # g.set("clip-path", el.get("clip-path"));   el.set("clip-path", None)
        # g.set("mask", el.get("mask"))          ;   el.set("mask", None)
        g = dh.group([el],moveTCM=True)
        
        for d in reversed(el.descendants2):
            xv = LineList.GetXY(d,'x')
            yv = LineList.GetXY(d,'y')
            dxv = LineList.GetXY(d,'dx')
            dyv = LineList.GetXY(d,'dy')
            
            if xv[0] is not None:  d.set('x',tline.writev([v*s for v in xv]))
            if yv[0] is not None:  d.set('y',tline.writev([v*s for v in yv]))
            if dxv[0] is not None: d.set('dx',tline.writev([v*s for v in dxv]))
            if dyv[0] is not None: d.set('dy',tline.writev([v*s for v in dyv]))
                
            fs,sf,tmp,tmp = dh.Get_Composed_Width(d,'font-size',nargout=4)
            dh.Set_Style_Comp(d, 'font-size', str(fs/sf*s))    
                
            otherpx = ['letter-spacing','inline-size']
            for oth in otherpx:
                othv = d.ccascaded_style.get(oth)
                if othv is not None:
                    dh.Set_Style_Comp(d, oth, str(dh.implicitpx(othv)*s))
                
            shape = d.ccascaded_style.get_link('shape-inside',svg);
            if shape is not None:
                dup = shape.duplicate2();
                svg.defs2.append(dup);
                dup.ctransform = inkex.Transform((s,0,0,s,0,0)) @ dup.ctransform
                dh.Set_Style_Comp(d, 'shape-inside', dup.get_id2(as_url=2))

        el.ctransform = inkex.Transform((1/s,0,0,1/s,0,0))
        dh.ungroup(g)
        
        # compose_all(el, clipurl, maskurl, transform, style)
        
    def Merge_Mask(self,el):
        # Office will poorly rasterize masked elements at PDF-time
        # Revert alpha masks made by PDFication back to alpha
        mymask = el.get_link('mask')
        if mymask is not None and len(list(mymask))==1:
            # only if one object in mask
            mask = list(mymask)[0]
            if isinstance(mask, inkex.Image):
                if mask.get('height')=='1' and mask.get('width')=='1':
                    im1 = ih.str_to_ImagePIL(el.get('xlink:href')).convert('RGBA')
                    im2 = ih.str_to_ImagePIL(mask.get('xlink:href')).convert('RGBA')
                    # only if mask the same size
                    if im1.size==im2.size:
                        import numpy as np
                        d1 = np.asarray(im1)
                        d2 = np.asarray(im2)
                        # only if image is opaque
                        if np.where(d1[:,:,3]==255,True,False).all():
                            nd = np.stack((d1[:,:,0],d1[:,:,1],d1[:,:,2],d2[:,:,0]),2);
                            from PIL import Image as ImagePIL
                            newstr = ih.ImagePIL_to_str(ImagePIL.fromarray(nd))
                            el.set('xlink:href',newstr)
                            mask.delete2();
                            el.set('mask',None)
                            
    def Replace_with_Raster(self,el,imgloc,bb,imgbbox):
        svg = el.croot;
        if svg is None: # in case we were already rasterized within ancestor
            return
        # dh.idebug(el.get_id())
        # dh.idebug(svg)
        ih.embed_external_image(el, imgloc)

        
        # The exported image has a different size and shape than the original
        # Correct by putting transform/clip/mask on a new parent group, then fix location, then ungroup
        g = dh.group([el],moveTCM=True)
        g.set("clip-path", None); # conversion to bitmap already includes clips
        g.set("mask", None)       # conversion to bitmap already includes masks

        # Calculate what transform is needed to preserve the image's location
        ct = (
            Transform("scale(" + str((svg.cscale)) + ")")
            @ el.ccomposed_transform
        )
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

        # if el not in raster_objects: # already an Image
        #     myx = dh.implicitpx(el.get("x"))
        #     myy = dh.implicitpx(el.get("y"))
        #     if myx is None:
        #         myx = 0
        #     if myy is None:
        #         myy = 0
        #     myw = dh.implicitpx(el.get("width"))
        #     myh = dh.implicitpx(el.get("height"))
        #     sty = el.get('image-rendering')
        # else: # replace object with Image
        
        newel = dh.new_element(inkex.Image, el);
        dh.replace_element(el, newel)
        newel.set('x',0); myx=0;
        newel.set('y',0); myy=0;
        newel.set('width',1);  myw = dh.implicitpx(newel.get("width"));
        newel.set('height',1); myh = dh.implicitpx(newel.get("height"));
        newel.set('xlink:href',el.get('xlink:href'))
        
        sty = ''
        ir = el.cstyle.get('image-rendering');
        if ir is not None:
            sty = 'image-rendering:'+ir
        el = newel;
            
            
        pgo = [
            Vector2d(myx, myy),
            Vector2d(myx + myw, myy),
            Vector2d(myx + myw, myy + myh),
            Vector2d(myx, myy + myh),
        ]  # where the image is
        el.set(
            "preserveAspectRatio", "none"
        )  # prevents aspect ratio snapping
        el.set('style',sty) # override existing styles

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
        
    def Add_Margin(self,svg,amt_mm):
        m = inkex.units.convert_unit(str(amt_mm)+'mm','px');
        
        try:
            nvs = [el for el in list(svg) if isinstance(el,inkex.NamedView)]
            pgs = [el for nv in nvs for el in list(nv) if isinstance(el,inkex.Page)]
        except:
            pgs = [];
            
        if len(pgs)>0:
            # Has Pages
            for pg in pgs:
                x = dh.implicitpx(pg.get('x'))
                y = dh.implicitpx(pg.get('y'))
                w = dh.implicitpx(pg.get('width'))
                h = dh.implicitpx(pg.get('height'))
                
                pg.set('x',str(x-m))
                pg.set('y',str(y-m))
                pg.set('width', str(w+2*m))
                pg.set('height',str(h+2*m))
        
        else:
            # If an old version of Inkscape or has no Pages, defined by viewbox
            vb = svg.get_viewbox2()
            w = inkex.units.convert_unit(svg.get('width'),'px')
            h = inkex.units.convert_unit(svg.get('height'),'px')
            
            wn = w + 2*m
            hn = h + 2*m
            
            wu = inkex.units.parse_unit(svg.get('width'))
            if wu is not None:
                wu = wu[1]
            else:
                wu = 'px'
                
            svg.set('width',str(inkex.units.convert_unit(str(wn)+'px', wu))+wu)
            svg.set('height',str(inkex.units.convert_unit(str(hn)+'px', wu))+wu)
            
            deltaw = (wn/w-1)*vb[2];
            deltah = (hn/h-1)*vb[3]; 
    
            nvb = [vb[0]-deltaw/2,vb[1]-deltah/2,vb[2]+deltaw,vb[3]+deltah]
            svg.set('viewBox',' '.join([str(v) for v in nvb]))
        



if __name__ == "__main__":
    dh.Version_Check("Autoexporter")
    import warnings

    warnings.filterwarnings("ignore")
    AutoExporter().run()


# Scour calling
# from output_scour import ScourInkscape

# sargs = SCOUR_OPTIONS + (fin,)


# if fformat == "svg":
#     try:
#         ScourInkscape().run(sargs, myoutput)
#     except:  # Scour failed
#         dh.idebug("\nWarning: Optimizer failed, making portable SVG instead")
#         if not(input_options.usepdf):
#             # Convert to PDF
#             tmp3 = basetemp.replace(".svg", "_tmp_small.pdf")
#             arg2 = [
#                 bfn,
#                 "--export-background",
#                 "#ffffff",
#                 "--export-background-opacity",
#                 "1.0",
#                 "--export-dpi",
#                 str(input_options.dpi),
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
#             str(input_options.dpi),
#             "--export-filename",
#             myoutput,
#             fin,
#         ]
#         dh.subprocess_repeat(arg2)