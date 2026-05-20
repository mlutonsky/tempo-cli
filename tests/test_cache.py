def test_cache_roundtrip():
    from tempo_cli import cache

    cache.put("foo", "bar")
    assert cache.get("foo") == "bar"

    cache.put_nested("issueKey", "STAN-1", 42)
    assert cache.get_nested("issueKey", "STAN-1") == 42

    cache.put_nested("issueKey", "STAN-2", 99)
    assert cache.get_nested("issueKey", "STAN-1") == 42
    assert cache.get_nested("issueKey", "STAN-2") == 99


def test_cache_miss_returns_none():
    from tempo_cli import cache

    assert cache.get("nope") is None
    assert cache.get_nested("a", "b", "c") is None
