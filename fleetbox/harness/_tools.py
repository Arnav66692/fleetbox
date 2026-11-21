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
        if name == "read_file":
            return sandbox.read_file(sandbox_id, str(args["path"])).output
    except KeyError as missing:
        return f"error: missing argument {missing} for tool {name}"
    return f"error: unknown tool {name}. Available: run_command, write_file, read_file"
