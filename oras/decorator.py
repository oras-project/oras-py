__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import time
import functools

from oras.logger import logger
from oras.provider import Registry


def ensure_container(fn):
    @functools.wraps(fn)
    def wrapper(self: Registry, *args, **kwargs):
        if "container" in kwargs:
            kwargs["container"] = self.get_container(kwargs["container"])
        elif args:
            container = self.get_container(args[0])
            args = (container, *args[1:])
        return fn(self, *args, **kwargs)

    return wrapper


def retry(func):
    """
    A simple retry decorator
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        attempts = 5
        timeout = 2
        attempt = 0
        while attempt < attempts:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                sleep = timeout + 3**attempt
                logger.info(f"Retrying in {sleep} seconds - error: {e}")
                time.sleep(sleep)
                attempt += 1
        return func(*args, **kwargs)

    return wrapper
