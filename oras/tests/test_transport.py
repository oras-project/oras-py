"""
Tests for the transport boundary, and the registry operations built on it.

These do not need a running registry: the transport can be swapped for a fake
one, which is the point of keeping request execution behind a small interface.
"""

import requests

import oras.auth
import oras.auth.utils as auth_utils
import oras.defaults
import oras.provider
from oras.transport import Transport, resolve_body, successful_response


def make_response(status_code: int = 200, content: bytes = b"", headers=None):
    """
    Build a requests response to hand back from a fake transport.
    """
    response = requests.Response()
    response.status_code = status_code
    response._content = content
    response.headers.update(headers or {})
    return response


class FakeSession:
    """Records requests instead of sending them."""

    def __init__(self, response=None):
        self.calls = []
        self.cookies = requests.cookies.RequestsCookieJar()
        self.response = response or make_response()

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.response


class FakeTransport:
    """Stands in for a Transport, returning canned responses in order."""

    def __init__(self, responses=None):
        self.session = None
        self.tls_verify = True
        self.calls = []
        self.responses = list(responses or [])

    def request(
        self,
        url,
        method="GET",
        data=None,
        headers=None,
        json=None,
        stream=False,
        params=None,
    ):
        self.calls.append(
            {
                "url": url,
                "method": method,
                "data": data,
                "headers": headers,
                "json": json,
                "stream": stream,
                "params": params,
            }
        )
        if self.responses:
            return self.responses.pop(0)
        return make_response()


def get_registry(transport=None):
    """
    An insecure registry, with an optional transport swapped in.
    """
    registry = oras.provider.Registry(hostname="registry.example", insecure=True)
    if transport is not None:
        registry.transport = transport
    return registry


def test_transport_request_forwards_arguments():
    session = FakeSession()
    transport = Transport(session=session, tls_verify=False)

    transport.request(
        "http://registry.example/v2/",
        "PUT",
        data=b"content",
        headers={"Content-Type": "application/octet-stream"},
        stream=True,
    )

    (call,) = session.calls
    assert call["method"] == "PUT"
    assert call["url"] == "http://registry.example/v2/"
    assert call["data"] == b"content"
    assert call["headers"] == {"Content-Type": "application/octet-stream"}
    assert call["stream"] is True

    # tls_verify is applied by the transport, not by callers
    assert call["verify"] is False


def test_transport_applies_custom_ca_bundle():
    session = FakeSession()
    transport = Transport(session=session, tls_verify="/path/to/ca-bundle.crt")

    transport.request("https://registry.example/v2/")

    assert session.calls[0]["verify"] == "/path/to/ca-bundle.crt"


def test_transport_rejects_cookies():
    """
    Registries that see cookies accepted may treat the client as a browser.
    """
    transport = Transport()
    assert transport.session.cookies.get_policy().allowed_domains() == ()


def test_successful_response():
    assert successful_response().status_code == 200
    assert successful_response(201).status_code == 201


def test_registry_session_comes_from_transport():
    registry = get_registry()

    assert registry.session is registry.transport.session

    # The auth backend shares the session with the provider
    assert registry.auth.session is registry.session


def test_registry_session_can_be_replaced():
    registry = get_registry()
    session = requests.Session()

    registry.session = session

    assert registry.session is session
    assert registry.transport.session is session


def test_registry_tls_verify_reads_and_writes_transport():
    registry = oras.provider.Registry(hostname="registry.example", tls_verify=False)
    assert registry._tls_verify is False

    registry._tls_verify = True
    assert registry.transport.tls_verify is True


def test_do_request_goes_through_the_transport():
    transport = FakeTransport([make_response(201)])
    registry = get_registry(transport)

    response = registry.do_request(
        "http://registry.example/v2/repository/manifests/tag", "PUT", json={"a": 1}
    )

    assert response.status_code == 201
    (call,) = transport.calls
    assert call["method"] == "PUT"
    assert call["url"] == "http://registry.example/v2/repository/manifests/tag"
    assert call["json"] == {"a": 1}


def test_get_manifest_content_returns_bytes_and_digest():
    digest = "sha256:aaaa"
    transport = FakeTransport(
        [
            make_response(
                content=b'{"schemaVersion":2}',
                headers={"Docker-Content-Digest": digest},
            )
        ]
    )
    registry = get_registry(transport)

    content, reported_digest = registry.get_manifest_content(
        "registry.example/dinosaur/artifact:v1"
    )

    # The bytes are handed back untouched, so the digest still matches
    assert content == b'{"schemaVersion":2}'
    assert reported_digest == digest

    (call,) = transport.calls
    assert call["method"] == "GET"
    assert call["url"] == "http://registry.example/v2/dinosaur/artifact/manifests/v1"
    assert call["headers"]["Accept"] == ", ".join(
        oras.defaults.default_manifest_accepted_media_types
    )


def test_get_manifest_content_without_digest_header():
    transport = FakeTransport([make_response(content=b"{}")])
    registry = get_registry(transport)

    _, reported_digest = registry.get_manifest_content(
        "registry.example/dinosaur/artifact:v1"
    )

    assert reported_digest is None


def test_get_manifest_content_by_reference():
    digest = "sha256:bbbb"
    transport = FakeTransport([make_response(content=b"{}")])
    registry = get_registry(transport)

    registry.get_manifest_content(
        "registry.example/dinosaur/artifact:v1",
        allowed_media_type=[oras.defaults.default_manifest_media_type],
        reference=digest,
    )

    (call,) = transport.calls
    assert (
        call["url"]
        == f"http://registry.example/v2/dinosaur/artifact/manifests/{digest}"
    )
    assert call["headers"]["Accept"] == oras.defaults.default_manifest_media_type


def test_upload_manifest_content_sends_raw_bytes():
    transport = FakeTransport([make_response(201)])
    registry = get_registry(transport)
    container = registry.get_container("registry.example/dinosaur/artifact:v1")

    response = registry.upload_manifest_content(
        b'{"schemaVersion":2}',
        container,
        oras.defaults.default_index_media_type,
    )

    assert response.status_code == 201
    (call,) = transport.calls
    assert call["method"] == "PUT"
    assert call["data"] == b'{"schemaVersion":2}'
    assert call["json"] is None
    assert call["headers"] == {"Content-Type": oras.defaults.default_index_media_type}
    assert call["url"] == "http://registry.example/v2/dinosaur/artifact/manifests/v1"


def test_upload_manifest_content_by_reference():
    digest = "sha256:cccc"
    transport = FakeTransport([make_response(201)])
    registry = get_registry(transport)
    container = registry.get_container("registry.example/dinosaur/artifact:v1")

    registry.upload_manifest_content(
        b"{}",
        container,
        oras.defaults.default_manifest_media_type,
        reference=digest,
    )

    (call,) = transport.calls
    assert (
        call["url"]
        == f"http://registry.example/v2/dinosaur/artifact/manifests/{digest}"
    )


def test_transport_forwards_query_parameters():
    """
    Token requests need query parameters, so the transport has to carry them.
    """
    session = FakeSession()
    transport = Transport(session=session)

    transport.request(
        "https://auth.example/token",
        params={"service": "registry.example", "scope": "repository:demo:pull"},
    )

    assert session.calls[0]["params"] == {
        "service": "registry.example",
        "scope": "repository:demo:pull",
    }


def test_transport_streams_without_reading_the_body():
    session = FakeSession()
    transport = Transport(session=session)

    transport.request("https://registry.example/v2/repo/blobs/sha256:abc", stream=True)

    assert session.calls[0]["stream"] is True


def test_transport_passes_file_objects_through_unread(tmp_path):
    """
    A file object must reach requests as-is, so uploads are not buffered here.
    """
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"some payload")

    session = FakeSession()
    transport = Transport(session=session)

    with open(blob, "rb") as handle:
        transport.request("https://registry.example/upload", "PUT", data=handle)
        sent = session.calls[0]["data"]

        # The very same handle is handed over, still unread
        assert sent is handle
        assert sent.tell() == 0


def test_transport_close_closes_the_session():
    closed = []

    class ClosableSession(FakeSession):
        def close(self):
            closed.append(True)

    transport = Transport(session=ClosableSession())
    transport.close()

    assert closed == [True]


def test_registry_accepts_an_injected_transport():
    transport = FakeTransport()
    registry = oras.provider.Registry(
        hostname="registry.example", insecure=True, transport=transport
    )

    assert registry.transport is transport
    # The auth backend is given the same one, so connections are shared
    assert registry.auth.transport is transport


def test_registry_builds_a_transport_when_none_is_given():
    registry = oras.provider.Registry(hostname="registry.example", tls_verify=False)

    assert isinstance(registry.transport, Transport)
    assert registry.transport.tls_verify is False
    assert registry.auth.transport is registry.transport


def test_registry_close_closes_the_transport():
    closed = []

    class ClosableTransport(FakeTransport):
        def close(self):
            closed.append(True)

    registry = get_registry(ClosableTransport())
    registry.close()

    assert closed == [True]


def test_get_auth_backend_still_accepts_a_session():
    """
    The older way of wiring a backend keeps working.
    """
    session = requests.Session()
    backend = oras.auth.get_auth_backend("token", session, insecure=True)

    assert backend.session is session
    assert backend.prefix == "http"


def test_auth_backend_tls_verify_reads_the_transport():
    backend = oras.auth.get_auth_backend("token", tls_verify=False)

    assert backend._tls_verify is False
    assert backend.transport.tls_verify is False


def token_response(payload: bytes = b'{"token": "a-token"}'):
    return make_response(content=payload)


def test_token_request_goes_through_the_transport():
    """
    Requesting a bearer token is an HTTP call like any other, so it uses the
    transport rather than reaching for a session of its own.
    """
    transport = FakeTransport([token_response()])
    backend = oras.auth.get_auth_backend("token", transport=transport)
    backend.set_basic_auth("myuser", "mypass")

    header = auth_utils.parse_auth_header(
        'Bearer realm="https://auth.example/token",'
        'service="registry.example",scope="repository:demo:pull"'
    )
    token = backend.request_token(header)

    assert token == "a-token"
    (call,) = transport.calls
    assert call["method"] == "GET"
    assert call["url"] == "https://auth.example/token"
    assert call["params"] == {
        "service": "registry.example",
        "scope": "repository:demo:pull",
    }
    assert call["headers"]["Authorization"].startswith("Basic ")
    assert call["headers"]["Service"] == "registry.example"


def test_anonymous_token_request_goes_through_the_transport():
    transport = FakeTransport([token_response(b'{"access_token": "anon"}')])
    backend = oras.auth.get_auth_backend("token", transport=transport)

    header = auth_utils.parse_auth_header(
        'Bearer realm="https://auth.example/token",service="registry.example"'
    )
    token = backend.request_anonymous_token(header)

    assert token == "anon"
    (call,) = transport.calls
    assert call["url"] == "https://auth.example/token"
    assert call["params"] == {"service": "registry.example"}


def test_token_request_returns_nothing_when_refused():
    transport = FakeTransport([make_response(401, content=b"{}")])
    backend = oras.auth.get_auth_backend("token", transport=transport)

    header = auth_utils.parse_auth_header('Bearer realm="https://auth.example/token"')

    assert backend.request_token(header) is None


def test_resolve_body_produces_a_fresh_body_for_each_attempt():
    produced = []

    def factory():
        produced.append(len(produced))
        return b"fresh"

    assert resolve_body(b"raw") == b"raw"
    assert resolve_body({"a": "b"}) == {"a": "b"}
    assert resolve_body(None) is None
    assert resolve_body(factory) == b"fresh"
    assert resolve_body(factory) == b"fresh"
    assert produced == [0, 1], "a callable body is produced again for each send"


def test_transport_resolves_a_callable_body_at_the_send():
    session = FakeSession()
    transport = Transport(session=session)

    transport.request("https://registry.example/v2/", "PUT", data=lambda: b"payload")
    transport.request("https://registry.example/v2/", "PUT", data=lambda: b"payload")

    assert [call["data"] for call in session.calls] == [b"payload", b"payload"]
