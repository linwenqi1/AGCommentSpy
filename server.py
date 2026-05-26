import json, os, re, glob
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 4567
ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT, 'frontend')

MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png', '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
}

def find_apps():
    apps = []
    for d in sorted(glob.glob(os.path.join(ROOT, 'com.*'))):
        pkg = os.path.basename(d)
        info_path = os.path.join(d, 'app_info.json')
        if os.path.exists(info_path):
            with open(info_path, 'r', encoding='utf-8') as f:
                info = json.load(f)
            apps.append({'package': pkg, 'title': info.get('title', pkg), 'subtitle': info.get('subtitle', '')})
        else:
            apps.append({'package': pkg, 'title': pkg, 'subtitle': ''})
    return apps

def read_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def compute_stats(pkg):
    app_dir = os.path.join(ROOT, pkg)
    comments = read_json(os.path.join(app_dir, 'comments.json'))
    classified = read_json(os.path.join(app_dir, 'classified_comments.json'))
    total_comments = len(comments) if comments else 0
    sc = {'Positive': 0, 'Negative': 0, 'Neutral': 0}
    dc = {}
    tc = 0
    if classified:
        for dim, sentiments in classified.items():
            for sent, items in sentiments.items():
                c = len(items)
                sc[sent] = sc.get(sent, 0) + c
                tc += c
                dc[dim] = dc.get(dim, 0) + c
    return {'total_comments': total_comments, 'total_classified': tc,
            'sentiment_distribution': sc, 'dimension_distribution': dc}

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        params = parse_qs(parsed.query)
        try:
            if path == '/api/apps':
                return self.json(find_apps())
            m = re.match(r'/api/apps/([^/]+)$', path)
            if m:
                pkg = m.group(1)
                info = read_json(os.path.join(ROOT, pkg, 'app_info.json'))
                if not info:
                    return self.json({'error': 'App not found'}, 404)
                return self.json({**info, 'package': pkg, 'stats': compute_stats(pkg)})
            m = re.match(r'/api/apps/([^/]+)/comments$', path)
            if m:
                return self.handle_comments(m.group(1), params)
            m = re.match(r'/api/apps/([^/]+)/analysis$', path)
            if m:
                return self.handle_analysis(m.group(1))
            m = re.match(r'/api/apps/([^/]+)/clusters$', path)
            if m:
                return self.handle_clusters(m.group(1))
            self.serve_static(path if path else '/index.html')
        except Exception as e:
            self.json({'error': str(e)}, 500)

    def handle_comments(self, pkg, params):
        all_c = read_json(os.path.join(ROOT, pkg, 'comments.json'))
        if all_c is None:
            return self.json({'error': 'No comments'}, 404)
        page = int(params.get('page', [1])[0])
        limit = int(params.get('limit', [50])[0])
        search = params.get('search', [None])[0]
        filtered = [c for c in all_c if not search or search.lower() in c.get('content', '').lower()]
        total = len(filtered)
        start = (page - 1) * limit
        page_data = filtered[start:start + limit]
        return self.json({'comments': page_data, 'total': total, 'page': page,
                          'limit': limit, 'total_pages': max(1, (total + limit - 1) // limit)})

    def handle_analysis(self, pkg):
        data = read_json(os.path.join(ROOT, pkg, 'classified_comments.json'))
        if data is None:
            return self.json({'error': 'No analysis'}, 404)
        comments = read_json(os.path.join(ROOT, pkg, 'comments.json')) or []
        for dim, sentiments in data.items():
            for sent, items in sentiments.items():
                for item in items:
                    idx_m = re.search(r'_(\d+)$', item.get('id', ''))
                    if idx_m:
                        idx = int(idx_m.group(1)) - 1
                        if 0 <= idx < len(comments):
                            item['original'] = comments[idx]
                            item['_idx'] = idx
        return self.json(data)

    def handle_clusters(self, pkg):
        data = read_json(os.path.join(ROOT, pkg, 'clusters_preview_llm.json'))
        if data is None:
            return self.json({'error': 'No clusters'}, 404)
        return self.json(data)

    def serve_static(self, path):
        file_path = os.path.normpath(os.path.join(FRONTEND_DIR, path.lstrip('/')))
        if not file_path.startswith(FRONTEND_DIR):
            return self.send_error(403)
        if os.path.isfile(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            ct = MIME_TYPES.get(ext, 'application/octet-stream')
            with open(file_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            index = os.path.join(FRONTEND_DIR, 'index.html')
            if os.path.isfile(index):
                with open(index, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)

    def json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {args[0]} {args[1]} {args[2]}")

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"Server running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
