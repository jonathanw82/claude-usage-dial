"""Entry point for frozen builds (PyInstaller needs a script, not `-m`)."""
import sys

from claude_usage.app import main

sys.exit(main())
