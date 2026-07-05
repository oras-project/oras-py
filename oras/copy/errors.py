"""
Error types for the copy engine.

Matches oras-go's copyerror.go with structured error reporting
that includes the operation name and origin (source or destination).
"""

__author__ = "The ORAS Authors"
__license__ = "Apache-2.0"

import enum


class CopyErrorOrigin(enum.IntEnum):
    """Indicates whether a copy error originated at the source or destination."""

    SOURCE = 1
    DESTINATION = 2

    def __str__(self) -> str:
        if self == CopyErrorOrigin.SOURCE:
            return "source"
        return "destination"


class CopyError(Exception):
    """
    Structured error from a copy operation.

    Includes the operation that failed (e.g., "Fetch", "Push", "Exists"),
    the origin (source or destination), and the underlying error.

    Matches oras-go's CopyError type.
    """

    def __init__(self, op: str, origin: CopyErrorOrigin, err: Exception):
        self.op = op
        self.origin = origin
        self.err = err
        super().__init__(f'failed to perform "{op}" on {origin}: {err}')
