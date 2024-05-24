# Fork of the v1.1 Style
# Adds some instance checks to reduce number of inits that need to be called
# Uses dicts instead of OrderedDicts, which are faster

# Copyright (C) 2005 Aaron Spike, aaron@ekips.org

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

import inkex

import inspect
from functools import lru_cache


def count_callers():
    caller_frame = inspect.stack()[2]
    filename = caller_frame.filename
    line_number = caller_frame.lineno
    lstr = f"{filename} at line {line_number}"
    global callinfo
    try:
        callinfo
    except:
        callinfo = dict()
    if lstr in callinfo:
        callinfo[lstr] += 1
    else:
        callinfo[lstr] = 1
    inkex.utils.debug(lstr)


class Style0(dict):
    """A list of style directives"""

    color_props = ("stroke", "fill", "stop-color", "flood-color", "lighting-color")
    opacity_props = ("stroke-opacity", "fill-opacity", "opacity", "stop-opacity")
    unit_props = "stroke-width"

    # We modify Style so that it has two versions: one without the callback
    # (Style0) and one with (Style0cb). That way, when no callback is needed,
    # we do not incur extra overhead by overloading __setitem__, __delitem__, etc.
    def __new__(cls, style=None, callback=None, **kw):
        if cls != Style0 and issubclass(
            cls, Style0
        ):  # Don't treat subclasses' arguments as callback
            return dict.__new__(cls)
        elif callback is not None:
            instance = dict.__new__(Style0cb)
            instance.__init__(style, callback, **kw)
            return instance
        else:
            return dict.__new__(cls)

    def __init__(self, style=None, **kw):
        # Either a string style or kwargs (with dashes as underscores).
        if style is None:    
            if kw:
                style = ((k.replace("_", "-"), v) for k, v in kw.items())
            else:
                return
        elif isinstance(style, str):
            style = self.parse_str(style)
        # Order raw dictionaries so tests can be made reliable
        # if isinstance(style, dict) and not isinstance(style, inkex.OrderedDict):
        #     style = [(name, style[name]) for name in sorted(style)]
        # Should accept dict, Style, parsed string, list etc.
        # dict.__init__(self,style)
        self.update(style)

    @staticmethod
    @lru_cache(maxsize=None)
    def parse_str(style):
        """Create a dictionary from the value of an inline style attribute"""
        if style is None:
            style = ""
        ret = []
        for directive in style.split(";"):
            if ":" in directive:
                (name, value) = directive.split(":", 1)
                # FUTURE: Parse value here for extra functionality
                ret.append((name.strip().lower(), value.strip()))
        return ret

    def __str__(self):
        """Format an inline style attribute from a dictionary"""
        return ';'.join(
            [f"{key}:{value}" for key, value in self.items()]
        )

    def to_str(self, sep=";"):
        """Convert to string using a custom delimiter"""
        return sep.join(
            [f"{key}:{value}" for key, value in self.items()]
        )

    def __hash__(self):
        return hash(tuple(self.items()))
        # return hash(self.to_str())

    def __add__(self, other):
        """Add two styles together to get a third, composing them"""
        # ret = self.copy()
        # ret.update(other)
        ret = dict.__new__(type(self))
        ret.update(self)
        ret.update(other)
        return ret
    
    def add3(self,other1,other2):
        ret = dict.__new__(type(self))
        ret.update(self)
        ret.update(other1)
        ret.update(other2)
        return ret

    # A shallow copy that does not call __init__
    def copy(self):
        new_instance = dict.__new__(type(self))
        new_instance.update(self)
        return new_instance

    def __iadd__(self, other):
        """Add style to this style, the same as style.update(dict)"""
        self.update(other)
        return self

    def __sub__(self, other):
        """Remove keys and return copy"""
        ret = self.copy()
        ret.__isub__(other)
        return ret

    def __isub__(self, other):
        """Remove keys from this style, list of keys or other style dictionary"""
        for key in other:
            self.pop(key, None)
        return self

    # def __eq__(self, other):
    #     """Not equals, prefer to overload 'in' but that doesn't seem possible"""
    #     if not isinstance(other, Style0):
    #         other = Style0(other)
    #     return dict.__eq__(self,other)
    #     # Inkex uses dict comparison, not OrderedDict
    #     # for arg in set(self) | set(other):
    #     #     if self.get(arg, None) != other.get(arg, None):
    #     #         return False
    #     # return True

    __ne__ = lambda self, other: not self.__eq__(other)

    # def update(self, other):
    #     if not (isinstance(other, Style0)):
    #         other = Style0(other)
    #     super().update(other)

    def get_color(self, name="fill"):
        """Get the color AND opacity as one Color object"""
        color = inkex.Color(self.get(name, "none"))
        return color.to_rgba(self.get(name + "-opacity", 1.0))

    def set_color(self, color, name="fill"):
        """Sets the given color AND opacity as rgba to the fill or stroke style properties."""
        color = inkex.Color(color)
        if color.space == "rgba":
            self[name + "-opacity"] = color.alpha
        self[name] = str(color.to_rgb())

    def update_urls(self, old_id, new_id):
        """Find urls in this style and replace them with the new id"""
        for name, value in self.items():
            if value == f"url(#{old_id})":
                self[name] = f"url(#{new_id})"

    def interpolate_prop(self, other, fraction, prop, svg=None):
        """Interpolate specific property."""
        a1 = self[prop]
        a2 = other.get(prop, None)
        if a2 is None:
            val = a1
        else:
            if prop in self.color_props:
                if isinstance(a1, inkex.Color):
                    val = a1.interpolate(inkex.Color(a2), fraction)
                elif a1.startswith("url(") or a2.startswith("url("):
                    # gradient requires changes to the whole svg
                    # and needs to be handled externally
                    val = a1
                else:
                    val = inkex.Color(a1).interpolate(inkex.Color(a2), fraction)
            elif prop in self.opacity_props:
                val = inkex.interpcoord(float(a1), float(a2), fraction)
            elif prop in self.unit_props:
                val = inkex.interpunit(a1, a2, fraction)
            else:
                val = a1
        return val

    def interpolate(self, other, fraction):
        """Interpolate all properties."""
        style = Style0()
        for prop, value in self.items():
            style[prop] = self.interpolate_prop(other, fraction, prop)
        return style


class Style0cb(Style0):
    def __init__(self, style=None, callback=None, **kw):
        # This callback is set twice because this is 'pre-initial' data (no callback)
        self.callback = None
        super().__init__(style, **kw)
        self.callback = callback

    # A shallow copy that does not call __init__
    def copy(self):
        new_instance = type(self).__new__(type(self))
        for k, v in self.items():
            dict.__setitem__(new_instance, k, v)
        new_instance.callback = self.callback
        return new_instance

    def update(self, other):
        super().update(other)
        if self.callback is not None:
            self.callback(self)

    def __delitem__(self, key):
        super().__delitem__(key)
        if self.callback is not None:
            self.callback(self)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self.callback is not None:
            self.callback(self)