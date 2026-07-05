"""
Registry target adapter for the copy engine.

Adapts a :class:`oras.provider.Registry` plus a repository (container) string
into the copy engine's ``Target``, ``ReferencePusher``, and ``Mounter``
protocols, so a remote registry repository can act as a copy source or
destination.
"""

__author__ = "The ORAS Authors"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import io
import os
import shutil
import tempfile
from typing import TYPE_CHECKING, BinaryIO, Callable, Optional

import requests

import oras.defaults
import oras.utils
from oras.types import Descriptor

if TYPE_CHECKING:
    from oras.copy.options import CopyOptions
    from oras.provider import Registry


# Broad Accept header covering all manifest media types for RegistryTarget.resolve().
# Derived from the canonical list in oras.defaults so the supported manifest
# media types live in exactly one place (shared with _is_manifest below and
# Registry.get_manifest in provider.py).
_ACCEPT_ALL_MANIFESTS = ", ".join(oras.defaults.default_manifest_accepted_media_types)


def _is_manifest(desc: Descriptor) -> bool:
    """Check if a descriptor refers to a manifest or index by media type."""
    media_type = desc.get("mediaType", "")
    return media_type in oras.defaults.default_manifest_accepted_media_types


class RegistryTarget:
    """
    Adapts a :class:`Registry` + container string into the copy engine's
    Target, ReferencePusher, and Mounter protocols.

    All operations are scoped to the single repository identified
    by the container string passed at construction time.
    """

    def __init__(
        self,
        registry: "Registry",
        container: str,
        opts: "Optional[CopyOptions]" = None,
    ):
        self._registry = registry
        self._container = registry.get_container(container)
        self._registry.auth.load_configs(self._container)
        self._opts = opts
        # Records the most recent manifest PUT response (from push /
        # push_reference) so callers like Registry.push can return the real
        # upload response rather than issuing a follow-up GET.
        self.last_manifest_response: "Optional[requests.Response]" = None

    def _manifest_url(self, ref: str) -> str:
        """Build full manifest URL for a reference (tag or digest)."""
        return f"{self._registry.prefix}://{self._container.manifest_url(ref)}"

    def _upload_blob_url(self) -> str:
        """Build full upload blob URL."""
        return f"{self._registry.prefix}://{self._container.upload_blob_url()}"

    def _put_manifest(
        self, reference: str, data: bytes, media_type: str, record: bool
    ) -> requests.Response:
        """PUT manifest bytes to a reference (tag or digest).

        Shared by :meth:`push` (manifest branch), :meth:`tag`, and
        :meth:`push_reference`. When ``record`` is True the response is stored
        on ``last_manifest_response`` so callers like ``Registry.push`` can
        return the real upload response instead of issuing a follow-up GET.
        """
        url = self._manifest_url(reference)
        headers = {"Content-Type": media_type}
        response = self._registry.do_request(
            url, "PUT", data=data, headers=headers
        )
        if record:
            self.last_manifest_response = response
        self._registry._check_200_response(response)
        return response

    def _head_manifest(self, reference: str) -> requests.Response:
        """Issue a HEAD for a manifest reference with a broad Accept header."""
        url = self._manifest_url(reference)
        headers = {"Accept": _ACCEPT_ALL_MANIFESTS}
        return self._registry.do_request(url, "HEAD", headers=headers)

    def fetch(self, desc: Descriptor) -> BinaryIO:
        """Fetch content for a descriptor. Routes blob vs manifest."""
        if _is_manifest(desc):
            url = self._manifest_url(desc["digest"])
            headers = {"Accept": desc.get("mediaType", "")}
            response = self._registry.do_request(url, "GET", headers=headers)
            self._registry._check_200_response(response)
            return io.BytesIO(response.content)
        else:
            response = self._registry.get_blob(self._container, desc["digest"])
            self._registry._check_200_response(response)
            return io.BytesIO(response.content)

    def exists(self, desc: Descriptor) -> bool:
        """Check if content exists. Routes blob vs manifest."""
        if _is_manifest(desc):
            return self._head_manifest(desc["digest"]).status_code == 200
        return self._registry.blob_exists(desc, self._container)

    def push(self, desc: Descriptor, content: BinaryIO) -> None:
        """Push content for a descriptor. Routes blob vs manifest."""
        if _is_manifest(desc):
            data = content.read()
            self._put_manifest(
                desc["digest"], data, desc.get("mediaType", ""), record=True
            )
        else:
            tmp = None
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                # Stream rather than buffer: large layers (and chunked
                # uploads) must not be fully materialized in memory.
                shutil.copyfileobj(content, tmp)
                tmp.close()
                do_chunked = False
                chunk_size = oras.defaults.default_chunksize
                if self._opts is not None:
                    do_chunked = self._opts.graph.do_chunked
                    chunk_size = (
                        self._opts.graph.chunk_size
                        or oras.defaults.default_chunksize
                    )
                response = self._registry.upload_blob(
                    tmp.name,
                    self._container,
                    desc,
                    do_chunked=do_chunked,
                    chunk_size=chunk_size,
                )
                # upload_blob returns the response rather than raising, so a
                # non-2xx here must be surfaced or the copy would appear to
                # succeed while the blob was never uploaded.
                self._registry._check_200_response(response)
            finally:
                if tmp is not None:
                    try:
                        tmp.close()
                    except Exception:
                        pass
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass

    def tag(self, desc: Descriptor, reference: str) -> None:
        """Tag a descriptor with a reference by re-uploading the manifest."""
        data = self.fetch(desc).read()
        self._put_manifest(
            reference, data, desc.get("mediaType", ""), record=False
        )

    def resolve(self, reference: str) -> Descriptor:
        """Resolve a reference to a descriptor via HEAD request."""
        response = self._head_manifest(reference)
        self._registry._check_200_response(response)
        return {
            "mediaType": response.headers.get("Content-Type", ""),
            "digest": response.headers.get("Docker-Content-Digest", ""),
            "size": int(response.headers.get("Content-Length", 0)),
        }

    def push_reference(
        self, desc: Descriptor, content: BinaryIO, reference: str
    ) -> None:
        """Atomic push + tag: PUT manifest bytes to the reference URL."""
        data = content.read()
        self._put_manifest(
            reference, data, desc.get("mediaType", ""), record=True
        )

    def mount(
        self,
        desc: Descriptor,
        from_repo: str,
        get_content: Callable[[], BinaryIO],
    ) -> None:
        """
        Attempt cross-repo blob mount, falling back to regular upload.

        POSTs to the blob upload endpoint with mount and from params.
        If the registry returns 201, the mount succeeded. If 202, the
        mount failed and we complete the upload session with get_content().
        """
        url = oras.utils.append_url_params(
            self._upload_blob_url(),
            {"mount": desc["digest"], "from": from_repo},
        )
        response = self._registry.do_request(url, "POST")
        if response.status_code == 201:
            return  # Mount succeeded

        # Mount failed (202) — fall back to regular upload. Close the stream
        # after reading: for file-backed sources (e.g. LayoutTarget) it is an
        # open file handle, and repeated mounts would otherwise leak descriptors.
        content = get_content()
        try:
            data = content.read()
        finally:
            content.close()
        session_url = self._registry._get_location(response, self._container)
        if not session_url:
            raise ValueError("Mount fallback: no session URL in response")

        blob_url = oras.utils.append_url_params(
            session_url, {"digest": desc["digest"]}
        )
        headers = {
            "Content-Length": str(len(data)),
            "Content-Type": "application/octet-stream",
        }
        response = self._registry.do_request(
            blob_url, "PUT", data=data, headers=headers
        )
        self._registry._check_200_response(response)
