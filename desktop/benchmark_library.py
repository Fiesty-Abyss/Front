"""Isolated generated-library probe. SQL seeding is not file-import throughput.
Run from the checkout with PYTHONPATH=backend and a NEW destination directory.
"""
import os,sys,time,json,statistics,sqlite3,subprocess,hashlib,platform
from pathlib import Path
import argparse
parser=argparse.ArgumentParser();parser.add_argument('new_output',type=Path);parser.add_argument('--images',type=int,default=100)
args=parser.parse_args()
if not 0<=args.images<=1000:parser.error('--images must be between 0 and 1000')
root=args.new_output.resolve();root.mkdir(parents=True,exist_ok=False)
os.environ['FRONT_DATA_DIR']=str(root/'data');os.environ['FRONT_CIVITAI']='off'
for k in ['FRONT_AI_API_KEY','FRONT_AI_BASE_URL','FRONT_AI_MODEL','FRONT_SD_WEBUI_URL','FRONT_COMFYUI_URL']:os.environ.pop(k,None)
from fastapi.testclient import TestClient
from front_api.main import create_app
from front_api.db import get_engine
from front_api import models as m
from sqlalchemy import insert,text
from datetime import datetime,date
project=Path(__file__).resolve().parents[1]
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True,timeout=10).strip()
dirty=subprocess.run(['git','diff','--quiet','HEAD'],cwd=project,timeout=10).returncode!=0
report={'data':'generated metadata; no original files; in-process ASGI, not network/UI','scales':[],
 'environment':{'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'platform':sys.platform,'source_revision':revision,'tracked_worktree_dirty':dirty,'benchmark_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
with TestClient(create_app()) as c:
 engine=get_engine();now=datetime.now();last=0
 with engine.begin() as conn:
  conn.execute(insert(m.World),[{'id':i,'name':f'Generated world {i}'} for i in range(1,11)])
  conn.execute(insert(m.Tag),[{'id':i,'name':f'tag {i}','category':'generated'} for i in range(1,21)])
  conn.execute(insert(m.Collection),[{'id':1,'name':'Generated large collection'}])
 for count in [10000,50000,100000]:
  start=time.perf_counter()
  with engine.begin() as conn:
   for lower in range(last+1,count+1,1000):
    rows=[{'id':i,'title':f'Generated asset {i:06d}','kind':'drawing' if i%5 else 'novel','content':('generated chapter text '*50 if i%5==0 else None),'world_id':i%10+1,'work_date':date(2026,1,i%28+1),'meta':{}} for i in range(lower,min(lower+1000,count+1))]
    conn.execute(insert(m.Asset),rows)
    conn.execute(text('INSERT INTO search_index(entity,entity_id,title,body) VALUES(:e,:i,:t,:b)'),[{'e':'asset','i':r['id'],'t':r['title'],'b':r['content'] or ''} for r in rows])
    conn.execute(insert(m.asset_tags),[{'asset_id':r['id'],'tag_id':r['id']%20+1} for r in rows])
   if last<10000:conn.execute(insert(m.collection_assets),[{'collection_id':1,'asset_id':i,'position':i-1} for i in range(last+1,min(count,10000)+1)])
  seeded=time.perf_counter()-start
  metrics={}
  for name,url in {'first':'/api/assets?limit=60','deep':'/api/assets?limit=60&offset='+str(count-60),'world':'/api/assets?limit=60&world_id=3','tags':'/api/assets?limit=60&tag=3&tag=4','fts':'/api/assets?limit=60&q=asset%20001','short':'/api/assets?limit=60&q=as','collections':'/api/collections?limit=20'}.items():
   samples=[]
   for _ in range(5):
    t=time.perf_counter();r=c.get(url);elapsed=(time.perf_counter()-t)*1000;r.raise_for_status();samples.append(elapsed)
   metrics[name]={'p50_ms':round(statistics.median(samples),2),'max_ms':round(max(samples),2),'bytes':len(r.content),'total':r.json().get('total')}
  with engine.connect() as conn:
   plans={name:[list(r) for r in conn.execute(text(sql))] for name,sql in {'world':'EXPLAIN QUERY PLAN SELECT id FROM assets WHERE world_id=3 ORDER BY work_date DESC NULLS LAST,id DESC LIMIT 60','tag':'EXPLAIN QUERY PLAN SELECT id FROM assets WHERE EXISTS(SELECT 1 FROM asset_tags WHERE asset_id=assets.id AND tag_id=3) ORDER BY work_date DESC NULLS LAST,id DESC LIMIT 60'}.items()}
   conn.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
  item={'count':count,'bulk_sql_seed_s':round(seeded,3),'new_records':count-last,'queries':metrics,'plans':plans,'db_bytes':(root/'data/front.db').stat().st_size}
  if os.name=='nt':
   from profiling import working_set
   item['process_memory_includes_test_client']=working_set(os.getpid())
  report['scales'].append(item);(root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(item),flush=True);last=count


if args.images:
 import io
 from PIL import Image,ImageDraw
 samples=[];started=time.perf_counter();input_bytes=0
 with TestClient(create_app()) as c:
  for i in range(args.images):
   image=Image.new('RGB',(1024,768),(i*37%255,i*73%255,i*17%255));ImageDraw.Draw(image).text((40,40),f'Generated performance image {i}',fill='white')
   output=io.BytesIO();image.save(output,format='PNG');body=output.getvalue();input_bytes+=len(body)
   t=time.perf_counter();response=c.post('/api/assets/upload',files={'file':(f'generated-{i}.png',body,'image/png')});response.raise_for_status();samples.append((time.perf_counter()-t)*1000)
   c.get('/api/assets/'+str(response.json()['id'])+'/thumb').raise_for_status()
 thumbs=list((root/'data/thumbs').iterdir())
 report['images']={'fixture':'generated PNG, real upload/parse/hash/thumbnail ASGI API','count':args.images,'seconds_including_generation':round(time.perf_counter()-started,3),'upload_p50_ms':round(statistics.median(samples),2),'upload_max_ms':round(max(samples),2),'input_bytes':input_bytes,'thumb_count':len(thumbs),'thumb_bytes':sum(p.stat().st_size for p in thumbs)}
 (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report['images']),flush=True)
