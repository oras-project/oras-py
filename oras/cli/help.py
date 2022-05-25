__author__ = "Vanessa Sochat"
__copyright__ = "Copyright The ORAS Authors."
__license__ = "Apache-2.0"

login_help = """
Log in to a remote registry

Example - Login with username and password from command line:
  oras-py login -u username -p password localhost:5000
Example - Login with username and password from stdin:
  oras-py login -u username --password-stdin localhost:5000
Example - Login with identity token from command line:
  oras-py login -p token localhost:5000
Example - Login with identity token from stdin:
  oras-py login --password-stdin localhost:5000
Example - Login with username and password by prompt:
  oras-py login localhost:5000
Example - Login with insecure registry from command line:
  oras-py login --insecure localhost:5000
"""

copy_help = """Copy artifacts from one location to another",

Example - Copy artifacts from local files to local files:
  oras copy foo/bar:v1 --from files --to files:path/to/save file1 file2 ... filen
Example - Copy artifacts from registry to local files:
  oras copy foo/bar:v1 --from registry --to files:path/to/save
Example - Copy artifacts from registry to oci:
  oras copy foo/bar:v1 --from registry --to oci:path/to/oci
Example - Copy artifacts from local files to registry:
  oras copy foo/bar:v1 --from files --to registry file1 file2 ... filen
When the source (--from) is "files", the config by default will be "{}" and of media type
application/vnd.unknown.config.v1+json. You can override it by setting the path, for example:
  oras copy foo/bar:v1 --from files --manifest-config path/to/config:application/vnd.oci.image.config.v1+json --to files:path/to/save file1 file2 ... fileN"""


logout_help = """
Log out from a remote registry

Example - Logout:
  oras-py logout localhost:5000
"""

push_help = """
Push files to remote registry

Example - Push file "hi.txt" with the "application/vnd.oci.image.layer.v1.tar" media type (default):
  oras-py push localhost:5000/hello:latest hi.txt
Example - Push file "hi.txt" with the custom "application/vnd.me.hi" media type:
  oras-py push localhost:5000/hello:latest hi.txt:application/vnd.me.hi
Example - Push multiple files with different media types:
  oras-py push localhost:5000/hello:latest hi.txt:application/vnd.me.hi bye.txt:application/vnd.me.bye
Example - Push file "hi.txt" with the custom manifest config "config.json" of the custom "application/vnd.me.config" media type:
  oras-py push --manifest-config config.json:application/vnd.me.config localhost:5000/hello:latest hi.txt
Example - Push file to the insecure registry:
  oras-py push localhost:5000/hello:latest hi.txt --insecure
Example - Push file to the HTTP registry:
  oras-py push localhost:5000/hello:latest hi.txt --plain-http
"""
