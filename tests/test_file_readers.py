from __future__ import annotations

from io import RawIOBase

from django.core.files.base import File


def test_file_chunks_accepts_a_reader_without_seek() -> None:
    class Reader:
        def __init__(self) -> None:
            self.parts = iter((b"first", b"second", b""))

        def read(self, size: int = -1) -> bytes:
            return next(self.parts)

    assert list(File(Reader()).chunks()) == [b"first", b"second"]


def test_file_chunks_accepts_an_unseekable_raw_reader() -> None:
    class Reader(RawIOBase):
        def __init__(self) -> None:
            self.parts = iter((b"data", b""))

        def read(self, size: int = -1) -> bytes:
            return next(self.parts)

    assert list(File(Reader()).chunks()) == [b"data"]
