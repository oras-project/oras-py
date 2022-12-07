__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

## Manifest and Layer schemas

schema_url = "http://json-schema.org/draft-07/schema"

# Layer

layerProperties = {
    "type": "object",
    "properties": {
        "mediaType": {"type": "string"},
        "size": {"type": "number"},
        "digest": {"type": "string"},
        "annotations": {"type": ["object", "null", "array"]},
    },
}

layer = {
    "$schema": schema_url,
    "title": "Layer Schema",
    "required": [
        "mediaType",
        "size",
        "digest",
    ],
    "additionalProperties": False,
}

layer.update(layerProperties)


# Manifest

manifestProperties = {
    "schemaVersion": {"type": "number"},
    "subject": {"type": ["null", "string"]},
    "mediaType": {"type": "string"},
    "layers": {"type": "array", "items": layerProperties},
    "config": layerProperties,
    "annotations": {"type": ["object", "null", "array"]},
}


manifest = {
    "$schema": schema_url,
    "title": "Manifest Schema",
    "type": "object",
    "required": [
        "schemaVersion",
        "config",
        "layers",
    ],
    "properties": manifestProperties,
    "additionalProperties": False,
}
