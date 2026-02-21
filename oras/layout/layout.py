from __future__ import annotations

__author__ = "Matteo Mortari"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import json
import pathlib
from typing import TYPE_CHECKING

import jsonschema
import requests

import oras.defaults
import oras.schemas
from oras.layout.validation import (
    _validate_blobs_directory,
    _validate_index_json,
    _validate_oci_layout_file,
)
from oras.logger import logger
from oras.utils.fileio import read_json, write_json

if TYPE_CHECKING:
    from oras.provider import Registry


def NewLayout(path: str, validate: bool = True) -> Layout:
    """
    Courtesy function to create a Layout from a path on disk.

    :param path: path to Layout directory
    :type path: str
    :param validate: whether to validate the Layout structure (default: True)
    :type validate: bool
    :return: Layout instance for the Layout directory
    :rtype: Layout
    :raises FileNotFoundError: if path does not exists, or validation fails (when validate=True)
    :raises ValueError: if path is not a directory, or validation fails (when validate=True)
    """
    return Layout(path=path, validate=validate)


def NewLayoutFromRegistry(
    path: str,
    provider: Registry,
    target: str,
    tag: str = "latest",
) -> Layout:
    """
    Create a new OCI Layout on disk by pulling from a remote registry.

    The path must either not exist or be an empty directory.

    :param path: path to create the Layout directory
    :type path: str
    :param provider: Registry provider instance for downloading
    :type provider: oras.provider.Registry
    :param target: source registry/repository with tag or digest
        (e.g., "ghcr.io/user/repo:v1.0" or "ghcr.io/user/repo@sha256:abc123...")
    :type target: str
    :param tag: tag to write in the layout's index.json annotation (default: "latest")
    :type tag: str
    :return: Layout instance for the pulled Layout directory
    :rtype: Layout
    :raises FileExistsError: if path exists and is not an empty directory
    :raises ValueError: if path exists but is not a directory
    """
    p = pathlib.Path(path)
    if p.exists():
        if not p.is_dir():
            raise ValueError(f"Path exists and is not a directory: {path}")
        if any(p.iterdir()):
            raise FileExistsError(f"Directory is not empty: {path}")
    else:
        p.mkdir(parents=True)

    layout = Layout(path=path, validate=False)
    layout.pull_from_registry(provider=provider, target=target, tag=tag)
    return layout


class Layout:
    _oci_layout_path: str

    def __init__(self, path: str, validate: bool = True):
        self._oci_layout_path = path
        if validate:
            self.validate()

    def validate(self):
        """
        Validate that this is a valid OCI layout directory.

        Checks that the directory contains valid 'oci-layout' and 'index.json' files,
        and a 'blobs' directory according to the OCI Image Layout Specification.

        :return: absolute path to the validated OCI layout directory
        :rtype: str
        :raises FileNotFoundError: if path or required files/directories don't exist
        :raises ValueError: if path is not a directory or validation fails
        """
        # Normalize path
        layout_path = pathlib.Path(self._oci_layout_path).expanduser().resolve()

        # Validate path exists
        if not layout_path.exists():
            raise FileNotFoundError(f"Path does not exist: {self._oci_layout_path}")

        # Validate path is a directory
        if not layout_path.is_dir():
            raise ValueError(f"Path is not a directory: {self._oci_layout_path}")

        # > The image layout is as follows:
        # > blobs directory
        _validate_blobs_directory(layout_path)

        # > oci-layout file
        _validate_oci_layout_file(layout_path)

        # > index.json file
        _validate_index_json(layout_path)

        # Return absolute path
        return str(layout_path)

    @staticmethod
    def is_oci_layout(path: str) -> bool:
        """
        Check if a path is a valid OCI layout directory.

        :param path: path to check
        :type path: str
        :return: True if path is a valid OCI layout, False otherwise
        :rtype: bool
        """
        try:
            Layout(path)
            return True
        except (FileNotFoundError, ValueError, OSError):
            return False

    def get_ordered_blobs(self, tag: str = "latest") -> list[str]:
        """
        Traverse an OCI layout and collect blob digests in dependency order for pushing.

        Returns digests with algorithm prefix (e.g., "sha256:...") in the order:
        - Layer blobs (layer0 to layerN)
        - Config blob
        - Manifest blob(s)
        - Index blob (if multi-arch or anyway Index collection of Image manifests)

        :param tag: tag to look up in annotations (default: "latest")
        :type tag: str
        :return: list of digest strings including algorithm prefix
        :rtype: list[str]
        :raises FileNotFoundError: if layout, index, or blob files don't exist
        :raises ValueError: if tag annotation not found or invalid structure
        """
        index_file = (
            pathlib.Path(self._oci_layout_path) / oras.defaults.oci_image_index_file
        )
        index_data = read_json(str(index_file))

        # Find the manifest with matching tag annotation (usually `:latest` for oci-layout on disk)
        target_digest = None
        for manifest_entry in index_data.get("manifests", []):
            annotations = manifest_entry.get("annotations", {})
            if annotations.get(oras.defaults.oci_ref_name_annotation) == tag:
                target_digest = manifest_entry["digest"]
                break

        if not target_digest:
            raise ValueError(f"Tag '{tag}' not found in index")

        # Collect blobs in dependency order
        collected = []
        Layout._process_manifest(
            pathlib.Path(self._oci_layout_path), target_digest, collected
        )
        return collected

    @staticmethod
    def _process_manifest(
        layout_dir: pathlib.Path, digest: str, collected: list[str]
    ) -> None:
        """
        Recursively process a manifest blob and collect dependencies.

        :param layout_dir: path to OCI layout directory
        :type layout_dir: pathlib.Path
        :param digest: digest of manifest to process (with algorithm prefix)
        :type digest: str
        :param collected: list to accumulate digests (mutated in place)
        :type collected: list[str]
        :raises FileNotFoundError: if blob file doesn't exist
        :raises ValueError: if manifest structure is invalid
        """
        # Construct blob path: blobs/sha256/abc123...
        algorithm, hash_value = digest.split(":", 1)
        blob_path = layout_dir / oras.defaults.oci_blobs_dir / algorithm / hash_value

        if not blob_path.exists():
            raise FileNotFoundError(f"Blob not found: {blob_path}")

        # Read manifest blob
        manifest = read_json(str(blob_path))
        media_type = manifest.get("mediaType", "")

        if media_type == oras.defaults.default_manifest_media_type:
            # Image manifest: layers -> config -> manifest
            for layer in manifest.get("layers", []):
                if layer["digest"] not in collected:
                    collected.append(layer["digest"])

            config_digest = manifest.get("config", {}).get("digest")
            if config_digest and config_digest not in collected:
                collected.append(config_digest)

            if digest not in collected:
                collected.append(digest)

        elif media_type == oras.defaults.default_index_media_type:
            # Image index: recurse on sub-manifests, then add index itself
            for sub_manifest in manifest.get("manifests", []):
                Layout._process_manifest(layout_dir, sub_manifest["digest"], collected)

            if digest not in collected:
                collected.append(digest)

        else:
            raise ValueError(
                f"Unsupported manifest mediaType: {media_type}. "
                f"Expected '{oras.defaults.default_manifest_media_type}' or '{oras.defaults.default_index_media_type}'"
            )

    @staticmethod
    def _digest_to_blob_path(layout_dir: pathlib.Path, digest: str) -> pathlib.Path:
        """
        Convert digest string (usually `sha256:abc123`) to blob file path in OCI layout.

        :param layout_dir: path to OCI layout directory
        :type layout_dir: pathlib.Path
        :param digest: digest with algorithm prefix (e.g., "sha256:abc123...")
        :type digest: str
        :return: path to blob file (e.g., layout_dir/blobs/sha256/abc123...)
        :rtype: pathlib.Path
        """
        algorithm, hash_value = digest.split(":", 1)
        return layout_dir / oras.defaults.oci_blobs_dir / algorithm / hash_value

    @staticmethod
    def _blob_exists(layout_dir: pathlib.Path, digest: str) -> bool:
        """
        Check if a blob already exists in the OCI layout on disk.

        :param layout_dir: path to OCI layout directory
        :type layout_dir: pathlib.Path
        :param digest: digest with algorithm prefix (e.g., "sha256:abc123...")
        :type digest: str
        :return: True if blob file exists on disk
        :rtype: bool
        """
        return Layout._digest_to_blob_path(layout_dir, digest).exists()

    @staticmethod
    def _create_layer_dict(
        blob_path: pathlib.Path, digest: str, media_type: str
    ) -> dict:
        """
        Create a layer dict for upload_blob from blob file.

        :param blob_path: path to blob file
        :type blob_path: pathlib.Path
        :param digest: digest with algorithm prefix
        :type digest: str
        :param media_type: media type for the blob
        :type media_type: str
        :return: layer dict with digest, size, mediaType
        :rtype: dict
        """
        size = blob_path.stat().st_size
        return {
            "digest": digest,
            "size": size,
            "mediaType": media_type or oras.defaults.unknown_config_media_type,
        }

    @staticmethod
    def _pull_manifest_blobs(
        provider: Registry,
        container,
        manifest_data: dict,
        manifest_digest: str,
        manifest_bytes: bytes,
        layout_dir: pathlib.Path,
    ) -> None:
        """
        Download all blobs referenced by an Image Manifest and store them in the OCI layout.

        Downloads layer blobs and config blob via the registry blob endpoint,
        then stores the manifest itself from its already-fetched raw bytes.
        Skips blobs that already exist on disk (deduplication).

        :param provider: Registry provider instance for downloading
        :type provider: oras.provider.Registry
        :param container: parsed container URI
        :type container: oras.container.Container
        :param manifest_data: parsed manifest JSON
        :type manifest_data: dict
        :param manifest_digest: digest of the manifest (with algorithm prefix)
        :type manifest_digest: str
        :param manifest_bytes: raw bytes of the manifest
        :type manifest_bytes: bytes
        :param layout_dir: path to OCI layout directory
        :type layout_dir: pathlib.Path
        """
        # layer blobs
        for layer in manifest_data.get("layers", []):
            layer_digest = layer["digest"]
            if not Layout._blob_exists(layout_dir, layer_digest):
                provider.download_blob(
                    container,
                    layer_digest,
                    str(Layout._digest_to_blob_path(layout_dir, layer_digest)),
                )
                logger.debug(f"Downloaded layer blob: {layer_digest}")

        # config blob
        config_digest = manifest_data.get("config", {}).get("digest")
        if config_digest and not Layout._blob_exists(layout_dir, config_digest):
            provider.download_blob(
                container,
                config_digest,
                str(Layout._digest_to_blob_path(layout_dir, config_digest)),
            )
            logger.debug(f"Downloaded config blob: {config_digest}")

        # manifest blob (raw bytes coming from manifest endpoint fetch)
        if not Layout._blob_exists(layout_dir, manifest_digest):
            blob_path = Layout._digest_to_blob_path(layout_dir, manifest_digest)
            blob_path.parent.mkdir(parents=True, exist_ok=True)  # ensures blobs/<algo>/
            blob_path.write_bytes(manifest_bytes)
            logger.debug(f"Stored manifest blob: {manifest_digest}")

    @staticmethod
    def _pull_index_blobs(
        provider: Registry,
        container,
        index_data: dict,
        index_digest: str,
        index_bytes: bytes,
        layout_dir: pathlib.Path,
    ) -> None:
        """
        Download all content referenced by an Image Index and store in the OCI layout.

        Iterates sub-manifests, fetches each by digest from the registry,
        and recursively processes them. Handles nested indexes.
        Skips blobs that already exist on disk (deduplication).

        :param provider: Registry provider instance for downloading
        :type provider: oras.provider.Registry
        :param container: parsed container URI
        :type container: oras.container.Container
        :param index_data: parsed index JSON
        :type index_data: dict
        :param index_digest: digest of the index (with algorithm prefix)
        :type index_digest: str
        :param index_bytes: raw bytes of the index
        :type index_bytes: bytes
        :param layout_dir: path to OCI layout directory
        :type layout_dir: pathlib.Path
        :raises ValueError: if a sub-manifest has an unsupported mediaType
        """
        for sub_manifest_ref in index_data.get("manifests", []):
            sub_digest = sub_manifest_ref["digest"]
            if Layout._blob_exists(layout_dir, sub_digest):
                continue

            logger.debug(f"Fetching sub-manifest: {sub_digest}")
            sub_media_type = sub_manifest_ref.get(
                "mediaType", oras.defaults.default_manifest_media_type
            )
            headers = {"Accept": sub_media_type}
            sub_url = f"{provider.prefix}://{container.registry}/v2/{container.api_prefix}/manifests/{sub_digest}"
            response = provider.do_request(sub_url, "GET", headers=headers)
            provider._check_200_response(response)

            sub_bytes = response.content
            sub_data = json.loads(sub_bytes)
            # the Index might have defaulted, so we overwrite with the actual content response
            sub_media_type = sub_data.get("mediaType", "")

            if sub_media_type == oras.defaults.default_manifest_media_type:
                Layout._pull_manifest_blobs(
                    provider,
                    container,
                    sub_data,
                    sub_digest,
                    sub_bytes,
                    layout_dir,
                )
            elif sub_media_type == oras.defaults.default_index_media_type:
                # nested index; rare but valid: https://github.com/opencontainers/image-spec/blob/6529f89e290d8169adbddf15e43493b9fdd37b62/image-index.md?plain=1#L40-L46
                Layout._pull_index_blobs(
                    provider,
                    container,
                    sub_data,
                    sub_digest,
                    sub_bytes,
                    layout_dir,
                )
            else:
                raise ValueError(
                    f"Unsupported manifest mediaType in index: {sub_media_type}. "
                    f"Expected '{oras.defaults.default_manifest_media_type}' or '{oras.defaults.default_index_media_type}'"
                )

        # store the index blob itself
        if not Layout._blob_exists(layout_dir, index_digest):
            blob_path = Layout._digest_to_blob_path(layout_dir, index_digest)
            blob_path.parent.mkdir(parents=True, exist_ok=True)  # ensures blobs/<algo>/
            blob_path.write_bytes(index_bytes)
            logger.debug(f"Stored index blob: {index_digest}")

    def push_to_registry(
        self,
        provider: Registry,
        target: str,
        tag: str = "latest",
        do_chunked: bool = False,
        chunk_size: int = oras.defaults.default_chunksize,
    ) -> requests.Response:
        """
        Push an OCI layout to a remote registry.

        :param provider: Registry provider instance for uploading
        :type provider: oras.provider.Registry
        :param target: target registry/repository with destination tag (e.g., "ghcr.io/user/repo:v1.0")
        :type target: str
        :param tag: source tag to read from the layout's index.json annotations (default: "latest")
        :type tag: str
        :param do_chunked: use chunked upload for large blobs
        :type do_chunked: bool
        :param chunk_size: chunk size for chunked uploads
        :type chunk_size: int
        :return: response from the final manifest upload
        :rtype: requests.Response
        :raises FileNotFoundError: if layout or blobs don't exist
        :raises ValueError: if layout is invalid or tag not found
        """
        if ":" not in target or target.endswith(":"):
            raise ValueError(
                f"Target must include a tag in format 'registry/repository:tag', got: {target}"
            )

        container = provider.get_container(target)
        ordered_blobs = self.get_ordered_blobs(tag)
        logger.debug(f"Pushing {len(ordered_blobs)} blobs from OCI layout to {target}")

        # Upload blobs in dependency order
        last_response = None
        for i, digest in enumerate(ordered_blobs):
            blob_path = Layout._digest_to_blob_path(
                pathlib.Path(self._oci_layout_path), digest
            )

            # Verify blob exists (we don't have this check by spec in validation_oci_layout)
            if not blob_path.exists():
                raise FileNotFoundError(f"Blob not found: {blob_path}")

            # Last blob will need to be tagged on Push/upload/PUT
            is_last_blob = i == len(ordered_blobs) - 1
            try:
                # Read raw bytes first to avoid reading file twice later below,
                # to ensure consistency with digest, upload will be performed not using blob_data.
                with open(blob_path, "rb") as f:
                    manifest_bytes = f.read()
                blob_data = json.loads(manifest_bytes)
                media_type = blob_data.get("mediaType", "")

                # Check if it's a Image manifest or Index
                if media_type in [
                    oras.defaults.default_manifest_media_type,
                    oras.defaults.default_index_media_type,
                ]:
                    if media_type == oras.defaults.default_manifest_media_type:
                        jsonschema.validate(blob_data, schema=oras.schemas.manifest)
                    else:
                        jsonschema.validate(blob_data, schema=oras.schemas.index)

                    # Use manifest's mediaType for Content-Type header as required.
                    content_type = blob_data.get(
                        "mediaType", oras.defaults.default_manifest_media_type
                    )
                    headers = {"Content-Type": content_type}

                    if is_last_blob:
                        # Final manifest/index - upload with tag
                        logger.debug(f"Uploading manifest/index with tag: {digest}")
                        url = f"{provider.prefix}://{container.manifest_url()}"
                        response = provider.do_request(
                            url, "PUT", headers=headers, data=manifest_bytes
                        )
                    else:
                        # Intermediate manifest - upload by digest only (no tag yet)
                        logger.debug(
                            f"Uploading intermediate manifest by digest: {digest}"
                        )
                        url = f"{provider.prefix}://{container.registry}/v2/{container.api_prefix}/manifests/{digest}"
                        response = provider.do_request(
                            url, "PUT", headers=headers, data=manifest_bytes
                        )
                else:
                    # It's JSON but not a Image/Index Manifest, upload as blob with layer dict
                    log_media_type_str = (
                        f" with mediaType {media_type}" if media_type else ""
                    )
                    logger.debug(f"Uploading blob{log_media_type_str}: {digest}")
                    layer = Layout._create_layer_dict(blob_path, digest, media_type)
                    response = provider.upload_blob(
                        str(blob_path), container, layer, do_chunked, chunk_size
                    )
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Not JSON - upload a binary layer blob
                logger.debug(f"Uploading layer blob: {digest}")
                layer = Layout._create_layer_dict(
                    blob_path, digest, oras.defaults.default_blob_media_type
                )
                response = provider.upload_blob(
                    str(blob_path), container, layer, do_chunked, chunk_size
                )

            # Check response status per ORAS-py conventions
            provider._check_200_response(response)
            last_response = response

        logger.debug(f"Successfully pushed {len(ordered_blobs)} blobs to {target}")
        return last_response

    def pull_from_registry(
        self,
        provider: Registry,
        target: str,
        tag: str = "latest",
    ) -> None:
        """
        Pull an OCI artifact from a remote registry into this OCI layout directory,
        overwriting the oci-layout index file.

        Creates a valid OCI Layout on disk at this oci-layout's path,
        downloading all referenced blobs (layers, configs, manifests).
        Handles both single Image Manifests and Indexes.

        :param provider: Registry provider instance for downloading
        :type provider: oras.provider.Registry
        :param target: source registry/repository with tag or digest
            (e.g., "ghcr.io/user/repo:v1.0" or "ghcr.io/user/repo@sha256:abc123...")
        :type target: str
        :param tag: tag to write in the layout's index.json annotation (default: "latest")
        :type tag: str
        :raises ValueError: if target is invalid or manifest has unsupported mediaType
        """
        container = provider.get_container(target)
        layout_dir = pathlib.Path(self._oci_layout_path)

        # prepare directory structure for blobs
        blobs_dir = layout_dir / oras.defaults.oci_blobs_dir / "sha256"
        blobs_dir.mkdir(parents=True, exist_ok=True)

        headers = {
            "Accept": ", ".join(oras.defaults.default_manifest_accepted_media_types)
        }
        manifest_url = f"{provider.prefix}://{container.manifest_url()}"
        response = provider.do_request(manifest_url, "GET", headers=headers)
        provider._check_200_response(response)

        manifest_bytes = response.content
        manifest_digest = response.headers.get(
            "Docker-Content-Digest", container.digest
        )
        if not manifest_digest:
            raise RuntimeError(
                "Expected to find Docker-Content-Digest header in manifest response."
            )
        manifest_data = json.loads(manifest_bytes)
        media_type = manifest_data.get("mediaType", "")

        logger.debug(
            f"Pulling {target} (mediaType={media_type}, digest={manifest_digest}) to OCI layout"
        )
        if media_type == oras.defaults.default_manifest_media_type:
            Layout._pull_manifest_blobs(
                provider,
                container,
                manifest_data,
                manifest_digest,
                manifest_bytes,
                layout_dir,
            )
        elif media_type == oras.defaults.default_index_media_type:
            Layout._pull_index_blobs(
                provider,
                container,
                manifest_data,
                manifest_digest,
                manifest_bytes,
                layout_dir,
            )
        else:
            raise ValueError(
                f"Unsupported manifest mediaType: {media_type}. "
                f"Expected '{oras.defaults.default_manifest_media_type}' or '{oras.defaults.default_index_media_type}'"
            )

        # oci-layout file
        oci_layout_content = {
            "imageLayoutVersion": oras.defaults.oci_layout_version_pin
        }
        write_json(oci_layout_content, str(layout_dir / oras.defaults.oci_layout_file))

        # index.json
        index_entry = {
            "mediaType": media_type,
            "digest": manifest_digest,
            "size": len(manifest_bytes),
            "annotations": {oras.defaults.oci_ref_name_annotation: tag},
        }
        index_content = {
            "schemaVersion": oras.defaults.oci_index_schema_version,
            "manifests": [index_entry],
        }
        jsonschema.validate(index_content, schema=oras.schemas.index)
        write_json(index_content, str(layout_dir / oras.defaults.oci_image_index_file))

        logger.debug(
            f"Successfully pulled {target} to OCI layout at {self._oci_layout_path}"
        )
