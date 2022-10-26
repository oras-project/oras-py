#!/bin/bash

# This script performs linting, and was used before pre-commit was added 10/25.
# It is included in case we want to use it in another context.

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../

black --check oras

for filename in $(find . -name "*.py" -not -path "./docs/*" -not -path "*__init__.py" -not -path "./env/*"); do
    pyflakes $filename
done

# mypy checks typing
mypy oras examples

# isort (import order)
isort --skip oras/utils/__init__.py --check-only *.py oras examples
