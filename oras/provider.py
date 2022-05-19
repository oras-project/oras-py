__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
__license__ = "Apache-2.0"

from oras.logger import logger
import oras.auth
import oras.oci
import oras.utils

from typing import Tuple
import copy
import os
import requests


class Registry:
    """
    Direct interactions with an OCI registry.

    This could also be called a "provider" when we add in the "copy" logic
    and the registry isn't necessarily the "remote" endpoint.
    """

    def __init__(self, hostname: str, insecure: bool = False):
        """
        Create a new registry provider.

        Arguments
        ---------
        hostname  : the registry hostname
        insecure  : use http instead of https
        """
        self.hostname = hostname
        self.headers = {}
        self.session = requests.Session()
        self.prefix = "http" if insecure else "https"
        self.token = None
        self._auths = None

    def logout(self, hostname: str):
        """
        If auths are loaded, remove a hostname.

        Arguments
        ---------
        hostname : the registry hostname to remove
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

    def load_configs(self, container: oras.container.Container, configs: list = None):
        """
        Load configs to discover credentials for a specific container.

        This is typically just called once. We always add the default Docker
        config to the set.s

        Arguments
        ---------
        container : the parsed container URI with components
        configs   : list of configs to read
        """
        if not self._auths:
            self._auths = oras.auth.load_configs(configs)
        for registry in oras.utils.iter_localhosts(container.registry):
            if self._load_auth(registry):
                return

    def _load_auth(self, hostname: str) -> bool:
        """
        Look for and load a named authentication token.

        Arguments
        ---------
        hostname : the registry hostname to look for
        """
        if hostname in self._auths:
            self.token = self._auths[hostname]["auth"]
            return True
        return False

    def set_basic_auth(self, username: str, password: str):
        """
        Set basic authentication.

        Arguments
        ---------
        username : the user account name
        password : the user account password
        """
        basic_auth = oras.auth.get_basic_auth(username, password)
        self.set_header("Authorization", "Basic %s" % basic_auth)

    def set_header(self, name: str, value: str):
        """
        Courtesy function to set a header

        Arguments
        ---------
        name : header name to set
        value : header value to set
        """
        self.headers.update({name: value})

    def _validate_path(self, path: str) -> bool:
        """
        Ensure a blob path is in the present working directory or below.

        Arguments
        ---------
        path : the path to validate
        """

        return os.getcwd() in os.path.abspath(path)

    def _parse_manifest_ref(self, ref: str) -> Tuple[str, str]:
        """
        Parse an optional manifest config, e.g:

        Examples
        --------
        <path>:<content-type>
        path/to/config:application/vnd.oci.image.config.v1+json
        /dev/null:application/vnd.oci.image.config.v1+json

        Arguments
        ---------
        ref : the manifest reference to parse (examples above)
        """
        if ":" not in ref:
            return ref, oras.defaults.unknown_config_media_type
        return ref.split(":", 1)

    def _upload_blob(
        self, blob: str, container: oras.container.Container, layer: dict
    ) -> requests.Response:
        """
        Prepare and upload a blob.

        Sizes > 1024 are uploaded via a chunked approach (post, patch+, put)
        and <= 1024 is a single post then put.

        Arguments
        ---------
        blob       : path to blob to upload
        container  : parsed container URI
        layer      : dict from oras.oci.NewLayer
        """
        blob = os.path.abspath(blob)
        size = layer["size"]

        # Chunked for large, otherwise POST and PUT
        if size < 1024:
            return self._put_upload(blob, container, layer)
        return self._chunked_upload(blob, container, layer)

    def _get_blob(
        self, container: oras.container.Container, digest: str, stream: bool = False
    ) -> requests.Response:
        """
        Retrieve a blob for a package.

        Arguments
        ---------
        container  : parsed container URI
        digest     : sha256 digest of the blob to retrieve
        stream     : stream the response (or not)
        """
        blob_url = f"{self.prefix}://{container.get_blob_url(digest)}"
        return self.do_request(blob_url, "GET", headers=self.headers, stream=stream)

    def _put_upload(
        self, blob: str, container: oras.container.Container, layer: dict
    ) -> requests.Response:
        """
        Upload to a registry via put.

        Arguments
        ---------
        blob       : path to blob to upload
        container  : parsed container URI
        layer      : dict from oras.oci.NewLayer
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

        Arguments
        ---------
        blob       : path to blob to upload
        container  : parsed container URI
        layer      : dict from oras.oci.NewLayer
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

        Arguments
        ---------
        response       : request response to inspect
        """
        if response.status_code not in [200, 201, 202]:
            logger.exit(f"Issue with {response.request.url}:\n{response.reason}")

    def _upload_manifest(
        self, manifest: dict, container: oras.container.Container
    ) -> requests.Response:
        """
        Read a manifest file and upload it.

        Arguments
        ---------
        manifest   : manifest to upload
        container  : parsed container URI
        """
        headers = {
            "Content-Type": oras.defaults.default_manifest_media_type,
            "Content-Length": str(len(manifest)),
        }
        put_url = f"{self.prefix}://{container.put_manifest_url()}"
        return self.do_request(put_url, "PUT", headers=headers, json=manifest)

    def push(self, *args, **kwargs):
        """
        Push a set of files to a target

        Arguments
        ---------
        config_path               (str) : path to a config file
        disable_path_validation  (bool) : ensure paths are relative to the running directory.
        files                    (list) : list of files to push
        insecure                 (bool) : allow registry to use http
        manifest_config           (str) : content type
        manifest_annotations      (str) : manifest annotations file
        username                  (str) : username for basic auth
        password                  (str) : password for basic auth
        target                    (str) : target location to push to
        """
        container = oras.container.Container(kwargs["target"], registry=self.hostname)
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

            # Create a new layer from the blob
            layer = oras.oci.NewLayer(blob)
            annotations = annotset.get_annotations(blob)
            layer["annotations"] = {
                oras.defaults.annotation_title: os.path.basename(blob)
            }
            if annotations:
                layer["annotations"].update(annotations)

            # update the manifest with the new layer
            manifest["layers"].append(layer)

            # Upload the blob layer
            response = self._upload_blob(blob, container, layer)
            self._check_200_response(response)

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

    def pull(self, *args, **kwargs):
        """
        Push an artifact from a target

        Arguments
        ---------
        config_path                 (str) : path to a config file
        allowed_media_type (list or None) : list of allowed media types
        overwrite                  (bool) : if output file exists, overwrite
        manifest_config_ref         (str) : save manifest config to this file
        outdir                      (str) : output directory path
        username                    (str) : username for basic auth
        password                    (str) : password for basic auth
        target                      (str) : target location to pull from
        """
        allowed_media_type = kwargs.get("allowed_media_type")
        container = oras.container.Container(kwargs["target"], self.hostname)
        self.load_configs(container, configs=kwargs.get("config_path"))
        manifest = self.get_manifest(container, allowed_media_type)
        outdir = kwargs.get("outdir") or oras.utils.get_tempdir()
        overwrite = kwargs.get("overwrite", True)

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
            with self._get_blob(container, layer["digest"], stream=True) as r:
                r.raise_for_status()
                with open(outfile, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info(f"Successfully pulled {outfile}.")

    def get_manifest(
        self, container: oras.container.Container, allowed_media_type: list = None
    ) -> dict:
        """
        Retrieve a manifest for a package.


        Arguments
        ---------
        container          : parsed container URI
        allowed_media_type : one or more allowed media types
        """
        if not allowed_media_type:
            allowed_media_type = [oras.defaults.default_manifest_media_type]
        headers = {"Accept": ";".join(allowed_media_type)}
        url = f"{self.prefix}://{container.get_manifest_url()}"
        response = self.do_request(url, "GET", headers=headers)
        self._check_200_response(response)
        return response.json()

    def do_request(
        self,
        url: str,
        method: str = "GET",
        data: dict = None,
        headers: dict = None,
        json: dict = None,
        stream: bool = False,
    ):
        """
        Do a request. This is a wrapper around requests to handle retry auth.

        Arguments
        ---------
        url     : the URL to issue the request to
        method  : the method to use (GET, DELETE, POST, PUT, PATCH)
        data    : data for requests
        headers : headers for the request
        json    : json data for requests
        stream : stream the responses
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

        Arguments
        ---------
        originalResponse : original response to get the Www-Authenticate header
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
        if not h.realm.startswith("http"):
            h.realm = f"{self.prefix}://{h.realm}"
        authResponse = self.session.get(h.realm, headers=headers)
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
