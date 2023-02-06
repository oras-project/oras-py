__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import time
from functools import partial, update_wrapper

from oras.logger import logger


class Decorator:
    """
    Shared parent decorator class
    """

    def __init__(self, func):
        update_wrapper(self, func)
        self.func = func

    def __get__(self, obj, objtype):
        return partial(self.__call__, obj)


class ensure_container(Decorator):
    """
    Ensure the first argument is a container, and not a string.
    """

    def __call__(self, cls, *args, **kwargs):
        if "container" in kwargs:
            kwargs["container"] = cls.get_container(kwargs["container"])
        elif args:
            container = cls.get_container(args[0])
            args = (container, *args[1:])
        return self.func(cls, *args, **kwargs)


class classretry(Decorator):
    """
    Retry a function that is part of a class
    """

    def __init__(self, func, attempts=5, timeout=2):
        super().__init__(func)
        self.attempts = attempts
        self.timeout = timeout

    def __call__(self, cls, *args, **kwargs):
        attempt = 0
        attempts = self.attempts
        timeout = self.timeout
        while attempt < attempts:
            try:
                return self.func(cls, *args, **kwargs)
            except Exception as e:
                sleep = timeout + 3**attempt
                logger.info(f"Retrying in {sleep} seconds - error: {e}")
                time.sleep(sleep)
                attempt += 1
        return self.func(cls, *args, **kwargs)


def retry(attempts, timeout=2):
    """
    A simple retry decorator
    """

    def decorator(func):
        def inner(*args, **kwargs):
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

        return inner

    return decorator
