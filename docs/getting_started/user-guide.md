# User Guide

Oras Python is a Python SDK that will allow you to create applications in Python
that can do traditional push and pull commands to interact with a custom set of
artifacts. As of version 0.1.0 we no longer provide a default client alongside
oras Python, and if you need a client you should use [oras](https://github.com/oras-project/oras) in Go.
This user guide will walk you through these various steps, and point you to
relevant examples. Please [open an issue](https://github.com/oras-project/oras-py/issues) if
you have a question or otherwise need help with your specific implementation,
or jump to our [developer guide](developer-guide.md) to learn about running tests
or contributing to the project. If you want to create your own client, you likely want to:


 1. Start a local registry (described below), or have access to an ORAS [supported registry](https://oras.land/implementors/#docker-distribution)
 2. Decide on the context for your code (e.g., it's easy to start with Python functions in a single file and move to a client setup if appropriate for your tool)
 3. Subclass the `oras.provider.Registry` for your custom class (examples below!)
 4. Add custom functions to push, pull, or create manifests / layers
 5. Provide authentication, if required.


## Local Development Registry

It's often helpful to develop with a local registry running.
If you want to deploy a local testing registry (without auth), you can do:


```bash
$ docker run -it --rm -p 5000:5000 ghcr.io/oras-project/registry:latest
```

And add the `-d` for detached.  If you are brave and want to try basic auth:
bash
```bash
# This is an htpassword file, "b" means bcrypt
htpasswd -cB -b auth.htpasswd myuser mypass
```

> ⚠️ The server below will work to login with basic auth, but you won't be able to issue tokens.

```bash
# And start the registry with authentication
docker run -it --rm -p 5000:5000 \
    -v $(pwd)/auth.htpasswd:/etc/docker/registry/auth.htpasswd \
    -e REGISTRY_AUTH="{htpasswd: {realm: localhost, path: /etc/docker/registry/auth.htpasswd}}" \
    ghcr.io/oras-project/registry:latest
```

### Create a Client Class

Your most basic registry (that will mimic the default can be created
like this:

```python
import oras.provider

class MyProvider(oras.provider.Registry):
    pass
```

If you want to also have the default `login` and `logout` functions, you
should wrap the `oras.client.OrasClient` instead:

```python
import oras.client

class MyProvider(oras.client.OrasClient):
    pass
```

Authentication is provided by custom modules, and you can read about loading
and using them [here](#authentication). Also note that we currently just have one provider type (the `Registry`) and if you
have an idea for a request or custom provider, please [let us know](https://github.com/oras-project/oras-py/issues).

### Creating OCI Objects

If you need to make a config, a manifest, or layers for it, we have helper functions to
support that!

<details>

<summary>Example of creating a config (click to expand)</summary>

This is an empty config, size 0 to /dev/null.

```python
import oras.oci

conf, config_file = oras.oci.ManifestConfig()
```
```console
# conf
{
    "mediaType": "application/vnd.unknown.config.v1+json",
    "size": 0,
    "digest": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}

# config_file
/dev/null
```

Here is a config for a file that you already have existing:

```python
conf, config_file = oras.oci.ManifestConfig('/tmp/config.json')
```
```console
# conf
{
    "mediaType": "application/vnd.unknown.config.v1+json",
    "size": 3891,
    "digest": "sha256:1192142acbf7ac7578906407f5a28820c4ff69937000558613c2d9ec56db370a"
}

# config_file
/tmp/config.json
```
</details>

Before you can use them to populate a manifest, you need layers!

<details>

<summary>Example of creating layers (click to expand)</summary>

Let's say we start with a list of files "blobs" and a custom media type:

```python
import os
import oras.oci
import oras.defaults

layers = []
for blob in blobs:
    layer = oras.oci.NewLayer(blob, is_dir=False, media_type="org.dinosaur.tools.blobish")

    # This is important so oras clients can derive the relative name you want to download to
    # Using basename assumes a flat directory of files - it doesn't have to be.
    # You can add more annotations here!
    layer["annotations"] = {oras.defaults.annotation_title: os.path.basename(blob)}
    layers.append(layer)
```

Next read the manifest example to see what to do with these layers! Note that our
push examples also have this in full.

</details>

Finally, assuming you have some layers, let's wrap a manifest around them.

<details>

<summary>Example of creating a manifest (click to expand)</summary>

This is fairly straight forward!

```python
import oras.oci

# Prepare a new manifest
manifest = oras.oci.NewManifest()

# update the manifest with layers
manifest["layers"] = layers

# Note that you can add annotations to the manifest too
manifest['annotations'] = {'org.dinosaur.tool.food': 'avocado'}

# Add your previously created config to it!
manifest["config"] = conf
```

Given a client, you would use `self.upload_manifest(manifest, package)` to push your manifest,
where package is the complete unique resource identifier. Note that
you should do blobs (layers) and the config first.

</details>

### Tags

We provide a simple "get_tags" function to make it easy to instantiate a client and ask for tags from
a registry. Let's say we want to get tags from conda-forge. We could create a client:

```python
import oras.client

client = oras.client.OrasClient(hostname="ghcr.io", insecure=False)
```

And then ask for either a specific number of tags:

```python
tags = client.get_tags("channel-mirrors/conda-forge/linux-aarch64/arrow-cpp", N=1005)
```

Or more likely, just ask for all tags (the default).

```python
tags = client.get_tags("channel-mirrors/conda-forge/linux-aarch64/arrow-cpp")
```
You can read more about how registries provide tags [at the distribution spec](https://github.com/opencontainers/distribution-spec/blob/067a0f5b0e256583bb9a088f72cba85ed043d1d2/spec.md?plain=1#L471-L513).

### Push Interactions

Let's start with a very basic push interaction, and this one
follows [the example here](https://oras.land/docs/how_to_guides/pushing_and_pulling/#pushing-artifacts-with-single-file).

<details>

<summary>Example of basic push (click to expand)</summary>

We are assuming an `artifact.txt` in the present working directory.

```python
client = oras.client.OrasClient(insecure=True)
client.push(files=["artifact.txt"], target="localhost:5000/dinosaur/artifact:v1")
Successfully pushed localhost:5000/dinosaur/artifact:v1
Out[4]: <Response [201]>
```

</details>

This next example has a similar design to what the `oras.provider.Registry` provides,
but we are allowing better customization of content types and overriding
the default "push" function. This example maintains providing archives
as a lookup of paths and media types, and assumes annotations provided
conform to what the ORAS command line client expects (e.g., groups like `$config`).

<details>

<summary>Example of custom push (click to expand)</summary>

You might start with a custom lookup of archive paths and
media types. Let's say we start with this lookup, `archives`:

```python
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

Then here is how our registry client would look:

```python
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
            response = self.upload_blob(blob, container, layer)
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
        response = self.upload_blob(config_file, container, conf)
        self._check_200_response(response)

        # Final upload of the manifest
        manifest["config"] = conf
        self._check_200_response(self.upload_manifest(manifest, container))
        print(f"Successfully pushed {container}")
        return response
```

Note that the decorator `ensure_container` simply ensures that
the target you provide as the first argument is properly parsed for the
remainder of the function. And the only difference between the above and the provided provider is that
we are allowing more customization of the layers. The default oras
client just assumes you have either a single layer or a compressed
layer.


</details>

Here is another derivation of the first example (and example
usage) that allows you to specify a custom path (title), media type, and annotations
as a list of artifacts (I like this design better).


<details>

<summary>Example of custom push with more intuitive list (click to expand)</summary>

This example provides a courtesy function to create your client, and also shows
how to use `oras.utils.workdir` to ensure the upload is in context of your archive files.

```python
import os
import sys

import oras.defaults
import oras.oci
import oras.provider
from oras.decorator import ensure_container
import logging

logger = logging.getLogger(__name__)


def get_oras_client():
    """
    Consistent method to get an oras client
    """
    reg = Registry()
    if not reg.auth.username or not reg.auth.password:
        sys.exit("ORAS_USER or ORAS_PASS is missing, and required.")

    print("Found username and password for basic auth")
    return reg


class Registry(oras.provider.Registry):
    @ensure_container
    def push(self, container, archives: list):
        """
        Given a list of layer metadata (paths and corresponding mediaType) push.
        """
        # Prepare a new manifest
        manifest = oras.oci.NewManifest()

        # Upload files as blobs
        for item in archives:

            blob = item.get("path")
            media_type = (
                item.get("media_type") or "org.dinosaur.tool.datatype"
            )
            annots = item.get("annotations") or {}

            if not blob or not os.path.exists(blob):
                logger.warning(f"Path {blob} does not exist or is not defined.")
                continue

            # Artifact title is basename or user defined
            blob_name = item.get("title") or os.path.basename(blob)

            # If it's a directory, we need to compress
            cleanup_blob = False
            if os.path.isdir(blob):
                blob = oras.utils.make_targz(blob)
                cleanup_blob = True

            # Create a new layer from the blob
            layer = oras.oci.NewLayer(blob, media_type, is_dir=cleanup_blob)
            logger.debug(f"Preparing layer {layer}")

            # Update annotations with title we will need for extraction
            annots.update({oras.defaults.annotation_title: blob_name})
            layer["annotations"] = annots

            # update the manifest with the new layer
            manifest["layers"].append(layer)

            # Upload the blob layer
            logger.info(f"Uploading {blob} to {container.uri}")
            response = self.upload_blob(blob, container, layer)
            self._check_200_response(response)

            # Do we need to cleanup a temporary targz?
            if cleanup_blob and os.path.exists(blob):
                os.remove(blob)

        # Prepare manifest and config (add your custom annotations here)
        manifest["annotations"] = {}
        conf, config_file = oras.oci.ManifestConfig()
        conf["annotations"] = {}

        # Config is just another layer blob!
        response = self.upload_blob(config_file, container, conf)
        self._check_200_response(response)

        # Final upload of the manifest
        manifest["config"] = conf
        self._check_200_response(self.upload_manifest(manifest, container))
        print(f"Successfully pushed {container}")
        return response
```

And here is an example of how you might assemble your artifacts and use the
function above to get a client and push! 🎉️

```python
from datetime import datetime
import oras.utils

def push(uri, root):
    """
    Given an ORAS identifier, save artifacts to it.
    """
    oras_cli = get_oras_client()

    # Create lookup of archives - relative path and mediatype
    archives = []
    now = datetime.now()

    # Using os.listdir assumes we have single files at the base of our root.
    for filename in os.listdir(root):

        # use some logic here to derive the mediaType
        media_type = "org.dinosaur.tool.datatype"

        # Add some custom annotations!
        size = os.path.getsize(os.path.join(root, filename))  # bytes
        annotations = {"creationTime": str(now), "size": str(size)}
        archives.append(
            {
                "path": filename,
                "title": filename,
                "media_type": media_type,
                "annotations": annotations,
             }
         )

    # Push should be relative to cache context
    with oras.utils.workdir(root):
        oras_cli.push(uri, archives)
```

</details>

The above examples are just a start! See our [examples](https://github.com/oras-project/oras-py/tree/main/examples)
folder alongside the repository for more code examples and clients. If you would like help
for an example, or to contribute an example, [you know what to do](https://github.com/oras-project/oras-py/issues)!


### Pull Interactions

Pull is simpler than push, so here is a basic example. You might need to add authentication
here (discussed in the [next section](#authentication).

<details>

<summary>Example of basic pull (click to expand)</summary>


```python
res = client.pull(target="localhost:5000/dinosaur/artifact:v1")
['/tmp/oras-tmp.e5itvzfi/artifact.txt']
```

</details>

You can imagine having a custom function that will retrieve a manifest
or blob and do custom operations on it.

```python
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

Specifically the function `self.get_blob` will allow you to do that, or
`self.download_blob` for the streaming version. Let's now extend the clients
shown above for "pull" to add a download ability (pull):

<details>

<summary>Example of custom pull (click to expand)</summary>

This custom pull shows how we might retrieve an ORAS artifact that
has multiple layers, each a different content type that we might
want to selectively download.

```python
import os
import sys

import oras.defaults
import oras.oci
import oras.provider
import oras.utils
from oras.decorator import ensure_container
import logging

logger = logging.getLogger(__name__)


class Registry(oras.provider.Registry):

    @ensure_container
    def download_layers(self, download_dir, package, media_type):
        """
        Given a manifest of layers, retrieve a layer based on desired media type
        """
        # If you intend to call this function again, you might cache this response
        # for the package of interest.
        manifest = self.get_manifest(package)

        # Let's return a list of download paths to the user
        paths = []

        # Find the layer of interest! Currently we look for presence of the string
        # e.g., "prices" can come from "prices" or "prices-web"
        for layer in manifest.get('layers', []):

            # E.g., google.prices or google.prices-web or aws.prices
            if layer['mediaType'] == media_type:

                # This annotation is currently the practice for a relative path to extract to
                artifact = layer['annotations']['org.opencontainers.image.title']

                # This raises an error if there is a malicious path
                outfile = oras.utils.sanitize_path(download_dir, os.path.join(download_dir, artifact))

                # download blob ensures we stream, otherwise get_blob would return request
                # this function also handles creating the output directory if does not exist
                path = self.download_blob(package, layer['digest'], outfile)
                paths.append(path)

        return paths
```

</details>

You can get creative with the above - e.g., perhaps a layer has a json file that you first
get in memory using `get_blob` (to get the response object) and then do further parsing
of metadata before deciding to retrieve it. Note that as of oras-py 0.1.11 download_blob
is exposed as above. For earlier versions, you can use `self._download_blob`.

### Authentication

As of oras Python 0.2.0, authentication is handled with modules. We take this approach because
different registries have subtle different logic and it led to many errors.

By default, you will get a bearer token setup that takes an initial set of basic credentials and then makes
requests for tokens.  This is set by way of defining the "auth_backend" variable. For example,
here is asking for the default.

```python
import oras.client
client = oras.client.OrasClient(auth_backend="token")
client.login(password="myuser", username="myuser", insecure=True)
```

If you wanted to always maintain the basic auth you might do:

```python
import oras.client
client = oras.client.OrasClient(auth_backend="basic")
client.login(password="myuser", username="myuser", insecure=True)
```

Here is a very basic example of logging in and out of a registry using the default (basic)
provided client:

<details>

<summary>Example using basic auth (click to expand)</summary>


```python
import oras.client
client = oras.client.OrasClient(hostname="ghcr.io")
client.login(password="myuser", username="myuser")
```

And logout!

```python
client.logout("localhost:5000")
```

</details>

### Debugging

> Can I see more debug information?

Yes! Try using setup_logger with debug set to true:

```
from oras.logger import setup_logger, logger
setup_logger(quiet=False, debug=True)
logger.debug('This is my debug message!')
```

More verbose output should appear.


> I get unauthorized when trying to login to an Amazon ECR Registry

Note that for [Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html)
you might need to login per the instructions at the link provided. If you look at your `~/.docker/config.json` and see
that there is a "credsStore" section that is populated, you might also need to comment this out
while using oras-py. Oras-py currently doesn't support reading external credential stores, so you will
need to comment it out, login again, and then try your request. To sanity check that you've done
this correctly, you should see an "auth" key under a hostname under "auths" in this file with a base64
encoded string (this is actually your username and password!) An empty dictionary there indicates that you
are using a helper. Finally, it would be cool if we supported these external stores! If you
want to contribute this or help think about how to do it, @vsoch would be happy to help.



## Custom Clients

The benefit of Oras Python is that you can create a subclass that easily implements
a registry, and then allows you to do custom interactions. In addition to the starter
examples above, we provide a directory of [examples](https://github.com/oras-project/oras-py/tree/main/examples)
that you can start from. Please [let us know](https://github.com/oras-project/oras-py/issues)
if you need help with your custom client, or would like to request a custom example.

See the [Developer Guide](developer-guide.md) for development tasks like running tests
and working on these docs!
