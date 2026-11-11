"""Brief 42 H1: context management for the Deep Agents role agents (behind ``--harness-arm H1``).

Two changes, both off by default:

1. **Offload of large tool results** (rtl role). A flow tool's result over ``OFFLOAD_CHARS`` characters is written in full
   to ``<design>/build/tool_results/NNN_<tool>.json`` and the model gets the small fields, a head and a tail of the
   output, and the path to read with ``read_file`` (offset/limit). Knowledge tools (``load_skill`` and the like) are not
   offloaded: their text is what the role asked for. deepagents' own offload (FilesystemMiddleware) is on at 20,000 tokens
   and so never fires on our results, which the registry already clips to 20,000 characters.
2. **Earlier summarisation.** deepagents 0.7.32 does add ``SummarizationMiddleware``, but our chat model has no profile,
   so its trigger is a fixed 170,000 tokens with 6 messages kept; one 80-turn repair visit never reached it. H1 replaces it
   (same middleware name, so it takes the default's slot) with a trigger at ``SUMMARY_TRIGGER_TOKENS`` and
   ``SUMMARY_KEEP_MESSAGES`` kept.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OFFLOAD_CHARS = 6000
HEAD_CHARS = TAIL_CHARS = 1500
SUMMARY_TRIGGER_TOKENS = 40_000
SUMMARY_KEEP_MESSAGES = 10
SMALL_FIELD_CHARS = 1500
OFFLOAD_DIR = ("build", "tool_results")


def offload_result(res: dict[str, Any], design: Path, tool: str, seq: int) -> str:
    """The model-facing text of one tool result: the full JSON when small, else the preview described above."""
    text = json.dumps(res)
    if len(text) <= OFFLOAD_CHARS:
        return text
    d = Path(design).joinpath(*OFFLOAD_DIR)
    d.mkdir(parents=True, exist_ok=True)
    name = f"{seq:03d}_{tool}.json"
    (d / name).write_text(text)
    out = str(res.get("output", ""))
    small = {k: v for k, v in res.items() if k != "output" and len(json.dumps(v)) <= SMALL_FIELD_CHARS}
    dropped = sorted(k for k in res if k != "output" and k not in small)
    preview = {**small, "output_head": out[:HEAD_CHARS],
               "output_tail": out[-TAIL_CHARS:] if len(out) > HEAD_CHARS + TAIL_CHARS else "",
               "output_chars": len(out), "fields_in_file_only": dropped,
               "full_result": f"/{'/'.join(OFFLOAD_DIR)}/{name}",
               "note": f"The result was {len(text)} characters; this is its head and tail. Read the rest with read_file "
                       f"(path, offset, limit) on full_result."}
    return json.dumps(preview)


def summarisation_middleware(model, backend):
    """deepagents' SummarizationMiddleware with H1's trigger; its history file goes to the in-memory backend."""
    from deepagents.middleware.summarization import SummarizationMiddleware
    return SummarizationMiddleware(model=model, backend=backend, trigger=("tokens", SUMMARY_TRIGGER_TOKENS),
                                   keep=("messages", SUMMARY_KEEP_MESSAGES), trim_tokens_to_summarize=None,
                                   truncate_args_settings={"trigger": ("messages", 20), "keep": ("messages", 10)})
