# OneNoteExtractor
# Copyright © 2023, Volexity, Inc
# All rights reserved.

# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

#     Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#     Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#     Neither the name of the Volexity, Inc nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS “AS IS” AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL Volexity, Inc BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


"""This is a temporary inclusion in this project to address an unknown issue when using msoffcrypto.

https://github.com/volexity/threat-intel/issues/7

Much of the code in this file was borrowed from:

https://github.com/nolze/msoffcrypto-tool/blob/master/msoffcrypto/method/ecma376_agile.py

Changes are highlighted using "#!NOTE".
"""

# builtins
import functools
import logging
from hashlib import sha1, sha256, sha384, sha512
from io import BytesIO
from struct import pack, unpack
from typing import Callable

# Install pyaes
import pyaes

ALGORITHM_HASH = {
    "SHA1": sha1,
    "SHA256": sha256,
    "SHA384": sha384,
    "SHA512": sha512,
}

logger = logging.getLogger(__name__)


def _get_hash_func(algorithm: str) -> Callable:
    return ALGORITHM_HASH.get(algorithm, sha1)


def decrypt(
    key: bytes, key_data_salt: bytes, hash_algorithm: str, ibuf: BytesIO
) -> bytes:
    r"""Return decrypted data.

    >>> key = b'@ f\t\xd9\xfa\xad\xf2K\x07j\xeb\xf2\xc45\xb7B\x92\xc8\xb8\xa7\xaa\x81\xbcg\x9b\xe8\x97\x11\xb0*\xc2'
    >>> keyDataSalt = b'\x8f\xc7x"+P\x8d\xdcL\xe6\x8c\xdd\x15<\x16\xb4'
    >>> hashAlgorithm = 'SHA512'
    """
    hash_calc = _get_hash_func(hash_algorithm)

    obuf = BytesIO()
    total_size = unpack("<I", ibuf.read(4))[0]
    logger.debug("totalSize: %s", total_size)
    remaining = total_size
    ibuf.seek(8)
    # !NOTE - the key change made is that instead of iterating over 4KB segments,
    # we read the data in a single buffer, this resolves the issue outlined
    # in the docstrings of this file.
    buf = ibuf.read(total_size)
    i = 0  # Block index
    salt_with_block_key = key_data_salt + pack("<I", i)
    iv = hash_calc(salt_with_block_key).digest()
    iv = iv[:16]

    # Initialize AES decrypter using pyaes
    aes = pyaes.AESModeOfOperationCBC(key, iv)

    # Decrypt the data
    dec = aes.decrypt(buf)

    # Handle any extra bytes if necessary
    if remaining < len(dec):
        dec = dec[:remaining]
    obuf.write(dec)
    return obuf.getvalue()
