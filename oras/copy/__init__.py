"""
ORAS Copy Engine.

Provides a complete OCI content copy implementation that copies content
DAGs between OCI targets (registries, OCI layouts, in-memory stores, etc.).

This is a Python port of the copy engine from oras-go
(https://github.com/oras-project/oras-go).

Public API:
    copy()              - Copy content between targets by reference
    CopyOptions         - Options for the copy function
    CopyGraphOptions    - Options for graph traversal behavior
    SkipNode            - Sentinel to skip a node in pre_copy callbacks
    CopyError           - Structured error with operation and origin info
    CopyErrorOrigin     - Source or destination origin enum

Content Protocols:
    Target              - Full read/write target with tag/resolve
    ReadOnlyTarget      - Read-only target with resolve
    Storage             - Content-addressable read/write storage
    ReadOnlyStorage     - Content-addressable read-only storage
    ReferencePusher     - Atomic push with reference tag
    ReferenceFetcher    - Fetch by reference (resolve + fetch in one call)
    Mounter             - Cross-repo blob mounting

Concrete targets that bridge this engine to a registry or an OCI layout:
:class:`oras.content.registry.RegistryTarget` and
:class:`oras.content.layout.LayoutTarget`.
"""

__author__ = "The ORAS Authors"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

from oras.content.storage import (
    Mounter,
    ReadOnlyStorage,
    ReadOnlyTarget,
    ReferenceFetcher,
    ReferencePusher,
    Storage,
    Target,
)
from oras.copy.copy import copy
from oras.copy.errors import CopyError, CopyErrorOrigin
from oras.copy.graph import SkipNode
from oras.copy.options import CopyGraphOptions, CopyOptions
from oras.types import Descriptor

__all__ = [
    # Core function
    "copy",
    # Options
    "CopyOptions",
    "CopyGraphOptions",
    # Sentinel
    "SkipNode",
    # Errors
    "CopyError",
    "CopyErrorOrigin",
    # Types
    "Descriptor",
    # Storage / Target Protocols
    "Storage",
    "ReadOnlyStorage",
    "Target",
    "ReadOnlyTarget",
    # Optional capability Protocols
    "ReferencePusher",
    "ReferenceFetcher",
    "Mounter",
]
