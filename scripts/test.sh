#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../

# Ensure envars are defined - expected registry port and host
export ORAS_PORT=5000
export ORAS_HOST=localhost
export ORAS_REGISTRY=${ORAS_HOST}:${ORAS_PORT}

printf "ORAS_PORT: ${ORAS_PORT}\n"
printf "ORAS_HOST: ${ORAS_HOST}\n"
printf "ORAS_REGISTRY: ${ORAS_REGISTRY}\n"

# Client (command line) tests
/bin/bash oras/tests/test_client.sh
