"""
Asynchronous interactions with an OCI registry.

:class:`AsyncRegistry` is the asynchronous counterpart to
:class:`oras.provider.Registry`. Both derive from
:class:`oras.provider.RegistryBase`, which holds everything that is a decision
rather than a call: url construction, reference handling, preparing layers from
files, resolving output paths, and interpreting responses.

What is written here is the orchestration that has to await, and only that. A
change to what a push does belongs in RegistryBase and is picked up by both;
a change to how a request is carried out belongs in a transport.
"""

__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import asyncio
import os
import urllib
from contextlib import asynccontextmanager, nullcontext
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

import jsonschema

import oras.auth
import oras.decorator as decorator
import oras.defaults
import oras.oci
import oras.schemas
import oras.utils
from oras.logger import logger
from oras.provider import RegistryBase, temporary_empty_config
from oras.transport_async import AsyncTransport, get_httpx, iter_file
from oras.types import container_type

if TYPE_CHECKING:
    import httpx

# A download streams rather than going through do_request, so it carries the
# same retry policy here instead of inheriting the decorator's.
DOWNLOAD_ATTEMPTS = 5
DOWNLOAD_TIMEOUT = 2


class AsyncRegistry(RegistryBase):
    """
    Asynchronous interactions with an OCI registry.

    The client owns an httpx connection pool for its lifetime, so it should be
    closed when finished, either with `async with` or by awaiting aclose().
    """

    def __init__(
        self,
        hostname: Optional[str] = None,
        insecure: bool = False,
        tls_verify=True,
        auth_backend: str = "token",
        transport: Optional[AsyncTransport] = None,
    ):
        """
        Create an asynchronous ORAS client.

        :param hostname: the hostname of the registry to ping
        :type hostname: str
        :param insecure: use http instead of https
        :type insecure: bool
        :param tls_verify: enable/disable tls verification or use a custom CA-Bundle
        :type tls_verify: bool or str
        :param auth_backend: name of the auth backend to use
        :type auth_backend: str
        :param transport: how to send requests, defaults to a new async
                          transport configured with tls_verify
        :type transport: oras.transport_async.AsyncTransport
        """
        super().__init__(
            transport=transport or AsyncTransport(tls_verify=tls_verify),
            hostname=hostname,
            insecure=insecure,
            auth_backend=auth_backend,
        )

    async def __aenter__(self) -> "AsyncRegistry":
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        """
        Close the underlying client and release its connections.
        """
        await self.transport.aclose()

    @decorator.retry_async()
    async def do_request(
        self,
        url: str,
        method: str = "GET",
        data=None,
        headers: Optional[dict] = None,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> "httpx.Response":
        """
        Do a request, answering an authentication challenge if there is one.

        This mirrors the synchronous Registry.do_request: try, and on a 401 or
        403 ask the auth backend to answer the challenge and try once more,
        with one further attempt after a second 403 in case the token needs
        refreshing. The answer is awaited, so no part of it blocks the loop.

        :param url: the URL to issue the request to
        :type url: str
        :param method: the method to use (GET, DELETE, POST, PUT, PATCH)
        :type method: str
        :param data: body for the request. A body that can only be read
                     once must be given as a callable returning a fresh
                     one, since the request may be sent again
        :param headers: headers for the request
        :type headers: dict
        :param json: json data for the request
        :type json: dict
        :param params: query string parameters to add to the url
        :type params: dict
        """
        if headers is None:
            headers = {}

        # Use a token we already hold, as the sync provider does
        if isinstance(self.auth, oras.auth.TokenAuth) and self.auth.token is not None:
            headers.update(self.auth.get_auth_header())
        response = await self.transport.request(
            url,
            method,
            data=data,
            headers=headers,
            json=json,
            params=params,
        )

        # A 401 response is a request for authentication, 404 is not found
        if response.status_code not in [401, 403]:
            return response

        headers, changed = await self.auth.authenticate_request_async(response, headers)
        if not changed:
            raise ValueError("Cannot respond to request for authentication.")
        response = await self.transport.request(
            url,
            method,
            data=data,
            headers=headers,
            json=json,
            params=params,
        )

        # One retry if 403 denied (need new token?)
        if response.status_code == 403:
            headers, changed = await self.auth.authenticate_request_async(
                response, headers, refresh=True
            )
            response = await self.transport.request(
                url,
                method,
                data=data,
                headers=headers,
                json=json,
                params=params,
            )

        return response

    @asynccontextmanager
    async def stream_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ):
        """
        Send a request and yield the response with its body still unread.

        This is the streaming counterpart to do_request, and answers an
        authentication challenge the same way: once, then once more with a
        refreshed token if the retry is still refused. do_request itself
        cannot be used here because it returns a response whose body has
        already been read, which is the thing a download must avoid.

        :param url: the URL to issue the request to
        :type url: str
        :param method: the method to use
        :type method: str
        :param headers: headers for the request
        :type headers: dict
        :param params: query string parameters to add to the url
        :type params: dict
        """
        headers = dict(headers or {})
        if isinstance(self.auth, oras.auth.TokenAuth) and self.auth.token is not None:
            headers.update(self.auth.get_auth_header())

        async def open_stream(request_headers):
            stream = self.transport.stream(
                url, method, headers=request_headers, params=params
            )
            return stream, await stream.__aenter__()

        stream, response = await open_stream(headers)
        try:
            # The challenge is in the headers, so it can be read without
            # touching the body; the stream is closed and opened again rather
            # than replayed.
            if response.status_code in [401, 403]:
                headers, changed = await self.auth.authenticate_request_async(
                    response, headers
                )
                if not changed:
                    raise ValueError("Cannot respond to request for authentication.")
                await stream.__aexit__(None, None, None)
                stream, response = await open_stream(headers)

                # One retry if 403 denied (need new token?). As in do_request,
                # the refreshed answer is tried whether or not the backend says
                # it changed anything.
                if response.status_code == 403:
                    headers, changed = await self.auth.authenticate_request_async(
                        response, headers, refresh=True
                    )
                    await stream.__aexit__(None, None, None)
                    stream, response = await open_stream(headers)

            yield response
        finally:
            await stream.__aexit__(None, None, None)

    async def _do_paginated_request(
        self, url: str, callable: Callable[["httpx.Response"], bool]
    ):
        """
        Paginate a request for a URL.

        We look for the "Link" header to get the next URL to ping. If
        the callable returns True, we continue to the next page, otherwise
        we stop.
        """
        parts = urllib.parse.urlparse(url)
        base_url = f"{parts.scheme}://{parts.netloc}"

        while True:
            response = await self.do_request(url, "GET", headers=self.headers)
            self._check_200_response(response)

            if not callable(response):
                break

            link = response.links.get("next", {}).get("url")
            if not link:
                break

            url = urllib.parse.urljoin(base_url, link)

    @decorator.ensure_container
    async def get_tags(self, container: container_type, N=None) -> List[str]:
        """
        Retrieve tags for a package.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param N: limit number of tags, None for all (default)
        :type N: Optional[int]
        """
        retrieve_all = N is None
        tags_url = self._url(container.tags_url(N=N))  # type: ignore
        tags: List[str] = []

        def extract_tags(response) -> bool:
            json = response.json()
            new_tags = json.get("tags") or []
            tags.extend(new_tags)
            return bool(len(new_tags) and (retrieve_all or len(tags) < N))

        await self._do_paginated_request(tags_url, callable=extract_tags)

        if N is not None and len(tags) > N:
            tags = tags[:N]
        return tags

    @decorator.ensure_container
    async def delete_tag(self, container: container_type, tag: str) -> bool:
        """
        Delete a tag for a container.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param tag: name of tag to delete
        :type tag: str
        """
        logger.debug(f"Deleting tag {tag} for {container}")

        head_url = self._url(container.manifest_url(tag))  # type: ignore
        response = await self.do_request(
            head_url,
            "HEAD",
            headers={"Accept": oras.defaults.default_manifest_media_type},
        )
        if response.status_code == 404:
            logger.error(f"Cannot find tag {container}:{tag}")
            return False

        digest = response.headers.get("Docker-Content-Digest")
        if not digest:
            raise RuntimeError("Expected to find Docker-Content-Digest header.")

        delete_url = self._url(container.manifest_url(digest))  # type: ignore
        response = await self.do_request(delete_url, "DELETE")
        if response.status_code != 202:
            raise RuntimeError(f"Delete was not successful: {response.json()}")
        return True

    async def delete_tags(self, name: str, tags) -> List[str]:
        """
        Delete one or more tags, returning those successfully deleted.

        :param name: container URI to parse
        :type name: str
        :param tags: single or multiple tags name to delete
        :type tags: string or list
        """
        if isinstance(tags, str):
            tags = [tags]
        deleted = []
        for tag in tags:
            if await self.delete_tag(name, tag):
                deleted.append(tag)
        return deleted

    async def blob_exists(self, layer: dict, container) -> bool:
        """
        Check if a layer already exists in the registry.

        :param layer: the layer to check for existence
        :type layer: dict
        :param container: where to look for the layer
        :type container: oras.container.Container
        """
        blob_url = container.get_blob_url(layer["digest"])
        response = await self.do_request(self._url(blob_url), "HEAD")
        return response.status_code == 200

    @decorator.ensure_container
    async def download_blob(
        self, container: container_type, digest: str, outfile: str
    ) -> str:
        """
        Stream a blob to a file, without holding it in memory.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param digest: sha256 digest of the blob to retrieve
        :type digest: str
        :param outfile: file to write the blob to
        :type outfile: str
        """
        httpx_module = get_httpx()
        blob_url = self._url(container.get_blob_url(digest))  # type: ignore

        attempt = 0
        while True:
            try:
                outdir = os.path.dirname(outfile)
                if outdir and not os.path.exists(outdir):
                    oras.utils.mkdir_p(outdir)

                async with self.stream_request(
                    blob_url, "GET", headers=self.headers
                ) as r:
                    r.raise_for_status()

                    # opened inside the attempt so a retry starts a fresh file
                    with open(outfile, "wb") as f:
                        async for chunk in r.aiter_bytes(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                return outfile

            # Allow an empty layer to fail and return /dev/null
            except (httpx_module.HTTPError, OSError) as e:
                if digest == oras.defaults.blank_hash:
                    return os.devnull

                # Only a failed connection is worth another go. A status the
                # registry meant, a 404 say, will say the same thing again.
                if not isinstance(e, httpx_module.TransportError):
                    raise
                attempt += 1
                if attempt >= DOWNLOAD_ATTEMPTS:
                    raise
                sleep = decorator.backoff_seconds(attempt - 1, DOWNLOAD_TIMEOUT)
                logger.info(f"Retrying in {sleep} seconds - error: {e}")
                await asyncio.sleep(sleep)

    async def _start_upload_session(self, container, headers: dict) -> str:
        """
        Open a blob upload session and return the url to upload to.

        :param container:  parsed container URI
        :type container: oras.container.Container
        :param headers: headers to start the session with
        :type headers: dict
        """
        upload_url = self._url(container.upload_blob_url())
        r = await self.do_request(upload_url, "POST", headers=headers)
        return self._require_location(r, container)

    async def put_upload(self, blob: str, container, layer: dict) -> "httpx.Response":
        """
        Upload a blob in one request, streamed from disk.

        :param blob: path to blob to upload
        :type blob: str
        :param container:  parsed container URI
        :type container: oras.container.Container
        :param layer: dict from oras.oci.NewLayer
        :type layer: dict
        """
        session_url = await self._start_upload_session(
            container, {"Content-Type": "application/octet-stream"}
        )

        headers = {
            "Content-Length": str(layer["size"]),
            "Content-Type": "application/octet-stream",
        }
        headers.update(self.headers)
        blob_url = oras.utils.append_url_params(
            session_url, {"digest": layer["digest"]}
        )

        # An iterator keeps the blob out of memory. Content-Length is set from
        # the layer, so the registry still gets a sized request. It is passed
        # as a callable because an iterator is spent once it has been read, and
        # this request is re-sent to answer an authentication challenge or by
        # the retry decorator - each attempt needs to read the file again.
        return await self.do_request(
            blob_url,
            method="PUT",
            data=lambda: iter_file(blob, oras.defaults.default_blocksize),
            headers=headers,
        )

    async def chunked_upload(
        self,
        blob: str,
        container,
        layer: dict,
        chunk_size: int = oras.defaults.default_chunksize,
    ) -> "httpx.Response":
        """
        Upload a blob as a series of chunks.

        Same sequence as the synchronous provider: POST to open a session,
        PATCH each chunk with its content range, then PUT with the digest to
        close it.

        :param blob: path to blob to upload
        :type blob: str
        :param container:  parsed container URI
        :type container: oras.container.Container
        :param layer: dict from oras.oci.NewLayer
        :type layer: dict
        :param chunk_size: chunk size in bytes
        :type chunk_size: int
        """
        headers = {"Content-Type": "application/octet-stream", "Content-Length": "0"}
        headers.update(self.headers)
        session_url = await self._start_upload_session(container, headers)

        start = 0
        with open(blob, "rb") as fd:
            for chunk in oras.utils.read_in_chunks(fd, chunk_size=chunk_size):
                end = start + len(chunk) - 1
                content_range = "%s-%s" % (start, end)
                headers = {
                    "Content-Range": content_range,
                    "Content-Length": str(len(chunk)),
                    "Content-Type": "application/octet-stream",
                }
                headers.update(self.headers)

                start = end + 1
                r = await self.do_request(
                    session_url, "PATCH", data=chunk, headers=headers
                )
                self._check_200_response(r)
                session_url = self._require_location(r, container)

        session_url = oras.utils.append_url_params(
            session_url, {"digest": layer["digest"]}
        )
        return await self.do_request(session_url, "PUT", headers=self.headers)

    async def upload_blob(
        self,
        blob: str,
        container: container_type,
        layer: dict,
        do_chunked: bool = False,
        chunk_size: int = oras.defaults.default_chunksize,
    ) -> "httpx.Response":
        """
        Prepare and upload a blob.

        :param blob: path to blob to upload
        :type blob: str
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param layer: dict from oras.oci.NewLayer
        :type layer: dict
        :param do_chunked: if true do chunked blob upload
        :type do_chunked: bool
        :param chunk_size: chunk size in bytes
        :type chunk_size: int
        """
        httpx_module = get_httpx()
        blob = os.path.abspath(blob)
        container = self.get_container(container)

        if await self.blob_exists(layer, container):
            logger.debug(f'layer already exists: {layer["digest"]}')
            return httpx_module.Response(200)

        if not do_chunked:
            response = await self.put_upload(blob, container, layer)
        else:
            response = await self.chunked_upload(
                blob, container, layer, chunk_size=chunk_size
            )

        # An empty layer the registry would not take is still a success
        if (
            response.status_code not in [200, 201, 202]
            and layer["digest"] == oras.defaults.blank_hash
        ):
            response = httpx_module.Response(200)
        return response

    async def upload_manifest(self, manifest: dict, container) -> "httpx.Response":
        """
        Read a manifest file and upload it.

        :param manifest: manifest to upload
        :type manifest: dict
        :param container:  parsed container URI
        :type container: oras.container.Container
        """
        jsonschema.validate(manifest, schema=oras.schemas.manifest)
        headers = {"Content-Type": oras.defaults.default_manifest_media_type}
        return await self.do_request(
            self._url(container.manifest_url()),
            "PUT",
            headers=headers,
            json=manifest,
        )

    async def upload_manifest_content(
        self,
        content: bytes,
        container,
        media_type: str,
        reference: Optional[str] = None,
    ) -> "httpx.Response":
        """
        Upload a manifest from the exact bytes it should be stored as.

        :param content: the raw manifest (or index) bytes to upload
        :type content: bytes
        :param container:  parsed container URI
        :type container: oras.container.Container
        :param media_type: media type of the manifest, used as the Content-Type
        :type media_type: str
        :param reference: tag or digest to upload to, defaults to the container reference
        :type reference: str
        """
        headers = {"Content-Type": media_type}
        return await self.do_request(
            self._url(container.manifest_url(reference)),
            "PUT",
            headers=headers,
            data=content,
        )

    @decorator.ensure_container
    async def get_manifest_content(
        self,
        container: container_type,
        allowed_media_type: Optional[list] = None,
        reference: Optional[str] = None,
    ) -> Tuple[bytes, Optional[str]]:
        """
        Retrieve a manifest as the raw bytes the registry served, with its digest.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param allowed_media_type: one or more allowed media types
        :type allowed_media_type: list
        :param reference: tag or digest to retrieve, defaults to the container reference
        :type reference: str
        :return: tuple of the raw manifest bytes, and the digest reported by the
                 registry in the Docker-Content-Digest header (None if absent)
        """
        if not allowed_media_type:
            allowed_media_type = oras.defaults.default_manifest_accepted_media_types
        headers = {"Accept": ", ".join(allowed_media_type)}

        manifest_url = self._url(container.manifest_url(reference))  # type: ignore
        response = await self.do_request(manifest_url, "GET", headers=headers)

        self._check_200_response(response)
        return response.content, response.headers.get("Docker-Content-Digest")

    @decorator.ensure_container
    async def get_manifest(
        self,
        container: container_type,
        allowed_media_type: Optional[list] = None,
        validation_schema: Optional[dict] = None,
    ) -> dict:
        """
        Retrieve a manifest for a package.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param allowed_media_type: one or more allowed media types
        :type allowed_media_type: str
        :param validation_schema: optional json schema to validate the manifest against
        :type validation_schema: dict
        """
        self.auth.load_configs(container)

        if not allowed_media_type:
            allowed_media_type = oras.defaults.default_manifest_accepted_media_types
        headers = {"Accept": ", ".join(allowed_media_type)}

        get_manifest = self._url(container.manifest_url())  # type: ignore
        response = await self.do_request(get_manifest, "GET", headers=headers)

        self._check_200_response(response)
        manifest = response.json()
        if validation_schema:
            jsonschema.validate(manifest, schema=validation_schema)
        return manifest

    async def push(
        self,
        target: str,
        config_path: Optional[str] = None,
        disable_path_validation: bool = False,
        files: Optional[List] = None,
        manifest_config: Optional[str] = None,
        annotation_file: Optional[str] = None,
        manifest_annotations: Optional[dict] = None,
        subject: Optional[str] = None,
        do_chunked: bool = False,
        chunk_size: int = oras.defaults.default_chunksize,
        quiet: bool = False,
    ) -> "httpx.Response":
        """
        Push a set of files to a target.

        What to push and how to describe it is decided by RegistryBase, so this
        is only the uploading.

        :param target: target location to push to
        :type target: str
        :param config_path: path to a config file
        :type config_path: str
        :param disable_path_validation: ensure paths are relative to the running directory.
        :type disable_path_validation: bool
        :param files: list of files to push
        :type files: list
        :param annotation_file: manifest annotations file
        :type annotation_file: str
        :param manifest_annotations: manifest annotations
        :type manifest_annotations: dict
        :param do_chunked: if true do chunked blob upload
        :type do_chunked: bool
        :param chunk_size: chunk size in bytes
        :type chunk_size: int
        :param subject: optional subject reference
        :type subject: oras.oci.Subject
        :param quiet: suppress the completion message
        :type quiet: bool
        """
        container = self.get_container(target)
        files = files or []
        self.auth.load_configs(
            container, configs=[config_path] if config_path else None
        )

        manifest = oras.oci.NewManifest()
        annotset = oras.oci.Annotations(annotation_file)

        for blob, layer, cleanup_blob in self._iter_push_layers(
            files, annotset, disable_path_validation
        ):
            manifest["layers"].append(layer)

            response = await self.upload_blob(
                blob, container, layer, do_chunked=do_chunked, chunk_size=chunk_size
            )
            self._check_200_response(response)

            if cleanup_blob and os.path.exists(blob):
                os.remove(blob)

        self._apply_manifest_annotations(
            manifest, annotset, manifest_annotations, subject
        )
        conf, config_file = self._prepare_manifest_config(manifest_config, annotset)

        with (
            temporary_empty_config()
            if config_file is None
            else nullcontext(config_file)
        ) as config_file:
            response = await self.upload_blob(config_file, container, conf)

        self._check_200_response(response)

        manifest["config"] = conf
        response = await self.upload_manifest(manifest, container)
        self._check_200_response(response)
        if not quiet:
            logger.info(f"Successfully pushed {container}")
        return response

    async def pull(
        self,
        target: str,
        config_path: Optional[str] = None,
        allowed_media_type: Optional[List] = None,
        overwrite: bool = True,
        outdir: Optional[str] = None,
    ) -> List[str]:
        """
        Pull an artifact from a target.

        Where each layer is written is decided by RegistryBase, so this is only
        the downloading.

        :param target: target location to pull from
        :type target: str
        :param config_path: path to a config file
        :type config_path: str
        :param allowed_media_type: list of allowed media types
        :type allowed_media_type: list or None
        :param overwrite: if output file exists, overwrite
        :type overwrite: bool
        :param outdir: output directory path
        :type outdir: str
        """
        container = self.get_container(target)
        self.auth.load_configs(
            container, configs=[config_path] if config_path else None
        )
        manifest = await self.get_manifest(container, allowed_media_type)
        outdir = outdir or oras.utils.get_tmpdir()

        files = []
        for layer, outfile in self._iter_pull_targets(manifest, outdir, overwrite):
            # A directory will need to be uncompressed and moved
            if layer["mediaType"] == oras.defaults.default_blob_dir_media_type:
                targz = oras.utils.get_tmpfile(suffix=".tar.gz")
                await self.download_blob(container, layer["digest"], targz)
                oras.utils.extract_targz(targz, os.path.dirname(outfile))
            else:
                await self.download_blob(container, layer["digest"], outfile)

            logger.info(f"Successfully pulled {outfile}.")
            files.append(outfile)
        return files
