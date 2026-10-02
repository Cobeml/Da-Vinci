"""Fresh-wheel, keyless public-route benchmark with native CAD; run outside checkout."""

import importlib.util
import os
from importlib.resources import files
from pathlib import Path


def main():
    for key in list(os.environ):
        if key.startswith(("OPENAI_", "MONGODB_", "DAVINCI_")) or key == "PYTHONPATH":
            os.environ.pop(key, None)
    import davinci
    from davinci.product.protocol import build_catalog, schema_catalog

    assert "site-packages" in Path(davinci.__file__).parts
    assert importlib.util.find_spec("gmsh") is None
    assert schema_catalog() == build_catalog()
    assert "RecordMeasurement" in schema_catalog()["schemas"]
    assert files("davinci.product").joinpath("static/docs/methodology/index.html").is_file()
    # This entry point controls a service; all benchmark mutations use its HTTP API.
    from run_methodology_benchmark import main as benchmark

    benchmark()


if __name__ == "__main__":
    main()
