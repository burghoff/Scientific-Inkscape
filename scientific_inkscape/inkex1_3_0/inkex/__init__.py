# coding=utf-8
"""
This describes the core API for the inkex core modules.

This provides the basis from which you can develop your inkscape extension.
"""

# pylint: disable=wildcard-import
import sys

from .extensions import *
from .utils import AbortExtension, DependencyError, Boolean, errormsg
from .styles import *
from .paths import Path, CubicSuperPath  # Path commands are not exported
from .colors import *
from .transforms import *
from .elements import *

# legacy proxies
from .deprecated import Effect
from .deprecated import localize
from .deprecated import debug

# legacy functions
from .deprecated import are_near_relative
from .deprecated import unittouu

MIN_VERSION = (3, 7)
if sys.version_info < MIN_VERSION:
    sys.exit("Inkscape extensions require Python 3.7 or greater.")

__version__ = "1.3.0"  # Version number for inkex; may differ from Inkscape version.
