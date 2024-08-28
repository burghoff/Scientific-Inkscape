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

import os
import warnings
import sys
import re
import ctypes
from unittest.mock import patch
from functools import lru_cache
import inkex
from inkex.text.utils import default_style_atts
from inkex import Style

# The fontconfig library is used to select a font given its CSS specs
# This library should work starting with v1.0

# Due to the way fontconfig is structured, we have to patch
# ctypes's LoadLibrary to help it find libfontconfig
original_load_library = ctypes.cdll.LoadLibrary


def custom_load_library(name):
    """
    Custom function to load a library based on the platform.
    """
    if name in ["libfontconfig.so.1", "libfreetype.so.6"]:
        libname = {
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
            fpath = os.path.abspath(os.path.join(os.environ["SI_FC_DIR"], libname))
            ret = original_load_library(fpath)
        else:
            try:
                ret = original_load_library(libname)
            except FileNotFoundError:
                biloc = inkex.inkscape_system_info.binary_location  # type: ignore
                blocdir = os.path.dirname(biloc)
                fpath = os.path.abspath(os.path.join(blocdir, libname))
                ret = original_load_library(fpath)
        return ret
    if name == "libc.so.6":
        # Do not need to load, return a blank class consistent with fontconfig
        libc = type("libc", (object,), {"free": staticmethod(lambda ptr: None)})()
        libc.free.argtypes = (ctypes.c_void_p,)
        return libc
    return original_load_library(name)


with patch("ctypes.cdll.LoadLibrary", side_effect=custom_load_library):
    import fontconfig as fc  # pylint: disable=import-error

    FC = fc.FC


def isnumeric(strv):
    """
    Check if a string can be converted to a number
    """
    try:
        float(strv)
        return True
    except ValueError:
        return False


def interpolate_dict(dictv, x, defaultval):
    """
    Interpolate an input over the numerical values of a dict
    Supports both string and int inputs and outputs
    If the dict's values are enums, pick the nearest value
    """
    # Check for exact match first
    if x in dictv:
        return dictv[x]

    # Interpolate numerical values
    if isnumeric(x):
        input_value = int(x)
        numerical_keys = sorted([int(k) for k in dictv.keys() if isnumeric(k)])
        for k, val in dictv.items():
            if isnumeric(k):
                ktype = type(k)  # int or str
                vtype = type(val)  # int or str

                if vtype not in [int, float, str]:  # enums
                    # Pick the nearest entry
                    intd = {int(k): v for k, v in dictv.items() if isnumeric(k)}
                    return intd[min(intd.keys(), key=lambda x: abs(x - int(x)))]
                break
        if input_value <= numerical_keys[0]:
            return dictv[ktype(numerical_keys[0])]
        if input_value >= numerical_keys[-1]:
            return dictv[ktype(numerical_keys[-1])]
        for i in range(len(numerical_keys) - 1):
            if numerical_keys[i] <= input_value <= numerical_keys[i + 1]:
                lower_key = numerical_keys[i]
                upper_key = numerical_keys[i + 1]
                lower_value = float(dictv[ktype(lower_key)])
                upper_value = float(dictv[ktype(upper_key)])
                ratio = (input_value - lower_key) / (upper_key - lower_key)
                interpolated_value = lower_value + ratio * (upper_value - lower_value)
                if vtype in [int, float]:
                    return interpolated_value
                return f"{interpolated_value:g}"
    return defaultval


# Windows doesn't have the XDG_DATA_HOME directory set, which is
# needed for /etc/fonts.conf to find the user fonts directory:
#   <dir prefix="xdg">fonts</dir>
# Needed for fontconfig
# Set it based on the location of preferences.xml
if sys.platform == "win32":
    if os.environ.get("XDG_DATA_HOME") is None:
        os.environ["XDG_DATA_HOME"] = os.path.dirname(
            inkex.inkscape_system_info.preferences  # type: ignore
        )


class FontConfig:
    """
    Class to handle FontConfig functionalities.
    """

    def __init__(self):
        self.truefonts = dict()  # css
        self.truefontsfc = dict()  # fontconfig
        self.truefontsfn = dict()  # fullnames
        self.truefontsft = dict()  # fonttools
        self.fontcharsets = dict()
        self.disable_lcctype()
        self.conf = fc.Config.get_current()
        self._font_list = None
        self._font_list_css = None

    def disable_lcctype(self):
        """
        Disables LC_CTYPE to suppress Mac warnings.
        """
        self.lcctype = os.environ.get("LC_CTYPE")
        if self.lcctype is not None and sys.platform == "darwin":
            del os.environ["LC_CTYPE"]  # suppress Mac warning

    def enable_lcctype(self):
        """
        Enables LC_CTYPE if it was previously disabled.
        """
        if self.lcctype is not None and sys.platform == "darwin":
            os.environ["LC_CTYPE"] = self.lcctype

    def get_true_font(self, fontsty):
        """Use fontconfig to get the true font that most text will be rendered as"""
        if fontsty not in self.truefonts:
            found = self.font_match(fontsty)
            truefont = FontConfig.fcfont_to_css(found)
            self.truefonts[fontsty] = truefont
            self.truefontsfc[fontsty] = found
            self.fontcharsets[truefont] = found.get(fc.PROP.CHARSET, 0)[0]
        return self.truefonts[fontsty]

    def get_true_font_fullname(self, fontsty):
        """Use fontconfig to get the Face name for a font style"""
        if fontsty not in self.truefontsfn:
            if fontsty not in self.truefontsfc:
                self.get_true_font(fontsty)
            self.truefontsfn[fontsty] = self.truefontsfc[fontsty].get(
                fc.PROP.FULLNAME, 0
            )[0]
        return self.truefontsfn[fontsty]

    def get_true_font_by_char(self, fontsty, chars):
        """
        Sometimes, a font will not have every character and a different one is
        substituted. (For example, many fonts do not have the ⎣ character.)
        Gets the true font by character
        """
        if fontsty not in self.truefonts:
            # font_match is more reliable at matching Inkscape than font_sort
            self.get_true_font(fontsty)
        truefont = self.truefonts[fontsty]
        cd1 = {k: truefont for k in chars if ord(k) in self.fontcharsets[truefont]}

        if len(cd1) < len(chars):
            found = self.font_sort(fontsty)
            for fnt in found:
                truefont = FontConfig.fcfont_to_css(fnt)
                if truefont not in self.fontcharsets:
                    self.fontcharsets[truefont] = fnt.get(fc.PROP.CHARSET, 0)[0]
                cset = self.fontcharsets[truefont]
                cd2 = {k: truefont for k in chars if ord(k) in cset and k not in cd1}
                cd1.update(cd2)
                if len(cd1) == len(chars):
                    break
            if len(cd1) < len(chars):
                cd1.update({c: None for c in chars if c not in cd1})
        return cd1

    @lru_cache(maxsize=None)
    def font_match(self, fontsty):
        """
        fc fonts matching a given reduced font style
        """
        pat = FontConfig.css_to_fcpattern(fontsty)
        self.conf.substitute(pat, FC.MatchPattern)
        pat.default_substitute()
        ret, _ = self.conf.font_match(pat)
        return ret

    @lru_cache(maxsize=None)
    def font_sort(self, fontsty):
        """
        List of fc fonts closest to a given reduced font style
        """
        pat = FontConfig.css_to_fcpattern(fontsty)
        self.conf.substitute(pat, FC.MatchPattern)
        pat.default_substitute()
        ret, _, _ = self.conf.font_sort(pat, trim=True, want_coverage=False)
        return ret

    def get_fonttools_font(self, fontsty):
        """
        Get a FontTools font instance based on the reduced style.
        """
        if fontsty not in self.truefontsft:
            if fontsty not in self.truefontsfc:
                self.get_true_font(fontsty)
            found = self.truefontsfc[fontsty]
            self.truefontsft[fontsty] = FontToolsFontInstance(found)
        return self.truefontsft[fontsty]

    @staticmethod
    def css_to_fcpattern(sty):
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
            interpolate_dict(C.CSSWGT_FCWGT, sty.get("font-weight"), FC.WEIGHT_NORMAL),
        )
        pat.add(
            fc.PROP.SLANT, C.CSSSTY_FCSLN.get(sty.get("font-style"), FC.SLANT_ROMAN)
        )
        return pat

    @staticmethod
    def fcfont_to_css(fnt):
        """Convert an fc font to a Style"""
        # For CSS, enclose font family in single quotes
        # Needed for fonts like Modern No. 20 with periods in the family
        fcfam = fnt.get(fc.PROP.FAMILY, 0)[0]
        fcwgt = fnt.get(fc.PROP.WEIGHT, 0)[0]
        fcsln = fnt.get(fc.PROP.SLANT, 0)[0]
        fcwdt = fnt.get(fc.PROP.WIDTH, 0)[0]
        if any(isinstance(v, tuple) for v in [fcfam, fcwgt, fcsln, fcwdt]):
            return None
        return Style(
            [
                ("font-family", "'" + fcfam.strip("'") + "'"),
                ("font-weight", interpolate_dict(C.FCWGT_CSSWGT, fcwgt, None)),
                ("font-style", C.FCSLN_CSSSTY[fcsln]),
                ("font-stretch", nearest_val(C.FCWDT_CSSSTR, fcwdt)),
            ]
        )

    @property
    def font_list(self):
        """
        Finds all fonts known to FontConfig
        Note that this does not appear to be completely comprehensive currently
        A few fonts are missing, such as HoloLens MDL2 Assets Bold on Windows
        These fonts can still be found using get_true_font
        """
        if self._font_list is None:
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
        if self._font_list_css is None:
            self._font_list_css = [FontConfig.fcfont_to_css(f) for f in self.font_list]
        return self._font_list_css


fcfg = FontConfig()
fontatt = ["font-family", "font-weight", "font-style", "font-stretch"]
dfltatt = [(k, default_style_atts[k]) for k in fontatt]


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
    tfnt = fcfg.get_true_font(sty2)
    return tfnt


def nearest_val(dictv, inputval):
    """Return the value of a dict whose key is closest to the input value"""
    return dictv[min(dictv.keys(), key=lambda x: abs(x - inputval))]


# Attempt to import the Pango bindings for the gi repository
with warnings.catch_warnings():
    # Ignore ImportWarning for Gtk/Pango
    warnings.simplefilter("ignore")

    HASPANGO = False
    HASPANGOFT2 = False
    pangoenv = os.environ.get("USEPANGO", "")
    if pangoenv != "False":
        try:
            if sys.platform == "win32":
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
                        not (os.path.exists(os.path.join(girepo, t))) for t in tlibs
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

            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import Pango

            try:
                HASPANGO = hasattr(Pango, "Variant") and hasattr(
                    Pango.Variant, "NORMAL"
                )
            except ValueError:
                HASPANGO = False
        except ImportError:
            HASPANGO = False

        if HASPANGO:
            try:
                # May require some typelibs we do not have
                gi.require_version("PangoFT2", "1.0")
                from gi.repository import PangoFT2

                HASPANGOFT2 = True
            except ValueError:
                HASPANGOFT2 = False
                from gi.repository import Gdk

if pangoenv in ["True", "False"]:
    os.environ["HASPANGO"] = str(HASPANGO)
    os.environ["HASPANGOFT2"] = str(HASPANGOFT2)
    with open("env_vars.txt", "w") as f:
        f.write(f"HASPANGO={os.environ['HASPANGO']}")
        f.write(f"\nHASPANGOFT2={os.environ['HASPANGOFT2']}")


class PangoRenderer:
    """
    Class to handle Pango rendering functionalities.
    """

    def __init__(self):
        self.pangosize = 1024 * 4
        # size of text to render. 1024 is good

        with warnings.catch_warnings():
            # Ignore ImportWarning
            warnings.filterwarnings("ignore", category=ImportWarning)
            if HASPANGOFT2:
                self.ctx = Pango.Context.new()
                self.ctx.set_font_map(PangoFT2.FontMap.new())
            else:
                self.ctx = Gdk.pango_context_get()
        self.pangolayout = Pango.Layout(self.ctx)
        self.pufd = Pango.units_from_double
        self.putd = Pango.units_to_double
        self.scale = Pango.SCALE
        self._families = None
        self._faces = None
        self._face_descriptions = None
        self._face_strings = None
        self._face_css = None

    @staticmethod
    def css_attribute_to_pango(sty, key):
        """
        Convert CSS style attributes to Pango attributes.
        """
        val = sty.get(key)
        if key == "font-weight":
            return C.CSSWGT_PWGT.get(val, Pango.Weight.NORMAL)
        if key == "font-style":
            return C.CSSSTY_PSTY.get(val, Pango.Style.NORMAL)
        if key == "font-stretch":
            return C.CSSSTR_PSTR.get(val, Pango.Stretch.NORMAL)
        if key == "font-variant":
            return C.CSSVAR_PVAR.get(val, Pango.Variant.NORMAL)
        return None

    @staticmethod
    def css_to_pango_description(sty):
        """
        Convert CSS style to Pango FontDescription.
        """
        fdesc = Pango.FontDescription(sty["font-family"].strip("'").strip('"') + ",")
        # The comma above is very important for font-families like Rockwell Condensed.
        # Without it, Pango will interpret it as the Condensed font-stretch of the
        # Rockwell font-family, rather than the Rockwell Condensed font-family.
        fdesc.set_weight(
            interpolate_dict(C.CSSWGT_PWGT, sty.get("font-weight"), Pango.Weight.NORMAL)
        )
        fdesc.set_variant(
            C.CSSVAR_PVAR.get(sty.get("font-variant"), Pango.Variant.NORMAL)
        )
        fdesc.set_style(C.CSSSTY_PSTY.get(sty.get("font-style"), Pango.Style.NORMAL))
        fdesc.set_stretch(
            C.CSSSTR_PSTR.get(sty.get("font-stretch"), Pango.Stretch.NORMAL)
        )
        return fdesc

    @staticmethod
    def pango_to_fc(pstretch, pweight, pstyle):
        """
        Convert Pango attributes to FontConfig attributes.
        """
        fcwidth = C.PSTR_FCWDT[pstretch]
        fcweight = C.PWGT_FCWGT[pweight]
        fcslant = C.PSTY_FCSLN[pstyle]
        return fcwidth, fcweight, fcslant

    @staticmethod
    def pango_to_css(pdescription):
        """
        Convert Pango FontDescription to CSS Style.
        """
        fdesc = pdescription
        cstr = [k for k, v in C.CSSSTR_PSTR.items() if v == fdesc.get_stretch()]
        fwgt = fdesc.get_weight()
        if fwgt not in C.CSSWGT_PWGT.values():
            cwgt = [str(int(fwgt))]
        else:
            cwgt = [
                k
                for k, v in C.CSSWGT_PWGT.items()
                if v == fdesc.get_weight() and isnumeric(k)
            ]
        csty = [k for k, v in C.CSSSTY_PSTY.items() if v == fdesc.get_style()]

        sty = (("font-family", fdesc.get_family()),)
        if len(cwgt) > 0:
            sty += (("font-weight", cwgt[0]),)
        if len(csty) > 0:
            sty += (("font-style", csty[0]),)
        if len(cstr) > 0:
            sty += (("font-stretch", cstr[0]),)
        return Style(sty)

    @property
    def families(self):
        """List all font families available in Pango context."""
        if self._families is None:
            families = self.ctx.get_font_map().list_families()
            self._families = sorted(
                families, key=lambda x: x.get_name()
            )  # Sort families alphabetically
        return self._families

    @property
    def faces(self):
        """List all font faces available in Pango context."""
        if self._faces is None:
            self._faces = [fc for fm in self.families for fc in fm.list_faces()]
        return self._faces

    @property
    def face_descriptions(self):
        """List all font face descriptions available in Pango context."""
        if self._face_descriptions is None:
            self._face_descriptions = [fc.describe() for fc in self.faces]
        return self._face_descriptions

    @property
    def face_strings(self):
        """List all font face strings available in Pango context."""
        if self._face_strings is None:
            self._face_strings = [fd.to_string() for fd in self.face_descriptions]
        return self._face_strings

    @property
    def face_css(self):
        """List all font face CSS styles available in Pango context."""
        if self._face_css is None:
            self._face_css = [
                PangoRenderer.pango_to_css(fd) for fd in self.face_descriptions
            ]
        return self._face_css

    @staticmethod
    def fc_match_pango(family, pstretch, pweight, pstyle):
        """Look up a font by its Pango properties"""
        pat = fc.Pattern.name_parse(re.escape(family.replace("'", "").replace('"', "")))
        fcwidth, fcweight, fcslant = PangoRenderer.pango_to_fc(
            pstretch, pweight, pstyle
        )
        pat.add(fc.PROP.WIDTH, fcwidth)
        pat.add(fc.PROP.WEIGHT, fcweight)
        pat.add(fc.PROP.SLANT, fcslant)

        fcfg.conf.substitute(pat, FC.MatchPattern)
        pat.default_substitute()
        found, _ = fcfg.conf.font_match(pat)
        return found

    def set_text_style(self, sty):
        """Set the text style for rendering based on the provided style"""
        fdesc = PangoRenderer.css_to_pango_description(sty)
        fdesc.set_absolute_size(self.pufd(self.pangosize))
        fnt = self.ctx.get_font_map().load_font(self.ctx, fdesc)

        success = fnt is not None
        if success:
            self.pangolayout.set_font_description(fdesc)
            metrics = fnt.get_metrics()
            metrics = [
                self.putd(v) / self.pangosize
                for v in [
                    metrics.get_height(),
                    metrics.get_ascent(),
                    metrics.get_descent(),
                ]
            ]
            return success, metrics
        return success, None

    def render_text(self, texttorender):
        """Render text using Pango layout."""
        self.pangolayout.set_text(texttorender, -1)

    def process_extents(self, ext, ascent):
        """
        Scale extents and return extents as standard bboxes
        (0:logical, 1:ink, 2: ink relative to anchor/baseline)
        """
        logr = ext.logical_rect
        logr = [
            self.putd(v) / self.pangosize
            for v in [logr.x, logr.y, logr.width, logr.height]
        ]
        inkr = ext.ink_rect
        inkr = [
            self.putd(v) / self.pangosize
            for v in [inkr.x, inkr.y, inkr.width, inkr.height]
        ]
        ir_rel = [inkr[0] - logr[0], inkr[1] - logr[1] - ascent, inkr[2], inkr[3]]
        return logr, inkr, ir_rel

    def get_character_extents(self, ascent, needexts):
        """
        Iterate through the layout to get the logical width of each character
        If there is differential kerning applied, it is applied to the
        width of the first character. For example, the 'V' in 'Voltage'
        will be thinner due to the 'o' that follows.
        Units: relative to font size
        """
        loi = self.pangolayout.get_iter()
        wds = []
        i = -1
        lastpos = True
        unwrapper = 0
        moved = True
        while moved:
            cext = loi.get_cluster_extents()
            i += 1
            if needexts[i] == "1":
                ext = self.process_extents(cext, ascent)
                if ext[0][0] < 0 and lastpos:
                    unwrapper += 2**32 / (self.scale * self.pangosize)
                lastpos = ext[0][0] >= 0
                ext[0][0] += unwrapper  # account for 32-bit overflow
                ext[1][0] += unwrapper
                wds.append(ext)
            else:
                wds.append(None)
            moved = loi.next_char()

        numunknown = self.pangolayout.get_unknown_glyphs_count()
        return wds, numunknown


# pylint:disable=import-outside-toplevel
class FontToolsFontInstance:
    """
    Class to handle FontTools font instances.
    Note that this is rarely used (only if Pango fails, or for getting the
    ascent for text flows). The imports are fairly time-consuming, so
    they are only performed conditionally.
    """

    def __init__(self, fcfont):
        self.font = FontToolsFontInstance.font_from_fc(fcfont)
        self.head = self.font["head"]
        self.os2 = self.font["OS/2"] if "OS/2" in self.font else None
        self.find_font_metrics()
        self.cmap = None
        self.hmtx = None
        self.kern = None
        self.gsub = None
        self.glyf = None
        self.glyph_names = None
        self.ligatures = None

    @staticmethod
    def font_from_fc(found):
        """Find a FontTools font from a FontConfig font."""
        fname = found.get(fc.PROP.FILE, 0)[0]

        from fontTools.ttLib import TTFont, TTLibFileIsCollectionError  # pylint: disable=no-name-in-module
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

        except TTLibFileIsCollectionError:
            # is TT collection
            fcfam = found.get(fc.PROP.FAMILY, 0)[0]
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

                # nameID=1: font family name
                familymatch = any(
                    fcfam in n.toUnicode() for n in tfont["name"].names if n.nameID == 1
                )
                widthmatch = C.OS2WDT_FCWDT[font_width] == fcwdt
                weightmatch = (
                    interpolate_dict(C.OS2WGT_FCWGT, font_weight, None) == fcwgt
                )
                slantmatch = (
                    font_italic and fcsln in [FC.SLANT_ITALIC, FC.SLANT_OBLIQUE]
                ) or (not font_italic and fcsln == FC.SLANT_ROMAN)
                num_match.append(
                    sum([weightmatch, widthmatch, slantmatch, familymatch])
                )
                if num_match[-1] == 4:
                    font = tfont
                    break
            if max(num_match) < 4:
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
        units_per_em = self.head.unitsPerEm
        os2 = self.os2
        if os2:
            self._ascent = abs(os2.sTypoAscender / units_per_em)
            self._descent = abs(os2.sTypoDescender / units_per_em)
        else:
            self._ascent = abs(font["hhea"].ascent / units_per_em)
            self._descent = abs(font["hhea"].descent / units_per_em)
        self._ascent_max = abs(font["hhea"].ascent / units_per_em)
        self._descent_max = abs(font["hhea"].descent / units_per_em)
        self._design_units = units_per_em
        emv = self._ascent + self._descent
        if emv > 0.0:
            self._ascent /= emv
            self._descent /= emv

        if os2 and os2.version >= 0x0002 and os2.version != 0xFFFF:
            self._xheight = abs(os2.sxHeight / units_per_em)
        else:
            glyph_set = font.getGlyphSet()
            self._xheight = (
                abs(glyph_set["x"].height / units_per_em)
                if "x" in glyph_set and glyph_set["x"].height is not None
                else 0.5
            )
        self._baselines = [0] * 8
        self.sp_css_baseline_ideographic = 0
        self.sp_css_baseline_hanging = 1
        self.sp_css_baseline_mathematical = 2
        self.sp_css_baseline_central = 3
        self.sp_css_baseline_middle = 4
        self.sp_css_baseline_text_beforeedge = 5
        self.sp_css_baseline_text_after_edge = 6
        self.sp_css_baseline_alphabetic = 7
        self._baselines[self.sp_css_baseline_ideographic] = -self._descent
        self._baselines[self.sp_css_baseline_hanging] = 0.8 * self._ascent
        self._baselines[self.sp_css_baseline_mathematical] = 0.8 * self._xheight
        self._baselines[self.sp_css_baseline_central] = 0.5 - self._descent
        self._baselines[self.sp_css_baseline_middle] = 0.5 * self._xheight
        self._baselines[self.sp_css_baseline_text_beforeedge] = self._ascent
        self._baselines[self.sp_css_baseline_text_after_edge] = -self._descent

        # Get capital height
        if os2 and hasattr(os2, "sCapHeight") and os2.sCapHeight not in [0, None]:
            self.cap_height = os2.sCapHeight / units_per_em
        elif "glyf" in font and "I" in font.getGlyphNames():
            glyf_table = font["glyf"]
            i_glyph = glyf_table["I"]
            self.cap_height = (i_glyph.yMax - 0 * i_glyph.yMin) / units_per_em
        else:
            self.cap_height = 1

    def get_char_advances(self, chars, pchars):
        """Get the advance width and bounding boxes of characters."""
        units_per_em = self.head.unitsPerEm
        if self.cmap is None:
            self.cmap = self.font.getBestCmap()
        if self.hmtx is None:
            self.hmtx = self.font["hmtx"]
        if self.kern is None:
            self.kern = self.font["kern"] if "kern" in self.font else None
        if self.gsub is None:
            self.gsub = self.font["GSUB"] if "GSUB" in self.font else None
        if self.glyf is None:
            self.glyf = self.font["glyf"] if "glyf" in self.font else None
        if self.glyph_names is None:
            self.glyph_names = self.font.getGlyphNames()

        if self.cmap is None:
            # Certain symbol fonts don't have a cmap table
            self.cmap = dict()
            for table in self.font["cmap"].tables:
                if table.isUnicode():
                    for codepoint, name in table.cmap.items():
                        self.cmap[codepoint] = name
                        self.cmap[codepoint - 15 * 4096] = name

        advs = dict()
        bbs = dict()
        for c in chars:
            glyph1 = self.cmap.get(ord(c))
            if glyph1 is not None:
                if glyph1 in self.hmtx.metrics:
                    advance_width, _ = self.hmtx.metrics[glyph1]
                    advs[c] = advance_width / units_per_em

                try:
                    glyph = self.glyf[glyph1]
                    bbx = [
                        glyph.xMin,
                        -glyph.yMax,
                        glyph.xMax - glyph.xMin,
                        glyph.yMax - glyph.yMin,
                    ]
                    bbs[c] = [v / units_per_em for v in bbx]
                except (AttributeError, TypeError):
                    bbs[c] = [0, 0, 0, 0]
            else:
                advs[c] = None

        # Get ligature table (made with LLM help)
        # Reference: https://learn.microsoft.com/en-us/typography/opentype/spec/gsub
        if self.ligatures is None:
            if self.gsub:
                gsub_table = self.gsub.table
                self.ligatures = dict()

                # Helper function to check if a feature tag is in the list
                def has_feature_tag(feature_tag, lookup_index):
                    for feature in gsub_table.FeatureList.FeatureRecord:
                        if feature.FeatureTag == feature_tag:
                            if lookup_index in feature.Feature.LookupListIndex:
                                return True
                    return False

                for lookup_index, lookup in enumerate(gsub_table.LookupList.Lookup):
                    for subtable in lookup.SubTable:
                        if lookup.LookupType == 7:  # Extension substitutions
                            ext_subtable = subtable.ExtSubTable
                            lookup_type = ext_subtable.LookupType
                        else:
                            ext_subtable = subtable
                            lookup_type = lookup.LookupType

                        if lookup_type == 4:  # Ligature substitutions
                            # Check if the lookup is for discretionary ligatures
                            if has_feature_tag("liga", lookup_index):
                                for (
                                    first_glyph,
                                    ligature_set,
                                ) in ext_subtable.ligatures.items():
                                    for ligature in ligature_set:
                                        component_glyphs = [
                                            first_glyph
                                        ] + ligature.Component
                                        ligature_glyph = ligature.LigGlyph
                                        self.ligatures[tuple(component_glyphs)] = (
                                            ligature_glyph
                                        )

            else:
                self.ligatures = dict()

        dadvs = dict()
        for c in pchars:
            glyph2 = self.cmap.get(ord(c))
            for pchar in pchars[c]:
                glyph1 = self.cmap.get(ord(pchar))
                kerning_value = None
                if (glyph1, glyph2) in self.ligatures:
                    ligglyph = self.ligatures[(glyph1, glyph2)]
                    awlig, _ = self.hmtx.metrics[ligglyph]
                    aw1, _ = self.hmtx.metrics[glyph1]
                    aw2, _ = self.hmtx.metrics[glyph2]
                    kerning_value = awlig - aw1 - aw2
                else:
                    if self.kern is not None:
                        for subtable in self.kern.kernTables:
                            kerning_value = subtable.kernTable.get((glyph1, glyph2))
                            if kerning_value is not None:
                                break
                if kerning_value is None:
                    kerning_value = 0
                dadvs[(pchar, c)] = kerning_value / units_per_em
        return advs, dadvs, bbs


# pylint:enable=import-outside-toplevel


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
    # And yet Semi-Light seems to work anyway
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
        "350": FC.WEIGHT_SEMILIGHT,
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
    # Despite this, Semi-Light seems to be valid
    FCWGT_CSSWGT = {
        FC.WEIGHT_THIN: "100",
        FC.WEIGHT_EXTRALIGHT: "200",
        FC.WEIGHT_LIGHT: "300",
        FC.WEIGHT_SEMILIGHT: "350",
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

    if HASPANGO:
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
            "semilight": Pango.Weight.SEMILIGHT,
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
            "350": Pango.Weight.SEMILIGHT,
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


C = Conversions  # pylint: disable=invalid-name


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
    if usepango and HASPANGO:
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
        for wrd in stylews:
            understood = False
            if wrd in pwgtstrs:
                sty["font-weight"] = pwgtstrs[wrd]
                understood = True
            elif "weight" in wrd:
                sty["font-weight"] = re.search(r"weight(\d+)", wrd).group(1)
                understood = True
            if wrd in pstystrs:
                sty["font-style"] = pstystrs[wrd]
                understood = True
            if wrd in pstrstrs:
                sty["font-stretch"] = pstrstrs[wrd]
                understood = True
            if not understood:
                return None
    sty = {key: sty[key] for key in fontatt if key in sty}  # order
    return sty
