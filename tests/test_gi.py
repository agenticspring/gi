#!/usr/bin/env python3
"""Unit tests for gi. Run from the repo root:  python3 -m unittest discover -s tests -v"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = WORKDIR / "gi" / "templates"
CLI = [sys.executable, str(WORKDIR / "gi" / "cli.py")]

# The CLI must work from ANY cwd (templates resolve relative to the module,
# never to the cwd), so every subprocess runs from a directory that is not
# the project root.
FOREIGN_CWDS = ["/tmp", "/"]


def run(*args, cwd="/tmp"):
    return subprocess.run(CLI + list(args), cwd=cwd,
                          capture_output=True, text=True, timeout=30)


EXPECTED_TEMPLATES = sorted([
    "c", "cpp", "dotnet", "emacs", "go", "java", "jetbrains", "jupyter",
    "kotlin", "latex", "linux", "macos", "node", "php", "python", "ruby",
    "rust", "swift", "terraform", "vim", "vscode", "windows",
])


class TestList(unittest.TestCase):
    def test_list_contains_all_bundled_templates(self):
        for cwd in FOREIGN_CWDS:
            with self.subTest(cwd=cwd):
                r = run("--list", cwd=cwd)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout.splitlines(), EXPECTED_TEMPLATES)

    def test_template_files_match_listed_names(self):
        on_disk = sorted(p.stem for p in TEMPLATES_DIR.glob("*.gitignore"))
        self.assertEqual(on_disk, EXPECTED_TEMPLATES)


class TestTemplateHygiene(unittest.TestCase):
    def test_each_template_nonempty_no_trailing_whitespace(self):
        files = sorted(TEMPLATES_DIR.glob("*.gitignore"))
        self.assertEqual(len(files), 22)
        for path in files:
            with self.subTest(template=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.strip(), "template is empty")
                for i, line in enumerate(text.split("\n"), 1):
                    self.assertEqual(line, line.rstrip(),
                                     "trailing whitespace on line %d" % i)
                self.assertTrue(text.endswith("\n"))
                self.assertFalse(text.endswith("\n\n"),
                                 "must end with a single newline")


class TestShow(unittest.TestCase):
    def test_show_prints_exact_template(self):
        on_disk = (TEMPLATES_DIR / "python.gitignore").read_text(encoding="utf-8")
        r = run("--show", "python", cwd="/tmp")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, on_disk)

    def test_show_unknown_template_exits_2(self):
        r = run("--show", "cobol")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown template", r.stderr)


class TestMerge(unittest.TestCase):
    def test_merge_dedupes_shared_lines(self):
        r = run("python", "macos", cwd="/tmp")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(lines.count(".DS_Store"), 1,
                         ".DS_Store must appear exactly once after dedupe")

    def test_merge_has_per_template_headers(self):
        r = run("python", "node", "macos")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# ----- python -----", r.stdout)
        self.assertIn("# ----- node -----", r.stdout)
        self.assertIn("# ----- macos -----", r.stdout)

    def test_output_ends_with_single_trailing_newline(self):
        r = run("python", "node")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.endswith("\n"))
        self.assertFalse(r.stdout.endswith("\n\n"))

    def test_case_insensitive_names(self):
        r = run("Python", "MACOS")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# ----- python -----", r.stdout)
        self.assertIn("# ----- macos -----", r.stdout)

    def test_merge_from_foreign_cwd(self):
        for cwd in FOREIGN_CWDS:
            with self.subTest(cwd=cwd):
                r = run("go", "rust", "linux", cwd=cwd)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("target/", r.stdout)
                self.assertIn("*.test", r.stdout)


class TestErrors(unittest.TestCase):
    def test_unknown_template_exits_2_with_helpful_message(self):
        r = run("pythn")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown template 'pythn'", r.stderr)
        self.assertIn("python", r.stderr)  # close-match suggestion
        self.assertIn("--list", r.stderr)

    def test_no_args_exits_2(self):
        r = run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("no templates given", r.stderr)

    def test_mixed_known_and_unknown_rejects(self):
        r = run("python", "notalanguage")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")

    def test_output_to_unwritable_path_exits_1_cleanly(self):
        r = run("python", "-o", "/nonexistent-dir-xyz/x.gitignore")
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot write", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class TestOutputFile(unittest.TestCase):
    def test_output_flag_writes_file(self):
        dest = Path("/tmp/gi_test_output_flag.gitignore")
        try:
            r = run("python", "-o", str(dest))
            self.assertEqual(r.returncode, 0, r.stderr)
            on_disk = dest.read_text(encoding="utf-8")
            r2 = run("python")
            self.assertEqual(on_disk, r2.stdout)
            self.assertTrue(on_disk.endswith("\n"))
            self.assertFalse(on_disk.endswith("\n\n"))
        finally:
            if dest.exists():
                dest.unlink()


class TestMisc(unittest.TestCase):
    def test_version_flag(self):
        r = run("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip().startswith("gi "))

    def test_broken_pipe_exits_quietly(self):
        # `gi python | head -c 10` closes the pipe early; gi must not traceback.
        p1 = subprocess.Popen(CLI + ["python"],
                              stdout=subprocess.PIPE, cwd="/tmp")
        p2 = subprocess.Popen(["head", "-c", "10"], stdin=p1.stdout,
                              stdout=subprocess.PIPE)
        p1.stdout.close()
        p2.communicate(timeout=30)
        p1.wait(timeout=30)
        self.assertEqual(p1.returncode, 0,
                         "broken pipe must exit 0 without traceback")


if __name__ == "__main__":
    unittest.main()
