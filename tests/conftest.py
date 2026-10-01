"""Ordinary tests never inherit live connection settings from the shell."""

import os

# Paid model smoke is separately authorized by an explicit flag AND budget.
# A key alone never enables it. Atlas is always excluded.
live_opt_in = os.environ.get("DAVINCI_LIVE_SMOKE") == "1" and bool(os.environ.get("DAVINCI_LIVE_BUDGET_USD"))
keep = {"DAVINCI_INTEGRATION"}
if live_opt_in:
    keep.update({"DAVINCI_LIVE_SMOKE", "DAVINCI_LIVE_BUDGET_USD", "OPENAI_API_KEY"})
for name in list(os.environ):
    if name.startswith(("OPENAI_", "MONGODB_", "DAVINCI_")) and name not in keep:
        os.environ.pop(name)
