import unittest

from fleetbox import harness, sandbox
from fleetbox.harness._llm import Reply, ToolCall, parse_text_tool_calls


class ScriptedClient:
    label = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, system, messages, tools):
        return self.replies.pop(0) if self.replies else Reply("ok")


class SandboxTest(unittest.TestCase):
    def setUp(self):
        self.sid = sandbox.create()

    def tearDown(self):
        sandbox.destroy(self.sid)

    def test_write_then_read_keeps_quotes_newlines_and_unicode(self):
        text = "a = \"x'y\"\nprint('héllo $HOME `ls`')\n"
        self.assertEqual(sandbox.write_file(self.sid, "sub/dir/f.py", text).exit_code, 0)
        self.assertEqual(sandbox.read_file(self.sid, "sub/dir/f.py").output, text)

    def test_nonzero_exit_and_stderr_are_returned(self):
        res = sandbox.run(self.sid, "echo boom >&2; exit 3")
        self.assertEqual(res.exit_code, 3)
        self.assertIn("boom", res.output)

    def test_runaway_command_is_killed(self):
        res = sandbox.run(self.sid, "sleep 30", timeout=2)
        self.assertNotEqual(res.exit_code, 0)

    def test_network_is_off(self):
        res = sandbox.run(self.sid, "python -c \"import urllib.request;urllib.request.urlopen('http://1.1.1.1',timeout=3)\"")
        self.assertNotEqual(res.exit_code, 0)

    def test_sandboxes_do_not_share_files(self):
        other = sandbox.create()
        try:
            sandbox.write_file(self.sid, "secret.txt", "mine")
            self.assertNotEqual(sandbox.read_file(other, "secret.txt").exit_code, 0)
        finally:
            sandbox.destroy(other)

    def test_missing_file_read_fails_cleanly(self):
        self.assertNotEqual(sandbox.read_file(self.sid, "nope.txt").exit_code, 0)


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.sid = sandbox.create()

    def tearDown(self):
        sandbox.destroy(self.sid)

    def test_loop_runs_tools_then_stops_when_no_tool_calls(self):
        client = ScriptedClient([
            Reply("", [ToolCall("1", "write_file", {"path": "a.py", "content": "print(6*7)"})]),
            Reply("", [ToolCall("2", "run_command", {"command": "python a.py"})]),
            Reply("printed 42"),
        ])
        events = []
        result = harness.run_agent("t", self.sid, client, on_event=events.append)
        self.assertEqual(result.status, "done")
        self.assertEqual(result.steps, 3)
        outputs = [e["output"] for e in events if e["type"] == "tool_result"]
        self.assertIn("42", outputs[-1])

    def test_unknown_tool_and_missing_args_become_messages_not_crashes(self):
        client = ScriptedClient([
            Reply("", [ToolCall("1", "rm_rf", {}), ToolCall("2", "write_file", {"path": "x"})]),
            Reply("gave up"),
        ])
        events = []
        result = harness.run_agent("t", self.sid, client, on_event=events.append)
        outputs = [e["output"] for e in events if e["type"] == "tool_result"]
        self.assertEqual(result.status, "done")
        self.assertIn("unknown tool", outputs[0])
        self.assertIn("missing argument", outputs[1])

    def test_step_limit_stops_a_looping_model(self):
        client = ScriptedClient([Reply("", [ToolCall(str(i), "run_command", {"command": "true"})]) for i in range(20)])
        result = harness.run_agent("t", self.sid, client, max_steps=4)
        self.assertEqual(result.status, "step_limit")
        self.assertEqual(result.steps, 4)

    def test_model_error_ends_run_as_error(self):
        class Broken:
            def complete(self, *a):
                raise ConnectionError("model down")
        result = harness.run_agent("t", self.sid, Broken())
        self.assertEqual(result.status, "error")
        self.assertIn("model down", result.summary)


class TextToolCallTest(unittest.TestCase):
    def test_json_tool_calls_in_text_are_parsed(self):
        text = 'Sure.\n```json\n{"name": "write_file", "arguments": {"path": "a.py", "content": "x = {1: 2}"}}\n```\n{"name": "run_command", "arguments": "{\\"command\\": \\"ls\\"}"}'
        calls = parse_text_tool_calls(text, {"write_file", "run_command"})
        self.assertEqual([c.name for c in calls], ["write_file", "run_command"])
        self.assertEqual(calls[0].args["content"], "x = {1: 2}")
        self.assertEqual(calls[1].args, {"command": "ls"})

    def test_plain_json_answers_are_not_tool_calls(self):
        self.assertEqual(parse_text_tool_calls('result: {"name": "bob", "age": 3}', {"run_command"}), [])


class ClientSpecTest(unittest.TestCase):
    def test_bad_spec_is_rejected(self):
        with self.assertRaises(ValueError):
            harness.make_client("openai/gpt")


if __name__ == "__main__":
    unittest.main()
