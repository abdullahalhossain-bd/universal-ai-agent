"""Lightweight structured worker metrics helpers."""
from __future__ import annotations
import time

def timer():
    started=time.monotonic()
    return lambda: round(time.monotonic()-started,3)
