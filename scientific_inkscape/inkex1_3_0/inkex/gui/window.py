#
# Copyright 2012-2022 Martin Owens <doctormo@geek-2.com>
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
# pylint: disable=too-many-instance-attributes
"""
Wraps the gtk windows with something a little nicer.
"""
import logging

from gi.repository import Gtk

PROPS = {
    "Box": ["expand", "fill", "padding", "pack-type"],
    "Grid": ["top-attach", "left-attach", "height", "width"],
    "Table": ["top-attach", "left-attach", "bottom-attach", "right-attach"],
}


def protect(cls, *methods):
    """Simple check for protecting an inherrited class from having
    certain methods over-ridden"""
    if not isinstance(cls, type):
        cls = type(cls)
    for method in methods:
        if method in cls.__dict__:  # pragma: no cover
            raise RuntimeError(
                f"{cls.__name__} in {cls.__module__} has" f" protected def {method}()"
            )


class Window:
    """
    This wraps gtk windows and allows for having parent windows

    name = 'name-of-the-window'

    Should the window be the first loaded and end gtk when closed:

    primary = True/False
    """

    primary = True
    name = None

    def __init__(self, gapp):
        self.gapp = gapp
        self.dead = False
        self.parent = None
        self.args = ()
        ui_file = gapp.get_ui_file(self.name)

        # Setup the gtk app connection
        self.w_tree = Gtk.Builder()
        self.widget = self.w_tree.get_object
        self.w_tree.set_translation_domain(gapp.app_name)
        self.w_tree.add_from_file(ui_file)

        # Setup the gtk builder window
        self.window = self.widget(self.name)
        if not self.window:  # pragma: no cover
            raise KeyError(f"Missing window widget '{self.name}' from '{ui_file}'")

        # Give us a window id to track this window
        self.wid = str(hash(self.window))

    def extract(self):
        """Extract this window's container for use in other apps"""
        for child in self.window.get_children():
            self.window.remove(child)
            return child

    def init(self, parent=None, **kwargs):
        """Initialise the window within the GtkApp"""
        if "replace" not in kwargs:
            protect(self, "destroy", "exit", "load_window", "proto_window")
        self.args = kwargs
        # Set object defaults
        self.parent = parent

        self.w_tree.connect_signals(self)

        # These are some generic convience signals
        self.window.connect("destroy", self.exit)

        # If we have a parent window, then we expect not to quit
        if self.parent:
            self.window.set_transient_for(self.parent)
            self.parent.set_sensitive(False)

        # We may have some more gtk widgets to setup
        self.load_widgets(**self.args)
        self.window.show()

    def load_window(self, name, *args, **kwargs):
        """Load child window, automatically sets parent"""
        kwargs["parent"] = self.window
        return self.gapp.load_window(name, *args, **kwargs)

    def load_widgets(self):
        """Child class should use this to create widgets"""

    def destroy(self, widget=None):  # pylint: disable=unused-argument
        """Destroy the window"""
        logging.debug("Destroying Window '%s'", self.name)
        self.window.destroy()
        # We don't need to call self.exit(), handeled by window event.

    def pre_exit(self):
        """Internal method for what to do when the window has died"""

    def exit(self, widget=None):
        """Called when the window needs to exit."""
        # Is the signal called by the window or by something else?
        if not widget or not isinstance(widget, Gtk.Window):
            self.destroy()
        # Clean up any required processes
        self.pre_exit()
        if self.parent:
            # We assume the parent didn't load another gtk loop
            self.parent.set_sensitive(True)
        # Exit our entire app if this is the primary window
        # Or just remove from parent window list, which may still exit.
        if self.primary:
            logging.debug("Exiting the application")
            self.gapp.exit()
        else:
            logging.debug("Removing Window %s from parent", self.name)
            self.gapp.remove_window(self)
        # Now finish up what ever is left to do now the window is dead.
        self.dead = True
        self.post_exit()
        return widget

    def post_exit(self):
        """Called after we've killed the window"""

    def if_widget(self, name):
        """
        Attempt to get the widget from gtk, but if not return a fake that won't
        cause any trouble if we don't further check if it's real.
        """
        return self.widget(name) or FakeWidget(name)

    def replace(self, old, new):
        """Replace the old widget with the new widget"""
        if isinstance(old, str):
            old = self.widget(old)
        if isinstance(new, str):
            new = self.widget(new)
        target = old.get_parent()
        source = new.get_parent()
        if target is not None:
            if source is not None:
                source.remove(new)
            target.remove(old)
            target.add(new)

    @staticmethod
    def get_widget_name(obj):
        """Return the widget's name in the builder file"""
        return Gtk.Buildable.get_name(obj)


class ChildWindow(Window):
    """
    Base class for child window objects, these child windows are typically
    window objects in the same gtk builder file as their parents. If you just want
    to make a window that interacts with a parent window, use the normal
    Window class and call with the optional parent attribute.
    """

    primary = False


class FakeWidget:
    """A fake widget class that can take calls"""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, name):
        def _fake(*args, **kwargs):
            logging.info("Calling fake method: %s:%s", args, kwargs)

        return _fake

    def __bool__(self):
        return False
