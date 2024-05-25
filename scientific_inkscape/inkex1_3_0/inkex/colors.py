# coding=utf-8
#
# Copyright (C) 2006 Jos Hirth, kaioa.com
# Copyright (C) 2007 Aaron C. Spike
# Copyright (C) 2009 Monash University
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
Basic color controls
"""


# All the names that get added to the inkex API itself.
__all__ = ("Color", "ColorError", "ColorIdError")

SVG_COLOR = {
    "aliceblue": "#f0f8ff",
    "antiquewhite": "#faebd7",
    "aqua": "#00ffff",
    "aquamarine": "#7fffd4",
    "azure": "#f0ffff",
    "beige": "#f5f5dc",
    "bisque": "#ffe4c4",
    "black": "#000000",
    "blanchedalmond": "#ffebcd",
    "blue": "#0000ff",
    "blueviolet": "#8a2be2",
    "brown": "#a52a2a",
    "burlywood": "#deb887",
    "cadetblue": "#5f9ea0",
    "chartreuse": "#7fff00",
    "chocolate": "#d2691e",
    "coral": "#ff7f50",
    "cornflowerblue": "#6495ed",
    "cornsilk": "#fff8dc",
    "crimson": "#dc143c",
    "cyan": "#00ffff",
    "darkblue": "#00008b",
    "darkcyan": "#008b8b",
    "darkgoldenrod": "#b8860b",
    "darkgray": "#a9a9a9",
    "darkgreen": "#006400",
    "darkgrey": "#a9a9a9",
    "darkkhaki": "#bdb76b",
    "darkmagenta": "#8b008b",
    "darkolivegreen": "#556b2f",
    "darkorange": "#ff8c00",
    "darkorchid": "#9932cc",
    "darkred": "#8b0000",
    "darksalmon": "#e9967a",
    "darkseagreen": "#8fbc8f",
    "darkslateblue": "#483d8b",
    "darkslategray": "#2f4f4f",
    "darkslategrey": "#2f4f4f",
    "darkturquoise": "#00ced1",
    "darkviolet": "#9400d3",
    "deeppink": "#ff1493",
    "deepskyblue": "#00bfff",
    "dimgray": "#696969",
    "dimgrey": "#696969",
    "dodgerblue": "#1e90ff",
    "firebrick": "#b22222",
    "floralwhite": "#fffaf0",
    "forestgreen": "#228b22",
    "fuchsia": "#ff00ff",
    "gainsboro": "#dcdcdc",
    "ghostwhite": "#f8f8ff",
    "gold": "#ffd700",
    "goldenrod": "#daa520",
    "gray": "#808080",
    "grey": "#808080",
    "green": "#008000",
    "greenyellow": "#adff2f",
    "honeydew": "#f0fff0",
    "hotpink": "#ff69b4",
    "indianred": "#cd5c5c",
    "indigo": "#4b0082",
    "ivory": "#fffff0",
    "khaki": "#f0e68c",
    "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5",
    "lawngreen": "#7cfc00",
    "lemonchiffon": "#fffacd",
    "lightblue": "#add8e6",
    "lightcoral": "#f08080",
    "lightcyan": "#e0ffff",
    "lightgoldenrodyellow": "#fafad2",
    "lightgray": "#d3d3d3",
    "lightgreen": "#90ee90",
    "lightgrey": "#d3d3d3",
    "lightpink": "#ffb6c1",
    "lightsalmon": "#ffa07a",
    "lightseagreen": "#20b2aa",
    "lightskyblue": "#87cefa",
    "lightslategray": "#778899",
    "lightslategrey": "#778899",
    "lightsteelblue": "#b0c4de",
    "lightyellow": "#ffffe0",
    "lime": "#00ff00",
    "limegreen": "#32cd32",
    "linen": "#faf0e6",
    "magenta": "#ff00ff",
    "maroon": "#800000",
    "mediumaquamarine": "#66cdaa",
    "mediumblue": "#0000cd",
    "mediumorchid": "#ba55d3",
    "mediumpurple": "#9370db",
    "mediumseagreen": "#3cb371",
    "mediumslateblue": "#7b68ee",
    "mediumspringgreen": "#00fa9a",
    "mediumturquoise": "#48d1cc",
    "mediumvioletred": "#c71585",
    "midnightblue": "#191970",
    "mintcream": "#f5fffa",
    "mistyrose": "#ffe4e1",
    "moccasin": "#ffe4b5",
    "navajowhite": "#ffdead",
    "navy": "#000080",
    "oldlace": "#fdf5e6",
    "olive": "#808000",
    "olivedrab": "#6b8e23",
    "orange": "#ffa500",
    "orangered": "#ff4500",
    "orchid": "#da70d6",
    "palegoldenrod": "#eee8aa",
    "palegreen": "#98fb98",
    "paleturquoise": "#afeeee",
    "palevioletred": "#db7093",
    "papayawhip": "#ffefd5",
    "peachpuff": "#ffdab9",
    "peru": "#cd853f",
    "pink": "#ffc0cb",
    "plum": "#dda0dd",
    "powderblue": "#b0e0e6",
    "purple": "#800080",
    "rebeccapurple": "#663399",
    "red": "#ff0000",
    "rosybrown": "#bc8f8f",
    "royalblue": "#4169e1",
    "saddlebrown": "#8b4513",
    "salmon": "#fa8072",
    "sandybrown": "#f4a460",
    "seagreen": "#2e8b57",
    "seashell": "#fff5ee",
    "sienna": "#a0522d",
    "silver": "#c0c0c0",
    "skyblue": "#87ceeb",
    "slateblue": "#6a5acd",
    "slategray": "#708090",
    "slategrey": "#708090",
    "snow": "#fffafa",
    "springgreen": "#00ff7f",
    "steelblue": "#4682b4",
    "tan": "#d2b48c",
    "teal": "#008080",
    "thistle": "#d8bfd8",
    "tomato": "#ff6347",
    "turquoise": "#40e0d0",
    "violet": "#ee82ee",
    "wheat": "#f5deb3",
    "white": "#ffffff",
    "whitesmoke": "#f5f5f5",
    "yellow": "#ffff00",
    "yellowgreen": "#9acd32",
    "none": None,
}
COLOR_SVG = {value: name for name, value in SVG_COLOR.items()}


def is_color(color):
    """Determine if it is a color that we can use. If not, leave it unchanged."""
    try:
        return bool(Color(color))
    except ColorError:
        return False


def constrain(minim, value, maxim, channel):
    """Returns the value so long as it is between min and max values"""
    if channel == "h":  # Hue
        return value % maxim  # Wrap around hue value
    return min([maxim, max([minim, value])])


class ColorError(KeyError):
    """Specific color parsing error"""


class ColorIdError(ColorError):
    """Special color error for gradient and color stop ids"""


class Color(list):
    """An RGB array for the color

    Can be constructed from valid CSS color attributes, as well as
    tuple/list + color space. Percentage values are supported.

    .. versionchanged:: 1.2
        Clarification with respect to values denoting unity: For RGB color channels,
        "1.0", 1.0 and "100%" are treated as 255, while "1" and 1 are treated as 1.

    """

    red = property(
        lambda self: self.to_rgb()[0], lambda self, value: self._set(0, value)
    )
    green = property(
        lambda self: self.to_rgb()[1], lambda self, value: self._set(1, value)
    )
    blue = property(
        lambda self: self.to_rgb()[2], lambda self, value: self._set(2, value)
    )
    alpha = property(
        lambda self: self.to_rgba()[3],
        lambda self, value: self._set(3, value, ("rgba",)),
    )
    hue = property(
        lambda self: self.to_hsl()[0], lambda self, value: self._set(0, value, ("hsl",))
    )
    saturation = property(
        lambda self: self.to_hsl()[1], lambda self, value: self._set(1, value, ("hsl",))
    )
    lightness = property(
        lambda self: self.to_hsl()[2], lambda self, value: self._set(2, value, ("hsl",))
    )

    def __init__(self, color=None, space="rgb"):
        super().__init__()
        if isinstance(color, Color):
            space, color = color.space, list(color)

        if isinstance(color, str):
            # String from xml or css attributes
            space, color = self.parse_str(color.strip())

        if isinstance(color, int):
            # Number from arg parser colour value
            space, color = self.parse_int(color)

        # Empty list means 'none', or no color
        if color is None:
            color = []

        if not isinstance(color, (list, tuple)):
            raise ColorError("Not a known a color value")

        self.space = space
        try:
            for val in color:
                self.append(val)
        except ValueError as error:
            raise ColorError("Bad color list") from error

    def __hash__(self):
        """Allow colors to be hashable"""
        return tuple(self.to_rgba()).__hash__()

    def _set(self, index, value, spaces=("rgb", "rgba")):
        """Set the color value in place, limits setter to specific color space"""
        # Named colors are just rgb, so dump name memory
        if self.space == "named":
            self.space = "rgb"
        if not self.space in spaces:
            if index == 3 and self.space == "rgb":
                # Special, add alpha, don't convert back to rgb
                self.space = "rgba"
                self.append(constrain(0.0, float(value), 1.0, "a"))
                return
            # Set in other colour space and convert back and forth
            target = self.to(spaces[0])
            target[index] = constrain(0, int(value), 255, spaces[0][index])
            self[:] = target.to(self.space)
            return
        self[index] = constrain(0, int(value), 255, spaces[0][index])

    def append(self, val):
        """Append a value to the local list"""
        if len(self) == len(self.space):
            raise ValueError("Can't add any more values to color.")

        if isinstance(val, str):
            val = val.strip()
            if val.endswith("%"):
                val = float(val.strip("%")) / 100
            elif "." in val:
                val = float(val)
            else:
                val = int(val)

        end_type = int
        if len(self) == 3:  # Alpha value
            val = min([1.0, val])
            end_type = float
        elif isinstance(val, float) and val <= 1.0:
            val *= 255

        if isinstance(val, (int, float)):
            super().append(max(end_type(val), 0))

    @staticmethod
    def parse_str(color):
        """Creates a rgb int array"""
        # Handle pre-defined svg color values
        if color and color.lower() in SVG_COLOR:
            return "named", Color.parse_str(SVG_COLOR[color.lower()])[1]

        if color is None:
            return "rgb", None

        if color.startswith("url("):
            raise ColorIdError("Color references other element id, e.g. a gradient")

        # Next handle short colors (css: #abc -> #aabbcc)
        if color.startswith("#"):
            # Remove any icc or ilab directives
            # FUTURE: We could use icc or ilab information
            col = color.split(" ")[0]
            if len(col) == 4:
                # pylint: disable=consider-using-f-string
                col = "#{1}{1}{2}{2}{3}{3}".format(*col)

            # Convert hex to integers
            try:
                return "rgb", (int(col[1:3], 16), int(col[3:5], 16), int(col[5:], 16))
            except ValueError as error:
                raise ColorError(f"Bad RGB hex color value {col}") from error

        # Handle other css color values
        elif "(" in color and ")" in color:
            space, values = color.lower().strip().strip(")").split("(")
            return space, values.split(",")

        try:
            return Color.parse_int(int(color))
        except ValueError:
            pass

        raise ColorError(f"Unknown color format: {color}")

    @staticmethod
    def parse_int(color):
        """Creates an rgb or rgba from a long int"""
        space = "rgb"
        color = [
            ((color >> 24) & 255),  # red
            ((color >> 16) & 255),  # green
            ((color >> 8) & 255),  # blue
            ((color & 255) / 255.0),  # opacity
        ]
        if color[-1] == 1.0:
            color.pop()
        else:
            space = "rgba"
        return space, color

    def __str__(self):
        """int array to #rrggbb"""
        # pylint: disable=consider-using-f-string
        if not self:
            return "none"
        if self.space == "named":
            rgbhex = "#{0:02x}{1:02x}{2:02x}".format(*self)
            if rgbhex in COLOR_SVG:
                return COLOR_SVG[rgbhex]
            self.space = "rgb"
        if self.space == "rgb":
            return "#{0:02x}{1:02x}{2:02x}".format(*self)
        if self.space == "rgba":
            if self[3] == 1.0:
                return "rgb({:g}, {:g}, {:g})".format(*self[:3])
            return "rgba({:g}, {:g}, {:g}, {:g})".format(*self)
        if self.space == "hsl":
            return "hsl({0:g}, {1:g}, {2:g})".format(*self)
        raise ColorError(f"Can't print colour space '{self.space}'")

    def __int__(self):
        """int array to large integer"""
        if not self:
            return -1
        color = self.to_rgba()
        return (
            (color[0] << 24)
            + (color[1] << 16)
            + (color[2] << 8)
            + (int(color[3] * 255))
        )

    def to(self, space):  # pylint: disable=invalid-name
        """Dynamic caller for to_hsl, to_rgb, etc"""
        return getattr(self, "to_" + space)()

    def to_hsl(self):
        """Turn this color into a Hue/Saturation/Lightness colour space"""
        if not self and self.space in ("rgb", "named"):
            return self.to_rgb().to_hsl()
        if self.space == "hsl":
            return self
        if self.space in ("named"):
            return self.to_rgb().to_hsl()
        if self.space == "rgb":
            return Color(rgb_to_hsl(*self.to_floats()), space="hsl")
        raise ColorError(f"Unknown color conversion {self.space}->hsl")

    def to_rgb(self):
        """Turn this color into a Red/Green/Blue colour space"""
        if not self and self.space in ("rgb", "named"):
            return Color([0, 0, 0])
        if self.space == "rgb":
            return self
        if self.space in ("rgba", "named"):
            return Color(self[:3], space="rgb")
        if self.space == "hsl":
            return Color(hsl_to_rgb(*self.to_floats()), space="rgb")
        raise ColorError(f"Unknown color conversion {self.space}->rgb")

    def to_rgba(self, alpha=1.0):
        """Turn this color isn't an RGB with Alpha colour space"""
        if self.space == "rgba":
            return self
        return Color(self.to_rgb() + [alpha], "rgba")

    def to_floats(self):
        """Returns the colour values as percentage floats (0.0 - 1.0)"""
        return [val / 255.0 for val in self]

    def to_named(self):
        """Convert this color to a named color if possible"""
        if not self:
            return Color()
        return Color(COLOR_SVG.get(str(self), str(self)))

    def interpolate(self, other, fraction):
        """Interpolate two colours by the given fraction

        .. versionadded:: 1.1"""
        from .tween import ColorInterpolator  # pylint: disable=import-outside-toplevel

        return ColorInterpolator(self, other).interpolate(fraction)

    @staticmethod
    def isnone(x):
        """Checks if a given color is none

        .. versionadded:: 1.2"""

        if x is None or (isinstance(x, str) and x.lower() == "none"):
            return True
        return False

    @staticmethod
    def iscolor(x, accept_none=False):
        """Checks if a given value can be parsed as a color

        .. versionadded:: 1.2"""
        if isinstance(x, str) and (accept_none or not (Color.isnone(x))):
            try:
                Color(x)
                return True
            except ColorError:
                pass
        if isinstance(x, Color):
            return True
        return False


def rgb_to_hsl(red, green, blue):
    """RGB to HSL colour conversion"""
    rgb_max = max(red, green, blue)
    rgb_min = min(red, green, blue)
    delta = rgb_max - rgb_min
    hsl = [0.0, 0.0, (rgb_max + rgb_min) / 2.0]
    if delta != 0:
        if hsl[2] <= 0.5:
            hsl[1] = delta / (rgb_max + rgb_min)
        else:
            hsl[1] = delta / (2 - rgb_max - rgb_min)

        if red == rgb_max:
            hsl[0] = (green - blue) / delta
        elif green == rgb_max:
            hsl[0] = 2.0 + (blue - red) / delta
        elif blue == rgb_max:
            hsl[0] = 4.0 + (red - green) / delta

        hsl[0] /= 6.0
        if hsl[0] < 0:
            hsl[0] += 1
        if hsl[0] > 1:
            hsl[0] -= 1
    return hsl


def hsl_to_rgb(hue, sat, light):
    """HSL to RGB Color Conversion"""
    if sat == 0:
        return [light, light, light]  # Gray

    if light < 0.5:
        val2 = light * (1 + sat)
    else:
        val2 = light + sat - light * sat
    val1 = 2 * light - val2
    return [
        _hue_to_rgb(val1, val2, hue * 6 + 2.0),
        _hue_to_rgb(val1, val2, hue * 6),
        _hue_to_rgb(val1, val2, hue * 6 - 2.0),
    ]


def _hue_to_rgb(val1, val2, hue):
    if hue < 0:
        hue += 6.0
    if hue > 6:
        hue -= 6.0
    if hue < 1:
        return val1 + (val2 - val1) * hue
    if hue < 3:
        return val2
    if hue < 4:
        return val1 + (val2 - val1) * (4 - hue)
    return val1
