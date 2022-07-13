# Installation

## Pypi

The module is available in pypi as
[oras](https://pypi.org/project/oras/), and you can install as follows:

``` console
$ pip install oras
```

You can also clone the repository and install locally:

``` console
$ git clone https://github.com/oras-project/oras-py
$ cd oras-py
$ pip install .
```

Note that we have several extra modes for installation:

``` console
# interactions are done via the docker client instead of manual
$ pip install oras[docker]

# Install dependencies for linting and tests
$ pip install oras[tests]

# install everything
$ pip install oras[all]
```

Or in development mode, add `-e`:

``` console
$ pip install -e .
```

Development mode means that the install is done from where you\'ve
cloned the library, so any changes you make are immediately \"live\" for
testing.

## Docker Container

We provide a
[Dockerfile](https://github.com/oras-project/oras-py/blob/main/Dockerfile)
to build a container with the client.

``` console
$ docker build -t oras-py .

$ docker run -it oras-py                                                                                                                   
# which oras-py
/opt/conda/bin/oras-py
```
