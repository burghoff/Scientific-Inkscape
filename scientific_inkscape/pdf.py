#!/usr/bin/env python
# coding=utf-8
#
# Copyright (c) 2025 David Burghoff <burghoff@utexas.edu>
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

DEBUG_PDF = False

import os, platform, sys
from shutil import which

MAX_THREADS_OFFICE = 1
MAX_THREADS_LIBREOFFICE = 1

def find_soffice():
    """
    Return the full path to LibreOffice's soffice executable.
    Raises FileNotFoundError if not found.
    """
    system = platform.system()

    # First try PATH
    soffice_path = which("soffice")
    if soffice_path:
        return soffice_path

    possible_paths = []
    if system == "Windows":
        possible_paths = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
    elif system == "Darwin":  # macOS
        possible_paths = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/usr/local/bin/soffice",
        ]
    elif system == "Linux":
        possible_paths = [
            "/usr/bin/soffice",
            "/usr/local/bin/soffice",
            "/snap/bin/libreoffice",
        ]

    for path in possible_paths:
        if os.path.isfile(path):
            return path

    raise FileNotFoundError(
        "LibreOffice (soffice) executable not found. "
        "PDF conversion relies on LibreOffice, the free and open source document creator. "
        "Please ensure LibreOffice is installed and added to your PATH."
    )


import threading
sema_office = threading.Semaphore(MAX_THREADS_OFFICE)
sema_libreoffice = threading.Semaphore(MAX_THREADS_LIBREOFFICE)

def make_pdf_libreoffice(input_file, output_file):
    import subprocess
    soffice = find_soffice()
    output_dir = os.path.split(input_file)[0]
    cmd = [
        soffice,
        "--headless",
        "--convert-to", "pdf:writer_pdf_Export",
        "--outdir", output_dir,
        input_file
    ]
    with sema_libreoffice:
        _ = subprocess.run(cmd, capture_output=True, text=True)
    generated_pdf = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(input_file))[0]}.pdf")
    from autoexporter import repeat_move
    repeat_move(generated_pdf, output_file)
    _debug_copy(output_file, label="libreoffice")

import time
import tempfile
import subprocess
from pathlib import Path


# ---- Debug flag ----
# When True, every SVG and PDF that flows through the PDF generation pipeline
# -- especially the SVG -> PDF marker-replacement path used by
# replace_color_markers_with_svgs / export_svg_to_pdf -- is copied into a
# temp folder for inspection. The folder is created lazily on first use and
# its location is printed once.
import shutil as _debug_shutil

_debug_dir = None
_debug_lock = threading.Lock()
_debug_counter = 0

def _debug_dir_path():
    """Return the (lazily created) debug folder, printing its path the first time."""
    global _debug_dir
    if _debug_dir is not None:
        return _debug_dir
    with _debug_lock:
        if _debug_dir is None:
            _debug_dir = tempfile.mkdtemp(prefix="si_pdf_debug_")
            print("[pdf debug] copying SVGs/PDFs to: {}".format(_debug_dir),
                  file=sys.stderr, flush=True)
    return _debug_dir

def _debug_copy(src_path, label=None):
    """If DEBUG_PDF is set and src_path exists, copy it into the debug folder.

    Files are prefixed with a monotonic counter so the order of operations is
    visible from the filenames alone. ``label`` is an optional short string
    woven into the destination filename to make the source step easy to
    identify (e.g. 'svg_in', 'svg_out', 'libreoffice', 'input_pdf').
    Returns the destination path on success, or None.
    """
    if not DEBUG_PDF:
        return None
    try:
        if not src_path or not os.path.exists(src_path):
            return None
        global _debug_counter
        with _debug_lock:
            _debug_counter += 1
            n = _debug_counter
        d = _debug_dir_path()
        base = os.path.basename(src_path)
        name = "{:04d}_{}_{}".format(n, label, base) if label else "{:04d}_{}".format(n, base)
        dst = os.path.join(d, name)
        _debug_shutil.copy2(src_path, dst)
        return dst
    except Exception as e:
        try:
            print("[pdf debug] failed to copy {}: {}".format(src_path, e),
                  file=sys.stderr, flush=True)
        except Exception:
            pass
        return None


def _debug_print(msg):
    """Emit a verbose debug line to stderr when DEBUG_PDF is set.

    Used to narrate the marker-detection / replacement pipeline -- especially
    *why* a candidate image was rejected as a marker. The DEBUG_PDF guard at
    the top keeps the cost negligible when debugging is off.
    """
    if not DEBUG_PDF:
        return
    try:
        print("[pdf debug] {}".format(msg), file=sys.stderr, flush=True)
    except Exception:
        pass


POWERSHELL_HELPER = r"""
param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath
)

$in  = [System.IO.Path]::GetFullPath($InputPath)
$out = [System.IO.Path]::GetFullPath($OutputPath)
$ext = [System.IO.Path]::GetExtension($in).ToLowerInvariant()

# Word constants
$wdFormatPDF = 17
$wdDoNotSaveChanges = 0

# PowerPoint constants
$ppSaveAsPDF = 32

$word = $null
$doc = $null

$pp = $null
$pres = $null
$createdApp = $false
$openedHere = $false

try {
    if ($ext -in @(".doc", ".docx", ".rtf")) {
        # --- Word path (unchanged) ---
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false
        $word.DisplayAlerts = 0
        # Open ReadOnly, no conversions
        $doc = $word.Documents.Open($in, [ref]$false, [ref]$true)
        # Hide revision/comment markup so the PDF is the final rendition.
        try {
            $doc.ActiveWindow.View.ShowRevisionsAndComments = $false
            $doc.ActiveWindow.View.RevisionsView = 0   # wdRevisionsViewFinal
        } catch {}
        $doc.SaveAs2([ref]$out, [ref]$wdFormatPDF)
    }
    elseif ($ext -in @(".ppt", ".pptx")) {
        # --- PowerPoint path (do not close user's instance) ---
        $pp   = $null
        $pres = $null
        $openedHere  = $false
        $hadInstance = $false
    
        # Ensure output dir exists; clear existing PDF
        $outDir = [System.IO.Path]::GetDirectoryName($out)
        if (-not [string]::IsNullOrEmpty($outDir) -and -not (Test-Path -LiteralPath $outDir)) {
            New-Item -ItemType Directory -Path $outDir -Force | Out-Null
        }
        if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Force }
    
        # Attach if running; else create our own
        try {
            $pp = [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application')
            $hadInstance = $true
        } catch {
            $pp = New-Object -ComObject PowerPoint.Application
            $hadInstance = $false
            try { $pp.Visible = $false } catch {}
            try { $pp.DisplayAlerts = 1 } catch {}  # ppAlertsNone
        }
    
        # Record presentation count BEFORE opening
        $preCount = 0
        try { $preCount = [int]$pp.Presentations.Count } catch {}
    
        # Open file headlessly in same process
        # Open(FileName, ReadOnly, Untitled, WithWindow)
        $pres = $pp.Presentations.Open($in, $true, $false, $false)
        $openedHere = $true
    
        # Export via ExportAsFixedFormat (more reliable headless than SaveAs)
        $ppFixedFormatTypePDF   = 2  # PDF
        $ppFixedFormatIntent    = 2  # Print
        $ppPrintAll             = 1
    
        $ok = $false
        try {
            $pres.ExportAsFixedFormat(
                $out,
                $ppFixedFormatTypePDF,
                $ppFixedFormatIntent,
                $true,       # FrameSlides
                $ppPrintAll, # RangeType
                1, 1,        # Start/End ignored for All
                $false,      # IncludeDocProps
                $false,      # KeepIRMSettings
                $false,      # DocStructureTags
                $false,      # BitmapMissingFonts
                $false       # UseISO19005_1 (PDF/A)
            )
            $ok = $true
        } catch {
            # Fallback to SaveAs if needed
            try {
                $ppSaveAsPDF = 32
                $pres.SaveAs($out, $ppSaveAsPDF)
                $ok = $true
            } catch { throw }
        }
    
        if (-not $ok -or -not (Test-Path -LiteralPath $out)) {
            throw "PowerPoint PDF export failed."
        }
    
        # Close only what we opened
        if ($openedHere -and $pres -ne $null) { $pres.Close() | Out-Null }
    
        # Quit ONLY if we created the instance and it's still 'ours'
        if (-not $hadInstance -and $pp -ne $null) {
            $postCount = 0
            try { $postCount = [int]$pp.Presentations.Count } catch {}
            if ($postCount -eq 0) { try { $pp.Quit() | Out-Null } catch {} }
        }
    }



}
catch {
    exit 2
}
finally {
    # Word cleanup (unchanged)
    if ($doc -ne $null)  { $doc.Close([ref]$wdDoNotSaveChanges) | Out-Null }
    if ($word -ne $null) { $word.Quit() | Out-Null }

    # PowerPoint cleanup: only close/quit what we created
    if ($openedHere -and $pres -ne $null) { $pres.Close() | Out-Null }
    if ($createdApp -and $pp -ne $null)   { $pp.Quit()  | Out-Null }
}
exit 0
"""

MAC_OFFICE_APPLESCRIPT = r'''
on run argv
    if (count of argv) is not 2 then
        error "Expected 2 arguments (input, output)"
    end if

    set inPosix to item 1 of argv
    set outPosix to item 2 of argv

    ----------------------------------------------------------------------
    -- Decide whether to use Word or PowerPoint based on file extension
    ----------------------------------------------------------------------
    set AppleScript's text item delimiters to "."
    set ext to ""
    if inPosix contains "." then
        set ext to last text item of inPosix
    end if
    set AppleScript's text item delimiters to ""

    set isWord to false
    if (ext is "doc" or ext is "docx" or ext is "rtf") then
        set isWord to true
    else if (ext is "ppt" or ext is "pptx") then
        set isWord to false
    else
        error "Unsupported file extension for Office conversion: " & ext
    end if

    set officeAppName to ""
    if isWord then
        set officeAppName to "Microsoft Word"
    else
        set officeAppName to "Microsoft PowerPoint"
    end if

    set inFile to POSIX file inPosix
    set outHFS to (POSIX file outPosix as text)
    set outFile to POSIX file outPosix

    ----------------------------------------------------------------------
    -- Remember which app was frontmost before we do anything
    ----------------------------------------------------------------------
    set frontAppName to ""
    tell application "System Events"
        try
            set frontAppName to name of first process whose frontmost is true
        end try
    end tell

    ----------------------------------------------------------------------
    -- Ensure the appropriate Office app is running
    ----------------------------------------------------------------------
    if isWord then
        tell application "Microsoft Word" to launch
    else
        tell application "Microsoft PowerPoint" to launch
    end if

    -- Wait until the Office process exists
    tell application "System Events"
        repeat until exists process officeAppName
            delay 0.05
        end repeat
    end tell

    ----------------------------------------------------------------------
    -- Open and prepare the document / presentation
    ----------------------------------------------------------------------
    set theItem to missing value

    if isWord then
        tell application "Microsoft Word"
            set priorItem to missing value
            if (count of documents) > 0 then set priorItem to active document

            open inFile

            -- wait until theItem becomes available
            set itemReady to false
            repeat 1000 times -- up to ~10 s total
                try
                    set theItem to active document
                    set itemReady to true
                    exit repeat
                on error
                    delay 0.01
                end try
            end repeat
            if not itemReady then error "Word never exposed active document"

            -- restore focus to prior doc inside Word, if any
            if priorItem is not missing value then
                try
                    set active document to priorItem
                end try
            end if
        end tell
    else
        tell application "Microsoft PowerPoint"
            set priorItem to missing value
            if (count of presentations) > 0 then set priorItem to active presentation

            open inFile

            -- wait until theItem becomes available
            set itemReady to false
            repeat 1000 times -- up to ~10 s total
                try
                    set theItem to active presentation
                    set itemReady to true
                    exit repeat
                on error
                    delay 0.01
                end try
            end repeat
            if not itemReady then error "PowerPoint never exposed active presentation"

            -- restore focus to prior presentation inside PowerPoint, if any
            if priorItem is not missing value then
                try
                    set active presentation to priorItem
                end try
            end if
        end tell
    end if

    ----------------------------------------------------------------------
    -- FIRST restore: put original app back on top and hide Office if needed
    ----------------------------------------------------------------------
    my restoreFrontApp(frontAppName, officeAppName)

    ----------------------------------------------------------------------
    -- Save as PDF and close the temporary item, with extra restores
    ----------------------------------------------------------------------
    if isWord then
        tell application "Microsoft Word"
            -- Start PDF export
            save as theItem file name outHFS file format format PDF

            -- SECOND restore: immediately after starting the save
            my restoreFrontApp(frontAppName, officeAppName)

            close theItem saving no

            if (count of documents) is 0 then quit
        end tell
    else
        tell application "Microsoft PowerPoint"
            -- Start PDF export
            save theItem in outFile as save as PDF

            -- SECOND restore: immediately after starting the save
            my restoreFrontApp(frontAppName, officeAppName)

            close theItem saving no

            if (count of presentations) is 0 then quit
        end tell
    end if

    -- Tiny pause, then THIRD restore to catch any late focus grabs
    delay 0.2
    my restoreFrontApp(frontAppName, officeAppName)
end run

on restoreFrontApp(appName, officeAppName)
    if appName is "" then return

    -- Activate the original app
    try
        tell application appName to activate
    end try

    -- If the original app is NOT the Office app, hide the Office windows so they
    -- can't sit visually on top even if macOS still considers them key.
    try
        if appName is not officeAppName then
            tell application "System Events"
                if exists process officeAppName then
                    set visible of process officeAppName to false
                end if
            end tell
        end if
    end try
end restoreFrontApp
'''




def _make_pdf_office_windows(in_path: Path,
                             out_path: Path,
                             retries: int,
                             delay: float) -> str:
    """
    Windows implementation: uses PowerShell COM automation (Word/PowerPoint)
    """
    # Write temporary PowerShell helper
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as tf:
        tf.write(POWERSHELL_HELPER)
        ps1_path = Path(tf.name)

    try:
        for attempt in range(1, retries + 1):
            with sema_office:
                proc = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy", "Bypass",
                        "-WindowStyle", "Hidden",
                        "-File", str(ps1_path),
                        str(in_path),
                        str(out_path),
                    ],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            if proc.returncode == 0:
                _debug_copy(str(out_path), label="office_win")
                return str(out_path)
            if proc.returncode == 3:
                raise RuntimeError(f"Unsupported file type: {in_path.suffix}")
            if attempt < retries:
                time.sleep(delay)
            else:
                raise RuntimeError(f"Conversion failed (exit code {proc.returncode}).")
    finally:
        try:
            ps1_path.unlink(missing_ok=True)
        except Exception:
            pass


def _make_pdf_office_macos(in_path: Path,
                           out_path: Path,
                           retries: int,
                           delay: float, exporter) -> str:
    """
    macOS implementation: uses AppleScript via `osascript`
    to drive Word / PowerPoint directly.
    """
    ext = in_path.suffix.lower()
    if ext not in (".doc", ".docx", ".rtf", ".ppt", ".pptx"):
        raise RuntimeError(f"Unsupported file type: {ext}")

    script_text = MAC_OFFICE_APPLESCRIPT

    with tempfile.NamedTemporaryFile("w", suffix=".applescript",
                                     delete=False, encoding="utf-8") as tf:
        tf.write(script_text)
        scpt_path = Path(tf.name)

    try:
        for attempt in range(1, retries + 1):
            with sema_office:
                proc = subprocess.run(
                    ["osascript", str(scpt_path), str(in_path), str(out_path)],
                    capture_output=True,
                    text=True,
                )
                # exporter.prints("osascript stdout:\n" + (proc.stdout or ""))
                # exporter.prints("osascript stderr:\n" + (proc.stderr or ""))
            if proc.returncode == 0 and out_path.exists():
                _debug_copy(str(out_path), label="office_mac")
                return str(out_path)
            if attempt < retries:
                time.sleep(delay)
            else:
                raise RuntimeError(
                    "Conversion failed on macOS (exit code {code}).\n"
                    "stdout:\n{stdout}\n"
                    "stderr:\n{stderr}".format(
                        code=proc.returncode,
                        stdout=proc.stdout or "",
                        stderr=proc.stderr or "",
                    )
                )

    finally:
        try:
            scpt_path.unlink()
        except Exception:
            pass


def make_pdf_office(input_path, output_path=None, exporter=None, retries=3, delay=1.0):
    """
    Convert DOC/DOCX/RTF or PPT/PPTX -> PDF using Office:
      - Windows: Word/PowerPoint via PowerShell COM.
      - macOS: Word/PowerPoint via AppleScript (`osascript`).

    Runs silently (no console output). Returns output path on success.

    Raises:
      - FileNotFoundError if input missing
      - RuntimeError on conversion failure or unsupported extension
    """
    in_path = Path(input_path).resolve()
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {in_path}")
    if output_path is None:
        out_path = in_path.with_suffix(".pdf")
    else:
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform.startswith("win"):
        return _make_pdf_office_windows(in_path, out_path, retries, delay)
    elif sys.platform == "darwin":
        return _make_pdf_office_macos(in_path, out_path, retries, delay, exporter)
    else:
        raise RuntimeError(
            "Office-based PDF conversion is only supported on Windows and macOS."
        )

# Backward-compat alias if existing code calls the old name
make_pdf_word = make_pdf_office

from typing import Dict, Optional

mydir = os.path.dirname(os.path.abspath(__file__))
packages = os.path.join(mydir, "packages")
if packages not in sys.path:
    sys.path.append(packages)
    
import os, sys

here = os.path.dirname(os.path.abspath(__file__))
pkgdir = os.path.join(here, "packages")

# On Python < 3.11, pypdf imports Self/TypeAlias/TypeGuard from
# typing_extensions, which not every Inkscape-bundled Python ships (1.0 and
# 1.2 do not). Fall back to the vendored copy only when the installed one is
# absent or lacks those symbols, so a working installation is never shadowed.
if sys.version_info < (3, 11):
    try:
        from typing_extensions import Self, TypeAlias, TypeGuard  # noqa: F401
    except ImportError:
        sys.modules.pop("typing_extensions", None)
        te_path = os.path.join(pkgdir, "typing_extensions-4.13.2")
        if te_path not in sys.path:
            sys.path.insert(0, te_path)

# pypdf 5.9.0 is the newest release that runs on all bundled Pythons
# (pypdf >= 6.0 requires Python >= 3.9, but Inkscape 1.0 bundles 3.8)
pypdf_path = os.path.join(pkgdir, "pypdf-5.9.0")
if pypdf_path not in sys.path:
    sys.path.insert(0, pypdf_path)


from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject, IndirectObject
from pypdf.generic import FloatObject
from pypdf.generic import DictionaryObject

# ---- Inkscape export (same conventions as AutoExporter) ----
def _inkscape_bin():
    # pull the Inkscape binary location the same way AutoExporter does
    # (requires dhelpers + inkex)
    import dhelpers as dh
    return dh.inkex.inkscape_system_info.binary_location  # noqa

from autoexporter import Exporter, ORIG_KEY, get_svg


def _is_ae_output_svg(svg_path: str) -> bool:
    """Return True iff the SVG carries AutoExporter's ORIG_KEY marker
    (a hidden <text> direct child of the root containing 'si_ae_original_filename').

    Uses raw lxml for speed — this is meant to be a cheap probe. If parsing
    fails for any reason, return False so the caller routes through the
    full AE pipeline (which uses inkex's more permissive loader)."""
    try:
        from lxml import etree as LET
        parser = LET.XMLParser(huge_tree=True, recover=True)
        root = LET.parse(svg_path, parser).getroot()
        if root is None:
            return False
        SVG_TEXT = "{http://www.w3.org/2000/svg}text"
        for child in root:
            if (child.tag == SVG_TEXT
                    and child.text is not None
                    and ORIG_KEY in child.text):
                return True
    except Exception:
        pass
    return False


def _strip_inkscape_pages(in_svg_path: str, out_svg_path: str) -> None:
    """Write a copy of in_svg_path to out_svg_path with all <inkscape:page>
    elements removed, so the Exporter treats it as a single-page document
    and exports just the viewBox (the only thing Word / PowerPoint render).

    Uses the codebase's own load/save helpers (get_svg + dh.overwrite_svg)
    so the file is guaranteed to round-trip through the rest of the AE
    pipeline. Raw lxml.etree.parse + tree.write produces files that inkex's
    loader sometimes can't read back, which causes get_svg to return None
    and visible_descendants to crash on `list(svg)`."""
    import dhelpers as dh
    svg = get_svg(in_svg_path)
    INK_PAGE = "{http://www.inkscape.org/namespaces/inkscape}page"
    for pg in list(svg.iter(INK_PAGE)):
        parent = pg.getparent()
        if parent is not None:
            parent.remove(pg)
    dh.overwrite_svg(svg, out_svg_path)
    
def export_svg_to_pdf(svg_path: str, exporter: Exporter) -> str:
    """Export SVG -> PDF next to the SVG.

    - If the SVG was produced by AutoExporter (carries the ORIG_KEY marker),
      use a simple Inkscape CLI call. AE outputs are already preprocessed.
    - Otherwise (e.g. a hand-made SVG someone dropped into a Word doc),
      run the full AE export pipeline, with margin=0 and viewBox-only output
      since Word/PowerPoint render only a single page.
    """
    pdf_path = os.path.splitext(svg_path)[0] + ".pdf"
    import dhelpers as dh

    _debug_copy(svg_path, label="svg_in")

    if _is_ae_output_svg(svg_path):
        # Simple, fast path for AE-processed SVGs.
        args = [
            _inkscape_bin(),
            "--export-background", "#ffffff",
            "--export-background-opacity", "1.0",
            "--export-dpi", "600",
            "--export-filename", pdf_path,
            svg_path,
        ]
        exporter.check(dh.subprocess_repeat, args, finalization=True)
        _debug_copy(pdf_path, label="svg_out_ae")
        return pdf_path

    # Full AE pipeline for foreign SVGs.
    import tempfile, shutil as _sh
    from types import SimpleNamespace

    tmp_dir = tempfile.mkdtemp(prefix="si_ae_subexport_")
    try:
        # 1. Strip <inkscape:page> elements so we get a single viewBox-sized PDF.
        stripped_svg = os.path.join(tmp_dir, os.path.basename(svg_path))
        _strip_inkscape_pages(svg_path, stripped_svg)
        # Capture the intermediate SVG before tmp_dir is wiped in the finally.
        _debug_copy(stripped_svg, label="svg_stripped")

        # 2. Inherit all of the calling exporter's settings, then override
        #    the few we need to change for a Word/PPT-bound export.
        opts = SimpleNamespace(**dict(vars(exporter)))
        opts.formats = ["pdf"]
        opts.margin = 0
        opts.original_file = svg_path
        opts.outtemplate = pdf_path[:-4] + ".svg"
        opts.display_name = "{0} in {1}".format(
            os.path.basename(svg_path), os.path.basename(exporter.filein)
        )
        
        # Exporter.__init__ sets self.filein=fin and then does
        # self.__dict__.update(vars(opts)) — so an inherited `filein` would
        # overwrite the stripped_svg we pass in. Drop it.
        opts.__dict__.pop("filein", None)
        
        # linked_locations from the parent are relative to the docx, not our SVG.
        # Force the sub-Exporter to scan the SVG for its own linked images.
        opts.exportnow = False
        opts.linked_locations = {}
        
        if exporter.prints:
            exporter.prints("{} : Beginning export".format(opts.display_name))
        Exporter(stripped_svg, opts).export_all()
    finally:
        _sh.rmtree(tmp_dir, ignore_errors=True)

    _debug_copy(pdf_path, label="svg_out_foreign")
    return pdf_path


# ---- Minimal PDF matrix helpers (column-vector form) ----
def _mat_from(a,b,c,d,e,f):
    return [[a, c, e],
            [b, d, f],
            [0, 0, 1]]

def _mat_mul(A, B):
    return [
        [A[0][0]*B[0][0] + A[0][1]*B[1][0] + A[0][2]*B[2][0],
         A[0][0]*B[0][1] + A[0][1]*B[1][1] + A[0][2]*B[2][1],
         A[0][0]*B[0][2] + A[0][1]*B[1][2] + A[0][2]*B[2][2]],
        [A[1][0]*B[0][0] + A[1][1]*B[1][0] + A[1][2]*B[2][0],
         A[1][0]*B[0][1] + A[1][1]*B[1][1] + A[1][2]*B[2][1],
         A[1][0]*B[0][2] + A[1][1]*B[1][2] + A[1][2]*B[2][2]],
        [0, 0, 1],
    ]

def _apply_mat(M, x, y):
    return (M[0][0]*x + M[0][1]*y + M[0][2],
            M[1][0]*x + M[1][1]*y + M[1][2])

def _resolve_xobj(xobjs, op_name):
    if not xobjs:
        return None
    raw = getattr(op_name, "name", op_name)
    if isinstance(raw, bytes):
        raw = raw.decode("latin1", errors="ignore")
    for k in (raw, str(raw).lstrip("/"), "/" + str(raw).lstrip("/")):
        nk = NameObject(k)
        if nk in xobjs:
            xo = xobjs[nk]
            if isinstance(xo, IndirectObject):
                try:
                    xo = xo.get_object()
                except Exception:
                    return None
            return xo
    return None

# ---- PNG predictor decoding for 8-bit RGB (filters 0..4) ----
def _paeth(a, b, c):
    # a=left, b=up, c=up-left
    p = a + b - c
    pa = abs(p - a); pb = abs(p - b); pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c

def _undo_png_predictors_rgb8(data: bytes, width: int, height: int) -> bytes:
    """Return raw RGB (no filter bytes). Handles filters 0..4 for 8-bit, 3-channel."""
    stride = 3 * width
    out = bytearray(height * stride)
    src = memoryview(data)
    pos = 0
    prev = bytearray(stride)  # prior row
    for row in range(height):
        f = src[pos]; pos += 1
        row_bytes = bytearray(src[pos:pos+stride]); pos += stride
        if f == 0:  # None
            rec = row_bytes
        elif f == 1:  # Sub
            rec = bytearray(row_bytes)
            for i in range(stride):
                left = rec[i-3] if i >= 3 else 0
                rec[i] = (rec[i] + left) & 0xFF
        elif f == 2:  # Up
            rec = bytearray(row_bytes)
            for i in range(stride):
                rec[i] = (rec[i] + prev[i]) & 0xFF
        elif f == 3:  # Average
            rec = bytearray(row_bytes)
            for i in range(stride):
                left = rec[i-3] if i >= 3 else 0
                up = prev[i]
                rec[i] = (rec[i] + ((left + up) // 2)) & 0xFF
        elif f == 4:  # Paeth
            rec = bytearray(row_bytes)
            for i in range(stride):
                left = rec[i-3] if i >= 3 else 0
                up = prev[i]
                up_left = prev[i-3] if i >= 3 else 0
                rec[i] = (rec[i] + _paeth(left, up, up_left)) & 0xFF
        else:
            # Unknown filter -> bail
            return b""
        out[row*stride:(row+1)*stride] = rec
        prev = rec
    return bytes(out)


def _is_rgb_colorspace(cs):
    # Resolve indirect color-space objects
    try:
        if hasattr(cs, "get_object"):  # works for IndirectObject
            cs = cs.get_object()
    except Exception:
        # If we can't resolve, fall back to simple check
        pass

    # Accept /DeviceRGB
    if not isinstance(cs, list):
        return str(cs) == "/DeviceRGB"

    # At this point cs is a list, e.g. [/DeviceRGB ...] or [/ICCBased profile]
    if any(str(x) == "/DeviceRGB" for x in cs):
        return True

    if len(cs) >= 2 and str(cs[0]) == "/ICCBased":
        try:
            profile = cs[1].get_object()
            alt = profile.get("/Alternate", None)
            return str(alt) == "/DeviceRGB"
        except Exception:
            return False

    return False


def _decode_image_rows(raw, w, h, bpp, predictor):
    """Generator yielding each decoded row of an 8-bit-per-channel image.

    Handles both PNG-style predictor (10..15) and the no-predictor case in a
    single helper so callers can walk RGB and SMask streams in lockstep.

    Yields ``(row_bytes, None)`` per row on success, or ``(None, error_msg)``
    once when the stream is malformed or uses an unsupported filter; the
    generator stops after a single error yield.
    """
    stride = bpp * w

    if predictor < 10:
        # No predictor: stream is just stride*h raw sample bytes.
        if len(raw) != stride * h:
            yield None, ("data length mismatch (no predictor): got {}, "
                         "expected {}").format(len(raw), stride * h)
            return
        for r in range(h):
            yield bytes(raw[r * stride:(r + 1) * stride]), None
        return

    # PNG-style predictor: each row is [filter byte][stride sample bytes].
    if len(raw) != (1 + stride) * h:
        yield None, ("predictor data length mismatch: got {}, "
                     "expected {} for {}x{}").format(
                         len(raw), (1 + stride) * h, w, h)
        return

    prev = bytearray(stride)
    src = memoryview(raw)
    for row in range(h):
        base = row * (1 + stride)
        f = src[base]
        line = src[base + 1:base + 1 + stride]
        if f == 0:
            rec = bytearray(line)
        elif f == 1:  # Sub
            rec = bytearray(stride)
            for i in range(stride):
                left = rec[i - bpp] if i >= bpp else 0
                rec[i] = (line[i] + left) & 0xFF
        elif f == 2:  # Up
            rec = bytearray(stride)
            for i in range(stride):
                rec[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:  # Average
            rec = bytearray(stride)
            for i in range(stride):
                left = rec[i - bpp] if i >= bpp else 0
                up = prev[i]
                rec[i] = (line[i] + ((left + up) // 2)) & 0xFF
        elif f == 4:  # Paeth
            rec = bytearray(stride)
            for i in range(stride):
                left = rec[i - bpp] if i >= bpp else 0
                up = prev[i]
                up_left = prev[i - bpp] if i >= bpp else 0
                rec[i] = (line[i] + _paeth(left, up, up_left)) & 0xFF
        else:
            yield None, "unknown PNG filter byte {} at row {}".format(f, row)
            return
        yield bytes(rec), None
        prev = rec


def _try_get_uniform_rgb_hex_from_ximage(ximg, name=None) -> Optional[str]:
    """
    Decode an image XObject and, if its visible (fully-opaque) pixels are all
    a single RGB color, return that color as lowercase 'rrggbb'. Otherwise
    return None.

    Why this isn't simply "every pixel must match":

      - Marker PNGs are written as 9x9 by office.py, but PDF generators
        (LibreOffice, Word, PowerPoint) routinely resize embedded images.
        Size is therefore not used for matching.
      - When a generator resizes a marker, it often splits the result into
        an RGB image + grayscale /SMask, with anti-aliased edge pixels whose
        RGB drifts by 1-2 levels. Those edge pixels have alpha < 255; the
        interior keeps the marker's exact color at alpha == 255.

    Rule:
      - If no /SMask: every pixel must match (early exit on first deviation).
      - If /SMask present and same dimensions: only fully-opaque pixels
        (alpha == 255) participate in the uniformity check; anti-aliased
        edge pixels are ignored. An image with no opaque pixels at all is
        rejected (it's invisible).

    Decoding is row-by-row with early exit so large photographic images get
    rejected in milliseconds instead of being fully decoded.

    ``name`` is an optional XObject reference name (e.g. '/Im5') used purely
    for verbose debug logging when DEBUG_PDF is enabled.
    """
    label = "image {}".format(name) if name else "image"
    try:
        w = int(ximg.get("/Width", 0))
        h = int(ximg.get("/Height", 0))
        bpc = int(ximg.get("/BitsPerComponent", 8))
        cs = ximg.get("/ColorSpace", "/DeviceRGB")
        smask = ximg.get("/SMask", None)
    except Exception as e:
        _debug_print("{}: rejected (metadata read failed: {})".format(label, e))
        return None

    # Indexed-color images get their own decoder (OneNote's PDF export
    # re-encodes the 9x9 marker PNGs as 4-bit /Indexed with a palette of
    # [black, white, marker color]).
    csr = cs
    try:
        if hasattr(csr, "get_object"):
            csr = csr.get_object()
    except Exception:
        pass
    if (isinstance(csr, (list, tuple)) and len(csr) == 4
            and str(csr[0]) == "/Indexed"):
        result = _uniform_hex_from_indexed_ximage(ximg)
        if result is None:
            _debug_print("{}: rejected (indexed, not uniform)".format(label))
        else:
            _debug_print("{}: uniform indexed color {}".format(label, result))
        return result

    if not (w > 0 and h > 0 and bpc == 8):
        if DEBUG_PDF:
            reasons = []
            if not (w > 0 and h > 0):
                reasons.append("bad size {}x{}".format(w, h))
            if bpc != 8:
                reasons.append("bit depth {}".format(bpc))
            _debug_print("{}: rejected ({})".format(label, "; ".join(reasons)))
        return None

    if not _is_rgb_colorspace(cs):
        _debug_print("{}: rejected (non-RGB colorspace: {})".format(label, cs))
        return None

    raw = ximg.get_data()
    dp = ximg.get("/DecodeParms", {})
    predictor = int(dp.get("/Predictor", 0)) if isinstance(dp, dict) else 0

    # Set up the alpha iterator if there's an SMask of matching dimensions.
    alpha_iter = None
    if smask is not None:
        try:
            sm = smask.get_object() if hasattr(smask, "get_object") else smask
            sw = int(sm.get("/Width", 0))
            sh = int(sm.get("/Height", 0))
            sbpc = int(sm.get("/BitsPerComponent", 8))
        except Exception as e:
            _debug_print("{}: rejected (SMask metadata read failed: {})".format(label, e))
            return None
        if (sw, sh) != (w, h):
            _debug_print("{}: rejected (SMask {}x{} doesn't match image {}x{})".format(
                label, sw, sh, w, h))
            return None
        if sbpc != 8:
            _debug_print("{}: rejected (SMask bit depth {})".format(label, sbpc))
            return None
        try:
            sraw = sm.get_data()
        except Exception as e:
            _debug_print("{}: rejected (SMask data read failed: {})".format(label, e))
            return None
        sdp = sm.get("/DecodeParms", {})
        spred = int(sdp.get("/Predictor", 0)) if isinstance(sdp, dict) else 0
        alpha_iter = _decode_image_rows(sraw, w, h, 1, spred)

    rgb_iter = _decode_image_rows(raw, w, h, 3, predictor)

    target = None      # (r, g, b) of the first opaque pixel
    target_row = None  # cached `bytes(target) * w` for fast row equality
    n_opaque = 0
    n_skipped_alpha = 0

    for row_idx in range(h):
        rgb_row, err = next(rgb_iter)
        if rgb_row is None:
            _debug_print("{}: rejected ({})".format(label, err))
            return None

        if alpha_iter is None:
            # No SMask -- every pixel must match the target.
            if target is None:
                target = (rgb_row[0], rgb_row[1], rgb_row[2])
                target_row = bytes(target) * w
                n_opaque += w
                # The very first row's first pixel is the target. The rest
                # of the row still needs to match it.
                if rgb_row != target_row:
                    _emit_first_deviation(label, row_idx, target, rgb_row, w)
                    return None
                continue
            if rgb_row == target_row:
                n_opaque += w
                continue
            _emit_first_deviation(label, row_idx, target, rgb_row, w)
            return None

        # SMask path: only count fully-opaque pixels.
        alpha_row, err = next(alpha_iter)
        if alpha_row is None:
            _debug_print("{}: rejected (SMask: {})".format(label, err))
            return None

        # Fast path: if the entire alpha row is 255, the row reduces to the
        # plain comparison above.
        if alpha_row == b"\xff" * w:
            if target is None:
                target = (rgb_row[0], rgb_row[1], rgb_row[2])
                target_row = bytes(target) * w
            if rgb_row != target_row:
                _emit_first_deviation(label, row_idx, target, rgb_row, w,
                                       through_smask=True)
                return None
            n_opaque += w
            continue

        # Slow path: walk the row, ignoring pixels whose alpha is not 255.
        for c in range(w):
            if alpha_row[c] != 255:
                n_skipped_alpha += 1
                continue
            base = c * 3
            r, g, b = rgb_row[base], rgb_row[base + 1], rgb_row[base + 2]
            if target is None:
                target = (r, g, b)
                target_row = bytes(target) * w
                n_opaque += 1
                continue
            if r != target[0] or g != target[1] or b != target[2]:
                _debug_print(
                    "{}: rejected (non-uniform opaque pixel at row {}, col {}; "
                    "target {:02x}{:02x}{:02x}, got "
                    "{:02x}{:02x}{:02x})".format(
                        label, row_idx, c,
                        target[0], target[1], target[2], r, g, b))
                return None
            n_opaque += 1

    if target is None:
        # Image is non-empty but every pixel had alpha != 255 -- effectively
        # invisible. Don't claim it as a marker.
        _debug_print("{}: rejected (no fully-opaque pixels: image is invisible "
                     "via SMask)".format(label))
        return None

    result = "{:02x}{:02x}{:02x}".format(target[0], target[1], target[2])
    if alpha_iter is not None:
        _debug_print(
            "{}: uniform color {} at {}x{} ({} opaque px, {} alpha-blended "
            "edge px ignored)".format(
                label, result, w, h, n_opaque, n_skipped_alpha))
    else:
        _debug_print("{}: uniform color {} at {}x{}".format(label, result, w, h))
    return result


def _emit_first_deviation(label, row_idx, target, rgb_row, w, through_smask=False):
    """Find the first pixel in ``rgb_row`` that doesn't match ``target`` and
    emit a debug rejection line that points at it. Used by the no-SMask fast
    path and the all-alpha-255 fast path so the user gets the same kind of
    diagnostic they'd get from the per-pixel slow path."""
    if not DEBUG_PDF:
        return
    tr, tg, tb = target
    for i in range(0, 3 * w, 3):
        if rgb_row[i] != tr or rgb_row[i + 1] != tg or rgb_row[i + 2] != tb:
            kind = "non-uniform opaque pixel" if through_smask else "non-uniform pixel"
            _debug_print(
                "{}: rejected ({} at row {}, col {}; "
                "target {:02x}{:02x}{:02x}, got "
                "{:02x}{:02x}{:02x})".format(
                    label, kind, row_idx, i // 3, tr, tg, tb,
                    rgb_row[i], rgb_row[i + 1], rgb_row[i + 2]))
            return


def print_ops(res,ops):
    import dhelpers as dh
    xobjs = res.get("/XObject", {})
    for operands, operator in ops:
        op = operator.decode("latin1") if isinstance(operator, (bytes, bytearray)) else operator
        dh.idebug(op)
        if len(operands)>0:
            xo = _resolve_xobj(xobjs, operands[0])
            dh.idebug(xo)

def _as_dict(obj):
    # Follow indirect reference once (enough for Resources trees)
    if isinstance(obj, IndirectObject):
        obj = obj.get_object()
    return obj

def _get_or_make_subdict(parent, key):
    parent_dict = _as_dict(parent) or DictionaryObject()
    sub = parent_dict.get(key)
    if sub is None:
        sub = DictionaryObject()
        parent_dict[NameObject(key)] = sub
        return parent_dict, sub
    sub_dict = _as_dict(sub)
    if sub_dict is not sub:
        parent_dict[NameObject(key)] = sub_dict
    return parent_dict, sub_dict

def _uniquify_rep_resource_names(dst_res, rep_res, rep_ops):
    """
    Make colliding names in the replacement page's /Resources unique against
    the destination page and rewrite the replacement ops accordingly.

    Handles resource dicts:
      /XObject, /ExtGState, /Font, /ColorSpace, /Pattern, /Shading, /Properties

    Rewrites operators:
      Do (/XObject), gs (/ExtGState), Tf (/Font),
      cs/CS (/ColorSpace), scn/SCN (Pattern name),
      sh (/Shading),
      BDC/DP (properties name when provided as a name)
    """
    if not rep_res:
        return

    # Resolve as writable dicts
    dst_res = _as_dict(dst_res) or DictionaryObject()
    rep_res = _as_dict(rep_res) or DictionaryObject()

    # Ensure & resolve all relevant subdicts
    dst_res, d_xobj_dst = _get_or_make_subdict(dst_res, "/XObject")
    dst_res, d_ext_dst  = _get_or_make_subdict(dst_res, "/ExtGState")
    dst_res, d_font_dst = _get_or_make_subdict(dst_res, "/Font")
    dst_res, d_cs_dst   = _get_or_make_subdict(dst_res, "/ColorSpace")
    dst_res, d_pat_dst  = _get_or_make_subdict(dst_res, "/Pattern")
    dst_res, d_sh_dst   = _get_or_make_subdict(dst_res, "/Shading")
    dst_res, d_prop_dst = _get_or_make_subdict(dst_res, "/Properties")

    rep_res, d_xobj_rep = _get_or_make_subdict(rep_res, "/XObject")
    rep_res, d_ext_rep  = _get_or_make_subdict(rep_res, "/ExtGState")
    rep_res, d_font_rep = _get_or_make_subdict(rep_res, "/Font")
    rep_res, d_cs_rep   = _get_or_make_subdict(rep_res, "/ColorSpace")
    rep_res, d_pat_rep  = _get_or_make_subdict(rep_res, "/Pattern")
    rep_res, d_sh_rep   = _get_or_make_subdict(rep_res, "/Shading")
    rep_res, d_prop_rep = _get_or_make_subdict(rep_res, "/Properties")

    # Build taken sets as strings ('/Im0', '/GS1', '/F1', '/Cs1', '/P1', '/Sh1', '/MC0')
    taken_x  = set(str(k) for k in d_xobj_dst.keys())
    taken_g  = set(str(k) for k in d_ext_dst.keys())
    taken_f  = set(str(k) for k in d_font_dst.keys())
    taken_cs = set(str(k) for k in d_cs_dst.keys())
    taken_p  = set(str(k) for k in d_pat_dst.keys())
    taken_sh = set(str(k) for k in d_sh_dst.keys())
    taken_pr = set(str(k) for k in d_prop_dst.keys())

    remap_xobj, remap_ext, remap_font = {}, {}, {}
    remap_cs, remap_pat, remap_sh, remap_prop = {}, {}, {}, {}

    def _fresh_name(base: str, taken: set) -> str:
        if base not in taken:
            taken.add(base)
            return base
        n = 1
        while True:
            cand = f"{base}_r{n}"
            if cand not in taken:
                taken.add(cand)
                return cand
            n += 1

    # Detect collisions
    for k in list(d_xobj_rep.keys()):
        s = str(k)
        if s in taken_x:
            remap_xobj[s] = _fresh_name(s, taken_x)
    for k in list(d_ext_rep.keys()):
        s = str(k)
        if s in taken_g:
            remap_ext[s] = _fresh_name(s, taken_g)
    for k in list(d_font_rep.keys()):
        s = str(k)
        if s in taken_f:
            remap_font[s] = _fresh_name(s, taken_f)
    for k in list(d_cs_rep.keys()):
        s = str(k)
        if s in taken_cs:
            remap_cs[s] = _fresh_name(s, taken_cs)
    for k in list(d_pat_rep.keys()):
        s = str(k)
        if s in taken_p:
            remap_pat[s] = _fresh_name(s, taken_p)
    for k in list(d_sh_rep.keys()):
        s = str(k)
        if s in taken_sh:
            remap_sh[s] = _fresh_name(s, taken_sh)
    for k in list(d_prop_rep.keys()):
        s = str(k)
        if s in taken_pr:
            remap_prop[s] = _fresh_name(s, taken_pr)

    if not (remap_xobj or remap_ext or remap_font or remap_cs or remap_pat or remap_sh or remap_prop):
        return

    # Apply renames to replacement resource dicts
    def _apply_renames(dct: DictionaryObject, remap: dict):
        for old_s, new_s in remap.items():
            old = NameObject(old_s)
            new = NameObject(new_s)
            if old in dct:
                dct[new] = dct.pop(old)

    if remap_xobj: _apply_renames(d_xobj_rep, remap_xobj)
    if remap_ext:  _apply_renames(d_ext_rep,  remap_ext)
    if remap_font: _apply_renames(d_font_rep, remap_font)
    if remap_cs:   _apply_renames(d_cs_rep,   remap_cs)
    if remap_pat:  _apply_renames(d_pat_rep,  remap_pat)
    if remap_sh:   _apply_renames(d_sh_rep,   remap_sh)
    if remap_prop: _apply_renames(d_prop_rep, remap_prop)

    # Rewrite operator operands in rep_ops to use fresh names
    def _maybe(name_obj, remap):
        s = str(name_obj)
        if s in remap:
            return NameObject(remap[s])
        return name_obj

    for i, (operands, operator) in enumerate(rep_ops):
        op = operator.decode("latin1") if isinstance(operator, (bytes, bytearray)) else operator

        if op == "Do" and len(operands) == 1 and remap_xobj:
            rep_ops[i] = ([_maybe(operands[0], remap_xobj)], operator)

        elif op == "gs" and len(operands) == 1 and remap_ext:
            rep_ops[i] = ([_maybe(operands[0], remap_ext)], operator)

        elif op == "Tf" and len(operands) >= 2 and remap_font:
            new0 = _maybe(operands[0], remap_font)
            if new0 is not operands[0]:
                ops2 = list(operands); ops2[0] = new0
                rep_ops[i] = (ops2, operator)

        elif op in ("cs", "CS") and len(operands) == 1 and remap_cs:
            rep_ops[i] = ([_maybe(operands[0], remap_cs)], operator)

        elif op in ("scn", "SCN") and len(operands) >= 1 and remap_pat:
            # Pattern usage: first operand can be the pattern name when current CS is /Pattern
            first = operands[0]
            new0  = _maybe(first, remap_pat)
            if new0 is not first:
                ops2 = list(operands); ops2[0] = new0
                rep_ops[i] = (ops2, operator)

        elif op == "sh" and len(operands) == 1 and remap_sh:
            rep_ops[i] = ([_maybe(operands[0], remap_sh)], operator)

        elif op in ("BDC", "DP") and len(operands) >= 2 and remap_prop:
            # operands: [tag, properties]; properties may be a dict or a name
            props = operands[1]
            # Only remap if it's a name (not a dict)
            try:
                is_name_like = not isinstance(_as_dict(props), dict)
            except Exception:
                is_name_like = True
            if is_name_like:
                newp = _maybe(props, remap_prop)
                if newp is not props:
                    ops2 = list(operands); ops2[1] = newp
                    rep_ops[i] = (ops2, operator)


def _collect_and_inline_markers(page, writer, color_to_svg, rep_by_color,
                                page_index=None):
    """
    Scan a page, replace any uniform-color marker images (any size) with the
    replacement PDF's operators in-place (inside the same q..Q / clip / cm).
    Markers are written as 9x9 by office.py but may be resized during PDF
    generation, so size is not used for matching.

    ``page_index`` is an optional 0-based page number used solely for verbose
    debug logging when DEBUG_PDF is enabled.
    """
    page_label = "page {}".format(page_index) if page_index is not None else "page"

    pdf = page.pdf
    res = page.get("/Resources", {}) or {}
    xobjs = res.get("/XObject", {})

    contents = page.get("/Contents", None)
    if contents is None:
        _debug_print("{}: no /Contents stream, skipping".format(page_label))
        return

    cs = ContentStream(contents, pdf)

    I = [[1,0,0],[0,1,0],[0,0,1]]
    stack = [I]
    CTM = stack[-1]
    new_ops = []
    touched_resources = False

    # Counters used only for the per-page summary in DEBUG_PDF mode.
    n_do = 0
    n_image_do = 0
    n_uniform = 0
    n_replaced = 0
    n_unknown_color = 0
    n_zero_size_skip = 0

    # Shallow merge helper for /Resources
    def _merge_resources(dst, src):
        nonlocal touched_resources
        if not src:
            return
        for k, sub in _as_dict(src).items():
            # sub-dicts like /Font, /XObject, /ExtGState, etc.
            if hasattr(sub, "get_object"):
                try:
                    sub = sub.get_object()
                except Exception:
                    pass
            if k not in dst:
                dst[k] = sub
                touched_resources = True
                continue
            # if both are dicts, copy missing entries
            try:
                d_dst = dst[k].get_object() if hasattr(dst[k], "get_object") else dst[k]
                d_src = sub.get_object() if hasattr(sub, "get_object") else sub
                if isinstance(d_dst, dict) and isinstance(d_src, dict):
                    for nk, nv in d_src.items():
                        if nk not in d_dst:
                            d_dst[nk] = nv
                            touched_resources = True
            except Exception:
                # if anything odd, just leave existing dst entry
                pass

    for operands, operator in cs.operations:
        op = operator.decode("latin1") if isinstance(operator, (bytes, bytearray)) else operator

        if op == "q":
            stack.append([row[:] for row in CTM]); CTM = stack[-1]
            new_ops.append((operands, operator))
            continue
        if op == "Q":
            if len(stack) > 1:
                stack.pop(); CTM = stack[-1]
            new_ops.append((operands, operator))
            continue
        if op == "cm":
            a,b,c,d,e,f = (float(v) for v in operands)
            CTM = _mat_mul(CTM, _mat_from(a,b,c,d,e,f))
            stack[-1] = CTM
            new_ops.append((operands, operator))
            continue

        if op == "Do" and len(operands) == 1:
            n_do += 1
            xo_name = str(operands[0])
            xo = _resolve_xobj(xobjs, operands[0])
            if xo is not None and xo.get("/Subtype") == "/Image":
                n_image_do += 1
                xo_label = "{} {}".format(page_label, xo_name)
                hexcolor = _try_get_uniform_rgb_hex_from_ximage(xo, name=xo_label)
                if hexcolor:
                    n_uniform += 1
                    if hexcolor in color_to_svg and hexcolor in rep_by_color:
                        # Inline replacement: q, [optional clip], cm, <rep_ops>, Q
                        rep_ops, rep_w, rep_h, rep_res, crop = rep_by_color[hexcolor]

                        if rep_w > 0 and rep_h > 0:
                            _debug_print(
                                "{}: replacing {} (color {}) with marker for {}{}".format(
                                    page_label, xo_name, hexcolor,
                                    color_to_svg[hexcolor][0],
                                    " crop={!r}".format(crop) if crop else ""))
                            _uniquify_rep_resource_names(res, rep_res, rep_ops)
                            # Merge resources so rep_ops names resolve
                            _merge_resources(res, rep_res)
                            # Sandbox replacement state
                            new_ops.append(([], b"q"))

                            if crop is None:
                                # No cropping: scale replacement page coords
                                # straight into the unit square the marker
                                # XObject occupies.
                                new_ops.append((
                                    [FloatObject(1.0/rep_w), FloatObject(0.0),
                                     FloatObject(0.0), FloatObject(1.0/rep_h),
                                     FloatObject(0.0), FloatObject(0.0)],
                                    b"cm"
                                ))
                            else:
                                # Cropped picture: the renderer placed the
                                # marker XObject so its unit square covers
                                # only the *visible* portion of the original
                                # source. We need to draw only the matching
                                # sub-rectangle of the replacement PDF -- and
                                # have it cover the full unit square -- not
                                # the whole replacement squashed in.
                                #
                                # Visible region of the replacement PDF (in
                                # PDF coords, y-up; OOXML 't' is from the top
                                # so the visible y-range is
                                # [b*rep_h, (1-t)*rep_h]):
                                #     x in [l*rep_w, (1-r)*rep_w]
                                #     y in [b*rep_h, (1-t)*rep_h]
                                #
                                # The cm we want maps that visible rectangle
                                # to [0,1]x[0,1]. Solving gives:
                                #     a = 1 / ((1-l-r) * rep_w)
                                #     d = 1 / ((1-t-b) * rep_h)
                                #     e = -l / (1-l-r)
                                #     f = -b / (1-t-b)
                                # (sanity check: l=t=r=b=0 collapses to the
                                # uncropped 1/rep_w, 1/rep_h scale above.)
                                l_f, t_f, r_f, b_f = crop
                                vis_w_frac = 1.0 - l_f - r_f
                                vis_h_frac = 1.0 - t_f - b_f
                                a = 1.0 / (vis_w_frac * rep_w)
                                d = 1.0 / (vis_h_frac * rep_h)
                                e = -l_f / vis_w_frac
                                f = -b_f / vis_h_frac
                                # Clip to the unit square *before* the cm so
                                # the rectangle is expressed in the same
                                # user-space the surrounding marker call set
                                # up. After cm, content from outside the
                                # visible region of the replacement maps
                                # outside [0,1]x[0,1] and gets clipped away
                                # instead of bleeding onto the page.
                                new_ops.append((
                                    [FloatObject(0.0), FloatObject(0.0),
                                     FloatObject(1.0), FloatObject(1.0)],
                                    b"re"
                                ))
                                new_ops.append(([], b"W"))
                                new_ops.append(([], b"n"))
                                new_ops.append((
                                    [FloatObject(a), FloatObject(0.0),
                                     FloatObject(0.0), FloatObject(d),
                                     FloatObject(e), FloatObject(f)],
                                    b"cm"
                                ))
                            # Splice the replacement operators
                            new_ops.extend(rep_ops)
                            new_ops.append(([], b"Q"))
                            # Skip the original Do (we've replaced it)
                            n_replaced += 1
                            continue
                        else:
                            n_zero_size_skip += 1
                            _debug_print(
                                "{}: skipping {} (color {}): replacement page "
                                "has zero size {}x{}".format(
                                    page_label, xo_name, hexcolor, rep_w, rep_h))
                    else:
                        n_unknown_color += 1
                        _debug_print(
                            "{}: {} is uniform color {} but not in marker map"
                            " -- leaving as-is".format(
                                page_label, xo_name, hexcolor))
            # Non-marker Do or no replacement available: keep as-is
            new_ops.append((operands, operator))
            continue

        # default
        new_ops.append((operands, operator))

    if DEBUG_PDF:
        _debug_print(
            "{}: summary -- {} Do ops, {} image XObjects, {} uniform, "
            "{} replaced, {} unknown-color, {} skipped (zero replacement size)"
            .format(page_label, n_do, n_image_do, n_uniform,
                    n_replaced, n_unknown_color, n_zero_size_skip))

    # Write back modified content stream and any resource merges
    cs.operations = new_ops
    new_obj = None
    for adder in (getattr(writer, "_add_object", None), getattr(pdf, "_add_object", None)):
        if callable(adder):
            try:
                new_obj = adder(cs)
                break
            except Exception:
                pass
    page[NameObject("/Contents")] = new_obj if new_obj is not None else cs
    if touched_resources:
        page[NameObject("/Resources")] = res

def _make_raster_marker_pdf(raster_path: str, out_pdf_path: str) -> None:
    """
    Build a single-page PDF whose only content is ``raster_path`` filling
    the page, embedded losslessly:

    - JPEG: raw bytes go in under /DCTDecode (pixel-perfect, byte-identical).
    - PNG (non-interlaced 8-bit, common subset): decoded with this module's
      pure-Python helpers, re-encoded with /FlateDecode (pixel-perfect;
      alpha/palette/grayscale variants split out into an /SMask where needed).
    - Anything else (Adam7-interlaced PNG, 1/2/4/16-bit PNG, TIFF, BMP,
      GIF, ...): falls back to Pillow.
    """
    from pypdf import PdfWriter
    from pypdf.generic import (
        StreamObject, DictionaryObject, NameObject, NumberObject,
    )
    import zlib, struct

    ext = os.path.splitext(raster_path)[1].lower()
    with open(raster_path, "rb") as fh:
        data = fh.read()

    img = StreamObject()
    smask_bytes = None
    w = h = None
    colorspace = None
    handled = False  # set True once the JPEG or native-PNG path populates img

    # ----- JPEG: lossless byte passthrough via /DCTDecode -----
    if ext in (".jpg", ".jpeg") and data[:2] == b"\xff\xd8":
        bits = comps = None
        i, N = 2, len(data)
        while i + 3 < N:
            while i < N and data[i] != 0xFF:
                i += 1
            while i < N and data[i] == 0xFF:
                i += 1
            if i >= N:
                break
            marker = data[i]; i += 1
            if marker == 0xD8 or marker == 0xD9 or 0xD0 <= marker <= 0xD7:
                continue
            if i + 2 > N:
                break
            seg_len = struct.unpack(">H", data[i:i+2])[0]
            if (marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                           0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF)
                    and seg_len >= 8):
                bits = data[i+2]
                h    = struct.unpack(">H", data[i+3:i+5])[0]
                w    = struct.unpack(">H", data[i+5:i+7])[0]
                comps = data[i+7]
                break
            i += seg_len
        if w and h and comps in (1, 3):
            img._data = data
            img[NameObject("/Filter")] = NameObject("/DCTDecode")
            colorspace = "/DeviceGray" if comps == 1 else "/DeviceRGB"
            img[NameObject("/ColorSpace")] = NameObject(colorspace)
            img[NameObject("/BitsPerComponent")] = NumberObject(bits or 8)
            img[NameObject("/Width")]  = NumberObject(w)
            img[NameObject("/Height")] = NumberObject(h)
            handled = True
        # else: malformed/exotic JPEG -> PIL fallback below

    # ----- PNG: native decode for the common case only -----
    if not handled and data[:8] == b"\x89PNG\r\n\x1a\n":
        bit_depth = color_type = interlace = None
        idat = bytearray(); palette = None; trns = None
        pos = 8
        while pos + 8 <= len(data):
            chunk_len = struct.unpack(">I", data[pos:pos+4])[0]
            ctype     = data[pos+4:pos+8]
            cdata     = data[pos+8:pos+8+chunk_len]
            pos += 8 + chunk_len + 4
            if ctype == b"IHDR":
                w, h, bit_depth, color_type, _c, _f, interlace = struct.unpack(
                    ">IIBBBBB", cdata[:13])
            elif ctype == b"IDAT":
                idat.extend(cdata)
            elif ctype == b"PLTE":
                palette = bytes(cdata)
            elif ctype == b"tRNS":
                trns = bytes(cdata)
            elif ctype == b"IEND":
                break
        bpp_map = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
        bpp = bpp_map.get(color_type)
        # Only the common subset goes through pure-Python. Adam7-interlaced
        # streams pack each of 7 sub-images with its own filter bytes, so the
        # raw stream isn't (1+stride)*h; 1/2/4/16-bit depths use a different
        # sample layout. Both are handled fine by Pillow below.
        if (w is not None and bit_depth == 8
                and interlace == 0 and bpp is not None):
            raw = zlib.decompress(bytes(idat))
            pixels = bytearray()
            for row_bytes, err in _decode_image_rows(raw, w, h, bpp, predictor=10):
                if err is not None:
                    raise ValueError(f"PNG decode error in {raster_path}: {err}")
                pixels.extend(row_bytes)
            if color_type == 2:
                colorspace = "/DeviceRGB"; sample_bytes = bytes(pixels)
            elif color_type == 0:
                colorspace = "/DeviceGray"; sample_bytes = bytes(pixels)
            elif color_type == 3:
                colorspace = "/DeviceRGB"
                out = bytearray(w * h * 3)
                for k, idx in enumerate(pixels):
                    out[k*3:k*3+3] = palette[idx*3:idx*3+3]
                sample_bytes = bytes(out)
                if trns is not None:
                    smask_bytes = bytes(trns[idx] if idx < len(trns) else 255
                                        for idx in pixels)
            elif color_type == 4:
                colorspace = "/DeviceGray"
                gray  = bytearray(w * h); alpha = bytearray(w * h)
                for k in range(w * h):
                    gray[k]  = pixels[2*k]
                    alpha[k] = pixels[2*k+1]
                sample_bytes = bytes(gray); smask_bytes = bytes(alpha)
            else:  # 6: RGBA
                colorspace = "/DeviceRGB"
                rgb   = bytearray(w * h * 3); alpha = bytearray(w * h)
                for k in range(w * h):
                    rgb[k*3:k*3+3] = pixels[4*k:4*k+3]
                    alpha[k]       = pixels[4*k+3]
                sample_bytes = bytes(rgb); smask_bytes = bytes(alpha)
            img._data = zlib.compress(sample_bytes, level=9)
            img[NameObject("/Filter")] = NameObject("/FlateDecode")
            img[NameObject("/Width")]  = NumberObject(w)
            img[NameObject("/Height")] = NumberObject(h)
            img[NameObject("/ColorSpace")] = NameObject(colorspace)
            img[NameObject("/BitsPerComponent")] = NumberObject(8)
            handled = True

    # ----- Pillow fallback (Adam7 PNG, 16-bit PNG, TIFF/BMP/GIF, ...) -----
    if not handled:
        from PIL import Image
        im = Image.open(raster_path)
        w, h = im.size
        smask_bytes = None
        if im.mode in ("RGBA", "LA"):
            base = "RGB" if im.mode == "RGBA" else "L"
            sample_bytes = im.convert(base).tobytes()
            smask_bytes  = im.split()[-1].tobytes()
            colorspace   = "/DeviceRGB" if base == "RGB" else "/DeviceGray"
        elif im.mode == "P":
            sample_bytes = im.convert("RGB").tobytes(); colorspace = "/DeviceRGB"
        elif im.mode == "L":
            sample_bytes = im.tobytes(); colorspace = "/DeviceGray"
        elif im.mode == "1":
            sample_bytes = im.convert("L").tobytes(); colorspace = "/DeviceGray"
        else:
            sample_bytes = im.convert("RGB").tobytes(); colorspace = "/DeviceRGB"
        img._data = zlib.compress(sample_bytes, level=9)
        img[NameObject("/Filter")] = NameObject("/FlateDecode")
        img[NameObject("/Width")]  = NumberObject(w)
        img[NameObject("/Height")] = NumberObject(h)
        img[NameObject("/ColorSpace")] = NameObject(colorspace)
        img[NameObject("/BitsPerComponent")] = NumberObject(8)

    img[NameObject("/Type")]    = NameObject("/XObject")
    img[NameObject("/Subtype")] = NameObject("/Image")

    if smask_bytes is not None:
        sm = StreamObject()
        sm._data = zlib.compress(smask_bytes, level=9)
        sm[NameObject("/Type")]    = NameObject("/XObject")
        sm[NameObject("/Subtype")] = NameObject("/Image")
        sm[NameObject("/Width")]   = NumberObject(w)
        sm[NameObject("/Height")]  = NumberObject(h)
        sm[NameObject("/ColorSpace")] = NameObject("/DeviceGray")
        sm[NameObject("/BitsPerComponent")] = NumberObject(8)
        sm[NameObject("/Filter")]  = NameObject("/FlateDecode")
        img[NameObject("/SMask")]  = sm

    writer = PdfWriter()
    writer.add_blank_page(width=w, height=h)
    page = writer.pages[0]
    img_ref = writer._add_object(img)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): img_ref})
    })
    cs = StreamObject()
    cs._data = f"q\n{w} 0 0 {h} 0 0 cm\n/Im0 Do\nQ\n".encode("latin1")
    page[NameObject("/Contents")] = writer._add_object(cs)
    with open(out_pdf_path, "wb") as f:
        writer.write(f)

def replace_color_markers_with_svgs(input_pdf_path: str,
                                    color_to_svg: Dict[str, tuple],
                                    output_pdf_path: Optional[str],
                                    exporter: Exporter) -> str:
    """
    Arguments:
      - input_pdf_path: the PDF to process
      - color_to_svg: dict like
            {'000001': ('C:/.../figure1.svg', (l, t, r, b)),
             '000002': ('C:/.../figure2.svg', None), ...}
        produced by leave_fallback_png_simple. Each value is a 2-tuple of
        (svg_path, crop_or_None) where the crop, if present, is a 4-tuple
        of fractions in [0, 1] indicating the OOXML <a:srcRect> on the
        original picture. Colors with crop=None are placed without
        inverse-cropping; colors with a crop have the SVG-PDF inverse-cropped
        so only the visible portion fills the marker's unit square (otherwise
        the renderer would squash the full SVG into the cropped display box).
      - output_pdf_path: output
    """
    _debug_print("replace_color_markers_with_svgs: input={}".format(input_pdf_path))
    _debug_print("  marker map has {} color(s)".format(len(color_to_svg)))
    if DEBUG_PDF:
        for hc, val in sorted(color_to_svg.items()):
            sp, cr = val
            _debug_print("    {} -> {}{}".format(
                hc, sp, " crop={!r}".format(cr) if cr else ""))

    in_reader = PdfReader(input_pdf_path)
    writer = PdfWriter()

    # Undo damage from the legacy vendored pypdf's constructor: it calls
    # set_need_appearances_writer(), which fabricates a dangling
    # /AcroForm reference (it resolves to the /Info dictionary, the object
    # occupying that slot) and writes /NeedAppearances through it into
    # /Info. Scrub both; a real AcroForm from the source document is
    # carried over by the catalog-preservation step before write().
    try:
        if "/AcroForm" in writer._root_object:
            del writer._root_object[NameObject("/AcroForm")]
        _winfo = getattr(writer, "_info", None) or getattr(writer, "_info_obj", None)
        if _winfo is not None:
            _winfo = _winfo.get_object()
            if "/NeedAppearances" in _winfo:
                del _winfo[NameObject("/NeedAppearances")]
    except Exception:
        pass

    _debug_copy(input_pdf_path, label="input_pdf")

    # Pre-export SVGs -> PDFs (once per unique SVG)
    svg_to_pdf_cache: Dict[str, str] = {}
    def _export_one(src: str):
        if not src:
            return
        _debug_copy(src, label="marker_source")
        pdf_path = os.path.splitext(src)[0] + ".pdf"
        cached = (os.path.exists(pdf_path)
                  and os.path.getmtime(pdf_path) >= os.path.getmtime(src))
        if not cached:
            if src.lower().endswith(".svg"):
                _debug_print("exporting SVG -> PDF: {}".format(src))
                pdf_path = export_svg_to_pdf(src, exporter)
            else:
                _debug_print("embedding raster -> PDF: {}".format(src))
                _make_raster_marker_pdf(src, pdf_path)
        else:
            _debug_print("using cached PDF for source: {}".format(src))
        svg_to_pdf_cache[src] = pdf_path
        _debug_copy(pdf_path, label="marker_pdf")
    import threading
    threads = []
    # Same SVG referenced cropped + uncropped (or with two crops) appears
    # under multiple colors but only needs one Inkscape conversion.
    unique_svgs = {svg for (svg, _crop) in color_to_svg.values()}
    for svg in unique_svgs:
        t = threading.Thread(target=_export_one, args=(svg,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    if hasattr(exporter, "aeThread") and exporter.aeThread.stopped is True:
        exporter.clear_temp()
        sys.exit()

    # Build hexcolor -> replacement content map (ops + size + resources + crop)
    rep_by_color = {}
    from pypdf.generic import ContentStream
    for hexcolor, (svg, crop) in color_to_svg.items():
        rep_pdf_path = svg_to_pdf_cache.get(svg)
        if not rep_pdf_path:
            _debug_print("no PDF available for color {} (svg={!r}) -- "
                         "this color will pass through unchanged".format(
                             hexcolor, svg))
            continue
        rr = PdfReader(rep_pdf_path)
        rp = rr.pages[0]
        rep_w = float(rp.mediabox.width)
        rep_h = float(rp.mediabox.height)
        # Parse replacement content ops
        rep_cs = ContentStream(rp.get_contents(), rr)
        rep_ops = list(rep_cs.operations)
        # Grab replacement resources (may be None)
        rep_res = rp.get("/Resources", {}) or {}
        rep_by_color[hexcolor] = (rep_ops, rep_w, rep_h, rep_res, crop)
        _debug_print(
            "replacement registered for color {}: page size {:g}x{:g}, "
            "{} content op(s){} from {}".format(
                hexcolor, rep_w, rep_h, len(rep_ops),
                (" crop=" + repr(crop)) if crop else "",
                rep_pdf_path))

    n_pages = len(in_reader.pages)
    _debug_print("scanning {} page(s) of {}".format(n_pages, input_pdf_path))

    # For each page: strip markers, then overlay their corresponding PDFs
    for i, page in enumerate(in_reader.pages):
        _collect_and_inline_markers(page, writer, color_to_svg, rep_by_color,
                                    page_index=i)

        # Just write the modified page; no later overlay needed
        writer.add_page(page)


    # preserve metadata if present
    try:
        if in_reader.metadata:
            writer.add_metadata(in_reader.metadata)
    except Exception:
        pass

    # Preserve document-level catalog entries from the source PDF. A fresh
    # PdfWriter's catalog only has /Type and /Pages, so tagging
    # (/StructTreeRoot, /MarkInfo), XMP metadata (/Metadata), language,
    # forms (/AcroForm), and viewer settings would otherwise be dropped --
    # or worse, leak in as stale references with source object numbers
    # (an untranslated /AcroForm previously ended up pointing at the new
    # file's /Info dictionary). Cloning after add_page reuses the pages
    # already translated into the writer, so /Fields and /Pg references
    # resolve to the cloned pages rather than duplicating them.
    _PRESERVED_ROOT_KEYS = ("/AcroForm", "/Metadata", "/StructTreeRoot",
                            "/MarkInfo", "/Lang", "/ViewerPreferences",
                            "/OutputIntents", "/PageLayout", "/PageMode")
    try:
        src_root = in_reader.root_object
    except AttributeError:  # very old pypdf
        src_root = in_reader.trailer["/Root"].get_object()
    for key in _PRESERVED_ROOT_KEYS:
        if key in src_root:
            try:
                raw = src_root.raw_get(key)
                if hasattr(raw, "clone"):
                    raw = raw.clone(writer)
                elif key in ("/StructTreeRoot", "/AcroForm"):
                    # pypdf-2.0.0 fallback: its write()-time reference sweep
                    # cannot handle these cyclic graphs (it leaves dangling
                    # objects and corrupts the xref); drop them there.
                    _debug_print("catalog preservation skipped for {} (legacy pypdf)".format(key))
                    continue
                # else (pypdf-2.0.0, acyclic keys): assign the reader-bound
                # object/reference as-is; write()'s reference sweep imports
                # foreign objects with translated numbering -- the same
                # mechanism that makes add_page work on that version.
                writer._root_object[NameObject(key)] = raw
            except Exception as e:
                _debug_print("catalog preservation failed for {}: {}".format(key, e))
                try:  # never leave a stale/unresolvable reference behind
                    del writer._root_object[NameObject(key)]
                except Exception:
                    pass
        elif key in writer._root_object:
            # key leaked into the fresh writer without a source counterpart
            del writer._root_object[NameObject(key)]

    if output_pdf_path is None:
        root, ext = os.path.splitext(input_pdf_path)
        output_pdf_path = f"{root}_replaced{ext}"
    with open(output_pdf_path, "wb") as f:
        writer.write(f)
    _debug_copy(output_pdf_path, label="output_pdf")
    _debug_print("replace_color_markers_with_svgs: wrote {}".format(output_pdf_path))
    return output_pdf_path

# ---------------------------------------------------------------------------
# OneNote page merging: recombine OneNote's per-page splits into one tall
# PDF page per OneNote page, guided by the ruler office.py injects.
# ---------------------------------------------------------------------------

def _uniform_hex_from_indexed_ximage(ximg):
    """Return 'rrggbb' if ximg is a uniform-color /Indexed image, else None.

    Used by _try_get_uniform_rgb_hex_from_ximage for indexed colorspaces.
    Deliberately narrow: no SMask, no predictor, base colorspace /DeviceRGB.
    """
    try:
        w = int(ximg.get("/Width", 0))
        h = int(ximg.get("/Height", 0))
        bpc = int(ximg.get("/BitsPerComponent", 8))
        cs = ximg.get("/ColorSpace")
        if hasattr(cs, "get_object"):
            cs = cs.get_object()
        if ximg.get("/SMask") is not None:
            return None
        dp = ximg.get("/DecodeParms", {})
        if isinstance(dp, dict) and int(dp.get("/Predictor", 0) or 0) > 1:
            return None
        if not (w > 0 and h > 0 and bpc in (1, 2, 4, 8)):
            return None
        if not (isinstance(cs, (list, tuple)) and len(cs) == 4
                and str(cs[0]) == "/Indexed"):
            return None
        base = cs[1]
        if hasattr(base, "get_object"):
            base = base.get_object()
        if str(base) != "/DeviceRGB":
            return None
        hival = int(cs[2])
        lookup = cs[3]
        if hasattr(lookup, "get_object"):
            lookup = lookup.get_object()
        if hasattr(lookup, "get_data"):
            lookup = lookup.get_data()
        lookup = bytes(lookup)

        raw = ximg.get_data()
        stride = (w * bpc + 7) // 8
        if len(raw) < stride * h:
            return None
        mask = (1 << bpc) - 1
        target = None
        for row in range(h):
            rowb = raw[row * stride:(row + 1) * stride]
            for col in range(w):
                bitpos = col * bpc
                shift = 8 - bpc - (bitpos % 8)
                idx = (rowb[bitpos // 8] >> shift) & mask
                if target is None:
                    target = idx
                elif idx != target:
                    return None
        if target is None or target > hival or len(lookup) < (target + 1) * 3:
            return None
        r, g, b = lookup[target * 3:target * 3 + 3]
        return "{:02x}{:02x}{:02x}".format(r, g, b)
    except Exception:
        return None


def _median(vals):
    vals = sorted(vals)
    return vals[len(vals) // 2] if vals else None


def _op_name(operator):
    return operator.decode("latin1") if isinstance(
        operator, (bytes, bytearray)) else operator


def _hex_to_rgb01(color):
    n = int(color.lstrip("#"), 16)
    return (((n >> 16) & 0xFF) / 255.0, ((n >> 8) & 0xFF) / 255.0,
            (n & 0xFF) / 255.0)


def _filter_ruler_ops(operations, ruler_rgb):
    """Drop text-showing operators drawn in the ruler's unique color."""
    tol = 2.0 / 255.0

    def _is_ruler(color):
        return all(abs(c - r) <= tol for c, r in zip(color, ruler_rgb))

    filtered = []
    color = (0.0, 0.0, 0.0)
    color_stack = []
    for operands, operator in operations:
        op = _op_name(operator)
        try:
            if op == "q":
                color_stack.append(color)
            elif op == "Q":
                if color_stack:
                    color = color_stack.pop()
            elif op == "rg":
                color = tuple(float(v) for v in operands[:3])
            elif op == "g":
                v = float(operands[0])
                color = (v, v, v)
            elif op == "k":
                c, m, y, k = (float(v) for v in operands[:4])
                color = ((1 - c) * (1 - k), (1 - m) * (1 - k),
                         (1 - y) * (1 - k))
            elif op in ("sc", "scn"):
                vals = [float(v) for v in operands
                        if isinstance(v, (int, float))]
                if len(vals) >= 3:
                    color = tuple(vals[:3])
                elif len(vals) == 1:
                    color = (vals[0],) * 3
        except (TypeError, ValueError):
            pass
        if op in ("Tj", "TJ", "'", '"') and _is_ruler(color):
            if op in ("'", '"'):
                filtered.append(([], b"T*"))  # keep the line advance
            continue
        filtered.append((operands, operator))
    return filtered


def _scan_ruler_marks(page):
    """Scan one published-PDF page for ruler strings and the OneNote footer.

    Returns (marks, footer_ytd, text_bottom_ytd):
        marks           : list of (onenote_page_idx, line_no, y_topdown)
        footer_ytd      : top-down y of the '... Page N' footer, or None
        text_bottom_ytd : deepest non-ruler, non-footer text baseline (0 if
                          none) -- used to trim trailing whitespace

    Text chunks are re-joined per baseline before matching so a ruler line
    split across several show-text operators still matches.
    """
    from office import RULER_RE, ONENOTE_FOOTER_RE

    height = float(page.mediabox.height)
    rows = {}  # rounded ytd -> list of (x, text, precise ytd)

    def _vis(text, cm, tm, font_dict, font_size):
        if not text.strip():
            return
        x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
        y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
        ytd = height - y
        rows.setdefault(round(ytd, 1), []).append((x, text, ytd))

    page.extract_text(visitor_text=_vis)

    marks = []
    footer = None
    text_bottom = 0.0
    for ytd_r, chunks in rows.items():
        chunks.sort()
        joined = "".join(t for _x, t, _y in chunks).strip()
        ytd = chunks[0][2]  # unrounded baseline of the leftmost chunk
        m = RULER_RE.search(joined)
        if m:
            marks.append((int(m.group(1)), int(m.group(2)), ytd))
        elif ytd > height - 30 and ONENOTE_FOOTER_RE.search(joined):
            footer = ytd
        elif ytd <= height - 12:
            # rows inside the bottom print margin are footer decorations
            # (timestamps etc.), never page content
            text_bottom = max(text_bottom, ytd)
    return marks, footer, text_bottom


def _page_graphics_bottom(reader, page):
    """Deepest top-down y touched by the page's non-decoration graphics.

    Walks the content stream tracking the CTM and collects each painted
    subpath's bounding box and each image placement. Decoration is
    filtered out geometrically: notebook rule lines (nearly full-width),
    the red margin line (nearly full-height), and the page background
    (both). Clipping-only paths ('W .. n') are ignored.
    """
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    ident = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def _mul(m, n):  # m then n, PDF row-vector convention
        return (m[0] * n[0] + m[1] * n[2],
                m[0] * n[1] + m[1] * n[3],
                m[2] * n[0] + m[3] * n[2],
                m[2] * n[1] + m[3] * n[3],
                m[4] * n[0] + m[5] * n[2] + n[4],
                m[4] * n[1] + m[5] * n[3] + n[5])

    def _pt(m, x, y):
        return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])

    stack = [ident]
    ctm = ident
    path_pts = []   # device-space points of the current path
    bottom = 0.0    # deepest included ytd

    def _flush(painting):
        nonlocal bottom, path_pts
        if painting and path_pts:
            xs = [p[0] for p in path_pts]
            ys = [p[1] for p in path_pts]
            wid, hgt = max(xs) - min(xs), max(ys) - min(ys)
            full_w = wid > 0.85 * width
            full_h = hgt > 0.85 * height
            if not (full_w or full_h):
                bottom = max(bottom, height - min(ys))
        path_pts = []

    try:
        cs = ContentStream(page.get_contents(), page.pdf)
        ops = cs.operations
    except Exception:
        return height  # unparseable: be conservative, claim full page

    for operands, operator in ops:
        op = _op_name(operator)
        try:
            if op == "q":
                stack.append(ctm)
            elif op == "Q":
                if len(stack) > 1:
                    ctm = stack.pop()
            elif op == "cm":
                a, b, c, d, e, f = (float(v) for v in operands)
                ctm = _mul((a, b, c, d, e, f), ctm)
            elif op in ("m", "l"):
                path_pts.append(_pt(ctm, float(operands[0]), float(operands[1])))
            elif op in ("c", "v", "y"):
                vals = [float(v) for v in operands]
                for i in range(0, len(vals), 2):
                    path_pts.append(_pt(ctm, vals[i], vals[i + 1]))
            elif op == "re":
                x, y, w, h = (float(v) for v in operands)
                for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                    path_pts.append(_pt(ctm, cx, cy))
            elif op in ("S", "s", "f", "F", "f*", "B", "B*", "b", "b*"):
                _flush(True)
            elif op == "n":
                _flush(False)  # clip-only path
            elif op == "Do":
                for cx, cy in ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)):
                    px, py = _pt(ctm, cx, cy)
                    bottom = max(bottom, height - py)
        except (TypeError, ValueError, IndexError):
            continue
    return bottom


# Operators that make marks on the page. In a survivor block everything
# else (state, positioning, clipping) is kept and only these are filtered.
_MARKING_OPS = {"m", "l", "c", "v", "y", "re", "h",
                "S", "s", "f", "F", "f*", "B", "B*", "b", "b*",
                "Tj", "TJ", "'", '"', "Do", "sh", "INLINE IMAGE"}
_PATH_PAINT_OPS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}


def _segment_units(ops, page_h, shift, page):
    """Segment a page's operator list into drawable units for seam dedup.

    Returns (units, clip_idx, window_clip_idx):
        units    : list of dicts with kind ('path'|'text'|'xobj'), drop_idx
                   (op indices that make the unit's marks), pts (global
                   top-down coords), bbox, and key (coarse equality key)
        clip_idx : op indices belonging to clipping paths ('W .. n'); these
                   must never be dropped from the band block
        window_clip_idx : the subset of clip_idx whose clip covers (almost)
                   the whole page -- OneNote's page-window clip. Survivor
                   blocks drop these: a straddling object's full geometry
                   is emitted on every page it touches but cut to the page
                   box by this clip, and the surviving copy must be free to
                   draw across its whole union rect.
    """
    ident = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def _mul(m, n):
        return (m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
                m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
                m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5])

    def _pt(m, x, y):
        return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])

    def _gpt(m, x, y):
        dx, dy = _pt(m, x, y)
        return (dx, page_h - dy + shift)

    def _rgb(vals):
        return tuple(round(v, 3) for v in vals)

    # Resolve an XObject name to a cross-page identity key
    def _xobj_key(name):
        try:
            res = page.get("/Resources", {})
            if hasattr(res, "get_object"):
                res = res.get_object()
            xo = res.get("/XObject", {})
            if hasattr(xo, "get_object"):
                xo = xo.get_object()
            obj = xo[name]
            if hasattr(obj, "get_object"):
                obj = obj.get_object()
            return (str(obj.get("/Subtype")), str(obj.get("/Width")),
                    str(obj.get("/Height")), str(obj.get("/Length")))
        except Exception:
            return (str(name),)

    def _sbytes(v):
        if hasattr(v, "original_bytes"):
            return v.original_bytes
        if isinstance(v, str):
            return v.encode("latin1", "replace")
        return bytes(v)

    page_w = float(page.mediabox.width)

    units = []
    clip_idx = set()
    window_clip_idx = set()
    stack = [ident]
    ctm = ident
    fill = (0.0, 0.0, 0.0)
    stroke = (0.0, 0.0, 0.0)
    lw = 1.0
    state_stack = []
    # current path accumulation
    p_idx = []
    p_pts = []
    p_ops = []
    # text block accumulation
    in_text = False
    t_shows = []      # (index, bytes, global pos)
    tm = tlm = ident
    tleading = 0.0

    def _close_path(i, op):
        if p_pts:
            xs = [p[0] for p in p_pts]
            ys = [p[1] for p in p_pts]
            # only the state the paint op actually uses belongs in the key
            if op in ("S", "s"):
                state = (_rgb(stroke), round(lw, 2))
            elif op in ("B", "B*", "b", "b*"):
                state = (_rgb(fill), _rgb(stroke), round(lw, 2))
            else:
                state = (_rgb(fill),)
            units.append({
                "kind": "path",
                "drop_idx": p_idx + [i],
                "pts": list(p_pts),
                "bbox": (min(xs), max(xs), min(ys), max(ys)),
                "key": ("path", op, " ".join(p_ops), len(p_pts), state),
            })

    for i, (operands, operator) in enumerate(ops):
        op = _op_name(operator)
        try:
            if op == "q":
                stack.append(ctm)
                state_stack.append((fill, stroke, lw))
            elif op == "Q":
                if len(stack) > 1:
                    ctm = stack.pop()
                if state_stack:
                    fill, stroke, lw = state_stack.pop()
            elif op == "cm":
                a, b, c, d, e, f = (float(v) for v in operands)
                ctm = _mul((a, b, c, d, e, f), ctm)
            elif op == "w":
                lw = float(operands[0])
            elif op == "rg":
                fill = tuple(float(v) for v in operands[:3])
            elif op == "RG":
                stroke = tuple(float(v) for v in operands[:3])
            elif op == "g":
                v = float(operands[0]); fill = (v, v, v)
            elif op == "G":
                v = float(operands[0]); stroke = (v, v, v)
            elif op == "k":
                c, m, y, k = (float(v) for v in operands[:4])
                fill = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
            elif op == "K":
                c, m, y, k = (float(v) for v in operands[:4])
                stroke = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
            elif op in ("sc", "scn"):
                vals = [float(v) for v in operands if isinstance(v, (int, float))]
                if len(vals) >= 3:
                    fill = tuple(vals[:3])
                elif len(vals) == 1:
                    fill = (vals[0],) * 3
            elif op in ("SC", "SCN"):
                vals = [float(v) for v in operands if isinstance(v, (int, float))]
                if len(vals) >= 3:
                    stroke = tuple(vals[:3])
                elif len(vals) == 1:
                    stroke = (vals[0],) * 3
            elif op in ("m", "l"):
                p_idx.append(i); p_ops.append(op)
                p_pts.append(_gpt(ctm, float(operands[0]), float(operands[1])))
            elif op in ("c", "v", "y"):
                p_idx.append(i); p_ops.append(op)
                vals = [float(v) for v in operands]
                for j in range(0, len(vals), 2):
                    p_pts.append(_gpt(ctm, vals[j], vals[j + 1]))
            elif op == "re":
                p_idx.append(i); p_ops.append(op)
                x, y, w2, h2 = (float(v) for v in operands)
                for cx, cy in ((x, y), (x + w2, y), (x, y + h2), (x + w2, y + h2)):
                    p_pts.append(_gpt(ctm, cx, cy))
            elif op == "h":
                p_idx.append(i); p_ops.append(op)
            elif op == "W" or op == "W*":
                p_idx.append(i)  # part of the clip construction
            elif op in _PATH_PAINT_OPS:
                _close_path(i, op)
                p_idx, p_pts, p_ops = [], [], []
            elif op == "n":
                clip_idx.update(p_idx)
                clip_idx.add(i)
                if p_pts:
                    xs = [p[0] for p in p_pts]
                    ys = [p[1] for p in p_pts]
                    if (max(xs) - min(xs) > 0.8 * page_w
                            and max(ys) - min(ys) > 0.8 * page_h):
                        window_clip_idx.update(p_idx)
                        window_clip_idx.add(i)
                p_idx, p_pts, p_ops = [], [], []
            elif op == "BT":
                in_text = True
                tm = tlm = ident
                t_shows = []
            elif op == "ET":
                if t_shows:
                    pts = [s[2] for s in t_shows]
                    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                    units.append({
                        "kind": "text",
                        "drop_idx": [s[0] for s in t_shows],
                        "pts": pts,
                        "bbox": (min(xs), max(xs), min(ys), max(ys)),
                        "key": ("text", tuple(s[1] for s in t_shows),
                                _rgb(fill)),
                    })
                in_text = False
                t_shows = []
            elif in_text and op == "Tm":
                a, b, c, d, e, f = (float(v) for v in operands)
                tm = tlm = (a, b, c, d, e, f)
            elif in_text and op in ("Td", "TD"):
                tx, ty2 = float(operands[0]), float(operands[1])
                if op == "TD":
                    tleading = -ty2
                tlm = _mul((1, 0, 0, 1, tx, ty2), tlm)
                tm = tlm
            elif in_text and op == "TL":
                tleading = float(operands[0])
            elif in_text and op == "T*":
                tlm = _mul((1, 0, 0, 1, 0, -tleading), tlm)
                tm = tlm
            elif in_text and op in ("Tj", "TJ", "'", '"'):
                if op in ("'", '"'):
                    tlm = _mul((1, 0, 0, 1, 0, -tleading), tlm)
                    tm = tlm
                if op == "TJ":
                    txt = b"".join(_sbytes(v) for v in operands[0]
                                   if not isinstance(v, (int, float)))
                elif op == '"':
                    txt = _sbytes(operands[2])
                else:
                    txt = _sbytes(operands[0])
                gp = _gpt(_mul(tm, ctm), 0.0, 0.0)
                t_shows.append((i, txt, gp))
            elif op == "Do":
                corners = [_gpt(ctm, cx, cy)
                           for cx, cy in ((0, 0), (1, 0), (0, 1), (1, 1))]
                xs = [p[0] for p in corners]; ys = [p[1] for p in corners]
                units.append({
                    "kind": "xobj",
                    "drop_idx": [i],
                    "pts": corners,
                    "bbox": (min(xs), max(xs), min(ys), max(ys)),
                    "key": ("xobj", _xobj_key(operands[0])),
                })
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    return units, clip_idx, window_clip_idx


def _units_equal(u, v, tol=0.3):
    if u["key"] != v["key"] or len(u["pts"]) != len(v["pts"]):
        return False
    return all(abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol
               for p, q in zip(u["pts"], v["pts"]))


def _build_page_content(cs, ops, width, band_rect, removed_idx,
                        pre_blocks, post_blocks, clip_idx, window_clip_idx):
    """Assemble a page's final content: survivor blocks that belong under
    the page's band (decoration), then the band-clipped stream minus
    removed/survivor units, then survivor blocks that belong on top
    (content). band_rect / block rects are (y_bu, height).

    Survivor blocks keep shaped clipping paths but drop the page-window
    clip, so a survivor whose geometry spans several pages can draw across
    its whole union rect instead of being cut at its page's box.
    """

    def _clip_prefix(rect):
        return "q -5 {:.2f} {:.2f} {:.2f} re W n\n".format(
            rect[0], width + 10, rect[1]).encode("latin1")

    def _survivor_block(rect, keep_idx):
        block = []
        for i, (operands, operator) in enumerate(ops):
            op = _op_name(operator)
            if i in window_clip_idx and i not in keep_idx:
                continue
            if i in keep_idx or i in clip_idx or op not in _MARKING_OPS:
                block.append((operands, operator))
            elif op in ("'", '"'):
                block.append(([], b"T*"))  # preserve the line advance
        cs.operations = block
        return _clip_prefix(rect) + cs.get_data() + b"\nQ\n"

    out = b""
    for rect, keep_idx in pre_blocks:
        out += _survivor_block(rect, keep_idx)

    main_ops = [(o, opr) for i, (o, opr) in enumerate(ops)
                if i not in removed_idx]
    cs.operations = main_ops
    out += _clip_prefix(band_rect) + cs.get_data() + b"\nQ"

    for rect, keep_idx in post_blocks:
        out += b"\n" + _survivor_block(rect, keep_idx)
    return out


def merge_onenote_pages(raw_pdf, merged_pdf, ruler_color=None, prints=None):
    """Merge each OneNote page's run of published PDF pages into one tall
    page, using the ruler office.mark_onenote_images injected for grouping
    and vertical alignment.

    For every group: the ruler line pitch is fit by least squares over all
    line numbers, each PDF page's canvas offset is chained through the
    duplicated line numbers at the breaks, pages are clipped to bands that
    meet at the midpoint of the overlap, objects OneNote duplicated across
    a break are drawn once (content survivors keep the last copy, above
    earlier pages' rule lines; rule-line survivors keep the first copy,
    below everything), the '... Page N' footers fall outside every band and
    their text ops are dropped, the ruler text is stripped by its color,
    trailing whitespace is trimmed to the deepest real content (but never
    below one natural page height), and the clipped pages are stacked onto
    one page of the combined height. PDF pages with no ruler marks pass
    through unchanged.
    """
    from pypdf import Transformation
    from pypdf.generic import RectangleObject, StreamObject
    from office import RULER_FALLBACK_PITCH

    def _say(msg):
        if prints:
            prints(msg)

    ruler_rgb = _hex_to_rgb01(ruler_color) if ruler_color else None
    reader = PdfReader(raw_pdf)
    infos = [_scan_ruler_marks(p) for p in reader.pages]

    # Group consecutive PDF pages by the OneNote page their marks encode
    groups = []  # (onenote_idx or None, [pdf page indices])
    for i, (marks, _footer, _tb) in enumerate(infos):
        gid = _median([m[0] for m in marks]) if marks else None
        if gid is not None and groups and groups[-1][0] == gid:
            groups[-1][1].append(i)
        else:
            groups.append((gid, [i]))

    writer = PdfWriter()
    for gid, idxs in groups:
        if gid is None:
            _say("  merge: page {} has no ruler marks; kept as-is".format(idxs[0]))
            writer.add_page(reader.pages[idxs[0]])
            continue

        pages = [reader.pages[i] for i in idxs]
        markss = [sorted((m[1], m[2]) for m in infos[i][0]) for i in idxs]
        footers = [infos[i][1] for i in idxs]
        text_bottoms = [infos[i][2] for i in idxs]

        # Line pitch: within a page the ruler lines are laid out perfectly
        # uniformly, so pool a least-squares slope over every page's marks.
        # (A median of per-line deltas is quantized by coordinate precision;
        # its error, multiplied by hundreds of lines, visibly misaligns the
        # seams.)
        num = den = 0.0
        for marks in markss:
            if len(marks) < 2:
                continue
            kbar = sum(k for k, _y in marks) / len(marks)
            ybar = sum(y for _k, y in marks) / len(marks)
            num += sum((k - kbar) * (y - ybar) for k, y in marks)
            den += sum((k - kbar) ** 2 for k, _y in marks)
        pitch = num / den if den else RULER_FALLBACK_PITCH

        # Global (canvas) offset of each PDF page. The first page is
        # anchored to global(k) = k*pitch; each later page is chained to
        # its predecessor through the ruler lines OneNote duplicated across
        # the break, which makes duplicated content coincide exactly. When
        # a pair shares no line, the chain steps by pitch over the gap.
        shifts = [_median([k * pitch - y for (k, y) in markss[0]])]
        for a in range(1, len(pages)):
            prev = dict(markss[a - 1])
            dups = [kp for kp, _y in markss[a] if kp in prev]
            if dups:
                delta = _median([prev[k] - dict(markss[a])[k] for k in dups])
            else:
                kp, yp = markss[a - 1][-1]
                kq, yq = markss[a][0]
                delta = (yp - yq) + pitch * (kq - kp)
            shifts.append(shifts[a - 1] + delta)

        # Verification: duplicated lines must land at identical global
        # positions, and all lines must sit on one straight line in k.
        dup_err = 0.0
        for a in range(1, len(pages)):
            prev = dict(markss[a - 1])
            for k, y in markss[a]:
                if k in prev:
                    dup_err = max(dup_err, abs(
                        (shifts[a - 1] + prev[k]) - (shifts[a] + y)))
        allg = [(k, shifts[a] + y)
                for a in range(len(pages)) for k, y in markss[a]]
        cbar = sum(g - k * pitch for k, g in allg) / len(allg)
        lin_err = max(abs(g - k * pitch - cbar) for k, g in allg)
        _say("  merge: alignment check: max duplicate mismatch {:.3f}pt, "
             "max linearity residual {:.3f}pt".format(dup_err, lin_err))

        # Band boundaries at the midpoint of the region shared/adjacent
        # between consecutive pages
        heights = [float(p.mediabox.height) for p in pages]
        bounds = [shifts[0]]  # global top of the first page
        for a in range(len(pages) - 1):
            bottom_a = markss[a][-1][0] * pitch
            top_b = markss[a + 1][0][0] * pitch
            bounds.append((bottom_a + top_b) / 2.0)

        # End of the merged page: just above the last footer, but trimmed
        # to the deepest real content so the ruler's overshoot (and
        # inflated declared extents) don't leave a blank tail.
        last_foot = footers[-1] if footers[-1] is not None else heights[-1] - 25.0
        footer_end = shifts[-1] + last_foot - 4.0
        content_end = 0.0
        for p in range(len(pages)):
            depth = max(_page_graphics_bottom(reader, pages[p]),
                        text_bottoms[p])
            if depth <= 0:
                continue  # ruler-only page: no content to preserve
            foot = footers[p] if footers[p] is not None else heights[p] - 25.0
            content_end = max(content_end, shifts[p] + min(depth, foot - 4.0))
        end = min(footer_end, content_end + 8.0) if content_end else footer_end
        # Never produce a page shorter than a natural page: for sub-page
        # content, keep the full page (its footer text is stripped anyway).
        end = max(end, bounds[0] + heights[0])
        bounds = [min(b, end) for b in bounds] + [end]

        top0 = bounds[0]
        total_h = max(bounds[-1] - top0, 8.0)
        width = max(float(p.mediabox.width) for p in pages)
        if total_h > 14400:
            _say("  merge: warning: page exceeds Acrobat's 14400pt "
                 "page-size limit ({:.0f}pt); some viewers may not "
                 "display it".format(total_h))
        dest = writer.add_blank_page(width=width, height=total_h)
        _say("  merge: OneNote page {}: {} PDF page(s) -> {:.0f}pt tall "
             "(pitch {:.2f})".format(gid, len(pages), total_h, pitch))

        # Parse each page's stream once; strip the ruler; segment into units
        css, opss, unitss, clip_idxs, wclip_idxs = [], [], [], [], []
        for p in range(len(pages)):
            cs = ContentStream(pages[p].get_contents(), reader)
            ops = list(cs.operations)
            if ruler_rgb is not None:
                ops = _filter_ruler_ops(ops, ruler_rgb)
            un, ci, wci = _segment_units(ops, heights[p], shifts[p], pages[p])
            css.append(cs); opss.append(ops)
            unitss.append(un); clip_idxs.append(ci); wclip_idxs.append(wci)

        # Objects OneNote duplicated across a break render identically at
        # the same global position on both pages. Chain the copies (3+
        # pages if needed) and keep one.
        removed = [set() for _ in pages]
        chains = {}       # id(unit) -> chain record
        chain_recs = []
        n_dup = 0
        for a in range(1, len(pages)):
            ov_top = shifts[a]                       # global top of page a
            ov_bot = shifts[a - 1] + heights[a - 1]  # global bottom of a-1
            if ov_bot <= ov_top:
                continue
            in_window = lambda u: (u["bbox"][3] >= ov_top - 0.5
                                   and u["bbox"][2] <= ov_bot + 0.5)
            cand_prev = [u for u in unitss[a - 1] if in_window(u)]
            cand_cur = [u for u in unitss[a] if in_window(u)]
            used = set()
            for u in cand_prev:
                for v in cand_cur:
                    if id(v) in used or not _units_equal(u, v):
                        continue
                    used.add(id(v))
                    rec = chains.get(id(u))
                    if rec is None:
                        rec = {"members": [(a - 1, u), (a, v)]}
                        chains[id(u)] = rec
                        chain_recs.append(rec)
                    else:
                        rec["members"].append((a, v))
                    chains[id(v)] = rec
                    n_dup += 1
                    break

        # One copy survives per chain. Z-order across pages matters: each
        # page's band is drawn after all earlier pages', so page Q's rule
        # lines would paint OVER a survivor kept with page P. Therefore
        # content survivors keep the LAST copy and are drawn after their
        # page's band (above every earlier page's decoration), while
        # decoration survivors (full-width rule lines) keep the FIRST copy
        # and are drawn before their page's band (below everything).
        pre_blocks = [{} for _ in pages]   # (first,last) -> keep idx set
        post_blocks = [{} for _ in pages]
        for rec in chain_recs:
            mem = rec["members"]
            for p, u in mem:
                removed[p].update(u["drop_idx"])
            u0 = mem[0][1]
            deco = (u0["kind"] == "path"
                    and (u0["bbox"][1] - u0["bbox"][0]) > 0.85 * width
                    and (u0["bbox"][3] - u0["bbox"][2]) < 3.0)
            span = (mem[0][0], mem[-1][0])
            kp, ku = mem[0] if deco else mem[-1]
            tgt = pre_blocks if deco else post_blocks
            tgt[kp].setdefault(span, set()).update(ku["drop_idx"])
        if n_dup:
            _say("  merge: deduplicated {} object(s) straddling "
                 "seams".format(n_dup))

        # The '... Page N' footers are clipped out of every band, but their
        # text ops would remain in the searchable text layer; drop them too.
        for p in range(len(pages)):
            strip = shifts[p] + heights[p] - 12.0
            for u in unitss[p]:
                if u["kind"] == "text" and u["bbox"][2] > strip:
                    removed[p].update(u["drop_idx"])

        for p, page, shift, h in zip(range(len(pages)), pages, shifts, heights):
            g0, g1 = bounds[p], bounds[p + 1]
            if g1 <= g0 and not pre_blocks[p] and not post_blocks[p]:
                continue
            # band in local bottom-up coords
            y_bu = h - (g1 - shift)

            def _mk_blocks(spans):
                blocks = []
                for (fst, lst), keep in spans.items():
                    ug0, ug1 = bounds[fst], bounds[lst + 1]
                    blocks.append(((h - (ug1 - shift), max(ug1 - ug0, 0.0)),
                                   keep))
                return blocks

            data = _build_page_content(css[p], opss[p], width,
                                       (y_bu, max(g1 - g0, 0.0)),
                                       removed[p], _mk_blocks(pre_blocks[p]),
                                       _mk_blocks(post_blocks[p]),
                                       clip_idxs[p], wclip_idxs[p])
            stream = StreamObject()
            stream._data = data
            page.replace_contents(stream)
            # merge_transformed_page clips to the source page's box; widen
            # it so survivors whose geometry extends beyond their page
            # (straddling objects) aren't cut -- our own clip rects govern.
            big = RectangleObject((-10.0, -total_h - 10.0,
                                   width + 10.0, h + total_h + 10.0))
            page.mediabox = big
            page.cropbox = big
            ty = total_h - (shift - top0) - h
            dest.merge_transformed_page(
                page, Transformation().translate(0, ty))

    with open(merged_pdf, "wb") as fh:
        writer.write(fh)
    return merged_pdf
