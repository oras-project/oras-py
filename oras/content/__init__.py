"""
OCI content layer for the copy engine.

Holds the storage/target Protocol contract and its general-purpose helpers
(read-through cache, callable-fetcher adapter) in :mod:`oras.content.storage`,
and the in-memory store in :mod:`oras.content.memory`, shared by the copy
algorithm and the concrete target adapters.
"""

__author__ = "The ORAS Authors"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"
