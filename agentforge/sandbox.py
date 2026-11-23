"""Run Python in a subprocess inside a throwaway directory that holds a copy of kiln.

This isolates the working directory and import path, and enforces a timeout. It is not a
security boundary: the code runs as the current user.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import kiln

KILN_DIR = Path(kiln.__file__).parent
MAX_OUTPUT = 4000


class Workdir:
    def __init__(self):
        self.path = Path(tempfile.mkdtemp(prefix="agentforge-"))
        shutil.copytree(KILN_DIR, self.path / "kiln", ignore=shutil.ignore_patterns("__pycache__"))

    def write(self, name, text):
        (self.path / name).write_text(text)

    def run(self, code, timeout=10):
        """Run code as a script; return combined stdout and stderr, truncated."""
        self.write("_main.py", code)
        return self.run_file("_main.py", timeout)

    def run_file(self, name, timeout=10):
        # -S and -E keep the project's own packages (tasks, hidden tests) off the import path.
        try:
            proc = subprocess.run(
                [sys.executable, "-S", "-E", name],
                cwd=self.path, capture_output=True, text=True, timeout=timeout,
            )
            out = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            out = f"TimeoutError: no result after {timeout} seconds"
        if len(out) > MAX_OUTPUT:
            out = out[:MAX_OUTPUT] + "\n[output truncated]"
        return out or "(no output)"

    def close(self):
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
