"""Dependency setup launched by the desktop Tools button, with captured output."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
hidden = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
print('Preparing Python extraction tools…', flush=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', '--target', str(ROOT / 'app/extractor/.deps'),
                '-r', str(ROOT / 'app/extractor/requirements-v8.txt')], check=True, **hidden)
if not shutil.which('dotnet'):
    print('The .NET 9 SDK is missing. Install it using the link in Tools, then try again.', flush=True)
    raise SystemExit(1)
print('Building the entity extraction tool…', flush=True)
subprocess.run(['dotnet', 'build', '-c', 'Release', str(ROOT / 'app/extractor/entity_v8/EntityExtractor.csproj')], check=True, **hidden)
print('Tools are ready.', flush=True)
