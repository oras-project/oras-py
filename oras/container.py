__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"


import re
from typing import Optional

import oras.defaults

docker_regex = re.compile(
    "(?:(?P<registry>[^/@]+[.:][^/@]*)/)?"
    "(?P<namespace>(?:[^:@/]+/)+)?"
    "(?P<repository>[^:@/]+)"
    "(?::(?P<tag>[^:@]+))?"
    "(?:@(?P<digest>.+))?"
    "$"
)


class Container:
    def __init__(self, name: str, registry: Optional[str] = None):
        """
        Parse a container name and easily get urls for registry interactions.

        :param name: the full name of the container to parse (with any components)
        :type name: str
        :param registry: a custom registry name, if not provided with URI
        :type registry: str
        """
        self.registry = registry or oras.defaults.registry.index_name

        # Registry is the name takes precendence
        self.parse(name)

    def get_blob_url(self, digest: str) -> str:
        """
        Get the URL to download a blob

        :param digest: the digest to download
        :type digest: str
        """
        return f"{self.registry}/v2/{self.namespace}/{self.repository}/blobs/{digest}"

    def upload_blob_url(self) -> str:
        return f"{self.registry}/v2/{self.namespace}/{self.repository}/blobs/uploads/"

    def tags_url(self, N=10_000) -> str:
        return f"{self.registry}/v2/{self.namespace}/{self.repository}/tags/list?n={N}"

    def put_manifest_url(self) -> str:
        return f"{self.registry}/v2/{self.namespace}/{self.repository}/manifests/{self.tag}"

    def get_manifest_url(self) -> str:
        return f"{self.registry}/v2/{self.namespace}/{self.repository}/manifests/{self.tag}"

    def __str__(self) -> str:
        return self.uri

    @property
    def uri(self) -> str:
        """
        Assemble the complete unique resource identifier
        """
        uri = f"{self.namespace}/{self.repository}"
        if self.registry:
            uri = f"{self.registry}/{uri}"

        # Digest takes preference because more specific
        if self.digest:
            uri = f"{uri}@{self.digest}"
        elif self.tag:
            uri = f"{uri}:{self.tag}"
        return uri

    def parse(self, name: str):
        """
        Parse the container name into registry, repository, and tag.

        :param name: the full name of the container to parse (with any components)
        :type name: str
        """
        match = re.search(docker_regex, name)
        if not match:
            raise ValueError(
                f"{name} does not match a recognized registry unique resource identifier. Try <registry>/<namespace>/<repository>:<tag|digest>"
            )
        items = match.groupdict()  # type: ignore
        self.repository = items["repository"]
        self.registry = items["registry"] or self.registry
        self.namespace = items["namespace"]
        self.tag = items["tag"] or oras.defaults.default_tag
        self.digest = items["digest"]

        # Repository and namespace are required
        if not self.repository or not self.namespace:
            raise ValueError(
                "You are minimally required to include a <namespace>/<repository>"
            )
        self.namespace = self.namespace.strip("/")
