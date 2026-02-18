__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors"
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
default_index_media_type = "application/vnd.oci.image.index.v1+json"
docker_manifest_media_type = "application/vnd.docker.distribution.manifest.v2+json"
docker_manifest_list_media_type = (
    "application/vnd.docker.distribution.manifest.list.v2+json"
)

default_manifest_accepted_media_types = [
    default_manifest_media_type,
    default_index_media_type,
    docker_manifest_media_type,
    docker_manifest_list_media_type,
]

# AnnotationDigest is the annotation key for the digest of the uncompressed content
annotation_digest = "io.deis.oras.content.digest"

# AnnotationTitle is the annotation key for the human-readable title of the image.
annotation_title = "org.opencontainers.image.title"

# AnnotationUnpack is the annotation key for indication of unpacking
annotation_unpack = "io.deis.oras.content.unpack"

# OCIImageIndexFile is the file name of the index from the OCI Image Layout Specification
# Reference: https://github.com/opencontainers/image-spec/blob/master/image-layout.md#indexjson-file
oci_image_index_file = "index.json"

# OCI Image Layout constants
# Reference: https://github.com/opencontainers/image-spec/blob/master/image-layout.md
oci_blobs_dir = "blobs"
oci_layout_file = "oci-layout"
oci_layout_version_pin = "1.0.0"
oci_index_schema_version = 2
oci_ref_name_annotation = "org.opencontainers.image.ref.name"

# DefaultBlocksize default size of each slice of bytes read in each write through in gunzipand untar.
default_blocksize = 32768

# DefaultChunkSize default size of each chunk when uploading chunked blobs.
default_chunksize = 16777216  # 16MB

# what you get for a blank digest, so we don't need to save and recalculate
blank_hash = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# what you get for a blank config digest, so we don't need to save and recalculate
blank_config_hash = (
    "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
)
