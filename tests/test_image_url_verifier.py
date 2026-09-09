import pytest

from app.images import url_verifier


@pytest.mark.asyncio
async def test_verify_image_url_reuses_cached_result(monkeypatch):
    url_verifier.clear_image_verification_cache()
    calls = 0

    async def fake_probe(url):
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(url_verifier, "_probe", fake_probe)

    assert await url_verifier.verify_image_url("https://cdn.example.com/a.jpg") is True
    assert await url_verifier.verify_image_url("https://cdn.example.com/a.jpg") is True
    assert calls == 1


@pytest.mark.asyncio
async def test_verify_image_urls_deduplicates(monkeypatch):
    url_verifier.clear_image_verification_cache()

    async def fake_probe(url):
        return url.endswith(".jpg")

    monkeypatch.setattr(url_verifier, "_probe", fake_probe)

    result = await url_verifier.verify_image_urls([
        "https://cdn.example.com/a.jpg",
        "https://cdn.example.com/a.jpg",
        "https://cdn.example.com/b.txt",
        None,
    ])

    assert result == {
        "https://cdn.example.com/a.jpg": True,
        "https://cdn.example.com/b.txt": False,
    }


def test_image_magic_bytes_are_checked():
    assert url_verifier._looks_like_image("image/jpeg", b"\xff\xd8\xffabc") is True
    assert url_verifier._looks_like_image("image/jpeg", b"not-an-image") is False
    assert url_verifier._looks_like_image("image/png", b"\x89PNG\r\n\x1a\nabc") is True
    assert url_verifier._looks_like_image("image/png", b"GIF89a") is False
    assert url_verifier._looks_like_image("image/webp", b"RIFFxxxxWEBPabc") is True
    assert url_verifier._looks_like_image("text/html", b"<html>") is False
