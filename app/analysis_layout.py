"""Shared, whitespace-free folder names for Toolbox analysis output."""
import hashlib
import re
from pathlib import Path


def component(value, limit=190):
    text = re.sub(r'\s+', '_', str(value).strip())
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', text).strip(' .') or 'Unknown'
    if re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', text):
        text = '_' + text
    if len(text) > limit:
        text = text[:limit - 11].rstrip(' .') + '_' + hashlib.sha256(str(value).encode()).hexdigest()[:10]
    return text


def analysis_name(stem):
    return 'Analysis_' + component(stem)


def validate_root(value):
    root = Path(value).resolve()
    if any(re.search(r'\s', part) for part in root.parts):
        raise ValueError('Analysis output paths cannot contain spaces. Choose a path using underscores or dashes.')
    return root


def collection(root, context):
    root = validate_root(root)
    kind = context.get('collection_kind')
    if not kind:
        # Compatibility for existing library entries created before typed contexts.
        kind = 'player' if context.get('source') == 'faceit' and context.get('label') == context.get('owner') else 'team'
    if kind == 'player':
        return root / ('Analysis_' + component(context['owner'], 70))
    # One match analysis is shared by both teams; team selection belongs in metadata.
    return root / component(context.get('event') or 'Unclassified', 80)


def destination(root, context, map_name, demo_stem):
    return collection(root, context) / component(str(map_name).removeprefix('de_').lower(), 40) / analysis_name(demo_stem)
