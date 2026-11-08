from pathlib import Path
import sys, json, math, re
BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(BASE / 'plot_deps'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from docx import Document
from docx.shared import Cm, Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

OUT = ROOT / 'output' / 'documents'
OUT.mkdir(parents=True, exist_ok=True)
ASSETS = BASE / 'figures'
ASSETS.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10, 'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','figure.facecolor':'white','axes.labelcolor':'#263344','text.color':'#172435'})
BLUE='#236A9E'; TEAL='#197D74'; GRAY='#6B7685'; ORANGE='#BA6C2F'

def savefig(name, fig):
    fig.savefig(ASSETS / name, dpi=220, bbox_inches='tight', facecolor='white')
    plt.close(fig)

def figures():
    fig, ax=plt.subplots(figsize=(8,3.1))
    x=np.linspace(.55,4,600)
    ax.plot(x,100*np.minimum(1.15,1/x**2),color=BLUE,lw=2.8)
    vals=[1,1.5,2,3,4]
    ax.scatter(vals,[100/v**2 for v in vals],color=TEAL,zorder=3)
    for v in vals:
        ax.annotate(f'{100/v**2:.1f}%'.replace('.',','),(v,100/v**2),xytext=(6,8),textcoords='offset points',fontsize=9)
    ax.set(xlabel='Действия агента / человеческий ориентир',ylabel='Балл пройденного уровня, %',ylim=(0,127),xlim=(.5,4.35))
    ax.grid(axis='y',alpha=.2)
    savefig('efficiency.png',fig)

    fig, ax=plt.subplots(figsize=(8,3.0))
    ax.axis('off'); ax.set_xlim(0,10); ax.set_ylim(0,4)
    labels=[('Наблюдение','кадр и статус'),('Память','объекты и факты'),('Гипотеза','правила и цель'),('План','выбор действия')]
    for i,(a,b) in enumerate(labels):
        x=i*2.5
        ax.add_patch(FancyBboxPatch((x+.1,2),2.15,1.05,boxstyle='round,pad=.08',facecolor='#EEF4F8',edgecolor='#9DB7C8'))
        ax.text(x+1.18,2.65,a,ha='center',va='center',weight='bold',fontsize=10)
        ax.text(x+1.18,2.3,b,ha='center',va='center',fontsize=9)
        if i<3: ax.annotate('',xy=(x+2.55,2.5),xytext=(x+2.3,2.5),arrowprops=dict(arrowstyle='->',color=BLUE,lw=1.6))
    ax.annotate('',xy=(1.15,1.93),xytext=(8.65,1.93),arrowprops=dict(arrowstyle='->',connectionstyle='bar,fraction=-.13',color=TEAL,lw=1.8))
    ax.text(5,.65,'Действие → новый кадр → проверка предсказания',ha='center',fontsize=11,color=TEAL)
    savefig('agent_loop.png',fig)

    fig, axes=plt.subplots(1,3,figsize=(8,2.75))
    from matplotlib.colors import ListedColormap
    cmap=ListedColormap(['#F3F5F6','#7C8A98','#287AB2','#EBAE40','#31A38C'])
    a=np.zeros((7,7),int); a[[0,-1],:]=1;a[:,[0,-1]]=1;a[3,2]=2;a[3,3]=3;a[3,5]=4
    b=a.copy();b[3,2]=0;b[3,3]=2;b[3,4]=3
    c=b.copy();c[3,3]=0;c[3,4]=2;c[3,5]=3
    for ax,grid,title in zip(axes,[a,b,c],['1  Наблюдение','2  Проба вправо','3  Проверка правила']):
        ax.imshow(grid,cmap=cmap,vmin=0,vmax=4)
        ax.set_xticks(np.arange(-.5,7,1),minor=True);ax.set_yticks(np.arange(-.5,7,1),minor=True)
        ax.grid(which='minor',color='white',lw=1.5);ax.tick_params(which='both',bottom=False,left=False,labelbottom=False,labelleft=False)
        ax.set_title(title,fontsize=10,pad=9)
    fig.text(.5,-.02,'Синий — игрок    Жёлтый — ящик    Зелёный — предполагаемая цель',ha='center',fontsize=10)
    savefig('toy_game.png',fig)

    fig,ax=plt.subplots(figsize=(8,2.65))
    labels=['Открытые\nдля разработки','Скрытые\nPublic LB','Скрытые\nPrivate LB']; values=[25,55,55]
    bars=ax.barh(labels,values,color=[TEAL,BLUE,GRAY],height=.6)
    ax.invert_yaxis(); ax.set_xlim(0,65);ax.set_xlabel('Число сред');ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    for bar,v in zip(bars,values): ax.text(v+1,bar.get_y()+bar.get_height()/2,str(v),va='center',weight='bold')
    savefig('splits.png',fig)

    fig,ax=plt.subplots(figsize=(8,3.35))
    labels=['Flash v3\nзапуск 1','Flash v3\nповтор','S4','S5','S8','S9','Внешний\nпример'];values=[3.39,2.95,3.70,3.13,3.10,2.81,2.92]
    bars=ax.bar(labels,values,color=[GRAY,GRAY,TEAL,BLUE,BLUE,BLUE,GRAY],width=.65)
    ax.set_ylim(0,4.3);ax.set_ylabel('Public score, шкала 0–100');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    for bar,v in zip(bars,values):ax.text(bar.get_x()+bar.get_width()/2,v+.07,f'{v:.2f}'.replace('.',','),ha='center',fontsize=10)
    savefig('local_results.png',fig)

    fig,ax=plt.subplots(figsize=(8,3.1))
    g=np.arange(1,111)
    for budget,col in [(6,GRAY),(9,BLUE)]:
        t=(budget*60-30)/g
        ax.plot(g,t,color=col,lw=2,label=f'Учебный бюджет {budget} ч')
    ax.set(xlim=(20,116),ylim=(0,30),xlabel='Количество игр в одном запуске',ylabel='Средний бюджет на игру, минут')
    ax.legend(frameon=False);ax.grid(alpha=.2)
    ax.scatter([55,110],[510/55,510/110],color=TEAL,zorder=3)
    ax.annotate('55 игр: 9,3 мин',xy=(55,510/55),xytext=(58,16),arrowprops=dict(arrowstyle='->',color=TEAL),fontsize=9)
    ax.annotate('110 игр: 4,6 мин',xy=(110,510/110),xytext=(82,10),arrowprops=dict(arrowstyle='->',color=TEAL),fontsize=9)
    savefig('budget.png',fig)

SOURCES={
1:('Kaggle — обзор конкурса','https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview'),
2:('Kaggle — обязательные правила','https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/rules'),
3:('Kaggle — оценивание','https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview/evaluation'),
4:('Kaggle — календарь','https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview/timeline'),
5:('Kaggle — данные','https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/data'),
6:('ARC Prize — общий регламент 2026','https://arcprize.org/competitions/2026'),
7:('ARC Prize — трек ARC AGI 3','https://arcprize.org/competitions/2026/arc-agi-3'),
8:('ARC Prize Docs — методика оценки','https://docs.arcprize.org/methodology'),
9:('ARC Prize — человеческий ориентир и изменения оценки','https://arcprize.org/blog/arc-agi-3-human-dataset'),
10:('ARC Prize Docs — начало работы','https://docs.arcprize.org/'),
11:('ARC Prize — официальный Python SDK','https://github.com/arcprize/ARC-AGI'),
12:('ARC Prize Docs — действия','https://docs.arcprize.org/actions'),
13:('ARC Prize — победители первого этапа','https://arcprize.org/blog/arc-prize-2026-milestone-1'),
14:('ARC Prize — результаты Astra и условия оценки','https://arcprize.org/blog/astra'),
15:('Исследование моделей мира и проверки предсказаний','https://arxiv.org/abs/2607.15439v2'),
16:('Локальное состояние проекта на 16 сентября', (ROOT/'experiment_state.json').as_uri()),
17:('Локальный отчёт об эксперименте S4',(ROOT/'reports'/'SUBMIT_2026-09-08_S4.md').as_uri()),
18:('Локальный отчёт о внешнем примере',(ROOT/'reports'/'EXTERNAL_BASELINE_2026-09-15.md').as_uri()),
19:('Python — официальный учебник','https://docs.python.org/3/tutorial/'),
20:('ARC AGI 3 — описание бенчмарка','https://arcprize.org/arc-agi/3'),
21:('ARC AGI 3 — технический отчёт','https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf'),
22:('Kaggle — требования к коду','https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview/code-requirements'),
23:('Kaggle Staff — открытие решения к milestone','https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/discussion/713634'),
24:('SDK — реализация оценки','https://github.com/arcprize/ARC-AGI/blob/main/arc_agi/scorecard.py'),
25:('ARC Prize Docs — Competition Mode','https://docs.arcprize.org/toolkit/competition_mode'),
26:('ARC Prize Docs — официальный старт на Kaggle','https://docs.arcprize.org/arc-prize-2026'),
27:('ARC Prize Docs — схема наблюдения','https://docs.arcprize.org/game-schema'),
28:('ARC Prize Docs — локальный и сетевой режимы','https://docs.arcprize.org/local-vs-online'),
29:('Kaggle Staff — исправление лимита до 9 часов','https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/discussion/699208'),
30:('ARC Prize Docs — изменения SDK','https://docs.arcprize.org/changelog'),
}

doc=Document()
sec=doc.sections[0]
sec.page_width=Cm(21);sec.page_height=Cm(29.7)
sec.top_margin=Cm(1.8);sec.bottom_margin=Cm(1.65);sec.left_margin=Cm(2);sec.right_margin=Cm(2)
sec.footer_distance=Cm(.75)
styles=doc.styles
for st in styles:
    for border in list(st.element.iter(qn('w:pBdr'))):
        border.getparent().remove(border)
for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Heading 3','Caption','List Bullet','List Number']:
    st=styles[name];st.font.name='Arial';st.font.color.rgb=RGBColor(0,0,0)
    st.element.get_or_add_rPr().append(OxmlElement('w:lang'))
    st.element.rPr[-1].set(qn('w:val'),'ru-RU')
styles['Normal'].font.size=Pt(10.5)
styles['Normal'].paragraph_format.line_spacing=1.12
styles['Normal'].paragraph_format.space_after=Pt(7)
for name,size in [('Title',30),('Subtitle',16),('Heading 1',18),('Heading 2',12),('Heading 3',10.5)]:
    styles[name].font.size=Pt(size)
    styles[name].font.bold=name not in ['Subtitle']
    styles[name].paragraph_format.space_before=Pt(10 if name!='Title' else 0)
    styles[name].paragraph_format.space_after=Pt(8)
styles['Heading 1'].paragraph_format.space_before=Pt(0)
styles['Caption'].font.size=Pt(9)
styles['Caption'].font.italic=False
styles['Caption'].font.color.rgb=RGBColor.from_string('505C67')
styles['Caption'].paragraph_format.space_after=Pt(10)
for name in ['List Bullet','List Number']:
    styles[name].paragraph_format.space_after=Pt(5)
    styles[name].paragraph_format.line_spacing=1.08
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
r=footer.add_run('ARC Prize 2026   •   ');r.font.size=Pt(8);r.font.color.rgb=RGBColor.from_string('66717C')
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)
doc.core_properties.title='ARC Prize 2026 ARC AGI 3 Руководство для начинающего'
doc.core_properties.subject='Устройство конкурса, стратегия экспериментов и практический план'
doc.core_properties.author='Подготовлено для Дмитрия'
doc.core_properties.keywords='ARC-AGI-3, Kaggle, начинающий, агенты, RHAE'

def link(par,text,url):
    h=OxmlElement('w:hyperlink');h.set(qn('r:id'),par.part.relate_to(url,RT.HYPERLINK,is_external=True))
    r=OxmlElement('w:r');rp=OxmlElement('w:rPr');col=OxmlElement('w:color');col.set(qn('w:val'),'1F638D');rp.append(col)
    r.append(rp);t=OxmlElement('w:t');t.text=text;r.append(t);h.append(r);par._p.append(h)

def text_runs(par,text):
    for chunk in re.split(r'(\[\d+\]|\*\*.*?\*\*)',text):
        if re.fullmatch(r'\[\d+\]',chunk):
            n=int(chunk[1:-1]);link(par,chunk,SOURCES[n][1])
        elif chunk.startswith('**') and chunk.endswith('**'):par.add_run(chunk[2:-2]).bold=True
        else:par.add_run(chunk)

def p(text='',style=None):
    par=doc.add_paragraph(style=style);text_runs(par,text);return par
def h(text):return p(text,'Heading 2')
def bullet(text):return p(text,'List Bullet')
current_num_id=None
def num(text):
    global current_num_id
    numbering=doc.part.numbering_part.element
    if current_num_id is None:
        old_id=styles['List Number'].element.pPr.numPr.numId.val
        old=next(v for v in numbering.findall(qn('w:num')) if int(v.get(qn('w:numId')))==old_id)
        abstract_id=old.find(qn('w:abstractNumId')).get(qn('w:val'))
        current_num_id=max(int(v.get(qn('w:numId'))) for v in numbering.findall(qn('w:num')))+1
        new=OxmlElement('w:num');new.set(qn('w:numId'),str(current_num_id))
        aid=OxmlElement('w:abstractNumId');aid.set(qn('w:val'),abstract_id);new.append(aid)
        override=OxmlElement('w:lvlOverride');override.set(qn('w:ilvl'),'0')
        start=OxmlElement('w:startOverride');start.set(qn('w:val'),'1');override.append(start);new.append(override)
        numbering.append(new)
    par=p(text,'List Number')
    np=par._p.get_or_add_pPr().get_or_add_numPr()
    np.get_or_add_ilvl().val=0;np.get_or_add_numId().val=current_num_id
    return par
page_titles=[]
def page(title):
    global current_num_id
    current_num_id=None
    if page_titles:doc.add_page_break()
    page_titles.append(title)
    if len(page_titles)>1:
        par=p(title,'Heading 1')
        par.paragraph_format.space_after=Pt(10)
def fig(name,caption,width=6.65):
    par=doc.add_paragraph();par.paragraph_format.space_after=Pt(4);par.paragraph_format.keep_with_next=True
    sh=par.add_run().add_picture(str(ASSETS/name),width=Inches(width));sh._inline.docPr.set('descr',caption)
    p(caption,'Caption')
def table(headers,rows,widths=None):
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    if widths is None:widths=[17/len(headers)]*len(headers)
    for c,w in zip(t.columns,widths):c.width=Cm(w)
    for i,tx in enumerate(headers):t.rows[0].cells[i].text=tx
    for row in rows:
        cells=t.add_row().cells
        for i,tx in enumerate(row):cells[i].text=re.sub(r'(?<=\d) (?=\d{3}(?:\D|$))','\u00a0',str(tx))
    for ri,row in enumerate(t.rows):
        trpr=row._tr.get_or_add_trPr()
        cant=OxmlElement('w:cantSplit');trpr.append(cant)
        if ri==0:trpr.append(OxmlElement('w:tblHeader'))
        for ci,cell in enumerate(row.cells):
            cell.width=Cm(widths[ci]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=cell._tc.get_or_add_tcPr();b=OxmlElement('w:tcBorders')
            for side in ['top','left','bottom','right']:
                e=OxmlElement('w:'+side);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');b.append(e)
            tcpr.append(b);m=OxmlElement('w:tcMar')
            for side,v in [('top',90),('bottom',90),('left',110),('right',110)]:
                e=OxmlElement('w:'+side);e.set(qn('w:w'),str(v));e.set(qn('w:type'),'dxa');m.append(e)
            tcpr.append(m)
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'254D6A' if ri==0 else ('F0F5F8' if ri%2==0 else 'FFFFFF'));tcpr.append(shade)
            for par in cell.paragraphs:
                par.paragraph_format.space_after=Pt(0);par.paragraph_format.line_spacing=1.04
                for run in par.runs:
                    run.font.size=Pt(9.3);run.bold=ri==0
                    if ri==0:run.font.color.rgb=RGBColor(255,255,255)
    doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t

def mathrun(s):
    r=OxmlElement('m:r');t=OxmlElement('m:t');t.text=s;r.append(t);return r
def sub(a,b):
    e=OxmlElement('m:sSub');aa=OxmlElement('m:e');aa.append(mathrun(a));bb=OxmlElement('m:sub');bb.append(mathrun(b));e.extend([aa,bb]);return e
def sup(a,b):
    e=OxmlElement('m:sSup');aa=OxmlElement('m:e');aa.append(mathrun(a));bb=OxmlElement('m:sup');bb.append(mathrun(b));e.extend([aa,bb]);return e
def fraction(a,b):
    f=OxmlElement('m:f')
    for tag,x in [('m:num',a),('m:den',b)]:
        z=OxmlElement(tag)
        for item in (x if isinstance(x,list) else [x]):z.append(mathrun(item) if isinstance(item,str) else item)
        f.append(z)
    return f
def eq(*items):
    par=doc.add_paragraph();par.alignment=WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before=Pt(6);par.paragraph_format.space_after=Pt(10)
    m=OxmlElement('m:oMathPara');o=OxmlElement('m:oMath')
    for x in items:o.append(mathrun(x) if isinstance(x,str) else x)
    m.append(o);par._p.append(m)
def code(s):
    for line in s.strip('\n').split('\n'):
        par=doc.add_paragraph();par.paragraph_format.space_after=Pt(0);par.paragraph_format.line_spacing=1
        r=par.add_run(line);r.font.name='Consolas';r.font.size=Pt(8.7)
    p('')

def save():
    path=OUT/'ARC_Prize_2026_Руководство_для_начинающего.docx'
    doc.save(path)
    (BASE/'page_plan.json').write_text(json.dumps(page_titles,ensure_ascii=False,indent=2),encoding='utf-8')
    print(path)
    print('Planned pages:',len(page_titles))

if __name__=='__main__':
    figures()
    exec((BASE/'content.py').read_text(encoding='utf-8'))
    save()
