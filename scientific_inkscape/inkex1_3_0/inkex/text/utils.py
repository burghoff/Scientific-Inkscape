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

import math
import re
import sys
import os
from functools import lru_cache
import lxml
from lxml import etree
import inkex
import inkex.command
from inkex.properties import all_properties
from inkex.units import CONVERSIONS, BOTH_MATCH

# For style components that represent a size (stroke-width, font-size, etc),
# calculate the true size reported by Inkscape in user units, inheriting
# any styles/transforms/document scaling
flookup = {"small": "10px", "medium": "12px", "large": "14px"}


def composed_width(elem, comp):
    """
    Gets the transformed size of a style component and the scale factor representing
    the scale of the composed transform, accounting for relative sizes.

    Parameters:
        elem (Element): The element whose style to compute.
        comp (str): The component of the style to compute, such as 'stroke-width'
        or 'font-size'.

    Returns:
        tuple: A tuple containing the true size in user units, the scale factor,
        and the untransformed size
    """
    sty = elem.cspecified_style
    ctf = elem.ccomposed_transform
    satt = sty.get(comp)

    # Get default attribute if empty
    if satt is None:
        satt = default_style_atts[comp]

    if "%" in satt:  # relative width, get ancestor width
        cel = elem
        while satt != cel.cstyle.get(comp) and satt != cel.get(comp):
            cel = cel.getparent()
            # figure out ancestor where % is coming from

        satt = float(satt.strip("%")) / 100
        tsz, scf, utsz = composed_width(cel.getparent(), comp)

        # Since relative widths have no untransformed width, we assign
        # it to be a scaled version of the ancestor's ut width
        return tsz * satt, scf, utsz * satt
    utsz = ipx(satt)
    if utsz is None:
        utsz = (
            utsz
            or ipx(flookup.get(satt) if comp == "font-size" else None)
            or ipx(default_style_atts[comp])
        )
    scf = math.sqrt(abs(ctf.a * ctf.d - ctf.b * ctf.c))  # scale factor
    return utsz * scf, scf, utsz


def composed_lineheight(elem):
    """
    Get absolute line-height in user units based on an element's specified style.

    Parameters:
        elem (Element): The element whose line-height to compute.

    Returns:
        float: The computed line-height in user units.
    """
    sty = elem.cspecified_style
    satt = sty.get("line-height", default_style_atts["line-height"])
    if satt == "normal":
        satt = 1.25
    elif "%" in satt:  # relative width, get parent width
        satt = float(satt.strip("%")) / 100
    else:
        try:
            # Lines have no unit, em treated the same
            satt = float(satt.strip("em"))
        except ValueError:
            fsz, scf, _ = composed_width(elem, "font-size")
            satt = ipx(satt) / (fsz / scf)
    fsz, _, _ = composed_width(elem, "font-size")
    return satt * fsz


def unique(lst):
    """
    Returns a list of unique items from the given list while preserving order.

    Parameters:
        lst (list): The list from which to remove duplicates.

    Returns:
        list: A list of unique items in the order they appeared in the input list.
    """
    return list(dict.fromkeys(lst))


def uniquetol(x, tol):
    """
    Like unique, but for numeric values and accepts a tolerance.

    Parameters:
        x (list of float): List of numeric values from which to remove near-duplicates.
        tol (float): The tolerance within which two numbers are considered the same.

    Returns:
        list of float: A list of unique numbers within the specified tolerance.
    """
    if not x:  # Check if the input list is empty
        return []
    x_sorted = sorted((y for y in x if y is not None))  # Sort, ignoring None values
    ret = (
        [x_sorted[0]] if x_sorted else []
    )  # Start with the first value if there are any non-None values
    for i in range(1, len(x_sorted)):
        if abs(x_sorted[i] - ret[-1]) > tol:
            ret.append(x_sorted[i])
    # If there were any None values in the original list, append None to the result list
    if None in x:
        ret.append(None)
    return ret


# Adds ctag to the inkex classes, which holds each class's corresponding tag
# Checking the tag is usually much faster than instance checking, which can
# substantially speed up low-level functions.
# pylint:disable=protected-access
lt = dict(inkex.elements._parser.NodeBasedLookup.lookup_table)
shapetags = set()
for key, v in lt.items():
    for v2 in v:
        v2.ctag = inkex.addNS(key[1], key[0]) if isinstance(key, tuple) else key
        if issubclass(v2, inkex.ShapeElement):
            shapetags.add(v2.ctag)
tags = lambda x: {v.ctag for v in x}  # converts class tuple to set of tags
# pylint:enable=protected-access

rectlike_tags = tags((inkex.PathElement, inkex.Rectangle, inkex.Line, inkex.Polyline))
rect_tag = inkex.Rectangle.ctag
pel_tag = inkex.PathElement.ctag
usetag = inkex.Use.ctag

PTH_CMDS = "".join(list(inkex.paths.PathCommand._letter_to_class.keys()))
pth_cmd_pat = re.compile("[" + re.escape(PTH_CMDS) + "]")
cnt_pth_cmds = lambda d: len(pth_cmd_pat.findall(d))  # count path commands


def isrectangle(elem, includingtransform=True):
    """
    Determines if an element is rectangle-like, considering transformations if
    specified.

    Parameters:
        elem (Element): The element to check.
        includingtransform (bool): Whether to consider transformations in the
            determination.

    Returns:
        tuple: A tuple containing a boolean indicating if the element is a rectangle and
        the path if it is.
    """

    ret = True
    if not includingtransform and elem.tag == rect_tag:
        pth = elem.cpath
    elif elem.tag in rectlike_tags:
        if elem.tag == pel_tag and not (1 <= cnt_pth_cmds(elem.get("d", "")) <= 6):
        # Allow up to 6 (initial M + 4 lines + redundant close path)
            return False
        pth = elem.cpath

        if includingtransform:
            tmat = elem.ctransform.matrix
            x, y = list(
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
            x, y = list(zip(*[(pt.x, pt.y) for pt in pth.end_points]))

        maxsz = max(max(x) - min(x), max(y) - min(y))
        tol = 1e-3 * maxsz
        if len(uniquetol(x, tol)) != 2 or len(uniquetol(y, tol)) != 2:
            ret = False
    elif elem.tag == usetag:
        useel = elem.get_link("xlink:href")
        if useel is not None:
            return isrectangle(useel)
        ret = True
    else:
        ret = False

    if ret:
        if (
            elem.get_link("mask", llget=True) is not None
            or elem.cspecified_style.get_link("filter", elem.croot) is not None
        ):
            ret = False
        elif elem.get_link("clip-path", llget=True) is not None and any(
            not isrectangle(k) for k in list(elem.get_link("clip-path", llget=True))
        ):
            ret = False
    return ret

class InkscapeSystemInfo:
    """
    Discovers and caches Inkscape System info.
    """

    _UNSET = object()  # Sentinel value for unset attributes

    def __init__(self):
        """Initialize InkscapeSystemInfo."""
        self._language = self._UNSET
        self._preferences = self._UNSET
        self._binary_location = self._UNSET
        self._binary_version = self._UNSET

    @property
    def language(self):
        """Get the language used by Inkscape."""
        if self._language is self._UNSET:
            self._language = self.determine_language()
        return self._language

    @property
    def preferences(self):
        """Get the preferences file location."""
        if self._preferences is self._UNSET:
            self._preferences = self.find_preferences()
        return self._preferences

    @property
    def binary_location(self):
        """Get the Inkscape binary location."""
        if self._binary_location is self._UNSET:
            self._binary_location = self.get_binary_location()
        return self._binary_location

    @property
    def binary_version(self):
        """Get the Inkscape binary version."""
        if self._binary_version is self._UNSET:
            self._binary_version = self.get_binary_version()
        return self._binary_version

    def get_binary_version(self):
        """Gets the binary location by calling with --version (slow)"""
        proc = subprocess_repeat([self.binary_location, "--version"])

        match = re.search(r"Inkscape\s+(\S+)\s+\(", str(proc.stdout))
        return match.group(1) if match else None

    @staticmethod
    def get_binary_location():
        """
        Gets the location of the Inkscape binary, checking the system
        path if necessary.
        """

        program = inkex.command.INKSCAPE_EXECUTABLE_NAME
        try:
            return inkex.command.which(program)
        except inkex.command.CommandNotFound as excp:
            # Search the path as a backup (primarily for testing)
            try:
                from shutil import which as warlock

                for sysp in sys.path:
                    if sys.platform == "win32":
                        prog = warlock(program, path=os.environ["PATH"] + ";" + sysp)
                        if prog:
                            return prog
            except ImportError as impe:
                raise ImportError("Failed to import the 'which' function.") from impe
            raise inkex.command.CommandNotFound(
                f"Can not find the command: '{program}'"
            ) from excp

    @staticmethod
    def find_preferences():
        """Attempt to discover preferences.xml"""
        prefspaths = []

        # First check the location of the user extensions directory
        mydir = os.path.dirname(os.path.abspath(__file__))
        file_path = mydir
        while "extensions" in file_path and os.path.basename(file_path) != "extensions":
            file_path = os.path.dirname(file_path)
        prefspaths.append(os.path.join(os.path.dirname(file_path), "preferences.xml"))

        # Try some common default locations based on the home directory
        home = os.path.expanduser("~")
        if sys.platform == "win32":
            appdata = os.getenv("APPDATA")
            if appdata is not None:
                # https://wiki.inkscape.org/wiki/Preferences_subsystem
                prefspaths.append(
                    os.path.join(
                        os.path.abspath(appdata), "inkscape", "preferences.xml"
                    )
                )
            # https://en.wikipedia.org/wiki/Environment_variable#Default_Values_on_Microsoft_Windows
            prefspaths.append(
                os.path.join(home, "AppData", "Roaming", "inkscape", "preferences.xml")
            )
            # https://en.wikipedia.org/wiki/Environment_variable#Default_Values_on_Microsoft_Windows
            # http://tavmjong.free.fr/INKSCAPE/MANUAL/html/Customize-Files.html
            prefspaths.append(
                os.path.join(home, "­Application Data", "­Inkscape", "preferences.xml")
            )
        else:
            if sys.platform == "darwin":
                # test Mac
                prefspaths.append(
                    os.path.join(
                        home,
                        "Library",
                        "Application Support",
                        "org.inkscape.Inkscape",
                        "config",
                        "inkscape",
                        "preferences.xml",
                    )
                )
            # test Linux
            prefspaths.append(
                os.path.join(home, ".config", "inkscape", "preferences.xml")
            )
            # https://wiki.inkscape.org/wiki/Preferences_subsystem#Where_preferences_are_stored
            prefspaths.append(
                os.path.join(home, ".config", "Inkscape", "preferences.xml")
            )
            # https://wiki.inkscape.org/wiki/Preferences_subsystem#Where_preferences_are_stored
            # https://alpha.inkscape.org/vectors/www.inkscapeforum.com/viewtopicc8ae.html?t=1712
            prefspaths.append(os.path.join(home, ".inkscape", "preferences.xml"))

            # Try finding from snap location
            file_path = mydir
            while "snap" in file_path and os.path.basename(file_path) != "snap":
                file_path = os.path.dirname(file_path)
            prefspaths.append(
                os.path.join(
                    os.path.dirname(file_path), ".config", "inkscape", "preferences.xml"
                )
            )

        # Iterate over potential paths and return the first existing one
        for path in prefspaths:
            if os.path.exists(path):
                return path

        return None  # failed

    @staticmethod
    def determine_language(verbose=False):
        """Try to find the language Inkscape is using"""

        def get_ui_language(prefspath):
            proot = etree.parse(prefspath).getroot()
            for k in proot:
                if k.get("id") == "ui" and k.get("language") is not None:
                    return k.get("language")
            return None

        def getlocale_mod():
            # pylint:disable=import-outside-toplevel
            import warnings
            import locale
            # pylint:enable=import-outside-toplevel

            with warnings.catch_warnings():
                # temporary work-around for
                # https://github.com/python/cpython/issues/82986
                # by continuing to use getdefaultlocale() even though it has been
                # deprecated.
                if sys.version_info.minor >= 13:
                    warnings.warn(
                        "This function may not behave as expected in"
                        " Python versions beyond 3.12",
                        FutureWarning,
                    )
                warnings.simplefilter("ignore", category=DeprecationWarning)
                language_code = locale.getdefaultlocale()[0]
            if language_code:
                return language_code
            return "en-US"

        # First, try to get the language from preferences.xml
        pxml = InkscapeSystemInfo().find_preferences()
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


inkex.inkscape_system_info = InkscapeSystemInfo()  # type: ignore


def subprocess_repeat(argin,cwd=None):
    """
    In the event of a timeout, repeats a subprocess call several times.

    Parameters:
        argin (list): The command and arguments to run in the subprocess.

    Returns:
        CompletedProcess: The result from the subprocess call.
    """
    base_timeout = 60
    nattempts = 6
    import subprocess

    nfails = 0
    ntime = 0
    for i in range(nattempts):
        timeout = base_timeout * 2**i
        try:
            os.environ["SELF_CALL"] = "true"  # seems to be needed for 1.3
            proc = subprocess.run(
                argin,
                shell=False,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True, cwd=cwd
            )
            break
        except subprocess.TimeoutExpired:
            nfails += 1
            ntime += timeout
    if nfails == nattempts:
        raise TimeoutError(
            "\nThe call to the Inkscape binary timed out "
            + str(nattempts)
            + " times in "
            + str(ntime)
            + " seconds.\n\n"
            + "This may be a temporary issue; try running the extension again."
        )
    else:
        return proc


# Get default style attributes
try:
    default_style_atts = {a: v[1] for a, v in all_properties.items()}  # type: ignore
except TypeError:
    default_style_atts = {
        a: "".join([str(t.value) for t in v.default_value])
        for a, v in all_properties.items()
    }  # type: ignore
default_style_atts["font-variant-ligatures"] = "normal"  # missing


comment_tag = lxml.etree.Comment("").tag


def list2(elem):
    """Returns non-comment children of an element."""
    return [k for k in list(elem) if not (k.tag == comment_tag)]


conv2 = {k: v / CONVERSIONS["px"] for k, v in CONVERSIONS.items()}


@lru_cache(maxsize=None)
def ipx(strin):
    """
    Implicit pixel function
    For many properties, a size specification of '1px' actually means '1uu'
    Even if the size explicitly says '1mm' and the user units are mm, this will be
    first converted to px and then interpreted to mean user units. (So '1mm' would
    up being bigger than 1 mm). This returns the size as Inkscape will interpret it
    (in uu).
      No unit: Assumes 'px'
      Invalid unit: Returns None
    """
    try:
        ret = BOTH_MATCH.match(strin)
        value = float(ret.groups()[0])
        from_unit = ret.groups()[-1] or "px"
        return value * conv2[from_unit]
    except (AttributeError, TypeError):
        return None


# pylint:disable=invalid-name
class bbox:
    """
    A modified bounding box class.
    """

    __slots__ = ("isnull", "x1", "x2", "y1", "y2", "xc", "yc", "w", "h", "sbb")

    def __init__(self, bb):
        """Initialize bbox."""
        if bb is not None:
            self.isnull = False
            if len(bb) == 2:  # allow tuple of two points ((x1,y1),(x2,y2))
                self.sbb = [
                    min(bb[0][0], bb[1][0]),
                    min(bb[0][1], bb[1][1]),
                    abs(bb[0][0] - bb[1][0]),
                    abs(bb[0][1] - bb[1][1]),
                ]
            else:
                self.sbb = bb[:]  # standard bbox
            self.x1, self.y1, self.w, self.h = self.sbb
            self.x2 = self.x1 + self.w
            self.y2 = self.y1 + self.h
            self.xc = (self.x1 + self.x2) / 2
            self.yc = (self.y1 + self.y2) / 2
        else:
            self.isnull = True

    def copy(self):
        """Copy the bounding box."""
        ret = bbox.__new__(bbox)
        ret.isnull = self.isnull
        if not self.isnull:
            ret.x1 = self.x1
            ret.x2 = self.x2
            ret.y1 = self.y1
            ret.y2 = self.y2
            ret.xc = self.xc
            ret.yc = self.yc
            ret.w = self.w
            ret.h = self.h
            ret.sbb = self.sbb[:]
        return ret

    def transform(self, xform):
        """Transform the bounding box."""
        if not (self.isnull) and xform is not None:
            tr1 = xform.apply_to_point([self.x1, self.y1])
            tr2 = xform.apply_to_point([self.x2, self.y2])
            tr3 = xform.apply_to_point([self.x1, self.y2])
            tr4 = xform.apply_to_point([self.x2, self.y1])
            return bbox(
                [
                    min(tr1[0], tr2[0], tr3[0], tr4[0]),
                    min(tr1[1], tr2[1], tr3[1], tr4[1]),
                    max(tr1[0], tr2[0], tr3[0], tr4[0])
                    - min(tr1[0], tr2[0], tr3[0], tr4[0]),
                    max(tr1[1], tr2[1], tr3[1], tr4[1])
                    - min(tr1[1], tr2[1], tr3[1], tr4[1]),
                ]
            )
        return bbox(None)

    def intersect(self, bb2):
        """Check if bounding boxes intersect."""
        return (abs(self.xc - bb2.xc) * 2 < (self.w + bb2.w)) and (
            abs(self.yc - bb2.yc) * 2 < (self.h + bb2.h)
        )

    def union(self, bb2):
        """Get the union of two bounding boxes."""
        if isinstance(bb2, list):
            bb2 = bbox(bb2)
        if not (self.isnull) and not bb2.isnull:
            minx = min((self.x1, self.x2, bb2.x1, bb2.x2))
            maxx = max((self.x1, self.x2, bb2.x1, bb2.x2))
            miny = min((self.y1, self.y2, bb2.y1, bb2.y2))
            maxy = max((self.y1, self.y2, bb2.y1, bb2.y2))
            return bbox([minx, miny, maxx - minx, maxy - miny])
        if self.isnull and not bb2.isnull:
            return bb2
        return self  # bb2 is empty

    def intersection(self, bb2):
        """Get the intersection of two bounding boxes."""
        if isinstance(bb2, list):
            bb2 = bbox(bb2)
        if not (self.isnull):
            minx = max([self.x1, bb2.x1])
            maxx = min([self.x2, bb2.x2])
            miny = max([self.y1, bb2.y1])
            maxy = min([self.y2, bb2.y2])
            if maxx < minx or maxy < miny:
                return bbox(None)
            return bbox([minx, miny, maxx - minx, maxy - miny])
        return bbox(bb2.sbb)

    def __mul__(self, scl):
        """Scale the bounding box."""
        return bbox([self.x1 * scl, self.y1 * scl, self.w * scl, self.h * scl])


# pylint:enable=invalid-name
