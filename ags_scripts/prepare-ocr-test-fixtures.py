"""Derive fictional scan fixtures from the existing resume pack for live QA."""
import io
import json
import sys
from pathlib import Path
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from PIL import Image, ImageDraw, ImageFont

pack=Path(sys.argv[1]);target=Path(sys.argv[2]);target.mkdir(parents=True,exist_ok=True)
for name in ('01-arjun-rao-backend.pdf','02-meera-iyer-devops.pdf'):
    raw=(pack/'ags_resumes'/name).read_bytes()
    with pdfium.PdfDocument(raw) as doc:
        image=doc[0].render(scale=2).to_pil().convert('RGB')
        image.save(target/('scan-'+name),format='PDF',resolution=144)
        image.save(target/('scan-'+name+'.png'))
    assert not PdfReader(target/('scan-'+name)).pages[0].extract_text().strip()
    writer=PdfWriter();writer.append(PdfReader(io.BytesIO(raw)));writer.append(PdfReader(target/('scan-'+name)))
    with (target/('mixed-'+name)).open('wb') as handle:writer.write(handle)
for filename,reference,total in [('ocr-invoice-a.pdf','OCR-A-42','42.50'),('ocr-invoice-b.pdf','OCR-B-75','75.25')]:
    image=Image.new('RGB',(1200,800),'white');draw=ImageDraw.Draw(image)
    draw.multiline_text((70,70),f'FICTIONAL TEST INVOICE\nReference: {reference}\nTotal including tax: {total} USD\nSupplier: Example Test Supplies',font=ImageFont.load_default(size=36),fill='black',spacing=25)
    image.save(target/filename,format='PDF',resolution=144);image.save(target/(filename+'.png'))
image=Image.new('RGB',(500,400),'white');image.save(target/'blank.pdf',format='PDF')
image=Image.open(target/'ocr-invoice-a.pdf.png').rotate(90,expand=True)
image.save(target/'rotated-invoice.pdf',format='PDF',resolution=144)
image=Image.new('RGB',(1200,900),'white');draw=ImageDraw.Draw(image)
draw.multiline_text((60,60),'FICTIONAL TABLE INVOICE\nReference: OCR-TABLE-88\nItem          Qty       Amount USD\nWidget A       2         40.00\nWidget B       1         48.50\nTotal including tax: 88.50 USD',font=ImageFont.load_default(size=36),fill='black',spacing=25)
image.save(target/'table-invoice.pdf',format='PDF',resolution=144)
# A visible DOCX image, plus an unrelated package thumbnail, exercises image
# selection without inventing page numbers for Word layout.
import zipfile
with zipfile.ZipFile(target/'image-invoice.docx','w') as docx:
    docx.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    docx.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rDoc" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    docx.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:r><w:t>Fictional invoice attached as a visible image.</w:t></w:r></w:p><w:p><w:r><w:drawing><a:blip r:embed="rImage"/></w:drawing></w:r></w:p></w:body></w:document>')
    docx.writestr('word/_rels/document.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/invoice.png"/></Relationships>')
    docx.writestr('word/media/invoice.png',(target/'ocr-invoice-a.pdf.png').read_bytes())
    docx.writestr('docProps/thumbnail.png',(target/'ocr-invoice-b.pdf.png').read_bytes())
writer=PdfWriter();writer.append(PdfReader(target/'ocr-invoice-a.pdf'));writer.encrypt('fictional-qa-password')
with (target/'encrypted.pdf').open('wb') as handle:writer.write(handle)
(target/'invalid.pdf').write_bytes(b'%PDF-1.4\nInvalid fictional fixture\n')
(target/'ocr-invoice.json').write_text(json.dumps({'schema':{'type':'object','additionalProperties':False,'properties':{'reference':{'type':'string','description':'Copy the invoice reference exactly'},'total':{'type':'number','description':'Total including tax in USD'}},'required':['reference','total']}}),encoding='utf-8')
print('Fictional OCR fixtures prepared; scan text layers verified absent.')
