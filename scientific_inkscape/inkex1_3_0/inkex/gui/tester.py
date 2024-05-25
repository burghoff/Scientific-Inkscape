# coding=utf-8
#
# Copyright 2022 Martin Owens <doctormo@geek-2.com>
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
Structures for consistant testing of Gtk GUI programs.
"""

import sys
from gi.repository import Gtk, GLib


class MainLoopProtection:
    """
    This protection class provides a way to launch the Gtk mainloop in a test
    friendly way.

    Exception handling hooks provide a way to see errors that happen
        inside the main loop, raising them back to the caller.
    A full timeout in seconds stops the gtk mainloop from operating
        beyond a set time, acting as a kill switch in the event something
        has gone horribly wrong.

    Use:
        with MainLoopProtection(timeout=10s):
            app.run()
    """

    def __init__(self, timeout=10):
        self.timeout = timeout * 1000
        self._hooked = None
        self._old_excepthook = None

    def __enter__(self):
        # replace sys.excepthook with our own and remember hooked raised error
        self._old_excepthook = sys.excepthook
        sys.excepthook = self.excepthook
        # Remove mainloop by force if it doesn't die within 10 seconds
        self._timeout = GLib.timeout_add(self.timeout, self.idle_exit)

    def __exit__(self, exc, value, traceback):  # pragma: no cover
        """Put the except handler back, cancel the timer and raise if needed"""
        if self._old_excepthook:
            sys.excepthook = self._old_excepthook
        # Remove the timeout, so we don't accidentally kill later mainloops
        if self._timeout:
            GLib.source_remove(self._timeout)
        # Raise an exception if one happened during the test run
        if self._hooked:
            exc, value, traceback = self._hooked
        if value and traceback:
            raise value.with_traceback(traceback)

    def idle_exit(self):  # pragma: no cover
        """Try to going to kill any running mainloop."""
        GLib.idle_add(Gtk.main_quit)

    def excepthook(self, ex_type, ex_value, traceback):  # pragma: no cover
        """Catch errors thrown by the Gtk mainloop"""
        self.idle_exit()
        # Remember the exception data for raising inside the test context
        if ex_value is not None:
            self._hooked = [ex_type, ex_value, traceback]
        # Fallback and double print the exception (remove if double printing is problematic)
        return self._old_excepthook(ex_type, ex_value, traceback)
