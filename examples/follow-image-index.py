"""
Follow homebrew image index to get the 'hello' bottle specific to your platform
"""
import re

import oras.client
import oras.provider
from oras import decorator


class MyRegistry(oras.provider.Registry):
    """
    Oras registry with support for image indexes.
    """

    @decorator.ensure_container
    def get_image_index(self, container, allowed_media_type=None):
        """
        Get an image index as a manifest.

        This is basically Registry.get_manifest with the following changes

        - different default allowed_media_type
        - no JSON schema validation
        """
        if not allowed_media_type:
            default_image_index_media_type = "application/vnd.oci.image.index.v1+json"
            allowed_media_type = [default_image_index_media_type]

        headers = {"Accept": ";".join(allowed_media_type)}

        manifest_url = f"{self.prefix}://{container.manifest_url()}"
        response = self.do_request(manifest_url, "GET", headers=headers)
        self._check_200_response(response)
        manifest = response.json()
        # this would be a good point to validate the schema of the manifest
        # jsonschema.validate(manifest, schema=...)
        return manifest


def get_uri_for_digest(uri, digest):
    """
    Given a URI for an image, return a URI for the related digest.

    URI may be in any of the following forms:

        ghcr.io/homebrew/core/hello
        ghcr.io/homebrew/core/hello:2.10
        ghcr.io/homebrew/core/hello@sha256:ff81...47a
    """
    base_uri = re.split(r"[@:]", uri, maxsplit=1)[0]
    return f"{base_uri}@{digest}"


def get_image_for_platform(client, uri, download_to, platform_details):
    def matches_platform(manifest):
        platform = manifest.get("platform", {})
        return all(
            platform.get(key) == requested_value
            for key, requested_value in platform_details.items()
        )

    index_manifest = client.remote.get_image_index(container=uri)
    # use first compatible manifest. YMMV and a tie-breaker may be more suitable
    for manifest in index_manifest["manifests"]:
        if matches_platform(manifest):
            break
    else:
        raise RuntimeError(
            f"No manifest definition matched platform {platform_details}"
        )

    platform_image_uri = get_uri_for_digest(uri, manifest["digest"])
    client.pull(target=platform_image_uri, outdir=download_to)


if __name__ == "__main__":
    client = oras.client.OrasClient(registry=MyRegistry())
    platform_details = {
        "architecture": "amd64",
        "os": "darwin",
        "os.version": "macOS 10.14",
    }
    get_image_for_platform(
        client,
        "ghcr.io/homebrew/core/hello:2.10",
        download_to="downloads",
        platform_details=platform_details,
    )
