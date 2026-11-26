"""The release job's merge gate (#55): .github/release_bumps.sh holds the bp-sunnypilot bump only for Ford code that
moved outside the library. The path check has its own self-test; this runs it. .github/ is left out of vendored
copies, so the test skips there."""
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "release_bumps.sh"


@unittest.skipUnless(SCRIPT.exists() and shutil.which("bash"), "needs bash and the library's .github/")
class TestReleaseBumpsGate(unittest.TestCase):
  def test_path_check(self):
    r = subprocess.run(["bash", str(SCRIPT), "--self-test"], capture_output=True, text=True)
    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
  unittest.main()
