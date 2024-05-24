#
# Copyright 2011-2022 Martin Owens <doctormo@geek-2.com>
#
# This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>
#
"""
Wraps the gtk treeview and iconview in something a little nicer.
"""

import logging

from typing import Tuple, Type, Optional
from gi.repository import Gtk, Gdk, GObject, GdkPixbuf, Pango

from .pixmap import PixmapManager, SizeFilter

GOBJ = GObject.TYPE_PYOBJECT


def default(item, attr, d=None):
    """Python logic to choose an attribute, call it if required and return"""
    if hasattr(item, attr):
        prop = getattr(item, attr)
        if callable(prop):
            prop = prop()
        return prop
    return d


def cmp(a, b):
    """Compare two objects"""
    return (a > b) - (a < b)


def item_property(name, d=None):
    def inside(item):
        return default(item, name, d)

    return inside


def label(obj):
    if isinstance(obj, tuple):
        return " or ".join([label(o) for o in obj])
    if not isinstance(obj, type):
        obj = type(obj)
    return obj.__name__


class BaseView:
    """Controls for tree and icon views, a base class"""

    widget_type: Optional[Type[Gtk.Widget]] = None

    def __init__(self, widget, liststore=None, **kwargs):
        if not isinstance(widget, self.widget_type):
            lbl1 = label(self.widget_type)
            lbl2 = label(widget)
            raise TypeError(f"Wrong widget type: Expected {lbl1} got {lbl2}")

        self.selected_signal = kwargs.get("selected", None)
        self._iids = []
        self._list = widget
        self.args = kwargs
        self.selected = None
        self._data = None
        self.no_dupes = True
        self._model = self.create_model(liststore or widget.get_model())
        self._list.set_model(self._model)
        self.setup()

        self._list.connect(self.changed_signal, self.item_selected_signal)

    def get_model(self):
        """Returns the current data store model"""
        return self._model

    def create_model(self, liststore):
        """Setup the model and list"""
        if not isinstance(liststore, (Gtk.ListStore, Gtk.TreeStore)):
            lbl = label(liststore)
            raise TypeError(f"Expected List or TreeStore, got {lbl}")
        return liststore

    def refresh(self):
        """Attempt to refresh the listview"""
        self._list.queue_draw()

    def setup(self):
        """Setup columns, views, sorting etc"""
        pass

    def get_item_id(self, item):
        """
        Return an id set against this item.

        If item.get_id() is set then duplicates will be ignored.
        """
        if hasattr(item, "get_id"):
            return item.get_id()
        return None

    def replace(self, new_item, item_iter=None):
        """Replace all items, or a single item with object"""
        if item_iter:
            self.remove_item(item_iter)
            self.add_item(new_item)
        else:
            self.clear()
            self._data = new_item
            self.add_item(new_item)

    def item_selected(self, item=None, *others):
        """Base method result, called as an item is selected"""
        if self.selected != item:
            self.selected = item
            if self.selected_signal and item:
                self.selected_signal(item)

    def remove_item(self, item=None):
        """Remove an item from this view"""
        return self._model.remove(self.get_iter(item))

    def check_item_id(self, item):
        """Item id is recorded to guard against duplicates"""
        iid = self.get_item_id(item)
        if iid in self._iids and self.no_dupes:
            raise ValueError(f"Will not add duplicate row {iid}")
        if iid:
            self._iids.append(iid)

    def __iter__(self):
        ret = []

        def collect_all(store, treepath, treeiter):
            ret.append((self.get_item(treeiter), treepath, treeiter))

        self._model.foreach(collect_all)
        return ret.__iter__()

    def set_sensitive(self, sen=True):
        """Proxy the GTK property for sensitivity"""
        self._list.set_sensitive(sen)

    def clear(self):
        """Clear all items from this treeview"""
        self._iids = []
        self._model.clear()

    def item_double_clicked(self, *items):
        """What happens when you double click an item"""
        return items  # Nothing

    def get_item(self, item_iter):
        """Return the object of attention from an iter"""
        return self._model[self.get_iter(item_iter)][0]

    def get_iter(self, item, path=False):
        """Return the iter given the item"""
        if isinstance(item, Gtk.TreePath):
            return item if path else self._model.get_iter(item)
        if isinstance(item, Gtk.TreeIter):
            return self._model.get_path(item) if path else item
        for src_item, src_path, src_iter in self:
            if item == src_item:
                return src_path if path else src_iter
        return None


class TreeView(BaseView):
    """Controls and operates a tree view."""

    column_size = 16
    widget_type = Gtk.TreeView
    changed_signal = "cursor_changed"

    def setup(self):
        """Setup the treeview"""
        self._sel = self._list.get_selection()
        self._sel.set_mode(Gtk.SelectionMode.MULTIPLE)
        self._list.connect("button-press-event", self.item_selected_signal)
        # Separators should do something
        self._list.set_row_separator_func(TreeView.is_separator, None)
        super().setup()

    @staticmethod
    def is_separator(model, item_iter, data):
        """Internal function for seperator checking"""
        return isinstance(model.get_value(item_iter, 0), Separator)

    def get_selected_items(self):
        """Return a list of selected item objects"""
        return [self.get_item(row) for row in self._sel.get_selected_rows()[1]]

    def set_selected_items(self, *items):
        """Select the given items"""
        self._sel.unselect_all()
        for item in items:
            path_item = self.get_iter(item, path=True)
            if path_item is not None:
                self._sel.select_path(path_item)

    def is_selected(self, item):
        """Return true if the item is selected"""
        return self._sel.iter_is_selected(self.get_iter(item))

    def add(self, target, parent=None):
        """Add all items from the target to the treeview"""
        for item in target:
            self.add_item(item, parent=parent)

    def add_item(self, item, parent=None):
        """Add a single item image to the control, returns the TreePath"""
        if item is not None:
            self.check_item_id(item)
            return self._add_item([item], self.get_iter(parent))
        raise ValueError("Item can not be None.")

    def _add_item(self, item, parent):
        return self.get_iter(self._model.append(parent, item), path=True)

    def item_selected_signal(self, *args, **kwargs):
        """Signal for selecting an item"""
        return self.item_selected(*self.get_selected_items())

    def item_button_clicked(self, _, event):
        """Signal for mouse button click"""
        if event is None or event.type == Gdk.EventType._2BUTTON_PRESS:
            self.item_double_clicked(*self.get_selected_items())

    def expand_item(self, item, expand=True):
        """Expand one of our nodes"""
        self._list.expand_row(self.get_iter(item, path=True), expand)

    def create_model(self, liststore=None):
        """Set up an icon view for showing gallery images"""
        if liststore is None:
            liststore = Gtk.TreeStore(GOBJ)
        return super().create_model(liststore)

    def create_column(self, name, expand=True):
        """
        Create and pack a new column to this list.

         name - Label in the column header
         expand - Should the column expand
        """
        return ViewColumn(self._list, name, expand=expand)

    def create_sort(self, *args, **kwargs):
        """
        Create and attach a sorting view to this list.

        see ViewSort arguments for details.
        """
        return ViewSort(self._list, *args, **kwargs)


class ComboBox(TreeView):
    """Controls and operates a combo box list."""

    widget_type = Gtk.ComboBox
    changed_signal = "changed"

    def setup(self):
        pass

    def get_selected_item(self):
        """Return the selected item of this combo box"""
        return self.get_item(self._list.get_active_iter())

    def set_selected_item(self, item):
        """Set the given item as the selected item"""
        self._list.set_active_iter(self.get_iter(item))

    def is_selected(self, item):
        """Returns true if this item is the selected item"""
        return self.get_selected_item() == item

    def get_selected_items(self):
        """Return a list of selected items (one)"""
        return [self.get_selected_item()]


class IconView(BaseView):
    """Allows a simpler IconView for DBus List Objects"""

    widget_type = Gtk.IconView
    changed_signal = "selection-changed"

    def __init__(self, widget, pixmaps, *args, **kwargs):
        super().__init__(widget, *args, **kwargs)
        self.pixmaps = pixmaps

    def set_selected_item(self, item):
        """Sets the selected item to this item"""
        path = self.get_iter(item, path=True)
        if path:
            self._list.set_cursor(path, None, False)

    def get_selected_items(self):
        """Return the seleced item"""
        return [self.get_item(path) for path in self._list.get_selected_items()]

    def create_model(self, liststore):
        """Setup the icon view control and model"""
        if not liststore:
            liststore = Gtk.ListStore(GOBJ, str, GdkPixbuf.Pixbuf)
        return super().create_model(liststore)

    def setup(self):
        """Setup the columns for the iconview"""
        self._list.set_markup_column(1)
        self._list.set_pixbuf_column(2)
        super().setup()

    def add(self, target):
        """Add all items from the target to the iconview"""
        for item in target:
            self.add_item(item)

    def add_item(self, item):
        """Add a single item image to the control"""
        if item is not None:
            self.check_item_id(item)
            return self._add_item(item)
        raise ValueError("Item can not be None.")

    def get_markup(self, item):
        """Default text return for markup."""
        return default(item, "name", str(item))

    def get_icon(self, item):
        """Default icon return, pixbuf or gnome theme name"""
        return default(item, "icon", None)

    def _get_icon(self, item):
        return self.pixmaps.get(self.get_icon(item), item=item)

    def _add_item(self, item):
        """
        Each item's properties must be stuffed into the ListStore directly
        or the IconView won't see them, but only if on auto.
        """
        if not isinstance(item, (tuple, list)):
            item = [item, self.get_markup(item), self._get_icon(item)]
        return self._model.append(item)

    def item_selected_signal(self, *args, **kwargs):
        """Item has been selected"""
        return self.item_selected(*self.get_selected_items())


class ViewSort(object):
    """
    A sorting function for use is ListViews

     ascending - Boolean which direction to sort
     contains - Contains this string
     data - A string or function to get data from each item.
     exact - Compare to this exact string instead.
    """

    def __init__(self, widget, data=None, ascending=False, exact=None, contains=None):
        self.tree = None
        self.data = data
        self.asc = ascending
        self.comp = exact.lower() if exact else None
        self.cont = contains
        self.tree = widget
        self.resort()

    def get_data(self, model, list_iter):
        """Generate sortable data from the item"""
        item = model.get_value(list_iter, 0)
        if isinstance(self.data, str):
            value = getattr(item, self.data)
        elif callable(self.data):
            value = self.data(item)
        return value

    def sort_func(self, model, iter1, iter2, data):
        """Called by Gtk to sort items"""
        value1 = self.get_data(model, iter1)
        value2 = self.get_data(model, iter2)
        if value1 == None or value2 == None:
            return 0
        if self.comp:
            if cmp(self.comp, value1.lower()) == 0:
                return 1
            elif cmp(self.comp, value2.lower()) == 0:
                return -1
            return 0
        elif self.cont:
            if self.cont in value1.lower():
                return 1
            elif self.cont in value2.lower():
                return -1
            return 0
        if value1 < value2:
            return 1
        if value2 < value1:
            return -1
        return 0

    def resort(self):
        model = self.tree.get_model()
        model.set_sort_func(0, self.sort_func, None)
        if self.asc:
            model.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        else:
            model.set_sort_column_id(0, Gtk.SortType.DESCENDING)


class ViewColumn(object):
    """
    Add a column to a gtk treeview.

     name - The column name used as a label.
     expand - Set column expansion.
    """

    def __init__(self, widget, name, expand=False):
        if isinstance(widget, Gtk.TreeView):
            column = Gtk.TreeViewColumn((name))
            column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            column.set_expand(expand)
            self._column = column
            widget.append_column(self._column)
        else:
            # Deal with possible drop down lists
            self._column = widget

    def add_renderer(self, renderer, func, expand=True):
        """Set a custom renderer"""
        self._column.pack_start(renderer, expand)
        self._column.set_cell_data_func(renderer, func, None)
        return renderer

    def add_image_renderer(self, icon, pad=0, pixmaps=None, size=None):
        """
        Set the image renderer

         icon - The function that returns the image to be dsplayed.
         pad - The amount of padding around the image.
         pixmaps - The pixmap manager to use to get images.
         size - Restrict the images to this size.
        """
        # Manager where icons will be pulled from
        filters = [SizeFilter] if size else []
        pixmaps = pixmaps or PixmapManager(
            "", pixmap_dir="./", filters=filters, size=size
        )

        renderer = Gtk.CellRendererPixbuf()
        renderer.set_property("ypad", pad)
        renderer.set_property("xpad", pad)
        func = self.image_func(icon or self.default_icon, pixmaps)
        return self.add_renderer(renderer, func, expand=False)

    def add_text_renderer(self, text, wrap=None, template=None):
        """
        Set the text renderer.

         text - the function that returns the text to be displayed.
         wrap - The wrapping setting for this renderer.
         template - A standard template used for this text markup.
        """

        renderer = Gtk.CellRendererText()
        if wrap is not None:
            renderer.props.wrap_width = wrap
            renderer.props.wrap_mode = Pango.WrapMode.WORD

        renderer.props.background_set = True
        renderer.props.foreground_set = True

        func = self.text_func(text or self.default_text, template)
        return self.add_renderer(renderer, func, expand=True)

    @classmethod
    def clean(cls, text, markup=False):
        """Clean text of any pango markup confusing chars"""
        if text is None:
            text = ""
        if isinstance(text, (str, int, float)):
            if markup:
                text = str(text).replace("<", "&lt;").replace(">", "&gt;")
            return str(text).replace("&", "&amp;")
        elif isinstance(text, dict):
            return dict([(k, cls.clean(v)) for k, v in text.items()])
        elif isinstance(text, (list, tuple)):
            return tuple([cls.clean(value) for value in text])
        raise TypeError("Unknown value type for text: %s" % str(type(text)))

    def get_callout(self, call, default=None):
        """Returns the right kind of method"""
        if isinstance(call, str):
            call = item_property(call, default)
        return call

    def text_func(self, call, template=None):
        """Wrap up our text functionality"""
        callout = self.get_callout(call)

        def internal(column, cell, model, item_iter, data):
            if TreeView.is_separator(model, item_iter, data):
                return
            item = model.get_value(item_iter, 0)
            markup = template is not None
            text = callout(item)
            if isinstance(template, str):
                text = template.format(self.clean(text, markup=True))
            else:
                text = self.clean(text)
            cell.set_property("markup", str(text))

        return internal

    def image_func(self, call, pixmaps=None):
        """Wrap, wrap wrap the func"""
        callout = self.get_callout(call)

        def internal(column, cell, model, item_iter, data):
            if TreeView.is_separator(model, item_iter, data):
                return
            item = model.get_value(item_iter, 0)
            icon = callout(item)
            # The or blank asks for the default icon from the pixmaps
            if isinstance(icon or "", str) and pixmaps:
                # Expect a Gnome theme icon
                icon = pixmaps.get(icon)
            elif icon:
                icon = pixmaps.apply_filters(icon)

            cell.set_property("pixbuf", icon)
            cell.set_property("visible", True)

        return internal

    def default_text(self, item):
        """Default text return for markup."""
        return default(item, "name", str(item))

    def default_icon(self, item):
        """Default icon return, pixbuf or gnome theme name"""
        return default(item, "icon", None)


class Separator:
    """Reprisentation of a separator in a list"""
