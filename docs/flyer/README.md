# Printed hackathon flyer

Print `da-vinci-flyer-letter.pdf` on US Letter or `da-vinci-flyer-a4.pdf` on A4, at 100% / actual size, one-sided. Both have generous printer margins. `preview.png` is a screen preview; use the PDF for printing so text and QR codes remain sharp.

The demo QR uses `https://da-vinci-psi.vercel.app/demo`; the second QR opens `https://github.com/Cobeml/Da-Vinci`. Neither depends on `dvcad.com` DNS. No voting destination was supplied, so neither code is labeled as a direct voting link.

The delivered Letter and A4 PDFs were checked to contain one page each. Both QR codes were decoded successfully from rasterized copies of each PDF, and both destination pages returned HTTP 200.

Images are captured from the live website's actual sensor CAD viewers. The mass values come from `web/data/sensor-gallery.json`; `evidence.json` records the capture and calculation. The editable layout is `flyer.html`.

To regenerate from the repository root:

```bash
npm install --prefix /tmp/davinci-flyer-tools --no-audit --no-fund qrcode jsqr
node scripts/build_flyer.mjs
```

This needs the project's existing Node/Playwright/Sharp dependencies, Playwright Chromium, and network access to the live site. It makes no paid model calls and does not read `.env`. The QR generator verifies both URLs by decoding rasterized versions of its SVG output.
