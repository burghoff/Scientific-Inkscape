#!/usr/bin/env python
# coding:utf-8
# Authors:  mozman <me@mozman.at>, Florian Festi
# Purpose: svgparser using re module
# Created: 16.10.2010
# Copyright (c) 2010, Manfred Moitzi & 2020, Florian Festi
# License: MIT License

__all__ = ["is_valid_transferlist", "is_valid_pathdata", "is_valid_animation_timing"]

import re

event_names = [
    "focusin",
    "focusout",
    "activate",
    "click",
    "mousedown",
    "mouseup",
    "mouseover",
    "mousemove",
    "mouseout",
    "DOMSubtreeModified",
    "DOMNodeInserted",
    "DOMNodeRemoved",
    "DOMNodeRemovedFromDocument",
    "DOMNodeInsertedtoDocument",
    "DOMAttrModified",
    "DOMCharacterDataModified",
    "SVGLoad",
    "SVGUnload",
    "SVGAbort",
    "SVGError",
    "SVGResize",
    "SVGScroll",
    "SVGZoom",
    "beginEvent",
    "endEvent",
    "repeatEvent",
]

c = r"\s*[, ]\s*"
s = r"\s*[; ]\s*"
integer_constant = r"\d+"
exponent = r"([eE][+-]?\d+)"
nonnegative_number = rf"(\d+\.?\d*|\.\d+){exponent}?"
number = r"[+-]?" + nonnegative_number
flag = r"[01]"

comma_delimited_coordinates = rf"\s*{number}({c}{number})*\s*"
two_comma_delimited_numbers = rf"\s*{number}({c}{number}\s*)" "{1}"
four_comma_delimited_numbers = rf"\s*{number}\s*({c}{number}\s*)" "{3}"
six_comma_delimited_numbers = rf"\s*{number}\s*({c}{number}\s*)" "{5}"
comma_delimited_coordinate_pairs = (
    rf"{two_comma_delimited_numbers}({c}{two_comma_delimited_numbers})*"
)


def is_valid(regex):
    reg = re.compile(regex)

    def f(term):
        return bool(reg.fullmatch(term))

    return f


def build_transferlist_parser():
    matrix = rf"matrix\s*\(\s*{six_comma_delimited_numbers}\s*\)"
    translate = rf"translate\s*\(\s*{number}({c}{number})?\s*\)"
    scale = rf"scale\s*\(\s*{number}({c}{number})?\s*\)"
    rotate = rf"rotate\s*\(\s*{number}({c}{number}{c}{number})?\s*\)"
    skewX = rf"skewX\s*\(\s*{number}\s*\)"
    skewY = rf"skewY\s*\(\s*{number}\s*\)"

    tl_re = "|".join(
        (rf"(\s*{cmd}\s*)" for cmd in (matrix, translate, scale, rotate, skewX, skewY))
    )
    return rf"({tl_re})({c}({tl_re}))*"


is_valid_transferlist = is_valid(build_transferlist_parser())


def build_pathdata_parser():
    moveto = rf"[mM]\s*{comma_delimited_coordinate_pairs}"
    lineto = rf"[lL]\s*{comma_delimited_coordinate_pairs}"
    horizontal_lineto = rf"[hH]\s*{comma_delimited_coordinates}"
    vertical_lineto = rf"[vV]\s*{comma_delimited_coordinates}"
    curveto = (
        rf"[cC]\s*({six_comma_delimited_numbers})({c}{six_comma_delimited_numbers})*"
    )
    smooth_curveto = (
        rf"[sS]{four_comma_delimited_numbers}({c}{four_comma_delimited_numbers})*"
    )
    quadratic_bezier_curveto = (
        rf"[qQ]{four_comma_delimited_numbers}({c}{four_comma_delimited_numbers})*"
    )
    smooth_quadratic_bezier_curveto = rf"[tT]\s*{comma_delimited_coordinate_pairs}"

    elliptical_arc_argument = rf"{c}".join(
        (
            rf"{nonnegative_number}",
            rf"{nonnegative_number}",
            rf"{number}",
            rf"{flag}",
            rf"{flag}",
            rf"{number}",
            rf"{number}",
        )
    )
    elliptical_arc_argument = r"\s*" + elliptical_arc_argument + r"\s*"
    elliptical_arc = rf"[aA]({elliptical_arc_argument})({c}{elliptical_arc_argument})*"

    drawto_command = "|".join(
        (
            rf"(\s*{cmd}\s*)"
            for cmd in (
                moveto,
                lineto,
                horizontal_lineto,
                vertical_lineto,
                "[zZ]",
                curveto,
                smooth_curveto,
                quadratic_bezier_curveto,
                smooth_quadratic_bezier_curveto,
                elliptical_arc,
            )
        )
    )

    return f"{moveto}({drawto_command})*"


is_valid_pathdata = is_valid(build_pathdata_parser())

digit2 = r"\d{2}"
digit4 = r"\d{4}"
seconds = rf"\d+(\.\d+)?"
seconds2 = rf"{digit2}(\.\d+)?"
metric = "(h|min|s|ms)"


def clock_val_re():
    timecount_val = rf"{seconds}\s*({metric})?"
    clock_val = rf"{digit2}:({digit2}:)?{seconds2}"
    return rf"({timecount_val}|{clock_val})"


def wall_clock_val_re():
    hhmmss = rf"{digit2}:{digit2}(:{seconds2})?"
    walltime = rf"{hhmmss}(Z|[+-]?{digit2}:{digit2})?"
    date = rf"{digit4}-{digit2}-{digit2}"
    datetime = rf"{date}(T{walltime})?"
    return "(" + "|".join((walltime, datetime)) + ")"


def build_animation_timing_parser():
    clock_val = clock_val_re()
    wallclock_val = wall_clock_val_re()

    event_ref = "(" + "|".join(event_names) + ")"
    id_value = "#?[-_a-zA-Z0-9]+"

    wallclock_sync_value = rf"wallclock\(\s*{wallclock_val}\s*\)"
    accesskey_value = rf"accessKey\(\s*[a-zA-Z]\s*\)\s*([+-]?{clock_val})?"
    repeat_value = rf"({id_value}\.)?repeat\s*\(\s*\d+\s*\)\s*([+-?]{clock_val})?"
    event_value = rf"({id_value}\.)?{event_ref}([+-]?{clock_val})?"
    offset_value = rf"[-+]?{clock_val}"
    syncbase_value = rf"{id_value}\.(begin|end)({offset_value})?"
    begin_value = (
        "("
        + "|".join(
            (
                f"({reg})"
                for reg in (
                    offset_value,
                    syncbase_value,
                    event_value,
                    repeat_value,
                    accesskey_value,
                    wallclock_sync_value,
                    "indefinite",
                )
            )
        )
        + ")"
    )
    return rf"{begin_value}({s}{begin_value})*"


is_valid_animation_timing = is_valid(build_animation_timing_parser())
