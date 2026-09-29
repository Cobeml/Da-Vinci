# Third-party notices

The Apache-2.0 project license applies to original Da Vinci code. Dependencies, external solver sources, measured datasets, and their generated distributions retain their own licenses and attribution requirements.

- **CadQuery / OCP / OpenCascade:** CAD generation and STEP/GLB export. Consult the distributions' Apache/LGPL terms and notices. These run in separately built Docker images.
- **AeroSandbox:** aerodynamic and flight-performance calculations; preserve its upstream license and dependency notices.
- **XFOIL 6.99:** downloaded from MIT while building the VTOL Docker image. Its upstream source and license govern distribution of compiled images; project licensing does not replace them.
- **UIUC Propeller Database:** experimental files in `sandbox/vtol_data`, attributed in `sources.json`; original source is https://m-selig.ae.illinois.edu/props/volume-4/propDB-volume-4.html. Preserve dataset attribution. This repository does not assert a new license over the measurements; confirm redistribution terms before a public package release.
- **Next.js, React, Three.js, React Three Fiber/Drei, and yaml:** browser runtime/build dependencies. Preserve license notices emitted with bundled JavaScript and the upstream package licenses.
- **FastAPI, Uvicorn, Pydantic, PyMongo, OpenAI Python SDK, PyYAML, and jsonschema:** Python dependencies installed separately with their distribution metadata and licenses.

The release build produces an inventory of direct Python and browser dependencies. Do not publish binary CAD images or the package until upstream redistribution obligations and data permissions have been reviewed. No third-party model downloads were added for the product demo; it uses this repository's generated study geometry.
