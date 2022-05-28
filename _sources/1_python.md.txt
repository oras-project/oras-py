# Oras Python User Guide

Oras Python will allow you to run traditional push and pull commands for artifacts,
or generate a custom client. This small user guide will walk you through these various
steps, and please open an issue if functionality is missing.

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

We provide a [Dockerfile](https://github.com/oras-project/oras-py/blob/main/Dockerfile) to build a container with the client.

```bash
$ docker build -t oras-py .

$ docker run -it oras-py                                                                                                                   
# which oras-py
/opt/conda/bin/oras-py
```

## Registry

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

## Command Line

### Login

Once you create (or already have) a registry, you will want to login. You can do:

```bash
$ oras-py login -u myuser -p mypass localhost:5000

# or localhost (insecure)
$ oras-py login -u myuser -p mypass -k localhost:5000 --insecure

WARNING! Using --password via the CLI is insecure. Use --password-stdin.
Login Succeeded
```

You can also provide them interactively

        
```bash   
$ oras-py login -k localhost:5000 --insecure
Username: myuser
Password: mypass
Login Succeeded
```

or use `--password-stdin`

```bash
$ echo mypass | oras-py login -u myuser -k localhost:5000 --insecure --password-stdin
Login Succeeded
```

Note that oras-py will not remove content from your docker config files, so
there is no concept of a "logout" unless you are using the client interactively,
and have configs loaded, then you can do:

```python
cli.logout(hostname)
```

### Push

Let's first push a container. Let's follow [the example here](https://oras.land/cli/1_pushing/):

```bash
echo "hello dinosaur" > artifact.txt
$ oras-py push localhost:5000/dinosaur/artifact:v1 \
--manifest-config /dev/null:application/vnd.acme.rocket.config \
./artifact.txt
Successfully pushed localhost:5000/dinosaur/artifact:v1
```

And if you aren't using https, add `--insecure`

```bash
$ oras-py push localhost:5000/dinosaur/artifact:v1 --insecure \
--manifest-config /dev/null:application/vnd.acme.rocket.config \
./artifact.txt
Successfully pushed localhost:5000/dinosaur/artifact:v1
```

### Pull


Now try a pull! We will first need to delete the file

```bash
$ rm -f artifact.txt # first delete the file
$ oras-py pull localhost:5000/dinosaur/artifact:v1
$ cat artifact.txt
hello dinosaur
```

## Within Python

If you want to use the library from within Python, here is how to do that.
You'll still need a running registry as shown above. As a trick, if you want
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
