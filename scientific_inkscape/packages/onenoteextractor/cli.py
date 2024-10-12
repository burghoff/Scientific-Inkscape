# OneNoteExtractor
# Copyright © 2023, Volexity, Inc
# All rights reserved.

# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

#     Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#     Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#     Neither the name of the Volexity, Inc nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS “AS IS” AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL Volexity, Inc BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Example script showing use of OneNoteExtractor."""

import argparse
import logging
import sys
import textwrap
from pathlib import Path

from one import OneNoteExtractor
# from ._version import __version__
__version__ ='beta'

logger = logging.getLogger(__name__)

import struct

def is_emf(file_data: bytes) -> bool:
    """Check if the file_data represents an EMF file by inspecting the header."""
    if len(file_data) < 88:
        return False  # EMF header should be at least 88 bytes
    
    # Unpack the first 4 bytes to get the Record Type
    record_type, = struct.unpack('<I', file_data[0:4])
    # Unpack bytes 40 to 44 to get the Signature
    signature, = struct.unpack('<I', file_data[40:44])
    
    # EMF specific values
    EMR_HEADER = 0x00000001
    EMF_SIGNATURE = 0x464D4520  # ' EMF' in ASCII (note the leading space)
    
    return record_type == EMR_HEADER and signature == EMF_SIGNATURE
def is_png(file_data: bytes) -> bool:
    """Check if the file_data represents a PNG file by inspecting the header."""
    return file_data.startswith(b'\x89PNG\r\n\x1a\n')

def is_jpeg(file_data: bytes) -> bool:
    """Check if the file_data represents a JPEG file by inspecting the header."""
    return file_data.startswith(b'\xFF\xD8\xFF')


def run() -> None:
    
    print('hello')
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(
            f"""
            Volexity OneNoteExtractor | Extract metadata and/or files from OneNote files
            Version {__version__}
            https://www.volexity.com
            (C) 2023 Volexity, Inc. All rights reserved"""
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("target_file", type=str, help="Input file to parse")
    parser.add_argument("--debug", help="If enabled, sets log level to debug", action="store_true")
    parser.add_argument("--extract-meta", help="If set, extracts metadata from .one file", action="store_true")
    parser.add_argument("--extract-files", help="If set, extracts files from .one file", action="store_true")
    parser.add_argument("--output-directory", help="Where should extracted objects be saved to?", default=Path.cwd())
    parser.add_argument(
        "--password", help="Password to use to extract files from encrypted " "onenote files", action="store"
    )
    parser.add_argument("--version", action="version", help="print the version of one-extract", version=__version__)
    args = parser.parse_args()
    
    print('hello')

    if not args.extract_meta and not args.extract_files:
        sys.exit("Must either attempt to extract metadata or files.")

    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(name)s %(levelname)-8s %(message)s",
            handlers=[logging.StreamHandler()],
        )
        logger.debug("Debug logging enabled.")
    with Path(args.target_file).open("rb") as infile:
        data = infile.read()

    document = OneNoteExtractor(data=data, password=args.password)
    # Extract subfile objects from the document
    if args.extract_files:
        for index, file_data in enumerate(document.extract_files()):
            bn = Path(args.target_file).stem  # Use stem to get filename without extension
    
            # Detect the file type
            if is_emf(file_data):
                extension = '.emf'
            elif is_png(file_data):
                extension = '.png'
            elif is_jpeg(file_data):
                extension = '.jpg'
            else:
                extension = '.bin'  # Default extension for unknown types
    
            target_path = Path(args.output_directory) / f"{bn}_{index}{extension}"
            print(f"Writing extracted file to: {target_path}")
            with target_path.open("wb") as outf:
                outf.write(file_data)


    # Extract metadata from the document
    if args.extract_meta:
        for on_meta in document.extract_meta():
            print(on_meta)  # noqa: T201

if __name__ == "__main__":
    run()
