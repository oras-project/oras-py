#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../

black --check oras

for filename in $(find . -name "*.py" -not -path "*__init__.py" -not -path "./env/*"); do
    pyflakes $filename
done

# mypy checks typing
mypy oras

# isort (import order)
isort --check-only *.py oras
