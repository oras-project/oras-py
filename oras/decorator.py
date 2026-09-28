__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import asyncio
import ssl
import time
from functools import wraps
from typing import Optional

import requests.exceptions

import oras.auth
from oras.logger import logger
from oras.transport import response_reason


def check_5xx(res):
    """
    Raise if a response is a server error, after logging what the registry said.

    Whether a response is worth retrying is a decision, not an execution
    detail, so the synchronous and asynchronous retries share it.

    :param res: the response to inspect
    """
    if res.status_code == 500:
        try:
            msg = res.json()
            for error in msg.get("errors", []):
                if isinstance(error, dict) and "message" in error:
                    logger.error(error["message"])
        except Exception:
            pass
        raise ValueError(f"Issue with {res.request.url}: {response_reason(res)}")


def is_certificate_error(error: BaseException) -> bool:
    """
    Whether a failure is a TLS problem rather than something transient.

    requests raises a distinct SSLError, which the synchronous retry re-raises
    at once: a bad certificate or the wrong hostname will not fix itself, and
    sleeping through the attempts only delays the message. httpx has no such
    class - a certificate failure and a refused connection are both a
    ConnectError - so the cause chain is what tells them apart. A refused
    connection is still worth retrying; a certificate is not.

    :param error: the exception a request raised
    """
    seen = set()
    cause: Optional[BaseException] = error
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause, ssl.SSLError):
            return True
        cause = cause.__cause__ or cause.__context__
    return False


def backoff_seconds(attempt: int, timeout: int) -> int:
    """
    How long to wait before retrying, shared by both retries.

    :param attempt: how many attempts have already failed
    :type attempt: int
    :param timeout: the base wait
    :type timeout: int
    """
    return timeout + 3**attempt


def ensure_container(func):
    """
    Ensure the first argument is a container, and not a string.
    """

    @wraps(func)
    def wrapper(cls, *args, **kwargs):
        if "container" in kwargs:
            kwargs["container"] = cls.get_container(kwargs["container"])
        elif args:
            container = cls.get_container(args[0])
            args = (container, *args[1:])
        return func(cls, *args, **kwargs)

    return wrapper


def retry(attempts=5, timeout=2):
    """
    A simple retry decorator
    """

    def decorator(func):
        @wraps(func)
        def inner(*args, **kwargs):
            attempt = 0
            while attempt < attempts:
                try:
                    res = func(*args, **kwargs)
                    check_5xx(res)
                    return res
                except oras.auth.AuthenticationException as e:
                    raise e
                except (requests.exceptions.SSLError, ImportError):
                    raise
                except Exception as e:
                    sleep = backoff_seconds(attempt, timeout)
                    logger.info(f"Retrying in {sleep} seconds - error: {e}")
                    time.sleep(sleep)
                    attempt += 1
            return func(*args, **kwargs)

        return inner

    return decorator


def retry_async(attempts=5, timeout=2):
    """
    The asynchronous counterpart to retry.

    The policy is the same and is shared through check_5xx and
    backoff_seconds; only waiting and calling differ, since neither can be
    written once for both execution models.

    asyncio.CancelledError derives from BaseException, so `except Exception`
    does not catch it and a cancelled request stops retrying immediately.
    """

    def decorator(func):
        @wraps(func)
        async def inner(*args, **kwargs):
            attempt = 0
            while attempt < attempts:
                try:
                    res = await func(*args, **kwargs)
                    check_5xx(res)
                    return res
                except oras.auth.AuthenticationException as e:
                    raise e
                except ImportError:
                    raise
                except Exception as e:
                    # httpx reports a bad certificate as an ordinary
                    # ConnectError, so it has to be recognised rather than
                    # caught by class, or it would sleep through every attempt
                    # before the user is told the certificate is wrong.
                    if is_certificate_error(e):
                        raise
                    sleep = backoff_seconds(attempt, timeout)
                    logger.info(f"Retrying in {sleep} seconds - error: {e}")
                    await asyncio.sleep(sleep)
                    attempt += 1
            return await func(*args, **kwargs)

        return inner

    return decorator
