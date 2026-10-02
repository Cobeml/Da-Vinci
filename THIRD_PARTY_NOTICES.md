# Third-party notices

The Apache-2.0 project license applies to original Da Vinci code. Dependencies, external solver sources, measured datasets, and their generated distributions retain their own licenses and attribution requirements.

- **CadQuery / OCP / OpenCascade:** CAD generation and STEP/GLB export. Consult the distributions' Apache/LGPL terms and notices. These run in separately built Docker images.
- **AeroSandbox:** aerodynamic and flight-performance calculations; preserve its upstream license and dependency notices.
- **XFOIL 6.99:** downloaded from MIT while building the VTOL Docker image. Its upstream source and license govern distribution of compiled images; project licensing does not replace them.
- **UIUC Propeller Database:** experimental files in `sandbox/vtol_data`, attributed in `sources.json`; original source is https://m-selig.ae.illinois.edu/props/volume-4/propDB-volume-4.html. Preserve dataset attribution. This repository does not assert a new license over the measurements; confirm redistribution terms before a public package release.
- **Next.js, React, Three.js, React Three Fiber/Drei, and yaml:** browser runtime/build dependencies. Preserve license notices emitted with bundled JavaScript and the upstream package licenses.
- **FastAPI, Uvicorn, Pydantic, PyMongo, OpenAI Python SDK, PyYAML, and jsonschema:** Python dependencies installed separately with their distribution metadata and licenses.

The release build produces an inventory of direct Python and browser dependencies. Do not publish binary CAD images or the package until upstream redistribution obligations and data permissions have been reviewed. No third-party model downloads were added for the product demo; it uses this repository's generated study geometry.

## Optional structural runtime

The optional `sandbox/Dockerfile.structural` builds CalculiX 2.23 (GPL-2.0-or-later) from the checksum-pinned [official source](https://www.dhondt.de/ccx_2.23.src.tar.bz2) and SPOOLES 2.2 from the checksum-pinned [Netlib distribution](https://www.netlib.org/linalg/spooles/spooles.2.2.html), whose release is public domain. The documented Tree makefile correction and compiler/linker flags are recorded in the Dockerfile. Gmsh 4.15.2 is installed only in this explicitly built runtime; its [license](https://gmsh.info/doc/texinfo/#License) is GPL-2.0-or-later. These packages retain their own licenses and notices; Apache-2.0 licensing of Da Vinci does not relicense them. The Python wheel contains adapter code/build instructions, not these solver binaries. Anyone redistributing a built solver image must retain applicable notices and meet its corresponding-source obligations.
