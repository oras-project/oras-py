import requests

from .basic import BasicAuth
from .token import TokenAuth

auth_backends = {"token": TokenAuth, "basic": BasicAuth}


class AuthenticationException(Exception):
    """
    An exception to raise when Authentication errors are fatal
    """

    pass


def get_auth_backend(name="token", session=None, **kwargs):
    backend = auth_backends.get(name)
    if not backend:
        raise ValueError(f"Authentication backend {backend} is not known.")
    backend = backend(**kwargs)
    backend.session = session or requests.Session()
    return backend
