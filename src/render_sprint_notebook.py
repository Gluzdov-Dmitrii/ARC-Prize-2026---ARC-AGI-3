"""Validate the notebook and export a static, offline reading companion.

Optional authoring dependencies: nbformat, nbconvert, beautifulsoup4. They are
not required by the competition notebook itself. No notebook cells execute.
"""
from pathlib import Path

import nbformat
from bs4 import BeautifulSoup
from nbconvert import HTMLExporter


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    notebook_path = root / "output/notebooks/arc3_s10_scoped_memory.ipynb"
    notebook = nbformat.read(notebook_path, as_version=4)
    nbformat.validate(notebook)
    html, _ = HTMLExporter().from_notebook_node(notebook)
    page = BeautifulSoup(html, "html.parser")
    # This notebook has no interactive outputs or LaTeX. Static HTML needs no
    # CDN scripts; removing them makes the reading companion fully offline.
    for script in page.find_all("script"):
        script.decompose()
    for link in page.find_all("link", href=True):
        if link["href"].startswith(("https://", "http://", "//")):
            link.decompose()
    page.html["lang"] = "ru"
    page.title.string = "ARC-AGI-3 · S10 — Notebook"
    hero = page.select_one(".jp-MarkdownCell")
    if hero is not None:
        hero["class"] = list(hero.get("class", [])) + ["arc3-hero"]

    nav = page.new_tag("nav", attrs={"class": "arc3-topbar", "aria-label": "Навигация по ноутбуку"})
    brand = page.new_tag("a", href="#top", attrs={"class": "arc3-brand"})
    brand.string = "ARC / S10"
    nav.append(brand)
    for label, href in (("Содержание", "#contents"), ("Модули", "#modules"),
                        ("Результаты", "#results"), ("Notebook ↓", notebook_path.name)):
        item = page.new_tag("a", href=href)
        item.string = label
        if href == notebook_path.name:
            item["download"] = notebook_path.name
            item["class"] = "arc3-download"
        nav.append(item)
    page.body.insert(0, nav)

    module_descriptions = {
        "arc3_runtime.py": "Режимы, лимиты и паспорт запуска",
        "arc3_s4_baseline.py": "Контрольный алгоритм памяти S4",
        "arc3_s10_memory.py": "Изолированная память и проверка переходов",
        "arc3_evaluation.py": "Экспорт результатов и парное сравнение",
    }
    for cell in list(page.select(".jp-CodeCell")):
        text = cell.get_text("", strip=False)
        if "%%writefile /kaggle/working/" not in text:
            continue
        filename = text.split("%%writefile /kaggle/working/", 1)[1].splitlines()[0].strip()
        details = page.new_tag("details")
        details["class"] = "arc3-module"
        summary = page.new_tag("summary")
        badge = page.new_tag("span", attrs={"class": "arc3-module-badge"})
        badge.string = "PY"
        summary.append(badge)
        name = page.new_tag("strong")
        name.string = filename
        summary.append(name)
        hint = page.new_tag("span", attrs={"class": "arc3-module-hint"})
        hint.string = "раскрыть код"
        summary.append(hint)
        cell.replace_with(details)
        details.append(summary)
        description = page.new_tag("p", attrs={"class": "arc3-module-description"})
        description.string = module_descriptions.get(filename, "Полный исходный код модуля")
        details.append(description)
        details.append(cell)
    style = page.new_tag("style")
    style.string = """
:root {--arc-ink: #172d3d; --arc-muted: #596c77; --arc-accent: #00796f;
       --arc-line: #dfe8e9; --arc-paper: #fff; --arc-soft: #f3f8f7;}
html {scroll-behavior: smooth; scroll-padding-top: 90px;}
body {margin: 0; padding: 0; background: #edf2f3; color: var(--arc-ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;}
main {max-width: 1090px; margin: 26px auto 60px; padding: 38px 44px 56px;
      background: var(--arc-paper); border: 1px solid var(--arc-line); border-radius: 14px;
      box-shadow: 0 14px 45px #172d3d08;}
.arc3-topbar {position: sticky; top: 0; z-index: 10; display: flex; align-items: center;
             gap: 24px; padding: 14px max(24px, calc((100vw - 1090px)/2));
             background: #172d3df5; color: white; font-size: 13px; box-shadow: 0 2px 10px #172d3d20;}
.arc3-topbar a {color: #dbe8e8; text-decoration: none; white-space: nowrap;}
.arc3-topbar a:hover {color: white; text-decoration: underline;}
.arc3-topbar .arc3-brand {font-weight: 750; letter-spacing: 1.5px; color: white; margin-right: auto;}
.arc3-topbar .arc3-download {padding: 7px 12px; border: 1px solid #83aca9; border-radius: 6px;}
.jp-Notebook {padding: 0; background: transparent;}
.jp-Cell {padding: 0; margin: 0 0 18px;}
.jp-InputPrompt, .jp-OutputPrompt {display: none;}
.jp-MarkdownCell {line-height: 1.72; font-size: 15px;}
.jp-RenderedHTMLCommon {font-family: inherit; color: var(--arc-ink); line-height: 1.72;}
.jp-RenderedHTMLCommon h1 {font-size: 42px; line-height: 1.15; letter-spacing: -1.3px;
                         color: var(--arc-ink); font-weight: 750; margin: 0 0 10px;}
.jp-RenderedHTMLCommon h2 {font-size: 26px; color: var(--arc-ink); font-weight: 700;
                         margin: 46px 0 18px; padding-top: 24px; border-top: 1px solid var(--arc-line);}
.jp-RenderedHTMLCommon h3 {font-size: 19px; color: var(--arc-ink); font-weight: 650; margin: 28px 0 14px;}
.jp-RenderedHTMLCommon h4 {font-size: 16px; font-weight: 650; margin: 24px 0 10px;}
.jp-RenderedHTMLCommon a {color: var(--arc-accent); text-underline-offset: 3px;}
.jp-RenderedHTMLCommon a.anchor-link {opacity: .35; font-size: .7em; padding-left: .4em;}
.jp-RenderedHTMLCommon p {margin-bottom: 14px;}
.jp-RenderedHTMLCommon li {margin: 7px 0;}
.jp-RenderedHTMLCommon code {font-size: .88em; padding: 2px 5px; color: #235a58;
                           background: #edf5f3; border-radius: 4px; word-break: break-word;}
.jp-RenderedHTMLCommon pre {border: 1px solid var(--arc-line); border-radius: 8px;
                          background: #f6f8fa; padding: 15px 18px;}
.jp-RenderedHTMLCommon blockquote {margin: 20px 0; padding: 16px 20px; border-left: 3px solid var(--arc-accent);
                                 background: var(--arc-soft); color: #35554f; border-radius: 0 8px 8px 0;}
.jp-RenderedHTMLCommon blockquote p:last-child {margin-bottom: 0;}
.jp-RenderedHTMLCommon table {width: 100%; margin: 18px 0 22px; border-collapse: collapse;
                             font-size: 13px; line-height: 1.6; text-align: left;}
.jp-RenderedHTMLCommon th {padding: 11px 13px; color: #365951; background: #edf5f3;
                          border-bottom: 2px solid #cbded9; font-weight: 650;}
.jp-RenderedHTMLCommon td {padding: 11px 13px; border-bottom: 1px solid var(--arc-line); vertical-align: top;}
.jp-RenderedHTMLCommon tbody tr:nth-child(even) {background: #fafcfc;}
.jp-RenderedHTMLCommon tbody tr:hover {background: #f4f8f7;}
.arc3-hero {padding: 8px 0 20px; border-bottom: 3px solid var(--arc-accent); margin-bottom: 26px;}
.arc3-hero h3:first-of-type {font-size: 23px; color: var(--arc-accent); margin-top: 0; letter-spacing: .2px;}
.arc3-hero table:first-of-type {border: 1px solid var(--arc-line); border-radius: 8px; overflow: hidden;}
.jp-CodeCell {border: 1px solid #e0e7eb; border-radius: 8px; background: #f8fafb; overflow: hidden;}
.jp-CodeCell .jp-InputArea-editor {border: 0; background: transparent; border-radius: 8px;}
.jp-CodeCell .highlight {padding: 15px 18px; max-height: 440px; overflow: auto;}
.jp-CodeCell pre {font-size: 12px; line-height: 1.55; tab-size: 4;}
.arc3-module {margin: 10px 0 22px; border: 1px solid #cfdedd; border-radius: 9px; overflow: hidden;}
.arc3-module summary {cursor: pointer; display: flex; align-items: center; gap: 12px;
                      padding: 15px 18px; color: var(--arc-ink); background: #f1f7f5; list-style: none;}
.arc3-module summary::-webkit-details-marker {display: none;}
.arc3-module summary:before {content: "+"; font-size: 21px; width: 14px; color: var(--arc-accent);}
.arc3-module[open] summary:before {content: "−";}
.arc3-module summary:focus-visible {outline: 3px solid #53a297; outline-offset: -3px;}
.arc3-module-badge {font-size: 10px; font-weight: 800; color: white; background: var(--arc-accent);
                   padding: 3px 5px; border-radius: 4px; letter-spacing: .5px;}
.arc3-module summary strong {font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 13px;}
.arc3-module-hint {margin-left: auto; font-size: 12px; color: var(--arc-muted);}
.arc3-module-description {padding: 13px 20px 0; font-size: 13px; color: var(--arc-muted);}
.arc3-module .jp-CodeCell {margin: 12px; border-color: #e4ebea;}
h1, h2, h3, h4, a[id] {scroll-margin-top: 90px;}
@media(max-width: 760px) {
  main {margin: 0; padding: 26px 17px; border-radius: 0; border: 0;}
  .arc3-topbar {gap: 13px; padding: 12px 16px; font-size: 11px;}
  .arc3-topbar a[href="#modules"] {display: none;}
  .jp-RenderedHTMLCommon h1 {font-size: 34px;}
  .jp-RenderedHTMLCommon h2 {font-size: 23px;}
  .jp-RenderedHTMLCommon table {font-size: 11px;}
  .jp-RenderedHTMLCommon th, .jp-RenderedHTMLCommon td {padding: 9px 7px;}
  .arc3-module summary {padding: 13px 11px; gap: 8px;}
  .arc3-module-hint {display: none;}
}
@media print {
  body {background: white;} main {max-width: none; margin: 0; padding: 0; border: 0; box-shadow: none;}
  .arc3-topbar {display: none;} .jp-CodeCell .highlight {max-height: none;}
  .jp-RenderedHTMLCommon h2 {break-after: avoid;}
}
"""
    page.head.append(style)
    out = notebook_path.with_suffix(".html")
    out.write_text(str(page), encoding="utf-8")
    print(f"Validated {len(notebook.cells)} notebook cells; static offline HTML: {out}")


if __name__ == "__main__":
    main()
