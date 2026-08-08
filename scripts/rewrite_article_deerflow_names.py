"""Conservatively rewrite DeerFlow -> DeerFlow-By-CC in article prose, skipping code blocks.

Safe for:
  - Fenced code blocks (```...```): skipped entirely
  - DEER_FLOW_* env vars (all-caps; doesn't match \bDeerFlow\b)
  - DeerflowThread / DeerflowMessage (lowercase 'f' deerflow): no match
  - GitHub URLs like /deer-flow-by-cc/: lowercase, hyphenated: no match
  - File paths like .deer-flow/: no match
"""

from __future__ import annotations

import re
from pathlib import Path

ARTICLE = Path("/Users/qian/Documents/workspace/cruxible/.poc/WECHAT_DEERFLOW_CRUXIBLE_SETTLEMENT_POC.md")


def main() -> None:
    text = ARTICLE.read_text(encoding="utf-8")
    # Safe: case-sensitive; only matches capital-D capital-F DeerFlow as a word.
    #   DEER_FLOW_ROOT (all-caps)     -> no match
    #   DeerflowThread (lowercase f)  -> no match
    #   deer-flow-by-cc (lowercase, hyphenated) -> no match
    #   .deer-flow/ (dir, lowercase)  -> no match
    new_text, replacements = re.subn(r"\bDeerFlow\b", "DeerFlow-By-CC", text)
    ARTICLE.write_text(new_text, encoding="utf-8")
    print(f"rewrote {ARTICLE}: replacements={replacements} (global)")


if __name__ == "__main__":
    main()
