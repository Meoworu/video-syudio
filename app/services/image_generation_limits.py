from __future__ import annotations

import threading

from app.config import Settings
from app.store.project_store import ProjectStore


_SEMAPHORE_LOCK = threading.Lock()
_SEMAPHORES: dict[tuple[str, int], threading.BoundedSemaphore] = {}


def image_generation_semaphore(settings: Settings, store: ProjectStore) -> threading.BoundedSemaphore:
    key = (str(store.root.resolve()), settings.google_image_max_concurrency)
    with _SEMAPHORE_LOCK:
        return _SEMAPHORES.setdefault(key, threading.BoundedSemaphore(key[1]))
