# Developer Guide

This developer guide includes more complex interactions like
contributing registry entries and building containers. If you haven't
read `getting_started-installation`{.interpreted-text role="ref"} you
should do that first. If you want to see a more general user guide, look
at the [oras.land Python guide](https://oras.land/client_libraries/1_python/).

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

``` console
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

## Running Tests

You'll want to create an environment to install to, and then install:

```bash
$ make install
```

You'll then want a registry running for the tests:

```bash
$ docker run -it --rm -p 5000:5000 ghcr.io/oras-project/registry:latest
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

## Creating a Custom Client

If you want to create your own client, you likely want to:

1.  Subclass the `oras.provider.Registry` class
2.  Add custom functions to push, pull, or create manifests / layers
3.  Provide authentication, if required.

### The Registry Client

Your most basic registry (that will mimic the default can be created
like this:

``` python
import oras.provider

class MyProvider(oras.provider.Registry):
    pass
```

### Pull Interactions

You can imagine having a custom function that will retrieve a manifest
or blob and do custom operations on it.

``` python
def inspect(self, name):

    # Parse the name into a container
    container = self.get_container(name)

    # Get the manifest with the three layers
    manifest = self.get_manifest(container)

    # Organize layers based on media_types
    layers = self._organize_layers(manifest)

    # Read info.json media type, find correct blob...
    # download correct blob, etc.
```

Specifically the function `self.get_blob` will allow you to do that.

### Push Interactions

You might instead want to have a custom lookup of archive paths and
media types. Let's say we start with this lookup, `archives`:

``` python
archives = {
    "/tmp/pakages-tmp.q6amnrkq/pakages-0.0.16.tar.gz": "application/vnd.oci.image.layer.v1.tar+gzip",
    "/tmp/pakages-tmp.q6amnrkq/sbom.json": "application/vnd.cyclonedx"
}
```

Note that since paths are unique (and media types are not) we use that
as the dictionary key. Here is how we might then create a custom
Registry provider to handle:

1.  Creating layers from the blobs and media types
2.  Creating a manifest with the layers, and a config
3.  Uploading all of them

This example is similar to what the `oras.provider.Registry` provides,
but we are allowing better customization of content types and overriding
the default "push" function.

``` python
import oras.oci
import oras.defaults
import oras.provider
from oras.decorator import ensure_container

import os
import sys

class Registry(oras.provider.Registry):
    @ensure_container
    def push(self, container, archives: dict, annotations=None):
        """
        Given a dict of layers (paths and corresponding mediaType) push.
        """
        # Prepare a new manifest
        manifest = oras.oci.NewManifest()

        # A lookup of annotations we can add
        annotset = oras.oci.Annotations(annotations or {})

        # Upload files as blobs
        for blob, mediaType in archives.items():

            # Must exist
            if not os.path.exists(blob):
                logger.exit(f"{blob} does not exist.")

            # Save directory or blob name before compressing
            blob_name = os.path.basename(blob)

            # If it's a directory, we need to compress
            cleanup_blob = False
            if os.path.isdir(blob):
                blob = oras.utils.make_targz(blob)
                cleanup_blob = True

            # Create a new layer from the blob
            layer = oras.oci.NewLayer(blob, mediaType, is_dir=cleanup_blob)
            annotations = annotset.get_annotations(blob)
            layer["annotations"] = {oras.defaults.annotation_title: blob_name}
            if annotations:
                layer["annotations"].update(annotations)

            # update the manifest with the new layer
            manifest["layers"].append(layer)

            # Upload the blob layer
            response = self._upload_blob(blob, container, layer)
            self._check_200_response(response)

            # Do we need to cleanup a temporary targz?
            if cleanup_blob and os.path.exists(blob):
                os.remove(blob)

        # Add annotations to the manifest, if provided
        manifest_annots = annotset.get_annotations("$manifest")
        if manifest_annots:
            manifest["annotations"] = manifest_annots

        # Prepare the manifest config (temporary or one provided)
        config_annots = annotset.get_annotations("$config")
        conf, config_file = oras.oci.ManifestConfig()

        # Config annotations?
        if config_annots:
            conf["annotations"] = config_annots

        # Config is just another layer blob!
        response = self._upload_blob(config_file, container, conf)
        self._check_200_response(response)

        # Final upload of the manifest
        manifest["config"] = conf
        self._check_200_response(self._upload_manifest(manifest, container))
        print(f"Successfully pushed {container}")
        return response
```

The only difference between the above and the provided provider is that
we are allowing more customization of the layers. The default oras
client just assumes you have either a single layer or a compressed
layer. Note that the decorator `ensure_container` simply ensures that
the target you provide as the first argument is properly parsed for the
remainder of the function.

### Instantiate

For both of the examples above, you might do the following. First, some
registries may require authentiation:

```python
# We will need GitHub personal access token or token
token = os.environ.get("GITHUB_TOKEN")
user = os.environ.get("GITHUB_USER")

if not token or not user:
    sys.exit("GITHUB_TOKEN and GITHUB_USER are required in the environment.")
```

And as a reminder, if you want to deploy a quick local registry (without auth)
you can do:

```bash
$ docker run -it --rm -p 5000:5000 ghcr.io/oras-project/registry:latest
```

And add the `-d` for detached. Then you can run your custom functions after
doing that, either inspecting a particular unique resource identifier or using
your lookup of archives (paths and media types) to push:

``` python
def main():

    # Pull Example
    reg = MyProvider()
    reg.set_basic_auth(user, token)
    reg.inspect("ghcr.io/wolfv/conda-forge/linux-64/xtensor:0.9.0-0")

    # Push Example
    reg = Registry()
    reg.set_basic_auth(user, token)
    archives = {
        "/tmp/pakages-tmp.q6amnrkq/pakages-0.0.16.tar.gz": "application/vnd.oci.image.layer.v1.tar+gzip",
        "/tmp/pakages-tmp.q6amnrkq/sbom.json": "application/vnd.cyclonedx"}
    reg.push("ghcr.io/vsoch/excellent-dinosaur:latest", archives)
```
