"""Ordinary tests never inherit live connection settings from the shell."""

import os

# Run before test module imports. Live validation is explicitly invoked through
# scripts.validate_atlas, never through this suite.
for name in list(os.environ):
    if name.startswith(("OPENAI_", "MONGODB_", "DAVINCI_")) and name != "DAVINCI_INTEGRATION":
        os.environ.pop(name)
