"""Build and archive XFOIL viscous polars without API or database access."""

import json
from pathlib import Path

from davinci.config import Settings
from davinci.runner import Runner

CODE = r"""
import subprocess, tempfile, pathlib, json
polars=[]
for code in ('2412','0012'):
 for re in (100000,150000,250000,400000,600000,1000000):
  with tempfile.TemporaryDirectory(dir='/tmp') as td:
   cmds=f'PLOP\nG\n\nNACA {code}\nPANE\nOPER\nVISC {re}\nITER 150\nPACC\n\n\nASEQ 0 12 .5\nINIT\nASEQ -.5 -6 -.5\nPACC\nPWRT\npolar.txt\n\nQUIT\n'
   proc=subprocess.run(['xfoil'],input=cmds,text=True,cwd=td,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
   path=pathlib.Path(td)/'polar.txt'
   rows=[]
   if path.exists():
    for line in path.read_text().splitlines():
     try:
      vals=[float(x) for x in line.split()]
      if len(vals)>=7: rows.append(vals[:5])
     except ValueError: pass
   if len(rows)<15: raise RuntimeError(f'XFOIL {code} Re {re} returned {len(rows)} points: '+proc.stdout[-3400:])
   polars.append(dict(airfoil=code,reynolds=re,columns=['alpha','cl','cd','cdp','cm'],rows=sorted(rows)))
   print(code,re,len(rows),flush=True)
pathlib.Path('/output/polars.json').write_text(json.dumps({'solver':'XFOIL 6.99','ncrit':9,'polars':polars},indent=2))
"""
if __name__ == "__main__":
    runner = Runner(Settings(_env_file=None))
    outputs, _, _ = runner.execute(
        "/input/prepare.py", {"prepare.py": CODE}, timeout=900, image="da-vinci-vtol:local"
    )
    path = Path("sandbox/vtol_data/polars.json")
    path.write_bytes(outputs["polars.json"])
    data = json.loads(path.read_text())
    print("Saved", len(data["polars"]), "converged XFOIL polar tables")
