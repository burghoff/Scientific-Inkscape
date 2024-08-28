"""
Useful decorators for tests.
"""
import pytest
from inkex.command import is_inkscape_available

requires_inkscape = pytest.mark.skipif(  # pylint: disable=invalid-name
    not is_inkscape_available(), reason="Test requires inkscape, but it's not available"
)
