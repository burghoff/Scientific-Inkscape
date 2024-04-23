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
        style = (
            ((k.replace("_", "-"), v) for k, v in kw.items())
            if style is None
            else style
        )
        if isinstance(style, str):
            style = self.parse_str(style)
        # Order raw dictionaries so tests can be made reliable
        # if isinstance(style, dict) and not isinstance(style, inkex.OrderedDict):
        #     style = [(name, style[name]) for name in sorted(style)]
        # Should accept dict, Style, parsed string, list etc.
        super().__init__(style)

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
        return self.to_str()

    def to_str(self, sep=";"):
        """Convert to string using a custom delimiter"""
        # return sep.join(["{0}:{1}".format(*seg) for seg in self.items()])
        return sep.join(
            [f"{key}:{value}" for key, value in self.items()]
        )  # about 40% faster

    def __hash__(self):
        return hash(tuple(self.items()))
        # return hash(self.to_str())

    def __add__(self, other):
        """Add two styles together to get a third, composing them"""
        ret = self.copy()
        if not (isinstance(other, Style0)):
            other = Style0(other)
        ret.update(other)
        return ret

    # A shallow copy that does not call __init__
    def copy(self):
        new_instance = type(self).__new__(type(self))
        for k, v in self.items():
            dict.__setitem__(new_instance, k, v)
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

    def __eq__(self, other):
        """Not equals, prefer to overload 'in' but that doesn't seem possible"""
        if not isinstance(other, Style0):
            other = Style0(other)
        return dict.__eq__(self,other)
        # Inkex uses dict comparison, not OrderedDict
        # for arg in set(self) | set(other):
        #     if self.get(arg, None) != other.get(arg, None):
        #         return False
        # return True

    __ne__ = lambda self, other: not self.__eq__(other)

    def update(self, other):
        if not (isinstance(other, Style0)):
            other = Style0(other)
        super().update(other)

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


# # We modify Style so that it has two versions: one without the callback
# # (Style0) and one with (Style0cb). That way, when no callback is needed,
# # we do not incur extra overhead by overloading __setitem__, __delitem__, etc.
# def __new__mod(cls, style=None, callback=None, **kw):
#     if cls != Style0 and issubclass(cls, Style0):  # Don't treat subclasses' arguments as callback
#         ret = inkex.OrderedDict.__new__(cls)
#         ret.callback = None
#     elif callback is not None:
#         ret = inkex.OrderedDict.__new__(Style0cb)
#         ret.__init__(style, callback, **kw)
#     else:
#         ret =  inkex.OrderedDict.__new__(cls)
#         ret.callback = None
#     return ret
# inkex.Style.__new__ = __new__mod


# def __init__mod(self, style=None, element=None, **kw):
#     self.element = element
#     # Either a string style or kwargs (with dashes as underscores).
#     style = ((k.replace("_", "-"), v) for k, v in kw.items()) if style is None else style
#     if isinstance(style, str):
#         style = self.parse_str(style)
#     # Order raw dictionaries so tests can be made reliable
#     if isinstance(style, dict) and not isinstance(style, inkex.OrderedDict):
#         style = [(name, style[name]) for name in sorted(style)]
#     # Should accept dict, Style, parsed string, list etc.
#     inkex.OrderedDict.__init__(self,style)
# inkex.Style.__init__ = __init__mod

# @staticmethod
# @lru_cache(maxsize=None)
# def parse_str_mod(style):
#     """Create a dictionary from the value of an inline style attribute"""
#     if style is None:
#         style = ""
#     ret = []
#     for directive in style.split(";"):
#         if ":" in directive:
#             (name, value) = directive.split(":", 1)
#             ret.append((name.strip().lower(), value.strip()))
#             # key = name.strip().lower(); value = value.strip();
#             # ret.append((key, inkex.properties.BaseStyleValue.factory(attr_name=key, value=value)))
#     return ret
# inkex.Style.parse_str = parse_str_mod

# def to_str_mod(self, sep=";"):
#     """Convert to string using a custom delimiter"""
#     # return sep.join(["{0}:{1}".format(*seg) for seg in self.items()])
#     return sep.join([f"{key}:{value}" for key, value in self.items()]) # about 40% faster
# inkex.Style.to_str = to_str_mod

# def __add__mod(self, other):
#     """Add two styles together to get a third, composing them"""
#     ret = self.copy()
#     if not (isinstance(other, Style0)):
#         other = Style0(other)
#     ret.update(other)
#     return ret
# inkex.Style.__add__ = __add__mod

# # A shallow copy that does not call __init__
# def copy_mod(self):
#     ret = type(self).__new__(type(self))
#     for k,v in self.items():
#         inkex.OrderedDict.__setitem__(ret,k,v)
#     ret.element = self.element
#     ret.callback = self.callback
#     return ret

# def get_importance_mod(self, key, default=False):
#     if key in self:
#         try:
#             return inkex.OrderedDict.__getitem__(self,key).important
#         except AttributeError:
#             pass
#     return default
# inkex.Style.get_importance = get_importance_mod

# def items_mod(self):
#     """The styles's parsed items

#     .. versionadded:: 1.2"""
#     for key, value in inkex.OrderedDict.items(self):
#         try:
#             yield key, value.value
#         except AttributeError:
#             yield key, value
# inkex.Style.items = items_mod


# def copy_mod(self):
#     ret = Style0({}, element=self.element)
#     # ret = type(self).__new__(type(self))
#     for key, value in inkex.OrderedDict.items(self):
#         ret[key] = value
#     return ret
# inkex.Style.copy = copy_mod
