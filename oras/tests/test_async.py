"""
Tests for the asynchronous client.

The unit tests swap in a fake transport, so registry logic can be checked
without a registry and without httpx doing any real work. The integration
tests exercise the httpx transport against a running registry, and skip when
there is not one, in the same way as the synchronous integration tests.
"""

import asyncio
import hashlib
import os
import pathlib
import ssl
from contextlib import asynccontextmanager

import pytest

import oras.auth.utils
import oras.client
import oras.decorator
import oras.defaults
import oras.layout
import oras.provider
import oras.utils
from oras.provider_async import AsyncRegistry
from oras.transport_async import AsyncTransport

# The async client is an extra, so skip rather than fail when it is absent
httpx = pytest.importorskip("httpx")

here = pathlib.Path(__file__).resolve().parent


def digest_of(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


class FakeAsyncTransport:
    """Records requests and returns canned responses, in order."""

    def __init__(self, responses=None):
        self.tls_verify = True
        self.calls = []
        self.responses = list(responses or [])
        self.closed = False

    async def request(
        self, url, method="GET", data=None, headers=None, json=None, params=None
    ):
        self.calls.append(
            {
                "url": url,
                "method": method,
                "data": data,
                "headers": dict(headers or {}),
                "json": json,
                "params": params,
            }
        )
        if self.responses:
            return self.responses.pop(0)
        return httpx.Response(200)

    async def aclose(self):
        self.closed = True


def get_registry(transport=None) -> AsyncRegistry:
    return AsyncRegistry(
        hostname="registry.example",
        insecure=True,
        transport=transport or FakeAsyncTransport(),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- construction


def test_async_client_is_exposed_from_client_module():
    assert oras.client.AsyncOrasClient is AsyncRegistry


def test_async_registry_shares_its_transport_with_auth():
    transport = FakeAsyncTransport()
    registry = get_registry(transport)

    assert registry.transport is transport
    assert registry.auth.transport is transport


def test_async_registry_builds_a_transport_by_default():
    registry = AsyncRegistry(hostname="registry.example", tls_verify=False)

    assert isinstance(registry.transport, AsyncTransport)
    assert registry.transport.tls_verify is False


def test_async_registry_shares_registry_logic_with_the_sync_provider():
    """
    The decisions live in one place, so both providers get them from there.
    """
    for shared in (
        "_iter_push_layers",
        "_iter_pull_targets",
        "_prepare_manifest_config",
        "_apply_manifest_annotations",
        "_check_200_response",
        "_get_location",
        "_url",
        "get_container",
    ):
        assert getattr(AsyncRegistry, shared) is getattr(oras.provider.Registry, shared)


# ---------------------------------------------------------------- transport


@pytest.mark.asyncio
async def test_do_request_goes_through_the_transport():
    transport = FakeAsyncTransport([httpx.Response(201)])
    registry = get_registry(transport)

    response = await registry.do_request(
        "http://registry.example/v2/repo/manifests/v1", "PUT", json={"a": 1}
    )

    assert response.status_code == 201
    (call,) = transport.calls
    assert call["method"] == "PUT"
    assert call["json"] == {"a": 1}


@pytest.mark.asyncio
async def test_aclose_closes_the_transport():
    transport = FakeAsyncTransport()
    registry = get_registry(transport)

    await registry.aclose()

    assert transport.closed is True


@pytest.mark.asyncio
async def test_async_context_manager_closes_the_transport():
    transport = FakeAsyncTransport()

    async with get_registry(transport) as registry:
        assert registry.transport is transport
    assert transport.closed is True


def test_transport_maps_bodies_onto_httpx_arguments():
    """
    requests takes bytes and forms through `data`, httpx separates them.
    """
    transport = AsyncTransport(client=httpx.AsyncClient())

    assert transport._content_arguments(None) == {}
    assert transport._content_arguments(b"raw") == {"content": b"raw"}
    assert transport._content_arguments({"a": "b"}) == {"data": {"a": "b"}}


# ---------------------------------------------------------------- manifests


@pytest.mark.asyncio
async def test_get_manifest_content_returns_bytes_and_digest():
    body = b'{"schemaVersion":2}'
    transport = FakeAsyncTransport(
        [
            httpx.Response(
                200, content=body, headers={"Docker-Content-Digest": "sha256:a"}
            )
        ]
    )
    registry = get_registry(transport)

    content, digest = await registry.get_manifest_content(
        "registry.example/demo/artifact:v1"
    )

    assert content == body
    assert digest == "sha256:a"
    (call,) = transport.calls
    assert call["url"] == "http://registry.example/v2/demo/artifact/manifests/v1"


@pytest.mark.asyncio
async def test_upload_manifest_content_sends_raw_bytes_by_reference():
    transport = FakeAsyncTransport([httpx.Response(201)])
    registry = get_registry(transport)
    container = registry.get_container("registry.example/demo/artifact:v1")

    await registry.upload_manifest_content(
        b"{}", container, oras.defaults.default_index_media_type, reference="sha256:b"
    )

    (call,) = transport.calls
    assert call["method"] == "PUT"
    assert call["data"] == b"{}"
    assert call["headers"]["Content-Type"] == oras.defaults.default_index_media_type
    assert call["url"] == "http://registry.example/v2/demo/artifact/manifests/sha256:b"


# ---------------------------------------------------------------- auth


@pytest.mark.asyncio
async def test_authentication_challenge_is_answered_and_retried_asynchronously():
    """
    401 -> token request -> retry, all awaited on the async transport.
    """
    challenge = httpx.Response(
        401,
        headers={
            "Www-Authenticate": 'Bearer realm="https://auth.example/token",service="registry.example"'
        },
    )
    token = httpx.Response(200, json={"token": "a-token"})
    transport = FakeAsyncTransport([challenge, token, httpx.Response(200)])
    registry = get_registry(transport)

    response = await registry.do_request("http://registry.example/v2/demo/tags/list")

    assert response.status_code == 200
    assert len(transport.calls) == 3

    # the token came from the realm, over the same async transport
    assert transport.calls[1]["url"] == "https://auth.example/token"
    assert transport.calls[1]["params"] == {"service": "registry.example"}

    # and the retry carried it
    assert transport.calls[2]["headers"]["Authorization"] == "Bearer a-token"
    assert registry.auth.token == "a-token"


@pytest.mark.asyncio
async def test_basic_auth_answers_a_challenge_without_a_token_request():
    challenge = httpx.Response(401, headers={"Www-Authenticate": 'Basic realm="r"'})
    transport = FakeAsyncTransport([challenge, httpx.Response(200)])
    registry = AsyncRegistry(
        hostname="registry.example",
        insecure=True,
        auth_backend="basic",
        transport=transport,
    )
    registry.auth.set_basic_auth("myuser", "mypass")

    response = await registry.do_request("http://registry.example/v2/")

    assert response.status_code == 200
    assert len(transport.calls) == 2
    assert transport.calls[1]["headers"]["Authorization"].startswith("Basic ")


@pytest.mark.asyncio
async def test_challenge_without_a_www_authenticate_header_is_not_answered():
    """
    Nothing to answer means no retry, matching the synchronous backend.
    """
    registry = get_registry()

    headers, changed = await registry.auth.authenticate_request_async(
        httpx.Response(401), {}
    )

    assert changed is False
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_a_refused_token_request_yields_no_token():
    transport = FakeAsyncTransport([httpx.Response(403, content=b"{}")])
    registry = get_registry(transport)
    header = oras.auth.utils.parse_auth_header(
        'Bearer realm="https://auth.example/token"'
    )

    assert await registry.auth.request_token_async(header) is None


# ---------------------------------------------------------------- integration


@pytest.fixture
def async_target(registry):
    return f"{registry}/dinosaur/async-artifact:v1"


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_push_pull_file(tmp_path, registry, credentials, async_target):
    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        with oras.utils.workdir(str(tmp_path)):
            oras.utils.write_file("artifact.txt", "async round trip\n")
            response = await client.push(
                files=["artifact.txt"],
                target=async_target,
                manifest_annotations={"mode": "async"},
            )
            assert response.status_code in (200, 201)

        outdir = str(tmp_path / "out")
        files = await client.pull(async_target, outdir=outdir)
        assert len(files) == 1
        assert oras.utils.read_file(files[0]) == "async round trip\n"

        manifest = await client.get_manifest(async_target)
        assert manifest["annotations"]["mode"] == "async"


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_push_pull_directory(tmp_path, registry, credentials):
    target = f"{registry}/dinosaur/async-directory:v1"
    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        with oras.utils.workdir(str(tmp_path)):
            os.makedirs("bundle", exist_ok=True)
            oras.utils.write_file(os.path.join("bundle", "inner.txt"), "nested\n")
            response = await client.push(files=["bundle"], target=target)
            assert response.status_code in (200, 201)

        files = await client.pull(target, outdir=str(tmp_path / "dirout"))
        assert len(files) == 1
        assert os.path.isdir(files[0])
        assert "inner.txt" in os.listdir(files[0])


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_chunked_upload(tmp_path, registry, credentials):
    target = f"{registry}/dinosaur/async-chunked:v1"
    payload = ("chunk" * 20000).encode()

    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        with oras.utils.workdir(str(tmp_path)):
            pathlib.Path("chunked.bin").write_bytes(payload)
            response = await client.push(
                files=["chunked.bin"],
                target=target,
                do_chunked=True,
                chunk_size=4096,
            )
            assert response.status_code in (200, 201, 202)

        files = await client.pull(target, outdir=str(tmp_path / "chunkout"))
        assert pathlib.Path(files[0]).read_bytes() == payload


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_large_blob_round_trips(tmp_path, registry, credentials):
    """
    A blob larger than the read buffer, to exercise streaming both ways.
    """
    target = f"{registry}/dinosaur/async-large:v1"
    payload = os.urandom(5 * 1024 * 1024)

    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        with oras.utils.workdir(str(tmp_path)):
            pathlib.Path("large.bin").write_bytes(payload)
            response = await client.push(files=["large.bin"], target=target)
            assert response.status_code in (200, 201)

        files = await client.pull(target, outdir=str(tmp_path / "largeout"))
        assert digest_of(pathlib.Path(files[0]).read_bytes()) == digest_of(payload)


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_digest_reference_and_tags(tmp_path, registry, credentials):
    repository = f"{registry}/dinosaur/async-refs"
    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        with oras.utils.workdir(str(tmp_path)):
            oras.utils.write_file("ref.txt", "by digest\n")
            await client.push(files=["ref.txt"], target=f"{repository}:v1")

        content, digest = await client.get_manifest_content(f"{repository}:v1")
        assert digest == digest_of(content)

        by_digest = await client.get_manifest(f"{repository}@{digest}")
        assert by_digest["schemaVersion"] == 2

        tags = await client.get_tags(repository)
        assert "v1" in tags


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_index_is_pushed_and_read_back(tmp_path, registry, credentials):
    """
    An image index pushed as exact bytes, then read back unchanged.
    """
    layout = oras.layout.Layout(str(here / "ocilayout_data" / "ocilayout2"))
    index_digest = oras.utils.read_json(
        str(here / "ocilayout_data" / "ocilayout2" / "index.json")
    )["manifests"][0]["digest"]
    index_bytes = layout.digest_to_blob_path(index_digest).read_bytes()

    target = f"{registry}/dinosaur/async-index:v1"
    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        container = client.get_container(target)

        # the blobs the index refers to have to exist before it does
        for digest in layout.get_ordered_blobs("latest"):
            blob_path = layout.digest_to_blob_path(digest)
            blob = blob_path.read_bytes()
            try:
                media_type = oras.utils.read_json(str(blob_path)).get("mediaType", "")
            except Exception:
                media_type = ""
            if media_type in (
                oras.defaults.default_manifest_media_type,
                oras.defaults.default_index_media_type,
            ):
                if digest == index_digest:
                    continue
                response = await client.upload_manifest_content(
                    blob, container, media_type, reference=digest
                )
            else:
                layer = {
                    "digest": digest,
                    "size": blob_path.stat().st_size,
                    "mediaType": media_type or oras.defaults.unknown_config_media_type,
                }
                response = await client.upload_blob(str(blob_path), container, layer)
            client._check_200_response(response)

        response = await client.upload_manifest_content(
            index_bytes, container, oras.defaults.default_index_media_type
        )
        client._check_200_response(response)

        content, digest = await client.get_manifest_content(
            target, allowed_media_type=[oras.defaults.default_index_media_type]
        )
        assert content == index_bytes
        assert digest == index_digest


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_operations_run_concurrently(tmp_path, registry, credentials):
    target = f"{registry}/dinosaur/async-concurrent:v1"
    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        with oras.utils.workdir(str(tmp_path)):
            oras.utils.write_file("shared.txt", "concurrent\n")
            await client.push(files=["shared.txt"], target=target)

        results = await asyncio.gather(
            client.pull(target, outdir=str(tmp_path / "a")),
            client.pull(target, outdir=str(tmp_path / "b")),
            client.get_manifest(target),
            client.get_tags(f"{registry}/dinosaur/async-concurrent"),
        )

    assert len(results[0]) == 1 and len(results[1]) == 1
    assert results[2]["schemaVersion"] == 2
    assert "v1" in results[3]

    # one shared token cache, one agreed answer
    assert client.auth.token is None or isinstance(client.auth.token, str)


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_pull_can_be_cancelled(tmp_path, registry, credentials):
    target = f"{registry}/dinosaur/async-cancel:v1"
    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        with oras.utils.workdir(str(tmp_path)):
            pathlib.Path("cancel.bin").write_bytes(os.urandom(2 * 1024 * 1024))
            await client.push(files=["cancel.bin"], target=target)

        task = asyncio.create_task(client.pull(target, outdir=str(tmp_path / "c")))
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
@pytest.mark.with_auth(False)
async def test_async_missing_manifest_raises_value_error(registry, credentials):
    async with AsyncRegistry(hostname=registry, insecure=True) as client:
        with pytest.raises(ValueError):
            await client.get_manifest(f"{registry}/dinosaur/does-not-exist:v1")


# ---------------------------------------------------------------- resent bodies


async def drain(body):
    """Resolve and read a body the way a real transport would."""
    if callable(body):
        body = body()
    if body is None:
        return b""
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    chunks = []
    async for chunk in body:
        chunks.append(chunk)
    return b"".join(chunks)


class BodyRecordingTransport(FakeAsyncTransport):
    """
    Reads each body, as a real transport does, and records what arrived.

    Reading matters: a body that can only be read once looks fine until
    something reads it twice.
    """

    def __init__(self, responses=None, fail_first=False):
        super().__init__(responses)
        self.bodies = []
        self.fail_first = fail_first
        self.sent = 0

    async def request(
        self, url, method="GET", data=None, headers=None, json=None, params=None
    ):
        body = await drain(data)
        if method == "PUT":
            self.bodies.append(body)
            self.sent += 1
            if self.fail_first and self.sent == 1:
                raise httpx.ConnectError("boom")
        return await super().request(
            url, method, data=data, headers=headers, json=json, params=params
        )


def upload_layer(payload: bytes) -> dict:
    return {
        "digest": digest_of(payload),
        "size": len(payload),
        "mediaType": "application/octet-stream",
    }


def blob_file(tmp_path, payload: bytes) -> str:
    path = tmp_path / "blob.bin"
    path.write_bytes(payload)
    return str(path)


@pytest.mark.asyncio
async def test_upload_body_survives_an_authentication_challenge(tmp_path):
    """
    The blob PUT is re-sent to answer a 401, and must carry the same bytes.

    A body read straight from disk is spent after the first send, which would
    leave the retry declaring a Content-Length and digest for content it did
    not actually send.
    """
    payload = b"hello world"
    session = httpx.Response(
        202, headers={"location": "http://registry.example/v2/demo/blobs/uploads/1"}
    )
    challenge = httpx.Response(
        401,
        headers={
            "Www-Authenticate": 'Bearer realm="https://auth.example/token",service="registry.example"'
        },
    )
    token = httpx.Response(200, json={"token": "a-token"})
    transport = BodyRecordingTransport([session, challenge, token, httpx.Response(201)])
    registry = get_registry(transport)
    container = registry.get_container("registry.example/demo/artifact:v1")

    await registry.put_upload(
        blob_file(tmp_path, payload), container, upload_layer(payload)
    )

    assert len(transport.bodies) == 2, "expected the PUT to be sent twice"
    assert transport.bodies == [payload, payload]


@pytest.mark.asyncio
async def test_upload_body_survives_a_retry(tmp_path, monkeypatch):
    """
    The same holds when the retry decorator re-sends after a failure.
    """
    monkeypatch.setattr(oras.decorator, "backoff_seconds", lambda attempt, timeout: 0)

    payload = b"retried payload"
    session = httpx.Response(
        202, headers={"location": "http://registry.example/v2/demo/blobs/uploads/1"}
    )
    transport = BodyRecordingTransport(
        [session, session, httpx.Response(201)], fail_first=True
    )
    registry = get_registry(transport)
    container = registry.get_container("registry.example/demo/artifact:v1")

    await registry.put_upload(
        blob_file(tmp_path, payload), container, upload_layer(payload)
    )

    assert len(transport.bodies) == 2, "expected the PUT to be sent twice"
    assert transport.bodies == [payload, payload]


# ---------------------------------------------------------------- redirects


class RedirectingServer:
    """
    A real HTTP server that redirects the first PUT, and records each body.

    This is deliberately not a fake transport: the bug it guards against lives
    inside httpx's own redirect handling, below where a fake would sit.
    """

    def __init__(self, redirect_status=307):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        self.received = []
        received = self.received

        class Handler(BaseHTTPRequestHandler):
            def do_PUT(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                received.append((self.path, body))
                if self.path.endswith("/first"):
                    self.send_response(redirect_status)
                    self.send_header("Location", "/second")
                else:
                    self.send_response(201)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]

    def __enter__(self):
        import threading

        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()


@pytest.mark.asyncio
async def test_streamed_body_survives_a_redirect():
    """
    Registries backed by object storage redirect blob uploads, and httpx
    cannot replay a body it has already streamed. Each hop must get a fresh one.
    """
    payload = b"hello world"

    with RedirectingServer() as server:
        transport = AsyncTransport()
        try:
            response = await transport.request(
                f"http://127.0.0.1:{server.port}/first",
                "PUT",
                data=lambda: iter_bytes(payload),
                headers={"Content-Length": str(len(payload))},
            )
        finally:
            await transport.aclose()

    assert response.status_code == 201
    assert [path for path, _ in server.received] == ["/first", "/second"]
    assert [body for _, body in server.received] == [payload, payload]


async def iter_bytes(payload: bytes):
    yield payload


# ---------------------------------------------------------------- streamed auth


class StreamingTransport(FakeAsyncTransport):
    """
    A transport whose stream() can be told what to answer with.

    Records the headers of every stream that is opened, which is how the
    authentication of a download is checked.
    """

    def __init__(self, statuses=None, transport_errors=0):
        super().__init__()
        self.statuses = list(statuses or [200])
        self.opened = []
        self.transport_errors = transport_errors

    @asynccontextmanager
    async def stream(self, url, method="GET", headers=None, params=None):
        self.opened.append(dict(headers or {}))
        if self.transport_errors:
            self.transport_errors -= 1
            raise httpx.ConnectError("connection lost")
        status = self.statuses.pop(0) if self.statuses else 200
        challenge = (
            {
                "Www-Authenticate": 'Bearer realm="https://auth.example/token",service="reg"'
            }
            if status == 401
            else {}
        )
        yield httpx.Response(
            status,
            headers=challenge,
            content=b"blob-bytes",
            request=httpx.Request(method, url),
        )

    async def request(
        self, url, method="GET", data=None, headers=None, json=None, params=None
    ):
        if "auth.example" in url:
            return httpx.Response(200, json={"token": "a-token"})
        return await super().request(
            url, method, data=data, headers=headers, json=json, params=params
        )


async def download(transport, tmp_path, backend="token", setup=None):
    registry = AsyncRegistry(
        hostname="registry.example",
        insecure=True,
        auth_backend=backend,
        transport=transport,  # type: ignore[arg-type]
    )
    if setup:
        setup(registry)
    container = registry.get_container("registry.example/demo/artifact:v1")
    outfile = str(tmp_path / "blob.bin")
    await registry.download_blob(container, "sha256:" + "a" * 64, outfile)
    return outfile


def authorizations(transport):
    return [opened.get("Authorization", None) for opened in transport.opened]


@pytest.mark.asyncio
async def test_download_answers_a_token_challenge(tmp_path):
    """
    A download is authenticated like any other request, not left to fail.
    """
    transport = StreamingTransport([401, 200])

    outfile = await download(transport, tmp_path)

    assert authorizations(transport) == [None, "Bearer a-token"]
    assert pathlib.Path(outfile).read_bytes() == b"blob-bytes"


@pytest.mark.asyncio
async def test_download_answers_a_basic_challenge(tmp_path):
    transport = StreamingTransport([401, 200])

    await download(
        transport,
        tmp_path,
        backend="basic",
        setup=lambda r: r.auth.set_basic_auth("myuser", "mypass"),
    )

    assert authorizations(transport)[1].startswith("Basic ")


@pytest.mark.asyncio
async def test_download_refreshes_after_a_403(tmp_path):
    """
    A token scoped too narrowly for the blob endpoint gets another chance.
    """
    transport = StreamingTransport([401, 403, 200])

    await download(transport, tmp_path)

    assert len(transport.opened) == 3


@pytest.mark.asyncio
async def test_download_reuses_a_token_it_already_holds(tmp_path):
    transport = StreamingTransport([200])
    registry = AsyncRegistry(
        hostname="registry.example",
        insecure=True,
        transport=transport,  # type: ignore[arg-type]
    )
    registry.auth.token = "held-token"
    container = registry.get_container("registry.example/demo/artifact:v1")

    await registry.download_blob(
        container, "sha256:" + "a" * 64, str(tmp_path / "blob.bin")
    )

    assert authorizations(transport) == ["Bearer held-token"]


@pytest.mark.asyncio
async def test_download_retries_a_failed_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(oras.decorator, "backoff_seconds", lambda attempt, timeout: 0)
    transport = StreamingTransport([200], transport_errors=2)

    outfile = await download(transport, tmp_path)

    assert len(transport.opened) == 3, "two failures, then a success"
    assert pathlib.Path(outfile).read_bytes() == b"blob-bytes"


@pytest.mark.asyncio
async def test_download_does_not_retry_a_status_the_registry_meant(tmp_path):
    """
    A 404 says the same thing however many times it is asked.
    """
    transport = StreamingTransport([404])

    with pytest.raises(httpx.HTTPStatusError):
        await download(transport, tmp_path)

    assert len(transport.opened) == 1


# ---------------------------------------------------------------- retry policy


def ssl_backed_connect_error():
    """
    A ConnectError shaped the way httpx reports a bad certificate.
    """
    error = httpx.ConnectError("connection failed")
    error.__cause__ = ssl.SSLCertVerificationError("certificate verify failed")
    return error


def test_a_certificate_failure_is_recognised_through_the_cause_chain():
    """
    httpx reports a bad certificate and a refused connection the same way, so
    only the cause tells them apart.
    """
    assert oras.decorator.is_certificate_error(ssl_backed_connect_error()) is True

    refused = httpx.ConnectError("connection failed")
    refused.__cause__ = ConnectionRefusedError("refused")
    assert oras.decorator.is_certificate_error(refused) is False

    assert (
        oras.decorator.is_certificate_error(ValueError("nothing to do with tls"))
        is False
    )


@pytest.mark.asyncio
async def test_retry_async_does_not_retry_a_certificate_failure(monkeypatch):
    """
    A wrong certificate will not fix itself, so it is reported at once rather
    than after every attempt has slept.
    """
    slept = []
    monkeypatch.setattr(asyncio, "sleep", lambda n: slept.append(n))
    attempts = []

    @oras.decorator.retry_async(attempts=5, timeout=2)
    async def failing():
        attempts.append(1)
        raise ssl_backed_connect_error()

    with pytest.raises(httpx.ConnectError):
        await failing()

    assert len(attempts) == 1, "the request should be made once"
    assert slept == [], "and nothing should be slept through"


@pytest.mark.asyncio
async def test_retry_async_still_retries_a_refused_connection(monkeypatch):
    """
    A refused connection may well succeed later, and is retried as before.
    """
    monkeypatch.setattr(oras.decorator, "backoff_seconds", lambda attempt, timeout: 0)
    attempts = []

    @oras.decorator.retry_async(attempts=3, timeout=2)
    async def failing():
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200)

    response = await failing()

    assert response.status_code == 200
    assert len(attempts) == 3, "it should keep trying"


# ---------------------------------------------------------------- cookies


class CookieServer:
    """
    A real server that sets a cookie on every response, and records what it
    was sent. Registries that do this treat an accepted cookie as a sign they
    are talking to a browser, and start asking for CSRF tokens.
    """

    def __init__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        self.received = []
        received = self.received

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append((self.path, self.headers.get("Cookie")))
                if self.path == "/redirect":
                    self.send_response(307)
                    self.send_header("Set-Cookie", "sid=from-redirect; Path=/")
                    self.send_header("Location", "/after")
                elif self.path == "/blob":
                    self.send_response(200)
                    self.send_header("Set-Cookie", "sid=from-blob; Path=/")
                    self.send_header("Content-Length", "9")
                    self.end_headers()
                    self.wfile.write(b"blob-body")
                    return
                else:
                    self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        import threading

        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()

    def cookies_sent(self):
        return [cookie for _, cookie in self.received]


@pytest.mark.asyncio
async def test_a_cookie_from_a_streamed_response_is_refused():
    """
    Downloads are most of the traffic, and they stream, so a cookie set on one
    must not be kept for later requests.
    """
    with CookieServer() as server:
        transport = AsyncTransport()
        try:
            async with transport.stream(f"{server.url}/blob") as response:
                async for _ in response.aiter_bytes():
                    pass

            assert list(transport.client.cookies.jar) == []

            await transport.request(f"{server.url}/next")
        finally:
            await transport.aclose()

    assert server.cookies_sent() == [None, None], "no cookie should be sent back"


@pytest.mark.asyncio
async def test_a_cookie_is_not_carried_across_a_redirect():
    """
    Refusing a cookie has to happen as the response is read, not afterwards,
    or it is still sent on the next leg of the same request.
    """
    with CookieServer() as server:
        transport = AsyncTransport()
        try:
            await transport.request(f"{server.url}/redirect")
        finally:
            await transport.aclose()

    assert [path for path, _ in server.received] == ["/redirect", "/after"]
    assert server.cookies_sent() == [None, None]
