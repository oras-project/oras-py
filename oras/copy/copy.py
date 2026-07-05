"""
Top-level copy function for the copy engine.

Orchestrates a complete reference-to-reference copy of OCI content
from a source to a destination, including reference resolution,
root mapping, tag preparation, and graph traversal.

Matches oras-go's Copy function in copy.go.
"""

__author__ = "The ORAS Authors"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import copy as copy_mod
import io
from typing import Optional

from oras.content import storage
from oras.content.memory import MemoryStorage
from oras.content.storage import CacheProxy, FetcherFunc
from oras.copy.errors import CopyError, CopyErrorOrigin
from oras.copy.graph import SkipNode, copy_graph, successors
from oras.copy.options import DEFAULT_MAX_METADATA_BYTES, CopyOptions
from oras.types import Descriptor, descriptors_equal


def copy(
    src: storage.ReadOnlyTarget,
    src_ref: str,
    dst: storage.Target,
    dst_ref: str = "",
    opts: Optional[CopyOptions] = None,
) -> Descriptor:
    """
    Copy content from a source to a destination by reference.

    Resolves the source reference to a root descriptor, optionally maps
    it (e.g., for platform selection), sets up tagging hooks, then
    performs a concurrent graph copy of the entire content DAG.

    Matches oras-go's Copy function.

    Args:
        src: Source target (read-only, must support resolve + fetch + exists).
        src_ref: Source reference string (e.g., "myrepo:v1.0" or digest).
        dst: Destination target (read-write, must support push + tag + resolve).
        dst_ref: Destination reference string. If empty, uses src_ref.
        opts: Copy options. Uses defaults if None.

    Returns:
        The root descriptor that was copied.

    Raises:
        CopyError: If any operation fails, with structured origin info.
        ValueError: If src or dst is None.
    """
    if opts is None:
        opts = CopyOptions()
    else:
        opts = copy_mod.copy(opts)
        opts.graph = copy_mod.copy(opts.graph)

    # Validate inputs
    if src is None:
        raise CopyError(
            "Copy", CopyErrorOrigin.SOURCE, ValueError("nil source target")
        )
    if dst is None:
        raise CopyError(
            "Copy",
            CopyErrorOrigin.DESTINATION,
            ValueError("nil destination target"),
        )

    if not dst_ref:
        dst_ref = src_ref

    # Create caching proxy for non-leaf nodes (manifests, indexes)
    # Ref: https://github.com/oras-project/oras-go/blob/3d90c80fc54d1eeb81dad4073cd9873345e9aebf/content.go#L225
    max_bytes = opts.graph.max_metadata_bytes
    if max_bytes <= 0:
        max_bytes = DEFAULT_MAX_METADATA_BYTES
    proxy = CacheProxy(src, MemoryStorage(), max_bytes)

    # Resolve the source reference to a root descriptor
    root = _resolve_root(src, src_ref, proxy)

    # Apply MapRoot transformation (e.g., platform selection)
    if opts.map_root is not None:
        proxy.stop_caching = True
        try:
            root = opts.map_root(proxy, root)
        except Exception as e:
            raise CopyError("MapRoot", CopyErrorOrigin.SOURCE, e)
        finally:
            proxy.stop_caching = False

    # Prepare copy hooks for tagging at destination
    _prepare_copy(dst, dst_ref, proxy, root, opts)

    # Execute the graph copy
    copy_graph(src, dst, root, proxy, opts.graph)

    return root


def _resolve_root(
    src: storage.ReadOnlyTarget,
    src_ref: str,
    proxy: CacheProxy,
) -> Descriptor:
    """
    Resolve a source reference to a root descriptor.

    If the source supports ReferenceFetcher, uses fetch_reference for
    a single round-trip (resolve + fetch). Otherwise, just resolves.

    The fetched content is fed through ``successors`` to ensure
    it gets cached in the proxy for later use during graph traversal.

    Currently referenceFetcher is not implemented for registry targets.

    Matches oras-go's resolveRoot.
    """
    if isinstance(src, storage.ReferenceFetcher):
        # Optimization: resolve + fetch in one call
        try:
            root, rc = src.fetch_reference(src_ref)
        except Exception as e:
            raise CopyError("FetchReference", CopyErrorOrigin.SOURCE, e)

        try:
            try:
                data = rc.read()
            except Exception as e:
                raise CopyError("FetchReference", CopyErrorOrigin.SOURCE, e)
        finally:
            if hasattr(rc, "close"):
                rc.close()

        def fetch_root(desc):
            if descriptors_equal(desc, root):
                return io.BytesIO(data)
            raise ValueError("fetching only root node expected")

        fetcher = FetcherFunc(fetch_root)
        try:
            successors(fetcher, root)
        except Exception as e:
            raise CopyError("Successors", CopyErrorOrigin.SOURCE, e)

        return root

    # Standard path: resolve only
    try:
        return src.resolve(src_ref)
    except Exception as e:
        raise CopyError("Resolve", CopyErrorOrigin.SOURCE, e)


def _prepare_copy(
    dst: storage.Target,
    dst_ref: str,
    proxy: CacheProxy,
    root: Descriptor,
    opts: CopyOptions,
) -> None:
    """
    Set up pre/post copy hooks to ensure the root gets tagged at
    the destination.

    Two paths:
    1. If dst supports ReferencePusher: intercept pre_copy for the root
       to atomically push + tag, then return SkipNode.
    2. Otherwise: intercept post_copy for the root to call dst.tag().

    Also intercepts on_copy_skipped so the root gets tagged even when
    its content already exists at the destination.

    Matches oras-go's prepareCopy.
    """
    if isinstance(dst, storage.ReferencePusher):
        # Path A: Atomic push + tag via ReferencePusher
        original_pre_copy = opts.graph.pre_copy

        def tagged_pre_copy(desc: Descriptor) -> None:
            if original_pre_copy is not None:
                original_pre_copy(desc)
            if not descriptors_equal(desc, root):
                return
            # Push root with reference atomically
            _copy_cached_node_with_reference(proxy, dst, desc, dst_ref)
            if opts.graph.post_copy is not None:
                opts.graph.post_copy(desc)
            raise SkipNode()

        opts.graph.pre_copy = tagged_pre_copy
    else:
        # Path B: Tag after copy
        original_post_copy = opts.graph.post_copy

        def tagged_post_copy(desc: Descriptor) -> None:
            if descriptors_equal(desc, root):
                try:
                    dst.tag(root, dst_ref)
                except Exception as e:
                    raise CopyError("Tag", CopyErrorOrigin.DESTINATION, e)
            if original_post_copy is not None:
                original_post_copy(desc)

        opts.graph.post_copy = tagged_post_copy

    # Handle the case where root already exists (skipped)
    original_on_copy_skipped = opts.graph.on_copy_skipped

    def tagged_on_copy_skipped(desc: Descriptor) -> None:
        if not descriptors_equal(desc, root):
            if original_on_copy_skipped is not None:
                original_on_copy_skipped(desc)
            return

        # Root was skipped but still needs to be tagged
        if isinstance(dst, storage.ReferencePusher):
            _copy_cached_node_with_reference(proxy, dst, desc, dst_ref)
            return

        if original_on_copy_skipped is not None:
            original_on_copy_skipped(desc)

        try:
            dst.tag(root, dst_ref)
        except Exception as e:
            raise CopyError("Tag", CopyErrorOrigin.DESTINATION, e)

    opts.graph.on_copy_skipped = tagged_on_copy_skipped


def _copy_cached_node_with_reference(
    proxy: CacheProxy,
    dst: storage.ReferencePusher,
    desc: Descriptor,
    reference: str,
) -> None:
    """
    Push a node to the destination with a reference tag.

    The content is normally already in the proxy cache (fetched during
    graph traversal). When the root already exists at the destination its
    sub-DAG is skipped and never fetched, so the cache may miss; in that
    case we fall back to fetching from the source via the proxy. This
    matches oras-go's copyCachedNodeWithReference, which uses FetchCached
    (cache-or-source), not a cache-only read.
    """
    rc = proxy.fetch(desc)
    try:
        data = rc.read()
    finally:
        if hasattr(rc, "close"):
            rc.close()
    dst.push_reference(desc, io.BytesIO(data), reference)
