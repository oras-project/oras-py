from oras.transport import Transport

from .basic import BasicAuth
from .ecr import EcrAuth
from .token import TokenAuth

auth_backends = {"token": TokenAuth, "basic": BasicAuth, "ecr": EcrAuth}


class AuthenticationException(Exception):
    """
    An exception to raise when Authentication errors are fatal
    """

    pass


def get_auth_backend(
    name="token",
    session=None,
    insecure=False,
    tls_verify=True,
    transport=None,
    **kwargs,
):
    """
    Get an auth backend by name, ready to send requests.

    :param name: name of the backend to create
    :type name: str
    :param session: a session for the backend to use, if no transport is given
    :type session: requests.Session
    :param insecure: use http instead of https
    :type insecure: bool
    :param tls_verify: enable/disable tls verification or use a custom CA-Bundle
    :type tls_verify: bool or str
    :param transport: transport to send requests with, usually the provider's
                      so that both share connections. One is created from the
                      session and tls_verify when not provided
    :type transport: oras.transport.Transport
    """
    backend = auth_backends.get(name)
    if not backend:
        raise ValueError(f"Authentication backend {backend} is not known.")
    backend = backend(**kwargs)
    backend.transport = transport or Transport(session=session, tls_verify=tls_verify)
    backend.prefix = "http" if insecure else "https"
    return backend
