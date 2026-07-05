"""
Status tracker for content deduplication during graph copy.

Ensures each descriptor is processed exactly once across concurrent
workers, matching oras-go's internal/status.Tracker.
"""

__author__ = "The ORAS Authors"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import threading
from typing import Tuple

from oras.types import Descriptor, descriptor_key


class StatusTracker:
    """
    Thread-safe tracker that ensures each content descriptor is
    processed exactly once during a copy operation.

    Uses a lock-protected dict mapping descriptor keys to Events.
    When a worker calls try_commit(), it either:
    - Claims the descriptor (returns event, True) and is responsible for
      processing it and then setting the event when done.
    - Finds it already claimed (returns event, False) and can wait on the
      event for the other worker to finish.

    Matches oras-go's internal/status.Tracker using sync.Map + chan struct{}.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._status: dict = {}  # descriptor_key -> threading.Event

    def try_commit(self, desc: Descriptor) -> Tuple[threading.Event, bool]:
        """
        Atomically try to claim ownership of a descriptor.

        Returns:
            (event, committed): If committed is True, the caller owns
            the descriptor and must call event.set() when done.
            If False, another worker owns it; wait on the event.
        """
        key = descriptor_key(desc)
        with self._lock:
            if key in self._status:
                return self._status[key], False
            event = threading.Event()
            self._status[key] = event
            return event, True
