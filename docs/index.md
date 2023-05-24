# Oras Python

![Oras Python Logo](https://github.com/oras-project/oras-www/blob/main/static/img/oras.png)

Welcome to Oras Python!

OCI Registry as Storage enables client libraries to push OCI Artifacts
to [OCI Conformant](https://github.com/opencontainers/oci-conformance)
registries. This is a Python SDK for that.

```console
# Install the client
$ pip install oras
```

And then within Python:

```python
# Create a basic client
import oras.client
client = oras.client.OrasClient()
client.login(password="myuser", username="myuser")

# Push
client.push(files=["artifact.txt"], target="ghcr.io/avocados/dinosaur/artifact:v1")
Successfully pushed ghcr.io/avocados/dinosaur/artifact:v1
Out[4]: <Response [201]>

# Pull
res = client.pull(target="localhost:5000/dinosaur/artifact:v1")
['/tmp/oras-tmp.e5itvzfi/artifact.txt']
```

To get started, see the links below. Would you like to
request a feature or contribute? [Open an issue](https://github.com/oras-project/oras-py/issues).

```{toctree}
:maxdepth: 2
getting_started/index.md
contributing.md
about/license
```

```{toctree}
:caption: API
:maxdepth: 1
source/modules.rst
```
