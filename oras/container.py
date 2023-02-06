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

    @property
    def api_prefix(self):
        """
        Return the repository prefix for the v2 API endpoints.
        """
        if self.namespace:
            return f"{self.namespace}/{self.repository}"
        return self.repository

    def get_blob_url(self, digest: str) -> str:
        """
        Get the URL to download a blob

        :param digest: the digest to download
        :type digest: str
        """
        return f"{self.registry}/v2/{self.api_prefix}/blobs/{digest}"

    def upload_blob_url(self) -> str:
        return f"{self.registry}/v2/{self.api_prefix}/blobs/uploads/"

    def tags_url(self, N=None) -> str:
        if N is None:
            return f"{self.registry}/v2/{self.api_prefix}/tags/list"
        return f"{self.registry}/v2/{self.api_prefix}/tags/list?n={N}"

    def manifest_url(self, tag: Optional[str] = None) -> str:
        """
        Get the manifest url for a specific tag, or the one for this container.

        The tag provided can also correspond to a digest.

        :param tag: an optional tag to provide (if not provided defaults to container)
        :type tag: None or str
        """
        tag = tag or self.tag
        return f"{self.registry}/v2/{self.api_prefix}/manifests/{tag}"

    def __str__(self) -> str:
        return self.uri

    @property
    def uri(self) -> str:
        """
        Assemble the complete unique resource identifier
        """
        if self.namespace:
            uri = f"{self.namespace}/{self.repository}"
        else:
            uri = f"{self.repository}"
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

        # Repository is required
        if not self.repository:
            raise ValueError(
                "You are minimally required to include a <namespace>/<repository>"
            )
        if self.namespace:
            self.namespace = self.namespace.strip("/")
