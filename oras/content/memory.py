"""
In-memory content storage implementation.

``MemoryStorage`` is a standalone, thread-safe in-memory content-addressable
store — a concrete realization of the storage protocols in
:mod:`oras.content.storage`, where the general-purpose ``FetcherFunc`` adapter
and the read-through ``CacheProxy`` cache also live.

Matches oras-go's content.Memory.
"""

__author__ = "The ORAS Authors"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import io
import threading
from typing import BinaryIO

from oras.types import Descriptor


# ---------------------------------------------------------------------------
# MemoryStorage: Thread-safe in-memory content-addressable storage
# ---------------------------------------------------------------------------


class MemoryStorage:
    """Thread-safe in-memory content storage keyed by digest."""

    def __init__(self):
        self._lock = threading.Lock()
        self._content: dict = {}  # digest -> bytes

    def exists(self, desc: Descriptor) -> bool:
        digest = desc.get("digest", "")
        with self._lock:
            return digest in self._content

    def fetch(self, desc: Descriptor) -> BinaryIO:
        digest = desc.get("digest", "")
        with self._lock:
            data = self._content.get(digest)
        if data is None:
            raise FileNotFoundError(f"content not found: {digest}")
        return io.BytesIO(data)

    def push(self, desc: Descriptor, content: BinaryIO) -> None:
        data = content.read()
        digest = desc.get("digest", "")
        with self._lock:
            self._content[digest] = data
