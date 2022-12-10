#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../

# Ensure envars are defined - expected registry port and host
export ORAS_PORT=5000
export ORAS_HOST=localhost
export ORAS_REGISTRY=${ORAS_HOST}:${ORAS_PORT}
export ORAS_USER=myuser
export ORAS_PASS=mypass

if [ ! -z ${with_auth} ]; then
    export ORAS_AUTH=true
fi

printf "ORAS_PORT: ${ORAS_PORT}\n"
printf "ORAS_HOST: ${ORAS_HOST}\n"
printf "ORAS_REGISTRY: ${ORAS_REGISTRY}\n"
printf "ORAS_AUTH: ${ORAS_AUTH}\n"

# Client (command line) tests
pytest oras/
