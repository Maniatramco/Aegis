"""Download and validate the fixed official model; sends no document/query text."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.reranker import MODEL_ID, REVISION, verify_assets

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True,type=Path)
    args=parser.parse_args()
    directory=args.directory.resolve()
    directory.mkdir(parents=True,exist_ok=True)
    from huggingface_hub import hf_hub_download
    for file in ('onnx/model.onnx','tokenizer.json'):
        hf_hub_download(repo_id=MODEL_ID,revision=REVISION,filename=file,
                        local_dir=directory,token=False,endpoint='https://huggingface.co')
    verify_assets(directory)
    (directory/'aegis-model.json').write_text(json.dumps({'model':MODEL_ID,'revision':REVISION}),encoding='utf-8')
    print('Pinned local reranker downloaded and integrity checks passed:',directory)

if __name__=='__main__':main()
