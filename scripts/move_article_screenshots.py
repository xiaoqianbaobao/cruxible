"""Move browser screenshots from Trae sandbox dir into the actual article assets dir."""

from __future__ import annotations

import shutil
from pathlib import Path

SANDBOX_PREFIX = Path(
    "/var/folders/hf/g3wtlh1j25x0988gs_mnrtbc0000gn/T/trae/screenshots"
)
TARGET_DIR = Path(
    "/Users/qian/Documents/workspace/cruxible/.poc/article_assets"
)
TARGET_DIR.mkdir(parents=True, exist_ok=True)

src_root = SANDBOX_PREFIX / TARGET_DIR.relative_to("/")
if not src_root.is_dir():
    raise SystemExit(f"source screenshot dir missing: {src_root}")

moved: list[str] = []
for src in sorted(src_root.glob("*.png")):
    dst = TARGET_DIR / src.name
    shutil.move(str(src), str(dst))
    moved.append(f"{dst.name}: {dst.stat().st_size / 1024:.1f} KB")

print("moved:\n -", "\n - ".join(moved) if moved else "(none)")
print("\nTARGET_DIR listing:")
for p in sorted(TARGET_DIR.glob("*.png"), key=lambda x: -x.stat().st_size):
    print(f"  {p.name:70s}  {p.stat().st_size / 1024:7.1f} KB")
