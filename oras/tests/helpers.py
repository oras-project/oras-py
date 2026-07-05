"""
Shared test helpers for the oras test suite.

Plain helper module (not a conftest) so it can be safely imported by tests.
Pytest may load ``conftest.py`` under its own internal module name, and
importing it as a package module can cause it to execute twice, leading to
confusing fixture/state duplication. Reusable helpers therefore live here.
"""

import io
import threading
from typing import BinaryIO, Dict, Optional

from oras.types import Descriptor


class InMemoryTarget:
    """
    Thread-safe in-memory Target for copy engine tests.

    Implements the full Target protocol (fetch, exists, push, tag, resolve)
    using plain dicts backed by a threading.Lock. Raises FileExistsError
    on duplicate push so copy engine idempotency handling is exercised.
    """

    def __init__(self):
        self._content: Dict[str, bytes] = {}
        self._tags: Dict[str, Descriptor] = {}
        self._lock = threading.Lock()

    def fetch(self, desc: Descriptor) -> BinaryIO:
        digest = desc.get("digest", "")
        with self._lock:
            data = self._content.get(digest)
        if data is None:
            raise FileNotFoundError(f"content not found: {digest}")
        return io.BytesIO(data)

    def exists(self, desc: Descriptor) -> bool:
        digest = desc.get("digest", "")
        with self._lock:
            return digest in self._content

    def push(self, desc: Descriptor, content: BinaryIO) -> None:
        data = content.read()
        digest = desc.get("digest", "")
        with self._lock:
            if digest in self._content:
                raise FileExistsError(f"content already exists: {digest}")
            self._content[digest] = data

    def tag(self, desc: Descriptor, reference: str) -> None:
        with self._lock:
            self._tags[reference] = desc

    def resolve(self, reference: str) -> Descriptor:
        with self._lock:
            desc = self._tags.get(reference)
        if desc is None:
            raise FileNotFoundError(f"reference not found: {reference}")
        return desc

    def get_content(self, digest: str) -> bytes:
        with self._lock:
            return self._content.get(digest, b"")

    def get_tag(self, reference: str) -> Optional[Descriptor]:
        with self._lock:
            return self._tags.get(reference)
