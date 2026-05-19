from __future__ import annotations

import os
import subprocess

from cdh.tui.commands.registry import command


@command("vim", "Edit a file with vim editor")
def cmd_vim(app, *args):
    if not args:
        return "Usage: /vim <filepath>  - Edit a file with vim"
    path = args[0]
    user_dir = os.path.expanduser("~")
    full_path = os.path.join(user_dir, path) if not os.path.isabs(path) else path

    if not os.path.exists(full_path):
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)

    editor = "vim"
    try:
        subprocess.run(["which", editor], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        editor = "vi"

    try:
        with app.suspend():
            subprocess.call([editor, full_path])
    except Exception as e:
        return f"Error running {editor}: {e}"

    try:
        with open(full_path, "r") as f:
            content = f.read()
        lines = content.split("\n")
        preview = "\n".join(lines[:20])
        if len(lines) > 20:
            preview += f"\n... [{len(lines) - 20} more lines]"
        return f"Edited: {full_path}\n\n{preview}"
    except Exception:
        return f"File saved: {full_path}"
