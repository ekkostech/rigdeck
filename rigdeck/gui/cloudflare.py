"""Read recent Cloudflare zone analytics using the owner's existing Mac vault bridge.

Only aggregate response data crosses SSH. Credentials stay in the Mac process.
"""
from __future__ import annotations
import json
import shlex
import subprocess

REMOTE_SCRIPT = r'''
import subprocess,json,urllib.request,os,datetime,sys
sites=json.loads(sys.argv[1])
r=subprocess.run([os.path.expanduser('~/.local/bin/ekkos-personal'),'secret','get','cloudflare-main'],capture_output=True,text=True,timeout=20)
if r.returncode: raise SystemExit('Cloudflare vault access failed')
token=json.loads(r.stdout)['value']
headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
with urllib.request.urlopen(urllib.request.Request('https://api.cloudflare.com/client/v4/zones?per_page=50',headers=headers),timeout=20) as f:
 zones=json.load(f).get('result',[])
zones=[z for z in zones if z['name'] in sites]
now=datetime.datetime.now(datetime.timezone.utc)
start=(now-datetime.timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M:%SZ')
end=now.strftime('%Y-%m-%dT%H:%M:%SZ')
result=[]
for z in zones:
 query='query { viewer { zones(filter: {zoneTag: '+json.dumps(z['id'])+'}) { httpRequestsAdaptiveGroups(limit: 10000, filter: {datetime_geq: '+json.dumps(start)+', datetime_lt: '+json.dumps(end)+', requestSource: "eyeball"}) { count dimensions { datetimeMinute cacheStatus edgeResponseStatus } sum { edgeResponseBytes } } } } }'
 req=urllib.request.Request('https://api.cloudflare.com/client/v4/graphql',data=json.dumps({'query':query}).encode(),headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=25) as f: d=json.load(f)
  if d.get('errors'): raise ValueError('; '.join(e.get('message','query error') for e in d['errors']))
  rows=d['data']['viewer']['zones'][0]['httpRequestsAdaptiveGroups']
  if len(rows)>=10000: raise ValueError('Query row limit reached')
  count=sum(r['count'] for r in rows)
  cached=sum(r['count'] for r in rows if r['dimensions']['cacheStatus'] in ('hit','stale','updating','revalidated'))
  errors=sum(r['count'] for r in rows if r['dimensions']['edgeResponseStatus']>=500)
  minutes={}
  for r in rows:
   key=r['dimensions']['datetimeMinute'];minutes[key]=minutes.get(key,0)+r['count']
  result.append({'site':z['name'],'requests':count,'bytes':sum(r['sum']['edgeResponseBytes'] for r in rows),'cachePct':100*cached/count if count else None,'serverErrors':errors,'series':[{'at':k,'value':v} for k,v in sorted(minutes.items())],'latestEvent':max(minutes,default=None)})
 except Exception as e: result.append({'site':z['name'],'error':str(e)})
for site in sites:
 if not any(r['site']==site for r in result):result.append({'site':site,'error':'Zone not available in connected Cloudflare account'})
print(json.dumps({'source':'Cloudflare adaptive analytics','start':start,'end':end,'fetchedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sites':result}))
'''


def fetch(sites, host='mac'):
    if not sites or len(sites)>20: raise ValueError('Choose 1–20 sites.')
    command = '/usr/bin/python3 /Users/seannmacdougall/.local/bin/ekkos-gui-run -- /usr/bin/python3 -c '+shlex.quote(REMOTE_SCRIPT)+' '+shlex.quote(json.dumps(sites))
    r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ControlMaster=no','-o','ControlPath=none','-o','ConnectTimeout=8',host,command],capture_output=True,text=True,timeout=240)
    if r.returncode: raise RuntimeError('Cloudflare connection unavailable through the Mac vault bridge.')
    try:
        data=json.loads(r.stdout)
        if not isinstance(data['sites'],list): raise ValueError('Invalid sites')
        return data
    except (ValueError,KeyError,TypeError) as e:
        raise RuntimeError('Cloudflare returned an unreadable response.') from e
