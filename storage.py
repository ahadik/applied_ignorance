"""Shared local JSON persistence; no provider or draft dependencies."""
import json
import os
from pathlib import Path
import tempfile


def save_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as file:
            temp = file.name
            json.dump(data, file, indent=2, allow_nan=False)
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
