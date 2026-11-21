# PyInstaller build for Linux (folder, wrapped into an AppImage), Windows (single .exe)
# and macOS (.app). Run from the repo root:  pyinstaller packaging/claude-usage-dial.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from claude_usage import __version__  # noqa: E402

NAME = "claude-usage-dial"
ICON = str(ROOT / "claude_usage" / "icon.png")  # converted to .ico/.icns by Pillow

a = Analysis(
    [str(ROOT / "packaging" / "run.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "claude_usage" / "fonts"), "claude_usage/fonts"),
           (str(ROOT / "claude_usage" / "icon.png"), "claude_usage")],
    # Only QtCore/Gui/Widgets/Svg/Network (local socket) are used; keep the rest of Qt out.
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf",
              "PySide6.QtOpenGL", "tkinter"],
)
# Linux: leave out Qt's GTK theme plugin and the GTK stack it drags in (not needed, and a
# bundled GTK can clash with the user's), plus font libraries every desktop already has and
# that the AppImage project recommends never bundling. Qt translations are unused too.
DROP = ("libqgtk3", "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libatk-", "libcairo",
        "libpango", "libepoxy", "libfontconfig", "libfreetype", "libharfbuzz")
a.binaries = [b for b in a.binaries if not any(Path(b[0]).name.startswith(d) for d in DROP)]
a.datas = [d for d in a.datas if "/translations/" not in d[0].replace("\\", "/")]

pyz = PYZ(a.pure)

if sys.platform == "win32":
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name=NAME, icon=ICON, console=False,
              upx=False)
else:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, name=NAME, icon=ICON, console=False,
              upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
    if sys.platform == "darwin":
        app = BUNDLE(
            coll, name="Claude Usage Dial.app", icon=ICON,
            bundle_identifier="com.claude-usage-dial",
            info_plist={
                "CFBundleShortVersionString": __version__,
                "LSUIElement": True,            # menu-bar app: no Dock icon
                "NSHighResolutionCapable": True,
            },
        )
