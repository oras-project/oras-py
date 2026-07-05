"""
Storage and target interfaces for the copy engine.

Defines the Protocol classes (the "from/to" storage + target contract) that
the copy engine checks against, plus the general-purpose helpers built on
them: :class:`FetcherFunc` (callable-to-fetcher adapter) and
:class:`CacheProxy` (read-through metadata cache). Other concrete
realizations live in :mod:`oras.content.memory` (in-memory store) and in the
target adapters :mod:`oras.content.registry` and :mod:`oras.content.layout`;
the copy algorithm in :mod:`oras.copy` consumes these protocols.

These mirror the relevant subset of oras-go's content package interfaces.
Only the protocols the engine actually uses are defined here:

* Type hints: ``ReadOnlyStorage``, ``Storage``, ``ReadOnlyTarget``, ``Target``
* Runtime capability dispatch (``isinstance``): ``ReferenceFetcher``,
  ``ReferencePusher``, ``Mounter``

Note: ``@runtime_checkable`` only verifies the *presence* of methods, not
their signatures (PEP 544). These protocols document intent and drive
capability detection; they do not enforce shape.
"""

__author__ = "The ORAS Authors"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import io
import threading
from typing import BinaryIO, Callable, Tuple

try:
    from typing import Protocol, runtime_checkable  # Python 3.8+
except ImportError:  # Python 3.7
    from typing_extensions import Protocol, runtime_checkable

from oras.types import Descriptor


# ---------------------------------------------------------------------------
# Storage Protocols (content-addressable, keyed by digest)
# ---------------------------------------------------------------------------


@runtime_checkable
class ReadOnlyStorage(Protocol):
    """Read-only content-addressable storage."""

    def fetch(self, desc: Descriptor) -> BinaryIO: ...
    def exists(self, desc: Descriptor) -> bool: ...


@runtime_checkable
class Storage(Protocol):
    """Content-addressable storage with read and write."""

    def fetch(self, desc: Descriptor) -> BinaryIO: ...
    def exists(self, desc: Descriptor) -> bool: ...
    def push(self, desc: Descriptor, content: BinaryIO) -> None: ...


# ---------------------------------------------------------------------------
# Target Protocols (storage + reference resolution / tagging)
# ---------------------------------------------------------------------------


@runtime_checkable
class Target(Protocol):
    """A target that supports full read/write storage + tag/resolve."""

    def fetch(self, desc: Descriptor) -> BinaryIO: ...
    def exists(self, desc: Descriptor) -> bool: ...
    def push(self, desc: Descriptor, content: BinaryIO) -> None: ...
    def tag(self, desc: Descriptor, reference: str) -> None: ...
    def resolve(self, reference: str) -> Descriptor: ...


@runtime_checkable
class ReadOnlyTarget(Protocol):
    """A target that supports read-only storage + resolve."""

    def fetch(self, desc: Descriptor) -> BinaryIO: ...
    def exists(self, desc: Descriptor) -> bool: ...
    def resolve(self, reference: str) -> Descriptor: ...


# ---------------------------------------------------------------------------
# Optional capability Protocols (detected at runtime via isinstance)
# ---------------------------------------------------------------------------


@runtime_checkable
class ReferencePusher(Protocol):
    """Pushes content with a reference tag atomically."""

    def push_reference(
        self, desc: Descriptor, content: BinaryIO, reference: str
    ) -> None: ...


@runtime_checkable
class ReferenceFetcher(Protocol):
    """Fetches content by reference, returning descriptor and content."""

    def fetch_reference(self, reference: str) -> Tuple[Descriptor, BinaryIO]: ...


@runtime_checkable
class Mounter(Protocol):
    """Mounts a blob from another repository, with fallback to copy."""

    def mount(
        self,
        desc: Descriptor,
        from_repo: str,
        get_content: Callable[[], BinaryIO],
    ) -> None: ...


# ---------------------------------------------------------------------------
# FetcherFunc: adapter from a plain callable to a fetcher
# ---------------------------------------------------------------------------


class FetcherFunc:
    """Wraps a callable as a Fetcher."""

    def __init__(self, fn: Callable[[Descriptor], BinaryIO]):
        self._fn = fn

    def fetch(self, desc: Descriptor) -> BinaryIO:
        return self._fn(desc)


# ---------------------------------------------------------------------------
# CacheProxy: read-through caching proxy built on the storage protocols
# ---------------------------------------------------------------------------


class CacheProxy:
    """
    Caching proxy that wraps a ReadOnlyStorage with a local Storage cache.

    Non-leaf nodes (manifests, indexes) are cached in memory for reuse
    during graph traversal. The cache has a byte size limit to prevent
    unbounded memory growth.

    Matches oras-go's internal/cas.Proxy.
    """

    def __init__(self, base: ReadOnlyStorage, cache: Storage, max_bytes: int):
        self.base = base
        self.cache = cache
        self.max_bytes = max_bytes
        self.stop_caching: bool = False
        self._cached_bytes: int = 0
        self._lock = threading.Lock()

    def exists(self, desc: Descriptor) -> bool:
        if self.cache.exists(desc):
            return True
        return self.base.exists(desc)

    def fetch(self, desc: Descriptor) -> BinaryIO:
        # Try cache first (single call avoids TOCTOU)
        try:
            return self.cache.fetch(desc)
        except FileNotFoundError:
            pass

        # Fetch from base
        stream = self.base.fetch(desc)

        if self.stop_caching:
            return stream

        size = desc.get("size", 0)
        with self._lock:
            if self._cached_bytes + size > self.max_bytes:
                return stream
            self._cached_bytes += size

        # Read fully into memory, cache, and return a fresh stream. The base
        # stream is consumed here, so close it to avoid leaking file descriptors
        # for file-backed targets (e.g. LayoutTarget.fetch()). The early-return
        # paths above hand the stream to the caller, who is responsible for it.
        try:
            data = stream.read()
        finally:
            stream.close()
        self.cache.push(desc, io.BytesIO(data))
        return io.BytesIO(data)

    def push(self, desc: Descriptor, content: BinaryIO) -> None:
        """Push delegates to the base (not the cache)."""
        raise NotImplementedError("CacheProxy is read-only; push to base directly")
