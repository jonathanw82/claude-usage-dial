"""Finding the login token that Claude Code saved on this computer."""

import json
from datetime import datetime, timezone
from pathlib import Path

CREDENTIALS = Path.home() / ".claude" / ".credentials.json"


class UsageError(Exception):
    """A problem with a message that is safe and useful to show the user."""


def read_token():
    try:
        data = json.loads(CREDENTIALS.read_text())
        oauth = data["claudeAiOauth"]
        token = oauth["accessToken"]
    except FileNotFoundError:
        raise UsageError("Not signed in: Claude Code's login file was not found")
    except (KeyError, TypeError, ValueError):
        raise UsageError("Could not read the login from Claude Code's credentials file")
    expires = oauth.get("expiresAt")
    if expires and expires / 1000 < datetime.now(timezone.utc).timestamp():
        raise UsageError("Login expired - open Claude Code once to refresh it")
    return token
