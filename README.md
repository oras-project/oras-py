# ORAS Python

![https://raw.githubusercontent.com/oras-project/oras-www/main/docs/assets/images/oras.png](https://raw.githubusercontent.com/oras-project/oras-www/main/docs/assets/images/oras.png)

OCI Registry as Storage enables client libraries to push OCI Artifacts to [OCI Conformant](https://github.com/opencontainers/oci-conformance) registries. This is a Python client for that.

**under development**
 
## Usage

### Install

You'll first need to install oras python! Either from pypi:

```bash
$ pip install oras
```

Or from a local clone:

```bash
$ git clone https://github.com/oras-project/oras-py
$ cd oras-py
$ pip install .
```

### Registry

You should see [supported registries](https://oras.land/implementors/#docker-distribution), or if you
want to deploy a local testing registry (without auth), you can do:

```bash
$ docker run -it --rm -p 5000:5000 ghcr.io/oras-project/registry:latest
```

Or with authentication:


```bash
# This is an htpassword file, "b" means bcrypt
htpasswd -cB -b auth.htpasswd myuser mypass

# And start the registry with authentication
docker run -it --rm -p 5000:5000 \
    -v $(pwd)/auth.htpasswd:/etc/docker/registry/auth.htpasswd \
    -e REGISTRY_AUTH="{htpasswd: {realm: localhost, path: /etc/docker/registry/auth.htpasswd}}" \
    docker run -it --rm -p 5000:5000 ghcr.io/oras-project/registry:latest
```

### Login

Once you create (or already have) a registry, you will want to login. You can do:

```bash
$ oras-py login -u myuser -p mypass localhost:5000

# or localhost (insecure)
$ oras-py login -u myuser -p mypass -k localhost:5000
```

### Push

Let's first push a container. Let's follow [the example here](https://oras.land/cli/1_pushing/).

```bash
echo "hello dinosaur" > artifact.txt
```
```bash
$ oras-py push localhost:5000/dinosaur/artifact:v1 \
--manifest-config /dev/null:application/vnd.acme.rocket.config \
./artifact.txt
```
```bash
Successfully pushed localhost:5000/dinosaur/artifact:v1
```

And if you aren't using https, add `--insecure`

```bash
$ oras-py push localhost:5000/dinosaur/artifact:v1 --insecure \
--manifest-config /dev/null:application/vnd.acme.rocket.config \
./artifact.txt
```
```bash
Successfully pushed localhost:5000/dinosaur/artifact:v1
```

### Pull

Now try a pull! We will first need to delete the file

```bash
$ rm -f artifact.txt # first delete the file
$ oras-py pull localhost:5000/dinosaur/artifact:v1
```bash
$ cat artifact.txt
```

## TODO

 - add same views with auth
 - logout command
 - finish all basic commands
 - add testing 
 - should there be a tags function?
 - add example (custom) GitHub client
 - refactor internals to be more like oras-go (e.g., provider, copy?)
 - add schemas for manifest, annotations, etc.
 - need to have git commit, state, added to defaults on install/release. See [here](https://github.com/oras-project/oras/blob/main/Makefile).
 - quiet should be controller for verbosity
 - plain_http, configs, need to be parsed in client
 - todo we haven't added path traversal, or cacheRoot to pull
 - we should have common function to parse errors in json 'errors' -> list -> message
 - environment variables like `ORAS_CACHE` 

## Code of Conduct

This project has adopted the [CNCF Code of Conduct](https://github.com/cncf/foundation/blob/master/code-of-conduct.md). See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for further details.

## License

This code is licensed under the Apache 2.0 [LICENSE](LICENSE).
