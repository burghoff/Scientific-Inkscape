# coding=utf-8
#
# Copyright (C) 2019 Martin Owens <doctormo@gmail.com>
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
Common access to serial and other computer ports.
"""

import os
import sys
import time
from .utils import DependencyError, AbortExtension

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None


class Serial:
    """
    Attempt to get access to the computer's serial port.

    with Serial(port_name, ...) as com:
        com.write(...)

    Provides access to the debug/testing ports which are pretend ports
    able to accept the same input but allow for debugging.
    """

    def __init__(self, port, baud=9600, timeout=0.1, **options):
        self.test = port == "[test]"
        if self.test:
            import pty  # This does not work on windows #pylint: disable=import-outside-toplevel

            self.controller, self.peripheral = pty.openpty()
            port = os.ttyname(self.peripheral)

        self.has_serial()
        self.com = serial.Serial()
        self.com.port = port
        self.com.baudrate = int(baud)
        self.com.timeout = timeout
        self.set_options(**options)

    def set_options(self, stop=1, size=8, flow=None, parity=None):
        """Set further options on the serial port"""
        size = {5: "five", 6: "six", 7: "seven", 8: "eight"}.get(size, size)
        stop = {"onepointfive": 1.5}.get(stop.lower(), stop)
        stop = {1: "one", 1.5: "one_point_five", 2: "two"}.get(stop, stop)
        self.com.bytesize = getattr(serial, str(str(size).upper()) + "BITS")
        self.com.stopbits = getattr(serial, "STOPBITS_" + str(stop).upper())
        self.com.parity = getattr(serial, "PARITY_" + str(parity).upper())
        # set flow control
        self.com.xonxoff = flow == "xonxoff"
        self.com.rtscts = flow in ("rtscts", "dsrdtrrtscts")
        self.com.dsrdtr = flow == "dsrdtrrtscts"

    def __enter__(self):
        try:
            # try to establish connection
            self.com.open()
        except serial.SerialException as error:
            raise AbortExtension(
                "Could not open serial port. Please check your device"
                " is running, connected and the settings are correct"
            ) from error
        return self.com

    def __exit__(self, exc, value, traceback):
        if not traceback and self.test:
            output = " " * 1024
            while len(output) == 1024:
                time.sleep(0.01)
                output = os.read(self.controller, 1024)
                sys.stderr.write(output.decode("utf8"))
        # self.com.read(2)
        self.com.close()

    @staticmethod
    def has_serial():
        """Late importing of pySerial module"""
        if serial is None:
            raise DependencyError("pySerial is required to open serial ports.")

    @staticmethod
    def list_ports():
        """Return a list of available serial ports"""
        Serial.has_serial()  # Cause DependencyError error
        return [hw.name for hw in list_ports.comports(True)]
