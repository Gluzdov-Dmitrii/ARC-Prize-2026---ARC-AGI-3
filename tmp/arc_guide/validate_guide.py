from pathlib import Path
import ast, contextlib, io, json, re
from zipfile import ZipFile
from lxml import etree
from docx import Document
from pypdf import PdfReader

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
path=ROOT/'output/documents/ARC_Prize_2026_Руководство_для_начинающего.docx'
source=(BASE/'content.py').read_text(encoding='utf-8')
tree=ast.parse(source)
samples=[]
for node in ast.walk(tree):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='code' and node.args:
        v=ast.literal_eval(node.args[0])
        if 'human = [10' in v:samples.append(v)
assert len(samples)==1
output=io.StringIO()
with contextlib.redirect_stdout(output):exec(compile(samples[0],'<guide_example>','exec'),{})
assert output.getvalue().strip()=='23.57'

d=Document(path)
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
xml=d._element
paragraphs=[p.text for p in d.paragraphs]
assert not any(x in '\n'.join(paragraphs) for x in ['TODO','TBD','turn0search','turn1view'])
assert len(d.inline_shapes)==7
assert len(xml.findall('.//m:oMath',ns))==7
assert all(s._inline.docPr.get('descr') for s in d.inline_shapes)
for t in d.tables:
    assert t.rows[0]._tr.find('w:trPr/w:tblHeader',ns) is not None
    for row in t.rows:
        assert row._tr.find('w:trPr/w:trHeight',ns) is None
with ZipFile(path) as z:
    assert 'word/comments.xml' not in z.namelist()
    assert xml.find('.//w:ins',ns) is None and xml.find('.//w:del',ns) is None

stats={'docx':str(path),'bytes':path.stat().st_size,'figures':len(d.inline_shapes),'tables':len(d.tables),
       'equations':len(xml.findall('.//m:oMath',ns)),'hyperlinks':len(xml.findall('.//w:hyperlink',ns)),
       'example_stdout':output.getvalue().strip(),
       'words_approx':sum(len(p.text.split()) for p in d.paragraphs)+sum(len(c.text.split()) for t in d.tables for r in t.rows for c in r.cells)}
import sys
if len(sys.argv)>1:
    pdf=Path(sys.argv[1]);reader=PdfReader(pdf)
    stats['rendered_pages']=len(reader.pages)
    pages=[]
    for i,page in enumerate(reader.pages,1):
        text=page.extract_text() or ''
        pages.append({'page':i,'chars':len(text),'start':text[:130].replace('\n',' | '),'end':text[-160:].replace('\n',' | ')})
    (BASE/'page_text_audit.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
(BASE/'validation.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(stats,ensure_ascii=False,indent=2))
