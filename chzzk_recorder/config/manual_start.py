import os,json,sys
sys.path.append('/app')
from chzzk_api import ChzzkAPI
from recorder import start_recording
config_dir='/app/config'
with open(os.path.join(config_dir,'config.json'),'r',encoding='utf-8') as f:
    cfg=json.load(f)
api=ChzzkAPI(config_dir)
cid=sys.argv[1] if len(sys.argv)>1 else ''
if not cid:
    print('Usage: manual_start.py <channel_id>'); sys.exit(1)
det=api.get_live_details(cid)
print('LIVE?', bool(det))
if det and det.get('m3u8_url'):
    info=start_recording(det, cfg)
    print('STARTED', info)
else:
    print('No live for', cid)
