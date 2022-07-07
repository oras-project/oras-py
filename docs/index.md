# Oras Python

![Oras Python Logo](https://raw.githubusercontent.com/oras-project/oras-www/main/docs/assets/images/oras.png)

Welcome to Oras Python!

OCI Registry as Storage enables client libraries to push OCI Artifacts
to [OCI Conformant](https://github.com/opencontainers/oci-conformance)
registries. This is a Python client for that.

``` console
# install the client
$ pip install  oras

# Login to an OCI registry
$ oras-py login -u myuser -p mypass localhost:5000

# Prepare an artifact!
echo "hello dinosaur" > artifact.txt

# Push it..
$ oras-py push localhost:5000/dinosaur/artifact:v1 \
--manifest-config /dev/null:application/vnd.acme.rocket.config \
./artifact.txt
Successfully pushed localhost:5000/dinosaur/artifact:v1

# And pull again
$ rm -f artifact.txt # first delete the file
$ oras-py pull localhost:5000/dinosaur/artifact:v1
```

To get started, see the [oras.land getting started
guide](https://oras.land/client_libraries/1_python/) or if you are a
developer, see the `getting-started`{.interpreted-text role="ref"} page
hosted here. Would you like to request a feature or contribute?

[Open an issue](https://github.com/oras-project/oras-py/issues).
