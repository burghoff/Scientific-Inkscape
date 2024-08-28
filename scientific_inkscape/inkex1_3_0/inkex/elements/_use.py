# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 Martin Owens <doctormo@gmail.com>
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
"""
Interface for the Use and Symbol elements
"""

from ..transforms import Transform

from ._groups import Group, GroupBase
from ._base import ShapeElement


class Symbol(GroupBase):
    """SVG symbol element"""

    tag_name = "symbol"


class Use(ShapeElement):
    """A 'use' element that links to another in the document"""

    tag_name = "use"

    @classmethod
    def new(cls, elem, x, y, **attrs):  # pylint: disable=arguments-differ
        ret = super().new(x=x, y=y, **attrs)
        ret.href = elem
        return ret

    def get_path(self):
        """Returns the path of the cloned href plus any transformation

        .. versionchanged:: 1.3
            include transform of the referenced element
        """
        path = self.href.path
        path = path.transform(self.href.transform)
        return path

    def effective_style(self):
        """Href's style plus this object's own styles"""
        style = self.href.effective_style()
        style.update(self.style)
        return style

    def unlink(self):
        """Unlink this clone, replacing it with a copy of the original"""
        copy = self.href.copy()
        if isinstance(copy, Symbol):
            group = Group(**copy.attrib)
            group.extend(copy)
            copy = group
        copy.transform = self.transform @ copy.transform
        copy.transform.add_translate(
            self.to_dimensionless(self.get("x", 0)),
            self.to_dimensionless(self.get("y", 0)),
        )
        copy.style = self.style + copy.style
        # Preserve the id of the clone to not break links that link the <use>
        # As we replace exactly one element by exactly one, this should be safe.
        old_id = self.get_id()
        self.replace_with(copy)
        copy.set_random_ids()
        copy.set_id(old_id)
        return copy

    def shape_box(self, transform=None):
        """BoundingBox of the unclipped shape

        .. versionadded:: 1.1"""
        effective_transform = Transform(transform) @ self.transform
        return self.href.bounding_box(effective_transform)
