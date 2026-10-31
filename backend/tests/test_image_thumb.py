"""Unit test untuk pembuatan thumbnail foto.

Tidak butuh server atau MongoDB: hanya menguji fungsi murni di server.py,
supaya regresi ukuran thumbnail langsung ketahuan.
"""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

import server  # noqa: E402


def _make_image(size=(1600, 1200), mode="RGB", fmt="JPEG") -> bytes:
    img = Image.new(mode, size, (200, 120, 60) if mode == "RGB" else (200, 120, 60, 128))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestThumbKey:
    def test_nested_path_keeps_folder(self):
        assert server.thumb_key("app/uploads/u1/abc.jpg") == "app/uploads/u1/thumb_abc.jpg"

    def test_root_path(self):
        assert server.thumb_key("abc.jpg") == "thumb_abc.jpg"

    def test_empty(self):
        assert server.thumb_key("") == ""


class TestThumbnail:
    def test_downscales_to_max_dimension(self):
        src = _make_image((1600, 1200))
        out = server._thumbnail_image_sync(src)
        assert out, "thumbnail tidak terbentuk"
        with Image.open(io.BytesIO(out)) as img:
            assert max(img.size) <= server.THUMB_MAX_DIMENSION
            assert img.format == "JPEG"
        assert len(out) < len(src), "thumbnail harus lebih kecil dari aslinya"

    def test_small_image_is_not_upscaled(self):
        src = _make_image((120, 90))
        out = server._thumbnail_image_sync(src)
        assert out
        with Image.open(io.BytesIO(out)) as img:
            assert img.size == (120, 90)

    def test_rgba_png_becomes_jpeg(self):
        src = _make_image((640, 640), mode="RGBA", fmt="PNG")
        out = server._thumbnail_image_sync(src)
        assert out
        with Image.open(io.BytesIO(out)) as img:
            assert img.mode == "RGB"
            assert img.format == "JPEG"

    def test_invalid_bytes_return_none(self):
        assert server._thumbnail_image_sync(b"bukan gambar") is None
        assert server._thumbnail_image_sync(b"") is None


def test_make_thumbnail_wrapper_matches_sync():
    src = _make_image((800, 600))
    out = asyncio.run(server.make_thumbnail(src))
    assert out and out == server._thumbnail_image_sync(src)


def test_make_thumbnail_never_raises():
    # Data sampah tidak boleh melempar error: upload tetap harus jalan.
    assert asyncio.run(server.make_thumbnail(b"\x00\x01\x02")) is None
