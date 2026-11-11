"""Rebuild the offline app from included snapshots; never fetches the network."""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys

root=pathlib.Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--verify',action='store_true',help='Run the Node functional checks after building')
args=parser.parse_args()
env=os.environ.copy()
env['PYTHONPATH']=os.pathsep.join([str(root),str(root/'research'),env.get('PYTHONPATH','')])
subprocess.run([sys.executable,str(root/'research/build_extended_movies.py')],cwd=root,env=env,check=True)
# TV finder: built only when the IMDb TV snapshot exists (python tools/refresh_tv.py creates it).
tv=(root/'research/imdb/tv_1k.json').exists()
if tv:subprocess.run([sys.executable,str(root/'research/build_tv.py')],cwd=root,check=True)
else:print('Skipping TV finder: research/imdb/tv_1k.json not present (run python tools/refresh_tv.py).')
if args.verify:
    subprocess.run([sys.executable,str(root/'tools/check_catalogue_lock.py')],cwd=root,check=True)
    node=shutil.which('node')
    if not node:raise SystemExit('Build succeeded. Install Node.js 18+ to run --verify.')
    subprocess.run([node,str(root/'tests/verify_movie_finder.mjs')],cwd=root,check=True)
    subprocess.run([sys.executable,str(root/'tests/test_tv_pipeline.py')],cwd=root,check=True)
    if tv:subprocess.run([node,str(root/'tests/verify_tv_finder.mjs')],cwd=root,check=True)
