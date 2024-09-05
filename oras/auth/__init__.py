from typing import Dict, Literal, Optional

import requests

from oras.auth.base import AuthBackend
from oras.logger import logger

from .basic import BasicAuth
from .token import TokenAuth

AuthBackendName = Literal["token", "basic"]

auth_backends: Dict[AuthBackendName, type[AuthBackend]] = {
    "token": TokenAuth,
    "basic": BasicAuth,
}


def get_auth_backend(
    name: AuthBackendName = "token",
    session: Optional[requests.Session] = None,
    **kwargs,
):
    backend = auth_backends.get(name)
    if not backend:
        return logger.exit(f"Authentication backend {backend} is not known.")
    _session = session or requests.Session()
    backend = backend(session=_session, **kwargs)
    return backend
