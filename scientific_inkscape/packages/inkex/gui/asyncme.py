#
# Copyright 2015 Ian Denhardt <ian@zenhack.net>
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
"""Convenience library for concurrency

GUI apps frequently need concurrency, for example to avoid blocking UI while
doing some long running computation. This module provides helpers for doing
this kind of thing.

The functions/methods here which spawn callables asynchronously
don't supply a direct way to provide arguments. Instead, the user is
expected to use a lambda, e.g::

    holding(lck, lambda: do_stuff(1,2,3, x='hello'))

This is because the calling function may have additional arguments which
could obscure the user's ability to pass arguments expected by the called
function. For example, in the call::

    holding(lck, lambda: run_task(blocking=True), blocking=False)

the blocking argument to holding might otherwise conflict with the
blocking argument to run_task.
"""
import time
import threading
from datetime import datetime, timedelta

from functools import wraps
from typing import Any, Tuple
from gi.repository import Gdk, GLib


class Future:
    """A deferred result

    A `Future` is a result-to-be; it can be used to deliver a result
    asynchronously. Typical usage:

        >>> def background_task(task):
        ...     ret = Future()
        ...     def _task(x):
        ...         return x - 4 + 2
        ...     thread = threading.Thread(target=lambda: ret.run(lambda: _task(7)))
        ...     thread.start()
        ...     return ret
        >>> # Do other stuff
        >>> print(ret.wait())
        5

    :func:`run` will also propagate exceptions; see its docstring for details.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._value = None
        self._exception = None
        self._lock.acquire()

    def is_ready(self):
        """Return whether the result is ready"""
        result = self._lock.acquire(False)
        if result:
            self._lock.release()
        return result

    def wait(self):
        """Wait for the result.

        `wait` blocks until the result is ready (either :func:`result` or
        :func:`exception` has been called), and then returns it (in the case
        of :func:`result`), or raises it (in the case of :func:`exception`).
        """
        with self._lock:
            if self._exception is None:
                return self._value
            else:
                raise self._exception  # pylint: disable=raising-bad-type

    def result(self, value):
        """Supply the result as a return value.

        ``value`` is the result to supply; it will be returned when
        :func:`wait` is called.
        """
        self._value = value
        self._lock.release()

    def exception(self, err):
        """Supply an exception as the result.

        Args:
            err (Exception): an exception, which will be raised when :func:`wait`
                is called.
        """
        self._exception = err
        self._lock.release()

    def run(self, task):
        """Calls task(), and supplies the result.

        If ``task`` raises an exception, pass it to :func:`exception`.
        Otherwise, pass the return value to :func:`result`.
        """
        try:
            self.result(task())
        except Exception as err:  # pylint: disable=broad-except
            self.exception(err)


class DebouncedSyncVar:
    """A synchronized variable, which debounces its value

    :class:`DebouncedSyncVar` supports three operations: put, replace, and get.
    get will only retrieve a value once it has "settled," i.e. at least
    a certain amount of time has passed since the last time the value
    was modified.
    """

    def __init__(self, delay_seconds=0):
        """Create a new dsv with the supplied delay, and no initial value."""
        self._cv = threading.Condition()
        self._delay = timedelta(seconds=delay_seconds)

        self._deadline = None
        self._value = None

        self._have_value = False

    def set_delay(self, delay_seconds):
        """Set the delay in seconds of the debounce."""
        with self._cv:
            self._delay = timedelta(seconds=delay_seconds)

    def get(self, blocking=True, remove=True) -> Tuple[Any, bool]:
        """Retrieve a value.

        Args:
            blocking (bool, optional): if True, block until (1) the dsv has a value
                and (2) the value has been unchanged for an amount of time greater
                than or equal to the dsv's delay. Otherwise, if these conditions
                are not met, return ``(None, False)`` immediately. Defaults to True.
            remove (bool, optional): if True, remove the value when returning it.
                Otherwise, leave it where it is.. Defaults to True.

        Returns:
            Tuple[Any, bool]: Tuple (value, ok). ``value`` is the value of the variable
            (if successful, see above), and ok indicates whether or not a value was
            successfully retrieved.
        """
        while True:
            with self._cv:
                # If there's no value, either wait for one or return
                # failure.
                while not self._have_value:
                    if blocking:
                        self._cv.wait()
                    else:
                        return None, False  # pragma: no cover

                now = datetime.now()
                deadline = self._deadline
                value = self._value
                if deadline <= now:
                    # Okay, we're good. Remove the value if necessary, and
                    # return it.
                    if remove:
                        self._have_value = False
                        self._value = None
                    self._cv.notify()
                    return value, True

            # Deadline hasn't passed yet. Either wait or return failure.
            if blocking:
                time.sleep((deadline - now).total_seconds())
            else:
                return None, False  # pragma: no cover

    def replace(self, value):
        """Replace the current value of the dsv (if any) with ``value``.

        replace never blocks (except briefly to acquire the lock). It does not
        wait for any unit of time to pass (though it does reset the timer on
        completion), nor does it wait for the dsv's value to appear or
        disappear.
        """
        with self._cv:
            self._replace(value)

    def put(self, value):
        """Set the dsv's value to ``value``.

        If the dsv already has a value, this blocks until the value is removed.
        Upon completion, this resets the timer.
        """
        with self._cv:
            while self._have_value:
                self._cv.wait()
            self._replace(value)

    def _replace(self, value):
        self._have_value = True
        self._value = value
        self._deadline = datetime.now() + self._delay
        self._cv.notify()


def spawn_thread(func):
    """Call ``func()`` in a separate thread

    Returns the corresponding :class:`threading.Thread` object.
    """
    thread = threading.Thread(target=func)
    thread.start()
    return thread


def in_mainloop(func):
    """Run f() in the gtk main loop

    Returns a :class:`Future` object which can be used to retrieve the return
    value of the function call.

    :func:`in_mainloop` exists because Gtk isn't threadsafe, and therefore cannot be
    manipulated except in the thread running the Gtk main loop. :func:`in_mainloop`
    can be used by other threads to manipulate Gtk safely.
    """
    future = Future()

    def handler(*_args, **_kwargs):
        """Function to be called in the future"""
        future.run(func)

    Gdk.threads_add_idle(0, handler, None)
    return future


def mainloop_only(f):
    """A decorator which forces a function to only be run in Gtk's main loop.

    Invoking a decorated function as ``f(*args, **kwargs)`` is equivalent to
    using the undecorated function (from a thread other than the one running
    the Gtk main loop) as::

        in_mainloop(lambda: f(*args, **kwargs)).wait()

    :func:`mainloop_only` should be used to decorate functions which are unsafe
    to run outside of the Gtk main loop.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        if GLib.main_depth():
            # Already in a mainloop, so just run it.
            return f(*args, **kwargs)
        return in_mainloop(lambda: f(*args, **kwargs)).wait()

    return wrapper


def holding(lock, task, blocking=True):
    """Run task() while holding ``lock``.

    Args:
        blocking (bool, optional): if True, wait for the lock before running.
            Otherwise, if the lock is busy, return None immediately, and don't
            spawn `task`. Defaults to True.

    Returns:
        Union[Future, None]: The return value is a future which can be used to retrieve
        the result of running task (or None if the task was not run).
    """
    if not lock.acquire(False):
        return None
    ret = Future()

    def _target():
        ret.run(task)
        if ret._exception:  # pragma: no cover
            ret.wait()
        lock.release()

    threading.Thread(target=_target).start()
    return ret


def run_or_wait(func):
    """A decorator which runs the function using :func:`holding`

    This function creates a single lock for this function and
    waits for the lock to release before returning.

    See :func:`holding` above, with ``blocking=True``
    """
    lock = threading.Lock()

    def _inner(*args, **kwargs):
        return holding(lock, lambda: func(*args, **kwargs), blocking=True)

    return _inner


def run_or_none(func):
    """A decorator which runs the function using :func:`holding`

    This function creates a single lock for this function and
    returns None if the process is already running (locked)

    See :func:`holding` above with ``blocking=True``
    """
    lock = threading.Lock()

    def _inner(*args, **kwargs):
        return holding(lock, lambda: func(*args, **kwargs), blocking=False)

    return _inner
