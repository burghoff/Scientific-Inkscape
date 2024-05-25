# coding=utf-8
#
# Copyright (C) 2021 Jonathan Neuhauser, jonathan.neuhauser@outlook.com
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
Property management and parsing, CSS cascading, default value storage

.. versionadded:: 1.2

.. data:: all_properties

    A list of all properties, their parser class, and additional information
    such as whether they are inheritable or can be given as presentation attributes
"""

from abc import ABC, abstractmethod

import re
from typing import Tuple, Dict, Type, Union, List, Optional
from .interfaces.IElement import IBaseElement, ISVGDocumentElement

from .units import parse_unit, convert_unit

from .colors import Color, ColorError


class BaseStyleValue:
    """A class encapsuling a single CSS declaration / presentation_attribute"""

    def __init__(self, declaration=None, attr_name=None, value=None, important=False):
        self.attr_name: str
        self.value: str
        self.important: bool
        if declaration is not None and ":" in declaration:
            (
                self.attr_name,
                self.value,
                self.important,
            ) = BaseStyleValue.parse_declaration(declaration)
        elif attr_name is not None:
            self.attr_name = attr_name.strip().lower()
            if isinstance(value, str):
                self.value = value.strip()
            else:
                # maybe its already parsed? then set it
                self.value = self.unparse_value(value)
            self.important = important
            _ = self.parse_value()  # check that we can parse this value

    @classmethod
    def parse_declaration(cls, declaration: str) -> Tuple[str, str, bool]:
        """Parse a single css declaration

        Args:
            declaration (str): a css declaration such as:
                ``fill: #000 !important;``. The trailing semicolon may be ommitted.

        Raises:
            ValueError: Unable to parse the declaration

        Returns:
            Tuple[str, str, bool]: a tuple with key, value and importance
        """
        if declaration != "" and ":" in declaration:
            declaration = declaration.replace(";", "")
            (name, value) = declaration.split(":", 1)
            # check whether this is an important declaration
            important = False
            if "!important" in value:
                value = value.replace("!important", "")
                important = True
            return (name.strip().lower(), value.strip(), important)
        raise ValueError("Invalid declaration")

    def parse_value(self, element=None):
        """Get parsed property value with resolved urls, color, etc.

        Args:
            element (BaseElement): the SVG element to which this style is applied to
                currently used for resolving gradients / masks, could be used for
                computing percentage attributes or calc() attributes [optional]

        Returns:
            object: parsed property value
        """
        if self.value == "inherit":
            if self.attr_name in all_properties:
                return self._parse_value(all_properties[self.attr_name][1], element)
            return None
        return self._parse_value(self.value, element)

    def _parse_value(  # pylint: disable=unused-argument, no-self-use
        self, value: str, element=None
    ) -> object:
        """internal parse method, to be overwritten by derived classes

        Args:
            value (str): unparsed value
            element (BaseElement): the SVG element to which this style is applied to
                [optional]

        Returns:
            object: the parsed value
        """
        return value

    def unparse_value(self, value: object) -> str:
        """ "Unparses" an object, i.e. converts an object back to an attribute.
        If the result is invalid, i.e. can't be parsed, an exception is raised.

        Args:
            value (object): the object to be unparsed

        Returns:
            str: the attribute value
        """
        result = self._unparse_value(value)
        self._parse_value(result)  # check if value can be parsed (value is valid)
        return result

    def _unparse_value(self, value: object) -> str:  # pylint: disable=no-self-use
        return str(value)

    @property
    def declaration(self) -> str:
        """The css declaration corresponding to the StyleValue object

        Returns:
            str: the css declaration, such as "fill: #000 !important;"
        """
        return (
            self.attr_name
            + ":"
            + self.value
            + (" !important" if self.important else "")
        )

    @classmethod
    def factory(
        cls,
        declaration: Optional[str] = None,
        attr_name: Optional[str] = None,
        value: Optional[object] = None,
        important: Optional[bool] = False,
    ):
        """Create an attribute

        Args:
            declaration (str, optional): the CSS declaration to parse. Defaults to None.
            attr_name (str, optional): the attribute name. Defaults to None.
            value (object, optional): the attribute value. Defaults to None.
            important (bool, optional): whether the attribute is marked !important.
                Defaults to False.

        Raises:
            Errors may also be raised on parsing, so make sure to handle them

        Returns:
            BaseStyleValue: the parsed style
        """
        if declaration is not None and ":" in declaration:
            attr_name, value, important = BaseStyleValue.parse_declaration(declaration)
        elif attr_name is not None and value is not None:
            attr_name = attr_name.strip().lower()
            if isinstance(value, str):
                value = value.strip()

        if attr_name in all_properties:
            valuetype = all_properties[attr_name][0]
            return valuetype(declaration, attr_name, value, important)
        return BaseStyleValue(declaration, attr_name, value, important)

    def __eq__(self, other):
        if not (isinstance(other, BaseStyleValue)):
            return False
        if self.declaration != other.declaration:
            return False
        return True

    @staticmethod
    def factory_errorhandled(element=None, declaration="", key="", value=""):
        """Error handling for the factory method: if something goes wrong during
        parsing, ignore the attribute

        Args:
            element (BaseElement, optional): The element this declaration is affecting,
                for finding gradients ect. Defaults to None.
            declaration (str, optional): the CSS declaration to parse. Defaults to "".
            key (str, optional): the attribute name. Defaults to "".
            value (str, optional): the attribute value. Defaults to "".

        Returns:
            BaseStyleValue: The parsed style
        """
        try:
            value = BaseStyleValue.factory(
                declaration=declaration, attr_name=key, value=value
            )
            key = value.attr_name
            # Try to parse the attribute
            _ = value.parse_value(element)
            return (key, value)
        except ValueError:
            # something went wrong during parsing, e.g. a bad attribute format
            # or an attribute referencing a missing gradient
            # -> ignore this declaration
            pass
        except ColorError:
            # The color parsing methods have their own error type
            pass


class AlphaValue(BaseStyleValue):
    """Stores an alpha value (such as opacity), which may be specified as
    as percentage or absolute value.

    Reference: https://www.w3.org/TR/css-color/#typedef-alpha-value"""

    def _parse_value(self, value: str, element=None):
        if value[-1] == "%":  # percentage
            parsed_value = float(value[:-1]) * 0.01
        else:
            parsed_value = float(value)
        if parsed_value < 0:
            return 0
        if parsed_value > 1:
            return 1
        return parsed_value

    def _unparse_value(self, value: object) -> str:
        if isinstance(value, (float, int)):
            if value < 0:
                return "0"
            if value > 1:
                return "1"
            return str(value)
        raise ValueError("Value must be number")


class ColorValue(BaseStyleValue):
    """Stores a color value

    Reference: https://drafts.csswg.org/css-color-3/#valuea-def-color"""

    def _parse_value(self, value: str, element=None):
        if value == "currentColor":
            if element is not None:
                style = element.specified_style()
                return style("color")
            return None
        return Color(value)


# https://www.w3.org/TR/css3-values/#url-value
# matches anything inside url() enclosed with single/double quotes
# (technically a fragment url) or no quotes at all
URLREGEX = r"url\(\s*('.*?'|\".*?\"|[^\"'].*?)\s*\)"


def match_url_and_return_element(string: str, svg):
    """Parses a string containing an url, e.g. "url(#rect1234)",
    looks up the element in the svg document and returns it.

    Args:
        string (str): the string to parse
        svg (SvgDocumentElement): document referenced in the URL

    Raises:
        ValueError: if the string has invalid format
        ValueError: if the referenced element is not found

    Returns:
        BaseElement: the referenced element
    """
    regex = re.compile(URLREGEX)
    match = regex.match(string)
    if match:
        url = match.group(1)
        paint_server = svg.getElementById(url)
        return paint_server
    raise ValueError("invalid URL format")


class URLNoneValue(BaseStyleValue):
    """Stores a value that is either none or an url, such as markers or masks.

    Reference: https://www.w3.org/TR/SVG2/painting.html#VertexMarkerProperties"""

    def _parse_value(self, value: str, element=None):
        if value == "none":
            return None
        if value[0:4] == "url(":
            if element is not None and self.element_has_root(element):
                return match_url_and_return_element(value, element.root)
            return None
        raise ValueError("Invalid property value")

    def _unparse_value(self, value: object):
        if isinstance(value, IBaseElement):
            return f"url(#{value.get_id()})"
        return super()._unparse_value(value)

    @staticmethod
    def element_has_root(element) -> bool:
        "Checks if an element has a root, i.e. if element.root will fail"

        return not (
            element.getparent() is None and not isinstance(element, ISVGDocumentElement)
        )


class PaintValue(ColorValue, URLNoneValue):
    """Stores a paint value (such as fill and stroke), which may be specified
    as color, or url.

    Reference: https://www.w3.org/TR/SVG2/painting.html#SpecifyingPaint"""

    def _parse_value(self, value: str, element=None):
        if value == "none":
            return None
        if value in ["context-fill", "context-stroke"]:
            return value
        if value == "currentColor":
            return super()._parse_value(value, element)
        if value[0:4] == "url(":
            # First part: fragment url
            # second part: a fallback color if the url is not found. Colors start with
            # a letter or a #
            regex = re.compile(URLREGEX + r"\s*([#\w].*?)?$")
            match = regex.match(value)
            if match:
                url = match.group(1)
                if element is not None and self.element_has_root(element):
                    paint_server = element.root.getElementById(url)
                else:
                    return None
                if paint_server is not None:
                    return paint_server
                if match.group(2) is None:
                    raise ValueError("Paint server not found")
                return Color(match.group(2))
        return Color(value)

    def _unparse_value(self, value: object):
        if value is None:
            return "none"
        return super()._unparse_value(value)


class EnumValue(BaseStyleValue):
    """Stores a value that can only have a finite set of options"""

    def __init__(self, declaration=None, attr_name=None, value=None, important=False):
        self.valueset = all_properties[attr_name][4]
        super().__init__(declaration, attr_name, value, important)

    def _parse_value(self, value: str, element=None):
        if value in self.valueset:
            return value
        raise ValueError(
            f"Value '{value}' is invalid for the property {self.attr_name}. "
            + f"Allowed values are: {self.valueset + ['inherit']}"
        )


class ShorthandValue(BaseStyleValue, ABC):
    """Stores a value that sets other values (e.g. the font shorthand)"""

    def apply_shorthand(self, style):
        """Applies a shorthand attribute to its style, respecting the
        importance state of the individual attributes.

        Args:
            style (Style): the style that the shorthand attribute is contained in,
                and that the shorthand attribute will be applied on
        """
        if self.attr_name not in style:
            return

        dct = self.get_shorthand_changes()
        importance = self.important

        # they are ordered in the order of adding the style elements.
        current_keys = list(style.keys())
        for curkey in dct:
            perform = False
            if curkey not in current_keys:
                # this is the easiest case, just set the element and the importance
                perform = True
            else:
                if importance != style.get_importance(curkey):
                    # different importance, result independent of position
                    perform = importance
                else:
                    # only apply if style overwrites previous with same importance
                    perform = current_keys.index(curkey) < current_keys.index(
                        self.attr_name
                    )

            if perform:
                style[curkey] = dct[curkey]
                style.set_importance(curkey, importance)
        style.pop(self.attr_name)

    @abstractmethod
    def get_shorthand_changes(self) -> Dict[str, str]:
        """calculates the value of affected attributes for this shorthand

        Returns:
            Dict[str, str]: a dictionary containing the new values of the
            affected attributes
        """


class FontValue(ShorthandValue):
    """Logic for the shorthand font property"""

    def get_shorthand_changes(self):
        keys = [
            "font-style",
            "font-variant",
            "font-weight",
            "font-stretch",
            "font-size",
            "line-height",
            "font-family",
        ]
        options = {
            key: all_properties[key][4]
            for key in keys
            if isinstance(all_properties[key][4], list)
        }
        # Font stretch can be specified in percent, but for the
        # shorthand, only a keyword value is allowed
        options["font-stretch"] = (
            "normal",
            "ultra-condensed",
            "extra-condensed",
            "condensed",
            "semi-condensed",
            "semi-expanded",
            "expanded",
            "extra-expanded",
            "ultra-expanded",
        )
        result = {key: all_properties[key][1] for key in keys}

        tokens = [i for i in self.value.split() if i != ""]

        if len(tokens) == 0:
            return {}  # shorthand not set, nothing to do

        while not (len(tokens) == 0):
            cur = tokens[0]
            if cur in options["font-style"]:
                result["font-style"] = cur
            elif cur in options["font-variant"]:
                result["font-variant"] = cur
            elif cur in options["font-weight"]:
                result["font-weight"] = cur
            elif cur in options["font-stretch"]:
                result["font-stretch"] = cur
            else:
                if "/" in cur:
                    result["font-size"], result["line-height"] = cur.split("/")
                else:
                    result["font-size"] = cur
                result["font-family"] = " ".join(tokens[1:])
                break
            tokens = tokens[1:]  # remove first element
        return result


class TextDecorationValue(ShorthandValue):
    """Logic for the shorthand font property

    .. versionadded:: 1.3"""

    def get_shorthand_changes(self):
        options = {
            "text-decoration-" + key: all_properties["text-decoration-" + key][4]
            for key in ("line", "style", "color")
            if isinstance(all_properties["text-decoration-" + key][4], list)
        }
        result = {
            "text-decoration-style": all_properties["text-decoration-style"][1],
            "text-decoration-color": "currentcolor",
            "text-decoration-line": [],
        }

        tokens = [i for i in self.value.split() if i != ""]

        if len(tokens) == 0:
            return {}  # shorthand not set, nothing to do

        for cur in tokens:
            if cur in ["underline", "overline", "line-through", "blink"]:
                result["text-decoration-line"] += [cur]
            elif cur in options["text-decoration-style"]:
                result["text-decoration-style"] = cur
            else:
                result["text-decoration-color"] = cur

        if len(result["text-decoration-line"]) == 0:
            result["text-decoration-line"] = all_properties["text-decoration-line"][4]
        else:
            # Text-decoration-line can have multiple values.
            result["text-decoration-line"] = " ".join(result["text-decoration-line"])

        return result


class MarkerShorthandValue(ShorthandValue, URLNoneValue):
    """Logic for the marker shorthand property"""

    def get_shorthand_changes(self):
        if self.value == "":
            return {}  # shorthand not set, nothing to do
        return {k: self.value for k in ["marker-start", "marker-end", "marker-mid"]}

    def _parse_value(self, value: str, element=None):
        # Make sure the parsing routine doesn't choke on an empty shorthand
        if value == "":
            return ""
        return super()._parse_value(value, element)


class FontSizeValue(BaseStyleValue):
    """Logic for the font-size property"""

    def _parse_value(self, value: str, element=None):
        if element is None:
            return value  # no additional logic in this case
        try:
            return element.to_dimensionless(value)
        except ValueError:  # unable to parse font size, e.g. font-size:normal
            return element.to_dimensionless("12")


class StrokeDasharrayValue(BaseStyleValue):
    """Logic for the stroke-dasharray property"""

    def _parse_value(self, value: str, element=None):
        dashes = re.findall(r"[^,\s]+", value)
        if len(dashes) == 0 or value == "none":
            return None  # no dasharray applied
        if not any(parse_unit(i) is None for i in dashes):
            dashes = [convert_unit(i, "px") for i in dashes]
        else:
            return None
        if any(i < 0 for i in dashes):
            return None  # one negative value makes the dasharray invalid
        if len(dashes) % 2 == 1:
            dashes = 2 * dashes
        return dashes

    def _unparse_value(self, value: object) -> str:
        if value is None:
            return "none"
        if isinstance(value, list):
            return " ".join(map(str, value))
        return str(value)


# keys: attributes, right side:
# - Subclass of BaseStyleValue used for instantiating
# - default value
# - is presentation attribute
# - inherited
# - additional information, such as valid enum values
# For properties which have no special implementation yet:
# "(BaseStyleValue, <default>, <inheritance>, None)"

# Source for this list: https://www.w3.org/TR/SVG2/styling.html#PresentationAttributes


all_properties: Dict[
    str, Tuple[Type[BaseStyleValue], str, bool, bool, Union[List[str], None]]
] = {
    "alignment-baseline": (
        EnumValue,
        "baseline",
        True,
        False,
        [
            "baseline",
            "text-bottom",
            "alphabetic",
            "ideographic",
            "middle",
            "central",
            "mathematical",
            "text-top",
        ],
    ),
    "baseline-shift": (BaseStyleValue, "0", True, False, None),
    "clip": (BaseStyleValue, "auto", True, False, None),
    "clip-path": (URLNoneValue, "none", True, False, None),
    "clip-rule": (EnumValue, "nonzero", True, True, ["nonzero", "evenodd"]),
    # only used for currentColor, which is not yet implemented
    "color": (PaintValue, "black", True, True, None),
    "color-interpolation": (
        EnumValue,
        "sRGB",
        True,
        True,
        ["sRGB", "auto", "linearRGB"],
    ),
    "color-interpolation-filters": (
        EnumValue,
        "linearRGB",
        True,
        True,
        ["auto", "sRGB", "linearRGB"],
    ),
    "color-rendering": (
        EnumValue,
        "auto",
        True,
        True,
        ["auto", "optimizeSpeed", "optimizeQuality"],
    ),
    "cursor": (BaseStyleValue, "auto", True, True, None),
    "direction": (EnumValue, "ltr", True, True, ["ltr", "rtl"]),
    "display": (
        EnumValue,
        "inline",
        True,
        False,
        [
            "inline",
            "block",
            "list-item",
            "inline-block",
            "table",
            "inline-table",
            "table-row-group",
            "table-header-group",
            "table-footer-group",
            "table-row",
            "table-column-group",
            "table-column",
            "table-cell",
            "table-caption",
            "none",
        ],
    ),  # every value except none is rendered normally
    "dominant-baseline": (
        EnumValue,
        "auto",
        True,
        True,
        [
            "auto",
            "text-bottom",
            "alphabetic",
            "ideographic",
            "middle",
            "central",
            "mathematical",
            "hanging",
            "text-top",
        ],
    ),
    "fill": (
        PaintValue,
        "black",
        True,
        True,
        None,
    ),  # the normal fill, not the <animation> one
    "fill-opacity": (AlphaValue, "1", True, True, None),
    "fill-rule": (EnumValue, "nonzero", True, True, ["nonzero", "evenodd"]),
    "filter": (URLNoneValue, "none", True, False, None),
    "flood-color": (PaintValue, "black", True, False, None),
    "flood-opacity": (AlphaValue, "1", True, False, None),
    "font": (FontValue, "", True, False, None),
    "font-family": (BaseStyleValue, "sans-serif", True, True, None),
    "font-size": (FontSizeValue, "medium", True, True, None),
    "font-size-adjust": (BaseStyleValue, "none", True, True, None),
    "font-stretch": (BaseStyleValue, "normal", True, True, None),
    "font-style": (EnumValue, "normal", True, True, ["normal", "italic", "oblique"]),
    # a lot more values and subproperties in SVG2 / CSS-Fonts3
    "font-variant": (EnumValue, "normal", True, True, ["normal", "small-caps"]),
    "font-weight": (
        EnumValue,
        "normal",
        True,
        True,
        ["normal", "bold"] + [str(i) for i in range(100, 901, 100)],
    ),
    "glyph-orientation-horizontal": (BaseStyleValue, "0deg", True, True, None),
    "glyph-orientation-vertical": (BaseStyleValue, "auto", True, True, None),
    "inline-size": (BaseStyleValue, "0", False, False, None),
    "image-rendering": (
        EnumValue,
        "auto",
        True,
        True,
        ["auto", "optimizeQuality", "optimizeSpeed"],
    ),
    "letter-spacing": (BaseStyleValue, "normal", True, True, None),
    "lighting-color": (ColorValue, "normal", True, False, None),
    "line-height": (BaseStyleValue, "normal", False, True, None),
    "marker": (MarkerShorthandValue, "", True, True, None),
    "marker-end": (URLNoneValue, "none", True, True, None),
    "marker-mid": (URLNoneValue, "none", True, True, None),
    "marker-start": (URLNoneValue, "none", True, True, None),
    # is a shorthand for a lot of mask-related properties which Inkscape doesn't support
    "mask": (URLNoneValue, "none", True, False, None),
    "opacity": (AlphaValue, "1", True, False, None),
    "overflow": (
        EnumValue,
        "visible",
        True,
        False,
        ["visible", "hidden", "scroll", "auto"],
    ),
    "paint-order": (BaseStyleValue, "normal", True, False, None),
    "pointer-events": (
        EnumValue,
        "visiblePainted",
        True,
        True,
        [
            "bounding-box",
            "visiblePainted",
            "visibleFill",
            "visibleStroke",
            "visible",
            "painted",
            "fill",
            "stroke",
            "all",
            "none",
        ],
    ),
    "shape-inside": (URLNoneValue, "none", False, False, None),
    "shape-rendering": (
        EnumValue,
        "visiblePainted",
        True,
        True,
        ["auto", "optimizeSpeed", "crispEdges", "geometricPrecision"],
    ),
    "stop-color": (ColorValue, "black", True, False, None),
    "stop-opacity": (AlphaValue, "1", True, False, None),
    "stroke": (PaintValue, "none", True, True, None),
    "stroke-dasharray": (StrokeDasharrayValue, "none", True, True, None),
    "stroke-dashoffset": (BaseStyleValue, "0", True, True, None),
    "stroke-linecap": (EnumValue, "butt", True, True, ["butt", "round", "square"]),
    "stroke-linejoin": (
        EnumValue,
        "miter",
        True,
        True,
        ["miter", "miter-clip", "round", "bevel", "arcs"],
    ),
    "stroke-miterlimit": (BaseStyleValue, "4", True, True, None),
    "stroke-opacity": (AlphaValue, "1", True, True, None),
    "stroke-width": (BaseStyleValue, "1", True, True, None),
    "text-align": (
        BaseStyleValue,
        "start",
        True,
        True,
        None,
    ),  # only HTML property, but used by some unit tests
    "text-anchor": (EnumValue, "start", True, True, ["start", "middle", "end"]),
    # shorthand for text-decoration-line, *-style, *-color
    "text-decoration": (TextDecorationValue, "", True, True, None),
    # multiple enum values are allowed
    "text-decoration-line": (BaseStyleValue, "none", False, False, None),
    "text-decoration-style": (
        EnumValue,
        "solid",
        False,
        False,
        ["solid", "double", "dotted", "dashed", "wavy"],
    ),
    # This currently cannot be a ColorValue because currentcolor and other special
    # colors are not supported by the Color class
    "text-decoration-color": (BaseStyleValue, "currentcolor", False, False, None),
    "text-overflow": (EnumValue, "clip", True, False, ["clip", "ellipsis"]),
    "text-rendering": (
        EnumValue,
        "auto",
        True,
        True,
        ["auto", "optimizeSpeed", "optimizeLegibility", "geometricPrecision"],
    ),
    "unicode-bidi": (
        EnumValue,
        "normal",
        True,
        False,
        [
            "normal",
            "embed",
            "isolate",
            "bidi-override",
            "isolate-override",
            "plaintext",
        ],
    ),
    "vector-effect": (BaseStyleValue, "none", True, False, None),
    "vertical-align": (BaseStyleValue, "baseline", False, False, None),
    "visibility": (EnumValue, "visible", True, True, ["visible", "hidden", "collapse"]),
    "white-space": (
        EnumValue,
        "normal",
        True,
        True,
        ["normal", "pre", "nowrap", "pre-wrap", "break-spaces", "pre-line"],
    ),
    "word-spacing": (BaseStyleValue, "normal", True, True, None),
    # including obsolete SVG 1.1 values
    "writing-mode": (
        EnumValue,
        "horizontal-tb",
        True,
        True,
        [
            "horizontal-tb",
            "vertical-rl",
            "vertical-lr",
            "lr",
            "lr-tb",
            "rl",
            "rl-tb",
            "tb",
            "tb-rl",
        ],
    ),
    "-inkscape-font-specification": (BaseStyleValue, "sans-serif", False, True, None),
}
