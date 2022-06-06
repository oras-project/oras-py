.. _getting_started-user-guide:

==========
User Guide
==========

Oras Python will allow you to run traditional push and pull commands for artifacts,
or generate a custom client. This small user guide will walk you through these various
steps, and please open an issue if functionality is missing. If you haven't read 
:ref:`getting_started-installation` you should do that first.


Registry
========

You should see `supported registries <https://oras.land/implementors/#docker-distribution>`_, or if you
want to deploy a local testing registry (without auth), you can do:

.. code-block:: console

    $ docker run -it --rm -p 5000:5000 ghcr.io/oras-project/registry:latest


To test token authentication, you can either `set up your own auth server <https://github.com/adigunhammedolalekan/registry-auth>`_
or just use an actual registry. The most we can do here is set up an example that uses basic auth.

.. code-block:: console

    # This is an htpassword file, "b" means bcrypt
    htpasswd -cB -b auth.htpasswd myuser mypass


.. warning::

    The server below will work to login with basic auth, but you won't be able to issue tokens.


.. code-block:: console

    # And start the registry with authentication
    docker run -it --rm -p 5000:5000 \
        -v $(pwd)/auth.htpasswd:/etc/docker/registry/auth.htpasswd \
        -e REGISTRY_AUTH="{htpasswd: {realm: localhost, path: /etc/docker/registry/auth.htpasswd}}" \
        ghcr.io/oras-project/registry:latest


Command Line
============

Login
-----

Once you create (or already have) a registry, you will want to login. You can do:

.. code-block:: console

    $ oras-py login -u myuser -p mypass localhost:5000

    # or localhost (insecure)
    $ oras-py login -u myuser -p mypass -k localhost:5000 --insecure

    WARNING! Using --password via the CLI is insecure. Use --password-stdin.
    Login Succeeded

You can also provide them interactively

        
.. code-block:: console
   
    $ oras-py login -k localhost:5000 --insecure
    Username: myuser
    Password: mypass
    Login Succeeded


or use ``--password-stdin``

.. code-block:: console

    $ echo mypass | oras-py login -u myuser -k localhost:5000 --insecure --password-stdin
    Login Succeeded


Note that oras-py will not remove content from your docker config files, so
there is no concept of a "logout" unless you are using the client interactively,
and have configs loaded, then you can do:

.. code-block:: console

    $ cli.logout(hostname)


Push
----

Let's first push a container. Let's follow `the example here <https://oras.land/cli/1_pushing/>`_.

.. code-block:: console

    echo "hello dinosaur" > artifact.txt
    $ oras-py push localhost:5000/dinosaur/artifact:v1 \
    --manifest-config /dev/null:application/vnd.acme.rocket.config \
    ./artifact.txt
    Successfully pushed localhost:5000/dinosaur/artifact:v1


And if you aren't using https, add ``--insecure``


.. code-block:: console

    $ oras-py push localhost:5000/dinosaur/artifact:v1 --insecure \
    --manifest-config /dev/null:application/vnd.acme.rocket.config \
    ./artifact.txt
    Successfully pushed localhost:5000/dinosaur/artifact:v1


Pull
----

Now try a pull! We will first need to delete the file

.. code-block:: console

    $ rm -f artifact.txt # first delete the file
    $ oras-py pull localhost:5000/dinosaur/artifact:v1
    $ cat artifact.txt
    hello dinosaur


Within Python
=============

If you want to use the library from within Python, here is how to do that.
You'll still need a running registry as shown above. As a trick, if you want
more detail than is available in these docs, you can peek into the
`Python client code <https://github.com/oras-project/oras-py/tree/main/oras/cli>`_.

Login and Logout
----------------

.. code-block:: python

    import oras.client
    client = oras.client.OrasClient()
    client.login(password="myuser", username="myuser", insecure=True)


And logout!
        
.. code-block:: console

    client.logout("localhost:5000")   


Push and Pull
-------------

We are again following `the example here <https://oras.land/cli/1_pushing/>`_.
We are assuming an ``artifact.txt`` in the present working directory.

.. code-block:: console
    
    client = oras.client.OrasClient(insecure=True)
    client.push(files=["artifact.txt"], target="localhost:5000/dinosaur/artifact:v1")
    Successfully pushed localhost:5000/dinosaur/artifact:v1
    Out[4]: <Response [201]>


And then pull!

.. code-block:: console

    res = client.pull(target="localhost:5000/dinosaur/artifact:v1")
    ['/tmp/oras-tmp.e5itvzfi/artifact.txt']



Custom Clients
==============

The benefit of Oras Python is that you can create a subclass that easily implements
a registry, and then allows you to do custom interactions. We provide a few examples:

 - `Conda Mirror <https://github.com/oras-project/oras-py/blob/main/examples/conda-mirror.py>`_: an example to parse custom layers to retrieve metadata index.jsons (and archive) along with a binary to download.
