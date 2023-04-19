"""Generate code for this package."""

import os
import subprocess
from pathlib import Path

import openai

from .render import _cmd_for_stats


def main(example_audio_file: Path) -> None:
    """Generate a parser for the stats output of ffmpeg.

    ffmpeg's output is verbose and not easily parsed. A parser would be brittle
    to maintain by hand. Have AI write it for us.
    """
    openai.api_key = os.environ["OPENAI_API_KEY"]

    fn_name = "parse_summary_stats"
    cmd = _cmd_for_stats(example_audio_file)
    proc = subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)
    proc_output = proc.stderr

    messages = [
        {
            "role": "system",
            "content": (
                "You are a CLI that writes Python source code. Do not converse. Do not"
                " show examples. Only respond in Python source code. Always include"
                " function argument and return type annotations. Disable type checking"
                " on lines that return Optionals."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a Python function named {fn_name} to parse the following output"
                " for max volume, LUFS-I, and LRA. Use regular expressions. Return the"
                f" values in a dict.\n\n{proc_output}"
            ),
        },
    ]
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, temperature=0)  # type: ignore[no-untyped-call]
    lines = response.choices[0].message["content"].splitlines()

    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines[-1].startswith("```"):
        lines = lines[:-1]

    out_fil = Path(__file__).parent / "__codegen__" / "stats.py"
    out_fil.write_text("\n".join(lines))

    print(response.usage)
