import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(
    os.environ.get(
        "OAUTH_SYNC_DISPATCH_SCRIPT",
        Path(__file__).resolve().parents[1] / "tools" / "oauth_sync_dispatch.sh",
    )
).resolve()


@unittest.skipUnless(Path("/bin/sh").exists(), "requires a POSIX shell")
class OauthSyncDispatchTest(unittest.TestCase):
    def test_failed_full_dispatch_does_not_advance_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "oauth-sync-dispatch.sh"
            shutil.copy2(SCRIPT, script)
            script.chmod(0o755)
            (root / "github_dispatch_token").write_text("test-token\n", encoding="utf-8")

            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                "#!/bin/sh\n"
                "out=''\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  case \"$1\" in\n"
                "    -o) out=\"$2\"; shift 2 ;;\n"
                "    -w) shift 2 ;;\n"
                "    *) shift ;;\n"
                "  esac\n"
                "done\n"
                "[ -z \"$out\" ] || printf '%s' '{\"message\":\"Bad credentials\"}' > \"$out\"\n"
                "printf '%s' '401'\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o755)

            full_state = root / "afdian-full-state"
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                    "SYNC_LOG": str(root / "sync.log"),
                    "AFDIAN_FULL_SYNC_STATE_FILE": str(full_state),
                    "BILI_INCREMENTAL_SYNC_STATE_FILE": str(root / "bili-incremental-state"),
                    "BILI_FULL_SYNC_STATE_FILE": str(root / "bili-full-state"),
                }
            )

            result = subprocess.run(
                ["/bin/sh", str(script)],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertFalse(full_state.exists())
            self.assertIn("afdian_full failed HTTP 401", (root / "sync.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
