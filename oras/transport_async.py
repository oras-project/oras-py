"""
Asynchronous HTTP transport for registry interactions.

This is the async counterpart to :class:`oras.transport.Transport`. It has the
same responsibility - own the connection and carry out one request - and the
same deliberate lack of responsibility: it knows nothing about manifests,
blobs or media types, and it decides neither when a request is authenticated
nor when one is retried.

httpx is imported lazily so that the async extra stays optional and importing
oras keeps working without it.
"""

__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

from http.cookiejar import DefaultCookiePolicy
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional, Union

from oras.transport import resolve_body

if TYPE_CHECKING:
    import httpx

ASYNC_EXTRA_MESSAGE = """the `httpx` dependency is required for asynchronous support.
Make sure to install the required extra "async", e.g.: pip install oras[async].
"""


def get_httpx():
    """
    Import httpx, with a message pointing at the extra when it is missing.
    """
    try:
        import httpx
    except ImportError as e:
        raise ImportError(ASYNC_EXTRA_MESSAGE) from e
    return httpx


class AsyncTransport:
    """
    Send HTTP requests to a registry with an httpx async client.
    """

    def __init__(
        self,
        client: Optional["httpx.AsyncClient"] = None,
        tls_verify: Union[bool, str] = True,
    ):
        """
        Create a new async transport.

        The client is created once and reused, so connections are pooled for
        the lifetime of the transport rather than per request.

        :param client: an existing httpx client to use, one is created if not provided
        :type client: httpx.AsyncClient
        :param tls_verify: enable/disable tls verification or use a custom CA-Bundle
        :type tls_verify: bool or str
        """
        httpx_module = get_httpx()
        self.tls_verify = tls_verify

        # requests follows redirects by default and the sync transport relies on
        # that, notably for registries that redirect blob uploads. httpx does
        # not, so it is asked to here to keep the two behaving the same way.
        self.client: "httpx.AsyncClient" = client or httpx_module.AsyncClient(
            verify=tls_verify, follow_redirects=True
        )

        # Ignore all cookies: some registries try to set one and take it as a
        # sign they are talking to a browser, trying to set further CSRF
        # cookies (Harbor is such a case). httpx keeps its cookies in a
        # standard library jar, so it can refuse them with the same policy the
        # sync transport uses. Refusing is what matters rather than clearing
        # afterwards, which would leave a cookie in play for the rest of the
        # request, redirects included, and would miss streamed responses.
        self.client.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))

    def _content_arguments(self, data: Any) -> dict:
        """
        Map a body onto the argument httpx expects for it.

        requests takes bytes, iterables and form dicts all through `data`,
        while httpx separates raw bodies (`content`) from form data (`data`).
        """
        if data is None:
            return {}
        if isinstance(data, dict):
            return {"data": data}
        return {"content": data}

    async def request(
        self,
        url: str,
        method: str = "GET",
        data: Optional[Any] = None,
        headers: Optional[dict] = None,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> "httpx.Response":
        """
        Send a single request, without any authentication or retry handling.

        :param url: the URL to issue the request to
        :type url: str
        :param method: the method to use (GET, DELETE, POST, PUT, PATCH)
        :type method: str
        :param data: body for the request. Bytes, or an iterator of bytes for a
                     body that should not be held in memory
        :type data: bytes or iterator or dict
        :param headers: headers for the request
        :type headers: dict
        :param json: json data for the request
        :type json: dict
        :param params: query string parameters to add to the url
        :type params: dict
        """
        # httpx cannot replay a body it has already streamed, so when the body
        # can be produced again this follows the redirect itself, with a fresh
        # body each hop. Anything re-readable is left to httpx as usual.
        if callable(data):
            response = await self._request_following_redirects(
                url, method, data, headers, json, params
            )
        else:
            response = await self.client.request(
                method,
                url,
                headers=headers,
                json=json,
                params=params,
                **self._content_arguments(data),
            )
        return response

    async def _request_following_redirects(
        self, url, method, data, headers, json, params, max_redirects: int = 5
    ):
        """
        Send a request whose body can be produced again, following redirects.

        Registries backed by object storage redirect blob uploads, and httpx
        raises StreamConsumed if it has to replay a streamed body. Each hop
        therefore asks for the body again rather than reusing a spent one.

        Only 307 and 308 are followed, because they are the redirects that keep
        the method and the body; anything else is returned for the caller to
        interpret, as httpx would when a redirect changes the request.
        """
        for _ in range(max_redirects):
            response = await self.client.request(
                method,
                url,
                headers=headers,
                json=json,
                params=params,
                follow_redirects=False,
                **self._content_arguments(resolve_body(data)),
            )
            if response.status_code not in (307, 308):
                return response

            location = response.headers.get("location")
            if not location:
                return response

            url = str(response.request.url.join(location))

            # the query is carried by the new location from here on
            params = None

        raise ValueError(f"Too many redirects uploading to {url}")

    def stream(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ):
        """
        Send a request and keep the body unread, for streaming a response.

        Returns an async context manager yielding the response, so that a
        caller can consume it in chunks without holding a whole blob in
        memory. Streaming lives here, and not in the registry layer, so that
        the registry never depends on the HTTP client being used.

        :param url: the URL to issue the request to
        :type url: str
        :param method: the method to use
        :type method: str
        :param headers: headers for the request
        :type headers: dict
        :param params: query string parameters to add to the url
        :type params: dict
        """
        return self.client.stream(method, url, headers=headers, params=params)

    async def aclose(self):
        """
        Close the underlying client and release its connections.
        """
        await self.client.aclose()


async def iter_file(path: str, chunk_size: int) -> AsyncIterator[bytes]:
    """
    Read a file in chunks, for uploading it without reading it all at once.

    :param path: the file to read
    :type path: str
    :param chunk_size: how much to read at a time
    :type chunk_size: int
    """
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            yield chunk
