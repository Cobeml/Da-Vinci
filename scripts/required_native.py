"""Required CI physics gate: missing images or skipped core tests are failures."""

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS = [
    "tests/product/test_cad.py",
    "tests/product/test_external_cli.py",
    "tests/product/test_simulation.py",
    "tests/product/test_managed.py",
    "tests/product/test_route_parity.py",
]
REQUIRED = {
    "test_native_route_parity",
    "test_native_request_without_pre_authored_directory",
    "test_v2_reference_verification_and_independent_beam_solver",
}


def main():
    for image in ("da-vinci-cad:local", "da-vinci-vtol:local"):
        try:
            subprocess.run(
                ["docker", "image", "inspect", image],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            raise SystemExit(
                f"Required solver image unavailable: {image}. Run davinci setup --template vtol; native checks were NOT run."
            ) from None
    with tempfile.TemporaryDirectory(prefix="davinci-required-native-") as folder:
        report = Path(folder) / "junit.xml"
        env = {**os.environ, "DAVINCI_INTEGRATION": "1"}
        # CI never authorizes paid model calls, even when a credential is configured.
        env.pop("DAVINCI_LIVE_SMOKE", None)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", *TESTS, "-m", "integration", "-q", f"--junitxml={report}"],
            env=env,
        )
        if result.returncode:
            raise SystemExit(result.returncode)
        cases = ET.parse(report).findall(".//testcase")
        passed = {
            c.attrib["name"]
            for c in cases
            if c.find("skipped") is None and c.find("failure") is None and c.find("error") is None
        }
        missing = REQUIRED - passed
        if missing:
            raise SystemExit("Required native tests did not execute: " + ", ".join(sorted(missing)))
        print(
            f"Required native gate: {len(passed)} executed tests; core route parity and physical checks passed."
        )


if __name__ == "__main__":
    main()
