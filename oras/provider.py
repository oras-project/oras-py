__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import copy
import hashlib
import io
import json
import os
import shutil
import sys
import urllib
from contextlib import contextmanager, nullcontext
from dataclasses import asdict
from http.cookiejar import DefaultCookiePolicy
from tempfile import TemporaryDirectory
from typing import (
    Callable,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)

import jsonschema
import requests

import oras.auth
import oras.container
import oras.decorator as decorator
import oras.defaults
import oras.main.login as login
import oras.oci
import oras.schemas
import oras.utils
from oras.content.layout import LayoutTarget
from oras.content.registry import RegistryTarget
from oras.copy import copy as copy_fn
from oras.copy.options import CopyOptions
from oras.layout import Layout
from oras.logger import logger
from oras.types import Descriptor, container_type
from oras.utils.fileio import PathAndOptionalContent



@contextmanager
def temporary_empty_config() -> Generator[str, None, None]:
    with TemporaryDirectory() as tmpdir:
        config_file = oras.utils.get_tmpfile(tmpdir=tmpdir, suffix=".json")
        oras.utils.write_file(config_file, "{}")
        yield config_file


class Registry:
    """
    Direct interactions with an OCI registry.

    This could also be called a "provider" when we add in the "copy" logic
    and the registry isn't necessarily the "remote" endpoint.
    """

    def __init__(
        self,
        hostname: Optional[str] = None,
        insecure: bool = False,
        tls_verify: Union[bool, str] = True,
        auth_backend: str = "token",
    ):
        """
        Create an ORAS client.

        The hostname is the remote registry to ping.

        :param hostname: the hostname of the registry to ping
        :type hostname: str
        :param insecure: use http instead of https
        :type insecure: bool
        :param tls_verify: enable/disable tls verification or use a custom CA-Bundle
        :type tls_verify: bool
        :param auth_backend: name of the auth backend to use
        :type auth_backend: str
        """
        self.hostname: Optional[str] = hostname
        self.headers: dict = {}
        self.session: requests.Session = requests.Session()
        self.prefix: str = "http" if insecure else "https"
        self._tls_verify = tls_verify

        if not tls_verify:
            requests.packages.urllib3.disable_warnings()  # type: ignore

        # Ignore all cookies: some registries try to set one
        # and take it as a sign they are talking to a browser,
        # trying to set further CSRF cookies (Harbor is such a case)
        self.session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))

        # Get custom backend, pass on session to share
        self.auth = oras.auth.get_auth_backend(
            auth_backend, self.session, insecure, tls_verify=tls_verify
        )

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return "[oras-client]"

    def as_target(self, container: str):
        """
        Return a copy-engine Target adapter for a specific repository.

        The returned RegistryTarget can be passed directly to
        :func:`oras.copy.copy` as either a source or destination.

        :param container: container URI (e.g., "ghcr.io/user/repo:latest")
        :type container: str
        :return: a Target adapter scoped to the given repository
        :rtype: oras.content.registry.RegistryTarget
        """
        return RegistryTarget(self, container)

    def version(self, return_items: bool = False) -> Union[dict, str]:
        """
        Get the version of the client.

        :param return_items : return the dict of version info instead of string
        :type return_items: bool
        """
        version = oras.version.__version__

        python_version = "%s.%s.%s" % (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        )
        versions = {"Version": version, "Python version": python_version}

        # If the user wants the dictionary of items returned
        if return_items:
            return versions

        # Otherwise return a string that can be printed
        return "\n".join(["%s: %s" % (k, v) for k, v in versions.items()])

    def delete_tags(self, name: str, tags: Union[str, list]) -> List[str]:
        """
        Delete one or more tags for a unique resource identifier.

        Returns those successfully deleted.

        :param name: container URI to parse
        :type name: str
        :param tags: single or multiple tags name to delete
        :type N: string or list
        """
        if isinstance(tags, str):
            tags = [tags]
        deleted = []
        for tag in tags:
            if self.delete_tag(name, tag):
                deleted.append(tag)
        return deleted

    def logout(self, hostname: str):
        """
        If auths are loaded, remove a hostname.

        :param hostname: the registry hostname to remove
        :type hostname: str
        """
        self.auth.logout(hostname)

    def login(
        self,
        username: str,
        password: str,
        password_stdin: bool = False,
        tls_verify: bool = True,
        hostname: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> dict:
        """
        Login to a registry.

        :param username: the user account name
        :type username: str
        :param password: the user account password
        :type password: str
        :param password_stdin: get the password from standard input
        :type password_stdin: bool
        :param insecure: use http instead of https
        :type insecure: bool
        :param tls_verify: verify tls
        :type tls_verify: bool
        :param hostname: the hostname to login to
        :type hostname: str
        :param config_path: custom config path to add credentials to
        :type config_path: str
        """
        # Read password from stdin
        if password_stdin:
            password = oras.utils.readline()

        # No username, try to get from stdin
        if not username:
            username = input("Username: ")

        # No password provided
        if not password:
            password = input("Password: ")
            if not password:
                raise ValueError("password required")

        # Cut out early if we didn't get what we need
        if not password or not username:
            return {"Login": "Not successful"}

        # Set basic auth for the auth client
        self.auth.set_basic_auth(username, password)

        # Login
        # https://docker-py.readthedocs.io/en/stable/client.html?highlight=login#docker.client.DockerClient.login
        try:
            client = oras.utils.get_docker_client(tls_verify=tls_verify)
            return client.login(
                username=username,
                password=password,
                registry=hostname,
                dockercfg_path=config_path,
            )

        # Fallback to manual login
        except Exception:
            return login.DockerClient().login(
                username=username,  # type: ignore
                password=password,  # type: ignore
                registry=hostname,  # type: ignore
                dockercfg_path=config_path,
            )

    def set_header(self, name: str, value: str):
        """
        Courtesy function to set a header

        :param name: header name to set
        :type name: str
        :param value: header value to set
        :type value: str
        """
        self.headers.update({name: value})

    def _validate_path(self, path: str) -> bool:
        """
        Ensure a blob path is in the present working directory or below.

        :param path: the path to validate
        :type path: str
        """
        return os.getcwd() in os.path.abspath(path)

    def _parse_manifest_ref(self, ref: str) -> Tuple[str, str]:
        """
        Parse an optional manifest config.

        Examples
        --------
        <path>:<content-type>
        path/to/config:application/vnd.oci.image.config.v1+json
        /dev/null:application/vnd.oci.image.config.v1+json

        :param ref: the manifest reference to parse (examples above)
        :type ref: str
        :return - A Tuple of the path and the content-type, using the default unknown
                  config media type if none found in the reference
        """
        path_content: PathAndOptionalContent = oras.utils.split_path_and_content(ref)
        if not path_content.content:
            path_content.content = oras.defaults.unknown_config_media_type
        return path_content.path, path_content.content

    def upload_blob(
        self,
        blob: str,
        container: container_type,
        layer: dict,
        do_chunked: bool = False,
        chunk_size: int = oras.defaults.default_chunksize,
    ) -> requests.Response:
        """
        Prepare and upload a blob.

        Large artifacts can be uploaded via a chunked approach (post, patch+, put)
        to registries that support it. Larger chunks generally give better throughput.
        Set do_chunked=True for chunked upload.

        :param blob: path to blob to upload
        :type blob: str
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param layer: dict from oras.oci.NewLayer
        :type layer: dict
        :param do_chunked: if true do chunked blob upload. This allows upload of larger oci artifacts.
        :type do_chunked: bool
        :param chunk_size: if true use chunked upload.
        :type chunk_size: int
        """
        blob = os.path.abspath(blob)
        container = self.get_container(container)

        if self.blob_exists(layer, container):
            logger.debug(f'layer already exists: {layer["digest"]}')
            response = requests.Response()
            response.status_code = 200
            return response

        # Chunked for large, otherwise POST and PUT
        # This is currently disabled unless the user asks for it, as
        # it doesn't seem to work for all registries
        if not do_chunked:
            response = self.put_upload(blob, container, layer)
        else:
            response = self.chunked_upload(
                blob,
                container,
                layer,
                chunk_size=chunk_size,
            )

        # If we have an empty layer digest and the registry didn't accept, just return dummy successful response
        if (
            response.status_code not in [200, 201, 202]
            and layer["digest"] == oras.defaults.blank_hash
        ):
            response = requests.Response()
            response.status_code = 200
        return response

    @decorator.ensure_container
    def delete_tag(self, container: container_type, tag: str) -> bool:
        """
        Delete a tag for a container.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param tag: name of tag to delete
        :type tag: str
        """
        logger.debug(f"Deleting tag {tag} for {container}")

        head_url = f"{self.prefix}://{container.manifest_url(tag)}"  # type: ignore

        # get digest of manifest to delete
        response = self.do_request(
            head_url,
            "HEAD",
            headers={"Accept": "application/vnd.oci.image.manifest.v1+json"},
        )
        if response.status_code == 404:
            logger.error(f"Cannot find tag {container}:{tag}")
            return False

        digest = response.headers.get("Docker-Content-Digest")
        if not digest:
            raise RuntimeError("Expected to find Docker-Content-Digest header.")

        delete_url = f"{self.prefix}://{container.manifest_url(digest)}"  # type: ignore
        response = self.do_request(delete_url, "DELETE")
        if response.status_code != 202:
            raise RuntimeError(f"Delete was not successful: {response.json()}")
        return True

    @decorator.ensure_container
    def get_tags(self, container: container_type, N=None) -> List[str]:
        """
        Retrieve tags for a package.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param N: limit number of tags, None for all (default)
        :type N: Optional[int]
        """
        retrieve_all = N is None
        tags_url = f"{self.prefix}://{container.tags_url(N=N)}"  # type: ignore
        tags: List[str] = []

        def extract_tags(response: requests.Response):
            """
            Determine if we should continue based on new tags and under limit.
            """
            json = response.json()
            new_tags = json.get("tags") or []
            tags.extend(new_tags)
            return len(new_tags) and (retrieve_all or len(tags) < N)

        self._do_paginated_request(tags_url, callable=extract_tags)

        # If we got a longer set than was asked for
        if N is not None and len(tags) > N:
            tags = tags[:N]
        return tags

    def _do_paginated_request(
        self, url: str, callable: Callable[[requests.Response], bool]
    ):
        """
        Paginate a request for a URL.

        We look for the "Link" header to get the next URL to ping. If
        the callable returns True, we continue to the next page, otherwise
        we stop.
        """
        # Save the base url to add parameters to, assuming only the params change
        parts = urllib.parse.urlparse(url)
        base_url = f"{parts.scheme}://{parts.netloc}"

        # get all results using the pagination
        while True:
            response = self.do_request(url, "GET", headers=self.headers)

            # Check 200 response, show errors if any
            self._check_200_response(response)

            want_more = callable(response)
            if not want_more:
                break

            link = response.links.get("next", {}).get("url")

            # Get the next link
            if not link:
                break

            # use link + base url to continue with next page
            url = urllib.parse.urljoin(base_url, link)

    @decorator.ensure_container
    def get_blob(
        self,
        container: container_type,
        digest: str,
        stream: bool = False,
        head: bool = False,
    ) -> requests.Response:
        """
        Retrieve a blob for a package.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param digest: sha256 digest of the blob to retrieve
        :type digest: str
        :param stream: stream the response (or not)
        :type stream: bool
        :param head: use head to determine if blob exists
        :type head: bool
        """
        method = "GET" if not head else "HEAD"
        blob_url = f"{self.prefix}://{container.get_blob_url(digest)}"  # type: ignore
        return self.do_request(blob_url, method, headers=self.headers, stream=stream)

    def get_container(self, name: container_type) -> oras.container.Container:
        """
        Courtesy function to get a container from a URI.

        :param name: unique resource identifier to parse
        :type name: oras.container.Container or str
        """
        if isinstance(name, oras.container.Container):
            return name
        return oras.container.Container(name, registry=self.hostname)

    @decorator.ensure_container
    def download_blob(
        self, container: container_type, digest: str, outfile: str
    ) -> str:
        """
        Stream download a blob into an output file.

        This function is a wrapper around get_blob.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        """
        try:
            # Ensure output directory exists first
            outdir = os.path.dirname(outfile)
            if outdir and not os.path.exists(outdir):
                oras.utils.mkdir_p(outdir)
            with self.get_blob(container, digest, stream=True) as r:
                r.raise_for_status()
                with open(outfile, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

        # Allow an empty layer to fail and return /dev/null
        except Exception as e:
            if digest == oras.defaults.blank_hash:
                return os.devnull
            raise e
        return outfile

    def put_upload(
        self,
        blob: str,
        container: oras.container.Container,
        layer: dict,
    ) -> requests.Response:
        """
        Upload to a registry via put.

        :param blob: path to blob to upload
        :type blob: str
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param layer: dict from oras.oci.NewLayer
        :type layer: dict
        """
        # Start an upload session
        headers = {"Content-Type": "application/octet-stream"}

        upload_url = f"{self.prefix}://{container.upload_blob_url()}"
        r = self.do_request(upload_url, "POST", headers=headers)

        # Location should be in the header
        session_url = self._get_location(r, container)
        if not session_url:
            raise ValueError(f"Issue retrieving session url: {r.json()}")

        # PUT to upload blob url
        headers = {
            "Content-Length": str(layer["size"]),
            "Content-Type": "application/octet-stream",
        }
        headers.update(self.headers)
        blob_url = oras.utils.append_url_params(
            session_url, {"digest": layer["digest"]}
        )
        with open(blob, "rb") as fd:
            response = self.do_request(
                blob_url,
                method="PUT",
                data=fd.read(),
                headers=headers,
            )
        return response

    def blob_exists(self, layer: dict, container: oras.container.Container) -> bool:
        """
        Check if a layer already exists in the registry.

        :param layer: the layer to check for existence
        :type layer: oras.oci.Layer
        :param container: the container to determine where to look for layer existence
        :type container: oras.container.Container
        """
        blob_url = container.get_blob_url(layer["digest"])
        response = self.do_request(f"{self.prefix}://{blob_url}", "HEAD")
        return response.status_code == 200

    def _get_location(
        self, r: requests.Response, container: oras.container.Container
    ) -> str:
        """
        Parse the location header and ensure it includes a hostname.
        This currently assumes if there isn't a hostname, we are pushing to
        the same registry hostname of the original request.

        :param r: requests response with headers
        :type r: requests.Response
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        """
        session_url = r.headers.get("location", "")
        if not session_url:
            return session_url

        # Some registries do not return the full registry hostname.  Check that
        # the url starts with a protocol scheme, change tracked with:
        # https://github.com/oras-project/oras-py/issues/78
        prefix = f"{self.prefix}://{container.registry}"

        if not session_url.startswith("http"):
            session_url = f"{prefix}{session_url}"
        return session_url

    def chunked_upload(
        self,
        blob: str,
        container: oras.container.Container,
        layer: dict,
        chunk_size: int = oras.defaults.default_chunksize,
    ) -> requests.Response:
        """
        Upload via a chunked upload.

        :param blob: path to blob to upload
        :type blob: str
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param layer: dict from oras.oci.NewLayer
        :type layer: dict
        :param chunk_size: chunk size in bytes
        :type chunk_size: int
        """
        # Start an upload session
        headers = {"Content-Type": "application/octet-stream", "Content-Length": "0"}
        headers.update(self.headers)

        upload_url = f"{self.prefix}://{container.upload_blob_url()}"
        r = self.do_request(upload_url, "POST", headers=headers)

        # Location should be in the header
        session_url = self._get_location(r, container)
        if not session_url:
            raise ValueError(f"Issue retrieving session url: {r.json()}")

        # Read the blob in chunks, for each do a patch
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

                # Important to update with auth token if acquired
                # TODO call to auth here
                start = end + 1
                r = self.do_request(
                    session_url, "PATCH", data=chunk, headers=headers
                )
                self._check_200_response(r)
                session_url = self._get_location(r, container)
                if not session_url:
                    raise ValueError(f"Issue retrieving session url: {r.json()}")

        # Finally, issue a PUT request to close blob
        session_url = oras.utils.append_url_params(
            session_url, {"digest": layer["digest"]}
        )
        return self.do_request(session_url, "PUT", headers=self.headers)

    def _check_200_response(self, response: requests.Response):
        """
        Helper function to ensure some flavor of 200

        :param response: request response to inspect
        :type response: requests.Response
        """
        if response.status_code not in [200, 201, 202]:
            self._parse_response_errors(response)
            raise ValueError(f"Issue with {response.request.url}: {response.reason}")

    def _parse_response_errors(self, response: requests.Response):
        """
        Given a failed request, look for OCI formatted error messages.

        :param response: request response to inspect
        :type response: requests.Response
        """
        try:
            msg = response.json()
            for error in msg.get("errors", []):
                if isinstance(error, dict) and "message" in error:
                    logger.error(error["message"])
        except Exception:
            pass

    def upload_manifest(
        self,
        manifest: dict,
        container: oras.container.Container,
    ) -> requests.Response:
        """
        Read a manifest file and upload it.

        :param manifest: manifest to upload
        :type manifest: dict
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        """
        jsonschema.validate(manifest, schema=oras.schemas.manifest)
        headers = {
            "Content-Type": oras.defaults.default_manifest_media_type,
        }
        return self.do_request(
            f"{self.prefix}://{container.manifest_url()}",  # noqa
            "PUT",
            headers=headers,
            json=manifest,
        )

    def copy(
        self,
        src: str,
        dst: str,
        config_path: Optional[str] = None,
        opts: "Optional[CopyOptions]" = None,
    ) -> Descriptor:
        """
        Copy content from one repository to another using the copy engine.

        Uses the copy engine's DAG-aware graph traversal to copy all content
        (manifests, configs, and layers) from the source reference to the
        destination reference.  Both endpoints use this Registry's credentials,
        so the method works for same-registry cross-repository copies as well as
        cross-registry copies where the same credentials are valid for both.

        :param src: source reference, e.g. "ghcr.io/user/repo:v1.0"
        :type src: str
        :param dst: destination reference, e.g. "ghcr.io/user/other:v2.0"
        :type dst: str
        :param config_path: path to an auth config file applied to both endpoints
        :type config_path: str
        :param opts: copy engine options (default: None for default settings)
        :type opts: oras.copy.options.CopyOptions
        :return: the root descriptor that was copied
        :rtype: dict
        """

        src_container = self.get_container(src)
        dst_container = self.get_container(dst)

        configs = [config_path] if config_path else None
        self.auth.load_configs(src_container, configs=configs)
        self.auth.load_configs(dst_container, configs=configs)

        src_target = RegistryTarget(self, src_container, opts)
        dst_target = RegistryTarget(self, dst_container, opts)

        src_ref = src_container.digest or src_container.tag
        dst_ref = dst_container.digest or dst_container.tag

        return copy_fn(src_target, src_ref, dst_target, dst_ref, opts)

    def push(
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
    ) -> requests.Response:
        """
        Push a set of files to a target

        :param config_path: path to a config file
        :type config_path: str
        :param disable_path_validation: ensure paths are relative to the running directory.
        :type disable_path_validation: bool
        :param files: list of files to push
        :type files: list
        :param insecure: allow registry to use http
        :type insecure: bool
        :param annotation_file: manifest annotations file
        :type annotation_file: str
        :param manifest_annotations: manifest annotations
        :type manifest_annotations: dict
        :param target: target location to push to
        :type target: str
        :param do_chunked: if true do chunked blob upload
        :type do_chunked: bool
        :param chunk_size: chunk size in bytes
        :type chunk_size: int
        :param subject: optional subject reference
        :type subject: oras.oci.Subject
        """

        container = self.get_container(target)
        files = files or []
        self.auth.load_configs(
            container, configs=[config_path] if config_path else None
        )

        # A push is a directional copy: local files -> registry.  Pack the
        # files (plus manifest config) into a temporary OCI layout, then copy
        # that layout up to the registry via the copy engine.  Note this means
        # blobs are written to a temporary layout on disk before upload; upload
        # failures surface as oras.copy.errors.CopyError.
        dst_ref = container.digest or container.tag
        opts = CopyOptions()
        opts.graph.do_chunked = do_chunked
        opts.graph.chunk_size = chunk_size

        with TemporaryDirectory() as tmp_layout_dir:
            layout = Layout(tmp_layout_dir, validate=False)
            src = LayoutTarget(layout)
            self._pack_files_to_layout(
                src,
                files=files,
                disable_path_validation=disable_path_validation,
                manifest_config=manifest_config,
                annotation_file=annotation_file,
                manifest_annotations=manifest_annotations,
                subject=subject,
                tag=dst_ref,
            )

            dst = RegistryTarget(self, container, opts)
            copy_fn(src, dst_ref, dst, dst_ref, opts)
            response = dst.last_manifest_response

        # Return the real manifest PUT response from the copy.  Fall back to a
        # GET only in the unexpected case that no manifest was pushed.
        if response is None:
            headers = {"Accept": oras.defaults.default_manifest_media_type}
            response = self.do_request(
                f"{self.prefix}://{container.manifest_url()}",
                "GET",
                headers=headers,
            )
        self._check_200_response(response)
        print(f"Successfully pushed {container}")
        return response

    def _pack_files_to_layout(
        self,
        layout_target: "LayoutTarget",
        files: List,
        disable_path_validation: bool = False,
        manifest_config: Optional[str] = None,
        annotation_file: Optional[str] = None,
        manifest_annotations: Optional[dict] = None,
        subject: Optional[oras.oci.Subject] = None,
        tag: str = oras.defaults.default_tag,
    ) -> Descriptor:
        """
        Pack a set of files into an OCI layout via a LayoutTarget.

        Builds layer blobs, a manifest config blob, and the image manifest,
        writing each into the layout's content-addressable store and tagging
        the manifest with ``tag``. Mirrors the manifest assembly done by
        :meth:`push`, but writes to a layout (instead of uploading directly)
        so the result can be transferred by the copy engine.

        :return: the manifest descriptor that was written and tagged
        :rtype: dict
        """
        # Prepare a new manifest
        manifest = oras.oci.NewManifest()

        # A lookup of annotations we can add (to blobs or manifest)
        annotset = oras.oci.Annotations(annotation_file)
        media_type = None

        # Pack files as blobs
        for blob in files:
            # You can provide a blob + content type
            path_content: PathAndOptionalContent = oras.utils.split_path_and_content(
                str(blob)
            )
            blob = path_content.path
            media_type = path_content.content

            # Must exist
            if not os.path.exists(blob):
                raise FileNotFoundError(f"{blob} does not exist.")

            # Path validation means blob must be relative to PWD.
            if not disable_path_validation:
                if not self._validate_path(blob):
                    raise ValueError(
                        f"Blob {blob} is not in the present working directory context."
                    )

            # Save directory or blob name before compressing
            blob_name = os.path.basename(blob)

            # If it's a directory, we need to compress
            cleanup_blob = False
            if os.path.isdir(blob):
                blob = oras.utils.make_targz(blob)
                cleanup_blob = True

            # Create a new layer from the blob
            layer = oras.oci.NewLayer(blob, is_dir=cleanup_blob, media_type=media_type)
            annotations = annotset.get_annotations(blob)

            # Always strip blob_name of path separator
            layer["annotations"] = {
                oras.defaults.annotation_title: blob_name.strip(os.sep)
            }
            if annotations:
                layer["annotations"].update(annotations)

            # update the manifest with the new layer
            manifest["layers"].append(layer)
            logger.debug(f"Preparing layer {layer}")

            # Write the blob layer into the layout
            try:
                with open(blob, "rb") as f:
                    layout_target.push(layer, f)
            finally:
                # Do we need to cleanup a temporary targz?
                if cleanup_blob and os.path.exists(blob):
                    os.remove(blob)

        # Add annotations to the manifest, if provided
        manifest_annots = annotset.get_annotations("$manifest") or {}

        # Custom manifest annotations from client key=value pairs
        # These over-ride any potentially provided from file
        custom_annots = copy.deepcopy(manifest_annotations)
        if custom_annots:
            manifest_annots.update(custom_annots)
        if manifest_annots:
            manifest["annotations"] = manifest_annots

        if subject:
            manifest["subject"] = asdict(subject)

        # Prepare the manifest config (temporary or one provided)
        config_annots = annotset.get_annotations("$config")
        if manifest_config:
            ref, media_type = self._parse_manifest_ref(manifest_config)
            conf, config_file = oras.oci.ManifestConfig(ref, media_type)
        else:
            conf, config_file = oras.oci.ManifestConfig()

        # Config annotations?
        if config_annots:
            conf["annotations"] = config_annots

        # Config is just another layer blob!
        logger.debug(f"Preparing config {conf}")
        with (
            temporary_empty_config()
            if config_file is None
            else nullcontext(config_file)
        ) as config_file:
            with open(config_file, "rb") as f:
                layout_target.push(conf, f)

        # Finalize the manifest and write it into the layout
        manifest["config"] = conf
        jsonschema.validate(manifest, schema=oras.schemas.manifest)
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_desc = {
            "mediaType": oras.defaults.default_manifest_media_type,
            "digest": "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
            "size": len(manifest_bytes),
        }
        layout_target.push(manifest_desc, io.BytesIO(manifest_bytes))
        layout_target.tag(manifest_desc, tag)
        return manifest_desc

    def pull(
        self,
        target: str,
        config_path: Optional[str] = None,
        allowed_media_type: Optional[List] = None,
        overwrite: bool = True,
        outdir: Optional[str] = None,
    ) -> List[str]:
        """
        Pull an artifact from a target

        :param config_path: path to a config file
        :type config_path: str
        :param allowed_media_type: list of allowed media types
        :type allowed_media_type: list or None
        :param overwrite: if output file exists, overwrite
        :type overwrite: bool
        :param manifest_config_ref: save manifest config to this file
        :type manifest_config_ref: str
        :param outdir: output directory path
        :type outdir: str
        :param target: target location to pull from
        :type target: str
        """

        container = self.get_container(target)
        self.auth.load_configs(
            container, configs=[config_path] if config_path else None
        )
        outdir = outdir or oras.utils.get_tmpdir()

        # Resolve and validate the manifest up front.  This preserves the
        # original Accept-header content negotiation and media-type rejection
        # (raised before any blob transfer), and lets us avoid downloading a
        # full multi-arch DAG for a reference that has no files to extract.
        manifest = self.get_manifest(container, allowed_media_type)

        layers = manifest.get("layers", [])
        if not layers:
            # e.g. an image index: nothing to materialize as flat files.
            return []

        # A pull is a directional copy: registry -> local OCI layout.  We copy
        # the artifact's content DAG into a temporary layout via the copy
        # engine, then materialize the layers as flat files in outdir.  Note
        # blobs are written to a temporary layout on disk before extraction.
        files: List[str] = []
        with TemporaryDirectory() as tmp_layout_dir:
            layout = Layout(tmp_layout_dir, validate=False)
            src_ref = container.digest or container.tag
            layout.copy_from_registry(
                provider=self, source=target, tag=src_ref
            )

            for layer in layers:
                filename = (layer.get("annotations") or {}).get(
                    oras.defaults.annotation_title
                )

                # If we don't have a filename, default to digest.
                if not filename:
                    filename = layer["digest"]

                # This raises an error if there is a malicious path
                outfile = oras.utils.sanitize_path(
                    outdir, os.path.join(outdir, filename)
                )

                if not overwrite and os.path.exists(outfile):
                    logger.warning(
                        f"{outfile} already exists and --keep-old-files set, will not overwrite."
                    )
                    continue

                blob_path = layout.digest_to_blob_path(layer["digest"])

                # Ensure the destination directory exists (mirrors the
                # behavior of download_blob, which created it before writing).
                dest_dir = os.path.dirname(outfile)
                if dest_dir and not os.path.exists(dest_dir):
                    oras.utils.mkdir_p(dest_dir)

                # A directory will need to be uncompressed and moved
                if layer["mediaType"] == oras.defaults.default_blob_dir_media_type:
                    oras.utils.extract_targz(
                        str(blob_path), os.path.dirname(outfile)
                    )

                # Anything else just copied directly to the output path
                else:
                    shutil.copyfile(str(blob_path), outfile)
                logger.info(f"Successfully pulled {outfile}.")
                files.append(outfile)
        return files

    @decorator.ensure_container
    def get_manifest(
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
        # Load authentication configs for the container's registry
        # This ensures credentials are available for authenticated registries
        self.auth.load_configs(container)

        if not allowed_media_type:
            allowed_media_type = oras.defaults.default_manifest_accepted_media_types
        headers = {"Accept": ", ".join(allowed_media_type)}

        get_manifest = f"{self.prefix}://{container.manifest_url()}"  # type: ignore
        response = self.do_request(get_manifest, "GET", headers=headers)

        self._check_200_response(response)
        manifest = response.json()
        if validation_schema:
            jsonschema.validate(manifest, schema=validation_schema)
        return manifest

    @decorator.retry()
    def do_request(
        self,
        url: str,
        method: str = "GET",
        data: Optional[Union[dict, bytes]] = None,
        headers: Optional[dict] = None,
        json: Optional[dict] = None,
        stream: bool = False,
    ) -> requests.Response:
        """
        Do a request. This is a wrapper around requests to handle retry auth.

        :param url: the URL to issue the request to
        :type url: str
        :param method: the method to use (GET, DELETE, POST, PUT, PATCH)
        :type method: str
        :param data: data for requests
        :type data: dict or bytes
        :param headers: headers for the request
        :type headers: dict
        :param json: json data for requests
        :type json: dict
        :param stream: stream the responses
        :type stream: bool
        """
        if headers is None:
            headers = {}

        def send() -> requests.Response:
            return self.session.request(
                method,
                url,
                data=data,
                json=json,
                headers=headers,
                stream=stream,
                verify=self._tls_verify,
            )

        # Make the request, attempting to use an auth token if previously obtained
        if isinstance(self.auth, oras.auth.TokenAuth) and self.auth.token is not None:
            headers.update(self.auth.get_auth_header())
        response = send()

        # A 401 response is a request for authentication, 404 is not found
        if response.status_code not in [401, 403]:
            return response

        # Otherwise, authenticate the request and retry
        headers, changed = self.auth.authenticate_request(response, headers)
        if not changed:
            raise ValueError("Cannot respond to request for authentication.")
        response = send()

        # One retry if 403 denied (need new token?)
        if response.status_code == 403:
            headers, changed = self.auth.authenticate_request(
                response, headers, refresh=True
            )
            response = send()

        return response
