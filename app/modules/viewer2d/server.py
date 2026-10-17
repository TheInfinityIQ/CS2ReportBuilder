"""Local-only replay server. Run python app/modules/viewer2d/server.py."""
import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, unquote

from replay import ANALYSIS, ROOT, build_replay


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript',
                      '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'app'), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def do_GET(self):
        url = urlsplit(self.path)
        try:
            if url.path == '/api/rebuild-status':
                path = ROOT / 'data/.desktop/rebuild-v8/progress.json'
                result = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'status':'not_started','total':0,'completed':0,'failed':0}
                result['stop_requested'] = (path.parent / 'stop.request').exists()
            elif url.path == '/api/matches':
                result = [{'source': p.parent.relative_to(ANALYSIS).as_posix(), 'name': p.parent.name}
                          for p in sorted(ANALYSIS.rglob('viewer_tracks_meta.json'))
                          if (p.parent / 'viewer_tracks.csv.gz').exists()]
            elif url.path == '/api/replay':
                query = parse_qs(url.query)
                result = build_replay(query['source'][0], int(query.get('round', ['13'])[0]))
            elif url.path == '/':
                self.send_response(302)
                self.send_header('Location', '/modules/viewer2d/')
                self.end_headers()
                return
            else:
                # Serve only this module and its map/weapon assets, never analysis folders.
                target = (ROOT / 'app' / unquote(url.path).lstrip('/')).resolve()
                allowed = [ROOT / 'app/modules/viewer2d', ROOT / 'app/assets']
                if not any(target.is_relative_to(p.resolve()) for p in allowed):
                    self.send_error(404)
                    return
                return super().do_GET()
            payload = json.dumps(result, separators=(',', ':'), allow_nan=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)
        except (ValueError, KeyError, FileNotFoundError) as exc:
            self.send_error(400, str(exc))

    def do_POST(self):
        if urlsplit(self.path).path != '/api/rebuild-stop':
            self.send_error(404); return
        # Only allow the local status page to request a graceful stop.
        if self.headers.get('Origin') != f'http://{self.headers.get("Host")}':
            self.send_error(403); return
        state = ROOT / 'data/.desktop/rebuild-v8'
        state.mkdir(parents=True, exist_ok=True)
        (state / 'stop.request').touch()
        self.send_response(204); self.end_headers()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    print(f'Viewer ready at http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
