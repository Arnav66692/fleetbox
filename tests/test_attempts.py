import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fleetbox import brain, sandbox
from fleetbox.harness._llm import Reply, ToolCall
from fleetbox.harness._tools import execute

BUGGY = "def add(a, b):\n    return a - b\n"
TEST = "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
CHECK = "python -m pytest -q -p no:cacheprovider test_calc.py"


class Scripted:
    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, system, messages, tools):
        return self.replies.pop(0) if self.replies else Reply("done")


def fix_reply():
    return [Reply("", [ToolCall("1", "edit_file", {"path": "calc.py", "old": "a - b", "new": "a + b"})])]


def cheat_reply():
    return [Reply("", [ToolCall("1", "write_file", {"path": "test_calc.py", "content": "def test_x():\n    pass\n"})])]


def make_project(root: Path) -> None:
    (root / "calc.py").write_text(BUGGY)
    (root / "test_calc.py").write_text(TEST)


def run_with(scripts, root, **kw):
    clients = iter([Scripted([])] + [Scripted(s) for s in scripts])
    with mock.patch("fleetbox.brain._attempts.harness.make_client", side_effect=lambda *a, **k: next(clients)):
        return brain.run_attempts(str(root), "fix add", CHECK, "scripted", n=len(scripts), parallel=1,
                                  out_dir=tempfile.mkdtemp(), **kw)


class EditToolTest(unittest.TestCase):
    def setUp(self):
        self.sid = sandbox.create()
        sandbox.write_file(self.sid, "f.py", "x = 1\ny = 1\n")

    def tearDown(self):
        sandbox.destroy(self.sid)

    def test_edit_replaces_a_unique_snippet(self):
        execute(self.sid, "edit_file", {"path": "f.py", "old": "y = 1", "new": "y = 2"})
        self.assertEqual(sandbox.read_file(self.sid, "f.py").output, "x = 1\ny = 2\n")

    def test_edit_refuses_ambiguous_or_missing_text(self):
        self.assertIn("2 times", execute(self.sid, "edit_file", {"path": "f.py", "old": "= 1", "new": "= 3"}))
        self.assertIn("0 times", execute(self.sid, "edit_file", {"path": "f.py", "old": "z", "new": "w"}))
        self.assertIn("must not be empty", execute(self.sid, "edit_file", {"path": "f.py", "old": "", "new": "w"}))
        self.assertEqual(sandbox.read_file(self.sid, "f.py").output, "x = 1\ny = 1\n")


class AttemptsTest(unittest.TestCase):
    def test_check_decides_pass_and_changed_files_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_project(Path(tmp))
            good, idle = run_with([fix_reply(), []], tmp)
        self.assertTrue(good.passed)
        self.assertEqual(good.changed, ["calc.py"])
        self.assertFalse(idle.passed)
        self.assertEqual(idle.changed, [])

    def test_editing_protected_tests_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_project(Path(tmp))
            (cheat,) = run_with([cheat_reply()], tmp, protect=["test_calc.py"])
        self.assertFalse(cheat.passed)

    def test_diff_trees_finds_deleted_files(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            (Path(a) / "gone.txt").write_text("x")
            (Path(a) / "same.txt").write_text("y")
            (Path(b) / "same.txt").write_text("y")
            (Path(b) / "__pycache__").mkdir()
            (Path(b) / "__pycache__" / "m.pyc").write_bytes(b"\0")
            self.assertEqual(brain.diff_trees(Path(a), Path(b)), ([], ["gone.txt"]))


class BranchTest(unittest.TestCase):
    def test_passing_attempt_becomes_a_branch_and_working_tree_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            make_project(repo)
            git = lambda *a: subprocess.run(["git", "-C", tmp, *a], capture_output=True, text=True, check=True).stdout
            git("init", "-q")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "root")
            git("add", "calc.py", "test_calc.py")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
            (repo / "notes.txt").write_text("uncommitted work")
            source, head = brain.snapshot_head(tmp)
            self.assertFalse((source / "notes.txt").exists())
            (attempt,) = run_with([fix_reply()], source)
            with mock.patch.dict("os.environ", {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}):
                branch = brain.make_branch(tmp, head, attempt, "fix add", "fleetbox/test")
            self.assertEqual(git("show", f"{branch}:calc.py"), BUGGY.replace("a - b", "a + b"))
            self.assertEqual((repo / "calc.py").read_text(), BUGGY)
            self.assertEqual((repo / "notes.txt").read_text(), "uncommitted work")
            self.assertEqual(git("worktree", "list").count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
