"""Known-value fictional one-page resume and strict extraction prompt."""
import json
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4

root=Path(__file__).resolve().parents[2];directory=root/'output/pdf';directory.mkdir(parents=True,exist_ok=True)
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='ResumeName',fontName='Helvetica-Bold',fontSize=25,leading=29,textColor=HexColor('#123e78'),spaceAfter=6))
styles.add(ParagraphStyle(name='ResumeSection',fontName='Helvetica-Bold',fontSize=11,leading=15,textColor=HexColor('#0863d8'),spaceBefore=16,spaceAfter=6))
styles.add(ParagraphStyle(name='ResumeBody',fontName='Helvetica',fontSize=10,leading=15,spaceAfter=7))
styles.add(ParagraphStyle(name='ResumeNote',fontName='Helvetica',fontSize=8,leading=12,textColor=HexColor('#627793'),spaceAfter=12))
story=[]
def paragraph(text,style='ResumeBody'):story.append(Paragraph(text,styles[style]))
paragraph('FICTIONAL SAMPLE RESUME | AEGIS INTEGRATION VERIFICATION','ResumeNote')
paragraph('Maya Rao','ResumeName')
paragraph('<b>Senior Data Engineer</b> | Hyderabad, India')
paragraph('maya.rao@example.com | +1 202 555 0108')
paragraph('PROFESSIONAL SUMMARY','ResumeSection')
paragraph('Senior data engineer with 8 years of experience building reliable data pipelines, APIs and analytics platforms. Experienced in Python, SQL and cloud infrastructure.')
paragraph('TECHNICAL SKILLS','ResumeSection')
paragraph('Python, SQL, FastAPI, Docker, Apache Airflow, PostgreSQL, AWS, Git')
paragraph('WORK EXPERIENCE','ResumeSection')
paragraph('<b>Senior Data Engineer | Blue Harbor Analytics</b><br/>July 2021 - Present')
paragraph('Built and maintained data pipelines using Python and Apache Airflow. Developed FastAPI services for analytics applications.')
paragraph('<b>Data Engineer | Cedar Systems</b><br/>June 2018 - June 2021')
paragraph('Developed SQL data models and PostgreSQL reporting pipelines. Containerized data services using Docker.')
paragraph('EDUCATION','ResumeSection')
paragraph('<b>B.Tech in Computer Science</b><br/>Sunrise Example Institute of Technology | Graduated 2018')
paragraph('CERTIFICATIONS','ResumeSection')
paragraph('AWS Certified Data Engineer - Associate | 2025')
doc=SimpleDocTemplate(str(directory/'maya-rao-sample-resume.pdf'),pagesize=A4,rightMargin=46,leftMargin=46,topMargin=38,bottomMargin=38)
def footer(canvas,doc):
    canvas.setStrokeColor(HexColor('#dbe4f1'));canvas.line(46,35,A4[0]-46,35)
    canvas.setFont('Helvetica',8);canvas.setFillColor(HexColor('#627793'));canvas.drawString(46,23,'All names, organizations and contact details are fictional.');canvas.drawRightString(A4[0]-46,23,str(doc.page))
doc.build(story,onFirstPage=footer,onLaterPages=footer)
nullable={'type':['string','null']}
experience={'type':'object','properties':{'company':{'type':'string'},'title':{'type':'string'},'start_date':{'type':'string'},'end_date':nullable},'required':['company','title','start_date','end_date'],'additionalProperties':False}
education={'type':'object','properties':{'degree':{'type':'string'},'institution':{'type':'string'},'graduation_year':{'type':'integer'}},'required':['degree','institution','graduation_year'],'additionalProperties':False}
properties={k:{'type':'string'} for k in ('full_name','professional_title','email','phone','location')}
properties.update(total_experience_years={'type':'integer'},skills={'type':'array','items':{'type':'string'}},work_experience={'type':'array','items':experience},education={'type':'array','items':education},certifications={'type':'array','items':{'type':'string'}})
prompt={'name':'Resume extraction v1','schema':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False},
    'instructions':'Extract only facts explicitly stated in the resume. Copy names and contacts exactly. Use YYYY-MM for employment dates; end_date is null for Present. Preserve the explicitly stated total years of experience. Do not infer expertise, demographics, or missing credentials. Return only JSON matching the schema.'}
(directory/'resume-extraction-v1.json').write_text(json.dumps(prompt,indent=2)+'\n',encoding='utf-8')
import pypdfium2 as pdfium
pdf=pdfium.PdfDocument(str(directory/'maya-rao-sample-resume.pdf'));assert len(pdf)==1
text=pdf[0].get_textpage().get_text_range();assert all(value in text for value in ('Maya Rao','8 years','FastAPI','Sunrise Example'))
pdf[0].render(scale=1.5).to_pil().save(directory/'maya-rao-sample-resume-preview.png')
print('Created one-page sample resume, extraction prompt and rendered preview.')
