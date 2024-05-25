# -*- coding: utf-8 -*-
#
# Copyright (c) 2021 Martin Owens <doctormo@gmail.com>
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
Useful utilities specifically for elements (that aren't base classes)

.. versionadded:: 1.1
    Most of the methods in this module were moved from inkex.utils.
"""

from collections import defaultdict
import re

# a dictionary of all of the xmlns prefixes in a standard inkscape doc
NSS = {
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
    "cc": "http://creativecommons.org/ns#",
    "ccOLD": "http://web.resource.org/cc/",
    "svg": "http://www.w3.org/2000/svg",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    "xlink": "http://www.w3.org/1999/xlink",
    "xml": "http://www.w3.org/XML/1998/namespace",
}
SSN = dict((b, a) for (a, b) in NSS.items())


def registerNS(prefix, url):
    """Register the given prefix as a namespace url."""
    NSS[prefix] = url
    SSN[url] = prefix


def addNS(tag, ns=None, namespaces=NSS):  # pylint: disable=invalid-name
    """Add a known namespace to a name for use with lxml"""
    if tag.startswith("{") and ns:
        _, tag = removeNS(tag)
    if not tag.startswith("{"):
        tag = tag.replace("__", ":")
        if ":" in tag:
            (ns, tag) = tag.rsplit(":", 1)
        ns = namespaces.get(ns, None) or ns
        if ns is not None:
            return f"{{{ns}}}{tag}"
    return tag


def removeNS(
    name, reverse_namespaces=SSN, default="svg"
):  # pylint: disable=invalid-name
    """The reverse of addNS, finds any namespace and returns tuple (ns, tag)"""
    if name[0] == "{":
        (url, tag) = name[1:].split("}", 1)
        return reverse_namespaces.get(url, default), tag
    if ":" in name:
        return name.rsplit(":", 1)
    return default, name


def splitNS(name, namespaces=NSS):  # pylint: disable=invalid-name
    """Like removeNS, but returns a url instead of a prefix"""
    (prefix, tag) = removeNS(name)
    return (namespaces[prefix], tag)


def natural_sort_key(key, _nsre=re.compile("([0-9]+)")):
    """Helper for a natural sort, see
    https://stackoverflow.com/a/16090640/3298143"""
    return [int(text) if text.isdigit() else text.lower() for text in _nsre.split(key)]


class ChildToProperty(property):
    """Use when you have a singleton child element who's text
    content is the canonical value for the property"""

    def __init__(self, tag, prepend=False):
        super().__init__()
        self.tag = tag
        self.prepend = prepend

    def __get__(self, obj, klass=None):
        elem = obj.findone(self.tag)
        return elem.text if elem is not None else None

    def __set__(self, obj, value):
        elem = obj.get_or_create(self.tag, prepend=self.prepend)
        elem.text = value

    def __delete__(self, obj):
        obj.remove_all(self.tag)

    @property
    def __doc__(self):
        return f"Get, set or delete the {self.tag} property."


class CloningVat:
    """
    When modifying defs, sometimes we want to know if every backlink would have
    needed changing, or it was just some of them.

    This tracks the def elements, their promises and creates clones if needed.
    """

    def __init__(self, svg):
        self.svg = svg
        self.tracks = defaultdict(set)
        self.set_ids = defaultdict(list)

    def track(self, elem, parent, set_id=None, **kwargs):
        """Track the element and connected parent"""
        elem_id = elem.get("id")
        parent_id = parent.get("id")
        self.tracks[elem_id].add(parent_id)
        self.set_ids[elem_id].append((set_id, kwargs))

    def process(self, process, types=(), make_clones=True, **kwargs):
        """
        Process each tracked item if the backlinks match the parents

        Optionally make clones, process the clone and set the new id.
        """
        for elem_id in list(self.tracks):
            parents = self.tracks[elem_id]
            elem = self.svg.getElementById(elem_id)
            backlinks = {blk.get("id") for blk in elem.backlinks(*types)}
            if backlinks == parents:
                # No need to clone, we're processing on-behalf of all parents
                process(elem, **kwargs)
            elif make_clones:
                clone = elem.copy()
                elem.getparent().append(clone)
                clone.set_random_id()
                for update, upkw in self.set_ids.get(elem_id, ()):
                    update(elem.get("id"), clone.get("id"), **upkw)
                process(clone, **kwargs)
