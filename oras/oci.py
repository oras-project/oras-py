__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
__license__ = "MIT"

import oras.defaults
import oras.utils
import copy
import os

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

    def load(self, filename):
        if filename and os.path.exists(filename):
            self.lookup = oras.utils.read_json(filename)

    def get_annotations(self, section):
        """
        Given the name (a relative path or named section) get annotations
        """
        for name in section, os.path.abspath(section):
            if name in self.lookup:
                return self.lookup[name]
        return {}


def NewLayer(blob, media_type=None):
    """
    Create a new Layer (todo, validate structure)
    """
    return {
        "mediaType": media_type or oras.defaults.default_blob_media_type,
        "size": oras.utils.get_size(blob),
        "digest": "sha256:" + oras.utils.get_file_hash(blob),
    }


def ManifestConfig(path=None, media_type=None):
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
    return conf, path


def NewManifest():
    """
    Get an empty manifest config.
    """
    return copy.deepcopy(EmptyManifest)
