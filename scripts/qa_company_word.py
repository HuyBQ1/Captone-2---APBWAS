import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from pdf2image import convert_from_path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1]
qa=root/'.test-tmp/word-qa'
poppler='C:/Users/huydd/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
results=json.loads((qa/'render-results.json').read_text(encoding='utf-8-sig'))
def raster(item):
    code=item['file'].split('_')[0]
    expected=1 if '-CAT-' in code else 2
    assert item['pages']==expected,(code,item['pages'])
    images=convert_from_path(item['pdf'],dpi=120,poppler_path=poppler)
    assert len(images)==expected
    paths=[]
    for i,img in enumerate(images,1):
        path=qa/f'{code}-page-{i}.png';img.save(path);paths.append((code,i,path))
    return paths
with ThreadPoolExecutor(max_workers=4) as pool:
    pages=[page for group in pool.map(raster,results) for page in group]
boards=[]
for i in range(0,len(pages),2):
    board=Image.new('RGB',(2040,1344),'white');draw=ImageDraw.Draw(board)
    for j,(code,page,path) in enumerate(pages[i:i+2]):
        board.paste(Image.open(path),(j*1020,24));draw.text((j*1020+15,5),f'{code} / page {page}',fill='black')
    path=qa/f'board-{i//2+1:02}.png';board.save(path);boards.append(str(path))
(qa/'boards.json').write_text(json.dumps(boards,indent=2),encoding='utf-8')
print(json.dumps({'documents':len(results),'pages':len(pages),'boards':len(boards)}))
