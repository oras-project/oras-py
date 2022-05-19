# ORAS Python

![https://raw.githubusercontent.com/oras-project/oras-www/main/docs/assets/images/oras.png](https://raw.githubusercontent.com/oras-project/oras-www/main/docs/assets/images/oras.png)

OCI Registry as Storage enables client libraries to push OCI Artifacts to [OCI Conformant](https://github.com/opencontainers/oci-conformance) registries. This is a Python client for that.

See our ⭐️ [Documentation](https://oras-project.github.io/oras-py/) ⭐️ to get started.
 
## TODO

 - add example (custom) GitHub client
 - refactor internals to be more like oras-go (e.g., provider, copy?)
 - need to have git commit, state, added to defaults on install/release. See [here](https://github.com/oras-project/oras/blob/main/Makefile).
 - plain_http vs insecure?
 - todo we haven't added path traversal, or cacheRoot to pull
 - environment variables like `ORAS_CACHE` 

## Code of Conduct

Please note that this project has adopted the [CNCF Code of Conduct](https://github.com/cncf/foundation/blob/master/code-of-conduct.md).
Please follow it in all your interactions with the project members and users.

## License

This code is licensed under the Apache 2.0 [LICENSE](LICENSE).
