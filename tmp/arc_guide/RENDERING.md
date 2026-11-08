# DOCX render setup

The canonical packaged `render_docx.py` is loaded by the task-local adapter of
the same name. Only `convert_to_pdf` is substituted with Microsoft Word COM;
the packaged sizing, rasterization, naming and optional PDF output remain in
use. There is no bundled LibreOffice in this Windows runtime, and installed
desktop LibreOffice is never used.

Run from the project directory, with `exec_command` permission
`sandbox_permissions: "require_escalated"` (Word COM activation inside the
sandbox fails with `0x80070520`, while the approved outside-sandbox probe
succeeds):

```powershell
& 'C:\Users\Dmitry\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' '.\tmp\arc_guide\render_docx.py' 'PATH_TO_GUIDE.docx' --output_dir '.\tmp\arc_guide\render_v1' --emit_pdf --verbose
```

Use a fresh versioned output directory after each revision so that old page
PNGs cannot be confused with the new page count. The PDF and page PNGs are QA
intermediates. Inspect every `page-N.png` after successful conversion.

The converter creates a separate hidden Word instance, refuses any instance
that already has open documents, disables macros, opens only the specified
DOCX read-only with no recent-file entry, exports PDF, and closes only its
own document and empty instance. It neither deletes files nor changes global
Word settings. No Python packages were installed.

Setup checks on 2026-09-22:

- Dependency paths verified with `load_workspace_dependencies`.
- Canonical renderer import and `--help`: pass.
- Bundled Poppler executable: version 26.07.0, pass.
- PowerShell script parse: pass.
- Separate Word COM activation outside sandbox: version 16.0, zero open
  documents, closed successfully.
- Full DOCX to PNG conversion succeeded for the guide in `render_v3` after
  rebuilding the root-authored document. Word COM and renderer both exited 0.
  Parameterless `Close()` and `Quit()` avoid Windows PowerShell COM optional
  argument binding errors; the task document is marked saved in memory and
  closed without writing to its read-only source. Successful PDFs are retained
  even if a later cleanup operation reports a warning.
- No artifact authoring marker was run by the rendering worker.
