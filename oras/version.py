__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

__version__ = "0.2.51"
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

TESTS_REQUIRES = (
    ("pytest", {"min_version": "4.6.2"}),
    ("pytest-asyncio", {"min_version": "0.21.0"}),
)

DOCKER_REQUIRES = (("docker", {"exact_version": "5.0.1"}),)

ECR_REQUIRES = (("boto3", {"min_version": "1.33.0"}),)

# Asynchronous support is optional: the synchronous client keeps working on
# requests alone, and only oras[async] pulls in httpx.
ASYNC_REQUIRES = (("httpx", {"min_version": "0.23.0"}),)

INSTALL_REQUIRES_ALL = (
    INSTALL_REQUIRES + TESTS_REQUIRES + DOCKER_REQUIRES + ECR_REQUIRES + ASYNC_REQUIRES
)
