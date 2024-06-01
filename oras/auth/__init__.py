import requests

from oras.logger import logger

from .basic import BasicAuth
from .token import TokenAuth

auth_backends = {"token": TokenAuth, "basic": BasicAuth}


def get_auth_backend(name="token", session=None, **kwargs):
    backend = auth_backends.get(name)
    if not backend:
        logger.exit(f"Authentication backend {backend} is not known.")
    backend = backend(**kwargs)
    backend.session = session or requests.Session()
    return backend
