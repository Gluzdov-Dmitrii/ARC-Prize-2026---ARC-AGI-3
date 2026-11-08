"""Use the packaged DOCX renderer with Word COM conversion on Windows.

LibreOffice is not bundled for this Windows runtime. This adapter preserves the
packaged OOXML checks, sizing, and page PNG workflow, and substitutes only its
DOCX-to-PDF converter. No desktop LibreOffice or global package installs are used.
"""
from __future__ import annotations

import functools
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


RUNTIME = Path(r"C:\Users\Dmitry\.cache\codex-runtimes\codex-primary-runtime\dependencies")
RENDERER = Path(r"C:\Users\Dmitry\.codex\plugins\cache\openai-primary-runtime\documents\26.909.12148\skills\documents\render_docx.py")
POPLER = RUNTIME / "native" / "poppler" / "Library" / "bin"
CONVERTER = Path(__file__).with_name("word_to_pdf.ps1")
POWERSHELL = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def convert_with_word(doc_path, user_profile, convert_tmp_dir, stem, verbose):
    """The same conversion contract as the packaged render_docx.py."""
    del user_profile
    pdf_path = Path(convert_tmp_dir) / f"{stem}.pdf"
    command = [
        str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Sta",
        "-ExecutionPolicy", "Bypass", "-File", str(CONVERTER),
        "-InputPath", str(Path(doc_path).resolve()),
        "-OutputPath", str(pdf_path.resolve()),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Word PDF export exceeded 180 seconds") from error
    log = f"Word COM exit: {result.returncode}\n{result.stdout}\n{result.stderr}"
    if verbose:
        print(log)
    if pdf_path.is_file() and pdf_path.stat().st_size > 0:
        if result.returncode != 0:
            log += "\nWARNING: Word produced a PDF but exited nonzero; preserving it for PDF validation and page QA."
            print(log)
        return str(pdf_path), log
    return "", log


def main():
    if sys.platform != "win32":
        raise RuntimeError("This adapter is for the bundled Windows runtime")
    for required in (RENDERER, POPLER / "pdftoppm.exe", POPLER / "pdfinfo.exe", CONVERTER, POWERSHELL):
        if not required.is_file():
            raise FileNotFoundError(required)
    spec = importlib.util.spec_from_file_location("packaged_docx_renderer", RENDERER)
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    renderer.convert_to_pdf = convert_with_word
    renderer.convert_from_path = functools.partial(renderer.convert_from_path, poppler_path=str(POPLER))
    renderer.pdfinfo_from_path = functools.partial(renderer.pdfinfo_from_path, poppler_path=str(POPLER))
    renderer.main()


if __name__ == "__main__":
    main()
