import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.git_identity_guard import audit, configure_local_identity, identity_is_usable


class GitIdentityGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_local_identity_fails_even_when_global_identity_exists(self):
        self.assertFalse(audit(self.repo)["usable"])

    def test_placeholder_local_identity_fails(self):
        subprocess.run(["git", "config", "--local", "user.name", "Your Name"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "--local", "user.email", "you@example.com"], cwd=self.repo, check=True)
        self.assertFalse(audit(self.repo)["usable"])

    def test_configure_writes_only_repository_local_identity(self):
        before_name = subprocess.run(["git", "config", "--global", "--get", "user.name"], text=True, capture_output=True).stdout
        before_email = subprocess.run(["git", "config", "--global", "--get", "user.email"], text=True, capture_output=True).stdout
        configure_local_identity(self.repo, "organicoverlords", "285070168+organicoverlords@users.noreply.github.com")
        self.assertTrue(audit(self.repo)["usable"])
        self.assertEqual(subprocess.run(["git", "config", "--global", "--get", "user.name"], text=True, capture_output=True).stdout, before_name)
        self.assertEqual(subprocess.run(["git", "config", "--global", "--get", "user.email"], text=True, capture_output=True).stdout, before_email)

    def test_placeholder_classifier(self):
        self.assertFalse(identity_is_usable("Your Name", "you@example.com"))
        self.assertFalse(identity_is_usable("worker", "worker@example.invalid"))
        self.assertTrue(identity_is_usable("organicoverlords", "285070168+organicoverlords@users.noreply.github.com"))


if __name__ == "__main__":
    unittest.main()
