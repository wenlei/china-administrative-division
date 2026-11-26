from pathlib import Path
import subprocess,sys,tempfile,time,json,uuid,threading,urllib.request,concurrent.futures,shutil
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));import switch_backend as release
# Creates and removes only uniquely labeled synthetic containers on an isolated network.
token='region-bg-test-'+uuid.uuid4().hex[:8];network=token;blue=token+'-blue';green=token+'-green';router=token+'-router'
created=[]
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
fixture='''import os,json,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/slow':time.sleep(4)
  b=json.dumps(dict(status='ok',service='regionCheck',version=os.environ['FIXTURE_VERSION'],data_sha256=os.environ['FIXTURE_SHA'],current_count=10)).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def log_message(self,*args):pass
ThreadingHTTPServer(('0.0.0.0',8000),H).serve_forever()
'''
with tempfile.TemporaryDirectory(prefix=token) as temp:
 root=Path(temp);root.chmod(0o755);(root/'server.py').write_text(fixture);(root/'server.py').chmod(0o644)
 config=root/'config';config.mkdir(mode=0o755);shutil.copyfile(SOURCE/'deployment/nginx.conf',config/'nginx.conf');(config/'upstream.conf').write_text(release.upstream(blue))
 for p in config.iterdir():p.chmod(0o644)
 try:
  run('docker','network','create','--label','codex.task='+token,network)
  for name,version,digest in [(blue,'old','a'*64),(green,'new','b'*64)]:
   run('docker','run','-d','--name',name,'--label','codex.task='+token,'--network',network,'--read-only','--cap-drop','ALL','-v',str(root/'server.py')+':/fixture.py:ro','-e','FIXTURE_VERSION='+version,'-e','FIXTURE_SHA='+digest,'--entrypoint','python','python:3.12-slim','/fixture.py');created.append(name)
  for _ in range(50):
   try:release.health(green,blue);release.health(green,green);break
   except Exception:time.sleep(.1)
  run('docker','run','-d','--name',router,'--label','codex.task='+token,'--network',network,'--read-only','--cap-drop','ALL','--user','101:101','--tmpfs','/tmp:uid=101,gid=101','-v',str(config)+':/etc/nginx/region-check:ro','-p','127.0.0.1::8000','--entrypoint','nginx','nginx:1.27-alpine','-c',release.CONFIG,'-g','daemon off;');created.append(router)
  time.sleep(.4)
  try:port=run('docker','port',router,'8000/tcp').strip().rsplit(':',1)[1]
  except Exception:
   log=subprocess.run(['docker','logs',router],capture_output=True,text=True);print(log.stdout+log.stderr);raise
  url='http://127.0.0.1:'+port
  def call(path='/health'):
   with urllib.request.urlopen(url+path,timeout=10) as r:return json.load(r)
  for _ in range(50):
   try:assert call()['version']=='old';break
   except Exception:time.sleep(.1)
  identity=release.inspect(router)['Id'];image=release.inspect(green)['Image'];results=[];errors=[];stop=threading.Event()
  def traffic():
   while not stop.is_set():
    try:results.append(call()['version'])
    except Exception as e:errors.append(type(e).__name__)
    time.sleep(.01)
  threads=[threading.Thread(target=traffic) for _ in range(3)]
  for t in threads:t.start()
  with concurrent.futures.ThreadPoolExecutor() as pool:
   slow=pool.submit(call,'/slow');time.sleep(.5)
   switched=release.switch(config,router,green,'new','b'*64,image,execute=True)
   assert slow.result()['version']=='old','In-flight request was interrupted or moved'
  for _ in range(100):
   if not release.draining_workers(router):break
   time.sleep(.1)
  rejected=False
  try:release.switch(config,router,blue,'old','c'*64,image,execute=True)
  except RuntimeError:rejected=True
  assert rejected and call()['version']=='new','Bad candidate must not replace active route'
  restored=release.switch(config,router,blue,'old','a'*64,image,execute=True)
  time.sleep(.2);stop.set()
  for t in threads:t.join()
  assert results and not errors,errors
  assert {'old','new'}<=set(results)
  assert call()['version']=='old' and release.inspect(router)['Id']==identity
  output=dict(passed=True,requests=len(results),failed_requests=len(errors),inflight_old_request_completed=True,invalid_candidate_refused=True,rollback_verified=True,router_not_restarted=True,both_backends_retained=True)
  print(json.dumps(output))
 finally:
  stop.set() if 'stop' in locals() else None
  for name in reversed(created):
   run('docker','rm','-f',name)
  run('docker','network','rm',network)
