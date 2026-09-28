__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"


# Fallback support so OrasClient still works
from .provider import Registry as OrasClient  # noqa


def __getattr__(name):
    """
    Expose AsyncOrasClient without importing httpx unless it is asked for.

    The async client needs httpx, which is an optional extra, so importing it
    eagerly here would make `import oras.client` fail for anyone who installed
    oras without that extra.
    """
    if name == "AsyncOrasClient":
        from .provider_async import AsyncRegistry

        return AsyncRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
