#!/usr/bin/env python3
import os, json, sys
sys.path.append('chzzk_recorder')
from chzzk_api import ChzzkAPI
from recorder import start_recording

if __name__ == '__main__':
    config_dir = os.path.join('chzzk_recorder','config')
    with open(os.path.join(config_dir,'config.json'), 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    api = ChzzkAPI(config_dir)
    targets = cfg.get('TARGET_CHANNELS', [])
    # allow channel override via argv
    if len(sys.argv) > 1:
        targets = [sys.argv[1]]
    for cid in targets:
        det = api.get_live_details(cid)
        if det and det.get('m3u8_url'):
            print('LIVE:', cid, det['liveTitle'])
            info = start_recording(det, cfg)
            print('STARTED:', info)
            sys.exit(0)
    print('No live channels found among targets')
