__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import copy
import os
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

    def load(self, filename: str):
        if filename and os.path.exists(filename):
            self.lookup = oras.utils.read_json(filename)

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
        self, blob: str, media_type: Optional[str] = None, is_dir: bool = False
    ):
        """
        Create a new Layer
        """
        self.blob = blob
        self.set_media_type(media_type, is_dir)

    def set_media_type(self, media_type: Optional[str] = None, is_dir: bool = False):
        """
        Vary the media type to be directory or default layer
        """
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
            "size": oras.utils.get_size(self.blob),
            "digest": "sha256:" + oras.utils.get_file_hash(self.blob),
        }
        jsonschema.validate(layer, schema=oras.schemas.layer)
        return layer


def NewLayer(blob: str, media_type: Optional[str] = None, is_dir: bool = False) -> dict:
    """
    Courtesy function to create and retrieve a layer as dict
    """
    return Layer(blob=blob, media_type=media_type, is_dir=is_dir).to_dict()


def ManifestConfig(
    path: str = None, media_type: str = None
) -> Tuple[Dict[str, object], str]:
    """
    Write an empty config, if one is not provided
    """
    # Create an empty config if we don't have one
    if not path or not os.path.exists(path):
        path = "/dev/null"
        conf = {
            "mediaType": media_type or oras.defaults.unknown_config_media_type,
            "size": 0,
            "digest": oras.defaults.blank_hash,
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
