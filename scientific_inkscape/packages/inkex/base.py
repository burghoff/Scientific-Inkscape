# coding=utf-8
#
# Copyright (c) 2018 - Martin Owens <doctormo@gmail.com>
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
The ultimate base functionality for every Inkscape extension.
"""

import io
import os
import re
import sys
import copy

from typing import (
    Dict,
    List,
    Tuple,
    Type,
    Optional,
    Callable,
    Any,
    Union,
    IO,
    TYPE_CHECKING,
    cast,
)

from argparse import ArgumentParser, Namespace
from lxml import etree

from .interfaces.IElement import IBaseElement, ISVGDocumentElement
from .utils import filename_arg, AbortExtension, ABORT_STATUS, errormsg, do_nothing
from .elements._parser import load_svg
from .elements._utils import NSS
from .localization import localize


class InkscapeExtension:
    """
    The base class extension, provides argument parsing and basic
    variable handling features.
    """

    multi_inx = False  # Set to true if this class is used by multiple inx files.
    extra_nss = {}  # type: Dict[str, str]

    # Provide a unique value to allow detection of no argument specified
    # for `output` parameter of `run()`, not even `None`; this has to be an io
    # type for type checking purposes:
    output_unspecified = io.StringIO("")

    def __init__(self):
        # type: () -> None
        NSS.update(self.extra_nss)
        self.file_io = None  # type: Optional[IO]
        self.options = Namespace()
        self.document = None  # type: Union[None, bytes, str, etree.element]
        self.arg_parser = ArgumentParser(description=self.__doc__)

        self.arg_parser.add_argument(
            "input_file",
            nargs="?",
            metavar="INPUT_FILE",
            type=filename_arg,
            help="Filename of the input file (default is stdin)",
            default=None,
        )

        self.arg_parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Optional output filename for saving the result (default is stdout).",
        )

        self.add_arguments(self.arg_parser)

        localize()

    def add_arguments(self, pars):
        # type: (ArgumentParser) -> None
        """Add any extra arguments to your extension handle, use:

        def add_arguments(self, pars):
            pars.add_argument("--num-cool-things", type=int, default=3)
            pars.add_argument("--pos-in-doc", type=str, default="doobry")
        """
        # No extra arguments by default so super is not required

    def parse_arguments(self, args):
        # type: (List[str]) -> None
        """Parse the given arguments and set 'self.options'"""
        self.options = self.arg_parser.parse_args(args)

    def arg_method(self, prefix="method"):
        # type: (str) -> Callable[[str], Callable[[Any], Any]]
        """Used by add_argument to match a tab selection with an object method

        pars.add_argument("--tab", type=self.arg_method(), default="foo")
        ...
        self.options.tab(arguments)
        ...
        .. code-block:: python
        .. def method_foo(self, arguments):
        ..     # do something
        """

        def _inner(value):
            name = f"""{prefix}_{value.strip('"').lower()}""".replace("-", "_")
            try:
                return getattr(self, name)
            except AttributeError as error:
                if name.startswith("_"):
                    return do_nothing
                raise AbortExtension(f"Can not find method {name}") from error

        return _inner

    @staticmethod
    def arg_number_ranges():
        """Parses a number descriptor. e.g:
        ``1,2,4-5,7,9-`` is parsed to ``1, 2, 4, 5, 7, 9, 10, ..., lastvalue``

        .. versionadded:: 1.2

        Usage:

        .. code-block:: python

            # in add_arguments()
            pars.add_argument("--pages", type=self.arg_number_ranges(), default=1-)
            # later on, pages is then a list of ints
            pages = self.options.pages(lastvalue)

        """

        def _inner(value):
            def method(pages, lastvalue, startvalue=1):
                # replace ranges, such as -3, 10- with startvalue,2,3,10..lastvalue
                pages = re.sub(
                    r"(\d+|)\s?-\s?(\d+|)",
                    lambda m: ",".join(
                        map(
                            str,
                            range(
                                int(m.group(1) or startvalue),
                                int(m.group(2) or lastvalue) + 1,
                            ),
                        )
                    )
                    if not (m.group(1) or m.group(2)) == ""
                    else "",
                    pages,
                )

                pages = map(int, re.findall(r"(\d+)", pages))
                pages = tuple({i for i in pages if i <= lastvalue})
                return pages

            return lambda lastvalue, startvalue=1: method(
                value, lastvalue, startvalue=startvalue
            )

        return _inner

    @staticmethod
    def arg_class(options: List[Type]) -> Callable[[str], Any]:
        """Used by add_argument to match an option with a class

        Types to choose from are given by the options list

        .. versionadded:: 1.2

        Usage:

        .. code-block:: python

            pars.add_argument("--class", type=self.arg_class([ClassA, ClassB]),
                              default="ClassA")
        """

        def _inner(value: str):
            name = value.strip('"')
            for i in options:
                if name == i.__name__:
                    return i
            raise AbortExtension(f"Can not find class {name}")

        return _inner

    def debug(self, msg):
        # type: (str) -> None
        """Write a debug message"""
        errormsg(f"DEBUG<{type(self).__name__}> {msg}\n")

    @staticmethod
    def msg(msg):
        # type: (str) -> None
        """Write a non-error message"""
        errormsg(msg)

    def run(self, args=None, output=output_unspecified):
        # type: (Optional[List[str]], Union[str, IO]) -> None
        """Main entrypoint for any Inkscape Extension"""
        try:
            if args is None:
                args = sys.argv[1:]

            self.parse_arguments(args)
            if self.options.input_file is None:
                self.options.input_file = sys.stdin
            elif "DOCUMENT_PATH" not in os.environ:
                os.environ["DOCUMENT_PATH"] = self.options.input_file

            self.bin_stdout = None
            if self.options.output is None:
                # If no output was specified, attempt to extract a binary
                # output from stdout, and if that doesn't seem possible,
                # punt and try whatever stream stdout is:
                if output is InkscapeExtension.output_unspecified:
                    output = sys.stdout
                    if "b" not in getattr(output, "mode", "") and not isinstance(
                        output, (io.RawIOBase, io.BufferedIOBase)
                    ):
                        if hasattr(output, "buffer"):
                            output = output.buffer  # type: ignore
                        elif hasattr(output, "fileno"):
                            self.bin_stdout = os.fdopen(
                                output.fileno(), "wb", closefd=False
                            )
                            output = self.bin_stdout
                self.options.output = output

            self.load_raw()
            self.save_raw(self.effect())
        except AbortExtension as err:
            errormsg(str(err))
            sys.exit(ABORT_STATUS)
        finally:
            self.clean_up()

    def load_raw(self):
        # type: () -> None
        """Load the input stream or filename, save everything to self"""
        if isinstance(self.options.input_file, str):
            # pylint: disable=consider-using-with
            self.file_io = open(self.options.input_file, "rb")
            document = self.load(self.file_io)
        else:
            document = self.load(self.options.input_file)
        self.document = document

    def save_raw(self, ret):
        # type: (Any) -> None
        """Save to the output stream, use everything from self"""
        if self.has_changed(ret):
            if isinstance(self.options.output, str):
                with open(self.options.output, "wb") as stream:
                    self.save(stream)
            else:
                if sys.platform == "win32" and not "PYTEST_CURRENT_TEST" in os.environ:
                    # When calling an extension from within Inkscape on Windows,
                    # Python thinks that the output stream is seekable
                    # (https://gitlab.com/inkscape/inkscape/-/issues/3273)
                    self.options.output.seekable = lambda self: False

                    def seek_replacement(offset: int, whence: int = 0):
                        raise AttributeError(
                            "We can't seek in the stream passed by Inkscape on Windows"
                        )

                    def tell_replacement():
                        raise AttributeError(
                            "We can't tell in the stream passed by Inkscape on Windows"
                        )

                    # Some libraries (e.g. ZipFile) don't query seekable, but check for an error
                    # on seek
                    self.options.output.seek = seek_replacement
                    self.options.output.tell = tell_replacement
                self.save(self.options.output)

    def load(self, stream):
        # type: (IO) -> str
        """Takes the input stream and creates a document for parsing"""
        raise NotImplementedError(f"No input handle for {self.name}")

    def save(self, stream):
        # type: (IO) -> None
        """Save the given document to the output file"""
        raise NotImplementedError(f"No output handle for {self.name}")

    def effect(self):
        # type: () -> Any
        """Apply some effects on the document or local context"""
        raise NotImplementedError(f"No effect handle for {self.name}")

    def has_changed(self, ret):  # pylint: disable=no-self-use
        # type: (Any) -> bool
        """Return true if the output should be saved"""
        return ret is not False

    def clean_up(self):
        # type: () -> None
        """Clean up any open handles and other items"""
        if hasattr(self, "bin_stdout"):
            if self.bin_stdout is not None:
                self.bin_stdout.close()
        if self.file_io is not None:
            self.file_io.close()

    @classmethod
    def svg_path(cls, default=None):
        # type: (Optional[str]) -> Optional[str]
        """
        Return the folder the svg is contained in.
        Returns None if there is no file.

        .. versionchanged:: 1.1
            A default path can be given which is returned in case no path to the
            SVG file can be determined.
        """
        path = cls.document_path()
        if path:
            return os.path.dirname(path)
        if default:
            return default
        return path  # Return None or '' for context

    @classmethod
    def ext_path(cls):
        # type: () -> str
        """Return the folder the extension script is in"""
        return os.path.dirname(sys.modules[cls.__module__].__file__ or "")

    @classmethod
    def get_resource(cls, name, abort_on_fail=True):
        # type: (str, bool) -> str
        """Return the full filename of the resource in the extension's dir

        .. versionadded:: 1.1"""
        filename = cls.absolute_href(name, cwd=cls.ext_path())
        if abort_on_fail and not os.path.isfile(filename):
            raise AbortExtension(f"Could not find resource file: {filename}")
        return filename

    @classmethod
    def document_path(cls):
        # type: () -> Optional[str]
        """Returns the saved location of the document

         * Normal return is a string containing the saved location
         * Empty string means the document was never saved
         * 'None' means this version of Inkscape doesn't support DOCUMENT_PATH

        DO NOT READ OR WRITE TO THE DOCUMENT FILENAME!

         * Inkscape may have not written the latest changes, leaving you reading old
           data.
         * Inkscape will not respect anything you write to the file, causing data loss.

        .. versionadded:: 1.1
        """
        return os.environ.get("DOCUMENT_PATH", None)

    @classmethod
    def absolute_href(cls, filename, default="~/", cwd=None):
        # type: (str, str, Optional[str]) -> str
        """
        Process the filename such that it's turned into an absolute filename
        with the working directory being the directory of the loaded svg.

        User's home folder is also resolved. So '~/a.png` will be `/home/bob/a.png`

        Default is a fallback working directory to use if the svg's filename is not
        available.

        .. versionchanged:: 1.1
            If you set default to None, then the user will be given errors if
            there's no working directory available from Inkscape.
        """
        filename = os.path.expanduser(filename)
        if not os.path.isabs(filename):
            filename = os.path.expanduser(filename)
        if not os.path.isabs(filename):
            if cwd is None:
                cwd = cls.svg_path(default)
                if cwd is None:
                    raise AbortExtension(
                        "Can not use relative path, Inkscape isn't telling us the "
                        "current working directory."
                    )
                if cwd == "":
                    raise AbortExtension(
                        "The SVG must be saved before you can use relative paths."
                    )
            filename = os.path.join(cwd, filename)
        return os.path.realpath(os.path.expanduser(filename))

    @property
    def name(self):
        # type: () -> str
        """Return a fixed name for this extension"""
        return type(self).__name__


if TYPE_CHECKING:
    _Base = InkscapeExtension
else:
    _Base = object


class TempDirMixin(_Base):  # pylint: disable=abstract-method
    """
    Provide a temporary directory for extensions to stash files.
    """

    dir_suffix = ""
    dir_prefix = "inktmp"

    def __init__(self, *args, **kwargs):
        self.tempdir = None
        self._tempdir = None
        super().__init__(*args, **kwargs)

    def load_raw(self):
        # type: () -> None
        """Create the temporary directory"""
        # pylint: disable=import-outside-toplevel
        from tempfile import TemporaryDirectory

        # Need to hold a reference to the Directory object or else it might get GC'd
        self._tempdir = TemporaryDirectory(  # pylint: disable=consider-using-with
            prefix=self.dir_prefix, suffix=self.dir_suffix
        )
        self.tempdir = os.path.realpath(self._tempdir.name)
        super().load_raw()

    def clean_up(self):
        # type: () -> None
        """Delete the temporary directory"""
        self.tempdir = None
        # if the file does not exist, _tempdir is never set.
        if self._tempdir is not None:
            self._tempdir.cleanup()
        super().clean_up()


class SvgInputMixin(_Base):  # pylint: disable=too-few-public-methods, abstract-method
    """
    Expects the file input to be an svg document and will parse it.
    """

    # Select all objects if none are selected
    select_all: Tuple[Type[IBaseElement], ...] = ()

    def __init__(self):
        super().__init__()

        self.arg_parser.add_argument(
            "--id",
            action="append",
            type=str,
            dest="ids",
            default=[],
            help="id attribute of object to manipulate",
        )

        self.arg_parser.add_argument(
            "--selected-nodes",
            action="append",
            type=str,
            dest="selected_nodes",
            default=[],
            help="id:subpath:position of selected nodes, if any",
        )

    def load(self, stream):
        # type: (IO) -> etree
        """Load the stream as an svg xml etree and make a backup"""
        document = load_svg(stream)
        self.original_document = copy.deepcopy(document)
        self.svg: ISVGDocumentElement = document.getroot()
        self.svg.selection.set(*self.options.ids)
        if not self.svg.selection and self.select_all:
            self.svg.selection = self.svg.descendants().filter(*self.select_all)
        return document


class SvgOutputMixin(_Base):  # pylint: disable=too-few-public-methods, abstract-method
    """
    Expects the output document to be an svg document and will write an etree xml.

    A template can be specified to kick off the svg document building process.
    """

    template = """<svg viewBox="0 0 {width} {height}"
        width="{width}{unit}" height="{height}{unit}"
        xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg"
        xmlns:xlink="http://www.w3.org/1999/xlink"
        xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
        xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">
    </svg>"""

    @classmethod
    def get_template(cls, **kwargs):
        """
        Opens a template svg document for building, the kwargs
        MUST include all the replacement values in the template, the
        default template has 'width' and 'height' of the document.
        """
        kwargs.setdefault("unit", "")
        return load_svg(str(cls.template.format(**kwargs)))

    def save(self, stream):
        # type: (IO) -> None
        """Save the svg document to the given stream"""
        if isinstance(self.document, (bytes, str)):
            document = self.document
        elif "Element" in type(self.document).__name__:
            # isinstance can't be used here because etree is broken
            doc = cast(etree, self.document)
            document = doc.getroot().tostring()
        else:
            raise ValueError(
                f"Unknown type of document: {type(self.document).__name__} can not"
                + "save."
            )

        try:
            stream.write(document)
        except TypeError:
            # we hope that this happens only when document needs to be encoded
            stream.write(document.encode("utf-8"))  # type: ignore


class SvgThroughMixin(SvgInputMixin, SvgOutputMixin):  # pylint: disable=abstract-method
    """
    Combine the input and output svg document handling (usually for effects).
    """

    def has_changed(self, ret):  # pylint: disable=unused-argument
        # type: (Any) -> bool
        """Return true if the svg document has changed"""
        original = etree.tostring(self.original_document)
        result = etree.tostring(self.document)
        return original != result
