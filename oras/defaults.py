__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
__license__ = "Apache-2.0"


# Default tag to use
default_tag = "latest"


# https://github.com/moby/moby/blob/master/registry/config.go#L29
class registry:
    index_hostname = "index.docker.io"
    index_server = "https://index.docker.io/v1/"
    index_name = "docker.io"
    default_v2_registry = {"scheme": "https", "host": "registry-1.docker.io"}


# DefaultBlobDirMediaType specifies the default blob directory media type
default_blob_dir_media_type = "application/vnd.oci.image.layer.v1.tar+gzip"

# MediaTypeImageLayer is the media type used for layers referenced by the manifest.
default_blob_media_type = "application/vnd.oci.image.layer.v1.tar"
unknown_config_media_type = "application/vnd.unknown.config.v1+json"
default_manifest_media_type = "application/vnd.oci.image.manifest.v1+json"

# AnnotationDigest is the annotation key for the digest of the uncompressed content
annotation_digest = "io.deis.oras.content.digest"

# AnnotationTitle is the annotation key for the human-readable title of the image.
annotation_title = "org.opencontainers.image.title"

# AnnotationUnpack is the annotation key for indication of unpacking
annotation_unpack = "io.deis.oras.content.unpack"

# OCIImageIndexFile is the file name of the index from the OCI Image Layout Specification
# Reference: https://github.com/opencontainers/image-spec/blob/master/image-layout.md#indexjson-file
oci_image_index_file = "index.json"

# DefaultBlocksize default size of each slice of bytes read in each write through in gunzipand untar.
default_blocksize = 32768

# what you get for a blank digest, so we don't need to save and recalculate
blank_hash = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
