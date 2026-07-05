"""
OCI layout target adapter for the copy engine.

Adapts a :class:`oras.layout.layout.Layout` directory into the copy engine's
``Target`` protocol, providing content-addressable blob storage plus
reference resolution/tagging via the layout's index.json.
"""

__author__ = "The ORAS Authors"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import os
import pathlib
import re
import shutil
import tempfile
import threading
from typing import TYPE_CHECKING, BinaryIO

import oras.defaults
from oras.types import Descriptor
from oras.utils.fileio import read_json, write_json

if TYPE_CHECKING:
    from oras.layout.layout import Layout


_VALID_DIGEST_RE = re.compile(r"^[a-z0-9]+:[a-f0-9]+$")


class LayoutTarget:
    """
    Adapts a :class:`Layout` directory into the copy engine's Target protocol.

    Provides full read/write access to the OCI layout's content-addressable
    blobs and manages references via the layout's index.json annotations.

    Implements Target (fetch, exists, push, tag, resolve), so it can serve
    as both source and destination in :func:`oras.copy.copy`.
    """

    def __init__(self, layout: "Layout"):
        self._layout = layout
        self._index_lock = threading.Lock()

    @staticmethod
    def _validate_digest(digest: str) -> None:
        if not _VALID_DIGEST_RE.match(digest):
            raise ValueError(f"invalid digest format: {digest!r}")

    def fetch(self, desc: Descriptor) -> BinaryIO:
        """Fetch blob content by digest, returning an open file handle."""
        digest = desc["digest"]
        self._validate_digest(digest)
        path = self._layout.digest_to_blob_path(digest)
        return open(path, "rb")

    def exists(self, desc: Descriptor) -> bool:
        """Check if a blob exists on disk."""
        digest = desc["digest"]
        self._validate_digest(digest)
        return self._layout.blob_exists(digest)

    def push(self, desc: Descriptor, content: BinaryIO) -> None:
        """Write blob content to the layout (content-addressed, deduplicated).

        Matching oras-go's Store.Push: skips silently if the blob already
        exists (same digest), otherwise writes atomically via a temp file +
        rename so concurrent writers never observe a partial blob.
        """
        digest = desc["digest"]
        self._validate_digest(digest)

        self._layout.init()

        path = self._layout.digest_to_blob_path(digest)
        if path.exists():
            return  # already present — deduplicate silently

        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent))
        try:
            # Stream rather than buffer: large blobs must not be fully
            # materialized in memory.
            with os.fdopen(tmp_fd, "wb") as f:
                shutil.copyfileobj(content, f)
            os.replace(tmp_name, str(path))
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def tag(self, desc: Descriptor, reference: str) -> None:
        """Update index.json to associate the descriptor with a reference tag.

        Matching oras-go's Store.Tag: finds an existing index.json entry for
        this reference and replaces it, or appends a new one.
        Thread-safe via _index_lock.
        """
        self._layout.init()

        layout_dir = pathlib.Path(self._layout._oci_layout_path)
        index_path = layout_dir / oras.defaults.oci_image_index_file

        new_entry = {
            "mediaType": desc.get("mediaType", ""),
            "digest": desc["digest"],
            "size": desc.get("size", 0),
            "annotations": {oras.defaults.oci_ref_name_annotation: reference},
        }

        with self._index_lock:
            index_data = read_json(str(index_path))
            manifests = index_data.setdefault("manifests", [])

            for i, entry in enumerate(manifests):
                if (
                    entry.get("annotations", {}).get(
                        oras.defaults.oci_ref_name_annotation
                    )
                    == reference
                ):
                    manifests[i] = new_entry
                    break
            else:
                manifests.append(new_entry)

            write_json(index_data, str(index_path))

    def resolve(self, reference: str) -> Descriptor:
        """Resolve a reference tag to a descriptor via index.json."""
        entry = self._layout.find_index_entry(reference)
        if entry is None:
            raise FileNotFoundError(
                f"Reference not found in layout index: {reference}"
            )
        return {
            "mediaType": entry.get("mediaType", ""),
            "digest": entry.get("digest", ""),
            "size": entry.get("size", 0),
        }
