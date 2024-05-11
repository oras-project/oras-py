# Developer Guide

This developer guide includes more complex interactions like
contributing registry entries and building containers. If you haven't
read [the installation guide](installation.md) you
should do that first. If you want to see a more general user guide with examples
for using the SDK and writing clients, see our [user guide](user-guide.md).

## Running Tests

You'll want to create an environment to install to, and then install:

```bash
$ make install
```

We recommend a local registry without auth for tests.

```bash
$ docker run -it --rm -p 5000:5000 ghcr.io/oras-project/registry:latest
```

Zot is a good solution too:

```bash
docker run -d -p 5000:5000 --name oras-quickstart ghcr.io/project-zot/zot-linux-amd64:latest
```

For quick auth, you can use the included Developer container and do:

```bash
make install
make test
```

And then when you run `make test`, the tests will run. This ultimately
runs the file [scripts/test.sh](https://github.com/oras-project/oras-py/blob/main/scripts/test.sh).
If you want to test interactively, add an IPython import statement somewhere in the tests:

```bash
# pip install IPython
import IPython
IPython.embed()
```

And then change the last line of the file to be:

```diff
- pytest oras/
+ pytest -xs oras/
```

And then you should be able to interactively run (and debug) the same tests
that run in GitHub actions.


## Code Linting

We use [pre-commit](https://pre-commit.com/) to handle code linting and formatting, including:

 - black
 - isort
 - flake8
 - mypy

Our setup also handles line endings and ensuring that you don't add large files!
Using the tools is easy. After installing oras-py to a local environment,
you can use pre-commit as follows:


```bash
$ pip install -r .github/dev-requirements.txt
```

Then to do a manual run:

```bash
$ pre-commit run --all-files
```
```console
check for added large files..............................................Passed
check for case conflicts.................................................Passed
check docstring is first.................................................Passed
fix end of files.........................................................Passed
trim trailing whitespace.................................................Passed
mixed line ending........................................................Passed
black....................................................................Passed
isort....................................................................Passed
flake8...................................................................Passed
```

And to install as a hook (recommended so you never commit with linting flaws!)

```bash
$ pre-commit install
```

The above are provided as courtesy commands via:

```bash
$ make develop
$ make lint
```

## Documentation

The documentation is provided in the `docs` folder of the repository,
and generally most content that you might want to add is under
`getting_started`. For ease of contribution, files that are likely to be
updated by contributors (e.g., mostly everything but the module generated files)
 are written in markdown. If you need to use [toctree](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#table-of-contents) you should not use extra newlines or spaces (see index.md files for exampls).
Markdown is the chosen language for the oras community, and this is why we chose to
use it over restructured syntax - it makes it easier to contribute documentation.


### Install Dependencies and Build

The documentation is built using sphinx, and generally you can install
dependencies:

```console
# In main oras-py folder (oras-py is needed to build docs)
$ pip install -e .

# Now docs dependencies
cd docs
pip install -r requrements.txt

# Build the docs into _build/html
make html
```

### Preview Documentation

After `make html` you can enter into `_build/html` and start a local web
server to preview:

```console
$ python -m http.server 9999
```

And open your browser to `localhost:9999`

### Docstrings

To render our Python API into the docs, we keep an updated restructured
syntax in the `docs/source` folder that you can update on demand as
follows:

```console
$ ./apidoc.sh
```

This should only be required if you change any docstrings or add/remove
functions from oras-py source code.
