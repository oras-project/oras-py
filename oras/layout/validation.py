__author__ = "Matteo Mortari"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import json
import pathlib

import oras.defaults
from oras.utils.fileio import read_json


def _validate_oci_layout_file(layout_dir: pathlib.Path) -> None:
    """
    Validate the oci-layout file in an OCI layout directory.

    :param layout_dir: path to the OCI layout directory
    :type layout_dir: pathlib.Path
    :raises FileNotFoundError: if oci-layout file doesn't exist
    :raises ValueError: if file content is invalid
    """
    layout_file = layout_dir / oras.defaults.oci_layout_file

    # > It MUST exist
    if not layout_file.exists():
        raise FileNotFoundError(
            f"Required file '{oras.defaults.oci_layout_file}' not found in {layout_dir}"
        )

    # Parse JSON
    try:
        layout_data = read_json(str(layout_file))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"File '{oras.defaults.oci_layout_file}' is not valid JSON: {e}"
        )

    # > It MUST be a JSON object
    if not isinstance(layout_data, dict):
        raise ValueError(
            f"File '{oras.defaults.oci_layout_file}' must contain a JSON object"
        )

    # > It MUST contain an imageLayoutVersion field
    if "imageLayoutVersion" not in layout_data:
        raise ValueError(
            f"File '{oras.defaults.oci_layout_file}' must contain 'imageLayoutVersion' property"
        )

    # > (...) version at the time changes to the layout are made, and will pin a given version until changes to the image layout are required.
    # At this time, that means pinning `1.0.0`.
    if (
        not isinstance(layout_data["imageLayoutVersion"], str)
        or not layout_data["imageLayoutVersion"] == oras.defaults.oci_layout_version_pin
    ):
        raise ValueError(
            f"imageLayoutVersion must be a string starting with '{oras.defaults.oci_layout_version_pin}', got: {layout_data['imageLayoutVersion']}"
        )


def _validate_index_json(layout_dir: pathlib.Path) -> None:
    """
    Validate the index.json file in an OCI layout directory.

    :param layout_dir: path to the OCI layout directory
    :type layout_dir: pathlib.Path
    :raises FileNotFoundError: if index.json doesn't exist
    :raises ValueError: if file content is invalid
    """
    index_file = layout_dir / oras.defaults.oci_image_index_file

    # > It MUST exist
    if not index_file.exists():
        raise FileNotFoundError(
            f"Required file '{oras.defaults.oci_image_index_file}' not found in {layout_dir}"
        )

    # Parse JSON
    try:
        index_data = read_json(str(index_file))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"File '{oras.defaults.oci_image_index_file}' is not valid JSON: {e}"
        )

    # > It MUST be an image index JSON object
    if not isinstance(index_data, dict):
        raise ValueError(
            f"File '{oras.defaults.oci_image_index_file}' must contain a JSON object"
        )
    # > REQUIRED property specifies the image manifest schema version
    if "schemaVersion" not in index_data:
        raise ValueError(
            f"File '{oras.defaults.oci_image_index_file}' must contain 'schemaVersion' property"
        )
    # > For this version of the specification, this MUST be 2
    if index_data["schemaVersion"] != oras.defaults.oci_index_schema_version:
        raise ValueError(
            f"schemaVersion must be {oras.defaults.oci_index_schema_version}, got: {index_data['schemaVersion']}"
        )

    # > SHOULD be used, and when used MUST be application/vnd.oci.image.index.v1+json
    if "mediaType" in index_data:
        if index_data["mediaType"] != oras.defaults.default_index_media_type:
            raise ValueError(
                f"mediaType must be '{oras.defaults.default_index_media_type}', got: {index_data['mediaType']}"
            )


def _validate_blobs_directory(layout_dir: pathlib.Path) -> None:
    """
    Validate the blobs directory in an OCI layout directory.

    :param layout_dir: path to the OCI layout directory
    :type layout_dir: pathlib.Path
    :raises FileNotFoundError: if blobs directory doesn't exist
    :raises ValueError: if blobs exists but is not a directory
    """
    blobs_dir = layout_dir / oras.defaults.oci_blobs_dir

    # > Directory MUST exist and MAY be empty
    if not blobs_dir.exists():
        raise FileNotFoundError(
            f"Required directory '{oras.defaults.oci_blobs_dir}' not found in {layout_dir}"
        )

    # Validate it's a directory (not a file)
    if not blobs_dir.is_dir():
        raise ValueError(
            f"'{oras.defaults.oci_blobs_dir}' must be a directory, not a file in {layout_dir}"
        )
