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
