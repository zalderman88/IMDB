"""Consolidate a fresh run's valid pages before rebuilding. No network calls."""
import json
import pathlib
root=pathlib.Path(__file__).resolve().parent.parent
nodes={}
for directory in ['jw_global','jw_1k']:
    for path in sorted((root/'research'/directory).glob('*.json')):
        d=json.loads(path.read_text())
        for edge in ((d.get('data') or {}).get('popularTitles') or {}).get('edges',[]):nodes[edge['node']['id']]=edge['node']
if not nodes:raise SystemExit('No fresh JW cache pages found; existing consolidated snapshot left unchanged.')
path=root/'research/jw_consolidated.json'
path.write_text(json.dumps({'complete':False,'movies':list(nodes.values())},ensure_ascii=False,separators=(',',':')))
print('Consolidated',len(nodes),'AU records')
