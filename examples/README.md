# Oras Python SDK Examples

The directory here has the following examples:

## Local Examples

 - [simple](simple): simple examples for individual commands adopted from oras-py [before the client was removed](https://github.com/oras-project/oras-py/tree/3b4e6d74d49b8c6a5d8180e646d52fcc50b3508a).
 - [conda-mirror.py](conda-mirror.py): upload to a conda mirror with ORAS with a manifest and custom content types.
 - [follow-image-index.py](follow-image-index.py): Download a homebrew image index and select a platform-specific image.

## In the Wild Examples

The following examples are found in other projects! If you have used oras in
your project, we encourage you to add it to the list here.

 - **cloud-select**: this tool [creates a list of custom layers](https://github.com/converged-computing/cloud-select/blob/main/cloud_select/main/cache.py#L81-L107) and content types to store via ORAS and a [custom client](https://github.com/converged-computing/cloud-select/blob/db02c4378f06bfbbe9df6b8a83c885cc9238a04e/cloud_select/main/cache.py#L81).
 - **pakages**: uses a [custom client](https://github.com/syspack/pakages/blob/main/pakages/oras.py) to store Spack or pypi (or other artifacts) in GitHub packages.


Know a project that uses the ORAS Python SDK and want to add to this list?
Please open a pull request or [let us know](https://github.com/oras-project/oras-py/issues).
