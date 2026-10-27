"""Shared helper for the notebook generators: build, execute (so outputs are saved) and write a notebook."""

from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell


def build(name: str, cells: list, timeout: int = 600) -> None:
    nb = nbf.v4.new_notebook(
        cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}}
    )
    ExecutePreprocessor(timeout=timeout, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).preprocess(
        nb, {"metadata": {"path": str(ROOT)}}
    )
    out = ROOT / "notebooks" / name
    nbf.write(nb, out)
    print("wrote", out.relative_to(ROOT))
