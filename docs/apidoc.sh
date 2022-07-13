#!/bin/bash
# If the modules changed, the content of "source" should be backed up and
# new files generated (to update) by doing:
#
# 
rm source/oras*.rst
sphinx-apidoc -o source/ ../oras
