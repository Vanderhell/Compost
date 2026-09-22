from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.backend import NativeBackendError, ReferenceBackend, create_backend  # noqa: E402


class BackendSelectionTests(unittest.TestCase):
    def test_python_backend_is_explicit(self) -> None:
        backend = create_backend("python", payload="AB")
        self.assertIsInstance(backend, ReferenceBackend)

    def test_native_backend_never_silently_falls_back(self) -> None:
        with self.assertRaises(NativeBackendError):
            create_backend("native", library=PROJECT_ROOT / "missing-compost-native.dll")

    def test_native_backend_requires_library(self) -> None:
        with self.assertRaises(NativeBackendError):
            create_backend("native")


if __name__ == "__main__":
    unittest.main()
