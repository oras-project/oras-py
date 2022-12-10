# Oras Python User Guide

Oras Python is a Python SDK that will allow you to create applications in Python
that can do traditional push and pull commands to interact with a custom set of
artifacts. As of version 0.1.0 we no longer provide a default client alongside
oras Python, and if you need a client you should use [oras](https://github.com/oras-project/oras) in Go.
This user guide will walk you through these various steps, and point you to
relevant examples. Please [open an issue](https://github.com/oras-project/oras-py/issues) if
you have a question or otherwise need help with your specific implementation.
More detailed developer examples can also be found on the
[Oras Python](https://oras-project.github.io/oras-py/) page hosted alongside the repository.

## Installation

### Pypi

The module is available in pypi as [oras](https://pypi.org/project/oras/)
and you can install as follows:

```bash
$ pip install oras
```

You can also clone the repository and install locally:

```bash
$ git clone https://github.com/oras-project/oras-py
$ cd oras-py
$ pip install .
```

Or in development mode:

```bash
$ pip install -e .
```

Development mode means that the install is done from where you've cloned the library,
so any changes you make are immediately "live" for testing.


### Docker Container

We provide a [Dockerfile](https://github.com/oras-project/oras-py/blob/main/Dockerfile) to build a container
with the Python SDK.

```bash
$ docker build -t oras-py .

$ docker run -it oras-py
$ ipython
> import oras
```

## Registry

It's often helpful to develop with a local registry running.
You should see [supported registries](https://oras.land/implementors/#docker-distribution) or if you
want to deploy a local testing registry (without auth), you can do:


```bash
$ docker run -it --rm -p 5000:5000 ghcr.io/oras-project/registry:latest
```

To test token authentication, you can either [set up your own auth server](https://github.com/adigunhammedolalekan/registry-auth)
or just use an actual registry. The most we can do here is set up an example that uses basic auth.


```bash
# This is an htpassword file, "b" means bcrypt
htpasswd -cB -b auth.htpasswd myuser mypass
```

> :warning: The server below will work to login with basic auth, but you won't be able to issue tokens.

```bash
# And start the registry with authentication
docker run -it --rm -p 5000:5000 \
    -v $(pwd)/auth.htpasswd:/etc/docker/registry/auth.htpasswd \
    -e REGISTRY_AUTH="{htpasswd: {realm: localhost, path: /etc/docker/registry/auth.htpasswd}}" \
    ghcr.io/oras-project/registry:latest
```

## Usage

The library is intended to be used within Python. We provide a basic client
that handles push and pull, and you are encouraged to check out our
[examples](https://github.com/oras-project/oras-py/tree/main/oras/cli)
(provided alongside the repository and in the wild) to see other implementations
available. You'll still need a running registry as shown above, or if you have
access to a remote registry (e.g., GitHub Packages, Docker Hub, or other that
supports ORAS) you can use that. As a trick, if you want
more detail than is available in these docs, you can peek into the
[Python client code](https://github.com/oras-project/oras-py/tree/main/oras/cli).


### Login and Logout

```bash
import oras.client
client = oras.client.OrasClient()
client.login(password="myuser", username="myuser", insecure=True)
```

And logout!

```bash
client.logout("localhost:5000")
```

### Push and Pull

We are again following [the example here](https://oras.land/cli/1_pushing/).
We are assuming an `artifact.txt` in the present working directory.


```bash
client = oras.client.OrasClient(insecure=True)
client.push(files=["artifact.txt"], target="localhost:5000/dinosaur/artifact:v1")
Successfully pushed localhost:5000/dinosaur/artifact:v1
Out[4]: <Response [201]>
```

And then pull!

```bash
res = client.pull(target="localhost:5000/dinosaur/artifact:v1")
['/tmp/oras-tmp.e5itvzfi/artifact.txt']
```


## Custom Clients

The benefit of Oras Python is that you can create a subclass that easily implements
a registry, and then allows you to do custom interactions. We provide a few examples:

 - [Conda Mirror](https://github.com/oras-project/oras-py/blob/main/examples/conda-mirror.py): an example to parse custom layers to retrieve metadata index.jsons (and archive) along with a binary to download.

If you are looking for developer documentation or more detailed client examples,
see the [Oras Python Documentation](https://oras-project.github.io/oras-py/)
hosted alongside the repository.


## Debugging

> Can I see more debug information?

Yes! Try adding `--debug` *after* any command like pull, push, login, etc. More verbose
output should appear. If we need further verbosity, please open an issue and it can be added.

> I get unauthorized when trying to login to an Amazon ECR Registry

Note that for [Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html)
you might need to login per the instructions at the link provided. If you look at your `~/.docker/config.json` and see
that there is a "credsStore" section that is populated, you might also need to comment this out
while using oras-py. Oras-py currently doesn't support reading external credential stores, so you will
need to comment it out, login again, and then try your request. To sanity check that you've done
this correctly, you should see an "auth" key under a hostname under "auths" in this file with a base64
encoded string (this is actually your username and password!) An empty dictionary there indicates that you
are using a helper.
