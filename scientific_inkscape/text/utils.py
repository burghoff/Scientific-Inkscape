# coding=utf-8
#
# Copyright (c) 2023 David Burghoff <burghoff@utexas.edu>
#                    Martin Owens <doctormo@gmail.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Thomas Holder <thomas.holder@schrodinger.com>
#                    Jonathan Neuhauser <jonathan.neuhauser@outlook.com>
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

"""
Utilities for text parsing
"""

import inkex
from inkex.text.cache import tags, ipx, cpath_support
import math, re, sys, os

# For style components that represent a size (stroke-width, font-size, etc), calculate
# the true size reported by Inkscape in user units, inheriting any styles/transforms/document scaling
flookup = {"small": "10px", "medium": "12px", "large": "14px"}


def composed_width(el, comp):
    """
    Gets the transformed size of a style component and the scale factor representing
    the scale of the composed transform, accounting for relative sizes.

    Parameters:
        el (Element): The element whose style to compute.
        comp (str): The component of the style to compute, such as 'stroke-width' or 'font-size'.

    Returns:
        tuple: A tuple containing the true size in user units and the scale factor.
    """
    cs = el.cspecified_style
    ct = el.ccomposed_transform
    sc = cs.get(comp)

    # Get default attribute if empty
    if sc is None:
        sc = default_style_atts[comp]

    if "%" in sc:  # relative width, get parent width
        cel = el
        while sc != cel.cstyle.get(comp) and sc != cel.get(comp):
            cel = cel.getparent()
            # figure out ancestor where % is coming from

        sc = float(sc.strip("%")) / 100
        tsz, sf = composed_width(cel.getparent(), comp)

        return tsz * sc, sf
    else:
        utsz = (
            ipx(sc)
            or ipx(flookup.get(sc) if comp == "font-size" else None)
            or ipx(default_style_atts[comp])
        )
        sf = math.sqrt(abs(ct.a * ct.d - ct.b * ct.c))  # scale factor
        return utsz * sf, sf


def composed_lineheight(el):
    """
    Get absolute line-height in user units based on an element's specified style.

    Parameters:
        el (Element): The element whose line-height to compute.

    Returns:
        float: The computed line-height in user units.
    """
    cs = el.cspecified_style
    sc = cs.get("line-height", default_style_atts["line-height"])
    if sc == "normal":
        sc = 1.25
    elif "%" in sc:  # relative width, get parent width
        sc = float(sc.strip("%")) / 100
    else:
        try:
            # Lines have no unit, em treated the same
            sc = float(sc.strip("em"))
        except:
            fs, sf = composed_width(el, "font-size")
            sc = ipx(sc) / (fs / sf)
    fs, _ = composed_width(el, "font-size")
    return sc * fs


def unique(lst):
    """
    Returns a list of unique items from the given list while preserving order.

    Parameters:
        lst (list): The list from which to remove duplicates.

    Returns:
        list: A list of unique items in the order they appeared in the input list.
    """
    return list(dict.fromkeys(lst))


def uniquetol(A, tol):
    """
    Like unique, but for numeric values and accepts a tolerance.

    Parameters:
        A (list of float): List of numeric values from which to remove near-duplicates.
        tol (float): The tolerance within which two numbers are considered the same.

    Returns:
        list of float: A list of unique numbers within the specified tolerance.
    """
    if not A:  # Check if the input list is empty
        return []
    A_sorted = sorted((x for x in A if x is not None))  # Sort, ignoring None values
    ret = (
        [A_sorted[0]] if A_sorted else []
    )  # Start with the first value if there are any non-None values
    for i in range(1, len(A_sorted)):
        if abs(A_sorted[i] - ret[-1]) > tol:
            ret.append(A_sorted[i])
    # If there were any None values in the original list, append None to the result list
    if None in A:
        ret.append(None)
    return ret


otp_support = cpath_support
otp_support_tags = tags(cpath_support)
ptag = inkex.PathElement.ctag


def object_to_path(el):
    """
    Converts specified elements to paths if supported. Adjusts the 'd' attribute and changes the element tag to a path.

    Parameters:
        el (Element): The element to convert to a path.

    Note:
        Only operates on elements within the `otp_support_tags` list.
    """
    if el.tag in otp_support_tags and not el.tag == ptag:
        el.set("d", str(el.cpath))  # do this first so cpath is correct
        el.tag = ptag


rectlike_tags = tags((inkex.PathElement, inkex.Rectangle, inkex.Line, inkex.Polyline))
rect_tag = inkex.Rectangle.ctag
pel_tag = inkex.PathElement.ctag
usetag = inkex.Use.ctag

pth_cmds = "".join(list(inkex.paths.PathCommand._letter_to_class.keys()))
pth_cmd_pat = re.compile("[" + re.escape(pth_cmds) + "]")
cnt_pth_cmds = lambda d: len(pth_cmd_pat.findall(d))  # count path commands


def isrectangle(el, includingtransform=True):
    """
    Determines if an element is rectangle-like, considering transformations if specified.

    Parameters:
        el (Element): The element to check.
        includingtransform (bool): Whether to consider transformations in the determination.

    Returns:
        tuple: A tuple containing a boolean indicating if the element is a rectangle and the path if it is.
    """

    if not includingtransform and el.tag == rect_tag:
        pth = el.cpath
    elif el.tag in rectlike_tags:
        # Before parsing the path (possibly slow), make sure 4-5 path commands
        if el.tag == pel_tag and not (4 <= cnt_pth_cmds(el.get("d", "")) <= 5):
            return False
        pth = el.cpath
        # if includingtransform:
        #     pth = pth.transform(el.ctransform)

        if includingtransform:
            tmat = el.ctransform.matrix
            xs, ys = list(
                zip(
                    *[
                        (
                            tmat[0][0] * pt.x + tmat[0][1] * pt.y + tmat[0][2],
                            tmat[1][0] * pt.x + tmat[1][1] * pt.y + tmat[1][2],
                        )
                        for pt in pth.end_points
                    ]
                )
            )
        else:
            xs, ys = list(zip(*[(pt.x, pt.y) for pt in pth.end_points]))

        maxsz = max(max(xs) - min(xs), max(ys) - min(ys))
        tol = 1e-3 * maxsz
        if len(uniquetol(xs, tol)) != 2 or len(uniquetol(ys, tol)) != 2:
            return False
    elif el.tag == usetag:
        useel = el.get_link("xlink:href")
        if useel is not None:
            return isrectangle(useel)
        else:
            return True
    else:
        return False

    # Assume masks aren't rectangular
    if el.get_link("mask", llget=True) is not None:
        return False
    # Clipped rectangles may not be rectangular
    if el.get_link("clip-path", llget=True) is not None and any(
        [not isrectangle(k) for k in list(el.get_link("clip-path", llget=True))]
    ):
        return False
    return True


def Get_Bounding_Boxes(filename, inkscape_binary=None, extra_args=[], svg=None):
    """
    Retrieves all of a document's bounding boxes using a call to the Inkscape binary.

    Parameters:
        filename (str): The path to the SVG file.
        inkscape_binary (str): The path to the Inkscape binary. If not provided, it will attempt to find it.
        extra_args (list): Additional arguments to pass to the Inkscape command.
        svg (SVGElement): An optional SVGElement to use instead of loading from file.

    Returns:
        dict: A dictionary where keys are element IDs and values are bounding boxes in user units.
    """
    if inkscape_binary is None:
        inkscape_binary = inkex.inkscape_system_info.binary_location
    arg2 = [inkscape_binary, "--query-all"] + extra_args + [filename]
    p = subprocess_repeat(arg2)
    tFStR = p.stdout

    # Parse the output
    tBBLi = tFStR.splitlines()
    bbs = dict()
    for d in tBBLi:
        key = str(d).split(",")[0]
        if key[0:2] == "b'":  # pre version 1.1
            key = key[2:]
        if str(d)[2:52] == "WARNING: Requested update while update in progress":
            continue
            # skip warnings (version 1.0 only?)
        data = [float(x.strip("'")) for x in str(d).split(",")[1:]]
        if key != "'":  # sometimes happens in v1.3
            bbs[key] = data

    # Inkscape always reports a bounding box in pixels, relative to the viewbox
    # Convert to user units for the output
    if svg is None:
        # If SVG not supplied, load from file from load_svg
        from inkex import load_svg

        svg = load_svg(filename).getroot()

    ds = svg.cdocsize
    for k in bbs:
        bbs[k] = ds.pxtouu(bbs[k])
    return bbs


class Inkscape_System_Info:
    """
    Discovers and caches Inkscape System info.
    """

    def __init__(self):
        pass

    @property
    def language(self):
        if not hasattr(self, "_language"):
            self._language = self.determine_language()
        return self._language

    @property
    def preferences(self):
        if not hasattr(self, "_preferences"):
            self._preferences = self.find_preferences()
        return self._preferences

    @property
    def binary_location(self):
        if not hasattr(self, "_binary_location"):
            self._binary_location = self.Get_Binary_Loc()
        return self._binary_location

    def Get_Binary_Loc(self):
        """
        Gets the location of the Inkscape binary, checking the system
        path if necessary.
        """
        try:
            import inkex.command
        except:
            # Import of inkex.command not working before v1.2
            import importlib.util

            module_path = os.path.join(
                os.path.split(os.path.abspath(inkex.__file__))[0], "command.py"
            )
            spec = importlib.util.spec_from_file_location("inkex.command", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            inkex.command = module

        def which2(program):
            try:
                return inkex.command.which(program)
            except:
                # Search the path as a backup (primarily for testing)
                try:
                    from shutil import which as warlock

                    for sp in sys.path:
                        if sys.platform == "win32":
                            prog = warlock(program, path=os.environ["PATH"] + ";" + sp)
                            if prog:
                                return prog
                except ImportError:
                    pass
                raise inkex.command.CommandNotFound(
                    f"Can not find the command: '{program}'"
                )

        return which2(inkex.command.INKSCAPE_EXECUTABLE_NAME)

    def find_preferences(self):
        """Attempt to discover preferences.xml"""
        # First check the location of the user extensions directory
        mydir = os.path.dirname(os.path.abspath(__file__))
        file_path = mydir
        while "extensions" in file_path and os.path.basename(file_path) != "extensions":
            file_path = os.path.dirname(file_path)
        prefspath = os.path.join(os.path.dirname(file_path), "preferences.xml")
        if os.path.exists(prefspath):
            return prefspath

        # Try some common default locations based on the home directory
        homedir = os.path.expanduser("~")
        if sys.platform == "win32":
            appdata = os.getenv("APPDATA")
            if appdata is not None:
                # https://wiki.inkscape.org/wiki/Preferences_subsystem
                prefspath = os.path.join(
                    os.path.abspath(appdata), "inkscape", "preferences.xml"
                )
                if os.path.exists(prefspath):
                    return prefspath
            # https://en.wikipedia.org/wiki/Environment_variable#Default_Values_on_Microsoft_Windows
            prefspath = os.path.join(
                homedir, "AppData", "Roaming", "inkscape", "preferences.xml"
            )
            if os.path.exists(prefspath):
                return prefspath
            # https://en.wikipedia.org/wiki/Environment_variable#Default_Values_on_Microsoft_Windows
            # http://tavmjong.free.fr/INKSCAPE/MANUAL/html/Customize-Files.html
            prefspath = os.path.join(
                homedir, "­Application Data", "­Inkscape", "preferences.xml"
            )
            if os.path.exists(prefspath):
                return prefspath
        else:
            if sys.platform == "darwin":
                # DB's Mac
                prefspath = os.path.join(
                    homedir,
                    "Library",
                    "Application Support",
                    "org.inkscape.Inkscape",
                    "config",
                    "inkscape",
                    "preferences.xml",
                )
                if os.path.exists(prefspath):
                    return prefspath
            # DB's Linux
            prefspath = os.path.join(homedir, ".config", "inkscape", "preferences.xml")
            if os.path.exists(prefspath):
                return prefspath
            # https://wiki.inkscape.org/wiki/Preferences_subsystem#Where_preferences_are_stored
            prefspath = os.path.join(homedir, ".config", "Inkscape", "preferences.xml")
            if os.path.exists(prefspath):
                return prefspath
            # https://wiki.inkscape.org/wiki/Preferences_subsystem#Where_preferences_are_stored
            # https://alpha.inkscape.org/vectors/www.inkscapeforum.com/viewtopicc8ae.html?t=1712
            prefspath = os.path.join(homedir, ".inkscape", "preferences.xml")
            if os.path.exists(prefspath):
                return prefspath

            # Try finding from snap location
            file_path = mydir
            while "snap" in file_path and os.path.basename(file_path) != "snap":
                file_path = os.path.dirname(file_path)
            prefspath = os.path.join(
                os.path.dirname(file_path), ".config", "inkscape", "preferences.xml"
            )
            if os.path.exists(prefspath):
                return prefspath
        return None  # failed

    def determine_language(self, verbose=False):
        """Try to find the language Inkscape is using"""

        def get_ui_language(prefspath):
            from lxml import etree

            proot = etree.parse(prefspath).getroot()
            for k in proot:
                if k.get("id") == "ui" and k.get("language") is not None:
                    return k.get("language")
            return None

        def getlocale_mod():
            import warnings, locale

            with warnings.catch_warnings():
                # temporary work-around for https://github.com/python/cpython/issues/82986
                # by continuing to use getdefaultlocale() even though it has been deprecated.
                if sys.version_info.minor >= 13:
                    warnings.warn(
                        "This function may not behave as expected in Python versions beyond 3.12",
                        FutureWarning,
                    )
                warnings.simplefilter("ignore", category=DeprecationWarning)
                language_code = locale.getdefaultlocale()[0]
            if language_code:
                return language_code
            return "en-US"

        # First, try to get the language from preferences.xml
        pxml = self.find_preferences()
        if verbose:
            inkex.utils.debug("Found preferences.xml: " + str(pxml))
        if pxml is not None:
            prefslang = get_ui_language(pxml)
            if verbose:
                inkex.utils.debug("preferences.xml language: " + str(prefslang))
        # If it can't be found or is set to use the system lang, use locale
        if pxml is None or prefslang in ["", None]:
            lcle = getlocale_mod()
            prefslang = lcle.split("_")[0]
            if verbose:
                inkex.utils.debug("locale language: " + str(prefslang))
        return prefslang


inkex.inkscape_system_info = Inkscape_System_Info()  # type: ignore


def subprocess_repeat(argin):
    """
    In the event of a timeout, repeats a subprocess call several times.

    Parameters:
        argin (list): The command and arguments to run in the subprocess.

    Returns:
        CompletedProcess: The result from the subprocess call.
    """
    BASE_TIMEOUT = 60
    NATTEMPTS = 4
    import subprocess

    nfails = 0
    ntime = 0
    for ii in range(NATTEMPTS):
        timeout = BASE_TIMEOUT * (ii + 1)
        try:
            os.environ["SELF_CALL"] = "true"  # seems to be needed for 1.3
            p = subprocess.run(
                argin,
                shell=False,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            break
        except subprocess.TimeoutExpired:
            nfails += 1
            ntime += timeout
    if nfails == NATTEMPTS:
        inkex.utils.errormsg(
            "Error: The call to the Inkscape binary timed out "
            + str(NATTEMPTS)
            + " times in "
            + str(ntime)
            + " seconds.\n\n"
            + "This may be a temporary issue; try running the extension again."
        )
        quit()
    else:
        return p


# Get default style attributes
try:
    from inkex.properties import all_properties

    default_style_atts = {a: v[1] for a, v in all_properties.items()}  # type: ignore
except:
    # Older versions without inkex.properties
    default_style_atts = {
        "alignment-baseline": "baseline",
        "baseline-shift": "0",
        "clip": "auto",
        "clip-path": "none",
        "clip-rule": "nonzero",
        "color": "black",
        "color-interpolation": "sRGB",
        "color-interpolation-filters": "linearRGB",
        "color-rendering": "auto",
        "cursor": "auto",
        "direction": "ltr",
        "display": "inline",
        "dominant-baseline": "auto",
        "fill": "black",
        "fill-opacity": "1",
        "fill-rule": "nonzero",
        "filter": "none",
        "flood-color": "black",
        "flood-opacity": "1",
        "font": "",
        "font-family": "sans-serif",
        "font-size": "medium",
        "font-size-adjust": "none",
        "font-stretch": "normal",
        "font-style": "normal",
        "font-variant": "normal",
        "font-weight": "normal",
        "glyph-orientation-horizontal": "0deg",
        "glyph-orientation-vertical": "auto",
        "image-rendering": "auto",
        "letter-spacing": "normal",
        "lighting-color": "normal",
        "line-height": "normal",
        "marker": "",
        "marker-end": "none",
        "marker-mid": "none",
        "marker-start": "none",
        "mask": "none",
        "opacity": "1",
        "overflow": "visible",
        "paint-order": "normal",
        "pointer-events": "visiblePainted",
        "shape-rendering": "visiblePainted",
        "stop-color": "black",
        "stop-opacity": "1",
        "stroke": "none",
        "stroke-dasharray": "none",
        "stroke-dashoffset": "0",
        "stroke-linecap": "butt",
        "stroke-linejoin": "miter",
        "stroke-miterlimit": "4",
        "stroke-opacity": "1",
        "stroke-width": "1",
        "text-align": "start",
        "text-anchor": "start",
        "text-decoration": "none",
        "text-overflow": "clip",
        "text-rendering": "auto",
        "unicode-bidi": "normal",
        "vector-effect": "none",
        "vertical-align": "baseline",
        "visibility": "visible",
        "white-space": "normal",
        "word-spacing": "normal",
        "writing-mode": "horizontal-tb",
        "-inkscape-font-specification": "sans-serif",
    }
default_style_atts["font-variant-ligatures"]="normal"