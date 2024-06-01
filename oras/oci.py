__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import copy
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import jsonschema

import oras.defaults
import oras.schemas
import oras.utils

EmptyManifest = {
    "schemaVersion": 2,
    "mediaType": oras.defaults.default_manifest_media_type,
    "config": {},
    "layers": [],
    "annotations": {},
}


class Annotations:
    """
    Create a new set of annotations
    """

    def __init__(self, filename=None):
        self.lookup = {}
        self.load(filename)

    def add(self, section, key, value):
        """
        Add key/value pairs to a named section.
        """
        if section not in self.lookup:
            self.lookup[section] = {}
        self.lookup[section][key] = value

    def load(self, filename: str):
        if filename and os.path.exists(filename):
            self.lookup = oras.utils.read_json(filename)
        if filename and not os.path.exists(filename):
            raise FileNotFoundError(f"Annotation file {filename} does not exist.")

    def get_annotations(self, section: str) -> dict:
        """
        Given the name (a relative path or named section) get annotations
        """
        for name in section, os.path.abspath(section):
            if name in self.lookup:
                return self.lookup[name]
        return {}


class Layer:
    def __init__(
        self, blob_path: str, media_type: Optional[str] = None, is_dir: bool = False
    ):
        """
        Create a new Layer

        :param blob_path: the path of the blob for the layer
        :type blob_path: str
        :param media_type: media type for the blob (optional)
        :type media_type: str
        :param is_dir: is the blob a directory?
        :type is_dir: bool
        """
        self.blob_path = blob_path
        self.set_media_type(media_type, is_dir)

    def set_media_type(self, media_type: Optional[str] = None, is_dir: bool = False):
        """
        Vary the media type to be directory or default layer

        :param media_type: media type for the blob (optional)
        :type media_type: str
        :param is_dir: is the blob a directory?
        :type is_dir: bool
        """
        self.media_type = media_type
        if is_dir and not media_type:
            self.media_type = oras.defaults.default_blob_dir_media_type
        elif not is_dir and not media_type:
            self.media_type = oras.defaults.default_blob_media_type

    def to_dict(self):
        """
        Return a dictionary representation of the layer
        """
        layer = {
            "mediaType": self.media_type,
            "size": oras.utils.get_size(self.blob_path),
            "digest": "sha256:" + oras.utils.get_file_hash(self.blob_path),
        }
        jsonschema.validate(layer, schema=oras.schemas.layer)
        return layer


def NewLayer(
    blob_path: str, media_type: Optional[str] = None, is_dir: bool = False
) -> dict:
    """
    Courtesy function to create and retrieve a layer as dict

    :param blob_path: the path of the blob for the layer
    :type blob_path: str
    :param media_type: media type for the blob (optional)
    :type media_type: str
    :param is_dir: is the blob a directory?
    :type is_dir: bool
    """
    return Layer(blob_path=blob_path, media_type=media_type, is_dir=is_dir).to_dict()


def ManifestConfig(
    path: Optional[str] = None, media_type: Optional[str] = None
) -> Tuple[Dict[str, object], Optional[str]]:
    """
    Write an empty config, if one is not provided

    :param path: the path of the manifest config, if exists.
    :type path: str
    :param media_type: media type for the manifest config (optional)
    :type media_type: str
    """
    # Create an empty config if we don't have one
    if not path or not os.path.exists(path):
        path = None
        conf = {
            "mediaType": media_type or oras.defaults.unknown_config_media_type,
            "size": 2,
            "digest": oras.defaults.blank_config_hash,
        }

    else:
        conf = {
            "mediaType": media_type or oras.defaults.unknown_config_media_type,
            "size": oras.utils.get_size(path),
            "digest": "sha256:" + oras.utils.get_file_hash(path),
        }

    jsonschema.validate(conf, schema=oras.schemas.layer)
    return conf, path


def NewManifest() -> dict:
    """
    Get an empty manifest config.
    """
    return copy.deepcopy(EmptyManifest)


@dataclass
class Subject:
    mediaType: str
    digest: str
    size: int

    @classmethod
    def from_manifest(cls, manifest: dict) -> "Subject":
        """
        Create a new Subject from a Manifest

        :param manifest: manifest to convert to subject
        """
        manifest_string = json.dumps(manifest).encode("utf-8")
        digest = "sha256:" + hashlib.sha256(manifest_string).hexdigest()
        size = len(manifest_string)

        return cls(
            manifest["mediaType"] or oras.defaults.default_manifest_media_type,
            digest,
            size,
        )
