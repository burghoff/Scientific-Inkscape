# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 Martin Owens <doctormo@gmail.com>
#                    Sergei Izmailov <sergei.a.izmailov@gmail.com>
#                    Thomas Holder <thomas.holder@schrodinger.com>
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
# pylint: disable=arguments-differ
"""
Provide extra utility to each svg element type specific to its type.

This is useful for having a common interface for each element which can
give path, transform, and property access easily.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Tuple, Optional, overload, TypeVar, List
from lxml import etree
import re

from ..interfaces.IElement import IBaseElement, ISVGDocumentElement

from ..base import SvgOutputMixin
from ..paths import Path
from ..styles import Style, Classes
from ..transforms import Transform, BoundingBox
from ..utils import FragmentError
from ..units import convert_unit, render_unit, parse_unit
from ._utils import ChildToProperty, NSS, addNS, removeNS, splitNS
from ..properties import BaseStyleValue, ShorthandValue, all_properties
from ._selected import ElementList
from ._parser import NodeBasedLookup, SVG_PARSER

T = TypeVar("T", bound="BaseElement")  # pylint: disable=invalid-name


class BaseElement(IBaseElement):
    """Provide automatic namespaces to all calls"""

    # pylint: disable=too-many-public-methods

    def __init_subclass__(cls):
        if cls.tag_name:
            NodeBasedLookup.register_class(cls)

    @classmethod
    def is_class_element(  # pylint: disable=unused-argument
        cls, elem: etree.Element
    ) -> bool:
        """Hook to do more restrictive check in addition to (ns,tag) match

        .. versionadded:: 1.2
            The function has been made public."""
        return True

    tag_name = ""

    @property
    def TAG(self):  # pylint: disable=invalid-name
        """Return the tag_name without NS"""
        if not self.tag_name:
            return removeNS(super().tag)[-1]
        return removeNS(self.tag_name)[-1]

    @classmethod
    def new(cls, *children, **attrs):
        """Create a new element, converting attrs values to strings."""
        obj = cls(*children)
        obj.update(**attrs)
        return obj

    NAMESPACE = property(lambda self: splitNS(self.tag_name)[0])
    """Get namespace of element"""

    PARSER = SVG_PARSER
    """A reference to the :attr:`inkex.elements._parser.SVG_PARSER`"""
    WRAPPED_ATTRS = (
        # (prop_name, [optional: attr_name], cls)
        ("transform", Transform),
        ("style", Style),
        ("classes", "class", Classes),
    )  # type: Tuple[Tuple[Any, ...], ...]
    """A list of attributes that are automatically converted to objects."""

    # We do this because python2 and python3 have different ways
    # of combining two dictionaries that are incompatible.
    # This allows us to update these with inheritance.
    @property
    def wrapped_attrs(self):
        """Map attributes to property name and wrapper class"""
        return {row[-2]: (row[0], row[-1]) for row in self.WRAPPED_ATTRS}

    @property
    def wrapped_props(self):
        """Map properties to attribute name and wrapper class"""
        return {row[0]: (row[-2], row[-1]) for row in self.WRAPPED_ATTRS}

    typename = property(lambda self: type(self).__name__)
    """Type name of the element"""
    xml_path = property(lambda self: self.getroottree().getpath(self))
    """XPath representation of the element in its tree
    
    .. versionadded:: 1.1"""
    desc = ChildToProperty("svg:desc", prepend=True)
    """The element's long-form description (for accessibility purposes)
    
    .. versionadded:: 1.1"""
    title = ChildToProperty("svg:title", prepend=True)
    """The element's short-form description (for accessibility purposes)
    
    .. versionadded:: 1.1"""

    def __getattr__(self, name):
        """Get the attribute, but load it if it is not available yet"""
        if name in self.wrapped_props:
            (attr, cls) = self.wrapped_props[name]

            # The reason we do this here and not in _init is because lxml
            # is inconsistant about when elements are initialised.
            # So we make this a lazy property.
            def _set_attr(new_item):
                if new_item:
                    self.set(attr, str(new_item))
                else:
                    self.attrib.pop(attr, None)  # pylint: disable=no-member

            # pylint: disable=no-member
            value = cls(self.attrib.get(attr, None), callback=_set_attr)
            if name == "style":
                value.element = self
            setattr(self, name, value)
            return value
        raise AttributeError(f"Can't find attribute {self.typename}.{name}")

    def __setattr__(self, name, value):
        """Set the attribute, update it if needed"""
        if name in self.wrapped_props:
            (attr, cls) = self.wrapped_props[name]
            # Don't call self.set or self.get (infinate loop)
            if value:
                if not isinstance(value, cls):
                    value = cls(value)
                self.attrib[attr] = str(value)
            else:
                self.attrib.pop(attr, None)  # pylint: disable=no-member
        else:
            super().__setattr__(name, value)

    def get(self, attr, default=None):
        """Get element attribute named, with addNS support."""
        if attr in self.wrapped_attrs:
            (prop, _) = self.wrapped_attrs[attr]
            value = getattr(self, prop, None)
            # We check the boolean nature of the value, because empty
            # transformations and style attributes are equiv to not-existing
            ret = str(value) if value else (default or None)
            return ret
        return super().get(addNS(attr), default)

    def set(self, attr, value):
        """Set element attribute named, with addNS support"""
        if attr in self.wrapped_attrs:
            # Always keep the local wrapped class up to date.
            (prop, cls) = self.wrapped_attrs[attr]
            setattr(self, prop, cls(value))
            value = getattr(self, prop)
            if not value:
                return
        if value is None:
            self.attrib.pop(addNS(attr), None)  # pylint: disable=no-member
        else:
            value = str(value)
            super().set(addNS(attr), value)

    def update(self, **kwargs):
        """
        Update element attributes using keyword arguments

        Note: double underscore is used as namespace separator,
        i.e. "namespace__attr" argument name will be treated as "namespace:attr"

        :param kwargs: dict with name=value pairs
        :return: self
        """
        for name, value in kwargs.items():
            self.set(name, value)
        return self

    def pop(self, attr, default=None):
        """Delete/remove the element attribute named, with addNS support."""
        if attr in self.wrapped_attrs:
            # Always keep the local wrapped class up to date.
            (prop, cls) = self.wrapped_attrs[attr]
            value = getattr(self, prop)
            setattr(self, prop, cls(None))
            return value
        return self.attrib.pop(addNS(attr), default)  # pylint: disable=no-member

    @overload
    def add(
        self, child1: BaseElement, child2: BaseElement, *children: BaseElement
    ) -> Tuple[BaseElement]:
        ...

    @overload
    def add(self, child: T) -> T:
        ...

    def add(self, *children):
        """
        Like append, but will do multiple children and will return
        children or only child
        """
        for child in children:
            self.append(child)
        return children if len(children) != 1 else children[0]

    def tostring(self):
        """Return this element as it would appear in an svg document"""
        # This kind of hack is pure maddness, but etree provides very little
        # in the way of fragment printing, prefering to always output valid xml

        svg = SvgOutputMixin.get_template(width=0, height=0).getroot()
        svg.append(self.copy())
        return svg.tostring().split(b">\n    ", 1)[-1][:-6]

    def set_random_id(
        self,
        prefix: Optional[str] = None,
        size: Optional[int] = None,
        backlinks: bool = False,
        blacklist: Optional[List[str]] = None,
    ):
        """Sets the id attribute if it is not already set.

        The id consists of a prefix and an appended random integer of length size.
        Args:
            prefix (str, optional): the prefix of the new ID. Defaults to the tag name.
            size (Optional[int], optional): number of digits of the second part of the
                id. If None, the length is chosen based on the amount of existing
                objects. Defaults to None.

                .. versionchanged:: 1.2
                    The default of this value has been changed from 4 to None.
            backlinks (bool, optional): Whether to update the links in existing objects
                that reference this element. Defaults to False.
            blacklist (List[str], optional): An additional list of ids that are not
                allowed to be used. This is useful when bulk inserting objects.
                Defaults to None.

                .. versionadded:: 1.2
        """
        prefix = str(self) if prefix is None else prefix
        self.set_id(
            self.root.get_unique_id(prefix, size=size, blacklist=blacklist),
            backlinks=backlinks,
        )

    def set_random_ids(
        self,
        prefix: Optional[str] = None,
        levels: int = -1,
        backlinks: bool = False,
        blacklist: Optional[List[str]] = None,
    ):
        """Same as set_random_id, but will apply also to children

        The id consists of a prefix and an appended random integer of length size.
        Args:
            prefix (str, optional): the prefix of the new ID. Defaults to the tag name.
            levels (int, optional): the depth of the tree traversion, if negative, no
                limit is imposed. Defaults to -1.
            backlinks (bool, optional): Whether to update the links in existing objects
                that reference this element. Defaults to False.
            blacklist (List[str], optional): An additional list of ids that are not
                allowed to be used. This is useful when bulk inserting objects.
                Defaults to None.

                .. versionadded:: 1.2
        """
        self.set_random_id(prefix=prefix, backlinks=backlinks, blacklist=blacklist)
        if levels != 0:
            for child in self:
                if hasattr(child, "set_random_ids"):
                    child.set_random_ids(
                        prefix=prefix, levels=levels - 1, backlinks=backlinks
                    )

    eid = property(lambda self: self.get_id())
    """Property to access the element's id; will set a new unique id if not set."""

    def get_id(self, as_url=0) -> str:
        """Get the id for the element, will set a new unique id if not set.

        as_url - If set to 1, returns #{id} as a string
                 If set to 2, returns url(#{id}) as a string

        Args:
            as_url (int, optional):
                - If set to 1, returns #{id} as a string
                - If set to 2, returns url(#{id}) as a string.

                Defaults to 0.

                .. versionadded:: 1.1

        Returns:
            str: formatted id
        """
        if "id" not in self.attrib:
            self.set_random_id(self.TAG)
        eid = self.get("id")
        if as_url > 0:
            eid = "#" + eid
        if as_url > 1:
            eid = f"url({eid})"
        return eid

    def set_id(self, new_id, backlinks=False):
        """Set the id and update backlinks to xlink and style urls if needed"""
        old_id = self.get("id", None)
        self.set("id", new_id)
        if backlinks and old_id:
            for elem in self.root.getElementsByHref(old_id):
                elem.href = self
            for attr in ["clip-path", "mask"]:
                for elem in self.root.getElementsByHref(old_id, attribute=attr):
                    elem.set(attr, self.get_id(2))
            for elem in self.root.getElementsByStyleUrl(old_id):
                elem.style.update_urls(old_id, new_id)

    @property
    def root(self):
        """Get the root document element from any element descendent"""
        root, parent = self, self
        while parent is not None:
            root, parent = parent, parent.getparent()

        if not isinstance(root, ISVGDocumentElement):
            raise FragmentError("Element fragment does not have a document root!")
        return root

    def get_or_create(self, xpath, nodeclass=None, prepend=False):
        """Get or create the given xpath, pre/append new node if not found.

        .. versionchanged:: 1.1
            The ``nodeclass`` attribute is optional; if not given, it is looked up
            using :func:`~inkex.elements._parser.NodeBasedLookup.find_class`"""
        node = self.findone(xpath)
        if node is None:
            if nodeclass is None:
                nodeclass = NodeBasedLookup.find_class(xpath)
            node = nodeclass()
            if prepend:
                self.insert(0, node)
            else:
                self.append(node)
        return node

    def descendants(self):
        """Walks the element tree and yields all elements, parent first

        .. versionchanged:: 1.1
            The ``*types`` attribute was removed

        """

        return ElementList(
            self.root,
            [
                element
                for element in self.iter()
                if isinstance(element, (BaseElement, str))
            ],
        )

    def ancestors(self, elem=None, stop_at=()):
        """
        Walk the parents and yield all the ancestor elements, parent first

        Args:
            elem (BaseElement, optional): If provided, it will stop at the last common
                ancestor. Defaults to None.

                .. versionadded:: 1.1

            stop_at (tuple, optional): If provided, it will stop at the first parent
                that is in this list. Defaults to ().

                .. versionadded:: 1.1

        Returns:
            ElementList: list of ancestors
        """

        return ElementList(self.root, self._ancestors(elem=elem, stop_at=stop_at))

    def _ancestors(self, elem, stop_at):
        if isinstance(elem, BaseElement):
            stop_at = list(elem.ancestors())
        for parent in self.iterancestors():
            yield parent
            if parent in stop_at:
                break

    def backlinks(self, *types):
        """Get elements which link back to this element, like ancestors but via
        xlinks"""
        if not types or isinstance(self, types):
            yield self
        my_id = self.get("id")
        if my_id is not None:
            elems = list(self.root.getElementsByHref(my_id)) + list(
                self.root.getElementsByStyleUrl(my_id)
            )
            for elem in elems:
                if hasattr(elem, "backlinks"):
                    for child in elem.backlinks(*types):
                        yield child

    def xpath(self, pattern, namespaces=NSS):  # pylint: disable=dangerous-default-value
        """Wrap xpath call and add svg namespaces"""
        return super().xpath(pattern, namespaces=namespaces)

    def findall(
        self, pattern, namespaces=NSS
    ):  # pylint: disable=dangerous-default-value
        """Wrap findall call and add svg namespaces"""
        return super().findall(pattern, namespaces=namespaces)

    def findone(self, xpath):
        """Gets a single element from the given xpath or returns None"""
        el_list = self.xpath(xpath)
        return el_list[0] if el_list else None

    def delete(self):
        """Delete this node from it's parent node"""
        if self.getparent() is not None:
            self.getparent().remove(self)

    def remove_all(self, *types):
        """Remove all children or child types

        .. versionadded:: 1.1"""
        types = tuple(NodeBasedLookup.find_class(t) for t in types)
        for child in self:
            if not types or isinstance(child, types):
                self.remove(child)

    def replace_with(self, elem):
        """Replace this element with the given element"""
        self.addnext(elem)
        if not elem.get("id") and self.get("id"):
            elem.set("id", self.get("id"))
        if not elem.label and self.label:
            elem.label = self.label
        self.delete()
        return elem

    def copy(self):
        """Make a copy of the element and return it"""
        elem = deepcopy(self)
        elem.set("id", None)
        return elem

    def duplicate(self):
        """Like copy(), but the copy stays in the tree and sets a random id on the
        duplicate.

        .. versionchanged:: 1.2
            A random id is also set on all the duplicate's descendants"""
        elem = self.copy()
        self.addnext(elem)
        elem.set_random_ids()
        return elem

    def __str__(self):
        # We would do more here, but lxml is VERY unpleseant when it comes to
        # namespaces, basically over printing details and providing no
        # supression mechanisms to turn off xml's over engineering.
        return str(self.tag).split("}", maxsplit=1)[-1]

    @property
    def href(self):
        """Returns the referred-to element if available

        .. versionchanged:: 1.1
            A setter for href was added."""
        ref = self.get("href") or self.get("xlink:href")
        if not ref:
            return None
        return self.root.getElementById(ref.strip("#"))

    @href.setter
    def href(self, elem):
        """Set the href object"""
        if isinstance(elem, BaseElement):
            elem = elem.get_id()
        if self.get("href"):
            self.set("href", "#" + elem)
        else:
            self.set("xlink:href", "#" + elem)

    @property
    def label(self):
        """Returns the inkscape label"""
        return self.get("inkscape:label", None)

    @label.setter
    def label(self, value):
        """Sets the inkscape label"""
        self.set("inkscape:label", str(value))

    def is_sensitive(self):
        """Return true if this element is sensitive in inkscape

        .. versionadded:: 1.1"""
        return self.get("sodipodi:insensitive", None) != "true"

    def set_sensitive(self, sensitive=True):
        """Set the sensitivity of the element/layer

        .. versionadded:: 1.1"""
        # Sensitive requires None instead of 'false'
        self.set("sodipodi:insensitive", ["true", None][sensitive])

    @property
    def unit(self):
        """Return the unit being used by the owning document, cached

        .. versionadded:: 1.1"""
        try:
            return self.root.unit
        except FragmentError:
            return "px"  # Don't cache.

    @staticmethod
    def to_dimensional(value, to_unit="px"):
        """Convert a value given in user units (px) the given unit type

        .. versionadded:: 1.2"""
        return convert_unit(value, to_unit)

    @staticmethod
    def to_dimensionless(value):
        """Convert a length value into user units (px)

        .. versionadded:: 1.2"""
        return convert_unit(value, "px")

    def uutounit(self, value, to_unit="px"):
        """Convert a unit value to a given unit. If the value does not have a unit,
        "Document" units are assumed. "Document units" are an Inkscape-specific concept.
        For most use-cases, :func:`to_dimensional` is more appropriate.

        .. versionadded:: 1.1"""
        return convert_unit(value, to_unit, default=self.unit)

    def unittouu(self, value):
        """Convert a unit value into document units. "Document unit" is an
        Inkscape-specific concept. For most use-cases, :func:`viewport_to_unit` (when
        the size of an object given in viewport units is needed) or
        :func:`to_dimensionless` (when the equivalent value without unit is needed) is
        more appropriate.

        .. versionadded:: 1.1"""
        return convert_unit(value, self.unit)

    def unit_to_viewport(self, value, unit="px"):
        """Converts a length value to viewport units, as defined by the width/height
        element on the root (i.e. applies the equivalent transform of the viewport)

        .. versionadded:: 1.2"""
        return self.to_dimensional(
            self.to_dimensionless(value) * self.root.equivalent_transform_scale, unit
        )

    def viewport_to_unit(self, value, unit="px"):
        """Converts a length given on the viewport to the specified unit in the user
        coordinate system

        .. versionadded:: 1.2"""
        return self.to_dimensional(
            self.to_dimensionless(value) / self.root.equivalent_transform_scale, unit
        )

    def add_unit(self, value):
        """Add document unit when no unit is specified in the string.

        .. versionadded:: 1.1"""
        return render_unit(value, self.unit)

    def cascaded_style(self):
        """Returns the cascaded style of an element (all rules that apply the element
        itself), based on the stylesheets, the presentation attributes and the inline
        style using the respective specificity of the style.

        see https://www.w3.org/TR/CSS22/cascade.html#cascading-order

        .. versionadded:: 1.2

        Returns:
            Style: the cascaded style

        """
        return Style.cascaded_style(self)

    def specified_style(self):
        """Returns the specified style of an element, i.e. the cascaded style +
        inheritance, see https://www.w3.org/TR/CSS22/cascade.html#specified-value.

        Returns:
            Style: the specified style

        .. versionadded:: 1.2
        """
        return Style.specified_style(self)

    def presentation_style(self):
        """Return presentation attributes of an element as style

        .. versionadded:: 1.2"""
        style = Style()
        for key in self.keys():
            if (
                key in all_properties
                and all_properties[key][2]
                and not issubclass(all_properties[key][0], ShorthandValue)
            ):
                # Shorthands cannot be set by presentation attributes
                result = BaseStyleValue.factory_errorhandled(
                    key=key, value=self.attrib[key]
                )
                if result is not None:  # parsing error
                    style[key] = result[1]
        return style

    def composed_transform(self, other=None):
        """Calculate every transform down to the other element
        if none specified the transform is to the root document element
        """
        parent = self.getparent()
        if parent is not other and isinstance(parent, BaseElement):
            return parent.composed_transform(other) @ self.transform
        return self.transform


NodeBasedLookup.default = BaseElement


class ShapeElement(BaseElement):
    """Elements which have a visible representation on the canvas"""

    @property
    def path(self):
        """Gets the outline or path of the element, this may be a simple bounding box"""
        return Path(self.get_path())

    @path.setter
    def path(self, path):
        self.set_path(path)

    @property
    def clip(self):
        """Gets the clip path element (if any). May be set through CSS.

        .. versionadded:: 1.1"""
        ref = self.get("clip-path")
        if not ref:
            return self.specified_style()("clip-path")
        return self.root.getElementById(ref)

    @clip.setter
    def clip(self, elem):
        self.set("clip-path", elem.get_id(as_url=2))

    def get_path(self) -> Path:
        """Generate a path for this object which can inform the bounding box"""
        raise NotImplementedError(
            f"Path should be provided by svg elem {self.typename}."
        )

    def set_path(self, path):
        """Set the path for this object (if possible)"""
        raise AttributeError(
            f"Path can not be set on this element: {self.typename} <- {path}."
        )

    def to_path_element(self):
        """Replace this element with a path element"""
        from ._polygons import PathElement

        elem = PathElement()
        elem.path = self.path
        elem.style = self.effective_style()
        elem.transform = self.transform
        return elem

    def effective_style(self):
        """Without parent styles, what is the effective style is"""
        return self.style

    def bounding_box(self, transform=None):
        # type: (Optional[Transform]) -> Optional[BoundingBox]
        """BoundingBox of the shape

        .. versionchanged:: 1.1
            result adjusted for element's clip path if applicable."""
        shape_box = self.shape_box(transform)
        clip = self.clip
        if clip is None or shape_box is None:
            return shape_box
        return shape_box & clip.bounding_box(Transform(transform) @ self.transform)

    def shape_box(self, transform=None):
        # type: (Optional[Transform]) -> Optional[BoundingBox]
        """BoundingBox of the unclipped shape

        .. versionadded:: 1.1
            Previous :func:`bounding_box` function, returning the bounding box
            without computing the effect of a possible clip."""
        path = self.path.to_absolute()
        if transform is True:
            path = path.transform(self.composed_transform())
        else:
            path = path.transform(self.transform)
            if transform:  # apply extra transformation
                path = path.transform(transform)
        return path.bounding_box()

    def is_visible(self):
        """Returns false if this object is invisible

        .. versionchanged:: 1.3
            rely on cascaded_style() to include CSS and presentation attributes
            include `visibility` attribute with check for inherit
            include ancestors

        .. versionadded:: 1.1"""
        return self._is_visible()

    def _is_visible(self, inherit_visibility=True):
        # iterate over self and ancestors
        for element in [self] + list(self.ancestors()):
            get_style = element.cascaded_style().get
            # case display:none
            if get_style("display", "inline") == "none":
                return False
            # case opacity:0
            if not float(get_style("opacity", 1.0)):
                return False
            # only check if childs visibility is inherited
            if inherit_visibility:
                # case visibility:hidden
                if get_style("visibility", "inherit") in (
                    "hidden",
                    "collapse",
                ):
                    return False
                # case visibility: not inherit
                elif get_style("visibility", "inherit") != "inherit":
                    inherit_visibility = False

        return True

    def get_line_height_uu(self):
        """Returns the specified value of line-height, in user units

        .. versionadded:: 1.1"""
        style = self.specified_style()
        font_size = style("font-size")  # already in uu
        line_height = style("line-height")
        parsed = parse_unit(line_height)
        if parsed is None:
            return font_size * 1.2
        if parsed[1] == "%":
            return font_size * parsed[0] * 0.01
        return self.to_dimensionless(line_height)


class ViewboxMixin:
    """Mixin for elements with viewboxes, such as <svg>, <marker>"""

    def parse_viewbox(self, vbox: Optional[str]) -> Optional[List[float]]:
        """Parses a viewbox. If an error occurs during parsing,
        (0, 0, 0, 0) is returned. If the viewbox is None, None is returned.

        .. versionadded:: 1.3"""
        if vbox is not None and isinstance(vbox, str):
            try:
                result = [float(unit) for unit in re.split(r",\s*|\s+", vbox)]
            except ValueError:
                result = []
            if len(result) != 4:
                result = [0, 0, 0, 0]
            return result
        return None
