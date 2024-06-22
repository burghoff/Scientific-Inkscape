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
#

"""
Some functions for getting the properties of fonts and characters.
Three libraries are used:
  fontconfig: Used for discovering fonts based on the CSS (SVG) style. This
              uses Inkscape's libfontconfig, so it always matches what Inkscape
              does.
  fonttools:  Gets font properties once discovered (from font's filename)
  Pango:      Used to render test characters (included with GTK)
              Sets up a blank GTK window and renders Pango text, reusing
              the same layout for all rendering.
"""

import inkex
import os, warnings, sys, re, ctypes
from inkex.text.utils import default_style_atts
from inkex import Style
from unittest.mock import patch

# The fontconfig library is used to select a font given its CSS specs
# This library should work starting with v1.0

# Due to the way fontconfig is structured, we have to patch
# ctypes's LoadLibrary to help it find libfontconfig
original_load_library = ctypes.cdll.LoadLibrary


def custom_load_library(name):
    if name in ["libfontconfig.so.1", "libfreetype.so.6"]:
        LIBNAME = {
            "linux": {
                "libfreetype.so.6": "libfreetype.so.6",
                "libfontconfig.so.1": "libfontconfig.so.1",
            },
            "openbsd6": {
                "libfreetype.so.6": "libfreetype.so.28",
                "libfontconfig.so.1": "libfontconfig.so.11",
            },
            "darwin": {
                "libfreetype.so.6": "libfreetype.6.dylib",
                "libfontconfig.so.1": "libfontconfig.1.dylib",
            },
            "win32": {
                "libfreetype.so.6": "libfreetype-6.dll",
                "libfontconfig.so.1": "libfontconfig-1.dll",
            },
        }[sys.platform][name]

        if "SI_FC_DIR" in os.environ:
            fpath = os.path.abspath(os.path.join(os.environ["SI_FC_DIR"], LIBNAME))
            ret = original_load_library(fpath)
        else:
            try:
                ret = original_load_library(LIBNAME)
            except FileNotFoundError:
                bloc = inkex.inkscape_system_info.binary_location  # type: ignore
                blocdir = os.path.dirname(bloc)
                fpath = os.path.abspath(os.path.join(blocdir, LIBNAME))
                ret = original_load_library(fpath)
        return ret
    elif name == "libc.so.6":
        # Do not need to load, return a blank class consistent with fontconfig
        libc = type("libc", (object,), {"free": staticmethod(lambda ptr: None)})()
        libc.free.argtypes = (ctypes.c_void_p,)
        return libc
    else:
        return original_load_library(name)


with patch("ctypes.cdll.LoadLibrary", side_effect=custom_load_library):
    try:
        import fontconfig as fc
    except ModuleNotFoundError:
        import inkex.text.packages.python_fontconfig.fontconfig as fc  # type: ignore
    FC = fc.FC


class FontConfig:
    def __init__(self):
        self.truefonts = dict()  # css
        self.truefontsfc = dict()  # fontconfig
        self.truefontsft = dict()  # fonttools
        self.fontcharsets = dict()
        self.disable_lcctype()
        self.conf = fc.Config.get_current()

    # MacOS can throw a warning if LC_CTYPE not disabled
    def disable_lcctype(self):
        self.lcctype = os.environ.get("LC_CTYPE")
        if self.lcctype is not None and sys.platform == "darwin":
            del os.environ["LC_CTYPE"]  # suppress Mac warning

    # Not actually needed since env vars won't persist
    def enable_lcctype(self):
        if self.lcctype is not None and sys.platform == "darwin":
            os.environ["LC_CTYPE"] = self.lcctype

    def get_true_font(self, reducedsty):
        """Use fontconfig to get the true font that most text will be rendered as"""
        nftuple = tuple(reducedsty.items())  # for hashing
        if nftuple not in self.truefonts:
            pat = self.css_to_fcpattern(reducedsty)

            self.conf.substitute(pat, FC.MatchPattern)
            pat.default_substitute()
            found, status = self.conf.font_match(pat)
            truefont = self.fcfont_to_css(found)

            if truefont not in self.font_list_css:
                # font_match rarely returns missing fonts, usually variable-weight
                # fonts where not all are installed. In that case, use the fallback
                # font_match method
                found, total_coverage, status = self.conf.font_sort(
                    pat, trim=True, want_coverage=False
                )
                found = found[0]
                truefont = self.fcfont_to_css(found)

            self.truefonts[nftuple] = truefont
            self.truefontsfc[nftuple] = found
            self.fontcharsets[tuple(truefont.items())] = found.get(fc.PROP.CHARSET, 0)[
                0
            ]
        return self.truefonts[nftuple]

    def get_true_font_by_char(self, reducedsty, chars):
        """
        Sometimes, a font will not have every character and a different one is
        substituted. (For example, many fonts do not have the ⎣ character.)
        Gets the true font by character
        """
        nftuple = tuple(reducedsty.items())
        if nftuple in self.truefonts:
            truefont = self.truefonts[nftuple]
            d = {
                k: truefont
                for k in chars
                if ord(k) in self.fontcharsets[tuple(truefont.items())]
            }
        else:
            d = {}

        if len(d) < len(chars):
            pat = self.css_to_fcpattern(reducedsty)
            self.conf.substitute(pat, FC.MatchPattern)
            pat.default_substitute()

            found, total_coverage, status = self.conf.font_sort(
                pat, trim=True, want_coverage=False
            )
            for f in found:
                truefont = self.fcfont_to_css(f)
                cs = f.get(fc.PROP.CHARSET, 0)[0]
                self.fontcharsets[tuple(truefont.items())] = cs
                d2 = {k: truefont for k in chars if ord(k) in cs and k not in d}
                d.update(d2)
                if len(d) == len(chars):
                    break
            if len(d) < len(chars):
                d.update({c: None for c in chars if c not in d})
        return d

    def get_fonttools_font(self, reducedsty):
        nftuple = tuple(reducedsty.items())  # for hashing
        if nftuple not in self.truefontsft:
            if nftuple not in self.truefontsfc:
                self.get_true_font(reducedsty)
            found = self.truefontsfc[nftuple]
            self.truefontsft[nftuple] = FontTools_FontInstance(found)
        return self.truefontsft[nftuple]

    def css_to_fcpattern(self, sty):
        """Convert a style dictionary to an fc search pattern"""
        pat = fc.Pattern.name_parse(
            re.escape(sty["font-family"].replace("'", "").replace('"', ""))
        )
        pat.add(
            fc.PROP.WIDTH,
            C.CSSSTR_FCWDT.get(sty.get("font-stretch"), FC.WIDTH_NORMAL),
        )
        pat.add(
            fc.PROP.WEIGHT,
            C.CSSWGT_FCWGT.get(sty.get("font-weight"), FC.WEIGHT_NORMAL),
        )
        pat.add(
            fc.PROP.SLANT, C.CSSSTY_FCSLN.get(sty.get("font-style"), FC.SLANT_ROMAN)
        )
        return pat

    def fcfont_to_css(self, f):
        """Convert an fc font to a Style"""
        # For CSS, enclose font family in single quotes
        # Needed for fonts like Modern No. 20 with periods in the family
        fcfam = f.get(fc.PROP.FAMILY, 0)[0]
        fcwgt = f.get(fc.PROP.WEIGHT, 0)[0]
        fcsln = f.get(fc.PROP.SLANT, 0)[0]
        fcwdt = f.get(fc.PROP.WIDTH, 0)[0]
        if any([isinstance(v, tuple) for v in [fcfam, fcwgt, fcsln, fcwdt]]):
            return None
        else:
            return Style(
                [
                    ("font-family", "'" + fcfam.strip("'") + "'"),
                    ("font-weight", nearest_val(C.FCWGT_CSSWGT, fcwgt)),
                    ("font-style", C.FCSLN_CSSSTY[fcsln]),
                    ("font-stretch", nearest_val(C.FCWDT_CSSSTR, fcwdt)),
                ]
            )

    @property
    def font_list(self):
        """Finds all fonts known to FontConfig"""
        if not hasattr(self, "_font_list"):
            pattern = fc.Pattern.create()  # blank pattern
            properties = ["family", "weight", "slant", "width", "style", "file"]
            # style is a nice name for the weight/slant/width combo
            # e.g., Arial Narrow Bold
            self._font_list = self.conf.font_list(pattern, properties)
            self._font_list = sorted(
                self._font_list, key=lambda x: x.get("family", 0)[0]
            )  # Sort by family
        return self._font_list

    @property
    def font_list_css(self):
        """Finds all fonts known to FontConfig in css form"""
        if not hasattr(self, "_font_list_css"):
            self._font_list_css = [self.fcfont_to_css(f) for f in self.font_list]
        return self._font_list_css


fcfg = FontConfig()
fontatt = ["font-family", "font-weight", "font-style", "font-stretch"]
dfltatt = [(k, default_style_atts[k]) for k in fontatt]
from functools import lru_cache


@lru_cache(maxsize=None)
def font_style(sty):
    """
    Given a CSS style, return a style that has the four attributes
    that matter for font selection
    Note that Inkscape may not draw this font if it is not present on the system.
    The family can have multiple comma-separated values, used for fallback
    """
    sty2 = Style(dfltatt)
    sty2.update({k: v for k, v in sty.items() if k in fontatt})
    sty2["font-family"] = ",".join(
        ["'" + v.strip('"').strip("'") + "'" for v in sty2["font-family"].split(",")]
    )
    return sty2


@lru_cache(maxsize=None)
def true_style(sty):
    """
    Given a CSS style, return a style with the actual font that
    fontconfig selected. This is the actual font that Inkscape will draw.
    """
    sty2 = font_style(sty)
    tf = fcfg.get_true_font(sty2)
    return tf


def nearest_val(dictv, inputval):
    """Return the value of a dict whose key is closest to the input value"""
    return dictv[min(dictv.keys(), key=lambda x: abs(x - inputval))]


# The Pango library is only available starting with v1.1 (when Inkscape added
# the Python bindings for the gtk library).
with warnings.catch_warnings():
    # Ignore ImportWarning for Gtk/Pango
    warnings.simplefilter("ignore")

    haspango = False
    haspangoFT2 = False
    pangoenv = os.environ.get("USEPANGO", "")
    if not (pangoenv == "False"):
        try:
            import platform

            if platform.system().lower() == "windows":
                # Windows may not have all of the typelibs needed for PangoFT2
                # Add the typelibs subdirectory as a fallback option
                bloc = inkex.inkscape_system_info.binary_location  # type: ignore
                girepo = os.path.join(
                    os.path.dirname(os.path.dirname(bloc)),
                    "lib",
                    "girepository-1.0",
                )  # Inkscape's GI repository
                if os.path.isdir(girepo):
                    tlibs = [
                        "fontconfig-2.0.typelib",
                        "PangoFc-1.0.typelib",
                        "PangoFT2-1.0.typelib",
                        "freetype2-2.0.typelib",
                    ]
                    # If any typelibs are missing, try adding the typelibs subdirectory
                    if any(
                        [not (os.path.exists(os.path.join(girepo, t))) for t in tlibs]
                    ):
                        tlibsub = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)), "typelibs"
                        )
                        for newpath in [girepo, tlibsub]:
                            # gi looks in the order specified in GI_TYPELIB_PATH
                            cval = os.environ.get("GI_TYPELIB_PATH", "")
                            if cval == "":
                                os.environ["GI_TYPELIB_PATH"] = newpath
                            elif newpath not in cval:
                                os.environ["GI_TYPELIB_PATH"] = (
                                    cval + os.pathsep + newpath
                                )
                # Windows doesn't have the XDG_DATA_HOME directory set, which is
                # needed for /etc/fonts.conf to find the user fonts directory:
                #   <dir prefix="xdg">fonts</dir>
                # Set it based on the location of preferences.xml
                if os.environ.get("XDG_DATA_HOME") is None:
                    os.environ["XDG_DATA_HOME"] = os.path.dirname(
                        inkex.inkscape_system_info.find_preferences()  # type: ignore
                    )

            import gi

            gi.require_version("Gtk", "3.0")
            # from gi.repository import GLib  # only needed by _none
            from gi.repository import Pango

            Pango.Variant.NORMAL  # make sure this exists
            haspango = True
        except:
            haspango = False

        if haspango:
            try:
                # May require some typelibs we do not have
                gi.require_version("PangoFT2", "1.0")
                from gi.repository import PangoFT2

                haspangoFT2 = True
            except:
                haspangoFT2 = False
                from gi.repository import Gdk

if pangoenv in ["True", "False"]:
    os.environ["HASPANGO"] = str(haspango)
    os.environ["HASPANGOFT2"] = str(haspangoFT2)
    with open("env_vars.txt", "w") as f:
        f.write(f"HASPANGO={os.environ['HASPANGO']}")
        f.write(f"\nHASPANGOFT2={os.environ['HASPANGOFT2']}")


class PangoRenderer:
    def __init__(self):
        self.PANGOSIZE = 1024 * 4
        # size of text to render. 1024 is good

        if haspangoFT2:
            self.ctx = Pango.Context.new()
            self.ctx.set_font_map(PangoFT2.FontMap.new())
        else:
            self.ctx = Gdk.pango_context_get()
        self.pangolayout = Pango.Layout(self.ctx)
        self.pufd = Pango.units_from_double
        self.putd = Pango.units_to_double
        self.scale = Pango.SCALE

    def css_to_pango(self, sty, key):
        val = sty.get(key)
        if key == "font-weight":
            return C.CSSWGT_PWGT.get(val, Pango.Weight.NORMAL)
        elif key == "font-style":
            return C.CSSSTY_PSTY.get(val, Pango.Style.NORMAL)
        elif key == "font-stretch":
            return C.CSSSTR_PSTR.get(val, Pango.Stretch.NORMAL)
        elif key == "font-variant":
            return C.CSSVAR_PVAR.get(val, Pango.Variant.NORMAL)
        return None

    def css_to_pango_description(self, sty):
        from gi.repository import Pango

        fd = Pango.FontDescription(sty["font-family"].strip("'").strip('"') + ",")
        # The comma above is very important for font-families like Rockwell Condensed.
        # Without it, Pango will interpret it as the Condensed font-stretch of the Rockwell font-family,
        # rather than the Rockwell Condensed font-family.
        fd.set_weight(C.CSSWGT_PWGT.get(sty.get("font-weight"), Pango.Weight.NORMAL))
        fd.set_variant(C.CSSVAR_PVAR.get(sty.get("font-variant"), Pango.Variant.NORMAL))
        fd.set_style(C.CSSSTY_PSTY.get(sty.get("font-style"), Pango.Style.NORMAL))
        fd.set_stretch(C.CSSSTR_PSTR.get(sty.get("font-stretch"), Pango.Stretch.NORMAL))
        return fd

    def pango_to_fc(self, pstretch, pweight, pstyle):
        fcwidth = C.PSTR_FCWDT[pstretch]
        fcweight = C.PWGT_FCWGT[pweight]
        fcslant = C.PSTY_FCSLN[pstyle]
        return fcwidth, fcweight, fcslant

    def pango_to_css(self, pdescription):
        fd = pdescription

        def isnumeric(s):
            try:
                float(s)
                return True
            except ValueError:
                return False

        cs = [k for k, v in C.CSSSTR_PSTR.items() if v == fd.get_stretch()]
        cw = [
            k for k, v in C.CSSWGT_PWGT.items() if v == fd.get_weight() and isnumeric(k)
        ]
        csty = [k for k, v in C.CSSSTY_PSTY.items() if v == fd.get_style()]

        s = (("font-family", fd.get_family()),)
        if len(cw) > 0:
            s += (("font-weight", cw[0]),)
        if len(csty) > 0:
            s += (("font-style", csty[0]),)
        if len(cs) > 0:
            s += (("font-stretch", cs[0]),)
        return Style(s)

    @property
    def families(self):
        if not hasattr(self, "_families"):
            families = self.ctx.get_font_map().list_families()
            self._families = sorted(
                families, key=lambda x: x.get_name()
            )  # Sort families alphabetically
        return self._families

    @property
    def faces(self):
        if not hasattr(self, "_faces"):
            self._faces = [fc for fm in self.families for fc in fm.list_faces()]
        return self._faces

    @property
    def face_descriptions(self):
        if not hasattr(self, "_face_descriptions"):
            self._face_descriptions = [fc.describe() for fc in self.faces]
        return self._face_descriptions

    @property
    def face_strings(self):
        if not hasattr(self, "_face_strings"):
            self._face_strings = [fd.to_string() for fd in self.face_descriptions]
        return self._face_strings

    @property
    def face_css(self):
        if not hasattr(self, "_face_css"):
            self._face_css = [self.pango_to_css(fd) for fd in self.face_descriptions]
        return self._face_css

    def fc_match_pango(self, family, pstretch, pweight, pstyle):
        """Look up a font by its Pango properties"""
        pat = fc.Pattern.name_parse(re.escape(family.replace("'", "").replace('"', "")))
        fcwidth, fcweight, fcslant = self.pango_to_fc(pstretch, pweight, pstyle)
        pat.add(fc.PROP.WIDTH, fcwidth)
        pat.add(fc.PROP.WEIGHT, fcweight)
        pat.add(fc.PROP.SLANT, fcslant)

        self.conf.substitute(pat, FC.MatchPattern)
        pat.default_substitute()
        found, status = self.conf.font_match(pat)
        return found

    def Set_Text_Style(self, stystr):
        sty2 = stystr.split(";")
        sty2 = {s.split(":")[0]: s.split(":")[1] for s in sty2}

        msty = fontatt + ["font-variant"]  # mandatory style
        for m in msty:
            if m not in sty2:
                sty2[m] = default_style_atts[m]

        fd = self.css_to_pango_description(sty2)
        fd.set_absolute_size(self.pufd(self.PANGOSIZE))
        fnt = self.ctx.get_font_map().load_font(self.ctx, fd)

        if not (haspangoFT2):
            success = fnt is not None
        else:
            success = fnt is not None
            # PangoFT2 sometimes gives mysterious errors that are actually fine

        if success:
            self.pangolayout.set_font_description(fd)
            fm = fnt.get_metrics()
            fm = [
                self.putd(v) / self.PANGOSIZE
                for v in [fm.get_height(), fm.get_ascent(), fm.get_descent()]
            ]
            return success, fm
        else:
            return success, None

    def Render_Text(self, texttorender):
        self.pangolayout.set_text(texttorender, -1)

    def process_extents(self, ext, ascent):
        """
        Scale extents and return extents as standard bboxes
        (0:logical, 1:ink, 2: ink relative to anchor/baseline)
        """
        lr = ext.logical_rect
        lr = [self.putd(v) / self.PANGOSIZE for v in [lr.x, lr.y, lr.width, lr.height]]
        ir = ext.ink_rect
        ir = [self.putd(v) / self.PANGOSIZE for v in [ir.x, ir.y, ir.width, ir.height]]
        ir_rel = [ir[0] - lr[0], ir[1] - lr[1] - ascent, ir[2], ir[3]]
        return lr, ir, ir_rel

    def Get_Character_Extents(self, ascent, needexts):
        """
        Iterate through the layout to get the logical width of each character
        If there is differential kerning applied, it is applied to the
        width of the first character. For example, the 'V' in 'Voltage'
        will be thinner due to the 'o' that follows.
        Units: relative to font size
        """
        loi = self.pangolayout.get_iter()
        ws = []
        ii = -1
        lastpos = True
        unwrapper = 0
        moved = True
        while moved:
            ce = loi.get_cluster_extents()
            ii += 1
            if needexts[ii] == "1":
                ext = self.process_extents(ce, ascent)
                if ext[0][0] < 0 and lastpos:
                    unwrapper += 2**32 / (self.scale * self.PANGOSIZE)
                lastpos = ext[0][0] >= 0
                ext[0][0] += unwrapper  # account for 32-bit overflow
                ext[1][0] += unwrapper
                ws.append(ext)
            else:
                ws.append(None)
            moved = loi.next_char()

        numunknown = self.pangolayout.get_unknown_glyphs_count()
        return ws, numunknown


class FontTools_FontInstance:
    def __init__(self, fcfont):
        self.font = self.font_from_fc(fcfont)
        self.head = self.font["head"]
        self.os2 = self.font["OS/2"] if "OS/2" in self.font else None
        self.find_font_metrics()

    # Find a FontTools font from a found FontConfig font
    def font_from_fc(self, found):
        fname = found.get(fc.PROP.FILE, 0)[0]

        try:
            from fontTools.ttLib import TTFont
        except ModuleNotFoundError:
            current_script_directory = os.path.dirname(os.path.abspath(__file__))
            sys.path += [os.path.join(current_script_directory, "packages")]
            from fontTools.ttLib import TTFont
        import logging

        logging.getLogger("fontTools").setLevel(logging.ERROR)

        try:
            font = TTFont(fname)

            # If font has variants, get them
            if "fvar" in font:
                fcwgt = found.get(fc.PROP.WEIGHT, 0)[0]
                fcsln = found.get(fc.PROP.SLANT, 0)[0]
                fcwdt = found.get(fc.PROP.WIDTH, 0)[0]
                location = dict()
                for axis in font["fvar"].axes:
                    if axis.axisTag == "wght":
                        location["wght"] = nearest_val(C.FCWGT_OS2WGT, fcwgt)
                    elif axis.axisTag == "wdth":
                        location["wdth"] = fcwdt
                if len(location) > 0:
                    from fontTools.varLib import mutator

                    font = mutator.instantiateVariableFont(font, location)

        except:
            # fcfam = found.get(fc.PROP.FAMILY,0)[0]
            fcwgt = found.get(fc.PROP.WEIGHT, 0)[0]
            fcsln = found.get(fc.PROP.SLANT, 0)[0]
            fcwdt = found.get(fc.PROP.WIDTH, 0)[0]

            from fontTools.ttLib import TTCollection

            collection = TTCollection(fname)
            num_fonts = len(collection)
            collection.close()
            num_match = []
            for i in range(num_fonts):
                tfont = TTFont(fname, fontNumber=i)
                font_weight = tfont["OS/2"].usWeightClass
                font_width = tfont["OS/2"].usWidthClass

                subfamily = tfont["name"].getName(2, 3, 1, 1033)
                subfamily = (
                    subfamily.toUnicode() if subfamily is not None else "Unknown"
                )
                font_italic = (
                    (tfont["OS/2"].fsSelection & 1) != 0
                    or "italic" in subfamily.lower()
                    or "oblique" in subfamily.lower()
                )

                matches = [
                    nearest_val(C.OS2WGT_FCWGT, font_weight) == fcwgt,
                    C.OS2WDT_FCWDT[font_width] == fcwdt,
                    (
                        (font_italic and fcsln in [FC.SLANT_ITALIC, FC.SLANT_OBLIQUE])
                        or (not font_italic and fcsln == FC.SLANT_ROMAN)
                    ),
                ]
                num_match.append(sum(matches))
                if num_match[-1] == 3:
                    font = tfont
                    break
            if max(num_match) < 3:
                # Did not find a perfect match
                font = [
                    TTFont(fname, fontNumber=i)
                    for i in range(num_fonts)
                    if num_match[i] == max(num_match)
                ][0]
        return font

    def find_font_metrics(self):
        """
        A modified version of Inkscape's find_font_metrics
        https://gitlab.com/inkscape/inkscape/-/blob/master/src/libnrtype/font-instance.cpp#L267
        Uses FontTools, which is Pythonic
        """
        font = self.font
        unitsPerEm = self.head.unitsPerEm
        os2 = self.os2
        if os2:
            self._ascent = abs(os2.sTypoAscender / unitsPerEm)
            self._descent = abs(os2.sTypoDescender / unitsPerEm)
        else:
            self._ascent = abs(font["hhea"].ascent / unitsPerEm)
            self._descent = abs(font["hhea"].descent / unitsPerEm)
        self._ascent_max = abs(font["hhea"].ascent / unitsPerEm)
        self._descent_max = abs(font["hhea"].descent / unitsPerEm)
        self._design_units = unitsPerEm
        em = self._ascent + self._descent
        if em > 0.0:
            self._ascent /= em
            self._descent /= em

        if os2 and os2.version >= 0x0002 and os2.version != 0xFFFF:
            self._xheight = abs(os2.sxHeight / unitsPerEm)
        else:
            glyph_set = font.getGlyphSet()
            self._xheight = (
                abs(glyph_set["x"].height / unitsPerEm)
                if "x" in glyph_set and glyph_set["x"].height is not None
                else 0.5
            )
        self._baselines = [0] * 8
        self.SP_CSS_BASELINE_IDEOGRAPHIC = 0
        self.SP_CSS_BASELINE_HANGING = 1
        self.SP_CSS_BASELINE_MATHEMATICAL = 2
        self.SP_CSS_BASELINE_CENTRAL = 3
        self.SP_CSS_BASELINE_MIDDLE = 4
        self.SP_CSS_BASELINE_TEXT_BEFORE_EDGE = 5
        self.SP_CSS_BASELINE_TEXT_AFTER_EDGE = 6
        self.SP_CSS_BASELINE_ALPHABETIC = 7
        self._baselines[self.SP_CSS_BASELINE_IDEOGRAPHIC] = -self._descent
        self._baselines[self.SP_CSS_BASELINE_HANGING] = 0.8 * self._ascent
        self._baselines[self.SP_CSS_BASELINE_MATHEMATICAL] = 0.8 * self._xheight
        self._baselines[self.SP_CSS_BASELINE_CENTRAL] = 0.5 - self._descent
        self._baselines[self.SP_CSS_BASELINE_MIDDLE] = 0.5 * self._xheight
        self._baselines[self.SP_CSS_BASELINE_TEXT_BEFORE_EDGE] = self._ascent
        self._baselines[self.SP_CSS_BASELINE_TEXT_AFTER_EDGE] = -self._descent

        # Get capital height
        if os2 and hasattr(os2, "sCapHeight") and os2.sCapHeight not in [0, None]:
            self.cap_height = os2.sCapHeight / unitsPerEm
        elif "glyf" in font and "I" in font.getGlyphNames():
            glyf_table = font["glyf"]
            i_glyph = glyf_table["I"]
            self.cap_height = (i_glyph.yMax - 0 * i_glyph.yMin) / unitsPerEm
        else:
            self.cap_height = 1

    def get_char_advances(self, chars, pchars):
        unitsPerEm = self.head.unitsPerEm
        if not hasattr(self, "cmap"):
            self.cmap = self.font.getBestCmap()
        if not hasattr(self, "htmx"):
            self.hmtx = self.font["hmtx"]
        if not hasattr(self, "kern"):
            self.kern = self.font["kern"] if "kern" in self.font else None
        if not hasattr(self, "GSUB"):
            self.gsub = self.font["GSUB"] if "GSUB" in self.font else None
        if not hasattr(self, "glyf"):
            self.glyf = self.font["glyf"] if "glyf" in self.font else None
        if not hasattr(self, "GlyphNames"):
            self.GlyphNames = self.font.getGlyphNames()

        if self.cmap is None:
            # Certain symbol fonts don't have a cmap table
            return None, None, None

        advs = dict()
        bbs = dict()
        for c in chars:
            glyph1 = self.cmap.get(ord(c))
            if glyph1 is not None:
                if glyph1 in self.hmtx.metrics:
                    advance_width, lsb = self.hmtx.metrics[glyph1]
                    advs[c] = advance_width / unitsPerEm

                try:
                    glyph = self.glyf[glyph1]
                    bb = [
                        glyph.xMin,
                        -glyph.yMax,
                        glyph.xMax - glyph.xMin,
                        glyph.yMax - glyph.yMin,
                    ]
                    bbs[c] = [v / unitsPerEm for v in bb]
                except:
                    bbs[c] = [0, 0, 0, 0]
            else:
                advs[c] = None

        # Get ligature table
        if not hasattr(self, "ligatures"):
            if self.gsub:
                gsub_table = self.gsub.table
                # Iterate over each LookupList in the GSUB table
                self.ligatures = dict()
                for lookup_index, lookup in enumerate(gsub_table.LookupList.Lookup):
                    # Each Lookup can contain multiple SubTables
                    for subtable_index, subtable in enumerate(lookup.SubTable):
                        # Handle extension lookups
                        if (
                            lookup.LookupType == 7
                        ):  # 7 is the Lookup type for Extension Substitutions
                            ext_subtable = subtable.ExtSubTable
                            lookup_type = ext_subtable.LookupType
                        else:
                            ext_subtable = subtable
                            lookup_type = lookup.LookupType

                        # We're only interested in ligature substitutions
                        if (
                            lookup_type == 4
                        ):  # 4 is the Lookup type for Ligature Substitutions
                            # Each subtable can define substitutions for multiple glyphs
                            for (
                                first_glyph,
                                ligature_set,
                            ) in ext_subtable.ligatures.items():
                                # The ligature set contains all ligatures that start with the first glyph
                                # Each ligature is a sequence of glyphs that it replaces
                                for ligature in ligature_set:
                                    # The 'Component' field is a list of glyphs that make up the ligature
                                    component_glyphs = [
                                        first_glyph
                                    ] + ligature.Component
                                    # The 'LigGlyph' field is the glyph that the components are replaced with
                                    ligature_glyph = ligature.LigGlyph
                                    self.ligatures[tuple(component_glyphs)] = (
                                        ligature_glyph
                                    )
            else:
                self.ligatures = dict()

        dadvs = dict()
        for c in pchars:
            glyph2 = self.cmap.get(ord(c))
            for pc in pchars[c]:
                glyph1 = self.cmap.get(ord(pc))
                kerning_value = None
                if (glyph1, glyph2) in self.ligatures:
                    ligglyph = self.ligatures[(glyph1, glyph2)]
                    awlig, lsb = self.hmtx.metrics[ligglyph]
                    aw1, lsb = self.hmtx.metrics[glyph1]
                    aw2, lsb = self.hmtx.metrics[glyph2]
                    kerning_value = awlig - aw1 - aw2
                else:
                    if self.kern is not None:
                        for subtable in self.kern.kernTables:
                            kerning_value = subtable.kernTable.get((glyph1, glyph2))
                            if kerning_value is not None:
                                break
                if kerning_value is None:
                    kerning_value = 0
                dadvs[(pc, c)] = kerning_value / unitsPerEm
        return advs, dadvs, bbs


class Conversions:
    """
    Conversions between CSS, FontConfig, Pango, and OS2 font attributes
    CSS:        font-weight, font-style, font-stretch
    FontConfig: weight,      slant,      width
    Pango:      weight,      style,      stretch
    OS2:        weight,      width,

    Inkscape conventions in libnrtype/font-factory.cpp
    https://gitlab.com/inkscape/inkscape/-/blob/master/src/libnrtype/font-factory.cpp
    """

    # CSS to fontconfig
    # For weights, Inkscape ignores anything commented out below
    # See ink_font_description_from_style in libnrtype/font-factory.cpp
    CSSWGT_FCWGT = {
        # 'thin'      : FC.WEIGHT_THIN,
        # 'ultralight': FC.WEIGHT_EXTRALIGHT,
        # 'light'     : FC.WEIGHT_LIGHT,
        # 'semilight' : FC.WEIGHT_SEMILIGHT,
        # 'book'      : FC.WEIGHT_BOOK,
        "normal": FC.WEIGHT_NORMAL,
        # 'medium'    : FC.WEIGHT_MEDIUM,
        # 'semibold'  : FC.WEIGHT_SEMIBOLD,
        "bold": FC.WEIGHT_BOLD,
        # 'ultrabold' : FC.WEIGHT_ULTRABOLD,
        # 'heavy'     : FC.WEIGHT_HEAVY,
        # 'ultraheavy': FC.WEIGHT_ULTRABLACK,
        "100": FC.WEIGHT_THIN,
        "200": FC.WEIGHT_EXTRALIGHT,
        "300": FC.WEIGHT_LIGHT,
        # '350'       : FC.WEIGHT_SEMILIGHT,
        # '380'       : FC.WEIGHT_BOOK,
        "400": FC.WEIGHT_NORMAL,
        "500": FC.WEIGHT_MEDIUM,
        "600": FC.WEIGHT_SEMIBOLD,
        "700": FC.WEIGHT_BOLD,
        "800": FC.WEIGHT_ULTRABOLD,
        "900": FC.WEIGHT_HEAVY,
        # '1000'      : FC.WEIGHT_ULTRABLACK
    }

    CSSSTY_FCSLN = {
        "normal": FC.SLANT_ROMAN,
        "italic": FC.SLANT_ITALIC,
        "oblique": FC.SLANT_OBLIQUE,
    }

    CSSSTR_FCWDT = {
        "ultra-condensed": FC.WIDTH_ULTRACONDENSED,
        "extra-condensed": FC.WIDTH_EXTRACONDENSED,
        "condensed": FC.WIDTH_CONDENSED,
        "semi-condensed": FC.WIDTH_SEMICONDENSED,
        "normal": FC.WIDTH_NORMAL,
        "semi-expanded": FC.WIDTH_SEMIEXPANDED,
        "expanded": FC.WIDTH_EXPANDED,
        "extra-expanded": FC.WIDTH_EXTRAEXPANDED,
        "ultra-expanded": FC.WIDTH_ULTRAEXPANDED,
    }

    # Fontconfig to CSS
    # Semi-Light, Book, and Ultra-Black are mapped to Light, Normal, Heavy
    # See FontFactory::GetUIStyles in libnrtype/font-factory.cpp
    FCWGT_CSSWGT = {
        FC.WEIGHT_THIN: "100",
        FC.WEIGHT_EXTRALIGHT: "200",
        FC.WEIGHT_LIGHT: "300",
        # FC.WEIGHT_SEMILIGHT  : '350',
        FC.WEIGHT_SEMILIGHT: "300",
        # FC.WEIGHT_BOOK       : '380',
        FC.WEIGHT_BOOK: "400",
        FC.WEIGHT_NORMAL: "400",
        FC.WEIGHT_MEDIUM: "500",
        FC.WEIGHT_SEMIBOLD: "600",
        FC.WEIGHT_BOLD: "700",
        FC.WEIGHT_ULTRABOLD: "800",
        FC.WEIGHT_HEAVY: "900",
        # FC.WEIGHT_ULTRABLACK : '1000',
        FC.WEIGHT_ULTRABLACK: "900",
    }
    FCSLN_CSSSTY = {
        FC.SLANT_ROMAN: "normal",
        FC.SLANT_ITALIC: "italic",
        FC.SLANT_OBLIQUE: "oblique",
    }
    FCWDT_CSSSTR = {
        FC.WIDTH_ULTRACONDENSED: "ultra-condensed",
        FC.WIDTH_EXTRACONDENSED: "extra-condensed",
        FC.WIDTH_CONDENSED: "condensed",
        FC.WIDTH_SEMICONDENSED: "semi-condensed",
        FC.WIDTH_NORMAL: "normal",
        FC.WIDTH_SEMIEXPANDED: "semi-expanded",
        FC.WIDTH_EXPANDED: "expanded",
        FC.WIDTH_EXTRAEXPANDED: "extra-expanded",
        FC.WIDTH_ULTRAEXPANDED: "ultra-expanded",
    }

    # Pango style string description to CSS
    # Needed for matching the name of styles shown in Inkscape
    PWGTSTR_CSSWGT = {
        "Ultra-Light": "200",
        "Light": "300",
        "Semi-Light": "350",
        "Medium": "500",
        "Semi-Bold": "600",
        "Bold": "bold",
        "Ultra-Bold": "800",
        "Heavy": "900",
        "Normal": "normal",
        "Book": "380",
        "Thin": "100",
        "Ultra-Heavy": "1000",
    }
    PSTRSTR_CSSSTR = {
        "Ultra-Condensed": "ultra-condensed",
        "Extra-Condensed": "extra-condensed",
        "Condensed": "condensed",
        "Semi-Condensed": "semi-condensed",
        "Normal": "normal",
        "Semi-Expanded": "semi-expanded",
        "Expanded": "expanded",
        "Extra-Expanded": "extra-expanded",
        "Ultra-Expanded": "ultra-expanded",
    }
    PSTYSTR_CSSSTY = {
        "Italic": "italic",
        "Oblique": "oblique",
        "Normal": "normal",
    }

    # FC to OS2 and OS2 to FC
    FCWGT_OS2WGT = {
        FC.WEIGHT_THIN: 100,
        FC.WEIGHT_EXTRALIGHT: 200,
        FC.WEIGHT_LIGHT: 300,
        FC.WEIGHT_SEMILIGHT: 350,
        FC.WEIGHT_BOOK: 380,
        FC.WEIGHT_NORMAL: 400,
        FC.WEIGHT_MEDIUM: 500,
        FC.WEIGHT_SEMIBOLD: 600,
        FC.WEIGHT_BOLD: 700,
        FC.WEIGHT_ULTRABOLD: 800,
        FC.WEIGHT_HEAVY: 900,
        FC.WEIGHT_ULTRABLACK: 1000,
    }
    OS2WDT_FCWDT = {
        1: FC.WIDTH_ULTRACONDENSED,
        2: FC.WIDTH_EXTRACONDENSED,
        3: FC.WIDTH_CONDENSED,
        4: FC.WIDTH_SEMICONDENSED,
        5: FC.WIDTH_NORMAL,
        6: FC.WIDTH_SEMIEXPANDED,
        7: FC.WIDTH_EXPANDED,
        8: FC.WIDTH_EXTRAEXPANDED,
        9: FC.WIDTH_ULTRAEXPANDED,
    }
    OS2WGT_FCWGT = {
        100: FC.WEIGHT_THIN,
        200: FC.WEIGHT_EXTRALIGHT,
        300: FC.WEIGHT_LIGHT,
        350: FC.WEIGHT_SEMILIGHT,
        380: FC.WEIGHT_BOOK,
        400: FC.WEIGHT_NORMAL,
        500: FC.WEIGHT_MEDIUM,
        600: FC.WEIGHT_SEMIBOLD,
        700: FC.WEIGHT_BOLD,
        800: FC.WEIGHT_ULTRABOLD,
        900: FC.WEIGHT_HEAVY,
        1000: FC.WEIGHT_ULTRABLACK,
    }

    if haspango:
        # Pango to fontconfig
        PWGT_FCWGT = {
            Pango.Weight.THIN: FC.WEIGHT_THIN,
            Pango.Weight.ULTRALIGHT: FC.WEIGHT_ULTRALIGHT,
            Pango.Weight.ULTRALIGHT: FC.WEIGHT_EXTRALIGHT,
            Pango.Weight.LIGHT: FC.WEIGHT_LIGHT,
            Pango.Weight.SEMILIGHT: FC.WEIGHT_DEMILIGHT,
            Pango.Weight.SEMILIGHT: FC.WEIGHT_SEMILIGHT,
            Pango.Weight.BOOK: FC.WEIGHT_BOOK,
            Pango.Weight.NORMAL: FC.WEIGHT_REGULAR,
            Pango.Weight.NORMAL: FC.WEIGHT_NORMAL,
            Pango.Weight.MEDIUM: FC.WEIGHT_MEDIUM,
            Pango.Weight.SEMIBOLD: FC.WEIGHT_DEMIBOLD,
            Pango.Weight.SEMIBOLD: FC.WEIGHT_SEMIBOLD,
            Pango.Weight.BOLD: FC.WEIGHT_BOLD,
            Pango.Weight.ULTRABOLD: FC.WEIGHT_EXTRABOLD,
            Pango.Weight.ULTRABOLD: FC.WEIGHT_ULTRABOLD,
            Pango.Weight.HEAVY: FC.WEIGHT_BLACK,
            Pango.Weight.HEAVY: FC.WEIGHT_HEAVY,
            Pango.Weight.ULTRAHEAVY: FC.WEIGHT_EXTRABLACK,
            Pango.Weight.ULTRAHEAVY: FC.WEIGHT_ULTRABLACK,
        }

        PSTY_FCSLN = {
            Pango.Style.NORMAL: FC.SLANT_ROMAN,
            Pango.Style.ITALIC: FC.SLANT_ITALIC,
            Pango.Style.OBLIQUE: FC.SLANT_OBLIQUE,
        }

        PSTR_FCWDT = {
            Pango.Stretch.ULTRA_CONDENSED: FC.WIDTH_ULTRACONDENSED,
            Pango.Stretch.EXTRA_CONDENSED: FC.WIDTH_EXTRACONDENSED,
            Pango.Stretch.CONDENSED: FC.WIDTH_CONDENSED,
            Pango.Stretch.SEMI_CONDENSED: FC.WIDTH_SEMICONDENSED,
            Pango.Stretch.NORMAL: FC.WIDTH_NORMAL,
            Pango.Stretch.SEMI_EXPANDED: FC.WIDTH_SEMIEXPANDED,
            Pango.Stretch.EXPANDED: FC.WIDTH_EXPANDED,
            Pango.Stretch.EXTRA_EXPANDED: FC.WIDTH_EXTRAEXPANDED,
            Pango.Stretch.ULTRA_EXPANDED: FC.WIDTH_ULTRAEXPANDED,
        }

        # CSS to Pango
        CSSVAR_PVAR = {
            "normal": Pango.Variant.NORMAL,
            "small-caps": Pango.Variant.SMALL_CAPS,
        }

        CSSSTY_PSTY = {
            "normal": Pango.Style.NORMAL,
            "italic": Pango.Style.ITALIC,
            "oblique": Pango.Style.OBLIQUE,
        }
        # For weights, Inkscape ignores anything commented out below
        # See ink_font_description_from_style in libnrtype/font-factory.cpp
        CSSWGT_PWGT = {
            # 'thin'       : Pango.Weight.THIN,
            # 'ultralight' : Pango.Weight.ULTRALIGHT,
            # 'light'      : Pango.Weight.LIGHT,
            # 'semilight'  : Pango.Weight.SEMILIGHT,
            # 'book'       : Pango.Weight.BOOK,
            "normal": Pango.Weight.NORMAL,
            # 'medium'     : Pango.Weight.MEDIUM,
            # 'semibold'   : Pango.Weight.SEMIBOLD,
            "bold": Pango.Weight.BOLD,
            # 'ultrabold'  : Pango.Weight.ULTRABOLD,
            # 'heavy'      : Pango.Weight.HEAVY,
            # 'ultraheavy' : Pango.Weight.ULTRAHEAVY,
            "100": Pango.Weight.THIN,
            "200": Pango.Weight.ULTRALIGHT,
            "300": Pango.Weight.LIGHT,
            # '350'        : Pango.Weight.SEMILIGHT,
            # '380'        : Pango.Weight.BOOK,
            "400": Pango.Weight.NORMAL,
            "500": Pango.Weight.MEDIUM,
            "600": Pango.Weight.SEMIBOLD,
            "700": Pango.Weight.BOLD,
            "800": Pango.Weight.ULTRABOLD,
            "900": Pango.Weight.HEAVY,
            # '1000'       : Pango.Weight.ULTRAHEAVY
        }
        CSSSTR_PSTR = {
            "ultra-condensed": Pango.Stretch.ULTRA_CONDENSED,
            "extra-condensed": Pango.Stretch.EXTRA_CONDENSED,
            "condensed": Pango.Stretch.CONDENSED,
            "semi-condensed": Pango.Stretch.SEMI_CONDENSED,
            "normal": Pango.Stretch.NORMAL,
            "semi-expanded": Pango.Stretch.SEMI_EXPANDED,
            "expanded": Pango.Stretch.EXPANDED,
            "extra-expanded": Pango.Stretch.EXTRA_EXPANDED,
            "ultra-expanded": Pango.Stretch.ULTRA_EXPANDED,
        }


C = Conversions


def inkscape_spec_to_css(fstr, usepango=False):
    """
    Look up a CSS style based on its Inkscape font specification, which is
    similar (identical?) to the Pango description's string representation.
    This function is meant to be forgiving, allowing a user to vary punctuation
    and capitalization, and tries to find a match in the system's families.
    It does NOT require Pango.
    """

    def clean_str(strin):
        ret = re.sub(r"[^\w\s]", "", strin)
        ret = re.sub(r"\s+", " ", ret)
        return ret.strip().lower()

    cstr = clean_str(fstr)
    if usepango and haspango:
        fullfams = [fm.get_name() for fm in PangoRenderer().families]
    else:
        fullfams = [f.get("family", 0)[0] for f in fcfg.font_list]
        fullfams += ["Serif", "Sans", "System-ui", "Monospace"]  # from Inkscape

    # Split the input into words and find the longest match to an installed
    # family at the beginning or end of the string
    fmnames = [clean_str(f) for f in fullfams]
    words = cstr.split()
    longest_match = ""
    match_length = 0
    match_type = None  # 'prefix' or 'suffix'
    # Check for the longest prefix match
    for i in range(1, len(words) + 1):
        current_match = " ".join(words[:i])
        if current_match in fmnames and len(current_match) > len(longest_match):
            longest_match = current_match
            match_length = i
            match_type = "prefix"
    # Check for the longest suffix match
    for i in range(1, len(words) + 1):
        current_match = " ".join(words[-i:])
        if current_match in fmnames and len(current_match) > len(longest_match):
            longest_match = current_match
            match_length = i
            match_type = "suffix"
    if longest_match:
        fam = fullfams[fmnames.index(longest_match)]
        if match_type == "prefix":
            stylews = words[match_length:]
        elif match_type == "suffix":
            stylews = words[:-match_length]
        if not stylews:
            stylews = None
    else:
        fam = None
        stylews = words

    sty = {}
    if fam:
        sty["font-family"] = fam
    if stylews:
        pwgtstrs = {clean_str(k): v for k, v in C.PWGTSTR_CSSWGT.items()}
        pstrstrs = {clean_str(k): v for k, v in C.PSTRSTR_CSSSTR.items()}
        pstystrs = {clean_str(k): v for k, v in C.PSTYSTR_CSSSTY.items()}
        for w in stylews:
            understood = False
            if w in pwgtstrs:
                sty["font-weight"] = pwgtstrs[w]
                understood = True
            elif "weight" in w:
                sty["font-weight"] = re.search(r"weight(\d+)", w).group(1)
                understood = True
            if w in pstystrs:
                sty["font-style"] = pstystrs[w]
                understood = True
            if w in pstrstrs:
                sty["font-stretch"] = pstrstrs[w]
                understood = True
            if not understood:
                return None
    sty = {key: sty[key] for key in fontatt if key in sty}  # order
    return sty
