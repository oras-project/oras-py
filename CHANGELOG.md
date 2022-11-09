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
 - ecr and others do not require a formatted namespace (0.0.18)
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
