#
# Copyright 2011-2022 Martin Owens <doctormo@geek-2.com>
#
# This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>
#
"""
Provides wrappers for pixmap access.
"""

import os
import logging

from typing import List
from collections.abc import Iterable
from gi.repository import Gtk, GLib, GdkPixbuf

ICON_THEME = Gtk.IconTheme.get_default()
BILINEAR = GdkPixbuf.InterpType.BILINEAR
HYPER = GdkPixbuf.InterpType.HYPER

SIZE_ASPECT = 0
SIZE_ASPECT_GROW = 1
SIZE_ASPECT_CROP = 2
SIZE_STRETCH = 3


class PixmapLoadError(ValueError):
    """Failed to load a pixmap"""


class PixmapFilter:  # pylint: disable=too-few-public-methods
    """Base class for filtering the pixmaps in a manager's output.

    required - List of values required for this filter.

    Use:

    class Foo(PixmapManager):
        filters = [ PixmapFilterFoo ]

    """

    required: List[str] = []
    optional: List[str] = []

    def __init__(self, **kwargs):
        self.enabled = True
        for key in self.required:
            if key not in kwargs:
                self.enabled = False
            else:
                setattr(self, key, kwargs[key])

        for key in self.optional:
            if key in kwargs:
                setattr(self, key, kwargs[key])

    def filter(self, img, **kwargs):
        """Run filter, replace this methodwith your own"""
        raise NotImplementedError(
            "Please add 'filter' method to your PixmapFilter class %s."
            % type(self).__name__
        )

    @staticmethod
    def to_size(dat):
        """Tries to calculate a size that will work for the data"""
        if isinstance(dat, (int, float)):
            return (dat, dat)
        if isinstance(dat, Iterable) and len(dat) >= 2:
            return (dat[0], dat[1])
        return None


class OverlayFilter(PixmapFilter):
    """Adds an overlay to output images, overlay can be any name that
    the owning pixmap manager can find.

    overlay  : Name of overlay image
    position : Location of the image:
      0      - Full size (1 to 1 overlay, default)
      (x,y)  - Percentage from one end to the other position 0-1
    alpha    : Blending alpha, 0 - 255

    """

    optional = ["position", "overlay", "alpha"]

    def __init__(self, *args, **kwargs):
        self.position = (0, 0)
        self.overlay = None
        self.alpha = 255
        super().__init__(*args, **kwargs)
        self.pad_x, self.pad_y = self.to_size(self.position)

    def get_overlay(self, **kwargs):
        if "manager" not in kwargs:
            raise ValueError("PixmapManager must be provided when adding an overlay.")
        return kwargs["manager"].get(
            kwargs.get("overlay", None) or self.overlay, no_overlay=True
        )

    def filter(self, img, no_overlay=False, **kwargs):
        # Recursion protection
        if no_overlay:
            return img

        overlay = self.get_overlay(**kwargs)
        if overlay:
            img = img.copy()

            (x, y, width, height) = self.set_position(overlay, img)
            overlay.composite(
                img, x, y, width, height, x, y, 1, 1, BILINEAR, self.alpha
            )
        return img

    def set_position(self, overlay, img):
        """Sets the position of img on the given width and height"""
        img_w, img_h = img.get_width(), img.get_height()
        ovl_w, ovl_h = overlay.get_width(), overlay.get_height()
        return (
            max([0, (img_w - ovl_w) * self.pad_x]),
            max([0, (img_h - ovl_h) * self.pad_y]),
            min([ovl_w, img_w]),
            min([ovl_h, img_h]),
        )


class SizeFilter(PixmapFilter):
    """Resizes images to a certain size:

    resize_mode - Way in which the size is calculated
      0 - Best Aspect, don't grow
      1 - Best Aspect, grow
      2 - Cropped Aspect
      3 - Stretch
    """

    required = ["size"]
    optional = ["resize_mode"]

    def __init__(self, *args, **kwargs):
        self.size = None
        self.resize_mode = SIZE_ASPECT
        super().__init__(*args, **kwargs)
        self.img_w, self.img_h = self.to_size(self.size) or (0, 0)

    def aspect(self, img_w, img_h):
        """Get the aspect ratio of the image resized"""
        if self.resize_mode == SIZE_STRETCH:
            return (self.img_w, self.img_h)

        if (
            self.resize_mode == SIZE_ASPECT
            and img_w < self.img_w
            and img_h < self.img_h
        ):
            return (img_w, img_h)
        (pcw, pch) = (self.img_w / img_w, self.img_h / img_h)
        factor = (
            max(pcw, pch) if self.resize_mode == SIZE_ASPECT_CROP else min(pcw, pch)
        )
        return (int(img_w * factor), int(img_h * factor))

    def filter(self, img, **kwargs):
        if self.size is not None:
            (width, height) = self.aspect(img.get_width(), img.get_height())
            return img.scale_simple(width, height, HYPER)
        return img


class PadFilter(SizeFilter):
    """Add padding to the image to make it a standard size"""

    optional = ["padding"]

    def __init__(self, *args, **kwargs):
        self.size = None
        self.padding = 0.5
        super().__init__(*args, **kwargs)
        self.pad_x, self.pad_y = self.to_size(self.padding)

    def filter(self, img, **kwargs):
        (width, height) = (img.get_width(), img.get_height())
        if width < self.img_w or height < self.img_h:
            target = GdkPixbuf.Pixbuf.new(
                img.get_colorspace(),
                True,
                img.get_bits_per_sample(),
                max([width, self.img_w]),
                max([height, self.img_h]),
            )
            target.fill(0x0)  # Transparent black

            x = (target.get_width() - width) * self.pad_x
            y = (target.get_height() - height) * self.pad_y

            img.composite(target, x, y, width, height, x, y, 1, 1, BILINEAR, 255)
            return target
        return img


class PixmapManager:
    """Manage a set of cached pixmaps, returns the default image
    if it can't find one or the missing image if that's available."""

    missing_image = "image-missing"
    default_image = "application-default-icon"
    icon_theme = ICON_THEME
    theme_size = 32
    filters: List[type] = []
    pixmap_dir = None

    def __init__(self, location="", **kwargs):
        self.location = location
        if self.pixmap_dir and not os.path.isabs(location):
            self.location = os.path.join(self.pixmap_dir, location)

        self.loader_size = PixmapFilter.to_size(kwargs.pop("load_size", None))

        # Add any instance specified filters first
        self._filters = []
        for item in kwargs.get("filters", []) + self.filters:
            if isinstance(item, PixmapFilter):
                self._filters.append(item)
            elif callable(item):
                # Now add any class specified filters with optional kwargs
                self._filters.append(item(**kwargs))

        self.cache = {}
        self.get_pixmap(self.default_image)

    def get(self, *args, **kwargs):
        """Get a pixmap of any kind"""
        return self.get_pixmap(*args, **kwargs)

    def get_missing_image(self):
        """Get a missing image when other images aren't found"""
        return self.get(self.missing_image)

    @staticmethod
    def data_is_file(data):
        """Test the file to see if it's a filename or not"""
        return isinstance(data, str) and "<svg" not in data

    def get_pixmap(self, data, **kwargs):
        """
        There are three types of images this might return.

         1. A named gtk-image such as "gtk-stop"
         2. A file on the disk such as "/tmp/a.png"
         3. Data as either svg or binary png

        All pixmaps are cached for multiple use.
        """
        if "manager" not in kwargs:
            kwargs["manager"] = self

        if not data:
            if not self.default_image:
                return None
            data = self.default_image

        key = data[-30:]  # bytes or string
        if not key in self.cache:
            # load the image from data or a filename/theme icon
            img = None
            try:
                if self.data_is_file(data):
                    img = self.load_from_name(data)
                else:
                    img = self.load_from_data(data)
            except PixmapLoadError as err:
                logging.warning(str(err))
                return self.get_missing_image()

            if img is not None:
                self.cache[key] = self.apply_filters(img, **kwargs)

        return self.cache[key]

    def apply_filters(self, img, **kwargs):
        """Apply all the filters to the given image"""
        for lens in self._filters:
            if lens.enabled:
                img = lens.filter(img, **kwargs)
        return img

    def load_from_data(self, data):
        """Load in memory picture file (jpeg etc)"""
        # This doesn't work yet, returns None *shrug*
        loader = GdkPixbuf.PixbufLoader()
        if self.loader_size:
            loader.set_size(*self.loader_size)
        try:
            if isinstance(data, str):
                data = data.encode("utf-8")
            loader.write(data)
            loader.close()
        except GLib.GError as err:
            raise PixmapLoadError(f"Faled to load pixbuf from data: {err}")
        return loader.get_pixbuf()

    def load_from_name(self, name):
        """Load a pixbuf from a name, filename or theme icon name"""
        pixmap_path = self.pixmap_path(name)
        if os.path.exists(pixmap_path):
            try:
                return GdkPixbuf.Pixbuf.new_from_file(pixmap_path)
            except RuntimeError as msg:
                raise PixmapLoadError(f"Faild to load pixmap '{pixmap_path}', {msg}")
        elif (
            self.icon_theme and "/" not in name and "." not in name and "<" not in name
        ):
            return self.theme_pixmap(name, size=self.theme_size)
        raise PixmapLoadError(f"Failed to find pixmap '{name}' in {self.location}")

    def theme_pixmap(self, name, size=32):
        """Internal user: get image from gnome theme"""
        size = size or 32
        if not self.icon_theme.has_icon(name):
            name = "image-missing"
        return self.icon_theme.load_icon(name, size, 0)

    def pixmap_path(self, name):
        """Returns the pixmap path based on stored location"""
        for filename in (
            name,
            os.path.join(self.location, f"{name}.svg"),
            os.path.join(self.location, f"{name}.png"),
        ):
            if os.path.exists(filename) and os.path.isfile(filename):
                return name
        return os.path.join(self.location, name)
