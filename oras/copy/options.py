"""
Copy options for the copy engine.

Defines CopyGraphOptions (controls graph traversal behavior) and
CopyOptions (adds root mapping on top), matching oras-go's copy options.
"""

__author__ = "The ORAS Authors"
__license__ = "Apache-2.0"

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from oras.types import Descriptor

# Default concurrency matches dockerd and containerd (3 concurrent copies)
DEFAULT_CONCURRENCY: int = 3

# Default max metadata bytes cached in memory (4 MiB)
DEFAULT_MAX_METADATA_BYTES: int = 4 * 1024 * 1024


@dataclass
class CopyGraphOptions:
    """
    Options controlling the graph copy algorithm.

    Matches oras-go's CopyGraphOptions struct.

    Attributes:
        concurrency: Max number of concurrent copy workers.
            If <= 0, defaults to DEFAULT_CONCURRENCY (3).
        max_metadata_bytes: Max bytes of metadata cached in memory.
            If <= 0, defaults to DEFAULT_MAX_METADATA_BYTES (4 MiB).
        pre_copy: Called before copying a descriptor. Raise SkipNode
            to signal the node was handled externally (e.g., mounted).
        post_copy: Called after a descriptor is successfully copied.
        on_copy_skipped: Called when a node's sub-DAG already exists
            in the destination and is skipped entirely.
        mount_from: Returns candidate repository names from which
            a blob may be mounted. Tried in order; falls back to copy.
        on_mounted: Called when a blob is successfully mounted.
        find_successors: Custom function to discover child nodes of
            a descriptor. If None, oras.copy.graph.successors is used.
        do_chunked: If True, blob uploads to a registry destination use
            chunked upload. Honored by RegistryTarget.push.
        chunk_size: Chunk size in bytes for chunked uploads. If <= 0,
            defaults to oras.defaults.default_chunksize.
    """

    concurrency: int = 0
    max_metadata_bytes: int = 0
    pre_copy: Optional[Callable[[Descriptor], None]] = None
    post_copy: Optional[Callable[[Descriptor], None]] = None
    on_copy_skipped: Optional[Callable[[Descriptor], None]] = None
    mount_from: Optional[Callable[[Descriptor], List[str]]] = None
    on_mounted: Optional[Callable[[Descriptor], None]] = None
    find_successors: Optional[Callable] = None
    do_chunked: bool = False
    chunk_size: int = 0


@dataclass
class CopyOptions:
    """
    Options for the top-level copy() function.

    Extends CopyGraphOptions with root mapping, which transforms
    the resolved root descriptor before copying (e.g., platform selection
    from a manifest index).

    Matches oras-go's CopyOptions struct.

    Attributes:
        graph: Options controlling the graph copy behavior.
        map_root: Optional function that transforms the resolved root
            descriptor. Receives (src, root_desc) and returns a new
            descriptor. Used for platform selection from manifest indexes.
    """

    graph: CopyGraphOptions = field(default_factory=CopyGraphOptions)
    map_root: Optional[Callable] = None
