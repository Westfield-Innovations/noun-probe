"""What the repository may hold, and how the package is declared."""

from __future__ import annotations

import os
import pathlib
import subprocess
import unittest

import noun_probe

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORBIDDEN_SUFFIXES = (".docx", ".pdf", ".zip", ".txt")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        if not (ROOT / ".git").exists():
            self.skipTest("not a git checkout")

    def test_repository_holds_no_word_files(self):
        paths = _git("ls-files").splitlines() + _git(
            "log", "--all", "--name-only", "--format="
        ).splitlines()
        offending = [p for p in paths if p.lower().endswith(FORBIDDEN_SUFFIXES)]
        self.assertEqual(offending, [])

    def test_repository_holds_no_words(self):
        # The words live only in a private place; point at them to check.
        words_file = os.environ.get("NOUN_PROBE_WORDS")
        if not words_file:
            self.skipTest("NOUN_PROBE_WORDS is not set")
        history = _git("log", "--all", "-p")
        # The credit lines close the words, and the reader must carry them.
        credit = {
            noun_probe.CREATOR_LINE,
            "Official Noun Probe: " + noun_probe.OFFICIAL_ADDRESS,
            "More Westfield tools: https://azus.ai/tools/",
        }
        lines = pathlib.Path(words_file).read_text("utf-8").splitlines()
        found = [
            line
            for line in lines
            if len(line) >= 40 and line.strip() not in credit and line in history
        ]
        self.assertEqual(found, [], "words found in the history")


class PackageTests(unittest.TestCase):
    def test_readme_has_what_the_spec_lists(self):
        readme = (ROOT / "README.md").read_text("utf-8")
        for needed in (
            noun_probe.OFFICIAL_ADDRESS,
            noun_probe.CREATOR_LINE,
            "import noun_probe",
            "terms published at https://azus.ai/tools/noun-probe/",
        ):
            self.assertIn(needed, readme)

    def test_version_is_declared_once(self):
        pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
        project = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
        self.assertNotIn("\nversion =", project)
        self.assertIn('attr = "noun_probe.__version__"', pyproject)

    def test_license_uses_the_current_packaging_form(self):
        # setuptools stops building a license table or license classifiers
        # after 2027-02-18; an SPDX expression is the form that stays.
        pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
        self.assertRegex(pyproject, r'(?m)^license = "LicenseRef-[A-Za-z0-9.-]+"$')
        self.assertNotIn("License ::", pyproject)


if __name__ == "__main__":
    unittest.main()
