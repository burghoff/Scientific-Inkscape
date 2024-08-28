# Stuff copied from image_extract and image_embed
#!/usr/bin/env python
# coding=utf-8
#
# Copyright (C) 2005,2007 Aaron Spike, aaron@ekips.org
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
Extract embedded images.
"""

from __future__ import unicode_literals

import os
import dhelpers # noqa
import inkex
from inkex import Image

try:
    from base64 import decodebytes
    from base64 import b64encode
except ImportError:
    from base64 import decodestring as decodebytes
    from base64 import b64encode


def mime_to_ext(mime):
    """Return an extension based on the mime type"""
    # Most extensions are automatic (i.e. extension is same as minor part of mime type)
    part = mime.split("/", 1)[1].split("+")[0]
    return "." + {
        # These are the non-matching ones.
        "svg+xml": ".svg",
        "jpeg": ".jpg",
        "icon": ".ico",
    }.get(part, part)


def extract_image(node, save_to):
    """Extract the node as if it were an image."""
    xlink = node.get("xlink:href")
    if not xlink.startswith("data:"):
        return  # Not embedded image data

    # This call will raise AbortExtension if the document wasn't saved
    # and the user is trying to extract them to a relative directory.
    # save_to = self.absolute_href(self.options.filepath, default=None)
    # Make the target directory if it doesn't exist yet.
    if not os.path.isdir(save_to):
        os.makedirs(save_to)

    try:
        data = xlink[5:]
        (mimetype, data) = data.split(";", 1)
        (base, data) = data.split(",", 1)
    except ValueError:
        inkex.errormsg("Invalid image format found")
        return

    if base != "base64":
        inkex.errormsg("Can't decode encoding: {}".format(base))
        return

    file_ext = mime_to_ext(mimetype)

    pathwext = os.path.join(save_to, node.get("id") + file_ext)
    if os.path.isfile(pathwext):
        inkex.errormsg(
            "Can't extract image, filename already used: {}".format(pathwext)
        )
        return

    # self.msg('Image extracted to: {}'.format(pathwext))

    with open(pathwext, "wb") as fhl:
        fhl.write(decodebytes(data.encode("utf-8")))

    # absolute for making in-mem cycles work
    node.set("xlink:href", os.path.realpath(pathwext))


"""
Embed images so they are base64 encoded data inside the svg.
"""

from inkex.localization import inkex_gettext as _

try:
    import urllib.request as urllib
    import urllib.parse as urlparse
    from base64 import encodebytes
except ImportError:
    # python2 compatibility, remove when python3 only.
    import urllib
    import urlparse
    from base64 import encodestring as encodebytes


def embed_image(node, svg_dir):
    """Embed the data of the selected Image Tag element"""
    xlink = node.get("xlink:href")
    if xlink is not None and xlink[:5] == "data:":
        # No need, data already embedded
        return
    if xlink is None:
        inkex.errormsg(
            _('Attribute "xlink:href" not set on node {}.'.format(node.get_id()))
        )
        return

    url = urlparse.urlparse(xlink)
    href = urllib.url2pathname(url.path)

    # Primary location always the filename itself, we allow this
    # call to search the user's home folder too.
    path = absolute_href2(href or "", svg_dir)

    # Backup directory where we can find the image
    if not os.path.isfile(path):
        path = node.get("sodipodi:absref", path)

    if not os.path.isfile(path):
        inkex.errormsg(_('File not found "{}". Unable to embed image.').format(path))
        return

    with open(path, "rb") as handle:
        # Don't read the whole file to check the header
        file_type = get_type(path, handle.read(10))
        handle.seek(0)

        if file_type:
            # Future: Change encodestring to encodebytes when python3 only
            node.set(
                "xlink:href",
                "data:{};base64,{}".format(
                    file_type, encodebytes(handle.read()).decode("ascii")
                ),
            )
            node.pop("sodipodi:absref")
        else:
            inkex.errormsg(
                _(
                    "%s is not of type image/png, image/jpeg, "
                    "image/bmp, image/gif, image/tiff, or image/x-icon"
                )
                % path
            )


def embed_external_image(el, filename):
    """Embed the data of the selected Image Tag element"""
    if filename is not None:
        with open(filename, "rb") as handle:
            # Don't read the whole file to check the header
            file_type = get_type(filename, handle.read(10))
            handle.seek(0)

            if file_type:
                # Future: Change encodestring to encodebytes when python3 only
                el.set(
                    "xlink:href",
                    "data:{};base64,{}".format(
                        file_type, encodebytes(handle.read()).decode("ascii")
                    ),
                )
                el.pop("sodipodi:absref")
            else:
                inkex.errormsg(
                    _(
                        "%s is not of type image/png, image/jpeg, "
                        "image/bmp, image/gif, image/tiff, or image/x-icon"
                    )
                    % filename
                )


# Check if image is linked or embedded. If linked, check if path is valid
def check_linked(node, svg_dir):
    """Embed the data of the selected Image Tag element"""
    xlink = node.get("xlink:href")
    if xlink is not None and xlink[:5] == "data:":
        return False, None
    url = urlparse.urlparse(xlink)
    href = urllib.url2pathname(url.path)
    path = absolute_href2(href or "", svg_dir)
    if not os.path.isfile(path):
        path = node.get("sodipodi:absref", path)
    fileexists = os.path.isfile(path)
    if not (fileexists):
        return True, None
    else:
        return True, path


# Gets the type of an image element
def get_image_type(node, svg_dir):
    xlink = node.get("xlink:href")

    if not xlink.startswith("data:"):
        # Linked image
        xlink = node.get("xlink:href")
        if xlink is not None and xlink[:5] == "data:":
            # No need, data already embedded
            return None
        if xlink is None:
            print(_('Attribute "xlink:href" not set on node {}.'.format(node.get_id())))
            return None

        url = urlparse.urlparse(xlink)
        href = urllib.url2pathname(url.path)

        # Primary location always the filename itself, we allow this
        # call to search the user's home folder too.
        path = absolute_href2(href or "", svg_dir)

        # Backup directory where we can find the image
        if not os.path.isfile(path):
            path = node.get("sodipodi:absref", path)

        if not os.path.isfile(path):
            print(_('File not found "{}". Unable to embed image.').format(path))
            return None

        with open(path, "rb") as handle:
            # Don't read the whole file to check the header
            file_type = get_type(path, handle.read(10))
            return file_type
    else:
        try:
            data = xlink[5:]
            (mimetype, data) = data.split(";", 1)
            (base, data) = data.split(",", 1)
        except ValueError:
            print("Invalid image format found")
            return None

        if base != "base64":
            print("Can't decode encoding: {}".format(base))
            return None
        return mimetype


def get_type(path, header):
    """Basic magic header checker, returns mime type"""
    for head, mime in (
        (b"\x89PNG", "image/png"),
        (b"\xff\xd8", "image/jpeg"),
        (b"BM", "image/bmp"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"MM\x00\x2a", "image/tiff"),
        (b"II\x2a\x00", "image/tiff"),
    ):
        if header.startswith(head):
            return mime

    # ico files lack any magic... therefore we check the filename instead
    for ext, mime in (
        # official IANA registered MIME is 'image/vnd.microsoft.icon' tho
        (".ico", "image/x-icon"),
        (".svg", "image/svg+xml"),
    ):
        if path.endswith(ext):
            return mime
    return None


# if __name__ == '__main__':
#     EmbedImage().run()


# Modification to the built-in absolute_href function that doesn't require an
# extension class
def absolute_href2(filename, svg_dir, default="~/"):
    """
    Process the filename such that it's turned into an absolute filename
    with the working directory being the directory of the loaded svg.

    User's home folder is also resolved. So '~/a.png` will be `/home/bob/a.png`

    Default is a fallback working directory to use if the svg's filename is not
    available, if you set default to None, then the user will be given errors if
    there's no working directory available from Inkscape.
    """
    filename = os.path.expanduser(filename)
    if not os.path.isabs(filename):
        filename = os.path.expanduser(filename)
    if not os.path.isabs(filename):
        filename = os.path.join(svg_dir, filename)
    return os.path.realpath(os.path.expanduser(filename))


# Stuff by David Burghoff
try:
    from PIL import Image as ImagePIL

    hasPIL = True
except:
    hasPIL = False

# def remove_alpha(imin):
#     background = ImagePIL.new('RGBA', imin.size, (255,255,255))
#     alpha_composite = ImagePIL.alpha_composite(background, imin)
#     alpha_composite_3 = alpha_composite.convert('RGB')
#     return alpha_composite_3


# def remove_alpha(imin, background):
#     # background = ImagePIL.new('RGBA', imin.size, (255,255,255))
#     alpha_composite = ImagePIL.alpha_composite(background, imin)
#     alpha_composite_3 = alpha_composite.convert("RGB")
#     return alpha_composite_3

# Convert and crop transparent image to JPG
# Requires the transparent version (imin) as well as the opaque version (opaqueimin)
# def to_jpeg(imin, opaqueimin, imout):
#     with ImagePIL.open(imin) as im:
#         with ImagePIL.open(opaqueimin) as oim:
#             bbox = im.getbbox()
#             # # Composite to remove transparent regions
#             # compim = remove_alpha(im, imb)

#             # Crop to non-transparent region only
#             # left,upper,right,lower (left & upper pixel is non-zero corner, right-1 & lower-1 is non-zero corner)
#             if bbox is not None:
#                 oim = oim.crop(bbox)
#                 bbox = [
#                     bbox[0] / im.size[0],
#                     bbox[1] / im.size[1],
#                     bbox[2] / im.size[0],
#                     bbox[3] / im.size[1],
#                 ]
#                 # normalize to original size
#             oim.convert('RGB').save(imout)
#             return imout, bbox


def to_jpeg(imin, imout):
    with ImagePIL.open(imin) as im:
        im.convert("RGB").save(imout)


def crop_image(imin):
    with ImagePIL.open(imin) as im:
        bbox = im.getbbox()
        # left,upper,right,lower (left & upper pixel is non-zero corner, right-1 & lower-1 is non-zero corner)
        if bbox is not None:
            cropim = im.crop(bbox)
            bbox = [
                bbox[0] / im.size[0],
                bbox[1] / im.size[1],
                bbox[2] / im.size[0],
                bbox[3] / im.size[1],
            ]
            # normalized to original size
            cropim.save(imin)
        return imin, bbox


# Extract an embedded image
def extract_image_simple(node, save_to_base):
    """Extract the node as if it were an image."""
    xlink = node.get("xlink:href")
    data = xlink[5:]
    try:
        data = xlink[5:]
        (mimetype, data) = data.split(";", 1)
        (base, data) = data.split(",", 1)
    except ValueError:
        return None
    file_ext = mime_to_ext(mimetype)
    pathwext = save_to_base + file_ext
    # inkex.utils.debug(pathwext)
    with open(pathwext, "wb") as fhl:
        fhl.write(decodebytes(data.encode("utf-8")))
    return pathwext


# Get the size of an embedded image
def embedded_size(node):
    xlink = node.get("xlink:href")
    try:
        data = xlink[5:]
        (mimetype, data) = data.split(";", 1)
        (base, data) = data.split(",", 1)
        return len(decodebytes(data.encode("utf-8")))
    except (ValueError, TypeError):
        return None


# Get the data string of an embedded image with the alpha stripped out
# This allows images to be identified after conversion to PDF
def Stripped_Alpha_String(el):
    import tempfile

    tf = tempfile.NamedTemporaryFile().name
    fullpath = extract_image_simple(el, tf)

    with ImagePIL.open(fullpath) as im:
        newfile = strip_ext(fullpath) + ".png"

        return str(im.size)

    #     im.convert('RGB').save(newfile)

    #     with open(newfile, "rb") as handle:
    #         # Don't read the whole file to check the header
    #         file_type = get_type(newfile, handle.read(10))
    #         handle.seek(0)

    #         if file_type:
    #             return "data:{};base64,{}".format(
    #                     file_type, encodebytes(handle.read()).decode("ascii"))
    # return None


def Make_Data_Image(datastr):
    data = [ord(c) for c in datastr]
    # inkex.utils.debug(data)
    import numpy as np

    im = ImagePIL.fromarray(np.array([data], dtype="uint8"))

    import tempfile

    tf = tempfile.NamedTemporaryFile().name
    newfile = tf + ".png"
    im.save(newfile)

    with open(newfile, "rb") as handle:
        # Don't read the whole file to check the header
        file_type = get_type(newfile, handle.read(10))
        handle.seek(0)

        if file_type:
            return "data:{};base64,{}".format(
                file_type, encodebytes(handle.read()).decode("ascii")
            )
    return None


def Read_Data_Image(imstr):
    data = imstr[5:]
    (mimetype, data) = data.split(";", 1)
    (base, data) = data.split(",", 1)
    import io

    im = ImagePIL.open(io.BytesIO(decodebytes(data.encode("utf-8"))))

    import numpy as np

    npa = np.asarray(im)
    if len(npa.shape) == 3:
        data = npa[:, :, 0]
    else:
        data = npa
    return "".join([chr(v) for v in list(data.ravel())])


import io


def str_to_ImagePIL(imstr):
    try:
        data = imstr[5:]
        (mimetype, data) = data.split(";", 1)
        (base, data) = data.split(",", 1)
        im = ImagePIL.open(io.BytesIO(decodebytes(data.encode("utf-8"))))
        return im
    except:
        return None


def ImagePIL_to_str(im):
    try:
        img_byte_arr = io.BytesIO()
        im.save(img_byte_arr, format="png")
        vals = img_byte_arr.getvalue()
        file_type = get_type(None, vals[0:10])
        if file_type:
            return "data:{};base64,{}".format(
                file_type, encodebytes(vals).decode("ascii")
            )
    except:
        return None


# Get just the alpha channel of an image, which can be turned into a mask
# def make_alpha_mask(fin,maskout):
#     from PIL import Image, ImageOps
#     with Image.open(fin) as im:
#         (r,g,b,a)=im.split()
#         # (r,g,b)=Image.new('RGB',im.size,'black').split()
#         # nim = Image.merge('RGBA',(r,g,b,ImageOps.invert(a)))
#         # (r,g,b)=Image.new('RGB',im.size,'black').split()
#         nim = Image.merge('L',(a,))
#         nim.save(maskout)

# # Get just the alpha channel of an image, which can be turned into a mask
# def make_rgb(fin,rgbout):
#     from PIL import Image, ImageOps
#     with Image.open(fin) as im:
#         (r,g,b,a)=im.split()
#         # (r,g,b)=Image.new('RGB',im.size,'black').split()
#         # nim = Image.merge('RGBA',(r,g,b,ImageOps.invert(a)))
#         # (r,g,b)=Image.new('RGB',im.size,'black').split()
#         nim = Image.merge('RGB',(r,g,b))
#         nim.save(rgbout)


# Strips image extensions
def strip_ext(fnin):
    # strip existing extension
    if fnin[-4:].lower() in [".png", ".gif", "jpg", "tif"]:
        fnin = fnin[0:-4]
    if fnin[-5:].lower() in ["jpeg", "tiff"]:
        fnin = fnin[0:-5]
    return fnin


# Extracts embedded images or returns the path of linked ones
def extract_img_file(el, svg_dir, newpath):
    islinked, validpath = check_linked(el, svg_dir)
    if islinked and validpath is not None:
        impath = validpath
        madenew = False
    elif islinked and validpath is None:
        impath = None
        madenew = False
    else:
        # inkex.utils.debug(newpath)
        extract = extract_image_simple(el, strip_ext(newpath))
        if extract is not None:
            impath = extract
            madenew = True
        else:
            impath = None
            madenew = False
    return impath, islinked


# For images with alpha=0 pixels, set the RGB of those pixels based on another
# image. This is usually the same image with a background and with other objects.
# For those pixels, alpha is then set to 1 (out of 255), which prevents the PDF
# renderer from replacing those pixels with black. This avoids the 'gray ring'
# issue that can happen on PDF exports.
def Set_Alpha0_RGB(img, imgref):
    im1 = ImagePIL.open(img).convert("RGBA")
    im2 = ImagePIL.open(imgref).convert("RGBA")
    import numpy as np

    d1 = np.asarray(im1)
    d2 = np.asarray(im2)
    a = d1[:, :, 3]
    nd = np.stack(
        (
            np.where(a == 0, d2[:, :, 0], d1[:, :, 0]),
            np.where(a == 0, d2[:, :, 1], d1[:, :, 1]),
            np.where(a == 0, d2[:, :, 2], d1[:, :, 2]),
            np.where(a == 0, 1 * np.ones_like(a), a),
        ),
        2,
    )
    ImagePIL.fromarray(nd).save(img)
    # inkex.utils.debug(img)
    anyalpha0 = np.where(a == 0, True, False).any()
    return anyalpha0


# Crop a list of images based on the transparency of the first one
# Returns the normalized bounding box, which we need later
def crop_images(ims_in):
    bbox = None
    with ImagePIL.open(ims_in[0]) as ref_im:
        bbox = ref_im.getbbox()
        nsz = ref_im.size

    if bbox is not None:
        # left,upper,right,lower (left & upper pixel is non-zero corner, right-1 & lower-1 is non-zero corner)
        nbbox = [
            bbox[0] / nsz[0],
            bbox[1] / nsz[1],
            bbox[2] / nsz[0],
            bbox[3] / nsz[1],
        ]  # normalize to original size
        for imf in ims_in:
            with ImagePIL.open(imf) as im:
                im.crop(bbox).save(imf)
        return nbbox
    else:
        return None


# Get the absolute locations of all linked images when called by an extension
# Needed because the temp file has a different location from the actual one
def get_linked_locations(slf):
    llocations = dict()
    images = slf.svg.xpath("//svg:image")
    for node in images:
        xlink = node.get("xlink:href")
        if xlink is not None and xlink[:5] != "data:":
            try:
                import urllib.request as urllib
                import urllib.parse as urlparse
            except ImportError:
                # python2 compatibility, remove when python3 only.
                import urllib
                import urlparse

            url = urlparse.urlparse(xlink)
            href = urllib.url2pathname(url.path)

            # Look relative to the *temporary* filename instead of the original filename.
            try:  # v1.2 forward
                path = slf.absolute_href(
                    href or "", cwd=os.path.dirname(slf.options.input_file)
                )
            except:  # pre-v1.2
                # Primary location always the filename itself, we allow this
                # call to search the user's home folder too.
                path = slf.absolute_href(href or "")

            # Backup directory where we can find the image
            if not os.path.isfile(path):
                path = node.get("sodipodi:absref", path)

            if os.path.isfile(path):
                llocations[node.get_id()] = path
            else:
                llocations[node.get_id()] = None
    return llocations


# Get the absolute locations of all linked images when the absolute path is known
def get_linked_locations_file(fin, svg):
    llocations = dict()
    images = svg.xpath("//svg:image")
    for node in images:
        xlink = node.get("xlink:href")
        if xlink is not None and xlink[:5] != "data:":
            try:
                import urllib.request as urllib
                import urllib.parse as urlparse
            except ImportError:
                # python2 compatibility, remove when python3 only.
                import urllib
                import urlparse

            url = urlparse.urlparse(xlink)
            href = urllib.url2pathname(url.path)

            path = absolute_href2(href or "", os.path.dirname(fin))

            # Backup directory where we can find the image
            if not os.path.isfile(path):
                path = node.get("sodipodi:absref", path)

            if os.path.isfile(path):
                llocations[node.get_id()] = path
            else:
                llocations[node.get_id()] = None
    return llocations
