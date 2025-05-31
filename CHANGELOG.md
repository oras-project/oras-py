# CHANGELOG

This is a manually generated log to track changes to the repository for each release.
Each section should include general headers such as **Implemented enhancements**
and **Merged pull requests**. Critical items to know are:

 - renamed commands
 - deprecated / removed commands
 - changed defaults
 - backward incompatible changes (recipe file format? image file format?)
 - migration guidance (how to convert images?)
 - changed behaviour (recipe sections work differently)

The versions coincide with releases on pip. Only major versions will be released as tags on Github.

## [0.0.x](https://github.com/oras-project/oras-py/tree/main) (0.0.x)
 - fix 'get_manifest()' method with adding 'load_configs()' calling (0.2.33)
 - fix 'Provider' method signature to allow custom CA-Bundles (0.2.32)
 - initialize headers variable in do_request (0.2.31)
 - Make reproducible targz without mimetype (0.2.30)
 - don't include Content-Length header in upload_manifest (0.2.29)
 - propagate the tls_verify parameter to auth backends (0.2.28)
 - don't add an Authorization header is there is no token (0.2.27), closes issue [182](https://github.com/oras-project/oras-py/issues/182)
 - check for blob existence before uploading (0.2.26)
   - fix get_tags for ECR when limit is None, closes issue [173](https://github.com/oras-project/oras-py/issues/173)
   - fix empty token for anon tokens to work, closes issue [167](https://github.com/oras-project/oras-py/issues/167)
 - retry on 500 (0.2.25)
 - align provider config_path type annotations (0.2.24)
 - add missing prefix property to auth backend (0.2.23)
 - allow for filepaths to include `:` (0.2.22)
 - release request (0.2.21)
 - add missing basic auth data for request token function in token auth backend (0.2.2)
 - re-enable chunked upload (0.2.1)
 - refactor of auth to be provided by backend modules (0.2.0)
   - bugfix maintain requests's verify valorization for all invocations, augment basic auth header to existing headers
 - Allow generating a Subject from a pre-existing Manifest (0.1.30)
 - add option to not refresh headers during the pushing flow, useful for push with basic auth (0.1.29)
 - enable additionalProperties in schema validation (0.1.28)
 - Introduce the option to not refresh headers when fetching manifests when pulling artifacts (0.1.27)
 - To make it available for more OCI registries, the value of config used when `manifest_config` is not specified in `client.push()` has been changed from a pure empty string to `{}` (0.1.26)
 - refactor tests using fixtures and rework pre-commit configuration (0.1.25)
 - eliminate the additional subdirectory creation while pulling an image to a custom output directory (0.1.24)
   - updating the exclude string in the pyproject.toml file to match the [data type black expects](https://black.readthedocs.io/en/stable/usage_and_configuration/the_basics.html#configuration-format)
 - patch fix for pulling artifacts by digest (0.1.23)
    - patch fix to reject cookies as this could trigger registries into handling the lib as a web client
    - patch fix for proper validation and specification of the subject element
 - add tls_verify to provider class for optional disable tls verification (0.1.22)
 - Allow to pull exactly to PWD (0.1.21)
 - Ensure insecure is passed to provider class (0.1.20)
 - patch fix for blob upload Windows, closes issue [93](https://github.com/oras-project/oras-py/issues/93) (0.1.19)
 - patch fix for empty manifest config on Windows, closes issue [90](https://github.com/oras-project/oras-py/issues/90) (0.1.18)
 - patch fix to correct session url pattern, closes issue [78](https://github.com/oras-project/oras-py/issues/78) (0.1.17)
 - add support for tag deletion and retry decorators (0.1.16)
 - bugfix that pagination sets upper limit of 10K (0.1.15)
 - pagination for tags (and general function for pagination) (0.1.14)
 - expose upload_blob function to be consistent (0.1.13)
 - ensure we always strip path separators before pull/push (0.1.12)
 - exposing download_blob to the user since it uses streaming (0.1.11)
   - adding developer examples for pull.
   - start deprecation for _download_blob, _put_upload, _chunked_upload, _upload_manifest
     in favor of equivalent public functions.
 - moving of docs to fully be here with extended examples (0.1.1)
   - addition of oras.utils.workdir to provide local context
 - clients are removed from Python SDK in favor of examples (0.1.0)
   - login refactored to be part of the basic client
 - ecr and others do not require a formatted namespace (0.0.19)
   - relaxing manifest requirements - ECR has extra field "subject"
   - relaxing manifest requirements - ECR has annotations with None
   - cutting out early for asking for token if Authorization header set.
 - logger should only exit in command line client, not in API (0.0.18)
   - raising exceptions allows the calling using to catch the error
   - support for requesting anonymous token from registry
 - Added expected header for authentication to gitlab registry (0.0.17)
 - safe extraction for targz extractions (0.0.16)
 - disable chunked upload for now (not supported by all registries) (0.0.15)
 - support for adding one-off annotations for a manifest (0.0.14)
 - add debug if location header returned is empty (0.0.13)
 - docker is an optional dependency, to minimize dependencies (0.0.12)
   - Removing runtime dependency pytest-runner
   - bug fixes for GitHub packages
 - Adding authenticated login tests, fixing bugs with login/logout (0.0.11)
 - First draft release with basic functionality (0.0.1)
 - Initial skeleton of project (0.0.0)
