# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Martin Owens <doctormo@gmail.com>
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
A helper module for creating Inkscape effect extensions

This provides the basic generic types of extensions which most writers should
use in their code. See below for the different types.
"""

import os
import re
import sys
import types
from abc import ABC

from .utils import errormsg, Boolean
from .colors import Color, ColorError
from .elements import (
    load_svg,
    BaseElement,
    ShapeElement,
    Group,
    Layer,
    Grid,
    TextElement,
    FlowPara,
    FlowDiv,
    Pattern,
)
from .elements._utils import CloningVat
from .base import (
    InkscapeExtension,
    SvgThroughMixin,
    SvgInputMixin,
    SvgOutputMixin,
    TempDirMixin,
)
from .transforms import Transform
from .elements import LinearGradient, RadialGradient
from .command import write_svg, inkscape, ProgramRunError
from .utils import errormsg
from .localization import inkex_gettext as _

# All the names that get added to the inkex API itself.
__all__ = (
    "EffectExtension",
    "GenerateExtension",
    "InputExtension",
    "OutputExtension",
    "RasterOutputExtension",
    "CallExtension",
    "TemplateExtension",
    "ColorExtension",
    "TextExtension",
)

stdout = sys.stdout


class EffectExtension(SvgThroughMixin, InkscapeExtension, ABC):
    """
    Takes the SVG from Inkscape, modifies the selection or the document
    and returns an SVG to Inkscape.
    """


class OutputExtension(SvgInputMixin, TempDirMixin, InkscapeExtension):
    """
    Takes the SVG from Inkscape and outputs it to something that's not an SVG.

    Used in functions for `Save As`
    """

    def effect(self):
        """Effect isn't needed for a lot of Output extensions"""

    def save(self, stream):
        """But save certainly is, we give a more exact message here"""
        raise NotImplementedError("Output extensions require a save(stream) method!")

    def preprocess(self, types_to_path=None, unlink_clones=True):
        """Preprocess the SVG into an export-friendly document by converting
        certain objects to path beforehand.

        Args:
            types_to_path (List[str], optional): List of element types to convert to
                path. Defaults to all text elements and all non-path shape elements.
            unlink_clones (bool, optional): If clones should be unlinked. Defaults to
                True.

        Returns:
            _type_: _description_
        """
        if types_to_path is None:
            types_to_path = [
                "flowRoot",
                "rect",
                "circle",
                "ellipse",
                "line",
                "polyline",
                "polygon",
                "text",
            ]
        actions = ["unlock-all"]
        if "flowRoot" in types_to_path:
            # Flow roots contain rectangles inside them, so they need to be
            # converted to paths separately from other shapes
            actions += [
                "select-by-element:flowRoot",
                "object-to-path",
                "select-clear",
            ]
            types_to_path.remove("flowRoot")

        # Now convert all non-paths to paths
        actions += ["select-by-element:" + i for i in types_to_path]
        actions += ["object-to-path", "select-clear"]
        # unlink clones
        if unlink_clones:
            actions += ["select-by-element:use", "object-unlink-clones"]
        # save and overwrite
        actions += ["export-overwrite", "export-do"]

        infile = os.path.join(self.tempdir, "input.svg")
        write_svg(self.document, infile)
        try:
            inkscape(infile, actions=";".join(actions))
        except ProgramRunError as err:
            errormsg(_("An error occurred during document preparation"))
            errormsg(err.stderr.decode("utf-8"))

        with open(infile, "r") as stream:
            self.document = load_svg(stream)
            self.svg = self.document.getroot()


class RasterOutputExtension(InkscapeExtension):
    """
    Takes a PNG from Inkscape and outputs it to another raster format.

    .. versionadded:: 1.1
    """

    def __init__(self):
        super().__init__()
        self.img = None

    def load(self, stream):
        from PIL import Image

        # disable the PIL decompression bomb DOS attack check.
        Image.MAX_IMAGE_PIXELS = None

        self.img = Image.open(stream)

    def effect(self):
        """Not needed since image isn't being changed"""

    def save(self, stream):
        """Implement raster image saving here from PIL"""
        raise NotImplementedError("Raster Output extension requires a save method!")


class InputExtension(SvgOutputMixin, InkscapeExtension):
    """
    Takes any type of file as input and outputs SVG which Inkscape can read.

    Used in functions for `Open`
    """

    def effect(self):
        """Effect isn't needed for a lot of Input extensions"""

    def load(self, stream):
        """But load certainly is, we give a more exact message here"""
        raise NotImplementedError("Input extensions require a load(stream) method!")


class CallExtension(TempDirMixin, InputExtension):
    """Call an external program to get the output"""

    input_ext = "svg"
    output_ext = "svg"

    def load(self, stream):
        pass  # Not called (load_raw instead)

    def load_raw(self):
        # Don't call InputExtension.load_raw
        TempDirMixin.load_raw(self)
        input_file = self.options.input_file

        if not isinstance(input_file, str):
            data = input_file.read()
            input_file = os.path.join(self.tempdir, "input." + self.input_ext)
            with open(input_file, "wb") as fhl:
                fhl.write(data)

        output_file = os.path.join(self.tempdir, "output." + self.output_ext)
        document = self.call(input_file, output_file) or output_file
        if isinstance(document, str):
            if not os.path.isfile(document):
                raise IOError(f"Can't find generated document: {document}")

            if self.output_ext == "svg":
                with open(document, "r", encoding="utf-8") as fhl:
                    document = fhl.read()
                if "<" in document:
                    document = load_svg(document.encode("utf-8"))
            else:
                with open(document, "rb") as fhl:
                    document = fhl.read()

        self.document = document

    def call(self, input_file, output_file):
        """Call whatever programs are needed to get the desired result."""
        raise NotImplementedError("Call extensions require a call(in, out) method!")


class GenerateExtension(EffectExtension):
    """
    Does not need any SVG, but instead just outputs an SVG fragment which is
    inserted into Inkscape, centered on the selection.
    """

    container_label = ""
    container_layer = False

    def generate(self):
        """
        Return an SVG fragment to be inserted into the selected layer of the document
        OR yield multiple elements which will be grouped into a container group
        element which will be given an automatic label and transformation.
        """
        raise NotImplementedError("Generate extensions must provide generate()")

    def container_transform(self):
        """
        Generate the transformation for the container group, the default is
        to return the center position of the svg document or view port.
        """
        (pos_x, pos_y) = self.svg.namedview.center
        if pos_x is None:
            pos_x = 0
        if pos_y is None:
            pos_y = 0
        return Transform(translate=(pos_x, pos_y))

    def create_container(self):
        """
        Return the container the generated elements will go into.

        Default is a new layer or current layer depending on the :attr:`container_layer`
        flag.

        .. versionadded:: 1.1
        """
        container = (Layer if self.container_layer else Group).new(self.container_label)
        if self.container_layer:
            self.svg.append(container)
        else:
            container.transform = self.container_transform()
            parent = self.svg.get_current_layer()
            try:
                parent_transform = parent.composed_transform()
            except AttributeError:
                pass
            else:
                container.transform = -parent_transform @ container.transform
            parent.append(container)
        return container

    def effect(self):
        layer = self.svg.get_current_layer()
        fragment = self.generate()
        if isinstance(fragment, types.GeneratorType):
            container = self.create_container()
            for child in fragment:
                if isinstance(child, BaseElement):
                    container.append(child)
        elif isinstance(fragment, BaseElement):
            layer.append(fragment)
        else:
            errormsg("Nothing was generated\n")


class TemplateExtension(EffectExtension):
    """
    Provide a standard way of creating templates.
    """

    size_rex = re.compile(r"([\d.]*)(\w\w)?x([\d.]*)(\w\w)?")
    template_id = "SVGRoot"

    def __init__(self):
        self.svg = None
        super().__init__()
        # Arguments added on after add_arguments so it can be overloaded cleanly.
        self.arg_parser.add_argument("--size", type=self.arg_size(), dest="size")
        self.arg_parser.add_argument("--width", type=int, default=800)
        self.arg_parser.add_argument("--height", type=int, default=600)
        self.arg_parser.add_argument("--orientation", default=None)
        self.arg_parser.add_argument("--unit", default="px")
        self.arg_parser.add_argument("--grid", type=Boolean)
        # self.svg = None

    def get_template(self, **kwargs):
        """Can be over-ridden with custom svg loading here"""
        return self.document

    def arg_size(self, unit="px"):
        """Argument is a string of the form X[unit]xY[unit], default units apply
        when missing"""

        def _inner(value):
            try:
                value = float(value)
                return (value, unit, value, unit)
            except ValueError:
                pass
            match = self.size_rex.match(str(value))
            if match is not None:
                size = match.groups()
                return (
                    float(size[0]),
                    size[1] or unit,
                    float(size[2]),
                    size[3] or unit,
                )
            return None

        return _inner

    def get_size(self):
        """Get the size of the new template (defaults to size options)"""
        size = self.options.size
        if self.options.size is None:
            size = (
                self.options.width,
                self.options.unit,
                self.options.height,
                self.options.unit,
            )
        if (
            self.options.orientation == "horizontal"
            and size[0] < size[2]
            or self.options.orientation == "vertical"
            and size[0] > size[2]
        ):
            size = size[2:4] + size[0:2]
        return size

    def effect(self):
        """Creates a template, do not over-ride"""
        (width, width_unit, height, height_unit) = self.get_size()
        width_px = int(self.svg.uutounit(width, "px"))
        height_px = int(self.svg.uutounit(height, "px"))

        self.document = self.get_template()
        self.svg = self.document.getroot()
        self.svg.set("id", self.template_id)
        self.svg.set("width", str(width) + width_unit)
        self.svg.set("height", str(height) + height_unit)
        self.svg.set("viewBox", f"0 0 {width} {height}")
        self.set_namedview(width_px, height_px, width_unit)

    def set_namedview(self, width, height, unit):
        """Setup the document namedview"""
        self.svg.namedview.set("inkscape:document-units", unit)
        self.svg.namedview.set("inkscape:zoom", "0.25")
        self.svg.namedview.set("inkscape:cx", str(width / 2.0))
        self.svg.namedview.set("inkscape:cy", str(height / 2.0))
        if self.options.grid:
            self.svg.namedview.set("showgrid", "true")
            self.svg.namedview.add(Grid(type="xygrid"))


class ColorExtension(EffectExtension):
    """
    A standard way to modify colours in an svg document.
    """

    process_none = False  # should we call modify_color for the "none" color.
    select_all = (ShapeElement,)
    pass_rgba = False
    """
    If true, color and opacity are processed together (as RGBA color) 
    by :func:`modify_color`.

    If false (default), they are processed independently by `modify_color` and 
    `modify_opacity`.

    .. versionadded:: 1.2
    """

    def __init__(self):
        super().__init__()
        self._renamed = {}

    def effect(self):
        # Limiting to shapes ignores Gradients (and other things) from the select_all
        # this prevents defs from being processed twice.
        self._renamed = {}
        gradients = CloningVat(self.svg)
        for elem in self.svg.selection.get(ShapeElement):
            self.process_element(elem, gradients)
        gradients.process(self.process_elements, types=(ShapeElement,))

    def process_elements(self, elem):
        """Process multiple elements (gradients)"""
        for child in elem.descendants():
            self.process_element(child)

    def process_element(self, elem, gradients=None):
        """Process one of the selected elements"""
        style = elem.specified_style()
        # Colours first
        for name in (
            elem.style.associated_props if self.pass_rgba else elem.style.color_props
        ):
            if name not in style:
                continue  # we don't want to process default values
            try:
                value = style(name)
            except ColorError:
                continue  # bad color value, don't touch.
            if isinstance(value, Color):
                col = Color(value)
                if self.pass_rgba:
                    col = col.to_rgba(
                        alpha=elem.style(elem.style.associated_props[name])
                    )
                rgba_result = self._modify_color(name, col)
                elem.style.set_color(rgba_result, name)

            if isinstance(value, (LinearGradient, RadialGradient, Pattern)):
                gradients.track(value, elem, self._ref_cloned, style=style, name=name)
                if value.href is not None:
                    gradients.track(value.href, elem, self._xlink_cloned, linker=value)
        # Then opacities (usually does nothing)
        if self.pass_rgba:
            return
        for name in elem.style.opacity_props:
            value = style(name)
            result = self.modify_opacity(name, value)
            if result not in (value, 1):  # only modify if not equal to old or default
                elem.style[name] = result

    def _ref_cloned(self, old_id, new_id, style, name):
        self._renamed[old_id] = new_id
        style[name] = f"url(#{new_id})"

    def _xlink_cloned(self, old_id, new_id, linker):  # pylint: disable=unused-argument
        lid = linker.get("id")
        linker = self.svg.getElementById(self._renamed.get(lid, lid))
        linker.href = new_id

    def _modify_color(self, name, color):
        """Pre-process color value to filter out bad colors"""
        if color or self.process_none:
            return self.modify_color(name, color)
        return color

    def modify_color(self, name, color):
        """Replace this method with your colour modifier method"""
        raise NotImplementedError("Provide a modify_color method.")

    def modify_opacity(
        self, name, opacity
    ):  # pylint: disable=no-self-use, unused-argument
        """Optional opacity modification"""
        return opacity


class TextExtension(EffectExtension):
    """
    A base effect for changing text in a document.
    """

    newline = True
    newpar = True

    def effect(self):
        nodes = self.svg.selection or {None: self.document.getroot()}
        for elem in nodes.values():
            self.process_element(elem)

    def process_element(self, node):
        """Reverse the node text"""
        if node.get("sodipodi:role") == "line":
            self.newline = True
        elif isinstance(node, (TextElement, FlowPara, FlowDiv)):
            self.newline = True
            self.newpar = True

        if node.text is not None:
            node.text = self.process_chardata(node.text)
            self.newline = False
            self.newpar = False

        for child in node:
            self.process_element(child)

        if node.tail is not None:
            node.tail = self.process_chardata(node.tail)

    def process_chardata(self, text):
        """Replaceable chardata method for processing the text"""
        return "".join(map(self.map_char, text))

    @staticmethod
    def map_char(char):
        """Replaceable map_char method for processing each letter"""
        raise NotImplementedError(
            "Please provide a process_chardata or map_char static method."
        )
