"""Validate generated notebook identity and executable cells without a GPU."""
import ast
import hashlib
import json
from pathlib import Path

from src.build_sprint_notebook import OUT, PARENT, ROOT


def main() -> None:
    path = OUT / "arc3_s10_scoped_memory.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads((OUT / "build_manifest.json").read_text())
    assert manifest["notebook_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] == 5
    assert len({cell["id"] for cell in nb["cells"]}) == len(nb["cells"])
    embedded = {}
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] != "code":
            continue
        assert cell["outputs"] == [] and cell["execution_count"] is None
        text = "".join(cell["source"])
        if text.startswith("%%writefile"):
            first, text = text.split("\n", 1)
            embedded[first.rsplit("/", 1)[-1]] = text
        compile(text, f"cell_{i}", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    for output, source in {
        "arc3_runtime.py": "sprint_runtime.py",
        "arc3_s10_memory.py": "s10_scoped_no_impact.py",
        "arc3_evaluation.py": "sprint_evaluation.py",
    }.items():
        assert embedded[output].strip() == (ROOT / "src" / source).read_text(encoding="utf-8").strip()
    old = json.loads(PARENT.read_text(encoding="utf-8"))
    tree = ast.parse("".join(old["cells"][13]["source"]))
    champion = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "S4_SOURCE" for t in n.targets))
    assert embedded["arc3_s4_baseline.py"].strip() == champion.strip()
    metadata = json.loads((OUT / "kernel-metadata.json").read_text())
    assert metadata["is_private"] and not metadata["enable_internet"]
    assert metadata["machine_shape"] == "NvidiaRtxPro6000"
    assert metadata["code_file"] == path.name
    html = path.with_suffix(".html").read_text(encoding="utf-8")
    assert "<script" not in html
    assert html.count('class="arc3-module"') == 4
    result = {"valid": True, "notebook_sha256": manifest["notebook_sha256"],
              "cells": len(nb["cells"]), "embedded_modules": len(embedded),
              "champion_source_identical": True, "all_cells_compile": True,
              "html_offline_scripts": 0, "html_expandable_modules": 4}
    (OUT / "artifact_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
