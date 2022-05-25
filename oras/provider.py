__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import copy
import os
from typing import List, Optional, Tuple, Union

import jsonschema
import requests

import oras.auth
import oras.container
import oras.oci
import oras.schemas
import oras.utils
from oras.decorator import ensure_container
from oras.logger import logger


class Registry:
    """
    Direct interactions with an OCI registry.

    This could also be called a "provider" when we add in the "copy" logic
    and the registry isn't necessarily the "remote" endpoint.
    """

    def __init__(self, hostname: Optional[str] = None, insecure: bool = False):
        """
        Create a new registry provider.

        :param hostname: the registry hostname (optional)
        :type hostname: str
        :param insecure: use http instead of https
        :type insecure: bool
        """
        self.hostname: Optional[str] = hostname
        self.headers: dict = {}
        self.session: requests.Session = requests.Session()
        self.prefix: str = "http" if insecure else "https"
        self.token: Optional[str] = None
        self._auths: dict = {}

    def logout(self, hostname: str):
        """
        If auths are loaded, remove a hostname.

        :param hostname: the registry hostname to remove
        :type hostname: str
        """
        if not self._auths:
            logger.info(f"You are not logged in to {hostname}")
            return

        for host in oras.utils.iter_localhosts(hostname):
            if host in self._auths:
                del self._auths[host]
                logger.info(f"You have successfully logged out of {hostname}")
                return
        logger.info(f"You are not logged in to {hostname}")

    @ensure_container
    def load_configs(
        self,
        container: Union[str, oras.container.Container],
        configs: Optional[list] = None,
    ):
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
        if hostname in self._auths:
            self.token = self._auths[hostname]["auth"]
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
        basic_auth = oras.auth.get_basic_auth(username, password)
        self.set_header("Authorization", "Basic %s" % basic_auth)

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

    def _parse_manifest_ref(self, ref: str) -> Union[Tuple[str, str], List[str]]:
        """
        Parse an optional manifest config, e.g:

        Examples
        --------
        <path>:<content-type>
        path/to/config:application/vnd.oci.image.config.v1+json
        /dev/null:application/vnd.oci.image.config.v1+json

        :param ref: the manifest reference to parse (examples above)
        :type ref: str
        """
        if ":" not in ref:
            return ref, oras.defaults.unknown_config_media_type
        return ref.split(":", 1)

    def _upload_blob(
        self, blob: str, container: Union[str, oras.container.Container], layer: dict
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
        size = layer["size"]

        # Chunked for large, otherwise POST and PUT
        if size < 1024:
            return self._put_upload(blob, container, layer)
        return self._chunked_upload(blob, container, layer)

    @ensure_container
    def get_tags(
        self, container: Union[str, oras.container.Container], N: int = 10_000
    ) -> List[str]:
        """
        Retrieve tags for a package.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param N: number of tags
        :type N: int
        """
        tags_url = f"{self.prefix}://{container.tags_url(N)}"  # type: ignore
        return self.do_request(tags_url, "GET", headers=self.headers)

    @ensure_container
    def get_blob(
        self,
        container: Union[str, oras.container.Container],
        digest: str,
        stream: bool = False,
    ) -> requests.Response:
        """
        Retrieve a blob for a package.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        :param digest: sha256 digest of the blob to retrieve
        :type digest: str
        :param stream: stream the response (or not)
        :type stream: bool
        """
        blob_url = f"{self.prefix}://{container.get_blob_url(digest)}"  # type: ignore
        return self.do_request(blob_url, "GET", headers=self.headers, stream=stream)

    def get_container(
        self, name: Union[str, oras.container.Container]
    ) -> oras.container.Container:
        """
        Courtesy function to get a container from a URI.

        :param name: unique resource identifier to parse
        :type name: oras.container.Container or str
        """
        if isinstance(name, oras.container.Container):
            return name
        return oras.container.Container(name, registry=self.hostname)

    @ensure_container
    def _download_blob(
        self, container: Union[str, oras.container.Container], digest: str, outfile: str
    ) -> str:
        """
        Stream download a blob into an output file.

        This function is a wrapper around get_blob.

        :param container:  parsed container URI
        :type container: oras.container.Container or str
        """
        with self.get_blob(container, digest, stream=True) as r:
            r.raise_for_status()
            with open(outfile, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return outfile

    def _put_upload(
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
        session_url = r.headers.get("location")

        # PUT to upload blob url
        headers = {
            "Content-Length": str(layer["size"]),
            "Content-Type": "application/octet-stream",
        }

        # headers.update(auth_headers)
        digest = layer["digest"]
        blob_url = f"{session_url}&digest={digest}"
        with open(blob, "rb") as fd:
            response = self.do_request(
                blob_url, method="PUT", data=fd.read(), headers=headers
            )
        return response

    def _chunked_upload(
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
        headers = {"Content-Type": "application/octet-stream", "Content-Length": 0}
        upload_url = f"{self.prefix}://{container.upload_blob_url()}"
        r = self.do_request(upload_url, "POST", headers=headers)

        # Location should be in the header
        session_url = r.headers.get("location")

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
                # headers.update(auth_headers)
                start = end + 1
                self._check_200_response(
                    self.do_request(session_url, "PATCH", data=chunk, headers=headers)
                )

        # Finally, issue a PUT request to close blob
        session_url = "%s&digest=%s" % (session_url, layer["digest"])
        return self.do_request(session_url, "PUT")

    def _check_200_response(self, response: requests.Response):
        """
        Helper function to ensure some flavor of 200

        :param response: request response to inspect
        :type response: requests.Response
        """
        if response.status_code not in [200, 201, 202]:
            self._parse_response_errors(response)
            logger.exit(f"Issue with {response.request.url}:\n{response.reason}")

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
        except:
            pass

    def _upload_manifest(
        self, manifest: dict, container: oras.container.Container
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
            "Content-Length": str(len(manifest)),
        }
        put_url = f"{self.prefix}://{container.put_manifest_url()}"
        return self.do_request(put_url, "PUT", headers=headers, json=manifest)

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
        :param manifest_config: content type
        :type manifest_config: str
        :param manifest_annotations: manifest annotations file
        :type manifest_annotations: str
        :param username: username for basic auth
        :type username: str
        :param password: password for basic auth
        :type password: str
        :param target: target location to push to
        :type target: str
        """
        container = self.get_container(kwargs["target"])
        self.load_configs(container, configs=kwargs.get("config_path"))

        # Hold state of request for http/https
        validate_path = not kwargs.get("disable_path_validation", False)

        # Prepare a new manifest
        manifest = oras.oci.NewManifest()

        # A lookup of annotations we can add
        annotset = oras.oci.Annotations(kwargs.get("manifest_annotations"))

        # Upload files as blobs
        for blob in kwargs.get("files", []):

            # Must exist
            if not os.path.exists(blob):
                logger.exit(f"{blob} does not exist.")

            # Path validation means blob must be relative to PWD.
            if validate_path:
                if not self._validate_path(blob):
                    logger.exit(
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
            layer = oras.oci.NewLayer(blob, is_dir=cleanup_blob)
            annotations = annotset.get_annotations(blob)
            layer["annotations"] = {oras.defaults.annotation_title: blob_name}
            if annotations:
                layer["annotations"].update(annotations)

            # update the manifest with the new layer
            manifest["layers"].append(layer)

            # Upload the blob layer
            response = self._upload_blob(blob, container, layer)
            self._check_200_response(response)

            # Do we need to cleanup a temporary targz?
            if cleanup_blob and os.path.exists(blob):
                os.remove(blob)

        # Add annotations to the manifest, if provided
        manifest_annots = annotset.get_annotations("$manifest")
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
        response = self._upload_blob(config_file, container, conf)
        self._check_200_response(response)

        # Final upload of the manifest
        manifest["config"] = conf
        self._check_200_response(self._upload_manifest(manifest, container))
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
        :param manifest_config_ref: sav manifest config to this file
        :type manifest_config_ref: str
        :param outdir: output directory path
        :type outdir: str
        :param username: username for basic auth
        :type username: str
        :param password: password for basic auth
        :type password: str
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
            filename = layer.get("annotations", {}).get(oras.defaults.annotation_title)

            # If we don't have a filename, default to digest. Hopefully does not happen
            if not filename:
                filename = layer["digest"]
            outfile = os.path.join(outdir, filename)
            if not overwrite and os.path.exists(outfile):
                logger.warning(
                    f"{outfile} already exists and --keep-old-files set, will not overwrite."
                )
                continue

            # A directory will need to be uncompressed and moved
            if layer["mediaType"] == oras.defaults.default_blob_dir_media_type:
                targz = oras.utils.get_tmpfile(suffix=".tar.gz")
                self._download_blob(container, layer["digest"], targz)

                # The artifact will be extracted to the correct name
                oras.utils.extract_targz(targz, os.path.dirname(outfile))

            # Anything else just extracted directly
            else:
                self._download_blob(container, layer["digest"], outfile)
            logger.info(f"Successfully pulled {outfile}.")
            files.append(outfile)
        return files

    @ensure_container
    def get_manifest(
        self,
        container: Union[str, oras.container.Container],
        allowed_media_type: list = None,
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
        url = f"{self.prefix}://{container.get_manifest_url()}"  # type: ignore
        response = self.do_request(url, "GET", headers=headers)
        self._check_200_response(response)
        manifest = response.json()
        jsonschema.validate(manifest, schema=oras.schemas.manifest)
        return manifest

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
            method, url, data=data, json=json, headers=headers, stream=stream
        )

        # A 401 response is a request for authentication
        if response.status_code != 401:
            return response

        # Otherwise, authenticate the request and retry
        if self.authenticate_request(response):
            headers.update(self.headers)
            return self.session.request(
                method, url, data=data, json=json, headers=headers, stream=stream
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
            return False

        # If we have a token, set auth header (base64 encoded user/pass)
        if self.token:
            self.set_header("Authorization", "Basic %s" % self.token)

        headers = copy.deepcopy(self.headers)
        if "Authorization" not in headers:
            logger.error(
                "This endpoint requires a token. Please set "
                "oras.provider.Registry.set_basic_auth(username, password) "
                "first or use oras-py login to do the same."
            )
            return False

        # Prepare request to retry
        h = oras.auth.parse_auth_header(authHeaderRaw)
        if h.service:
            headers.update(
                {
                    "Service": h.service,
                    "Accept": "application/json",
                    "User-Agent": "oras-py",
                }
            )

        # Currently we don't set a scope (it defaults to build)
        if not h.realm.startswith("http"):  # type: ignore
            h.realm = f"{self.prefix}://{h.realm}"
        authResponse = self.session.get(h.realm, headers=headers)  # type: ignore
        if authResponse.status_code != 200:
            return False

        # Request the token
        info = authResponse.json()
        token = info.get("token")
        if not token:
            token = info.get("access_token")

        # Set the token to the original request and retry
        self.headers.update({"Authorization": "Bearer %s" % token})
        return True
