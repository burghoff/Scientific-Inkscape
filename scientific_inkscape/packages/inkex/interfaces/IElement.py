"""Element abstractions for type comparisons without circular imports

.. versionadded:: 1.2"""

from __future__ import annotations

from abc import ABC, abstractmethod

import sys
from lxml import etree

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    from typing_extensions import Protocol


class IBaseElement(ABC, etree.ElementBase):
    """Abstraction for BaseElement to avoid circular imports"""

    @abstractmethod
    def get_id(self, as_url=0):
        """Returns the element ID. If not set, generates a unique ID."""
        raise NotImplementedError


class BaseElementProtocol(Protocol):
    """Abstraction for BaseElement, to be used as typehint in mixin classes"""

    def get_id(self, as_url=0) -> str:
        """Returns the element ID. If not set, generates a unique ID."""

    @property
    def root(self) -> ISVGDocumentElement:
        """Returns the element's root."""


class ISVGDocumentElement(IBaseElement):
    """Abstraction for SVGDocumentElement"""
