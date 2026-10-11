"""Actual vision inference check; no DB writes or user documents."""
import io
import json
import time
from PIL import Image, ImageDraw, ImageFont
from . import ocr


def run():
    if not ocr.config()['enabled']:
        return {'passed':True,'skipped':True,'reason':'OCR explicitly disabled'}
    cfg=ocr.available()
    image=Image.new('RGB',(1000,260),'white')
    ImageDraw.Draw(image).multiline_text((30,25),'AEGIS OCR CHECK\nInvoice total: 42.50\nReference: OCR-104',font=ImageFont.load_default(size=36),fill='black',spacing=15)
    out=io.BytesIO();image.save(out,format='PNG')
    started=time.monotonic()
    text,metadata=ocr.transcribe(out.getvalue(),cfg)
    if not all(value in text for value in ('AEGIS OCR CHECK','42.50','OCR-104')):
        raise ocr.OcrError('OCR smoke transcription differs from the known image. Inspect the model before using scanned documents.')
    models=ocr.call(cfg,'/api/ps',timeout=10).get('models',[])
    loaded=next((m for m in models if m.get('name') in (cfg['model'],cfg['model']+':latest')),None)
    if not loaded:raise ocr.OcrError('OCR model is not loaded after inference; hardware use could not be verified.')
    result={'passed':True,'model':cfg['model'],'digest':cfg['digest'],'seconds':round(time.monotonic()-started,3),
        'inference_hardware':'GPU offload' if loaded.get('size_vram',0) else 'CPU','size_vram_bytes':loaded.get('size_vram',0),
        'fixture_exact_values':True}
    print(json.dumps(result));return result


if __name__=='__main__':run()
