# ORAS Python

![https://raw.githubusercontent.com/oras-project/oras-www/main/docs/assets/images/oras.png](https://raw.githubusercontent.com/oras-project/oras-www/main/docs/assets/images/oras.png)

OCI Registry as Storage enables client libraries to push OCI Artifacts to [OCI Conformant](https://github.com/opencontainers/oci-conformance) registries. This is a Python client for that.

**under development**
 
## Usage

You should see [supported registries](https://oras.land/implementors/#docker-distribution), or if you
want to deploy a local testing registry, you can do:

```bash
$ docker run -it --rm -p 5000:5000 registry 
```

And follow [the instructions here](https://oras.land/implementors/#using-docker-registry-with-authentication)
to add authentication (recommended). There is a [start-dev-server.sh](start-dev-server.sh) script
in the root of this repository that will start your registry for you after you generate
a credential.

### Login

Once you create (or already have) a registry, you will want to login. You can do:


```bash
$ oras-py login -u myuser -p mypass localhost:5000

# or localhost (insecure)
$ oras-py login -u myuser -p mypass -k localhost:5000
```


## TODO

 - finish all basic commands
 - add testing
 - need to have git commit, state, added to defaults on install/release. See [here](https://github.com/oras-project/oras/blob/main/Makefile).

## License

This code is licensed under the MIT [LICENSE](LICENSE).
