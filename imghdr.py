"""Compatibility shim for packages that still import the removed stdlib imghdr.

Python 3.13 removed ``imghdr``. The mtcnn-opencv package imports it at module
load time, so this small subset keeps that package usable on Python 3.14.
"""

from __future__ import annotations


def what(file, h: bytes | None = None) -> str | None:
    """Return a simple image type name for common enrollment image formats."""
    if h is None:
        if file is None:
            return None
        with open(file, "rb") as image_file:
            h = image_file.read(32)

    if h.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if h.startswith(b"BM"):
        return "bmp"
    if h.startswith(b"RIFF") and h[8:12] == b"WEBP":
        return "webp"
    return None
