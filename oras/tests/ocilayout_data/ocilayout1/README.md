This oci-layout was realized by first creating a simple "artifact" using container engine:

```sh
podman build --format=oci -f Dockerfile . -t quay.io/mmortari/oci-image-from-scratch-like-artifact:singlearch
podman push quay.io/mmortari/oci-image-from-scratch-like-artifact:singlearch
```

and then transfering from OCI registry to oci-layout:

```sh
skopeo copy --preserve-digests --multi-arch all docker://quay.io/mmortari/oci-image-from-scratch-like-artifact:singlearch oci:oras/tests/ocilayout_data/ocilayout1:latest
```

resulting in an OCI layout that mimics both an OCI Image and an Artifact, which can be used conveniently for oci-layout testing.
