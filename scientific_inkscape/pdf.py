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

import os, platform, sys
from shutil import which

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
    _ = subprocess.run(cmd, capture_output=True, text=True)
    generated_pdf = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(input_file))[0]}.pdf")
    from autoexporter import repeat_move
    repeat_move(generated_pdf, output_file)

import time
import tempfile
import subprocess
from pathlib import Path

import threading
MAX_THREADS_OFFICE = 1
sema_office = threading.Semaphore(MAX_THREADS_OFFICE)

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

def make_pdf_office(input_path, output_path=None, retries=3, delay=1.0):
    """
    Convert DOC/DOCX/RTF or PPT/PPTX -> PDF using Office (Word/PowerPoint) via PowerShell COM.
    Runs silently (no console, no output). Returns output path on success.
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

# Backward-compat alias if existing code calls the old name
make_pdf_word = make_pdf_office

from typing import Dict, Tuple, List, Optional

mydir = os.path.dirname(os.path.abspath(__file__))
packages = os.path.join(mydir, "packages")
if packages not in sys.path:
    sys.path.append(packages)
    
import os, sys

here = os.path.dirname(os.path.abspath(__file__))
pkgdir = os.path.join(here, "packages")
try:
    import typing_extensions # noqa
    pypdf_path = os.path.join(pkgdir, "pypdf-6.1.3")
except ImportError:
    # v1.0 of Inkscape, use old pypdf
    pypdf_path = os.path.join(pkgdir, "pypdf-2.0.0")
if pypdf_path not in sys.path:
    sys.path.insert(0, pypdf_path)


from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject, IndirectObject
from pypdf.generic import FloatObject
from pypdf.generic import DictionaryObject

# ---- Inkscape export (same conventions as AutoExporter) ----
def _inkscape_bin():
    # pull the Inkscape binary location the same way AutoExporter does
    # (requires dhelpers + inkex, which you already use elsewhere)
    import dhelpers as dh
    return dh.inkex.inkscape_system_info.binary_location  # noqa

from autoexporter import Exporter
def export_svg_to_pdf(svg_path: str, exporter: Exporter) -> str:
    """Export SVG -> PDF next to the SVG, mirroring AutoExporter’s CLI call."""
    pdf_path = os.path.splitext(svg_path)[0] + ".pdf"
    args = [
        _inkscape_bin(),
        "--export-background", "#ffffff",
        "--export-background-opacity", "1.0",
        "--export-dpi", "600",
        "--export-filename", pdf_path,
        svg_path,
    ]
    import dhelpers as dh
    exporter.check(dh.subprocess_repeat,args)  # same wrapper used by AutoExporter
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

def _try_get_uniform_rgb_hex_from_ximage(ximg) -> Optional[str]:
    """
    Attempt to decode the image XObject to raw RGB and check if it's uniform.
    Returns lowercase 'rrggbb' or None.
    """
    try:
        w = int(ximg.get("/Width", 0))
        h = int(ximg.get("/Height", 0))
        bpc = int(ximg.get("/BitsPerComponent", 8))
        cs = ximg.get("/ColorSpace", "/DeviceRGB")
        smask = ximg.get("/SMask", None)
    except Exception:
        return None

    if not (w == 9 and h == 9 and bpc == 8 and smask is None):
        return None

    # Only handle DeviceRGB (or [/DeviceRGB] form)
    if isinstance(cs, list):
        if not any(str(x) == "/DeviceRGB" for x in cs):
            return None
    else:
        if str(cs) != "/DeviceRGB":
            return None

    # pypdf gives decoded-by-filter data, but PNG 'Predictor' is still present in DecodeParms
    raw = ximg.get_data()
    dp = ximg.get("/DecodeParms", {})
    predictor = int(dp.get("/Predictor", 0)) if isinstance(dp, dict) else 0

    # If predictor is PNG-style (10..15), each row is [filter][bytes...]
    if predictor >= 10:
        rgb = _undo_png_predictors_rgb8(raw, w, h)
        if not rgb:
            return None
    else:
        # No predictor: expect raw planar? In practice for these markers it will be PNG predictor.
        # Fallback: assume row filter=0 was used and raw has no filter bytes (rare).
        expected = 3 * w * h
        if len(raw) != expected:
            return None
        rgb = raw

    # Check uniform
    r0, g0, b0 = rgb[0], rgb[1], rgb[2]
    for i in range(0, len(rgb), 3):
        if rgb[i] != r0 or rgb[i+1] != g0 or rgb[i+2] != b0:
            return None

    return f"{r0:02x}{g0:02x}{b0:02x}"

def _collect_and_strip_markers(page, writer, color_to_svg: Dict[str, str]) -> List[Tuple[Tuple[float,float,float,float], str]]:
    """
    Scan a page, remove any 9x9 uniform-color image draw ops that have a hit in color_to_svg.
    Returns list of (xmin,ymin,xmax,ymax, svg_path).
    """
    pdf = page.pdf
    res = page.get("/Resources", {}) or {}
    xobjs = res.get("/XObject", {})

    contents = page.get("/Contents", None)
    if contents is None:
        return []

    cs = ContentStream(contents, pdf)

    I = [[1,0,0],[0,1,0],[0,0,1]]
    stack = [I]
    CTM = stack[-1]
    new_ops = []
    placements: List[Tuple[Tuple[float,float,float,float], str]] = []

    for operands, operator in cs.operations:
        op = operator.decode("latin1") if isinstance(operator, (bytes, bytearray)) else operator

        if op == "q":
            stack.append([row[:] for row in CTM]); CTM = stack[-1]
            new_ops.append((operands, operator))
        elif op == "Q":
            if len(stack) > 1:
                stack.pop(); CTM = stack[-1]
            new_ops.append((operands, operator))
        elif op == "cm":
            a,b,c,d,e,f = (float(v) for v in operands)
            CTM = _mat_mul(CTM, _mat_from(a,b,c,d,e,f))
            stack[-1] = CTM
            new_ops.append((operands, operator))
        elif op == "Do" and len(operands) == 1:
            xo = _resolve_xobj(xobjs, operands[0])
            # Only intercept actual image draws
            if xo is not None and xo.get("/Subtype") == "/Image":
                hexcolor = _try_get_uniform_rgb_hex_from_ximage(xo)
                if hexcolor and hexcolor in color_to_svg:
                    # Compute AABB of the transformed unit square
                    p00 = _apply_mat(CTM, 0, 0)
                    p10 = _apply_mat(CTM, 1, 0)
                    p01 = _apply_mat(CTM, 0, 1)
                    p11 = _apply_mat(CTM, 1, 1)
                    xs = [p00[0], p10[0], p01[0], p11[0]]
                    ys = [p00[1], p10[1], p01[1], p11[1]]
                    rect = (min(xs), min(ys), max(xs), max(ys))
                    placements.append((rect, color_to_svg[hexcolor]))
                    # Skip drawing: we “delete” the image op by not appending
                    continue
            # fall-through: keep non-marker images
            new_ops.append((operands, operator))
        else:
            new_ops.append((operands, operator))

    # Persist modified content stream so deletions stick
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
    return placements

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


def _collect_and_inline_markers(page, writer, color_to_svg, rep_by_color):
    """
    Scan a page, replace any 9x9 uniform-color marker images with the
    replacement PDF's operators in-place (inside the same q..Q / clip / cm).
    """
    pdf = page.pdf
    res = page.get("/Resources", {}) or {}
    xobjs = res.get("/XObject", {})

    contents = page.get("/Contents", None)
    if contents is None:
        return

    cs = ContentStream(contents, pdf)

    I = [[1,0,0],[0,1,0],[0,0,1]]
    stack = [I]
    CTM = stack[-1]
    new_ops = []
    touched_resources = False

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
            xo = _resolve_xobj(xobjs, operands[0])
            if xo is not None and xo.get("/Subtype") == "/Image":
                hexcolor = _try_get_uniform_rgb_hex_from_ximage(xo)
                if hexcolor and hexcolor in color_to_svg and hexcolor in rep_by_color:
                    # Inline replacement here: q, cm(1/rep_w,1/rep_h), <rep_ops>, Q
                    rep_ops, rep_w, rep_h, rep_res = rep_by_color[hexcolor]
                    
                    if rep_w > 0 and rep_h > 0:
                        _uniquify_rep_resource_names(res, rep_res, rep_ops)
                        # Merge resources so rep_ops names resolve
                        _merge_resources(res, rep_res)
                        # Sandbox replacement state
                        new_ops.append(([], b"q"))
                        # Scale from replacement page units to unit square
                        new_ops.append((
                            [FloatObject(1.0/rep_w), FloatObject(0.0), FloatObject(0.0),
                             FloatObject(1.0/rep_h), FloatObject(0.0), FloatObject(0.0)],
                            b"cm"
                        ))
                        # Splice the replacement operators
                        new_ops.extend(rep_ops)
                        new_ops.append(([], b"Q"))
                        # Skip the original Do (we've replaced it)
                        continue
            # Non-marker Do or no replacement available: keep as-is
            new_ops.append((operands, operator))
            continue

        # default
        new_ops.append((operands, operator))

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


def replace_color_markers_with_svgs(input_pdf_path: str,
                                    color_to_svg: Dict[str, str],
                                    output_pdf_path: Optional[str],
                                    exporter: Exporter) -> str:
    """
    Arguments:
      - input_pdf_path: the PDF to process
      - color_to_svg: dict like {'000001': 'C:/.../figure1.svg', ...} from leave_fallback_png_simple
      - output_pdf_path: output
    """
    in_reader = PdfReader(input_pdf_path)
    writer = PdfWriter()

    # Pre-export SVGs -> PDFs (once per unique SVG)
    svg_to_pdf_cache: Dict[str, str] = {}
    def _export_one(svg: str):
        if not svg:
            return
        pdf_path = os.path.splitext(svg)[0] + ".pdf"
        if (not os.path.exists(pdf_path)
                or os.path.getmtime(pdf_path) < os.path.getmtime(svg)):
            pdf_path = export_svg_to_pdf(svg, exporter)   # gated by Exporter.check(...)
        svg_to_pdf_cache[svg] = pdf_path
    import threading
    threads = []
    for svg in set(color_to_svg.values()):
        t = threading.Thread(target=_export_one, args=(svg,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
        
    if hasattr(exporter, "aeThread") and exporter.aeThread.stopped is True:
        exporter.clear_temp()
        sys.exit()
        
    # Build hexcolor -> replacement content map (ops + size + resources)
    rep_by_color = {}
    from pypdf.generic import ContentStream
    for hexcolor, svg in color_to_svg.items():
        rep_pdf_path = svg_to_pdf_cache.get(svg)
        if not rep_pdf_path:
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
        rep_by_color[hexcolor] = (rep_ops, rep_w, rep_h, rep_res)


    # For each page: strip markers, then overlay their corresponding PDFs
    for page in in_reader.pages:
        _collect_and_inline_markers(page, writer, color_to_svg, rep_by_color)
    
        # Just write the modified page; no later overlay needed
        writer.add_page(page)


    # preserve metadata if present
    try:
        if in_reader.metadata:
            writer.add_metadata(in_reader.metadata)
    except Exception:
        pass

    if output_pdf_path is None:
        root, ext = os.path.splitext(input_pdf_path)
        output_pdf_path = f"{root}_replaced{ext}"
    with open(output_pdf_path, "wb") as f:
        writer.write(f)
    return output_pdf_path
