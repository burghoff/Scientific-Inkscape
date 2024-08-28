#
# Copyright 2011 (c) Ian Bicking <ianb@colorstudy.com>
#           2019 (c) Martin Owens <doctormo@gmail.com>
#
# Taken from http://formencode.org under the GPL compatible PSF License.
# Modified to produce more output as a diff.
#
"""
Allow two xml files/lxml etrees to be compared, returning their differences.
"""
import xml.etree.ElementTree as xml
from io import BytesIO

from inkex.paths import Path


def text_compare(test1, test2):
    """
    Compare two text strings while allowing for '*' to match
    anything on either lhs or rhs.
    """
    if not test1 and not test2:
        return True
    if test1 == "*" or test2 == "*":
        return True
    return (test1 or "").strip() == (test2 or "").strip()


class DeltaLogger(list):
    """A record keeper of the delta between two svg files"""

    def append_tag(self, tag_a, tag_b):
        """Record a tag difference"""
        if tag_a:
            tag_a = f"<{tag_a}.../>"
        if tag_b:
            tag_b = f"<{tag_b}.../>"
        self.append((tag_a, tag_b))

    def append_attr(self, attr, value_a, value_b):
        """Record an attribute difference"""

        def _prep(val):
            if val:
                if attr == "d":
                    return [attr] + Path(val).to_arrays()
                return (attr, val)
            return val

        # Only append a difference if the preprocessed values are different.
        # This solves the issue that -0 != 0 in path data.
        prep_a = _prep(value_a)
        prep_b = _prep(value_b)
        if prep_a != prep_b:
            self.append((prep_a, prep_b))

    def append_text(self, text_a, text_b):
        """Record a text difference"""
        self.append((text_a, text_b))

    def __bool__(self):
        """Returns True if there's no log, i.e. the delta is clean"""
        return not self.__len__()

    __nonzero__ = __bool__

    def __repr__(self):
        if self:
            return "No differences detected"
        return f"{len(self)} xml differences"


def to_xml(data):
    """Convert string or bytes to xml parsed root node"""
    if isinstance(data, str):
        data = data.encode("utf8")
    if isinstance(data, bytes):
        return xml.parse(BytesIO(data)).getroot()
    return data


def xmldiff(data1, data2):
    """Create an xml difference, will modify the first xml structure with a diff"""
    xml1, xml2 = to_xml(data1), to_xml(data2)
    delta = DeltaLogger()
    _xmldiff(xml1, xml2, delta)
    return xml.tostring(xml1).decode("utf-8"), delta


def _xmldiff(xml1, xml2, delta):
    if xml1.tag != xml2.tag:
        xml1.tag = f"{xml1.tag}XXX{xml2.tag}"
        delta.append_tag(xml1.tag, xml2.tag)
    for name, value in xml1.attrib.items():
        if name not in xml2.attrib:
            delta.append_attr(name, xml1.attrib[name], None)
            xml1.attrib[name] += "XXX"
        elif xml2.attrib.get(name) != value:
            delta.append_attr(name, xml1.attrib.get(name), xml2.attrib.get(name))
            xml1.attrib[name] = f"{xml1.attrib.get(name)}XXX{xml2.attrib.get(name)}"
    for name, value in xml2.attrib.items():
        if name not in xml1.attrib:
            delta.append_attr(name, None, value)
            xml1.attrib[name] = "XXX" + value
    if not text_compare(xml1.text, xml2.text):
        delta.append_text(xml1.text, xml2.text)
        xml1.text = f"{xml1.text}XXX{xml2.text}"
    if not text_compare(xml1.tail, xml2.tail):
        delta.append_text(xml1.tail, xml2.tail)
        xml1.tail = f"{xml1.tail}XXX{xml2.tail}"

    # Get children and pad with nulls
    children_a = list(xml1)
    children_b = list(xml2)
    children_a += [None] * (len(children_b) - len(children_a))
    children_b += [None] * (len(children_a) - len(children_b))

    for child_a, child_b in zip(children_a, children_b):
        if child_a is None:  # child_b exists
            delta.append_tag(child_b.tag, None)
        elif child_b is None:  # child_a exists
            delta.append_tag(None, child_a.tag)
        else:
            _xmldiff(child_a, child_b, delta)
