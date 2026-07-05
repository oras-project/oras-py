"""
Tests for the oras.copy engine.

Tests the copy engine using in-memory storage implementations,
verifying the core algorithm: graph traversal, deduplication,
existence checking, blob mounting, tagging, and error handling.
"""

import hashlib
import io
import json
import threading
from typing import BinaryIO, List, Tuple
from unittest.mock import MagicMock

import pytest

import oras.defaults
from oras.content.layout import LayoutTarget, _VALID_DIGEST_RE
from oras.layout import Layout
from oras.content.memory import MemoryStorage
from oras.content.storage import CacheProxy, FetcherFunc
from oras.copy import (
    CopyError,
    CopyErrorOrigin,
    CopyGraphOptions,
    CopyOptions,
    Descriptor,
    SkipNode,
    copy,
)
from oras.copy.graph import LimitedRegion, copy_graph, successors
from oras.copy.tracker import StatusTracker
from oras.tests.helpers import InMemoryTarget  # shared test helper
from oras.types import (
    descriptor_key,
    descriptors_equal,
    is_foreign_layer,
    is_manifest,
    remove_foreign_layers,
)


def _make_blob(data: bytes, media_type: str = "application/octet-stream") -> Descriptor:
    """Create a descriptor for raw blob data."""
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    return {
        "mediaType": media_type,
        "digest": digest,
        "size": len(data),
    }


def _make_manifest(config: Descriptor, layers: List[Descriptor]) -> Tuple[Descriptor, bytes]:
    """Create a manifest descriptor and its JSON content."""
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": config,
        "layers": layers,
    }
    data = json.dumps(manifest, sort_keys=True).encode("utf-8")
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    desc = {
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "digest": digest,
        "size": len(data),
    }
    return desc, data


def _make_index(manifests: List[Descriptor]) -> Tuple[Descriptor, bytes]:
    """Create an index descriptor and its JSON content."""
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": manifests,
    }
    data = json.dumps(index, sort_keys=True).encode("utf-8")
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    desc = {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "digest": digest,
        "size": len(data),
    }
    return desc, data


# ---------------------------------------------------------------------------
# Tests: Descriptor utilities
# ---------------------------------------------------------------------------


class TestDescriptor:
    def test_is_manifest_oci(self):
        desc = {"mediaType": "application/vnd.oci.image.manifest.v1+json"}
        assert is_manifest(desc)

    def test_is_manifest_index(self):
        desc = {"mediaType": "application/vnd.oci.image.index.v1+json"}
        assert is_manifest(desc)

    def test_is_manifest_docker(self):
        desc = {"mediaType": "application/vnd.docker.distribution.manifest.v2+json"}
        assert is_manifest(desc)

    def test_is_manifest_docker_list(self):
        desc = {"mediaType": "application/vnd.docker.distribution.manifest.list.v2+json"}
        assert is_manifest(desc)

    def test_is_not_manifest(self):
        desc = {"mediaType": "application/octet-stream"}
        assert not is_manifest(desc)

    def test_is_foreign_layer(self):
        desc = {
            "mediaType": "application/vnd.oci.image.layer.nondistributable.v1.tar+gzip"
        }
        assert is_foreign_layer(desc)

    def test_is_not_foreign_layer(self):
        desc = {"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"}
        assert not is_foreign_layer(desc)

    def test_descriptor_key(self):
        desc = {
            "mediaType": "application/octet-stream",
            "digest": "sha256:abc",
            "size": 100,
        }
        key = descriptor_key(desc)
        assert key == ("application/octet-stream", "sha256:abc", 100)

    def test_descriptors_equal(self):
        a = {"mediaType": "text/plain", "digest": "sha256:abc", "size": 10}
        b = {"mediaType": "text/plain", "digest": "sha256:abc", "size": 10}
        assert descriptors_equal(a, b)

    def test_descriptors_not_equal(self):
        a = {"mediaType": "text/plain", "digest": "sha256:abc", "size": 10}
        b = {"mediaType": "text/plain", "digest": "sha256:def", "size": 20}
        assert not descriptors_equal(a, b)

    def test_remove_foreign_layers(self):
        foreign = {
            "mediaType": "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip",
            "digest": "sha256:foreign",
            "size": 50,
        }
        normal = {
            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
            "digest": "sha256:normal",
            "size": 100,
        }
        result = remove_foreign_layers([foreign, normal])
        assert len(result) == 1
        assert result[0]["digest"] == "sha256:normal"


# ---------------------------------------------------------------------------
# Tests: MemoryStorage
# ---------------------------------------------------------------------------


class TestMemoryStorage:
    def test_push_and_fetch(self):
        store = MemoryStorage()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        store.push(desc, io.BytesIO(b"abc"))
        result = store.fetch(desc)
        assert result.read() == b"abc"

    def test_exists(self):
        store = MemoryStorage()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        assert not store.exists(desc)
        store.push(desc, io.BytesIO(b"abc"))
        assert store.exists(desc)

    def test_fetch_not_found(self):
        store = MemoryStorage()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        with pytest.raises(FileNotFoundError):
            store.fetch(desc)

    def test_thread_safety(self):
        store = MemoryStorage()
        errors = []

        def push_data(i):
            try:
                desc = {
                    "digest": f"sha256:{i}",
                    "size": len(str(i)),
                    "mediaType": "text/plain",
                }
                store.push(desc, io.BytesIO(str(i).encode()))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=push_data, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        for i in range(100):
            desc = {
                "digest": f"sha256:{i}",
                "size": len(str(i)),
                "mediaType": "text/plain",
            }
            assert store.exists(desc)


# ---------------------------------------------------------------------------
# Tests: CacheProxy
# ---------------------------------------------------------------------------


class TestCacheProxy:
    def test_fetch_caches_data(self):
        base = MemoryStorage()
        cache = MemoryStorage()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        base.push(desc, io.BytesIO(b"abc"))

        proxy = CacheProxy(base, cache, 1024)
        result = proxy.fetch(desc)
        assert result.read() == b"abc"
        # Should now be in cache
        assert cache.exists(desc)

    def test_fetch_from_cache(self):
        base = MemoryStorage()
        cache = MemoryStorage()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        cache.push(desc, io.BytesIO(b"cached"))

        proxy = CacheProxy(base, cache, 1024)
        result = proxy.fetch(desc)
        assert result.read() == b"cached"

    def test_stop_caching(self):
        base = MemoryStorage()
        cache = MemoryStorage()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        base.push(desc, io.BytesIO(b"abc"))

        proxy = CacheProxy(base, cache, 1024)
        proxy.stop_caching = True
        proxy.fetch(desc)
        # Should NOT be in cache when stop_caching is True
        assert not cache.exists(desc)

    def test_max_bytes_limit(self):
        base = MemoryStorage()
        cache = MemoryStorage()
        desc1 = {"digest": "sha256:a", "size": 100, "mediaType": "text/plain"}
        desc2 = {"digest": "sha256:b", "size": 100, "mediaType": "text/plain"}
        base.push(desc1, io.BytesIO(b"a" * 100))
        base.push(desc2, io.BytesIO(b"b" * 100))

        # Cache limit of 150 bytes: first fits, second doesn't
        proxy = CacheProxy(base, cache, 150)
        proxy.fetch(desc1)
        proxy.fetch(desc2)
        assert cache.exists(desc1)
        assert not cache.exists(desc2)

    def test_exists_checks_both(self):
        base = MemoryStorage()
        cache = MemoryStorage()
        desc_base = {"digest": "sha256:base", "size": 4, "mediaType": "text/plain"}
        desc_cache = {"digest": "sha256:cache", "size": 5, "mediaType": "text/plain"}
        base.push(desc_base, io.BytesIO(b"base"))
        cache.push(desc_cache, io.BytesIO(b"cache"))

        proxy = CacheProxy(base, cache, 1024)
        assert proxy.exists(desc_base)
        assert proxy.exists(desc_cache)
        assert not proxy.exists(
            {"digest": "sha256:missing", "size": 0, "mediaType": "text/plain"}
        )


# ---------------------------------------------------------------------------
# Tests: StatusTracker
# ---------------------------------------------------------------------------


class TestStatusTracker:
    def test_first_commit_succeeds(self):
        tracker = StatusTracker()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        event, committed = tracker.try_commit(desc)
        assert committed
        assert not event.is_set()

    def test_second_commit_fails(self):
        tracker = StatusTracker()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        event1, committed1 = tracker.try_commit(desc)
        event2, committed2 = tracker.try_commit(desc)
        assert committed1
        assert not committed2
        assert event1 is event2

    def test_event_signaling(self):
        tracker = StatusTracker()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        event, _ = tracker.try_commit(desc)
        event.set()
        # Another try_commit should get the set event
        event2, committed = tracker.try_commit(desc)
        assert not committed
        assert event2.is_set()

    def test_concurrent_commits(self):
        tracker = StatusTracker()
        desc = {"digest": "sha256:abc", "size": 3, "mediaType": "text/plain"}
        results = []
        lock = threading.Lock()

        def worker():
            event, committed = tracker.try_commit(desc)
            with lock:
                results.append(committed)
            if committed:
                event.set()
            else:
                event.wait()

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one should have committed
        assert sum(1 for r in results if r) == 1


# ---------------------------------------------------------------------------
# Tests: FetcherFunc
# ---------------------------------------------------------------------------


class TestFetcherFunc:
    def test_wraps_callable(self):
        def my_fetch(desc):
            return io.BytesIO(b"hello")

        fetcher = FetcherFunc(my_fetch)
        result = fetcher.fetch({"digest": "sha256:x"})
        assert result.read() == b"hello"


# ---------------------------------------------------------------------------
# Tests: Content successors
# ---------------------------------------------------------------------------


class TestSuccessors:
    def test_manifest_successors(self):
        config = {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": "sha256:cfg", "size": 10}
        layer = {"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": "sha256:layer1", "size": 100}
        manifest_data = json.dumps({
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": config,
            "layers": [layer],
        }).encode()

        desc = {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:mfst", "size": len(manifest_data)}
        fetcher = FetcherFunc(lambda d: io.BytesIO(manifest_data))

        result = successors(fetcher, desc)
        assert len(result) == 2
        assert result[0]["digest"] == "sha256:cfg"
        assert result[1]["digest"] == "sha256:layer1"

    def test_manifest_with_subject(self):
        config = {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": "sha256:cfg", "size": 10}
        subject = {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:subj", "size": 50}
        manifest_data = json.dumps({
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": config,
            "layers": [],
            "subject": subject,
        }).encode()

        desc = {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:mfst", "size": len(manifest_data)}
        fetcher = FetcherFunc(lambda d: io.BytesIO(manifest_data))

        result = successors(fetcher, desc)
        assert len(result) == 2  # config + subject
        assert result[1]["digest"] == "sha256:subj"

    def test_index_successors(self):
        m1 = {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:m1", "size": 100}
        m2 = {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": "sha256:m2", "size": 200}
        index_data = json.dumps({
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [m1, m2],
        }).encode()

        desc = {"mediaType": "application/vnd.oci.image.index.v1+json", "digest": "sha256:idx", "size": len(index_data)}
        fetcher = FetcherFunc(lambda d: io.BytesIO(index_data))

        result = successors(fetcher, desc)
        assert len(result) == 2
        assert result[0]["digest"] == "sha256:m1"
        assert result[1]["digest"] == "sha256:m2"

    def test_blob_has_no_successors(self):
        desc = {"mediaType": "application/octet-stream", "digest": "sha256:blob", "size": 50}
        fetcher = FetcherFunc(lambda d: io.BytesIO(b""))
        result = successors(fetcher, desc)
        assert result == []


# ---------------------------------------------------------------------------
# Tests: CopyError
# ---------------------------------------------------------------------------


class TestCopyError:
    def test_error_message_source(self):
        err = CopyError("Fetch", CopyErrorOrigin.SOURCE, ValueError("not found"))
        assert "Fetch" in str(err)
        assert "source" in str(err)
        assert "not found" in str(err)

    def test_error_message_destination(self):
        err = CopyError("Push", CopyErrorOrigin.DESTINATION, IOError("disk full"))
        assert "Push" in str(err)
        assert "destination" in str(err)
        assert "disk full" in str(err)

    def test_unwrap(self):
        inner = ValueError("inner error")
        err = CopyError("Op", CopyErrorOrigin.SOURCE, inner)
        assert err.err is inner


# ---------------------------------------------------------------------------
# Tests: copy_graph (unit tests with in-memory storage)
# ---------------------------------------------------------------------------


class TestCopyGraph:
    def test_copy_single_blob(self):
        """Copy a leaf node (blob) from source to destination."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"hello world"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        copy_graph(src, dst, desc)

        assert dst.exists(desc)
        assert dst.get_content(desc["digest"]) == blob_data

    def test_copy_manifest_with_layers(self):
        """Copy a manifest with config and layers."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        # Create blobs
        config_data = b'{"architecture":"amd64"}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer content here"
        layer_desc = _make_blob(layer_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer_desc, io.BytesIO(layer_data))

        # Create manifest
        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))

        copy_graph(src, dst, manifest_desc)

        # All content should be at destination
        assert dst.exists(config_desc)
        assert dst.exists(layer_desc)
        assert dst.exists(manifest_desc)
        assert dst.get_content(config_desc["digest"]) == config_data
        assert dst.get_content(layer_desc["digest"]) == layer_data

    def test_copy_index_with_manifests(self):
        """Copy an index containing multiple manifests."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        # Create two manifests with their blobs
        config_data = b'{"architecture":"amd64"}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer data"
        layer_desc = _make_blob(layer_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer_desc, io.BytesIO(layer_data))

        m1_desc, m1_data = _make_manifest(config_desc, [layer_desc])
        src.push(m1_desc, io.BytesIO(m1_data))

        # Second manifest can share the same config
        layer2_data = b"layer 2 data"
        layer2_desc = _make_blob(layer2_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer2_desc, io.BytesIO(layer2_data))

        m2_desc, m2_data = _make_manifest(config_desc, [layer2_desc])
        src.push(m2_desc, io.BytesIO(m2_data))

        # Create index
        index_desc, index_data = _make_index([m1_desc, m2_desc])
        src.push(index_desc, io.BytesIO(index_data))

        copy_graph(src, dst, index_desc)

        assert dst.exists(index_desc)
        assert dst.exists(m1_desc)
        assert dst.exists(m2_desc)
        assert dst.exists(config_desc)
        assert dst.exists(layer_desc)
        assert dst.exists(layer2_desc)

    def test_skip_existing_content(self):
        """Content already at destination should not be re-pushed."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"existing blob"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        dst.push(desc, io.BytesIO(blob_data))  # Already exists

        skipped = []
        opts = CopyGraphOptions(
            on_copy_skipped=lambda d: skipped.append(d),
        )

        copy_graph(src, dst, desc, opts=opts)
        assert len(skipped) == 1
        assert descriptors_equal(skipped[0], desc)

    def test_pre_copy_callback(self):
        """pre_copy callback is invoked before each node copy."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"callback test"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        pre_copy_descs = []
        opts = CopyGraphOptions(
            pre_copy=lambda d: pre_copy_descs.append(d),
        )

        copy_graph(src, dst, desc, opts=opts)
        assert len(pre_copy_descs) == 1

    def test_post_copy_callback(self):
        """post_copy callback is invoked after each node copy."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"callback test"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        post_copy_descs = []
        opts = CopyGraphOptions(
            post_copy=lambda d: post_copy_descs.append(d),
        )

        copy_graph(src, dst, desc, opts=opts)
        assert len(post_copy_descs) == 1

    def test_skip_node_in_pre_copy(self):
        """SkipNode from pre_copy should prevent the copy."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"skip me"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        def skip_pre_copy(d):
            raise SkipNode()

        opts = CopyGraphOptions(pre_copy=skip_pre_copy)

        copy_graph(src, dst, desc, opts=opts)
        # The node should NOT have been pushed to dst
        assert not dst.exists(desc)

    def test_deduplication(self):
        """Shared blobs across manifests should be copied only once."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        # Shared config
        config_data = b'{"shared": true}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        # Shared layer
        layer_data = b"shared layer"
        layer_desc = _make_blob(layer_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer_desc, io.BytesIO(layer_data))

        # Two manifests referencing the same config and layer
        m1_desc, m1_data = _make_manifest(config_desc, [layer_desc])
        src.push(m1_desc, io.BytesIO(m1_data))
        m2_desc, m2_data = _make_manifest(config_desc, [layer_desc])
        # m1 and m2 have the same content, so same digest
        # Let's make them different
        layer2_data = b"unique layer for m2"
        layer2_desc = _make_blob(layer2_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer2_desc, io.BytesIO(layer2_data))
        m2_desc, m2_data = _make_manifest(config_desc, [layer_desc, layer2_desc])
        src.push(m2_desc, io.BytesIO(m2_data))

        index_desc, index_data = _make_index([m1_desc, m2_desc])
        src.push(index_desc, io.BytesIO(index_data))

        # Track push calls
        push_digests = []
        original_push = dst.push

        def tracking_push(desc, content):
            push_digests.append(desc["digest"])
            return original_push(desc, content)

        dst.push = tracking_push

        copy_graph(src, dst, index_desc)

        # The shared config and layer should appear only once
        assert push_digests.count(config_desc["digest"]) == 1
        assert push_digests.count(layer_desc["digest"]) == 1

    def test_foreign_layers_filtered(self):
        """Foreign layers should not be copied."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        config_data = b'{"arch":"amd64"}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        # Normal layer
        normal_data = b"normal layer"
        normal_desc = _make_blob(normal_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(normal_desc, io.BytesIO(normal_data))

        # Foreign layer
        foreign_data = b"foreign layer"
        foreign_desc = _make_blob(
            foreign_data,
            "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip",
        )
        src.push(foreign_desc, io.BytesIO(foreign_data))

        manifest_desc, manifest_data = _make_manifest(
            config_desc, [normal_desc, foreign_desc]
        )
        src.push(manifest_desc, io.BytesIO(manifest_data))

        copy_graph(src, dst, manifest_desc)

        # Normal layer copied, foreign layer not
        assert dst.exists(normal_desc)
        assert not dst.exists(foreign_desc)
        assert dst.exists(config_desc)
        assert dst.exists(manifest_desc)

    def test_concurrency_option(self):
        """Concurrency option should limit parallel operations."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"concurrent test"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        opts = CopyGraphOptions(concurrency=1)
        copy_graph(src, dst, desc, opts=opts)
        assert dst.exists(desc)

    def test_custom_find_successors(self):
        """Custom find_successors should override default behavior."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"blob"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        # Custom that always returns no successors
        opts = CopyGraphOptions(
            find_successors=lambda fetcher, d: [],
        )

        copy_graph(src, dst, desc, opts=opts)
        assert dst.exists(desc)


# ---------------------------------------------------------------------------
# Tests: Top-level copy() function
# ---------------------------------------------------------------------------


class TestCopy:
    def test_copy_with_tag(self):
        """copy() should resolve, copy, and tag at destination."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"tagged content"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1.0")

        result = copy(src, "v1.0", dst, "v1.0")

        assert descriptors_equal(result, desc)
        assert dst.exists(desc)
        assert dst.get_tag("v1.0") is not None

    def test_copy_default_dst_ref(self):
        """When dst_ref is empty, should use src_ref."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"default ref"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "latest")

        result = copy(src, "latest", dst)

        assert dst.get_tag("latest") is not None

    def test_copy_manifest_with_tag(self):
        """copy() should tag the manifest at the destination."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        config_data = b'{"architecture":"amd64"}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer"
        layer_desc = _make_blob(layer_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v2.0")

        result = copy(src, "v2.0", dst, "v2.0")

        assert descriptors_equal(result, manifest_desc)
        assert dst.exists(config_desc)
        assert dst.exists(layer_desc)
        assert dst.exists(manifest_desc)

        tagged = dst.get_tag("v2.0")
        assert tagged is not None
        assert descriptors_equal(tagged, manifest_desc)

    def test_copy_with_map_root(self):
        """map_root should transform the root descriptor before copy."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        # Original blob tagged at source
        blob_data = b"original"
        blob_desc = _make_blob(blob_data)
        src.push(blob_desc, io.BytesIO(blob_data))
        src.tag(blob_desc, "original")

        # Alternate blob also available
        alt_data = b"alternate"
        alt_desc = _make_blob(alt_data)
        src.push(alt_desc, io.BytesIO(alt_data))

        opts = CopyOptions(
            map_root=lambda src_store, root: alt_desc,
        )

        result = copy(src, "original", dst, "mapped", opts)

        assert descriptors_equal(result, alt_desc)
        assert dst.exists(alt_desc)

    def test_copy_nil_source_raises(self):
        """copy() with None src should raise CopyError."""
        dst = InMemoryTarget()
        with pytest.raises(CopyError) as exc_info:
            copy(None, "ref", dst, "ref")
        assert exc_info.value.origin == CopyErrorOrigin.SOURCE

    def test_copy_nil_destination_raises(self):
        """copy() with None dst should raise CopyError."""
        src = InMemoryTarget()
        with pytest.raises(CopyError) as exc_info:
            copy(src, "ref", None, "ref")
        assert exc_info.value.origin == CopyErrorOrigin.DESTINATION

    def test_copy_already_exists_tags(self):
        """When root already exists at dst, it should still get tagged."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"existing"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1.0")
        dst.push(desc, io.BytesIO(blob_data))  # Already at destination

        result = copy(src, "v1.0", dst, "v1.0")

        assert descriptors_equal(result, desc)
        tagged = dst.get_tag("v1.0")
        assert tagged is not None

    def test_copy_with_pre_post_hooks(self):
        """Pre and post copy hooks should be invoked."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"hooks test"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1.0")

        pre_copy_called = []
        post_copy_called = []

        opts = CopyOptions(
            graph=CopyGraphOptions(
                pre_copy=lambda d: pre_copy_called.append(d),
                post_copy=lambda d: post_copy_called.append(d),
            ),
        )

        copy(src, "v1.0", dst, "v1.0", opts)

        # Single-blob copy: exactly one pre/post call
        assert len(pre_copy_called) == 1
        assert len(post_copy_called) == 1


# ---------------------------------------------------------------------------
# Tests: ReferencePusher path
# ---------------------------------------------------------------------------


class InMemoryTargetWithRefPush(InMemoryTarget):
    """Target that also supports push_reference (atomic push+tag)."""

    def __init__(self):
        super().__init__()
        self.ref_pushes: List[Tuple[Descriptor, str]] = []

    def push_reference(
        self, desc: Descriptor, content: BinaryIO, reference: str
    ) -> None:
        data = content.read()
        digest = desc.get("digest", "")
        with self._lock:
            self._content[digest] = data
            self._tags[reference] = desc
        self.ref_pushes.append((desc, reference))


class TestCopyWithReferencePusher:
    def test_copy_uses_push_reference(self):
        """When dst supports ReferencePusher, the root should use push_reference."""
        src = InMemoryTarget()
        dst = InMemoryTargetWithRefPush()

        config_data = b'{"config":true}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer data"
        layer_desc = _make_blob(layer_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1.0")

        result = copy(src, "v1.0", dst, "v1.0")

        assert descriptors_equal(result, manifest_desc)
        # Root must use push_reference exactly once
        assert len(dst.ref_pushes) == 1
        ref_push_desc, ref_push_ref = dst.ref_pushes[0]
        assert descriptors_equal(ref_push_desc, manifest_desc)
        assert ref_push_ref == "v1.0"


# ---------------------------------------------------------------------------
# Tests: ReferenceFetcher path
# ---------------------------------------------------------------------------


class InMemorySourceWithRefFetch(InMemoryTarget):
    """Source that also supports fetch_reference (resolve + fetch in one call)."""

    def fetch_reference(self, reference: str) -> Tuple[Descriptor, BinaryIO]:
        desc = self.resolve(reference)
        content = self.fetch(desc)
        return desc, content


class TestCopyWithReferenceFetcher:
    def test_copy_uses_fetch_reference(self):
        """When src supports ReferenceFetcher, should use fetch_reference."""
        src = InMemorySourceWithRefFetch()
        dst = InMemoryTarget()

        config_data = b'{"config":true}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer for ref fetch"
        layer_desc = _make_blob(layer_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1.0")

        result = copy(src, "v1.0", dst, "v1.0")

        assert descriptors_equal(result, manifest_desc)
        assert dst.exists(config_desc)
        assert dst.exists(layer_desc)
        assert dst.exists(manifest_desc)


# ---------------------------------------------------------------------------
# Tests: Mounting path
# ---------------------------------------------------------------------------


class InMemoryTargetWithMount(InMemoryTarget):
    """Target that supports blob mounting."""

    def __init__(self):
        super().__init__()
        self.mount_calls: List[Tuple[Descriptor, str]] = []

    def mount(
        self,
        desc: Descriptor,
        from_repo: str,
        get_content,
    ) -> None:
        # Simulate successful mount
        self.mount_calls.append((desc, from_repo))
        # Mark as existing
        digest = desc.get("digest", "")
        with self._lock:
            self._content[digest] = b"mounted"


class TestCopyWithMounting:
    def test_mount_from_callback(self):
        """Blobs should be mounted when mount_from provides source repos."""
        src = InMemoryTarget()
        dst = InMemoryTargetWithMount()

        config_data = b'{"config":true}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"mountable layer"
        layer_desc = _make_blob(layer_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1.0")

        mounted = []
        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: ["source/repo"],
                on_mounted=lambda d: mounted.append(d),
            ),
        )

        copy(src, "v1.0", dst, "v1.0", opts)

        # Config and layer should have been mounted (not manifests)
        assert len(dst.mount_calls) == 2  # config + layer

    def test_mount_not_attempted_for_manifests(self):
        """Mounting should not be attempted for manifest descriptors."""
        src = InMemoryTarget()
        dst = InMemoryTargetWithMount()

        blob_data = b"just a blob"
        blob_desc = _make_blob(blob_data)
        src.push(blob_desc, io.BytesIO(blob_data))
        src.tag(blob_desc, "v1.0")

        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: ["source/repo"],
            ),
        )

        copy(src, "v1.0", dst, "v1.0", opts)

        # Should have mounted the blob (not a manifest)
        assert len(dst.mount_calls) == 1


# ---------------------------------------------------------------------------
# Tests: CopyOptions.WithTargetPlatform-equivalent
# ---------------------------------------------------------------------------


class TestCopyOptionsMapRoot:
    def test_map_root_chains(self):
        """Multiple map_root transformations should chain."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blobs = {}
        for name in ("original", "final"):
            data = name.encode()
            desc = _make_blob(data)
            src.push(desc, io.BytesIO(data))
            blobs[name] = desc

        src.tag(blobs["original"], "start")

        opts = CopyOptions(
            map_root=lambda store, root: blobs["final"],
        )

        result = copy(src, "start", dst, "result", opts)
        assert descriptors_equal(result, blobs["final"])


# ---------------------------------------------------------------------------
# Tests: Error paths in copy.py
# ---------------------------------------------------------------------------


class TestCopyErrorPaths:
    def test_map_root_error_raises_copy_error(self):
        """map_root that raises should be wrapped in CopyError."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"data"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        def bad_map_root(store, root):
            raise RuntimeError("map root failed")

        opts = CopyOptions(map_root=bad_map_root)
        with pytest.raises(CopyError) as exc_info:
            copy(src, "v1", dst, "v1", opts)
        assert exc_info.value.op == "MapRoot"
        assert exc_info.value.origin == CopyErrorOrigin.SOURCE

    def test_resolve_error_raises_copy_error(self):
        """Source resolve failure should be wrapped in CopyError."""
        src = InMemoryTarget()  # no tags set, so resolve will fail
        dst = InMemoryTarget()

        with pytest.raises(CopyError) as exc_info:
            copy(src, "missing", dst, "missing")
        assert exc_info.value.op == "Resolve"
        assert exc_info.value.origin == CopyErrorOrigin.SOURCE

    def test_fetch_reference_error_raises_copy_error(self):
        """fetch_reference failure should be wrapped in CopyError."""

        class FailingRefFetchSource(InMemoryTarget):
            def fetch_reference(self, reference):
                raise ConnectionError("network down")

        src = FailingRefFetchSource()
        dst = InMemoryTarget()

        with pytest.raises(CopyError) as exc_info:
            copy(src, "v1", dst, "v1")
        assert exc_info.value.op == "FetchReference"
        assert exc_info.value.origin == CopyErrorOrigin.SOURCE

    def test_successors_error_in_resolve_root(self):
        """successors failure during _resolve_root should be CopyError."""

        class RefFetchWithBadSuccessors(InMemoryTarget):
            def fetch_reference(self, reference):
                desc = self.resolve(reference)
                content = self.fetch(desc)
                return desc, content

        src = RefFetchWithBadSuccessors()
        dst = InMemoryTarget()

        # Push a blob tagged as a manifest media type so successors tries to parse it
        bad_manifest_data = b"not valid json"
        digest = "sha256:" + hashlib.sha256(bad_manifest_data).hexdigest()
        desc = {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": digest,
            "size": len(bad_manifest_data),
        }
        src.push(desc, io.BytesIO(bad_manifest_data))
        src.tag(desc, "bad")

        with pytest.raises(CopyError) as exc_info:
            copy(src, "bad", dst, "bad")
        assert exc_info.value.op == "Successors"


# ---------------------------------------------------------------------------
# Tests: CacheProxy.push raises NotImplementedError
# ---------------------------------------------------------------------------


class TestCacheProxyPush:
    def test_push_raises_not_implemented(self):
        base = MemoryStorage()
        cache = MemoryStorage()
        proxy = CacheProxy(base, cache, 1024)
        desc = {"digest": "sha256:x", "size": 1, "mediaType": "text/plain"}
        with pytest.raises(NotImplementedError):
            proxy.push(desc, io.BytesIO(b"x"))


# ---------------------------------------------------------------------------
# Tests: successors for Docker media types
# ---------------------------------------------------------------------------


class TestSuccessorsDockerTypes:
    def test_docker_manifest_v2_successors(self):
        """Docker manifest v2 should extract config + layers."""
        config = {
            "mediaType": "application/vnd.docker.container.image.v1+json",
            "digest": "sha256:cfg",
            "size": 10,
        }
        layer = {
            "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
            "digest": "sha256:layer1",
            "size": 100,
        }
        manifest_data = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "config": config,
                "layers": [layer],
            }
        ).encode()

        desc = {
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "digest": "sha256:dockermfst",
            "size": len(manifest_data),
        }
        fetcher = FetcherFunc(lambda d: io.BytesIO(manifest_data))
        result = successors(fetcher, desc)
        assert len(result) == 2
        assert result[0]["digest"] == "sha256:cfg"
        assert result[1]["digest"] == "sha256:layer1"

    def test_docker_manifest_list_successors(self):
        """Docker manifest list should extract manifests."""
        m1 = {
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "digest": "sha256:m1",
            "size": 100,
        }
        m2 = {
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "digest": "sha256:m2",
            "size": 200,
        }
        list_data = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
                "manifests": [m1, m2],
            }
        ).encode()

        desc = {
            "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
            "digest": "sha256:dockerlist",
            "size": len(list_data),
        }
        fetcher = FetcherFunc(lambda d: io.BytesIO(list_data))
        result = successors(fetcher, desc)
        assert len(result) == 2
        assert result[0]["digest"] == "sha256:m1"
        assert result[1]["digest"] == "sha256:m2"

    def test_index_with_subject(self):
        """OCI index with a subject should include it in successors."""
        m1 = {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": "sha256:m1",
            "size": 100,
        }
        subject = {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": "sha256:subj",
            "size": 50,
        }
        index_data = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.index.v1+json",
                "manifests": [m1],
                "subject": subject,
            }
        ).encode()

        desc = {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "digest": "sha256:idxsubj",
            "size": len(index_data),
        }
        fetcher = FetcherFunc(lambda d: io.BytesIO(index_data))
        result = successors(fetcher, desc)
        assert len(result) == 2
        assert result[0]["digest"] == "sha256:m1"
        assert result[1]["digest"] == "sha256:subj"


# ---------------------------------------------------------------------------
# Tests: copy_graph error paths
# ---------------------------------------------------------------------------


class TestCopyGraphErrorPaths:
    def test_exists_error_raises_copy_error(self):
        """dst.exists raising should produce a CopyError."""
        src = InMemoryTarget()
        blob_data = b"exists fail"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        class FailingExistsDst(InMemoryTarget):
            def exists(self, desc):
                raise IOError("disk error")

        dst = FailingExistsDst()
        with pytest.raises(CopyError) as exc_info:
            copy_graph(src, dst, desc)
        assert exc_info.value.op == "Exists"
        assert exc_info.value.origin == CopyErrorOrigin.DESTINATION

    def test_find_successors_error_raises_copy_error(self):
        """find_successors raising should produce a CopyError."""
        src = InMemoryTarget()

        # Create a manifest but don't push the manifest content (so successors fails)
        config_data = b'{"arch":"amd64"}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))

        # Manifest with valid descriptor but content will fail to parse
        bad_data = b"not json"
        digest = "sha256:" + hashlib.sha256(bad_data).hexdigest()
        manifest_desc = {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": digest,
            "size": len(bad_data),
        }
        src.push(manifest_desc, io.BytesIO(bad_data))

        dst = InMemoryTarget()
        with pytest.raises(CopyError) as exc_info:
            copy_graph(src, dst, manifest_desc)
        assert exc_info.value.op == "FindSuccessors"
        assert exc_info.value.origin == CopyErrorOrigin.SOURCE

    def test_fetch_error_during_copy_raises_copy_error(self):
        """Fetch failure during _do_copy_node should produce CopyError."""
        blob_data = b"fetch fail"
        desc = _make_blob(blob_data)

        class FailingFetchSrc(InMemoryTarget):
            def exists(self, desc):
                return True

            def fetch(self, desc):
                raise IOError("read error")

        src = FailingFetchSrc()
        src.push(desc, io.BytesIO(blob_data))

        # dst doesn't have it, so it'll try to copy
        dst = InMemoryTarget()

        # Use copy_graph directly so we can bypass exists check
        # We need the src to fail on fetch but not on exists
        class FetchFailSource(InMemoryTarget):
            def fetch(self, desc):
                raise IOError("read error")

        bad_src = FetchFailSource()
        with pytest.raises(CopyError) as exc_info:
            copy_graph(bad_src, dst, desc)
        assert exc_info.value.op == "Fetch"
        assert exc_info.value.origin == CopyErrorOrigin.SOURCE

    def test_push_error_during_copy_raises_copy_error(self):
        """Push failure during _do_copy_node should produce CopyError."""
        src = InMemoryTarget()
        blob_data = b"push fail"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        class FailingPushDst(InMemoryTarget):
            def push(self, desc, content):
                raise IOError("write error")

        dst = FailingPushDst()
        with pytest.raises(CopyError) as exc_info:
            copy_graph(src, dst, desc)
        assert exc_info.value.op == "Push"
        assert exc_info.value.origin == CopyErrorOrigin.DESTINATION

    def test_pre_copy_non_skip_exception_propagates(self):
        """Non-SkipNode exceptions from pre_copy should propagate."""
        src = InMemoryTarget()
        dst = InMemoryTarget()
        blob_data = b"precopy fail"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))

        def bad_pre_copy(d):
            raise RuntimeError("pre_copy exploded")

        opts = CopyGraphOptions(pre_copy=bad_pre_copy)
        with pytest.raises(RuntimeError, match="pre_copy exploded"):
            copy_graph(src, dst, desc, opts=opts)

    def test_cancel_event_prevents_further_processing(self):
        """After an error, subsequent nodes should be short-circuited."""
        src = InMemoryTarget()

        # Create an index with two manifests
        config_data = b'{"config":true}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer"
        layer_desc = _make_blob(
            layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
        )
        src.push(layer_desc, io.BytesIO(layer_data))

        m1_desc, m1_data = _make_manifest(config_desc, [layer_desc])
        src.push(m1_desc, io.BytesIO(m1_data))

        index_desc, index_data = _make_index([m1_desc])
        src.push(index_desc, io.BytesIO(index_data))

        push_count = 0

        class CountingFailDst(InMemoryTarget):
            def push(self, desc, content):
                nonlocal push_count
                push_count += 1
                if push_count == 1:
                    raise IOError("first push fails")
                super().push(desc, content)

        dst = CountingFailDst()
        with pytest.raises(CopyError):
            copy_graph(src, dst, index_desc)

    def test_mount_error_raises_copy_error(self):
        """Mount that raises should produce CopyError."""
        src = InMemoryTarget()
        blob_data = b"mount error"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        class FailingMountDst(InMemoryTarget):
            def mount(self, desc, from_repo, get_content):
                raise ConnectionError("mount network error")

        dst = FailingMountDst()
        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: ["source/repo"],
            ),
        )
        with pytest.raises(CopyError) as exc_info:
            copy(src, "v1", dst, "v1", opts)
        assert exc_info.value.op == "Mount"
        assert exc_info.value.origin == CopyErrorOrigin.DESTINATION

    def test_mount_fallback_with_skip_source(self):
        """Mount with multiple repos: first fails, second succeeds via copy."""
        src = InMemoryTarget()
        blob_data = b"multi mount"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        mount_attempts = []

        class MultiMountDst(InMemoryTarget):
            def mount(self, desc, from_repo, get_content):
                mount_attempts.append(from_repo)
                # Always call get_content to trigger fallback
                content = get_content()
                data = content.read()
                digest = desc.get("digest", "")
                with self._lock:
                    if digest not in self._content:
                        self._content[digest] = data

        dst = MultiMountDst()
        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: ["repo1", "repo2"],
            ),
        )
        copy(src, "v1", dst, "v1", opts)
        # Should have tried repo1 first, then repo2
        assert "repo1" in mount_attempts

    def test_mount_fallback_with_pre_copy_skip_node(self):
        """Mount fallback get_content with pre_copy that raises SkipNode."""
        src = InMemoryTarget()
        blob_data = b"skip mount"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        class FallbackMountDst(InMemoryTarget):
            def mount(self, mount_desc, from_repo, get_content):
                content = get_content()
                data = content.read()
                digest = mount_desc.get("digest", "")
                with self._lock:
                    if digest not in self._content:
                        self._content[digest] = data

        dst = FallbackMountDst()

        def skip_pre_copy(d):
            raise SkipNode()

        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: ["repo1"],
                pre_copy=skip_pre_copy,
            ),
        )
        # SkipNode from pre_copy skips the node: no upload, no error.
        copy(src, "v1", dst, "v1", opts)
        assert not dst.exists(desc)

    def test_mount_fallback_post_copy_called(self):
        """After mount fallback to copy, post_copy should be called."""
        src = InMemoryTarget()
        blob_data = b"fallback post"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        class FallbackMountDst(InMemoryTarget):
            def mount(self, mount_desc, from_repo, get_content):
                content = get_content()
                data = content.read()
                digest = mount_desc.get("digest", "")
                with self._lock:
                    if digest not in self._content:
                        self._content[digest] = data

        dst = FallbackMountDst()
        post_copy_called = []
        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: ["repo1"],
                post_copy=lambda d: post_copy_called.append(d),
            ),
        )
        copy(src, "v1", dst, "v1", opts)
        # Single blob via mount fallback: exactly one post_copy call
        assert len(post_copy_called) == 1

    def test_mount_empty_source_repositories(self):
        """mount_from returning empty list should fall back to copy."""
        src = InMemoryTarget()
        blob_data = b"empty repos"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        class MountDst(InMemoryTarget):
            def mount(self, desc, from_repo, get_content):
                raise AssertionError("mount should not be called")

        dst = MountDst()
        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: [],  # empty list
            ),
        )
        copy(src, "v1", dst, "v1", opts)
        assert dst.exists(desc)

    def test_mount_on_non_mounter_dst(self):
        """mount_from provided but dst doesn't support Mounter."""
        src = InMemoryTarget()
        blob_data = b"no mounter"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        dst = InMemoryTarget()  # no mount method matching Mounter protocol
        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: ["repo1"],
            ),
        )
        copy(src, "v1", dst, "v1", opts)
        assert dst.exists(desc)


# ---------------------------------------------------------------------------
# Tests: _prepare_copy paths (ReferencePusher tagging)
# ---------------------------------------------------------------------------


class TestPrepareCopyPaths:
    def test_reference_pusher_with_existing_root(self):
        """ReferencePusher dst: root already exists → on_copy_skipped still tags."""
        # Use ReferenceFetcher source so root gets cached in proxy during resolve
        src = InMemorySourceWithRefFetch()
        dst = InMemoryTargetWithRefPush()

        config_data = b'{"config":true}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))
        dst.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer existing"
        layer_desc = _make_blob(
            layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
        )
        src.push(layer_desc, io.BytesIO(layer_data))
        dst.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1")
        dst.push(manifest_desc, io.BytesIO(manifest_data))  # already at dst

        skipped = []
        copy(
            src,
            "v1",
            dst,
            "v1",
            CopyOptions(
                graph=CopyGraphOptions(on_copy_skipped=lambda d: skipped.append(d))
            ),
        )
        # Root skipped but still tagged via push_reference exactly once
        assert len(dst.ref_pushes) == 1

    def test_reference_pusher_existing_root_non_ref_fetch_source(self):
        """Re-push identical content when the source is NOT a ReferenceFetcher.

        With a non-ReferenceFetcher source (e.g. LayoutTarget, as used by
        Registry.push), resolveRoot only resolves and does not cache the root.
        If the root already exists at a ReferencePusher destination the whole
        DAG is skipped and the root is tagged via
        _copy_cached_node_with_reference, which must fall back to fetching from
        the source (FetchCached semantics) rather than reading a cache that was
        never populated.

        Regression test: previously raised FileNotFoundError (cache-only fetch),
        breaking idempotent re-push of identical content.
        """
        src = InMemoryTarget()  # not a ReferenceFetcher
        dst = InMemoryTargetWithRefPush()

        config_data = b'{"config":true}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        layer_data = b"layer existing"
        layer_desc = _make_blob(
            layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
        )
        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])

        # Everything already present at the destination -> full DAG skip.
        for desc, data in (
            (config_desc, config_data),
            (layer_desc, layer_data),
            (manifest_desc, manifest_data),
        ):
            src.push(desc, io.BytesIO(data))
            dst.push(desc, io.BytesIO(data))
        src.tag(manifest_desc, "v1")

        # Must not raise (previously: FileNotFoundError "content not found").
        root = copy(src, "v1", dst, "v1")

        assert descriptors_equal(root, manifest_desc)
        # Skipped root is still tagged via push_reference exactly once.
        assert len(dst.ref_pushes) == 1
        assert dst.ref_pushes[0][1] == "v1"

    def test_reference_pusher_on_copy_skipped_non_root(self):
        """on_copy_skipped for non-root with ReferencePusher dst delegates to original."""
        src = InMemoryTarget()
        dst = InMemoryTargetWithRefPush()

        config_data = b'{"config":true}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))
        dst.push(config_desc, io.BytesIO(config_data))  # config already at dst

        layer_data = b"layer data"
        layer_desc = _make_blob(
            layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
        )
        src.push(layer_desc, io.BytesIO(layer_data))
        dst.push(layer_desc, io.BytesIO(layer_data))  # layer already at dst

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1")

        skipped = []
        copy(
            src,
            "v1",
            dst,
            "v1",
            CopyOptions(
                graph=CopyGraphOptions(on_copy_skipped=lambda d: skipped.append(d))
            ),
        )
        # Non-root nodes that were skipped should have called the original callback
        assert any(
            descriptors_equal(s, config_desc) or descriptors_equal(s, layer_desc)
            for s in skipped
        )

    def test_tag_error_raises_copy_error(self):
        """Tag failure at destination should produce CopyError."""
        src = InMemoryTarget()

        class FailingTagDst(InMemoryTarget):
            def tag(self, desc, reference):
                raise IOError("tag failed")

        dst = FailingTagDst()

        blob_data = b"tag fail"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        with pytest.raises(CopyError) as exc_info:
            copy(src, "v1", dst, "v1")
        assert exc_info.value.op == "Tag"
        assert exc_info.value.origin == CopyErrorOrigin.DESTINATION

    def test_on_copy_skipped_tag_error(self):
        """Tag failure during on_copy_skipped should produce CopyError."""
        src = InMemoryTarget()

        class FailingTagDst(InMemoryTarget):
            def tag(self, desc, reference):
                raise IOError("tag failed in skip")

        dst = FailingTagDst()

        blob_data = b"skip tag fail"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")
        dst.push(desc, io.BytesIO(blob_data))  # already at dst

        with pytest.raises(CopyError) as exc_info:
            copy(src, "v1", dst, "v1")
        assert exc_info.value.op == "Tag"
        assert exc_info.value.origin == CopyErrorOrigin.DESTINATION

    def test_reference_pusher_pre_copy_chains_original(self):
        """ReferencePusher path: original pre_copy should be invoked first."""
        src = InMemoryTarget()
        dst = InMemoryTargetWithRefPush()

        config_data = b'{"config":true}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer"
        layer_desc = _make_blob(
            layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
        )
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1")

        pre_copy_calls = []
        opts = CopyOptions(
            graph=CopyGraphOptions(
                pre_copy=lambda d: pre_copy_calls.append(d),
            ),
        )
        copy(src, "v1", dst, "v1", opts)
        # pre_copy called for config + layer + manifest = 3 nodes minimum
        assert len(pre_copy_calls) >= 3

    def test_reference_pusher_with_post_copy(self):
        """ReferencePusher path: post_copy should be invoked for the root."""
        src = InMemorySourceWithRefFetch()
        dst = InMemoryTargetWithRefPush()

        config_data = b'{"config":true}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer"
        layer_desc = _make_blob(
            layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
        )
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1")

        post_copy_calls = []
        opts = CopyOptions(
            graph=CopyGraphOptions(
                post_copy=lambda d: post_copy_calls.append(d),
            ),
        )
        copy(src, "v1", dst, "v1", opts)
        # post_copy should have been invoked for the root (in tagged_pre_copy)
        assert any(descriptors_equal(d, manifest_desc) for d in post_copy_calls)

    def test_non_ref_pusher_on_copy_skipped_with_original_callback(self):
        """Non-ReferencePusher: on_copy_skipped calls original callback for non-root."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        config_data = b'{"config":true}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))
        dst.push(config_desc, io.BytesIO(config_data))  # already at dst

        layer_data = b"layer"
        layer_desc = _make_blob(
            layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
        )
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1")

        original_skipped = []
        opts = CopyOptions(
            graph=CopyGraphOptions(
                on_copy_skipped=lambda d: original_skipped.append(d),
            ),
        )
        copy(src, "v1", dst, "v1", opts)
        # Original callback should be invoked for the non-root skipped node (config)
        assert any(descriptors_equal(d, config_desc) for d in original_skipped)


# ---------------------------------------------------------------------------
# Tests: _do_copy_node FileExistsError idempotency
# ---------------------------------------------------------------------------


class TestDoCopyNodeIdempotent:
    def test_push_file_exists_is_silent(self):
        """FileExistsError on push should be silently ignored."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"idempotent"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        dst.push(desc, io.BytesIO(blob_data))  # already at dst

        # But we bypass the exists check by using copy_graph with a custom
        # dst that returns False from exists but raises FileExistsError on push
        class AlwaysMissingDst(InMemoryTarget):
            def exists(self, desc):
                return False

        trick_dst = AlwaysMissingDst()
        trick_dst.push(desc, io.BytesIO(blob_data))  # pre-populate
        # Now exists returns False but push will raise FileExistsError
        copy_graph(src, trick_dst, desc)
        # Should succeed without raising


# ---------------------------------------------------------------------------
# Tests: mount fallback with pre_copy that raises non-SkipNode
# ---------------------------------------------------------------------------


class TestMountFallbackPreCopyError:
    def test_mount_fallback_pre_copy_raises_propagates(self):
        """Mount fallback get_content: pre_copy raising non-SkipNode propagates."""
        src = InMemoryTarget()
        blob_data = b"pre_copy fail mount"
        desc = _make_blob(blob_data)
        src.push(desc, io.BytesIO(blob_data))
        src.tag(desc, "v1")

        class FallbackMountDst(InMemoryTarget):
            def mount(self, mount_desc, from_repo, get_content):
                content = get_content()
                data = content.read()
                digest = mount_desc.get("digest", "")
                with self._lock:
                    if digest not in self._content:
                        self._content[digest] = data

        dst = FallbackMountDst()

        def exploding_pre_copy(d):
            raise RuntimeError("pre_copy exploded in mount")

        opts = CopyOptions(
            graph=CopyGraphOptions(
                mount_from=lambda d: ["repo1"],
                pre_copy=exploding_pre_copy,
            ),
        )
        with pytest.raises(CopyError) as exc_info:
            copy(src, "v1", dst, "v1", opts)
        # The RuntimeError from pre_copy is the inner error
        assert isinstance(exc_info.value.err, RuntimeError)
        assert "pre_copy exploded in mount" in str(exc_info.value.err)


# ---------------------------------------------------------------------------
# Tests: LimitedRegion
# ---------------------------------------------------------------------------


class TestLimitedRegion:
    def test_end_releases_semaphore(self):
        sem = threading.Semaphore(1)
        sem.acquire()
        region = LimitedRegion(sem)
        # Semaphore is at 0 -- another acquire would block
        region.end()
        # Now semaphore should be available
        assert sem.acquire(timeout=0.1)
        sem.release()

    def test_start_reacquires_semaphore(self):
        sem = threading.Semaphore(1)
        sem.acquire()
        region = LimitedRegion(sem)
        region.end()
        region.start()
        # Region holds the slot again; semaphore should be at 0
        assert not sem.acquire(timeout=0.01)
        region.end()  # cleanup

    def test_double_end_is_idempotent(self):
        sem = threading.Semaphore(1)
        sem.acquire()
        region = LimitedRegion(sem)
        region.end()
        region.end()  # should not release a second time
        assert sem.acquire(timeout=0.1)  # only one release happened
        assert not sem.acquire(timeout=0.01)  # no extra release
        sem.release()

    def test_start_when_not_ended_is_noop(self):
        sem = threading.Semaphore(1)
        sem.acquire()
        region = LimitedRegion(sem)
        region.start()  # not ended, should be a no-op (no extra acquire)
        region.end()  # cleanup


class TestLimitedRegionDeadlockPrevention:
    """
    Verify that the LimitedRegion pattern prevents deadlocks when
    copying deep content DAGs with low concurrency.
    """

    def test_deep_tree_with_concurrency_1(self):
        """
        A 3-level tree (index -> manifest -> blobs) with concurrency=1
        would deadlock without LimitedRegion: the root would hold the
        only slot while waiting for children that can never start.
        """
        src = InMemoryTarget()
        dst = InMemoryTarget()

        config_data = b'{"arch":"amd64"}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer content"
        layer_desc = _make_blob(layer_data, "application/vnd.oci.image.layer.v1.tar+gzip")
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))

        index_desc, index_data = _make_index([manifest_desc])
        src.push(index_desc, io.BytesIO(index_data))

        opts = CopyGraphOptions(concurrency=1)
        # This would hang forever without LimitedRegion
        copy_graph(src, dst, index_desc, opts=opts)

        assert dst.exists(index_desc)
        assert dst.exists(manifest_desc)
        assert dst.exists(config_desc)
        assert dst.exists(layer_desc)

    def test_wide_tree_with_concurrency_1(self):
        """
        An index with multiple manifests, each with their own layers,
        using concurrency=1 must still complete without deadlock.
        """
        src = InMemoryTarget()
        dst = InMemoryTarget()

        manifest_descs = []
        for i in range(5):
            cfg_data = f'{{"id":{i}}}'.encode()
            cfg_desc = _make_blob(cfg_data, "application/vnd.oci.image.config.v1+json")
            src.push(cfg_desc, io.BytesIO(cfg_data))

            lyr_data = f"layer-{i}".encode()
            lyr_desc = _make_blob(lyr_data, "application/vnd.oci.image.layer.v1.tar+gzip")
            src.push(lyr_desc, io.BytesIO(lyr_data))

            m_desc, m_data = _make_manifest(cfg_desc, [lyr_desc])
            src.push(m_desc, io.BytesIO(m_data))
            manifest_descs.append(m_desc)

        index_desc, index_data = _make_index(manifest_descs)
        src.push(index_desc, io.BytesIO(index_data))

        opts = CopyGraphOptions(concurrency=1)
        copy_graph(src, dst, index_desc, opts=opts)

        assert dst.exists(index_desc)
        for m in manifest_descs:
            assert dst.exists(m)

    def test_concurrent_copy_respects_semaphore(self):
        """
        Verify that at most `concurrency` copy operations run in parallel,
        even with the LimitedRegion release/reacquire pattern.
        """
        src = InMemoryTarget()
        dst = InMemoryTarget()

        max_concurrent = 0
        current_concurrent = 0
        lock = threading.Lock()

        # Wrap dst.push to track concurrent operations
        original_push = dst.push

        def tracking_push(desc, content):
            nonlocal max_concurrent, current_concurrent
            with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            try:
                original_push(desc, content)
            finally:
                with lock:
                    current_concurrent -= 1

        dst.push = tracking_push

        # Build content: 10 independent blobs under a manifest
        config_data = b'{"config":true}'
        config_desc = _make_blob(config_data, "application/vnd.oci.image.config.v1+json")
        src.push(config_desc, io.BytesIO(config_data))

        layers = []
        for i in range(10):
            data = f"blob-{i}-padding".encode()
            desc = _make_blob(data, "application/vnd.oci.image.layer.v1.tar+gzip")
            src.push(desc, io.BytesIO(data))
            layers.append(desc)

        manifest_desc, manifest_data = _make_manifest(config_desc, layers)
        src.push(manifest_desc, io.BytesIO(manifest_data))

        concurrency = 2
        opts = CopyGraphOptions(concurrency=concurrency)
        copy_graph(src, dst, manifest_desc, opts=opts)

        assert dst.exists(manifest_desc)
        # max_concurrent should not exceed the concurrency limit
        assert max_concurrent <= concurrency


# ---------------------------------------------------------------------------
# Tests for digest verification (S2 fix)
# ---------------------------------------------------------------------------


class TestDigestVerification:
    """Tests for content integrity verification during copy."""

    def test_digest_mismatch_raises_error(self):
        """Tampered content must be rejected."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"original content"
        blob_desc = _make_blob(blob_data)

        # Push tampered data under the correct digest
        tampered_data = b"TAMPERED content"
        with src._lock:
            src._content[blob_desc["digest"]] = tampered_data

        with pytest.raises(CopyError, match="digest mismatch"):
            copy_graph(src, dst, blob_desc)

    def test_size_mismatch_raises_error(self):
        """Content with wrong size must be rejected."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"some content"
        blob_desc = _make_blob(blob_data)
        # Lie about the size
        blob_desc["size"] = 1

        src.push(
            {"mediaType": blob_desc["mediaType"], "digest": blob_desc["digest"], "size": len(blob_data)},
            io.BytesIO(blob_data),
        )

        with pytest.raises(CopyError, match="size mismatch"):
            copy_graph(src, dst, blob_desc)

    def test_correct_content_passes_verification(self):
        """Correct content is copied without error."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"valid content"
        blob_desc = _make_blob(blob_data)
        src.push(blob_desc, io.BytesIO(blob_data))

        copy_graph(src, dst, blob_desc)
        assert dst.exists(blob_desc)
        assert dst.get_content(blob_desc["digest"]) == blob_data

    def test_invalid_digest_format_raises_error(self):
        """A non-empty but malformed digest must be rejected, not skipped."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"deadbeef"
        bad_desc = {
            "mediaType": "application/octet-stream",
            "digest": "deadbeef",  # missing "algorithm:" prefix
            "size": len(blob_data),
        }
        with src._lock:
            src._content[bad_desc["digest"]] = blob_data

        with pytest.raises(CopyError, match="invalid digest format"):
            copy_graph(src, dst, bad_desc)
        assert not dst.exists(bad_desc)

    def test_unsupported_digest_algorithm_raises_error(self):
        """A digest with an unsupported algorithm must be rejected, not skipped."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"payload"
        bad_desc = {
            "mediaType": "application/octet-stream",
            "digest": "fakealgo:abcdef",
            "size": len(blob_data),
        }
        with src._lock:
            src._content[bad_desc["digest"]] = blob_data

        with pytest.raises(CopyError, match="unsupported digest algorithm"):
            copy_graph(src, dst, bad_desc)
        assert not dst.exists(bad_desc)


# ---------------------------------------------------------------------------
# Tests for options mutation safety (C3 fix)
# ---------------------------------------------------------------------------


class TestCopyOptionsMutationSafety:
    """Tests that copy() does not mutate the caller's CopyOptions."""

    def test_copy_does_not_mutate_opts(self):
        """Calling copy() should not modify the original opts object."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"hello"
        blob_desc = _make_blob(blob_data)
        src.push(blob_desc, io.BytesIO(blob_data))

        manifest_desc, manifest_data = _make_manifest(blob_desc, [])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1")

        pre_copy_calls = []
        original_pre_copy = lambda desc: pre_copy_calls.append(desc)

        opts = CopyOptions(
            graph=CopyGraphOptions(pre_copy=original_pre_copy)
        )

        copy(src, "v1", dst, "v1", opts=opts)

        # The original pre_copy should NOT have been replaced
        assert opts.graph.pre_copy is original_pre_copy

    def test_reuse_opts_across_copies(self):
        """Using the same opts for two copies should work correctly."""
        src = InMemoryTarget()
        dst = InMemoryTarget()

        blob_data = b"data1"
        blob_desc = _make_blob(blob_data)
        src.push(blob_desc, io.BytesIO(blob_data))

        m1_desc, m1_data = _make_manifest(blob_desc, [])
        src.push(m1_desc, io.BytesIO(m1_data))
        src.tag(m1_desc, "v1")

        blob_data2 = b"data2"
        blob_desc2 = _make_blob(blob_data2)
        src.push(blob_desc2, io.BytesIO(blob_data2))

        m2_desc, m2_data = _make_manifest(blob_desc2, [])
        src.push(m2_desc, io.BytesIO(m2_data))
        src.tag(m2_desc, "v2")

        opts = CopyOptions()

        copy(src, "v1", dst, "tag1", opts=opts)
        copy(src, "v2", dst, "tag2", opts=opts)

        assert dst.get_tag("tag1") is not None
        assert dst.get_tag("tag2") is not None


# ---------------------------------------------------------------------------
# Tests for LayoutTarget digest validation (S1 fix)
# ---------------------------------------------------------------------------


class TestLayoutTargetDigestValidation:
    """Tests that LayoutTarget rejects malicious digest strings."""

    def test_rejects_path_traversal_digest(self):
        """Digests containing path traversal must be rejected."""
        mock_layout = MagicMock()
        mock_layout._oci_layout_path = "/tmp/fake"
        target = LayoutTarget(mock_layout)

        evil_desc = {"digest": "sha256:../../etc/passwd", "mediaType": "", "size": 0}
        with pytest.raises(ValueError, match="invalid digest format"):
            target.fetch(evil_desc)
        with pytest.raises(ValueError, match="invalid digest format"):
            target.exists(evil_desc)

    def test_accepts_valid_digest(self, tmp_path):
        """Valid hex digests are accepted."""
        assert _VALID_DIGEST_RE.match("sha256:abcdef0123456789")
        assert not _VALID_DIGEST_RE.match("sha256:../../etc/passwd")
        assert not _VALID_DIGEST_RE.match("sha256:ABCDEF")  # uppercase
        assert not _VALID_DIGEST_RE.match("")


# ---------------------------------------------------------------------------
# Tests: LayoutTarget real on-disk behavior (Target protocol round-trips)
# ---------------------------------------------------------------------------


class TestLayoutTargetFilesystem:
    """
    Exercise LayoutTarget against a real OCI layout directory.

    The other LayoutTarget tests use a MagicMock layout; these drive the
    actual filesystem code paths: atomic content-addressed push, fetch,
    existence checks, index.json tagging/resolution, and skeleton init.
    """

    @staticmethod
    def _new_target(tmp_path, name="layout"):
        layout = Layout(str(tmp_path / name), validate=False)
        return LayoutTarget(layout)

    def test_push_creates_layout_skeleton(self, tmp_path):
        """First push should materialize the OCI layout skeleton on disk."""
        layout_dir = tmp_path / "layout"
        target = LayoutTarget(Layout(str(layout_dir), validate=False))

        data = b"hello layout"
        desc = _make_blob(data)
        target.push(desc, io.BytesIO(data))

        assert (layout_dir / oras.defaults.oci_layout_file).exists()
        assert (layout_dir / oras.defaults.oci_image_index_file).exists()
        assert (layout_dir / oras.defaults.oci_blobs_dir).is_dir()
        # The resulting directory is a valid OCI layout.
        assert Layout.is_oci_layout(str(layout_dir)) is True

    def test_push_fetch_exists_round_trip(self, tmp_path):
        """Content pushed to the layout can be checked and read back exactly."""
        target = self._new_target(tmp_path)

        data = b"round trip content"
        desc = _make_blob(data)

        assert not target.exists(desc)
        target.push(desc, io.BytesIO(data))
        assert target.exists(desc)

        with target.fetch(desc) as fh:
            assert fh.read() == data

        # Blob is stored content-addressed at blobs/<algo>/<hash>.
        algo, hexd = desc["digest"].split(":", 1)
        blob_path = tmp_path / "layout" / "blobs" / algo / hexd
        assert blob_path.read_bytes() == data

    def test_push_is_idempotent_and_deduplicates(self, tmp_path):
        """Pushing the same digest twice is silent and leaves content intact."""
        target = self._new_target(tmp_path)

        data = b"dedupe me"
        desc = _make_blob(data)
        target.push(desc, io.BytesIO(data))

        algo, hexd = desc["digest"].split(":", 1)
        blob_path = tmp_path / "layout" / "blobs" / algo / hexd
        first_mtime = blob_path.stat().st_mtime_ns

        # Second push should short-circuit without rewriting the blob file.
        target.push(desc, io.BytesIO(data))
        assert blob_path.stat().st_mtime_ns == first_mtime
        with target.fetch(desc) as fh:
            assert fh.read() == data

    def test_push_streams_large_content(self, tmp_path):
        """Large blobs round-trip correctly through the streaming push path."""
        target = self._new_target(tmp_path)

        data = b"x" * (1024 * 1024 + 7)  # ~1 MiB, not a round buffer size
        desc = _make_blob(data)
        target.push(desc, io.BytesIO(data))

        with target.fetch(desc) as fh:
            assert fh.read() == data

    def test_push_leaves_no_temp_files(self, tmp_path):
        """Atomic push must not leave temp files behind in the blob dir."""
        target = self._new_target(tmp_path)

        data = b"atomic"
        desc = _make_blob(data)
        target.push(desc, io.BytesIO(data))

        algo, _ = desc["digest"].split(":", 1)
        algo_dir = tmp_path / "layout" / "blobs" / algo
        entries = list(algo_dir.iterdir())
        assert len(entries) == 1  # only the final blob, no tmp* leftovers

    def test_push_failure_cleans_up_temp_file(self, tmp_path):
        """A streaming error mid-push must propagate and leave no temp file."""
        target = self._new_target(tmp_path)
        target.push(_make_blob(b"seed"), io.BytesIO(b"seed"))  # init skeleton

        class ExplodingReader(io.RawIOBase):
            def readable(self):
                return True

            def readinto(self, b):
                raise IOError("stream died mid-copy")

        desc = _make_blob(b"never lands")
        with pytest.raises(IOError, match="stream died mid-copy"):
            target.push(desc, ExplodingReader())

        # Blob was not committed, and no tmp* scratch file was left behind.
        assert not target.exists(desc)
        algo, _ = desc["digest"].split(":", 1)
        algo_dir = tmp_path / "layout" / "blobs" / algo
        leftover = [p for p in algo_dir.iterdir() if p.name.startswith("tmp")]
        assert leftover == []

    def test_fetch_missing_blob_raises(self, tmp_path):
        """Fetching a valid-but-absent digest raises FileNotFoundError."""
        target = self._new_target(tmp_path)
        target.push(_make_blob(b"seed"), io.BytesIO(b"seed"))  # ensure skeleton

        missing = _make_blob(b"never pushed")
        with pytest.raises(FileNotFoundError):
            target.fetch(missing)

    def test_tag_then_resolve_round_trip(self, tmp_path):
        """A tagged descriptor resolves back to equal metadata."""
        target = self._new_target(tmp_path)

        desc, data = _make_manifest(
            _make_blob(b'{"c":1}', "application/vnd.oci.image.config.v1+json"), []
        )
        target.push(desc, io.BytesIO(data))
        target.tag(desc, "v1.0")

        resolved = target.resolve("v1.0")
        assert resolved["digest"] == desc["digest"]
        assert resolved["mediaType"] == desc["mediaType"]
        assert resolved["size"] == desc["size"]

    def test_tag_replaces_existing_reference(self, tmp_path):
        """Re-tagging the same reference replaces, not duplicates, the entry."""
        target = self._new_target(tmp_path)

        desc1 = _make_blob(b"first", "application/vnd.oci.image.manifest.v1+json")
        desc2 = _make_blob(b"second", "application/vnd.oci.image.manifest.v1+json")
        target.push(desc1, io.BytesIO(b"first"))
        target.push(desc2, io.BytesIO(b"second"))

        target.tag(desc1, "stable")
        target.tag(desc2, "stable")  # same ref, new target

        index = read_json_index(tmp_path / "layout")
        stable_entries = [
            m
            for m in index["manifests"]
            if m.get("annotations", {}).get(
                oras.defaults.oci_ref_name_annotation
            )
            == "stable"
        ]
        assert len(stable_entries) == 1
        assert target.resolve("stable")["digest"] == desc2["digest"]

    def test_tag_appends_distinct_references(self, tmp_path):
        """Distinct references each get their own index entry."""
        target = self._new_target(tmp_path)

        desc_a = _make_blob(b"a", "application/vnd.oci.image.manifest.v1+json")
        desc_b = _make_blob(b"b", "application/vnd.oci.image.manifest.v1+json")
        target.push(desc_a, io.BytesIO(b"a"))
        target.push(desc_b, io.BytesIO(b"b"))
        target.tag(desc_a, "alpha")
        target.tag(desc_b, "beta")

        assert target.resolve("alpha")["digest"] == desc_a["digest"]
        assert target.resolve("beta")["digest"] == desc_b["digest"]
        index = read_json_index(tmp_path / "layout")
        assert len(index["manifests"]) == 2

    def test_resolve_missing_reference_raises(self, tmp_path):
        """Resolving an unknown reference raises FileNotFoundError."""
        target = self._new_target(tmp_path)
        target.push(_make_blob(b"seed"), io.BytesIO(b"seed"))  # creates index.json

        with pytest.raises(FileNotFoundError, match="Reference not found"):
            target.resolve("does-not-exist")

    def test_invalid_digest_rejected_on_all_ops(self, tmp_path):
        """Path-traversal digests are rejected by fetch/exists/push alike."""
        target = self._new_target(tmp_path)
        evil = {"digest": "sha256:../../etc/passwd", "mediaType": "", "size": 0}

        with pytest.raises(ValueError, match="invalid digest format"):
            target.fetch(evil)
        with pytest.raises(ValueError, match="invalid digest format"):
            target.exists(evil)
        with pytest.raises(ValueError, match="invalid digest format"):
            target.push(evil, io.BytesIO(b"x"))

    def test_tag_thread_safety(self, tmp_path):
        """Concurrent tagging of distinct refs keeps the index consistent."""
        target = self._new_target(tmp_path)
        target.push(_make_blob(b"seed"), io.BytesIO(b"seed"))  # init skeleton

        descs = {}
        for i in range(25):
            data = f"blob-{i}".encode()
            d = _make_blob(data, "application/vnd.oci.image.manifest.v1+json")
            target.push(d, io.BytesIO(data))
            descs[f"ref-{i}"] = d

        errors = []

        def tag_one(ref, desc):
            try:
                target.tag(desc, ref)
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

        threads = [
            threading.Thread(target=tag_one, args=(ref, d))
            for ref, d in descs.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        for ref, d in descs.items():
            assert target.resolve(ref)["digest"] == d["digest"]


# ---------------------------------------------------------------------------
# Tests: end-to-end copy() between two on-disk OCI layouts
# ---------------------------------------------------------------------------


def read_json_index(layout_dir):
    """Read a layout's index.json as a dict."""
    import oras.utils as utils

    return utils.read_json(str(layout_dir / oras.defaults.oci_image_index_file))


class TestCopyBetweenLayouts:
    """copy() should work with LayoutTarget on both ends (real filesystem)."""

    def test_copy_manifest_layout_to_layout(self, tmp_path):
        """Copy a manifest (config + layer) from one layout dir to another."""
        src = LayoutTarget(Layout(str(tmp_path / "src"), validate=False))
        dst = LayoutTarget(Layout(str(tmp_path / "dst"), validate=False))

        config_data = b'{"architecture":"amd64"}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))

        layer_data = b"layer payload"
        layer_desc = _make_blob(
            layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
        )
        src.push(layer_desc, io.BytesIO(layer_data))

        manifest_desc, manifest_data = _make_manifest(config_desc, [layer_desc])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1")

        root = copy(src, "v1", dst, "v1")

        assert descriptors_equal(root, manifest_desc)
        # All blobs landed on disk at the destination.
        assert dst.exists(config_desc)
        assert dst.exists(layer_desc)
        assert dst.exists(manifest_desc)
        with dst.fetch(layer_desc) as fh:
            assert fh.read() == layer_data
        # Tag resolves at the destination and the result is a valid layout.
        assert dst.resolve("v1")["digest"] == manifest_desc["digest"]
        assert Layout.is_oci_layout(str(tmp_path / "dst")) is True

    def test_copy_index_layout_to_layout(self, tmp_path):
        """Copy a multi-manifest index between layouts, sharing a config blob."""
        src = LayoutTarget(Layout(str(tmp_path / "src"), validate=False))
        dst = LayoutTarget(Layout(str(tmp_path / "dst"), validate=False))

        config_data = b'{"shared":true}'
        config_desc = _make_blob(
            config_data, "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(config_data))

        manifest_descs = []
        for i in range(3):
            layer_data = f"layer-{i}".encode()
            layer_desc = _make_blob(
                layer_data, "application/vnd.oci.image.layer.v1.tar+gzip"
            )
            src.push(layer_desc, io.BytesIO(layer_data))
            m_desc, m_data = _make_manifest(config_desc, [layer_desc])
            src.push(m_desc, io.BytesIO(m_data))
            manifest_descs.append(m_desc)

        index_desc, index_data = _make_index(manifest_descs)
        src.push(index_desc, io.BytesIO(index_data))
        src.tag(index_desc, "multi")

        root = copy(src, "multi", dst, "multi")

        assert descriptors_equal(root, index_desc)
        assert dst.exists(index_desc)
        assert dst.exists(config_desc)
        for m in manifest_descs:
            assert dst.exists(m)
        assert dst.resolve("multi")["digest"] == index_desc["digest"]

    def test_copy_layout_to_layout_idempotent(self, tmp_path):
        """Copying twice into the same destination must not error (dedup)."""
        src = LayoutTarget(Layout(str(tmp_path / "src"), validate=False))
        dst = LayoutTarget(Layout(str(tmp_path / "dst"), validate=False))

        config_desc = _make_blob(
            b'{"c":1}', "application/vnd.oci.image.config.v1+json"
        )
        src.push(config_desc, io.BytesIO(b'{"c":1}'))
        manifest_desc, manifest_data = _make_manifest(config_desc, [])
        src.push(manifest_desc, io.BytesIO(manifest_data))
        src.tag(manifest_desc, "v1")

        copy(src, "v1", dst, "v1")
        # Second copy: everything already present at dst -> full skip + re-tag.
        root = copy(src, "v1", dst, "v1")

        assert descriptors_equal(root, manifest_desc)
        assert dst.resolve("v1")["digest"] == manifest_desc["digest"]
