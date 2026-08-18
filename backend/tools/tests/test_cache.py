import uuid

from tools import cache


def _unique_namespace() -> str:
    # Each test gets its own namespace so version counters and keys from one test can't
    # bleed into another via the shared cache backend.
    return f"test-{uuid.uuid4().hex}"


def test_cached_call_computes_once_then_serves_cached() -> None:
    calls = []

    def producer() -> str:
        calls.append(1)
        return "computed"

    key = cache.build_cache_key(_unique_namespace(), "a")
    first = cache.cached_call(key, 60, producer)
    second = cache.cached_call(key, 60, producer)

    assert first == "computed"
    assert second == "computed"
    assert len(calls) == 1


def test_build_cache_key_is_stable_for_the_same_inputs() -> None:
    namespace = _unique_namespace()
    assert cache.build_cache_key(namespace, "a", 1) == cache.build_cache_key(namespace, "a", 1)


def test_build_cache_key_differs_across_namespaces() -> None:
    assert cache.build_cache_key(_unique_namespace(), "a") != cache.build_cache_key(
        _unique_namespace(), "a"
    )


def test_build_cache_key_differs_across_parts() -> None:
    namespace = _unique_namespace()
    assert cache.build_cache_key(namespace, "a") != cache.build_cache_key(namespace, "b")


def test_long_or_unsafe_parts_are_hashed_not_embedded_raw() -> None:
    namespace = _unique_namespace()
    unsafe = "weird key/with spaces?and=stuff&" * 3
    key = cache.build_cache_key(namespace, unsafe)
    assert unsafe not in key


def test_invalidate_namespace_bumps_the_version() -> None:
    namespace = _unique_namespace()
    before = cache.namespace_version(namespace)
    after = cache.invalidate_namespace(namespace)
    assert after == before + 1
    assert cache.namespace_version(namespace) == after


def test_invalidate_namespace_changes_keys_built_after_it() -> None:
    namespace = _unique_namespace()
    key_before = cache.build_cache_key(namespace, "a")
    cache.invalidate_namespace(namespace)
    key_after = cache.build_cache_key(namespace, "a")
    assert key_before != key_after


def test_invalidate_namespace_makes_previously_cached_values_unreachable() -> None:
    namespace = _unique_namespace()
    key_before = cache.build_cache_key(namespace, "a")
    cache.cached_call(key_before, 60, lambda: "first-value")

    cache.invalidate_namespace(namespace)
    key_after = cache.build_cache_key(namespace, "a")

    assert key_after != key_before
    # The old key is a different string now under the bumped version, so a producer keyed
    # off the *current* version recomputes rather than serving the stale value.
    assert cache.cached_call(key_after, 60, lambda: "second-value") == "second-value"
