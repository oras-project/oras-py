__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

import pytest

from oras.container import Container


@pytest.mark.parametrize(
    "name,registry,namespace,repository,tag",
    [
        ("localhost/myrepo:v1", "localhost", None, "myrepo", "v1"),
        ("localhost/org/myrepo:v1", "localhost", "org", "myrepo", "v1"),
        ("localhost:5000/myrepo:v1", "localhost:5000", None, "myrepo", "v1"),
        ("ghcr.io/org/myrepo:v1", "ghcr.io", "org", "myrepo", "v1"),
        ("localhostx/myrepo:v1", "docker.io", "localhostx", "myrepo", "v1"),
        ("org/myrepo", "docker.io", "org", "myrepo", "latest"),
    ],
)
def test_parse_registry(name, registry, namespace, repository, tag):
    container = Container(name)
    assert container.registry == registry
    assert container.namespace == namespace
    assert container.repository == repository
    assert container.tag == tag


def test_localhost_manifest_url():
    container = Container("localhost/myrepo:v1")
    assert container.manifest_url() == "localhost/v2/myrepo/manifests/v1"
