"""Render packaging/icon.png (512 px) from the dial's styling. Run: python packaging/make_icon.py"""
import math
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_usage.app import svg_pixmap  # noqa: E402
from claude_usage.core import TEAL, _arc  # noqa: E402

spark = " ".join(
    f"M{256 + 22 * math.sin(math.radians(a)):.1f},{256 - 22 * math.cos(math.radians(a)):.1f} "
    f"L{256 + (120 if i % 2 == 0 else 80) * math.sin(math.radians(a)):.1f},"
    f"{256 - (120 if i % 2 == 0 else 80) * math.cos(math.radians(a)):.1f}"
    for i, a in enumerate(range(0, 360, 45)))
SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
<defs>
 <radialGradient id="face" cx="50%" cy="40%" r="62%"><stop offset="0" stop-color="#1e2b2d"/>
  <stop offset="1" stop-color="#080b0c"/></radialGradient>
 <linearGradient id="bezel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4a5054"/>
  <stop offset=".45" stop-color="#121416"/><stop offset="1" stop-color="#30353a"/></linearGradient>
 <filter id="glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="9" result="b"/>
  <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<circle cx="256" cy="256" r="250" fill="url(#bezel)"/>
<circle cx="256" cy="256" r="232" fill="url(#face)"/>
<circle cx="256" cy="256" r="178" fill="none" stroke="#15302b" stroke-width="30"/>
<path d="{_arc(256, 256, 178, 0, 250)}" fill="none" stroke="{TEAL}" stroke-width="30"
      stroke-linecap="round" filter="url(#glow)"/>
<path d="{spark}" stroke="{TEAL}" stroke-width="26" stroke-linecap="round" filter="url(#glow)"/>
</svg>"""

if __name__ == "__main__":
    app = QApplication([])
    out = Path(__file__).with_name("icon.png")
    svg_pixmap(SVG, 512).save(str(out))
    print("wrote", out)
