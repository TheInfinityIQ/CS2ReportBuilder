"""Display labels only: original filenames, score order and identities stay intact."""
from pathlib import Path
import re
from datetime import datetime


def map_label(value):
    return str(value or 'Unknown').removeprefix('de_').replace('_',' ').title()


def demo_label(entry):
    if not entry:return {'name':'No demo selected','source':'','map':'','date':''}
    filename=Path(entry['demo_path']).stem if entry.get('demo_path') else str(entry.get('title') or 'Downloaded demo')
    map_name=str(entry.get('map','')).removeprefix('de_')
    date=re.search(r'(?:_|\s)([A-Za-z]{3}-\d{2}-\d{4})(?=[_\s](?:de_)?'+re.escape(map_name)+r'[_\s])',filename) if map_name else None
    name=filename[:date.start()] if date else str(entry.get('title') or filename)
    name=name.replace('_',' ').replace('-vs-',' vs ')
    name=re.sub(r'^\[(\d+) vs (\d+)\]',r'[\1–\2]',name)
    source=''
    if date:
        tail=filename[date.end():].lstrip('_ ')
        for prefix in [map_name+'_','de_'+map_name+'_',map_name+' ','de_'+map_name+' ']:
            if tail.lower().startswith(prefix.lower()):tail=tail[len(prefix):];break
        source=tail.replace('_',' ')
        if source.casefold()=='faceit':source='FACEIT'
    date_value=entry.get('date')
    if not date_value and date:
        try:date_value=datetime.strptime(date.group(1),'%b-%d-%Y').date().isoformat()
        except ValueError:pass
    return {'name':name.strip(),'source':source,'map':map_label(entry.get('map')),'date':date_value or 'Date unknown'}
