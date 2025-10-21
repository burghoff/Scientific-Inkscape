import sys
import dhelpers as dh
bfn = dh.inkex.inkscape_system_info.binary_location

def overwrite_output(filein, fileout):
    if os.path.exists(fileout):
        os.remove(fileout)
    args = [
        bfn,
        "--export-background", "#ffffff",
        "--export-background-opacity", "0.0",
        "--export-dpi", str(600),
        "--export-filename", fileout,
        filein,
    ]
    dh.subprocess_repeat(args)

import os
import shutil
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
from urllib.parse import unquote
from lxml import etree as ET
import re

def svg_to_png(svg_path, png_path):
    print(f'Exporting {svg_path}')
    overwrite_output(svg_path, png_path)

def normalize_and_copy(source_path, media_dir):
    os.makedirs(media_dir, exist_ok=True)
    basename = os.path.basename(source_path)
    target_path = os.path.join(media_dir, basename)
    if not os.path.exists(target_path):
        shutil.copy2(source_path, target_path)
    return target_path

            
class Unzipped_Office():
    def __init__(self,file,temp_dir=None):
        with ZipFile(file, 'r') as zip_read:
            if temp_dir is None:
                temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_extracted_pptx')
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            zip_read.extractall(temp_dir)
        
        self.temp_dir = temp_dir
        self.type = 'ppt' if os.path.isdir(os.path.join(temp_dir,"ppt")) else 'word'
        self.media_dir = os.path.join(temp_dir, self.type, "media")
        
        if not os.path.exists(self.media_dir):
            self.nfiles = 0
            self.slides = []
            return
        
        self.nfiles = len([f for f in os.listdir(self.media_dir) if os.path.isfile(os.path.join(self.media_dir, f))])
        self.slides = []
        
        if self.type == 'ppt':
            dir_paths = [os.path.join(temp_dir, 'ppt', sd) for sd in ["slides", "slideMasters", "slideLayouts"]]
            self.media_loc = "../media"
        elif self.type == 'word':
            dir_paths = [os.path.join(temp_dir, 'word')]
            self.media_loc = "media"
        
        for dir_path in dir_paths:
            for root_dir, _, files in os.walk(dir_path):
                for file in files:
                    if file.endswith(".xml"):
                        try:
                            self.slides.append(Slide_and_Rels(os.path.join(root_dir,file),self))
                        except NameError:
                            pass
                    
    def embed_linked(self):
        for slide in self.slides:
            slide.embed_linked()
            
    def delete_fallback_png(self):
        for slide in self.slides:
            slide.delete_fallback_png()
            
    def leave_fallback_png(self):
        for slide in self.slides:
            slide.leave_fallback_png()
    
    def ensure_image_in_content_types(self, filename):
        """
        Ensures that the correct image content type for `filename` is present
        in [Content_Types].xml within self.temp_dir.
    
        Supports all common Office image formats (PNG, JPG, JPEG, GIF, BMP,
        TIFF, EMF, WMF, SVG).
        """
        # --- Determine extension and MIME type ---
        ext = os.path.splitext(filename)[1].lower().lstrip('.')
        mime_map = {
            'png':  'image/png',
            'jpg':  'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif':  'image/gif',
            'bmp':  'image/bmp',
            'tif':  'image/tiff',
            'tiff': 'image/tiff',
            'emf':  'image/x-emf',
            'wmf':  'image/x-wmf',
            'svg':  'image/svg+xml',
        }
    
        if ext not in mime_map:
            raise ValueError(f"Unsupported image type: {ext}")
    
        content_type = mime_map[ext]
        content_types_path = os.path.join(self.temp_dir, '[Content_Types].xml')
    
        # --- Parse and check existing entries ---
        tree = ET.parse(content_types_path)
        root = tree.getroot()
        ns = {'ct': 'http://schemas.openxmlformats.org/package/2006/content-types'}
    
        already_defined = any(
            elem.attrib.get('Extension', '').lower() == ext
            for elem in root.findall('ct:Default', ns)
        )
    
        # --- Add entry if missing ---
        if not already_defined:
            new_default = ET.Element(
                '{http://schemas.openxmlformats.org/package/2006/content-types}Default',
                Extension=ext,
                ContentType=content_type
            )
            root.append(new_default)
            tree.write(content_types_path, xml_declaration=True, encoding='UTF-8')
            print(f"Added {ext.upper()} content type ({content_type}) to [Content_Types].xml")

            
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
                    index.setdefault(target.abs_path, []).append((slide_name, target.mode))
        return index

    def rezip(self,output):
        with ZipFile(output, 'w') as zip_write:
            for root, _, files in os.walk(self.temp_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, self.temp_dir).replace(os.sep, '/')

                    with open(abs_path, 'rb') as f:
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
        unrenderable = ['Helvetica Light']
        
        processed = []
        if not os.path.exists(self.media_dir):
            return processed
    
        import inkex
        import dhelpers as dh
        from types import SimpleNamespace
        from autoexporter import get_svg, Exporter, Act
    
        bfn = inkex.inkscape_system_info.binary_location
        for fname in os.listdir(self.media_dir):
            fpath = os.path.join(self.media_dir, fname)
            if not (os.path.isfile(fpath) and fname.lower().endswith('.svg')):
                continue
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
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
                if (ff := d.cspecified_style.get('font-family'))
                and any(bad in ff for bad in unrenderable)
            }
    
            if not bad_ids:
                continue
    
            # Create temporary output path
            tempdir, temphead = dh.shared_temp('aeftf')
            tmpout = os.path.join(tempdir, f"{temphead}_ttop.svg")
    
            # Minimal Exporter context (mimics autoexporter)
            opts = SimpleNamespace(bfn=bfn)
            exp = Exporter(fpath, opts)
            exp.tempdir = tempdir
            exp.stpact = "object-to-path"
            stp_act = Act('stp', list(bad_ids), exp, tmpout)
            exp.split_acts(fnm=fpath, acts=[stp_act], get_bbs=False)
    
            # Replace file if new SVG created
            if os.path.exists(tmpout):
                new_svg = get_svg(tmpout)
                dh.overwrite_svg(new_svg, fpath)
                processed.append(fpath)
    
        return processed





class SlideTarget:
    def __init__(self, target, mode, abs_path):
        self.target = target        # str: the raw target string from the rels
        self.mode = mode            # str: either "embed" or "link"
        self.abs_path = abs_path    # str: resolved absolute path

    def __repr__(self):
        return f"SlideTarget(target={self.target!r}, mode={self.mode!r}, abs_path={self.abs_path!r})"

class Slide_and_Rels():
    def __init__(self,path,uzo):
        self.slide_path = path
        self.uzo = uzo
        self.rels_path = os.path.join(os.path.dirname(self.slide_path), "_rels", os.path.basename(path) + ".rels")
        if not os.path.exists(self.rels_path):
            raise NameError("No rels file")
            
        if uzo.type=='word':
            self.slide_name = 'Document'
        else:
            self.slide_name = re.sub(r'([a-zA-Z]+?)(\d+)\.xml$', lambda m: f"{' '.join(re.findall('[A-Z][a-z]*|[a-z]+', m.group(1))).title()} {int(m.group(2))}", os.path.basename(path))

        self.slide_tree = ET.parse(self.slide_path)
        self.slide_root = self.slide_tree.getroot()
        self.rels_tree = ET.parse(self.rels_path)
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
                if attr.endswith('}embed'):
                    used_ids[elem.attrib[attr]] = 'embed'
                elif attr.endswith('}link'):
                    used_ids[elem.attrib[attr]] = 'link'
    
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
        rel_map = {rel.attrib["Id"]: rel for rel in self.rels_root if rel.tag.endswith("Relationship")}
        existing_ids = set(rel_map.keys())
        changed_rels = False
        changed_slide = False

        new_names = set()
        for rel in list(self.rels_root):
            target_mode = rel.get("TargetMode")
            raw_target = rel.get("Target")
            if target_mode != "External" and not (raw_target or '').startswith("file"):
                continue

            abs_path = unquote(raw_target or '')
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
                new_name = f"image{self.uzo.nfiles+1}{ext}"
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
            if elem.tag.endswith('blip') or elem.tag.endswith('svgBlip'):
                embed_id = elem.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                link_id = elem.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link")
        
                if link_id:
                    if link_id not in existing_ids and embed_id is not None:
                        elem.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link"] = embed_id
                        link_id = embed_id
                    elem.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"] = link_id
                    del elem.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link"]
                    changed_slide = True

        if changed_rels:
            self.rels_tree.write(self.rels_path, xml_declaration=True, encoding='UTF-8', pretty_print=False)
            for nn in new_names:
                self.uzo.ensure_image_in_content_types(nn)
        if changed_slide:
            self.slide_tree.write(self.slide_path, xml_declaration=True, encoding='UTF-8', pretty_print=False)
            
            
            
    def delete_fallback_png(self):
        ns = {
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
            'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
            'asvg': 'http://schemas.microsoft.com/office/drawing/2016/SVG/main'
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

            if (ext is not None and ext.tag == f"{{{ns['a']}}}ext" and
                extLst is not None and extLst.tag == f"{{{ns['a']}}}extLst" and
                blip is not None and blip.tag == f"{{{ns['a']}}}blip"):

                blip.attrib[f"{{{ns['r']}}}embed"] = svgblip.attrib.get(f"{{{ns['r']}}}embed")
                for k in blip:
                    blip.remove(k)                           
                changed_slide = True

        if changed_slide:
            self.slide_tree.write(self.slide_path, xml_declaration=True, encoding='UTF-8', method="xml")
            
            
    def leave_fallback_png(self):
        ns = {
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
            'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
            'asvg': 'http://schemas.microsoft.com/office/drawing/2016/SVG/main'
        }
        
        rel_id_to_target = {
            rel.attrib["Id"]: unquote(rel.attrib["Target"])
            for rel in self.rels_root if rel.tag.endswith("Relationship")
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

        if len(svgblips)+len(blips)==0:
            return

        removed_svgblips = []
        for svgblip in svgblips:
            # SVGs are usually embedded with a backup PNG
            # Find the <a:blip> ancestor
            ext = svgblip.getparent()
            extLst = ext.getparent() if ext is not None else None
            blip = extLst.getparent() if extLst is not None else None

            if (ext is not None and ext.tag == f"{{{ns['a']}}}ext" and
                extLst is not None and extLst.tag == f"{{{ns['a']}}}extLst" and
                blip is not None and blip.tag == f"{{{ns['a']}}}blip"):

                embed_rid = blip.attrib.get(f"{{{ns['r']}}}embed")
                target = rel_id_to_target.get(embed_rid, "").lower()
                if embed_rid and target.endswith(".png"):
                    blip.remove(extLst)
                    changed_slide = True
                    removed_svgblips.append(svgblip)
                else:
                    # Invalid blip ancestor, replace with svgblip
                    blip.getparent().replace(blip, svgblip)
                    changed_slide = True
        all_remaining = {b for b in svgblips + blips if b not in set(removed_svgblips)}

        for blip in all_remaining:
            # If there is no backup PNG, replace bare <asvg:svgBlip> or <a:blip>
            # with new PNG <a:blip>
            svg_rid = blip.attrib.get(f"{{{ns['r']}}}embed")
            if not svg_rid:
                continue

            svg_target = rel_id_to_target.get(svg_rid)
            if not svg_target or not svg_target.lower().endswith(".svg"):
                continue

            source_part_path = self.rels_path.replace('\\_rels\\', '\\').replace('/_rels/', '/').rsplit('.rels', 1)[0]
            svg_path = os.path.normpath(os.path.join(os.path.dirname(source_part_path), svg_target))

            new_png_path = None
            while new_png_path is None or os.path.exists(new_png_path):
                self.uzo.nfiles += 1
                new_png_name = f"image{self.uzo.nfiles}.png"
                new_png_path = os.path.join(self.uzo.media_dir, new_png_name)
            
            new_rel_target = f"{self.uzo.media_loc}/{new_png_name}"
            svg_to_png(svg_path, new_png_path)

            imagenum = len(self.rels_root) + 1
            while f"rId{imagenum}" in rel_id_to_target:
                imagenum +=1
            new_rid = f"rId{imagenum}"
            rel_id_to_target
            new_blip = ET.Element(f"{{{ns['a']}}}blip")
            new_blip.attrib[f"{{{ns['r']}}}embed"] = new_rid
            blip.getparent().replace(blip, new_blip)
            changed_slide = True

            rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            ET.SubElement(self.rels_root, f"{{{rels_ns}}}Relationship", {
                "Id": new_rid,
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                "Target": new_rel_target
            })
            changed_rels = True

        if changed_slide:
            self.slide_tree.write(self.slide_path, xml_declaration=True, encoding='UTF-8', method="xml")
        if changed_rels:
            self.rels_tree.write(self.rels_path, xml_declaration=True, encoding='UTF-8', method="xml")
            self.uzo.ensure_image_in_content_types('foo.png')
            
    def cleanup_unused_rels(self):
        # Collect all embed/link rel IDs used in the slide
        referenced_files = set()
        used_ids_in_slide = set()
        for elem in self.slide_root.iter():
            for attr_name, attr_val in elem.attrib.items():
                if attr_name.endswith('}embed') or attr_name.endswith('}link'):
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
            self.rels_tree.write(self.rels_path, xml_declaration=True, encoding='UTF-8')
        return referenced_files
    
def get_images_onenote(target_file,outputdir):
    ''' Extracts OneNote files to the output directory '''
    pkg_dir = os.path.join(dh.si_dir,'packages')
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
        record_type, = struct.unpack('<I', file_data[0:4])
        # Unpack bytes 40 to 44 to get the Signature
        signature, = struct.unpack('<I', file_data[40:44])
        # EMF specific values
        EMR_HEADER = 0x00000001
        EMF_SIGNATURE = 0x464D4520 # ' EMF' in ASCII (note the leading space)
        
        return record_type == EMR_HEADER and signature == EMF_SIGNATURE
    def is_wmf(file_data: bytes) -> bool:
        """Check if the file_data represents a WMF file by inspecting the header."""
        if len(file_data) < 4:
            return False  # WMF header should be at least 4 bytes
        # Check for Placeable WMF magic number
        if file_data.startswith(b'\xD7\xCD\xC6\x9A'):
            return True
        # For non-placeable WMF files, check the Type and Header Size
        if len(file_data) < 18:  # Minimum WMF header size
            return False
        try:
            type_, header_size, version = struct.unpack('<HHH', file_data[0:6])
            if type_ in (1, 2) and header_size == 9 and version in (0x0300, 0x0100):
                return True
        except struct.error:
            pass
        return False
    def is_png(file_data: bytes) -> bool:
        """Check if the file_data represents a PNG file by inspecting the header."""
        return file_data.startswith(b'\x89PNG\r\n\x1a\n')

    def is_jpeg(file_data: bytes) -> bool:
        """Check if the file_data represents a JPEG file by inspecting the header."""
        return file_data.startswith(b'\xFF\xD8\xFF')
    for index, file_data in enumerate(document.extract_files()):
        bn = Path(target_file).stem  # Use stem to get filename without extension
        if is_emf(file_data):
            extension = '.emf'
        elif is_wmf(file_data):
            extension = '.wmf'
        elif is_png(file_data):
            extension = '.png'
        elif is_jpeg(file_data):
            extension = '.jpg'
        else:
            extension = '.bin'  # Default extension for unknown types
        target_path = Path(outputdir) / f"{bn}_{index}{extension}"
        print(f"Writing extracted file to: {target_path}")
        with target_path.open("wb") as outf:
            outf.write(file_data)