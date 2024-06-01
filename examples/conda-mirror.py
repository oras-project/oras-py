# This is an example of a custom client described in:
# https://github.com/oras-project/oras-py/issues/11 that wants to use oras
# to upload multiple different objects in different layers of a manifest,
# and then have a custom filter for those layers.

import io
import json
import os
import sys
import tarfile

import oras.client
import oras.provider


class CondaMirror(oras.provider.Registry):
    """
    A CondaMirror is a custom remote to push three layers per conda package:
     1. .tar.bz2 package file
     2. index.json file containing metadata and package dependencies
     3. .tar.gz of the info directory

    For the third, we want to be able to get interesting metadata about the
    package without actually needing to download it.
    """

    # We can use media types to organize layers
    media_types = {
        "application/vnd.conda.info.v1.tar+gzip": "info_archive",
        "application/vnd.conda.info.index.v1+json": "info_index",
        "application/vnd.conda.package.v1": "package_tarbz2",
        "application/vnd.conda.package.v2": "package_conda",
    }

    def inspect(self, name):
        # Parse the name into a container
        container = self.get_container(name)

        # Get the manifest with the three layers
        manifest = self.get_manifest(container)

        # Organize layers based on media_types
        layers = self._organize_layers(manifest)

        # Get the index (the function will check the success of the response)
        if "info_index" in layers:
            index = self.get_blob(container, layers["info_index"]["digest"]).json()
            print(json.dumps(index, indent=4))

        # The compressed index
        if "info_archive" in layers:
            archive = self.get_blob(container, layers["info_archive"]["digest"])
            archive = tarfile.open(fileobj=io.BytesIO(archive.content), mode="r:gz")
            print(archive.members)

        if "package_tarbz2" in layers:
            print(
                "Found layer %s that could be extracted to %s."
                % (
                    layers["package_tarbz2"]["digest"],
                    layers["package_tarbz2"]["annotations"][
                        "org.opencontainers.image.title"
                    ],
                )
            )

    def _organize_layers(self, manifest: dict) -> dict:
        """
        Given a manifest, organize based on the media type.
        """
        layers = {}
        for layer in manifest.get("layers", []):
            if layer["mediaType"] in self.media_types:
                layers[self.media_types[layer["mediaType"]]] = layer
        return layers


# We will need GitHub personal access token or token
token = os.environ.get("GITHUB_TOKEN")
user = os.environ.get("GITHUB_USER")

if not token or not user:
    sys.exit("GITHUB_TOKEN and GITHUB_USER are required in the environment.")


def main():
    mirror = CondaMirror()
    mirror.inspect("ghcr.io/wolfv/conda-forge/linux-64/xtensor:0.9.0-0")


if __name__ == "__main__":
    main()
