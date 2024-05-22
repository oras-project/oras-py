import pytest

import oras.defaults
import oras.oci


@pytest.mark.with_auth(False)
def test_create_subject_from_manifest():
    """
    Basic tests for oras Subject creation from empty manifest
    """
    manifest = oras.oci.NewManifest()
    subject = oras.oci.Subject.from_manifest(manifest)

    assert subject.mediaType == oras.defaults.default_manifest_media_type
    assert (
        subject.digest
        == "sha256:7a6f84d8c73a71bf9417c13f721ed102f74afac9e481f89e5a72d28954e7d0c5"
    )
    assert subject.size == 126
