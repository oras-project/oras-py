.. _getting_started-developer-guide:

===============
Developer Guide
===============

This developer guide includes more complex interactions like contributing
registry entries and building containers. If you haven't read :ref:`getting_started-installation`
you should do that first.


Creating a Custom Client
========================

If you want to create your own client, you likely want to:

1. Subclass the ``oras.provider.Registry`` class
2. Add custom functions to push, pull, or create manifests / layers
3. Provide authentication, if required.

The Registry Client
-------------------

Your most basic registry (that will mimic the default can be created like this:

.. code-block:: python

    import oras.provider

    class MyProvider(oras.provider.Registry):
        pass


Interactions
------------

You can imagine having a custom function that will retrieve a manifest or blob
and do custom operations on it.


.. code-block:: python


    def inspect(self, name):

        # Parse the name into a container
        container = self.get_container(name)

        # Get the manifest with the three layers
        manifest = self.get_manifest(container)

        # Organize layers based on media_types
        layers = self._organize_layers(manifest)

        # Read info.json media type, find correct blob...
        # download correct blob, etc.

Specifically the function ``self.get_blob`` will allow you to do that.

Instantiate
-----------

Some registries may require authentiation:

.. code-block:: python

    # We will need GitHub personal access token or token
    token = os.environ.get("GITHUB_TOKEN")
    user = os.environ.get("GITHUB_USER")

    if not token or not user:
        sys.exit("GITHUB_TOKEN and GITHUB_USER are required in the environment.")


And then you can run your custom functions after doing that.


.. code-block:: python

    def main():
        reg = MyProvider()
        reg.set_basic_auth(user, token)
        reg.inspect("ghcr.io/wolfv/conda-forge/linux-64/xtensor:0.9.0-0")


