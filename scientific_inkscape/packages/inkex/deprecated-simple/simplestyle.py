# coding=utf-8
# COPYRIGHT
"""DOCSTRING"""

import inkex
from inkex.colors import SVG_COLOR as svgcolors
from inkex.deprecated import deprecate


@deprecate
def parseStyle(s):
    """dict(inkex.Style.parse_str(s))"""
    return dict(inkex.Style.parse_str(s))


@deprecate
def formatStyle(a):
    """str(inkex.Style(a))"""
    return str(inkex.Style(a))


@deprecate
def isColor(c):
    """inkex.colors.is_color(c)"""
    return inkex.colors.is_color(c)


@deprecate
def parseColor(c):
    """inkex.Color(c).to_rgb()"""
    return tuple(inkex.Color(c).to_rgb())


@deprecate
def formatColoria(a):
    """str(inkex.Color(a))"""
    return str(inkex.Color(a))


@deprecate
def formatColorfa(a):
    """str(inkex.Color(a))"""
    return str(inkex.Color(a))


@deprecate
def formatColor3i(r, g, b):
    """str(inkex.Color((r, g, b)))"""
    return str(inkex.Color((r, g, b)))


@deprecate
def formatColor3f(r, g, b):
    """str(inkex.Color((r, g, b)))"""
    return str(inkex.Color((r, g, b)))
