from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from time import monotonic, sleep

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mathematical_organism.compost import CompostController  # noqa: E402
from tools.compost import _print_food, _print_organisms, print_live_view  # noqa: E402


class CompostTests(unittest.TestCase):
    def test_compost_directories_and_bootstrap_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = CompostController(Path(directory) / "sandbox")
            self.assertTrue(all(path.is_dir() for path in (controller.runtime.inbox, controller.runtime.food, controller.runtime.organisms_dir, controller.runtime.corpses_dir, controller.runtime.traces, controller.runtime.results)))
            created = controller.add_organisms(3)
            self.assertEqual(len(created), 3)
            self.assertEqual(len(controller.runtime.organisms), 3)
            self.assertTrue(all((controller.runtime.organism_directory(item.name) / "ALIVE").is_file() for item in created))
            self.assertEqual(len({item.territory_state.territory.path for item in created}), 3)

    def test_generated_food_is_exact_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = CompostController(Path(directory) / "sandbox")
            first = controller.generate_food(1024, seed=7, name="one.bin")
            second = controller.generate_food(1024, seed=7, name="two.bin")
            self.assertEqual(first.path.stat().st_size, 1024)
            self.assertEqual(first.path.read_bytes(), second.path.read_bytes())

    def test_real_file_food_and_cleanup_require_stopped_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "real.bin"; source.write_bytes(b"real food")
            controller = CompostController(root / "sandbox")
            copied = controller.add_real_path(source)
            self.assertEqual(copied[0].read_bytes(), source.read_bytes())
            controller.start()
            with self.assertRaises(RuntimeError): controller.delete_food("all")
            with self.assertRaises(RuntimeError): controller.delete_organisms("all")
            controller.stop(); controller.delete_food("all")
            self.assertEqual(list(controller.runtime.inbox.iterdir()), [])

    def test_observer_views_and_family_tree_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = CompostController(Path(directory) / "sandbox")
            created = controller.add_organisms(3)
            before = [(item.name, item.body.body_mass, item.body.reserve, item.territory_state.territory.path) for item in controller.runtime.organisms]
            with redirect_stdout(StringIO()):
                print_live_view(controller); _print_organisms(controller); _print_food(controller)
            after = [(item.name, item.body.body_mass, item.body.reserve, item.territory_state.territory.path) for item in controller.runtime.organisms]
            self.assertEqual(before, after)
            names = [name for _, name in controller.family_tree(4)]
            self.assertEqual(set(names), {item.name for item in created})

    def test_dead_marker_preserved_and_dead_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = CompostController(Path(directory) / "sandbox")
            organism = controller.add_organisms(1)[0]
            organism._die(controller.runtime)
            marker = controller.runtime.organism_directory(organism.name)
            self.assertTrue((marker / "DEAD").is_file())
            self.assertEqual(controller.delete_organisms("dead"), 1)
            self.assertFalse(marker.exists())

    def test_clear_sandbox_removes_only_requested_experiment_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = CompostController(Path(directory) / "sandbox")
            controller.add_organisms(1)
            controller.generate_food(128, seed=1)
            controller.clear("food")
            self.assertEqual(list(controller.runtime.inbox.iterdir()), [])
            self.assertEqual(controller.runtime.food_sources, {})
            self.assertEqual(len(controller.runtime.organisms), 1)
            controller.clear("everything")
            self.assertEqual(controller.runtime.organisms, [])
            self.assertTrue(all(path.is_dir() for path in (controller.runtime.inbox, controller.runtime.food, controller.runtime.organisms_dir, controller.runtime.corpses_dir, controller.runtime.traces, controller.runtime.results)))

    def test_small_real_runtime_run_has_exact_food_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = CompostController(Path(directory) / "sandbox", block_size=4096)
            controller.add_organisms(10)
            controller.generate_food(8 * 1024, seed=12345)
            controller.start(); deadline = monotonic() + 10.0
            while monotonic() < deadline and controller.snapshot()["food_eaten"] < 8 * 1024:
                sleep(0.01)
            controller.stop(); view = controller.snapshot()
            self.assertEqual(view["food_eaten"], 8 * 1024)
            self.assertEqual(view["food_remaining"], 0)
            self.assertEqual(view["duplicates"], 0)
            self.assertEqual(view["food_missing"], 0)
            self.assertTrue((controller.runtime.organism_directory("ORG-ROOT") / "state.json").is_file())


if __name__ == "__main__":
    unittest.main()
