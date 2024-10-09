__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

__version__ = "0.2.22"
AUTHOR = "Vanessa Sochat"
EMAIL = "vsoch@users.noreply.github.com"
NAME = "oras"
PACKAGE_URL = "https://github.com/oras-project/oras-py"
KEYWORDS = "oci, registry, storage"
DESCRIPTION = "OCI Registry as Storage Python SDK"
LICENSE = "LICENSE"

################################################################################
# Global requirements

INSTALL_REQUIRES = (
    ("jsonschema", {"min_version": None}),
    ("requests", {"min_version": None}),
)

TESTS_REQUIRES = (("pytest", {"min_version": "4.6.2"}),)

DOCKER_REQUIRES = (("docker", {"exact_version": "5.0.1"}),)

INSTALL_REQUIRES_ALL = INSTALL_REQUIRES + TESTS_REQUIRES + DOCKER_REQUIRES
