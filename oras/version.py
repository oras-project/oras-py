__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021-2022, Vanessa Sochat"
__license__ = "Apache-2.0"

__version__ = "0.0.1"
AUTHOR = "Vanessa Sochat"
EMAIL = "vsoch@users.noreply.github.com"
NAME = "oras"
PACKAGE_URL = "https://github.com/oras-project/oras-python"
KEYWORDS = "oci, registry, storage"
DESCRIPTION = "OCI Registry as Storage Python client"
LICENSE = "LICENSE"

################################################################################
# Global requirements

INSTALL_REQUIRES = (
    ("requests", {"min_version": None}),
    ("docker", {"min_version": "5.0.0"}),
)

TESTS_REQUIRES = (("pytest", {"min_version": "4.6.2"}),)
INSTALL_REQUIRES_ALL = INSTALL_REQUIRES + TESTS_REQUIRES
