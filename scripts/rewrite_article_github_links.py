"""Rewrite file:// links in WECHAT_DEERFLOW_CRUXIBLE_SETTLEMENT_POC.md to xiaoqianbaobao GitHub HTTP URLs.

Rule:
- file:///Users/qian/Documents/workspace/cruxible/<rest>
  -> https://github.com/xiaoqianbaobao/cruxible/blob/main/<rest>
- file:///Users/qian/Documents/workspace/deer-flow-by-cc/<rest>
  -> https://github.com/xiaoqianbaobao/deer-flow-by-cc/blob/main/<rest>
- file:///Users/qian/Documents/workspace/cruxible-app/<rest>
  -> https://github.com/xiaoqianbaobao/cruxible-app/blob/main/<rest>

Only rewrite links within `[display](url)` markdown and inline bare urls are
not rewritten; we're safe because this article only uses the bracket-paren
markdown link form.
"""

from __future__ import annotations

import re
from pathlib import Path

MD_PATH = (
    Path(__file__).resolve().parent.parent
    / ".poc/WECHAT_DEERFLOW_CRUXIBLE_SETTLEMENT_POC.md"
)

MAPPINGS = [
    (
        "file:///Users/qian/Documents/workspace/cruxible/",
        "https://github.com/xiaoqianbaobao/cruxible/blob/main/",
    ),
    (
        "file:///Users/qian/Documents/workspace/deer-flow-by-cc/",
        "https://github.com/xiaoqianbaobao/deer-flow-by-cc/blob/main/",
    ),
    (
        "file:///Users/qian/Documents/workspace/cruxible-app/",
        "https://github.com/xiaoqianbaobao/cruxible-app/blob/main/",
    ),
]


def _sub(match: re.Match[str]) -> str:
    inner = match.group(1)
    for prefix, replacement in MAPPINGS:
        if inner.startswith(prefix):
            return f"({replacement + inner[len(prefix):]})"
    # No mapping: leave it alone.
    return f"({inner})"


def main() -> None:
    src = MD_PATH.read_text(encoding="utf-8")
    # Captures only the (url) portion of markdown links, leaving [text] alone.
    new_src = re.sub(r"\((file:///[^)\s]+)\)", _sub, src)
    MD_PATH.write_text(new_src, encoding="utf-8")
    changed = sum(1 for a, _ in MAPPINGS if a in src)
    print(f"applied {changed} prefixes")


if __name__ == "__main__":
    main()
