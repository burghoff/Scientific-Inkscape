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
import inkex
from inkex import Image

try:
    from base64 import decodebytes
except ImportError:
    from base64 import decodestring as decodebytes

def mime_to_ext(mime):
    """Return an extension based on the mime type"""
    # Most extensions are automatic (i.e. extension is same as minor part of mime type)
    part = mime.split('/', 1)[1].split('+')[0]
    return '.' + {
        # These are the non-matching ones.
        'svg+xml' : '.svg',
        'jpeg'    : '.jpg',
        'icon'    : '.ico',
    }.get(part, part)

def extract_image(node,save_to):
    """Extract the node as if it were an image."""
    xlink = node.get('xlink:href')
    if not xlink.startswith('data:'):
        return # Not embedded image data

    # This call will raise AbortExtension if the document wasn't saved
    # and the user is trying to extract them to a relative directory.
    # save_to = self.absolute_href(self.options.filepath, default=None)
    # Make the target directory if it doesn't exist yet.
    if not os.path.isdir(save_to):
        os.makedirs(save_to)

    try:
        data = xlink[5:]
        (mimetype, data) = data.split(';', 1)
        (base, data) = data.split(',', 1)
    except ValueError:
        inkex.errormsg("Invalid image format found")
        return

    if base != 'base64':
        inkex.errormsg("Can't decode encoding: {}".format(base))
        return

    file_ext = mime_to_ext(mimetype)

    pathwext = os.path.join(save_to, node.get("id") + file_ext)
    if os.path.isfile(pathwext):
        inkex.errormsg("Can't extract image, filename already used: {}".format(pathwext))
        return

    # self.msg('Image extracted to: {}'.format(pathwext))

    with open(pathwext, 'wb') as fhl:
        fhl.write(decodebytes(data.encode('utf-8')))

    # absolute for making in-mem cycles work
    node.set('xlink:href', os.path.realpath(pathwext))


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

def embed_image(node,svg_path):
    """Embed the data of the selected Image Tag element"""
    xlink = node.get('xlink:href')
    if (xlink is not None and xlink[:5] == 'data:'):
        # No need, data already embedded
        return
    if xlink is None:
        inkex.errormsg(_('Attribute "xlink:href" not set on node {}.'.format(node.get_id())))
        return

    url = urlparse.urlparse(xlink)
    href = urllib.url2pathname(url.path)

    # Primary location always the filename itself, we allow this
    # call to search the user's home folder too.
    path = absolute_href(href or '',svg_path)

    # Backup directory where we can find the image
    if not os.path.isfile(path):
        path = node.get('sodipodi:absref', path)

    if not os.path.isfile(path):
        inkex.errormsg(_('File not found "{}". Unable to embed image.').format(path))
        return

    with open(path, "rb") as handle:
        # Don't read the whole file to check the header
        file_type = get_type(path, handle.read(10))
        handle.seek(0)

        if file_type:
            # Future: Change encodestring to encodebytes when python3 only
            node.set('xlink:href', 'data:{};base64,{}'.format(
                file_type, encodebytes(handle.read()).decode('ascii')))
            node.pop('sodipodi:absref')
        else:
            inkex.errormsg(_("%s is not of type image/png, image/jpeg, "\
                "image/bmp, image/gif, image/tiff, or image/x-icon") % path)
                
def embed_external_image(node,path):
    """Embed the data of the selected Image Tag element"""
    xlink = node.get('xlink:href')

    url = urlparse.urlparse(xlink)
    href = urllib.url2pathname(url.path)

    with open(path, "rb") as handle:
        # Don't read the whole file to check the header
        file_type = get_type(path, handle.read(10))
        handle.seek(0)

        if file_type:
            # Future: Change encodestring to encodebytes when python3 only
            node.set('xlink:href', 'data:{};base64,{}'.format(
                file_type, encodebytes(handle.read()).decode('ascii')))
            node.pop('sodipodi:absref')
        else:
            inkex.errormsg(_("%s is not of type image/png, image/jpeg, "\
                "image/bmp, image/gif, image/tiff, or image/x-icon") % path)

# Gets the type of an image element
def get_image_type(node,svg_path):
    xlink = node.get('xlink:href')
    
    if not xlink.startswith('data:'):
        # Linked image
        xlink = node.get('xlink:href')
        if (xlink is not None and xlink[:5] == 'data:'):
            # No need, data already embedded
            return None
        if xlink is None:
            print(_('Attribute "xlink:href" not set on node {}.'.format(node.get_id())))
            return None

        url = urlparse.urlparse(xlink)
        href = urllib.url2pathname(url.path)

        # Primary location always the filename itself, we allow this
        # call to search the user's home folder too.
        path = absolute_href(href or '',svg_path)

        # Backup directory where we can find the image
        if not os.path.isfile(path):
            path = node.get('sodipodi:absref', path)

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
            (mimetype, data) = data.split(';', 1)
            (base, data) = data.split(',', 1)
        except ValueError:
            print("Invalid image format found")
            return None
    
        if base != 'base64':
            print("Can't decode encoding: {}".format(base))
            return None
        return mimetype



def get_type(path, header):
    """Basic magic header checker, returns mime type"""
    for head, mime in (
            (b'\x89PNG', 'image/png'),
            (b'\xff\xd8', 'image/jpeg'),
            (b'BM', 'image/bmp'),
            (b'GIF87a', 'image/gif'),
            (b'GIF89a', 'image/gif'),
            (b'MM\x00\x2a', 'image/tiff'),
            (b'II\x2a\x00', 'image/tiff'),
        ):
        if header.startswith(head):
            return mime

    # ico files lack any magic... therefore we check the filename instead
    for ext, mime in (
            # official IANA registered MIME is 'image/vnd.microsoft.icon' tho
            ('.ico', 'image/x-icon'),
            ('.svg', 'image/svg+xml'),
        ):
        if path.endswith(ext):
            return mime
    return None

# if __name__ == '__main__':
#     EmbedImage().run()

def absolute_href(filename, svg_path, default="~/"):
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
        filename = os.path.join(svg_path, filename)
    return os.path.realpath(os.path.expanduser(filename))

# Stuff by David Burghoff
try:
    from PIL import Image as Image2
    hasPIL = True;
except:
    hasPIL = False;
    
# def remove_alpha(imin):
#     background = Image2.new('RGBA', imin.size, (255,255,255))
#     alpha_composite = Image2.alpha_composite(background, imin)
#     alpha_composite_3 = alpha_composite.convert('RGB')
#     return alpha_composite_3

def remove_alpha(imin,background):
    # background = Image2.new('RGBA', imin.size, (255,255,255))
    alpha_composite = Image2.alpha_composite(background, imin)
    alpha_composite_3 = alpha_composite.convert('RGB')
    return alpha_composite_3

def to_jpeg(imin,background,imout):
    with Image2.open(imin) as im:
        with Image2.open(background) as imb:
            # Composite to remove transparent regions
            compim = remove_alpha(im,imb); 
            # Crop to non-transparent region only
            bbox = im.getbbox(); #left,upper,right,lower (left & upper pixel is non-zero corner, right-1 & lower-1 is non-zero corner)
            if bbox is not None:
                compim = compim.crop(bbox);
                bbox = [bbox[0]/im.size[0],bbox[1]/im.size[1],bbox[2]/im.size[0],bbox[3]/im.size[1]]; # normalize to original size
            compim.save(imout);
            return imout, bbox
        
def crop_image(imin):
    with Image2.open(imin) as im:
        bbox = im.getbbox(); #left,upper,right,lower (left & upper pixel is non-zero corner, right-1 & lower-1 is non-zero corner)
        if bbox is not None:
            cropim = im.crop(bbox);
            bbox = [bbox[0]/im.size[0],bbox[1]/im.size[1],bbox[2]/im.size[0],bbox[3]/im.size[1]]; # normalized to original size
            cropim.save(imin);
        return imin, bbox