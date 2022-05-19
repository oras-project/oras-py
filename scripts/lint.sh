#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../

black --check oras

for filename in $(find . -name "*.py" -not -path "*__init__.py"); do
    pyflakes $filename
done

