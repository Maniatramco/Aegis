"""JSON documents retain their originals and index readable structured text."""
import json

def json_document_text(raw):
    def invalid_constant(value):
        raise ValueError('Invalid JSON constant: ' + value)
    try:
        value = json.loads(raw.decode('utf-8-sig'), parse_constant=invalid_constant)
        text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError('Invalid JSON document. Use valid UTF-8 JSON and try again.') from exc
    if len(text) > 5000000:
        raise ValueError('JSON document exceeds the 5 million character text limit.')
    return text
