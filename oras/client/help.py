#!/usr/bin/env python

__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MIT"

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
