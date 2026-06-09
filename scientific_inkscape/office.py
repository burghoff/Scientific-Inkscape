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


DPI_MIN = 300  # when replacing SVG with PNG, ensure DPI is at least this
EMU_PER_INCH = 914400  # Office EMUs

import sys
import dhelpers as dh

bfn = dh.inkex.inkscape_system_info.binary_location


def overwrite_output(filein, fileout):
    if os.path.exists(fileout):
        os.remove(fileout)
    args = [
        bfn,
        "--export-background",
        "#ffffff",
        "--export-background-opacity",
        "0.0",
        "--export-dpi",
        str(600),
        "--export-filename",
        fileout,
        filein,
    ]
    dh.subprocess_repeat(args)


import os
import shutil
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo, BadZipFile
from urllib.parse import unquote
from lxml import etree as ET
import re
import zlib, struct, binascii, threading


# Drawing-ML namespaces used when locating <a:srcRect> alongside an
# <a:blip>/<asvg:svgBlip> in a <pic:blipFill>.
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_ASVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"


def _find_srcrect_crop(node):
    """Locate the <a:srcRect> sibling of the *outer* <a:blip> that owns
    ``node`` (which can itself be the outer <a:blip> or a nested
    <asvg:svgBlip>) and return ``(crop_tuple, srcrect_elem)`` where:

    - ``crop_tuple`` is ``(left, top, right, bottom)`` as fractions in [0, 1]
      if the srcRect contains a non-zero crop that leaves a non-empty visible
      region; otherwise ``None``.
    - ``srcrect_elem`` is the <a:srcRect> XML element if one exists at all
      (regardless of whether the crop was meaningful), so callers can decide
      to remove it from the tree. ``None`` if no srcRect exists.

    OOXML stores each side as an integer in 100000ths of a percent:
    ``l="34146"`` means 34.146% cropped from the left. Any side not
    present defaults to 0.
    """
    # Walk up to the outer <a:blip>. <asvg:svgBlip> lives inside
    # <a:blip>/<a:extLst>/<a:ext>, so we may need to climb three levels.
    outer_blip = node
    if node.tag == f"{{{_ASVG_NS}}}svgBlip":
        ext = node.getparent()
        extLst = ext.getparent() if ext is not None else None
        outer_blip = extLst.getparent() if extLst is not None else None

    if outer_blip is None or outer_blip.tag != f"{{{_A_NS}}}blip":
        return None, None

    blip_fill = outer_blip.getparent()
    if blip_fill is None:
        return None, None

    src_rect = blip_fill.find(f"{{{_A_NS}}}srcRect")
    if src_rect is None:
        return None, None

    def _frac(attr):
        v = src_rect.get(attr)
        if v is None:
            return 0.0
        try:
            return int(v) / 100000.0
        except (ValueError, TypeError):
            return 0.0

    l = _frac("l")
    t = _frac("t")
    r = _frac("r")
    b = _frac("b")

    # All zero -> there's a srcRect element but no actual crop. Word
    # occasionally writes empty <a:srcRect/>; nothing to record.
    if max(abs(l), abs(t), abs(r), abs(b)) < 1e-9:
        return None, src_rect

    # Defensive: if the crop fully eliminates the visible region, treat as
    # no-crop so pdf.py never has to divide by zero. Such a srcRect would
    # produce nothing visible anyway.
    if (1.0 - l - r) <= 1e-9 or (1.0 - t - b) <= 1e-9:
        return None, src_rect

    return (l, t, r, b), src_rect


def normalize_and_copy(source_path, media_dir):
    os.makedirs(media_dir, exist_ok=True)
    basename = os.path.basename(source_path)
    target_path = os.path.join(media_dir, basename)
    if not os.path.exists(target_path):
        shutil.copy2(source_path, target_path)
    return target_path


import time


def safe_extract_zip(file, temp_dir=None, retries=5, delay=0.5):
    for attempt in range(retries):
        try:
            with ZipFile(file, "r") as zip_read:
                if temp_dir is None:
                    temp_dir = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "temp_extracted_pptx",
                    )

                # Temporary staging directory
                staging_dir = temp_dir + "_temp"
                if os.path.exists(staging_dir):
                    shutil.rmtree(staging_dir)
                zip_read.extractall(staging_dir)

            os.makedirs(temp_dir, exist_ok=True)

            # Move everything from staging_dir to temp_dir
            # Do this in case the temp_dir already existed and had contents
            # we don't want to remove
            for name in os.listdir(staging_dir):
                src = os.path.join(staging_dir, name)
                dst = os.path.join(temp_dir, name)
                if os.path.exists(dst):
                    if os.path.isdir(dst) and not os.path.islink(dst):
                        shutil.rmtree(dst)
                    else:
                        os.remove(dst)
                shutil.move(src, dst)
            shutil.rmtree(staging_dir)

            return temp_dir  # success
        except (BadZipFile, PermissionError):
            if attempt == retries - 1:
                raise  # re-raise after last attempt
            time.sleep(delay * (2**attempt))  # exponential backoff


class Unzipped_Office:
    def __init__(self, file, temp_dir=None, aecaller=None):
        safe_extract_zip(file, temp_dir)

        self.temp_dir = temp_dir
        self.type = "ppt" if os.path.isdir(os.path.join(temp_dir, "ppt")) else "word"
        self.media_dir = os.path.join(temp_dir, self.type, "media")

        # Two dicts (inverses of each other) track which marker color
        # represents which (svg_path, crop) reference. We always key by the
        # full (norm_path, crop) tuple -- crop=None for uncropped, a
        # (l, t, r, b) tuple for cropped -- so two crops of the same SVG and
        # the same SVG referenced both cropped and uncropped each get their
        # own color cleanly.
        # crop is a 4-tuple of fractions in [0,1]: (left, top, right, bottom).
        self.svg_to_color = {}   # {(norm_svg_path, crop_or_None): '000001'}
        self.svg_color_map = {}  # {'000001': (norm_svg_path, crop_or_None)}
        # Tracks which color we've already burned into each marker PNG file
        # (absolute path -> '000001'). Two <pic> elements can legally share
        # the same PNG part (same rId, or different rIds pointing at the same
        # target). If they need *different* colors -- e.g. one cropped and one
        # uncropped reference to the same SVG -- a naive second
        # _write_solid_png_9x9 would clobber the first picture's color, and
        # both pictures would end up rendering with the second's substitution
        # in pdf.py. Case 1 below uses this map to detect that situation and
        # divert the conflicting picture to a freshly minted PNG file.
        self.png_color_written = {}
        self._simple_png_next_color = 1  # next RGB code as integer (start at 1)
        # Set of lowercase 'rrggbb' colors already used by pre-existing flat
        # PNGs in the media dir. Populated lazily on first _alloc_next_color
        # call so we never assign a marker color that collides with an
        # unrelated uniform-color image already in the document.
        self._forbidden_colors = None

        self.aecaller = aecaller
        self._queued_png_out = set()
        self._queued_png_lock = threading.Lock()

        if not os.path.exists(self.media_dir):
            self.nfiles = 0
            self.slides = []
            return

        self.nfiles = len(
            [
                f
                for f in os.listdir(self.media_dir)
                if os.path.isfile(os.path.join(self.media_dir, f))
            ]
        )
        self.slides = []

        if self.type == "ppt":
            dir_paths = [
                os.path.join(temp_dir, "ppt", sd)
                for sd in ["slides", "slideMasters", "slideLayouts"]
            ]
            self.media_loc = "../media"
        elif self.type == "word":
            dir_paths = [os.path.join(temp_dir, "word")]
            self.media_loc = "media"

        for dir_path in dir_paths:
            for root_dir, _, files in os.walk(dir_path):
                for file in files:
                    if file.endswith(".xml"):
                        try:
                            self.slides.append(
                                Slide_and_Rels(os.path.join(root_dir, file), self)
                            )
                        except NameError:
                            pass

    def embed_linked(self):
        for slide in self.slides:
            slide.embed_linked()

    def delete_fallback_png(self):
        for slide in self.slides:
            slide.delete_fallback_png()

    def svg_to_png(self, svg_path, png_path):
        print(f"Exporting {svg_path}")

        if self.aecaller is not None:
            self.aecaller.check(overwrite_output, svg_path, png_path,finalization=True)
        else:
            overwrite_output(svg_path, png_path)

    def queue_svg_to_png(self, svg_path, png_path):
        key = os.path.normcase(os.path.abspath(os.path.normpath(png_path)))

        # Deduplicate by output file path so we never render the same PNG twice.
        with self._queued_png_lock:
            if key in self._queued_png_out:
                return
            self._queued_png_out.add(key)

        t = threading.Thread(
            target=self.svg_to_png, args=(svg_path, png_path), daemon=True
        )
        t.start()
        self.threads.append(t)

    def leave_fallback_png(self):
        self.threads = []
        for slide in self.slides:
            slide.leave_fallback_png()
        for t in self.threads:
            t.join()

    def leave_fallback_png_simple(self):
        for slide in self.slides:
            slide.leave_fallback_png_simple()

    def _norm_path(self, p: str) -> str:
        return os.path.normcase(os.path.abspath(os.path.normpath(p))) if p else ""

    def _lookup_color_for_svg(self, svg_path: str, crop=None):
        np = self._norm_path(svg_path)
        return self.svg_to_color.get((np, crop))

    def _register_svg_color(self, svg_path: str, color_hex: str, crop=None):
        np = self._norm_path(svg_path)
        self.svg_to_color[(np, crop)] = color_hex
        self.svg_color_map[color_hex] = (np, crop)
        
    def _saved_rasters_dir(self):
        """Sibling temp dir holding pristine copies of every raster we swap
        out for a marker, so pdf.py can re-embed the originals losslessly."""
        d = os.path.join(self.temp_dir, "_saved_rasters")
        os.makedirs(d, exist_ok=True)
        return d
    
    def _save_raster_copy(self, src_path):
        """Copy src_path into _saved_rasters_dir; idempotent per src."""
        if not hasattr(self, "_raster_save_map"):
            self._raster_save_map = {}
        key = self._norm_path(src_path)
        cached = self._raster_save_map.get(key)
        if cached is not None:
            return cached
        base = os.path.basename(src_path)
        dest = os.path.join(self._saved_rasters_dir(), base)
        if os.path.exists(dest):
            root, ext = os.path.splitext(base)
            n = 1
            while os.path.exists(dest):
                dest = os.path.join(self._saved_rasters_dir(), f"{root}_{n}{ext}")
                n += 1
        shutil.copy2(src_path, dest)
        self._raster_save_map[key] = dest
        return dest

    def _hex_to_rgb(self, color_hex: str):
        n = int(color_hex, 16)
        return ((n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF)

    def ensure_image_in_content_types(self, filename):
        """
        Ensures that the correct image content type for `filename` is present
        in [Content_Types].xml within self.temp_dir.

        Supports all common Office image formats (PNG, JPG, JPEG, GIF, BMP,
        TIFF, EMF, WMF, SVG).
        """
        # --- Determine extension and MIME type ---
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        mime_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "tif": "image/tiff",
            "tiff": "image/tiff",
            "emf": "image/x-emf",
            "wmf": "image/x-wmf",
            "svg": "image/svg+xml",
        }

        if ext not in mime_map:
            raise ValueError(f"Unsupported image type: {ext}")

        content_type = mime_map[ext]
        content_types_path = os.path.join(self.temp_dir, "[Content_Types].xml")

        # --- Parse and check existing entries ---
        tree = ET.parse(content_types_path)
        root = tree.getroot()
        ns = {"ct": "http://schemas.openxmlformats.org/package/2006/content-types"}

        already_defined = any(
            elem.attrib.get("Extension", "").lower() == ext
            for elem in root.findall("ct:Default", ns)
        )

        # --- Add entry if missing ---
        if not already_defined:
            new_default = ET.Element(
                "{http://schemas.openxmlformats.org/package/2006/content-types}Default",
                Extension=ext,
                ContentType=content_type,
            )
            root.append(new_default)
            tree.write(content_types_path, xml_declaration=True, encoding="UTF-8")
            print(
                f"Added {ext.upper()} content type ({content_type}) to [Content_Types].xml"
            )

    def cleanup_unused_rels_and_media(self):
        referenced_files = set()
        for slide in self.slides:
            rfiles = slide.cleanup_unused_rels()
            referenced_files.update(rfiles)

        # Delete unused media
        if os.path.exists(self.media_dir):
            for file in os.listdir(self.media_dir):
                if file not in referenced_files:
                    path = os.path.join(self.media_dir, file)
                    os.remove(path)
                    print(f"Deleted unused media: {path}")

    def get_target_index(self):
        """
        Returns a dict mapping absolute paths to a list of (slide_name, mode) tuples
        """
        index = {}
        all_targets = {}
        for slide in self.slides:
            name = slide.slide_name
            targets = slide.get_slide_targets()
            if name in all_targets:
                all_targets[name].extend(targets)
            else:
                all_targets[name] = targets[:]

        for slide_name, targets in all_targets.items():
            for target in targets:
                if target.abs_path:
                    index.setdefault(target.abs_path, []).append(
                        (slide_name, target.mode)
                    )
        return index

    def rezip(self, output):
        with ZipFile(output, "w") as zip_write:
            for root, _, files in os.walk(self.temp_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, self.temp_dir).replace(
                        os.sep, "/"
                    )

                    with open(abs_path, "rb") as f:
                        data = f.read()

                    zip_info = ZipInfo(rel_path, (1980, 1, 1, 0, 0, 0))
                    zip_info.compress_type = ZIP_DEFLATED
                    zip_info.create_system = 0
                    zip_info.create_version = 45
                    zip_info.extract_version = 20
                    zip_info.flag_bits = 6
                    zip_info.volume = 0
                    zip_info.internal_attr = 0
                    zip_info.external_attr = 0

                    zip_write.writestr(zip_info, data)

    def unrenderable_fonts_to_paths(self):
        """
        Load each SVG in self.media_dir and convert unrenderable text in
        LibreOffice to paths using the Autoexporter flow, then overwrite in place.
        Returns a list of processed SVG paths.
        """
        # Fonts to convert to paths
        unrenderable = ["Helvetica Light"]

        processed = []
        if not os.path.exists(self.media_dir):
            return processed

        import inkex
        import dhelpers as dh
        from types import SimpleNamespace
        from autoexporter import get_svg, Exporter, Act, repeat_remove

        tempdir = None

        bfn = inkex.inkscape_system_info.binary_location
        for fname in os.listdir(self.media_dir):
            fpath = os.path.join(self.media_dir, fname)
            if not (os.path.isfile(fpath) and fname.lower().endswith(".svg")):
                continue
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                raw = fh.read()
                if not any(u in raw for u in unrenderable):
                    # None of the target font names even appear; skip this file
                    continue

            svg = get_svg(fpath)
            ttags = {inkex.TextElement.ctag, inkex.FlowRoot.ctag}
            tels = [el for el in dh.visible_descendants(svg) if el.tag in ttags]

            # Gather IDs of elements with unrenderable fonts
            bad_ids = {
                el.get_id()
                for el in tels
                for d in el.descendants2()
                if (ff := d.cspecified_style.get("font-family"))
                and any(bad in ff for bad in unrenderable)
            }

            if not bad_ids:
                continue

            # Create temporary output path
            if tempdir is None:
                tempdir, temphead = dh.shared_temp("aeftf")
            tmpout = os.path.join(tempdir, f"{temphead}_ttop.svg")

            # Minimal Exporter context (mimics autoexporter)
            opts = SimpleNamespace(bfn=bfn)
            exp = Exporter(fpath, opts)
            exp.tempdir = tempdir
            exp.stpact = "object-to-path"
            stp_act = Act("stp", list(bad_ids), exp, tmpout)
            exp.split_acts(fnm=fpath, acts=[stp_act], get_bbs=False)

            # Replace file if new SVG created
            if os.path.exists(tmpout):
                new_svg = get_svg(tmpout)
                dh.overwrite_svg(new_svg, fpath)
                processed.append(fpath)
                repeat_remove(tmpout)

        if tempdir:
            repeat_remove(os.path.join(tempdir, temphead + ".lock"))
        return processed

    def _alloc_next_color(self):
        """
        Return ('%06X' % n).lower() and (R,G,B) for next color, skipping any
        color already used by a pre-existing flat (uniform-color) PNG in the
        media dir so our marker colors stay unique.
        """
        self._ensure_forbidden_colors_scanned()
        while True:
            n = self._simple_png_next_color
            self._simple_png_next_color += 1
            color_hex = f"{n:06x}"
            if color_hex not in self._forbidden_colors:
                r = (n >> 16) & 0xFF
                g = (n >> 8) & 0xFF
                b = (n >> 0) & 0xFF
                return color_hex, (r, g, b)

    def _ensure_forbidden_colors_scanned(self):
        """
        Lazily walk self.media_dir once and record the colors of every
        pre-existing uniform-color PNG. Called before the first marker color
        is handed out, so the scan reflects the document's original state
        (no markers we wrote ourselves are present yet).
        """
        if self._forbidden_colors is not None:
            return
        forbidden = set()
        if os.path.isdir(self.media_dir):
            for fname in os.listdir(self.media_dir):
                if not fname.lower().endswith(".png"):
                    continue
                path = os.path.join(self.media_dir, fname)
                if not os.path.isfile(path):
                    continue
                color_hex = self._read_png_uniform_color(path)
                if color_hex is not None:
                    forbidden.add(color_hex.lower())
        self._forbidden_colors = forbidden

    def _read_png_uniform_color(self, path):
        """
        If the PNG at ``path`` is a single uniform opaque color, return that
        color as a lowercase 'rrggbb' hex string. Otherwise return None.

        Supports non-interlaced 8-bit PNGs of color types 0 (grayscale),
        2 (truecolor RGB), 3 (palette), 4 (gray + alpha) and 6 (RGB + alpha).
        Anything else (interlaced, 1/2/4/16-bit depth, unknown filter) is
        treated as not-flat. Decoding bails on the first deviating pixel.
        """
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            return None
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return None

        pos = 8
        width = height = bit_depth = color_type = None
        interlace = 0
        idat = bytearray()
        palette = None

        while pos + 8 <= len(data):
            try:
                chunk_len = struct.unpack(">I", data[pos:pos + 4])[0]
            except struct.error:
                return None
            chunk_type = data[pos + 4:pos + 8]
            chunk_start = pos + 8
            chunk_end = chunk_start + chunk_len
            if chunk_end + 4 > len(data):
                return None
            chunk_data = data[chunk_start:chunk_end]
            pos = chunk_end + 4  # skip CRC

            if chunk_type == b"IHDR":
                if len(chunk_data) < 13:
                    return None
                (width, height, bit_depth, color_type,
                 _comp, _filt, interlace) = struct.unpack(">IIBBBBB", chunk_data[:13])
            elif chunk_type == b"IDAT":
                idat.extend(chunk_data)
            elif chunk_type == b"PLTE":
                palette = bytes(chunk_data)
            elif chunk_type == b"IEND":
                break

        if (not width or not height
                or bit_depth != 8 or interlace != 0
                or color_type is None):
            return None

        if color_type == 0:
            bpp = 1
        elif color_type == 2:
            bpp = 3
        elif color_type == 3:
            if not palette:
                return None
            bpp = 1
        elif color_type == 4:
            bpp = 2
        elif color_type == 6:
            bpp = 4
        else:
            return None

        try:
            raw = zlib.decompress(bytes(idat))
        except zlib.error:
            return None

        stride = bpp * width
        if len(raw) != (1 + stride) * height:
            return None

        def _paeth(a, b, c):
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            if pa <= pb and pa <= pc:
                return a
            return b if pb <= pc else c

        prev = bytearray(stride)
        target = None  # bytes-like row[0:bpp] of first row, established on row 0
        src_pos = 0
        for _row in range(height):
            f = raw[src_pos]; src_pos += 1
            line = raw[src_pos:src_pos + stride]; src_pos += stride
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
                return None

            if target is None:
                target = bytes(rec[:bpp])
            for i in range(0, stride, bpp):
                if rec[i:i + bpp] != target:
                    return None
            prev = rec

        if target is None:
            return None

        # Convert the per-pixel bytes to RGB.
        if color_type == 2:
            r, g, b = target[0], target[1], target[2]
        elif color_type == 0:
            r = g = b = target[0]
        elif color_type == 3:
            idx = target[0]
            if (idx + 1) * 3 > len(palette):
                return None
            r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
        elif color_type == 4:
            if target[1] != 255:
                return None
            r = g = b = target[0]
        elif color_type == 6:
            if target[3] != 255:
                return None
            r, g, b = target[0], target[1], target[2]
        else:
            return None
        return f"{r:02x}{g:02x}{b:02x}"

    def _write_solid_png_9x9(self, rgb, out_path):
        """
        Manually write a 9x9 opaque truecolor PNG with no alpha.
        Uses: PNG signature, IHDR, IDAT (zlib-compressed), IEND. No libraries like PIL.
        """
        w, h = 9, 9
        r, g, b = rgb

        def _chunk(typ, data=b""):
            # PNG chunk: length(4) + type(4) + data + crc(4)
            crc = binascii.crc32(typ)
            crc = binascii.crc32(data, crc) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", crc)

        # Signature
        sig = b"\x89PNG\r\n\x1a\n"

        # IHDR: width, height, bit depth=8, color type=2 (truecolor), compression=0, filter=0, interlace=0
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        ch_ihdr = _chunk(b"IHDR", ihdr)

        # Raw image data: each row starts with filter byte 0, then 9 * 3 bytes (RGB)
        one_row = bytes([0]) + bytes((r, g, b)) * w
        raw = one_row * h
        comp = zlib.compress(raw, level=9)
        ch_idat = _chunk(b"IDAT", comp)

        ch_iend = _chunk(b"IEND", b"")

        with open(out_path, "wb") as f:
            f.write(sig + ch_ihdr + ch_idat + ch_iend)


class SlideTarget:
    def __init__(self, target, mode, abs_path):
        self.target = target  # str: the raw target string from the rels
        self.mode = mode  # str: either "embed" or "link"
        self.abs_path = abs_path  # str: resolved absolute path

    def __repr__(self):
        return f"SlideTarget(target={self.target!r}, mode={self.mode!r}, abs_path={self.abs_path!r})"


class Slide_and_Rels:
    def __init__(self, path, uzo):
        self.slide_path = path
        self.uzo = uzo
        self.rels_path = os.path.join(
            os.path.dirname(self.slide_path), "_rels", os.path.basename(path) + ".rels"
        )
        if not os.path.exists(self.rels_path):
            raise NameError("No rels file")

        if uzo.type == "word":
            self.slide_name = "Document"
        else:
            self.slide_name = re.sub(
                r"([a-zA-Z]+?)(\d+)\.xml$",
                lambda m: f"{' '.join(re.findall('[A-Z][a-z]*|[a-z]+', m.group(1))).title()} {int(m.group(2))}",
                os.path.basename(path),
            )

        huge_parser = ET.XMLParser(huge_tree=True)
        self.slide_tree = ET.parse(self.slide_path, huge_parser)
        self.slide_root = self.slide_tree.getroot()
        self.rels_tree = ET.parse(self.rels_path, huge_parser)
        self.rels_root = self.rels_tree.getroot()

    def get_slide_targets(self):
        """
        Returns a list of SlideTarget objects:
        - target: raw target string from the .rels file
        - mode: 'embed' or 'link'
        - abs_path: absolute path to the file (resolved but not checked for existence)
        """
        used_ids = {}
        for elem in self.slide_root.iter():
            for attr in elem.attrib:
                if attr.endswith("}embed"):
                    used_ids[elem.attrib[attr]] = "embed"
                elif attr.endswith("}link"):
                    used_ids[elem.attrib[attr]] = "link"

        results = []
        for rel in self.rels_root:
            rel_id = rel.attrib.get("Id")
            if rel_id not in used_ids:
                continue

            mode = used_ids[rel_id]
            target = unquote(rel.attrib.get("Target", ""))
            if target.startswith("file:///"):
                abs_path = os.path.normpath(target[8:])
            elif target.startswith("file://"):
                abs_path = os.path.normpath(target[7:])
            elif target.startswith("file:"):
                abs_path = os.path.normpath(target[5:])
            else:
                rel_base = os.path.dirname(self.slide_path)
                abs_path = os.path.normpath(os.path.join(rel_base, target))

            results.append(SlideTarget(target, mode, abs_path))
        return results

    def embed_linked(self):
        rel_map = {
            rel.attrib["Id"]: rel
            for rel in self.rels_root
            if rel.tag.endswith("Relationship")
        }
        existing_ids = set(rel_map.keys())
        changed_rels = False
        changed_slide = False

        new_names = set()
        for rel in list(self.rels_root):
            target_mode = rel.get("TargetMode")
            raw_target = rel.get("Target")
            if target_mode != "External" and not (raw_target or "").startswith("file"):
                continue

            abs_path = unquote(raw_target or "")
            if abs_path.startswith("file:///"):
                abs_path = abs_path[8:]
            elif abs_path.startswith("file://"):
                abs_path = abs_path[7:]
            elif abs_path.startswith("file:"):
                abs_path = abs_path[5:]
            abs_path = os.path.normpath(abs_path)

            if not os.path.exists(abs_path):
                abs_path = dh.si_config.find_missing_links(abs_path)
                if not abs_path:
                    existing_ids.remove(rel.attrib["Id"])
                    continue

            os.makedirs(self.uzo.media_dir, exist_ok=True)
            _, ext = os.path.splitext(abs_path)

            new_path = None
            while new_path is None or os.path.exists(new_path):
                new_name = f"image{self.uzo.nfiles + 1}{ext}"
                new_path = os.path.join(self.uzo.media_dir, new_name)
                new_names.add(new_name)
                self.uzo.nfiles += 1

            shutil.copy2(abs_path, new_path)
            from urllib.parse import quote

            rel.set("Target", f"{self.uzo.media_loc}/{quote(new_name)}")
            if "TargetMode" in rel.attrib:
                del rel.attrib["TargetMode"]
            changed_rels = True

        for elem in self.slide_root.iter():
            if elem.tag.endswith("blip") or elem.tag.endswith("svgBlip"):
                embed_id = elem.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                )
                link_id = elem.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link"
                )

                if link_id:
                    if link_id not in existing_ids and embed_id is not None:
                        elem.attrib[
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link"
                        ] = embed_id
                        link_id = embed_id
                    elem.attrib[
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                    ] = link_id
                    del elem.attrib[
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link"
                    ]
                    changed_slide = True

        if changed_rels:
            self.rels_tree.write(
                self.rels_path,
                xml_declaration=True,
                encoding="UTF-8",
                pretty_print=False,
            )
            for nn in new_names:
                self.uzo.ensure_image_in_content_types(nn)
        if changed_slide:
            self.slide_tree.write(
                self.slide_path,
                xml_declaration=True,
                encoding="UTF-8",
                pretty_print=False,
            )

    def delete_fallback_png(self):
        ns = {
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
        }
        changed_slide = False
        svgblips = []

        for elem in self.slide_root.iter():
            if elem.tag == f"{{{ns['asvg']}}}svgBlip":
                svgblips.append(elem)

        if not svgblips:
            return

        for svgblip in svgblips:
            # Find the <a:blip> ancestor
            ext = svgblip.getparent()
            extLst = ext.getparent() if ext is not None else None
            blip = extLst.getparent() if extLst is not None else None

            if (
                ext is not None
                and ext.tag == f"{{{ns['a']}}}ext"
                and extLst is not None
                and extLst.tag == f"{{{ns['a']}}}extLst"
                and blip is not None
                and blip.tag == f"{{{ns['a']}}}blip"
            ):
                blip.attrib[f"{{{ns['r']}}}embed"] = svgblip.attrib.get(
                    f"{{{ns['r']}}}embed"
                )
                for k in blip:
                    blip.remove(k)
                changed_slide = True

        if changed_slide:
            self.slide_tree.write(
                self.slide_path, xml_declaration=True, encoding="UTF-8", method="xml"
            )

    def leave_fallback_png(self):
        ns = {
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
        }

        def min_dpi(blip_el, png_abs_path):
            def _png_px_size(png_path):
                # Read PNG width/height from IHDR (no PIL)
                try:
                    with open(png_path, "rb") as f:
                        sig = f.read(8)
                        if sig != b"\x89PNG\r\n\x1a\n":
                            return None
                        # Next chunk must be IHDR
                        _len = struct.unpack(">I", f.read(4))[0]
                        ctyp = f.read(4)
                        if ctyp != b"IHDR":
                            return None
                        data = f.read(_len)
                        if len(data) < 8:
                            return None
                        w, h = struct.unpack(">II", data[:8])
                        return (w, h)
                except Exception:
                    return None

            def _display_emu_from_blip(blip_el):
                # Walk up to <p:pic>, then grab <a:xfrm><a:ext cx cy>
                cur = blip_el
                while cur is not None and not cur.tag.endswith("}pic"):
                    cur = cur.getparent()
                if cur is None:
                    return None
                xfrm = cur.find(".//a:xfrm", namespaces=ns)
                if xfrm is None:
                    return None
                ext = xfrm.find("a:ext", namespaces=ns)
                if ext is None:
                    return None
                try:
                    cx = int(ext.get("cx"))
                    cy = int(ext.get("cy"))
                    return (cx, cy)
                except Exception:
                    return None

            px = _png_px_size(png_abs_path)
            emu = _display_emu_from_blip(blip_el)
            if not px or not emu:
                return True  # can't evaluate -> don't force rerender
            wpx, hpx = px
            cx, cy = emu
            if cx <= 0 or cy <= 0:
                return True
            win = cx / EMU_PER_INCH
            hin = cy / EMU_PER_INCH
            if win <= 0 or hin <= 0:
                return True
            dpx = wpx / win
            dpy = hpx / hin
            return min(dpx, dpy)

        rel_id_to_target = {
            rel.attrib["Id"]: unquote(rel.attrib["Target"])
            for rel in self.rels_root
            if rel.tag.endswith("Relationship")
        }

        changed_slide = False
        changed_rels = False
        svgblips = []
        blips = []

        # Gather all svgblips and regular blips
        for elem in self.slide_root.iter():
            if elem.tag == f"{{{ns['asvg']}}}svgBlip":
                svgblips.append(elem)
            elif elem.tag == f"{{{ns['a']}}}blip":
                rid = elem.attrib.get(f"{{{ns['r']}}}embed")
                target = rel_id_to_target.get(rid, "").lower() if rid else ""
                if target.endswith(".svg"):
                    blips.append(elem)

        if len(svgblips) + len(blips) == 0:
            return

        removed_svgblips = []
        for svgblip in svgblips:
            # SVGs are usually embedded with a backup PNG
            # Find the <a:blip> ancestor
            ext = svgblip.getparent()
            extLst = ext.getparent() if ext is not None else None
            blip = extLst.getparent() if extLst is not None else None

            if (
                ext is not None
                and ext.tag == f"{{{ns['a']}}}ext"
                and extLst is not None
                and extLst.tag == f"{{{ns['a']}}}extLst"
                and blip is not None
                and blip.tag == f"{{{ns['a']}}}blip"
            ):
                embed_rid = blip.attrib.get(f"{{{ns['r']}}}embed")
                target = rel_id_to_target.get(embed_rid, "").lower()
                if embed_rid and target.endswith(".png"):
                    # Resolve SVG + PNG absolute paths (part-dir relative)
                    source_part_path = (
                        self.rels_path.replace("\\_rels\\", "\\")
                        .replace("/_rels/", "/")
                        .rsplit(".rels", 1)[0]
                    )
                    part_dir = os.path.dirname(source_part_path)

                    # svgblip's rid points to the SVG
                    svg_rid = svgblip.attrib.get(f"{{{ns['r']}}}embed")
                    svg_target = rel_id_to_target.get(svg_rid, "")
                    svg_abs = (
                        os.path.normpath(os.path.join(part_dir, svg_target))
                        if svg_target
                        else None
                    )

                    # blip's embed_rid points to the PNG fallback
                    png_target = rel_id_to_target.get(embed_rid, "")
                    png_abs = (
                        os.path.normpath(os.path.join(part_dir, png_target))
                        if png_target
                        else None
                    )

                    # If PNG exists but is too low DPI for its displayed size -> rerender
                    if svg_abs and png_abs and os.path.exists(png_abs):
                        mdpi = min_dpi(blip, png_abs)
                        print(
                            "DPI of " + svg_abs + " : " + str(int(mdpi)) + ""
                            if mdpi >= DPI_MIN
                            else " (rerendering)"
                        )
                        if mdpi < DPI_MIN:
                            self.uzo.queue_svg_to_png(svg_abs, png_abs)

                    blip.remove(extLst)
                    changed_slide = True
                    removed_svgblips.append(svgblip)

                else:
                    # No PNG fallback exists. Handle the full conversion here so we
                    # never leave an orphaned SVG relationship in the .rels file and
                    # never promote an <asvg:svgBlip> into the tree as an intermediate
                    # state that the second loop then has to clean up.
                    #
                    # Also guard against a second svgBlip that shares the same parent
                    # blip already detached by a previous iteration of this loop.
                    blip_parent = blip.getparent()
                    if blip_parent is None:
                        removed_svgblips.append(svgblip)
                        continue

                    svg_rid = svgblip.attrib.get(f"{{{ns['r']}}}embed")
                    svg_target = rel_id_to_target.get(svg_rid, "") if svg_rid else ""

                    if svg_rid and svg_target.lower().endswith(".svg"):
                        source_part_path = (
                            self.rels_path.replace("\\_rels\\", "\\")
                            .replace("/_rels/", "/")
                            .rsplit(".rels", 1)[0]
                        )
                        svg_path = os.path.normpath(
                            os.path.join(os.path.dirname(source_part_path), svg_target)
                        )

                        new_png_path = None
                        while new_png_path is None or os.path.exists(new_png_path):
                            self.uzo.nfiles += 1
                            new_png_name = f"image{self.uzo.nfiles}.png"
                            new_png_path = os.path.join(
                                self.uzo.media_dir, new_png_name
                            )

                        new_rel_target = f"{self.uzo.media_loc}/{new_png_name}"
                        self.uzo.queue_svg_to_png(svg_path, new_png_path)

                        imagenum = len(self.rels_root) + 1
                        while f"rId{imagenum}" in rel_id_to_target:
                            imagenum += 1
                        new_rid = f"rId{imagenum}"
                        rel_id_to_target[new_rid] = new_rel_target  # keep dict in sync
                        new_blip = ET.Element(f"{{{ns['a']}}}blip")
                        new_blip.attrib[f"{{{ns['r']}}}embed"] = new_rid
                        blip_parent.replace(blip, new_blip)
                        changed_slide = True

                        rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
                        ET.SubElement(
                            self.rels_root,
                            f"{{{rels_ns}}}Relationship",
                            {
                                "Id": new_rid,
                                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                                "Target": new_rel_target,
                            },
                        )
                        changed_rels = True

                    removed_svgblips.append(svgblip)

        all_remaining = {b for b in svgblips + blips if b not in set(removed_svgblips)}

        for blip in all_remaining:
            # If there is no backup PNG, replace bare <asvg:svgBlip> or <a:blip>
            # with new PNG <a:blip>
            parent = blip.getparent()  # ← guard against orphaned nodes
            if parent is None:
                continue  # already detached in the first loop

            svg_rid = blip.attrib.get(f"{{{ns['r']}}}embed")
            if not svg_rid:
                continue

            svg_target = rel_id_to_target.get(svg_rid)
            if not svg_target or not svg_target.lower().endswith(".svg"):
                continue

            source_part_path = (
                self.rels_path.replace("\\_rels\\", "\\")
                .replace("/_rels/", "/")
                .rsplit(".rels", 1)[0]
            )
            svg_path = os.path.normpath(
                os.path.join(os.path.dirname(source_part_path), svg_target)
            )

            new_png_path = None
            while new_png_path is None or os.path.exists(new_png_path):
                self.uzo.nfiles += 1
                new_png_name = f"image{self.uzo.nfiles}.png"
                new_png_path = os.path.join(self.uzo.media_dir, new_png_name)

            new_rel_target = f"{self.uzo.media_loc}/{new_png_name}"
            self.uzo.queue_svg_to_png(svg_path, new_png_path)

            imagenum = len(self.rels_root) + 1
            while f"rId{imagenum}" in rel_id_to_target:
                imagenum += 1
            new_rid = f"rId{imagenum}"
            rel_id_to_target[new_rid] = new_rel_target  # keep dict in sync
            new_blip = ET.Element(f"{{{ns['a']}}}blip")
            new_blip.attrib[f"{{{ns['r']}}}embed"] = new_rid
            parent.replace(blip, new_blip)
            changed_slide = True

            rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            ET.SubElement(
                self.rels_root,
                f"{{{rels_ns}}}Relationship",
                {
                    "Id": new_rid,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                    "Target": new_rel_target,
                },
            )
            changed_rels = True

        if changed_slide:
            self.slide_tree.write(
                self.slide_path, xml_declaration=True, encoding="UTF-8", method="xml"
            )
        if changed_rels:
            self.rels_tree.write(
                self.rels_path, xml_declaration=True, encoding="UTF-8", method="xml"
            )
            self.uzo.ensure_image_in_content_types("foo.png")

    def cleanup_unused_rels(self):
        # Collect all embed/link rel IDs used in the slide
        referenced_files = set()
        used_ids_in_slide = set()
        for elem in self.slide_root.iter():
            for attr_name, attr_val in elem.attrib.items():
                if attr_name.endswith("}embed") or attr_name.endswith("}link"):
                    used_ids_in_slide.add(attr_val)

        changed_rels = False
        for rel in list(self.rels_root):
            rel_id = rel.attrib.get("Id")
            target = unquote(rel.attrib.get("Target", ""))
            target_in_media = target.startswith(self.uzo.media_loc)

            if rel_id not in used_ids_in_slide and target_in_media:
                self.rels_root.remove(rel)
                changed_rels = True
            elif target_in_media:
                referenced_files.add(os.path.basename(target))

        if changed_rels:
            os.makedirs(os.path.dirname(self.rels_path), exist_ok=True)
            self.rels_tree.write(self.rels_path, xml_declaration=True, encoding="UTF-8")
        return referenced_files

    def leave_fallback_png_simple(self):
        """
        Alternate to leave_fallback_png:
        - Ensures each SVG reference resolves to a PNG fallback that is a 9x9
          opaque solid color (sequential RGB 000001, 000002, ...)
        - Records color -> (svg_path, crop_or_None) in self.uzo.svg_color_map
        """
        ns = {
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
        }

        rel_id_to_target = {
            rel.attrib["Id"]: unquote(rel.attrib.get("Target", ""))
            for rel in self.rels_root
            if rel.tag.endswith("Relationship")
        }

        changed_slide = False
        changed_rels = False

        # Gather all svgBlips and any <a:blip> that actually points to an .svg
        svgblips = []
        blips_pointing_to_svg = []
        for elem in self.slide_root.iter():
            if elem.tag == f"{{{ns['asvg']}}}svgBlip":
                svgblips.append(elem)
            elif elem.tag == f"{{{ns['a']}}}blip":
                rid = elem.attrib.get(f"{{{ns['r']}}}embed")
                target = rel_id_to_target.get(rid, "").lower() if rid else ""
                if target.endswith(".svg"):
                    blips_pointing_to_svg.append(elem)

        if not svgblips and not blips_pointing_to_svg:
            return

        # Helper: resolve source part dir (the part that owns this .rels)
        source_part_path = (
            self.rels_path.replace("\\_rels\\", "\\")
            .replace("/_rels/", "/")
            .rsplit(".rels", 1)[0]
        )
        source_part_dir = os.path.dirname(source_part_path)

        # svgBlips fully resolved by Case 1 below: their <a:extLst> has been
        # detached from the live tree, so they should not be re-handled by
        # Case 2 (which would otherwise allocate a duplicate color/PNG/rel
        # for the same picture).
        case1_handled = set()

        # Case 1: svgBlip paired with an existing PNG fallback -> overwrite that PNG file in-place
        for svgblip in list(svgblips):
            ext = svgblip.getparent()
            extLst = ext.getparent() if ext is not None else None
            blip = extLst.getparent() if extLst is not None else None
            if not (
                ext is not None
                and ext.tag == f"{{{ns['a']}}}ext"
                and extLst is not None
                and extLst.tag == f"{{{ns['a']}}}extLst"
                and blip is not None
                and blip.tag == f"{{{ns['a']}}}blip"
            ):
                continue

            png_rid = blip.attrib.get(f"{{{ns['r']}}}embed")
            png_target = rel_id_to_target.get(png_rid, "")
            has_png = png_rid and png_target.lower().endswith(".png")

            # Need the associated SVG's rid/target to record its name
            svg_rid = svgblip.attrib.get(f"{{{ns['r']}}}embed")
            svg_target = rel_id_to_target.get(svg_rid, "")
            # Resolve absolute svg path for record (and to check existence)
            if svg_target:
                svg_path = os.path.abspath(
                    os.path.normpath(os.path.join(source_part_dir, svg_target))
                )
            else:
                svg_path = ""

            if has_png:
                # Overwrite existing media PNG file with our 9x9 color square
                # Target is relative to the part; we want absolute disk path:
                png_abs = os.path.normpath(os.path.join(source_part_dir, png_target))

                # If this picture is cropped via <a:srcRect>, record the crop
                # so pdf.py can substitute only the visible portion of the SVG
                # instead of squashing the whole thing into the cropped frame.
                # A non-zero crop forces a unique color per (SVG, crop) combo
                # so two crops of the same SVG don't collide.
                crop, srcrect_elem = _find_srcrect_crop(svgblip)

                # Use existing color if we've seen this SVG (with this crop) before
                if svg_path:
                    existing = self.uzo._lookup_color_for_svg(svg_path, crop)
                else:
                    existing = None

                if existing:
                    color_hex = existing
                    rgb = self.uzo._hex_to_rgb(existing)
                else:
                    color_hex, rgb = self.uzo._alloc_next_color()
                    if svg_path:
                        self.uzo._register_svg_color(svg_path, color_hex, crop)

                # Detect the multi-reference conflict: same PNG file already
                # had a *different* color burned in for an earlier <pic>. We
                # can't share the file, so mint a fresh one and rewire just
                # this picture's <a:blip> r:embed to it. The other picture
                # still points at the original file.
                prev_color = self.uzo.png_color_written.get(png_abs)
                if prev_color is not None and prev_color != color_hex:
                    new_png_path = None
                    while new_png_path is None or os.path.exists(new_png_path):
                        self.uzo.nfiles += 1
                        new_png_name = f"image{self.uzo.nfiles}.png"
                        new_png_path = os.path.join(self.uzo.media_dir, new_png_name)
                    new_rel_target = f"{self.uzo.media_loc}/{new_png_name}"
                    imagenum = len(self.rels_root) + 1
                    while f"rId{imagenum}" in rel_id_to_target:
                        imagenum += 1
                    new_rid = f"rId{imagenum}"
                    rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
                    ET.SubElement(
                        self.rels_root,
                        f"{{{rels_ns}}}Relationship",
                        {
                            "Id": new_rid,
                            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                            "Target": new_rel_target,
                        },
                    )
                    rel_id_to_target[new_rid] = new_rel_target
                    changed_rels = True
                    self.uzo._write_solid_png_9x9(rgb, new_png_path)
                    self.uzo.png_color_written[new_png_path] = color_hex
                    blip.attrib[f"{{{ns['r']}}}embed"] = new_rid
                else:
                    self.uzo._write_solid_png_9x9(rgb, png_abs)
                    self.uzo.png_color_written[png_abs] = color_hex
                self.uzo.ensure_image_in_content_types("dummy.png")
                # Also remove the <asvg:svgBlip> extension so the PNG fallback is used
                blip.remove(extLst)
                # Drop the <a:srcRect> too. The marker PNG is uniform color so
                # cropping it has no visual effect, and removing it lets the
                # PDF generator place the full marker in the displayed extent
                # without stitching together a sub-image XObject. pdf.py then
                # applies the inverse crop using the recorded crop tuple.
                if srcrect_elem is not None:
                    parent_fill = srcrect_elem.getparent()
                    if parent_fill is not None:
                        parent_fill.remove(srcrect_elem)
                case1_handled.add(svgblip)
                changed_slide = True

        # Case 2: bare svgBlip or <a:blip> that points to an .svg but has no PNG fallback
        # Replace node with a new <a:blip> that points at a freshly minted PNG
        residual = [n for n in (svgblips + blips_pointing_to_svg)
                    if n not in case1_handled]
        for node in residual:
            # Get the SVG rid/target
            svg_rid = node.attrib.get(f"{{{ns['r']}}}embed")
            if not svg_rid:
                continue
            svg_target = rel_id_to_target.get(svg_rid)
            if not (svg_target and svg_target.lower().endswith(".svg")):
                continue

            svg_path = os.path.abspath(
                os.path.normpath(os.path.join(source_part_dir, svg_target))
            )

            # See Case 1 above: detect any srcRect on this picture so pdf.py
            # can inverse-crop the SVG-PDF replacement instead of squashing it.
            crop, srcrect_elem = _find_srcrect_crop(node)

            # Allocate a new media png name
            new_png_path = None
            while new_png_path is None or os.path.exists(new_png_path):
                self.uzo.nfiles += 1
                new_png_name = f"image{self.uzo.nfiles}.png"
                new_png_path = os.path.join(self.uzo.media_dir, new_png_name)
            new_rel_target = f"{self.uzo.media_loc}/{new_png_name}"

            # Generate or re-use color + PNG
            existing = (
                self.uzo._lookup_color_for_svg(svg_path, crop) if svg_path else None
            )
            if existing:
                color_hex = existing
                rgb = self.uzo._hex_to_rgb(existing)
            else:
                color_hex, rgb = self.uzo._alloc_next_color()
                if svg_path:
                    self.uzo._register_svg_color(svg_path, color_hex, crop)

            self.uzo._write_solid_png_9x9(rgb, new_png_path)
            self.uzo.png_color_written[new_png_path] = color_hex

            # Drop any <a:srcRect> sibling now that the marker PNG (uniform
            # color) will fill the picture's full extent. The crop is recorded
            # on the color and replayed during PDF post-processing.
            if srcrect_elem is not None:
                parent_fill = srcrect_elem.getparent()
                if parent_fill is not None:
                    parent_fill.remove(srcrect_elem)

            # Create new relationship
            imagenum = len(self.rels_root) + 1
            while f"rId{imagenum}" in rel_id_to_target:
                imagenum += 1
            new_rid = f"rId{imagenum}"

            rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            ET.SubElement(
                self.rels_root,
                f"{{{rels_ns}}}Relationship",
                {
                    "Id": new_rid,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                    "Target": new_rel_target,
                },
            )
            rel_id_to_target[new_rid] = new_rel_target
            changed_rels = True

            # If this is an <asvg:svgBlip> nested in <a:blip>/<a:extLst>/<a:ext>
            # whose outer <a:blip> has no r:embed, promote the new PNG rid onto
            # the outer blip and drop the extLst. A plain parent.replace here
            # would leave the PNG reference buried inside the SVG-extension slot
            # and the outer blip still with no primary image, so PowerPoint
            # would render a broken-picture placeholder.
            promoted = False
            if node.tag == f"{{{ns['asvg']}}}svgBlip":
                ext = node.getparent()
                extLst = ext.getparent() if ext is not None else None
                outer_blip = extLst.getparent() if extLst is not None else None
                if (ext is not None and ext.tag == f"{{{ns['a']}}}ext"
                        and extLst is not None and extLst.tag == f"{{{ns['a']}}}extLst"
                        and outer_blip is not None and outer_blip.tag == f"{{{ns['a']}}}blip"
                        and not outer_blip.attrib.get(f"{{{ns['r']}}}embed")):
                    outer_blip.attrib[f"{{{ns['r']}}}embed"] = new_rid
                    outer_blip.remove(extLst)
                    promoted = True
            if not promoted:
                # Replace the node with a fresh <a:blip> that embeds our new PNG rid
                new_blip = ET.Element(f"{{{ns['a']}}}blip")
                new_blip.attrib[f"{{{ns['r']}}}embed"] = new_rid
                parent = node.getparent()
                parent.replace(node, new_blip)
            changed_slide = True
            
        # Case 3: standalone raster images. Swap each for a 9x9 marker PNG so
        # Office's PDF renderer can't recompress it; the original raster is
        # stashed in uzo._saved_rasters_dir and recorded in svg_color_map by
        # its saved path. pdf.py inlines those bytes back into the final PDF
        # with complete fidelity. Markers we wrote earlier in Cases 1/2 are
        # tracked in png_color_written and skipped here.
        RASTER_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif")
        
        # Refresh map: Cases 1/2 may have appended rels
        rel_id_to_target = {
            rel.attrib["Id"]: unquote(rel.attrib.get("Target", ""))
            for rel in self.rels_root
            if rel.tag.endswith("Relationship")
        }
        
        raster_blips = []
        for elem in self.slide_root.iter():
            if elem.tag != f"{{{ns['a']}}}blip":
                continue
            rid = elem.attrib.get(f"{{{ns['r']}}}embed")
            if not rid:
                continue
            target = rel_id_to_target.get(rid, "")
            if not target.lower().endswith(RASTER_EXTS):
                continue
            raster_abs = os.path.normpath(os.path.join(source_part_dir, target))
            if not os.path.isfile(raster_abs):
                continue
            if raster_abs in self.uzo.png_color_written:
                continue  # marker we wrote ourselves in Case 1/2
            raster_blips.append((elem, raster_abs))
        
        # Within one slide, multiple blips referencing the same (file, crop)
        # share a single freshly-minted marker PNG/rel.
        color_to_rid_case3 = {}
        
        def _mint_marker_png_and_rel(rgb):
            """Inline mirror of the Case 1 conflict branch / Case 2 mint dance."""
            new_png_path = None
            while new_png_path is None or os.path.exists(new_png_path):
                self.uzo.nfiles += 1
                new_png_name = f"image{self.uzo.nfiles}.png"
                new_png_path = os.path.join(self.uzo.media_dir, new_png_name)
            new_rel_target = f"{self.uzo.media_loc}/{new_png_name}"
            imagenum = len(self.rels_root) + 1
            while f"rId{imagenum}" in rel_id_to_target:
                imagenum += 1
            new_rid = f"rId{imagenum}"
            rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            ET.SubElement(
                self.rels_root,
                f"{{{rels_ns}}}Relationship",
                {
                    "Id": new_rid,
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                    "Target": new_rel_target,
                },
            )
            rel_id_to_target[new_rid] = new_rel_target
            self.uzo._write_solid_png_9x9(rgb, new_png_path)
            return new_rid, new_png_path
        
        for blip, raster_abs in raster_blips:
            crop, srcrect_elem = _find_srcrect_crop(blip)
            saved_path = self.uzo._save_raster_copy(raster_abs)
        
            existing = self.uzo._lookup_color_for_svg(saved_path, crop)
            if existing:
                color_hex = existing
                rgb = self.uzo._hex_to_rgb(existing)
            else:
                color_hex, rgb = self.uzo._alloc_next_color()
                self.uzo._register_svg_color(saved_path, color_hex, crop)
        
            if raster_abs.lower().endswith(".png"):
                # Overwrite in place (PNG → PNG). Multi-rId conflict handled
                # the same way Case 1 does it.
                prev_color = self.uzo.png_color_written.get(raster_abs)
                if prev_color is not None and prev_color != color_hex:
                    new_rid, new_png_path = _mint_marker_png_and_rel(rgb)
                    self.uzo.png_color_written[new_png_path] = color_hex
                    blip.attrib[f"{{{ns['r']}}}embed"] = new_rid
                    changed_rels = True
                else:
                    self.uzo._write_solid_png_9x9(rgb, raster_abs)
                    self.uzo.png_color_written[raster_abs] = color_hex
            else:
                # Non-PNG raster: extension/content-type would mismatch if we
                # overwrote bytes in place, so mint a fresh imageN.png and rewire
                # the blip. The original file becomes unreferenced and is removed
                # by cleanup_unused_rels_and_media.
                new_rid = color_to_rid_case3.get(color_hex)
                if new_rid is None:
                    new_rid, new_png_path = _mint_marker_png_and_rel(rgb)
                    self.uzo.png_color_written[new_png_path] = color_hex
                    color_to_rid_case3[color_hex] = new_rid
                blip.attrib[f"{{{ns['r']}}}embed"] = new_rid
                changed_rels = True
                
            # Drop every <a:blip> child. After substitution the blip points at
            # a flat 9x9 PNG marker; any child element would either distort the
            # marker's color so pdf.py can't find it back, or route Office at
            # an entirely different source layer:
            #   <a:duotone>, <a:lum>, <a:tint>, <a:hsl>, <a:clrChange>,
            #   <a:clrRepl>, <a:grayscl>, <a:biLevel>, <a:fillOverlay>,
            #   <a:blur>  -- mangle marker RGB (e.g. a duotone with a black
            #               end maps marker #000004 to #000000 in the PDF, so
            #               _try_get_uniform_rgb_hex_from_ximage reads black
            #               and color_to_svg has no entry for it)
            #   <a:alpha*>  -- same problem on the alpha channel
            #   <a:extLst>  -- can host <a14:imgLayer> pointing at a JPEG-XR
            #                  alternative-content source that Office uses
            #                  *instead of* our PNG, so the marker is never
            #                  drawn into the PDF at all
            # The only blip child Cases 1/2 care about is <asvg:svgBlip>
            # inside an extLst, and they always strip that extLst before
            # Case 3 sees the blip, so this is safe to do unconditionally.
            # Side effect: any color filter the user authored on this picture
            # is lost. That's the price of byte-perfect raster fidelity --
            # the raw bytes win over the filter's visual effect.
            for child in list(blip):
                blip.remove(child)
        
            self.uzo.ensure_image_in_content_types("dummy.png")
            if srcrect_elem is not None:
                parent_fill = srcrect_elem.getparent()
                if parent_fill is not None:
                    parent_fill.remove(srcrect_elem)
            changed_slide = True

        if changed_slide:
            self.slide_tree.write(
                self.slide_path, xml_declaration=True, encoding="UTF-8", method="xml"
            )
        if changed_rels:
            self.rels_tree.write(
                self.rels_path, xml_declaration=True, encoding="UTF-8", method="xml"
            )
            # Ensure PNG content type is declared
            self.uzo.ensure_image_in_content_types("placeholder.png")


def get_images_onenote(target_file, outputdir):
    """Extracts OneNote files to the output directory"""
    pkg_dir = os.path.join(dh.si_dir, "packages")
    if pkg_dir not in sys.path:
        sys.path.append(pkg_dir)
    from onenoteextractor.one import OneNoteExtractor
    from pathlib import Path

    with Path(target_file).open("rb") as infile:
        data = infile.read()
    document = OneNoteExtractor(data=data, password=None)
    import struct

    def is_emf(file_data: bytes) -> bool:
        """Check if the file_data represents an EMF file by inspecting the header."""
        if len(file_data) < 88:
            return False  # EMF header should be at least 88 bytes
        # Unpack the first 4 bytes to get the Record Type
        (record_type,) = struct.unpack("<I", file_data[0:4])
        # Unpack bytes 40 to 44 to get the Signature
        (signature,) = struct.unpack("<I", file_data[40:44])
        # EMF specific values
        EMR_HEADER = 0x00000001
        EMF_SIGNATURE = 0x464D4520  # ' EMF' in ASCII (note the leading space)

        return record_type == EMR_HEADER and signature == EMF_SIGNATURE

    def is_wmf(file_data: bytes) -> bool:
        """Check if the file_data represents a WMF file by inspecting the header."""
        if len(file_data) < 4:
            return False  # WMF header should be at least 4 bytes
        # Check for Placeable WMF magic number
        if file_data.startswith(b"\xd7\xcd\xc6\x9a"):
            return True
        # For non-placeable WMF files, check the Type and Header Size
        if len(file_data) < 18:  # Minimum WMF header size
            return False
        try:
            type_, header_size, version = struct.unpack("<HHH", file_data[0:6])
            if type_ in (1, 2) and header_size == 9 and version in (0x0300, 0x0100):
                return True
        except struct.error:
            pass
        return False

    def is_png(file_data: bytes) -> bool:
        """Check if the file_data represents a PNG file by inspecting the header."""
        return file_data.startswith(b"\x89PNG\r\n\x1a\n")

    def is_jpeg(file_data: bytes) -> bool:
        """Check if the file_data represents a JPEG file by inspecting the header."""
        return file_data.startswith(b"\xff\xd8\xff")

    def is_gif(file_data: bytes) -> bool:
        """Check if the file_data represents a GIF file by inspecting the header."""
        return file_data.startswith(b"GIF87a") or file_data.startswith(b"GIF89a")

    def is_tiff(file_data: bytes) -> bool:
        """Check if the file_data represents a TIFF file by inspecting the header."""
        return file_data.startswith(b"II*\x00") or file_data.startswith(b"MM\x00*")

    def is_bmp(file_data: bytes) -> bool:
        """Check if the file_data represents a BMP file by inspecting the header."""
        return file_data.startswith(b"BM")

    def is_pdf(file_data: bytes) -> bool:
        """Check if the file_data represents a PDF file by inspecting the header."""
        return file_data.startswith(b"%PDF")

    for index, file_data in enumerate(document.extract_files()):
        bn = Path(target_file).stem  # Use stem to get filename without extension
        if is_emf(file_data):
            extension = ".emf"
        elif is_wmf(file_data):
            extension = ".wmf"
        elif is_png(file_data):
            extension = ".png"
        elif is_jpeg(file_data):
            extension = ".jpg"
        elif is_gif(file_data):
            extension = ".gif"
        elif is_tiff(file_data):
            extension = ".tif"
        elif is_bmp(file_data):
            extension = ".bmp"
        elif is_pdf(file_data):
            extension = ".pdf"
        else:
            extension = ".bin"  # Default extension for unknown types
        target_path = Path(outputdir) / f"{bn}_{index}{extension}"
        print(f"Writing extracted file to: {target_path}")
        with target_path.open("wb") as outf:
            outf.write(file_data)