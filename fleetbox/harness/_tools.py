from .. import sandbox

TOOLS = [
    {
        "name": "run_command",
        "description": "Run a shell command inside your sandbox (Debian, Python 3.12, no network). Working dir is /workspace. Returns exit code and output.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Shell command to run"}},
            "required": ["command"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file in the sandbox. Paths are relative to /workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path, e.g. main.py"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace one exact snippet of text in a file. old must appear exactly once. Prefer this over write_file for changing existing files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string", "description": "Exact text to replace, including indentation"},
                "new": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old", "new"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the sandbox.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]


def execute(sandbox_id: str, name: str, args: dict) -> str:
    try:
        if name == "run_command":
            res = sandbox.run(sandbox_id, str(args["command"]))
            return f"exit={res.exit_code}\n{res.output}"
        if name == "write_file":
            return sandbox.write_file(sandbox_id, str(args["path"]), str(args["content"])).output
        if name == "edit_file":
            return _edit(sandbox_id, str(args["path"]), str(args["old"]), str(args["new"]))
        if name == "read_file":
            return sandbox.read_file(sandbox_id, str(args["path"])).output
    except KeyError as missing:
        return f"error: missing argument {missing} for tool {name}"
    return f"error: unknown tool {name}. Available: " + ", ".join(t["name"] for t in TOOLS)


def _edit(sandbox_id: str, path: str, old: str, new: str) -> str:
    if not old:
        return "error: old must not be empty. Copy the exact lines you want to replace from read_file output."
    current = sandbox.read_file(sandbox_id, path)
    if current.exit_code != 0:
        return f"error: cannot read {path}: {current.output.strip()}"
    count = current.output.count(old)
    if count != 1:
        return f"error: old text found {count} times in {path}, it must appear exactly once. Read the file and copy the text exactly."
    if len(current.output) >= sandbox.MAX_FILE_READ:
        return f"error: {path} is too large to edit safely, use run_command"
    return sandbox.write_file(sandbox_id, path, current.output.replace(old, new)).output
