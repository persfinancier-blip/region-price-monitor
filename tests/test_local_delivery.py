import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_delivery", ROOT / "tools" / "local_delivery.py")
local_delivery = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(local_delivery)


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class LocalDeliveryGitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "seed"

        run("git", "init", "--bare", str(self.remote))
        run("git", "init", str(self.seed))
        run("git", "config", "user.email", "test@example.com", cwd=self.seed)
        run("git", "config", "user.name", "Test", cwd=self.seed)
        (self.seed / ".gitignore").write_text("runtime/\n", encoding="utf-8")
        (self.seed / "file.txt").write_text("v1\n", encoding="utf-8")
        run("git", "add", ".", cwd=self.seed)
        run("git", "commit", "-m", "initial", cwd=self.seed)
        run("git", "checkout", "-b", "work/g01-implementation", cwd=self.seed)
        run("git", "remote", "add", "origin", str(self.remote), cwd=self.seed)
        run("git", "push", "-u", "origin", "work/g01-implementation", cwd=self.seed)
        self.checkout = self.root / "checkout"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _commit_push(self, text: str) -> None:
        (self.seed / "file.txt").write_text(text, encoding="utf-8")
        run("git", "add", "file.txt", cwd=self.seed)
        run("git", "commit", "-m", text.strip(), cwd=self.seed)
        run("git", "push", "origin", "work/g01-implementation", cwd=self.seed)

    def test_first_clone_and_second_no_change(self) -> None:
        self.assertTrue(
            local_delivery.ensure_checkout(
                self.checkout, str(self.remote), "work/g01-implementation"
            )
        )
        self.assertFalse(
            local_delivery.sync_checkout(
                self.checkout, str(self.remote), "work/g01-implementation"
            )
        )
        self.assertEqual((self.checkout / "file.txt").read_text(), "v1\n")

    def test_fast_forward_update_preserves_ignored_state(self) -> None:
        local_delivery.ensure_checkout(
            self.checkout, str(self.remote), "work/g01-implementation"
        )
        runtime = self.checkout / "runtime"
        runtime.mkdir()
        secret = runtime / "secret.bin"
        secret.write_bytes(b"KEEP-ME")

        self._commit_push("v2\n")
        self.assertTrue(
            local_delivery.sync_checkout(
                self.checkout, str(self.remote), "work/g01-implementation"
            )
        )
        self.assertEqual((self.checkout / "file.txt").read_text(), "v2\n")
        self.assertEqual(secret.read_bytes(), b"KEEP-ME")

    def test_dirty_tracked_checkout_stops_without_overwrite(self) -> None:
        local_delivery.ensure_checkout(
            self.checkout, str(self.remote), "work/g01-implementation"
        )
        (self.checkout / "file.txt").write_text("local edit\n", encoding="utf-8")

        with self.assertRaises(local_delivery.DeliveryError) as ctx:
            local_delivery.sync_checkout(
                self.checkout, str(self.remote), "work/g01-implementation"
            )
        self.assertEqual(ctx.exception.code, "LOCAL_CHECKOUT_DIRTY")
        self.assertEqual((self.checkout / "file.txt").read_text(), "local edit\n")

    def test_wrong_remote_stops(self) -> None:
        local_delivery.ensure_checkout(
            self.checkout, str(self.remote), "work/g01-implementation"
        )
        with self.assertRaises(local_delivery.DeliveryError) as ctx:
            local_delivery.sync_checkout(
                self.checkout, str(self.root / "other.git"), "work/g01-implementation"
            )
        self.assertEqual(ctx.exception.code, "LOCAL_CHECKOUT_WRONG_REMOTE")

    def test_local_commit_stops_as_diverged(self) -> None:
        local_delivery.ensure_checkout(
            self.checkout, str(self.remote), "work/g01-implementation"
        )
        run("git", "config", "user.email", "local@example.com", cwd=self.checkout)
        run("git", "config", "user.name", "Local", cwd=self.checkout)
        (self.checkout / "local.txt").write_text("local commit\n", encoding="utf-8")
        run("git", "add", "local.txt", cwd=self.checkout)
        run("git", "commit", "-m", "local commit", cwd=self.checkout)

        with self.assertRaises(local_delivery.DeliveryError) as ctx:
            local_delivery.sync_checkout(
                self.checkout, str(self.remote), "work/g01-implementation"
            )
        self.assertEqual(ctx.exception.code, "LOCAL_CHECKOUT_DIVERGED")

    def test_products_runtime_isolated_from_tracked_file(self) -> None:
        repo = self.root / "runtime-repo"
        core = repo / "parser" / "core"
        core.mkdir(parents=True)
        tracked = core / "products.json"
        tracked.write_text('{"wb": ["1"], "ozon": []}\n', encoding="utf-8")

        env = local_delivery.prepare_local_runtime(repo)
        local_products = core / "local" / "products.json"
        self.assertEqual(local_products.read_bytes(), tracked.read_bytes())
        self.assertEqual(Path(env["RPM_PRODUCTS"]), local_products)

        local_products.write_text('{"wb": ["2"], "ozon": []}\n', encoding="utf-8")
        self.assertEqual(tracked.read_text(), '{"wb": ["1"], "ozon": []}\n')

    def test_windows_entrypoint_is_ascii_only_and_bootstraps_stale_checkout(self) -> None:
        data = (ROOT / "START_PARSER.bat").read_bytes()
        self.assertTrue(data)
        self.assertTrue(all(byte < 128 for byte in data))
        self.assertNotIn(b"chcp 65001", data.lower())
        self.assertIn(b"work/g01-implementation", data)
        self.assertIn(b"%~dp0region-price-monitor", data)
        self.assertIn(b":bootstrap_helper", data)
        self.assertIn(b"fetch --prune origin", data)
        self.assertIn(b"merge --ff-only", data)
        self.assertIn(b"LOCAL_CHECKOUT_DIRTY", data)
        self.assertIn(b"LOCAL_CHECKOUT_DIVERGED", data)


if __name__ == "__main__":
    unittest.main()
