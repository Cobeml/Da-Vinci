"""Finalist consistency check against XFOIL; not independent experimental validation."""

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from surface_geometry import profile, stations


def crosscheck(spec, audit):
    rows = []
    count = audit["main_panel_count"]
    ys = np.abs(np.array(audit["panel_y"][:count]))
    for station in (stations(spec)[0], stations(spec)[-1]):
        i = int(np.argmin(abs(ys - station["y"])))
        re = float(audit["local_reynolds"][i])
        alpha = float(audit["local_alpha"][i])
        foil = profile(station["section"])
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            path = Path(td)
            foil.to_airfoil(n_coordinates_per_side=100).write_dat(str(path / "foil.dat"))
            commands = f"PLOP\nG\n\nLOAD foil.dat\nPANE\nOPER\nVISC {re}\nITER 200\nPACC\n\n\nASEQ {alpha - 1} {alpha + 1} .5\nPACC\nPWRT\npolar.txt\n\nQUIT\n"
            subprocess.run(
                ["xfoil"],
                input=commands,
                text=True,
                cwd=td,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=100,
            )
            data = []
            if (path / "polar.txt").exists():
                for line in (path / "polar.txt").read_text().splitlines():
                    try:
                        values = [float(x) for x in line.split()]
                        if len(values) >= 7:
                            data.append(values)
                    except ValueError:
                        pass
            errors = []
            for point in data:
                n = foil.get_aero_from_neuralfoil(alpha=point[0], Re=re, model_size="xlarge")
                errors.append(
                    {
                        "alpha_deg": point[0],
                        "xfoil_cl": point[1],
                        "xfoil_cd": point[2],
                        "cl_error": abs(float(np.asarray(n["CL"]).item()) - point[1]),
                        "cd_relative_error": abs(float(np.asarray(n["CD"]).item()) / point[2] - 1),
                    }
                )
            rows.append(
                {
                    "fraction": station["fraction"],
                    "reynolds": re,
                    "points": errors,
                    "passed": len(errors) >= 3
                    and all(x["cl_error"] <= 0.10 and x["cd_relative_error"] <= 0.20 for x in errors),
                }
            )
    return {
        "passed": all(r["passed"] for r in rows),
        "sections": rows,
        "scope": "Consistency against training solver, not flight evidence",
    }


if __name__ == "__main__":
    r = json.loads(Path("/input/request.json").read_text())
    Path("/output/result.json").write_text(json.dumps(crosscheck(r["geometry"], r["audit"]), allow_nan=False))
