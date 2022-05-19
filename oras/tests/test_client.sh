#!/bin/bash

here="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# ORAS_REGISTRY needs to be defined (and running)
if [ -z ${ORAS_REGISTRY+x} ]; then
   printf "ORAS_REGISTRY needs to be defined\n"
   exit 1
fi

printf "ORAS_REGISTRY found as ${ORAS_REGISTRY}\n"

runTest() {

    # The first argument is the code we should get
    ERROR="${1:-}"
    shift
    OUTPUT=${1:-}
    shift
    echo "$@"

    "$@" > "${OUTPUT}" 2>&1
    RETVAL="$?"

    if [ "$ERROR" = "0" -a "$RETVAL" != "0" ]; then
        echo "$@ (retval=$RETVAL) ERROR"
        cat ${OUTPUT}
        echo "Output in ${OUTPUT}"
        exit 1
    elif [ "$ERROR" != "0" -a "$RETVAL" = "0" ]; then
        echo "$@ (retval=$RETVAL) ERROR"
        echo "Output in ${OUTPUT}"
        cat ${OUTPUT}
        exit 1
    else
        echo "$@ (retval=$RETVAL) OK"
    fi
}

# The artifact file
artifact=$here/artifact.txt

# Create temporary testing directory
tmpdir=$(mktemp -d)
output=$(mktemp ${tmpdir:-/tmp}/shpc_test.XXXXXX)
printf "Created temporary directory to work in. ${tmpdir}\n"

# Make sure it's installed
if ! command -v oras-py &> /dev/null
then
    printf "oras-py is not installed\n"
    exit 1
else
    printf "oras-py is installed\n"
fi

echo
echo "#### Testing help "
runTest 0 $output oras-py --help

echo
echo "#### Testing push "
runTest 0 $output oras-py push --help
runTest 0 $output oras-py push ${ORAS_REGISTRY}/dinosaur/artifact:v1 --insecure --manifest-config /dev/null:application/vnd.acme.rocket.config ${artifact}

echo
echo "#### Testing pull "
runTest 0 $output oras-py pull --help
runTest 0 $output oras-py pull ${ORAS_REGISTRY}/dinosaur/artifact:v1 --insecure --output $tmpdir/
runTest 0 $output test -f "$tmpdir/artifact.txt"

rm -rf ${tmpdir}
