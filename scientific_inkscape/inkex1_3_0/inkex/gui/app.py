# coding=utf-8
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
Gtk Application base classes, providing a way to load a GtkBuilder
with a specific glade/ui file containing windows, and building
a usable pythonic interface from them.
"""
import os
import signal
import logging

from gi.repository import Gtk, GLib


class GtkApp:
    """
    This wraps gtk builder and allows for some extra functionality with
    windows, especially the management of gtk main loops.

    Args:
        start_loop (bool, optional): If set to true will start a new gtk main loop.
            Defaults to False.
        start_gui (bool, optional): Used as local propertes if unset and passed to
                primary window when loaded. Defaults to True.
    """

    @property
    def prefix(self):
        """Folder prefix added to ui_dir"""
        return self.kwargs.get("prefix", "")

    @property
    def windows(self):
        """Returns a list of windows for this app"""
        return self.kwargs.get("windows", [])

    @property
    def ui_dir(self):
        """This is often the local directory"""
        return self.kwargs.get("ui_dir", "./")

    @property
    def ui_file(self):
        """If a single file is used for multiple windows"""
        return self.kwargs.get("ui_file", None)

    @property
    def app_name(self):
        """Set this variable in your class"""
        try:
            return self.kwargs["app_name"]
        except KeyError:
            raise NotImplementedError(
                "App name is not set, pass in or set 'app_name' in class."
            )

    @property
    def window(self):
        """Return the primary window"""
        return self._primary

    def __init__(self, start_loop=False, start_gui=True, **kwargs):
        """Creates a new GtkApp."""
        self.kwargs = kwargs
        self._loaded = {}
        self._initial = {}
        self._primary = None

        self.main_loop = GLib.main_depth()

        # Start with creating all the defined windows.
        if start_gui:
            self.init_gui()
        # Start up a gtk main loop when requested
        if start_loop:
            self.run()

    def run(self):
        """Run the gtk mainloop with ctrl+C and keyboard interrupt additions"""
        if not Gtk.init_check()[0]:  # pragma: no cover
            raise RuntimeError(
                "Gtk failed to start." " Make sure $DISPLAY variable is set.\n"
            )
        try:
            # Add a signal to force quit on Ctrl+C (just like the old days)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            Gtk.main()
        except KeyboardInterrupt:  # pragma: no cover
            logging.info("User Interrupted")
        logging.debug("Exiting %s", self.app_name)

    def get_ui_file(self, window):
        """Load any given gtk builder file from a standard location."""
        paths = [
            os.path.join(self.ui_dir, self.prefix, f"{window}.ui"),
            os.path.join(self.ui_dir, self.prefix, f"{self.ui_file}.ui"),
        ]
        for path in paths:
            if os.path.isfile(path):
                return path
        raise FileNotFoundError(f"Gtk Builder file is missing: {paths}")

    def init_gui(self):
        """Initialise all of our windows and load their signals"""
        if self.windows:
            for cls in self.windows:
                window = cls
                logging.debug("Adding window %s to GtkApp", window.name)
                self._initial[window.name] = window
            for window in self._initial.values():
                if window.primary:
                    if not self._primary:
                        self._primary = self.load_window(window.name)
        if not self.windows or not self._primary:
            raise KeyError(f"No primary window found for '{self.app_name}' app.")

    def load_window(self, name, *args, **kwargs):
        """Load a specific window from our group of windows"""
        window = self.proto_window(name)
        window.init(*args, **kwargs)
        return window

    def load_window_extract(self, name, **kwargs):
        """Load a child window as a widget container"""
        window = self.proto_window(name)
        window.load_widgets(**kwargs)
        return window.extract()

    def proto_window(self, name):
        """
        Loads a Glade window as a window without initialisation, used for
        extracting widgets from windows without loading them as windows.
        """
        logging.debug("Loading '%s' from %s", name, self._initial)
        if name in self._initial:
            # Create a new instance of this window
            window = self._initial[name](self)
            # Save the window object linked against the gtk window instance
            self._loaded[window.wid] = window
            return window
        raise KeyError(f"Can't load window '{name}', class not found.")

    def remove_window(self, window):
        """Remove the window from the list and exit if none remain"""
        if window.wid in self._loaded:
            self._loaded.pop(window.wid)
        else:
            logging.warning("Missing window '%s' on exit.", window.name)
        logging.debug("Loaded windows: %s", self._loaded)
        if not self._loaded:
            self.exit()

    def exit(self):
        """Exit our gtk application and kill gtk main if we have to"""
        if self.main_loop < GLib.main_depth():
            # Quit Gtk loop if we started one.
            tag = self._primary.name if self._primary else "program"
            logging.debug("Quit '%s' Main Loop.", tag)
            Gtk.main_quit()
        # You have to return in order for the loop to exit
        return 0
