__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import copy
import os
import urllib
from typing import Callable, List, Optional, Tuple, Union

import jsonschema
import requests

import oras.auth
import oras.container
import oras.decorator as decorator
import oras.oci
import oras.schemas
import oras.utils
from oras.logger import logger
from oras.utils.fileio import PathAndOptionalContent

# container type can be string or container
container_type = Union[str, oras.container.Container]


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
        tls_verify: bool = True,
    ):
        """
        Create a new registry provider.

        :param hostname: the registry hostname (optional)
        :type hostname: str
        :param insecure: use http instead of https
        :type insecure: bool
        :param tls_verify: verify TLS certificates
        :type tls_verify: bool
        """
        self.hostname: Optional[str] = hostname
        self.headers: dict = {}
        self.session: requests.Session = requests.Session()
        self.prefix: str = "http" if insecure else "https"
        self.token: Optional[str] = None
        self._auths: dict = {}
        self._basic_auth = None
        self._tls_verify = tls_verify

        if not tls_verify:
            requests.packages.urllib3.disable_warnings()  # type: ignore

    def logout(self, hostname: str):
        """
        If auths are loaded, remove a hostname.

        :param hostname: the registry hostname to remove
        :type hostname: str
        """
        # Remove any basic auth or token
        self._basic_auth = None
        self.token = None

        if not self._auths:
            logger.info(f"You are not logged in to {hostname}")
            return

        for host in oras.utils.iter_localhosts(hostname):
            if host in self._auths:
                del self._auths[host]
                logger.info(f"You have successfully logged out of {hostname}")
                return
        logger.info(f"You are not logged in to {hostname}")

    @decorator.ensure_container
    def load_configs(self, container: container_type, configs: Optional[list] = None):
        """
        Load configs to discover credentials for a specific container.

        This is typically just called once. We always add the default Docker
        config to the set.s

        :param container: the parsed container URI with components
        :type container: oras.container.Container
        :param configs: list of configs to read (optional)
        :type configs: list
        """
        if not self._auths:
            self._auths = oras.auth.load_configs(configs)
        for registry in oras.utils.iter_localhosts(container.registry):  # type: ignore
            if self._load_auth(registry):
                return

    def _load_auth(self, hostname: str) -> bool:
        """
        Look for and load a named authentication token.

        :param hostname: the registry hostname to look for
        :type hostname: str
        """
        # Note that the hostname can be defined without a token
        if hostname in self._auths:
            auth = self._auths[hostname].get("auth")

            # Case 1: they use a credsStore we don't know how to read
            if not auth and "credsStore" in self._auths[hostname]:
                logger.warning(
                    '"credsStore" found in your ~/.docker/config.json, which is not supported by oras-py. Remove it, docker login, and try again.'
                )
                return False

            # Case 2: no auth there (wonky file)
            elif not auth:
                return False
            self._basic_auth = auth
            return True
        return False

    def set_basic_auth(self, username: str, password: str):
        """
        Set basic authentication.

        :param username: the user account name
        :type username: str
        :param password: the user account password
        :type password: str
        """
        self._basic_auth = oras.auth.get_basic_auth(username, password)
        self.set_header("Authorization", "Basic %s" % self._basic_auth)

    def set_token_auth(self, token: str):
        """
        Set token authentication.

        :param token: the bearer token
        :type token: str
        """
        self.token = token
        self.set_header("Authorization", "Bearer %s" % token)

    def reset_basic_auth(self):
        """
        Given we have basic auth, reset it.
        """
        if "Authorization" in self.headers:
            del self.headers["Authorization"]
        if self._basic_auth:
            self.set_header("Authorization", "Basic %s" % self._basic_auth)

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
    ) -> requests.Response:
        """
        Prepare and upload a blob.

        Sizes > 1024 are uploaded via a chunked approach (post, patch+, put)
        and <= 1024 is a single post then put.

        :param blob: path to blob to upload
        :type blob: str
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param layer: dict from oras.oci.NewLayer
        :type layer: dict
        """
        blob = os.path.abspath(blob)
        container = self.get_container(container)

        # Always reset headers between uploads
        self.reset_basic_auth()

        # Chunked for large, otherwise POST and PUT
        # This is currently disabled unless the user asks for it, as
        # it doesn't seem to work for all registries
        if not do_chunked:
            response = self.put_upload(blob, container, layer)
        else:
            response = self.chunked_upload(blob, container, layer)

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
            raise RuntimeError("Delete was not successful: {response.json()}")
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
            url = f"{base_url}{link}"

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

    # Functions to be deprecated in favor of exposed ones
    @decorator.ensure_container
    def _download_blob(
        self, container: container_type, digest: str, outfile: str
    ) -> str:
        logger.warning(
            "This function is deprecated in favor of download_blob and will be removed by 0.1.2"
        )
        return self.download_blob(container, digest, outfile)

    def _put_upload(
        self, blob: str, container: oras.container.Container, layer: dict
    ) -> requests.Response:
        logger.warning(
            "This function is deprecated in favor of put_upload and will be removed by 0.1.2"
        )
        return self.put_upload(blob, container, layer)

    def _chunked_upload(
        self, blob: str, container: oras.container.Container, layer: dict
    ) -> requests.Response:
        logger.warning(
            "This function is deprecated in favor of chunked_upload and will be removed by 0.1.2"
        )
        return self.chunked_upload(blob, container, layer)

    def _upload_manifest(
        self, manifest: dict, container: oras.container.Container
    ) -> requests.Response:
        logger.warning(
            "This function is deprecated in favor of upload_manifest and will be removed by 0.1.2"
        )
        return self.upload_manifest(manifest, container)

    def _upload_blob(
        self,
        blob: str,
        container: container_type,
        layer: dict,
        do_chunked: bool = False,
    ) -> requests.Response:
        logger.warning(
            "This function is deprecated in favor of upload_blob and will be removed by 0.1.2"
        )
        return self.upload_blob(blob, container, layer, do_chunked)

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
        self, blob: str, container: oras.container.Container, layer: dict
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
        self, blob: str, container: oras.container.Container, layer: dict
    ) -> requests.Response:
        """
        Upload via a chunked upload.

        :param blob: path to blob to upload
        :type blob: str
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param layer: dict from oras.oci.NewLayer
        :type layer: dict
        """
        # Start an upload session
        headers = {"Content-Type": "application/octet-stream", "Content-Length": "0"}
        upload_url = f"{self.prefix}://{container.upload_blob_url()}"
        r = self.do_request(upload_url, "POST", headers=headers)

        # Location should be in the header
        session_url = self._get_location(r, container)
        if not session_url:
            raise ValueError(f"Issue retrieving session url: {r.json()}")

        # Read the blob in chunks, for each do a patch
        start = 0
        with open(blob, "rb") as fd:
            for chunk in oras.utils.read_in_chunks(fd):
                if not chunk:
                    break

                end = start + len(chunk) - 1
                content_range = "%s-%s" % (start, end)
                headers = {
                    "Content-Range": content_range,
                    "Content-Length": str(len(chunk)),
                    "Content-Type": "application/octet-stream",
                }

                # Important to update with auth token if acquired
                headers.update(self.headers)
                start = end + 1
                self._check_200_response(
                    self.do_request(session_url, "PATCH", data=chunk, headers=headers)
                )

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
        self, manifest: dict, container: oras.container.Container
    ) -> requests.Response:
        """
        Read a manifest file and upload it.

        :param manifest: manifest to upload
        :type manifest: dict
        :param container:  parsed container URI
        :type container: oras.container.Container or str
        """
        self.reset_basic_auth()
        jsonschema.validate(manifest, schema=oras.schemas.manifest)
        headers = {
            "Content-Type": oras.defaults.default_manifest_media_type,
            "Content-Length": str(len(manifest)),
        }
        return self.do_request(
            f"{self.prefix}://{container.manifest_url()}",  # noqa
            "PUT",
            headers=headers,
            json=manifest,
        )

    def push(self, *args, **kwargs) -> requests.Response:
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
        """
        container = self.get_container(kwargs["target"])
        self.load_configs(container, configs=kwargs.get("config_path"))

        # Hold state of request for http/https
        validate_path = not kwargs.get("disable_path_validation", False)

        # Prepare a new manifest
        manifest = oras.oci.NewManifest()

        # A lookup of annotations we can add (to blobs or manifest)
        annotset = oras.oci.Annotations(kwargs.get("annotation_file"))
        media_type = None

        # Upload files as blobs
        for blob in kwargs.get("files", []):
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
            if validate_path:
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

            # Upload the blob layer
            response = self.upload_blob(blob, container, layer)
            self._check_200_response(response)

            # Do we need to cleanup a temporary targz?
            if cleanup_blob and os.path.exists(blob):
                os.remove(blob)

        # Add annotations to the manifest, if provided
        manifest_annots = annotset.get_annotations("$manifest") or {}

        # Custom manifest annotations from client key=value pairs
        # These over-ride any potentially provided from file
        custom_annots = kwargs.get("manifest_annotations")
        if custom_annots:
            manifest_annots.update(custom_annots)
        if manifest_annots:
            manifest["annotations"] = manifest_annots

        # Prepare the manifest config (temporary or one provided)
        manifest_config = kwargs.get("manifest_config")
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
        response = self.upload_blob(config_file, container, conf)
        self._check_200_response(response)

        # Final upload of the manifest
        manifest["config"] = conf
        self._check_200_response(self.upload_manifest(manifest, container))
        print(f"Successfully pushed {container}")
        return response

    def pull(self, *args, **kwargs) -> List[str]:
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
        allowed_media_type = kwargs.get("allowed_media_type")
        container = self.get_container(kwargs["target"])
        self.load_configs(container, configs=kwargs.get("config_path"))
        manifest = self.get_manifest(container, allowed_media_type)
        outdir = kwargs.get("outdir") or oras.utils.get_tmpdir()
        overwrite = kwargs.get("overwrite", True)

        files = []
        for layer in manifest.get("layers", []):
            filename = (layer.get("annotations") or {}).get(
                oras.defaults.annotation_title
            )

            # If we don't have a filename, default to digest. Hopefully does not happen
            if not filename:
                filename = layer["digest"]

            # This raises an error if there is a malicious path
            outfile = oras.utils.sanitize_path(outdir, os.path.join(outdir, filename))

            if not overwrite and os.path.exists(outfile):
                logger.warning(
                    f"{outfile} already exists and --keep-old-files set, will not overwrite."
                )
                continue

            # A directory will need to be uncompressed and moved
            if layer["mediaType"] == oras.defaults.default_blob_dir_media_type:
                targz = oras.utils.get_tmpfile(suffix=".tar.gz")
                self.download_blob(container, layer["digest"], targz)

                # The artifact will be extracted to the correct name
                oras.utils.extract_targz(targz, os.path.dirname(outfile))

            # Anything else just extracted directly
            else:
                self.download_blob(container, layer["digest"], outfile)
            logger.info(f"Successfully pulled {outfile}.")
            files.append(outfile)
        return files

    @decorator.ensure_container
    def get_manifest(
        self, container: container_type, allowed_media_type: list = None
    ) -> dict:
        """
        Retrieve a manifest for a package.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param allowed_media_type: one or more allowed media types
        :type allowed_media_type: str
        """
        if not allowed_media_type:
            allowed_media_type = [oras.defaults.default_manifest_media_type]
        headers = {"Accept": ";".join(allowed_media_type)}

        get_manifest = f"{self.prefix}://{container.manifest_url()}"  # type: ignore
        response = self.do_request(get_manifest, "GET", headers=headers)
        self._check_200_response(response)
        manifest = response.json()
        jsonschema.validate(manifest, schema=oras.schemas.manifest)
        return manifest

    @decorator.classretry
    def do_request(
        self,
        url: str,
        method: str = "GET",
        data: Union[dict, bytes] = None,
        headers: dict = None,
        json: dict = None,
        stream: bool = False,
    ):
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
        headers = headers or {}

        # Make the request and return to calling function, unless requires auth
        response = self.session.request(
            method,
            url,
            data=data,
            json=json,
            headers=headers,
            stream=stream,
            verify=self._tls_verify,
        )

        # A 401 response is a request for authentication
        if response.status_code not in [401, 404]:
            return response

        # Otherwise, authenticate the request and retry
        if self.authenticate_request(response):
            headers.update(self.headers)
            response = self.session.request(
                method,
                url,
                data=data,
                json=json,
                headers=headers,
                stream=stream,
            )

        # Fallback to using Authorization if already required
        # This is a catch for EC2. I don't think this is correct
        # A basic token should be used for a bearer one.
        if response.status_code in [401, 404] and "Authorization" in self.headers:
            logger.debug("Trying with provided Basic Authorization...")
            headers.update(self.headers)
            response = self.session.request(
                method,
                url,
                data=data,
                json=json,
                headers=headers,
                stream=stream,
            )

        return response

    def authenticate_request(self, originalResponse: requests.Response) -> bool:
        """
        Authenticate Request
        Given a response, look for a Www-Authenticate header to parse.

        We return True/False to indicate if the request should be retried.

        :param originalResponse: original response to get the Www-Authenticate header
        :type originalResponse: requests.Response
        """
        authHeaderRaw = originalResponse.headers.get("Www-Authenticate")
        if not authHeaderRaw:
            logger.debug(
                "Www-Authenticate not found in original response, cannot authenticate."
            )
            return False

        # If we have a token, set auth header (base64 encoded user/pass)
        if self.token:
            self.set_header("Authorization", "Bearer %s" % self._basic_auth)
            return True

        headers = copy.deepcopy(self.headers)
        h = oras.auth.parse_auth_header(authHeaderRaw)

        if "Authorization" not in headers:
            # First try to request an anonymous token
            logger.debug("No Authorization, requesting anonymous token")
            if self.request_anonymous_token(h):
                logger.debug("Successfully obtained anonymous token!")
                return True

            logger.error(
                "This endpoint requires a token. Please set "
                "oras.provider.Registry.set_basic_auth(username, password) "
                "first or use oras-py login to do the same."
            )
            return False

        params = {}

        # Prepare request to retry
        if h.service:
            logger.debug(f"Service: {h.service}")
            params["service"] = h.service
            headers.update(
                {
                    "Service": h.service,
                    "Accept": "application/json",
                    "User-Agent": "oras-py",
                }
            )

        # Ensure the realm starts with http
        if not h.realm.startswith("http"):  # type: ignore
            h.realm = f"{self.prefix}://{h.realm}"

        # If the www-authenticate included a scope, honor it!
        if h.scope:
            logger.debug(f"Scope: {h.scope}")
            params["scope"] = h.scope

        authResponse = self.session.get(h.realm, headers=headers, params=params)  # type: ignore
        if authResponse.status_code != 200:
            logger.debug(f"Auth response was not successful: {authResponse.text}")
            return False

        # Request the token
        info = authResponse.json()
        token = info.get("token") or info.get("access_token")

        # Set the token to the original request and retry
        self.headers.update({"Authorization": "Bearer %s" % token})
        return True

    def request_anonymous_token(self, h: oras.auth.authHeader) -> bool:
        """
        Given no basic auth, fall back to trying to request an anonymous token.

        Returns: boolean if headers have been updated with token.
        """
        if not h.realm:
            logger.debug("Request anonymous token: no realm provided, exiting early")
            return False

        params = {}
        if h.service:
            params["service"] = h.service
        if h.scope:
            params["scope"] = h.scope

        logger.debug(f"Final params are {params}")
        response = self.session.request("GET", h.realm, params=params)
        if response.status_code != 200:
            logger.debug(f"Response for anon token failed: {response.text}")
            return False

        # From https://docs.docker.com/registry/spec/auth/token/ section
        # We can get token OR access_token OR both (when both they are identical)
        data = response.json()
        token = data.get("token") or data.get("access_token")

        # Update the headers but not self.token (expects Basic)
        if token:
            self.headers.update({"Authorization": "Bearer %s" % token})
            return True
        logger.debug("Warning: no token or access_token present in response.")
        return False
