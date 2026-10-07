"""Saved review exports. XLSX uses OOXML inline strings, never formulas."""
import csv, io, json, zipfile, re
from xml.sax.saxutils import escape

HEADERS=['extraction_id','version','field','value','value_type','document_id','document_name','page','chunk_id','quote','review_status','evidence_status']

def leaves(value,path=''):
    if isinstance(value,dict) and value:
        for key,item in value.items():yield from leaves(item,path+'/'+str(key).replace('~','~0').replace('/','~1'))
    elif isinstance(value,list) and value:
        for i,item in enumerate(value):yield from leaves(item,path+'/'+str(i))
    else:yield path or '/',value

def rows(record,data):
    evidence={item.get('field') or item.get('path') or item.get('json_pointer'):item for item in data.get('evidence',[])}
    for path,value in leaves(data['result']):
        source=evidence.get(path,{})
        # Sources without field-level evidence remain document provenance, not verified claims.
        sources=[source] if source else data.get('sources',[]) or [{}]
        for origin in sources:
            yield [record.id,record.version,path,value if isinstance(value,str) else json.dumps(value,ensure_ascii=False),type(value).__name__,origin.get('document_id',''),origin.get('document_name',''),origin.get('page') or '',origin.get('chunk_id',''),source.get('quote',''),data.get('review_status','unreviewed'),'verified quote' if source else 'unverified field']

def safe(value):
    text=str(value)
    # Leading whitespace must not bypass spreadsheet formula detection.
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text

def xlsx(table):
    def col(n):
        result=''
        while n:n,k=divmod(n-1,26);result=chr(65+k)+result
        return result
    body=[]
    for i,row in enumerate(table,1):
        if i>1048576:raise ValueError('Results exceed the Excel row limit. Use JSON or CSV.')
        cells=[]
        for j,value in enumerate(row,1):
            # XML 1.0 cannot represent these control characters. Reject rather than silently corrupt.
            text=str(value)
            if len(text)>32767:raise ValueError('A saved value exceeds the Excel cell limit. Use JSON or CSV.')
            if re.search('[\x00-\x08\x0b\x0c\x0e-\x1f]',text):raise ValueError('A saved value contains a control character unsupported by Excel. Use JSON or CSV.')
            cells.append(f'<c r="{col(j)}{i}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>')
        body.append(f'<row r="{i}">{"".join(cells)}</row>')
    files={
        '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Saved results" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml':'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(body)+'</sheetData></worksheet>'}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,xml in files.items():archive.writestr(name,'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+xml)
    return out.getvalue()

def render(record,data,format):
    table=[HEADERS,*rows(record,data)]
    if format=='json':return json.dumps({'extraction_id':record.id,'version':record.version,'result':data['result'],'evidence':data.get('evidence',[]),'sources':data.get('sources',[]),'review_status':data.get('review_status','unreviewed'),'saved_values_only':True},ensure_ascii=False,indent=2).encode(),'application/json'
    if format=='xlsx':return xlsx(table),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    if format=='csv':
        out=io.StringIO(newline='');writer=csv.writer(out);writer.writerows([[safe(v) for v in row] for row in table]);return ('\ufeff'+out.getvalue()).encode('utf-8'),'text/csv; charset=utf-8'
    raise ValueError('Export format must be xlsx, csv or json')
