This oci-layout was realized by first creating a simple "artifact" using container engine:

```sh
podman manifest rm quay.io/mmortari/oci-image-from-scratch-like-artifact:multiarch
podman manifest create quay.io/mmortari/oci-image-from-scratch-like-artifact:multiarch
podman build --format=oci --platform linux/amd64 -f Dockerfile . --manifest quay.io/mmortari/oci-image-from-scratch-like-artifact:multiarch
podman build --format=oci --platform linux/arm64 -f Dockerfile . --manifest quay.io/mmortari/oci-image-from-scratch-like-artifact:multiarch
podman manifest push quay.io/mmortari/oci-image-from-scratch-like-artifact:multiarch
podman manifest rm quay.io/mmortari/oci-image-from-scratch-like-artifact:multiarch
```

and then transfering from OCI registry to oci-layout:

```sh
skopeo copy --preserve-digests --multi-arch all docker://quay.io/mmortari/oci-image-from-scratch-like-artifact:multiarch oci:oras/tests/ocilayout_data/ocilayout2:latest
```

resulting in an OCI layout that:
- mimics both an OCI Image and an Artifact
- mimics a multi-arch oci-layout (OCI Image Index -> 2 OCI Image Manifest for Arm and Amd)
- the OCI Image Manifests also instrumentally share a layer (blob)

which can be used conveniently for oci-layout testing, especially use-cases of layer de-dups and presence of OCI Image Index manifest.
