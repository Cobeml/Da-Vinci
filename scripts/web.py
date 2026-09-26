"""Load server-only environment and exec Next without forwarding Node CLI flags."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()
command = "start" if "--production" in sys.argv else "dev"
os.execvp(
    "node",
    ["node", "node_modules/next/dist/bin/next", command, "web", "--hostname", "127.0.0.1", "--port", "3215"],
)
