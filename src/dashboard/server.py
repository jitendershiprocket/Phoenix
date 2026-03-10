"""Phoenix Dashboard - Flask server for real-time progress UI."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from src.dashboard.progress import progress

_server_thread: threading.Thread | None = None
_app = None


def _create_app():
    from flask import Flask, Response, jsonify, send_from_directory
    app = Flask(__name__, static_folder="static", static_url_path="")

    @app.route("/")
    def index():
        static_dir = Path(__file__).resolve().parent / "static"
        if (static_dir / "index.html").exists():
            return send_from_directory(static_dir, "index.html")
        return """<html><head><meta charset="utf-8"><title>Phoenix Dashboard</title></head>
<body><h1>Phoenix Dashboard</h1><div id="status">Loading...</div>
<script>fetch('/api/status').then(r=>r.json()).then(d=>{
  document.getElementById('status').innerHTML='<pre>'+JSON.stringify(d,null,2)+'</pre';
}).catch(e=>document.getElementById('status').textContent='Error: '+e);
setInterval(()=>fetch('/api/status').then(r=>r.json()).then(d=>{
  document.getElementById('status').innerHTML='<pre>'+JSON.stringify(d,null,2)+'</pre';
}), 500);</script></body></html>"""

    @app.route("/api/status")
    def api_status():
        return jsonify(progress.to_dict())

    @app.route("/events")
    def events():
        def generate():
            import time as _time
            last = None
            while True:
                data = progress.to_dict()
                s = json.dumps(data)
                if s != last:
                    last = s
                    yield f"data: {s}\n\n"
                _time.sleep(0.5)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def start_dashboard(port: int = 5050) -> int:
    """Start dashboard server in background thread. Returns actual port used."""
    import socket
    global _server_thread, _app
    if _server_thread is not None and _server_thread.is_alive():
        return port

    def _port_free(p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", p))
                return True
            except OSError:
                return False

    actual_port = port
    for _ in range(5):
        if _port_free(actual_port):
            break
        actual_port += 1

    _app = _create_app()

    def run():
        _app.run(host="0.0.0.0", port=actual_port, threaded=True, use_reloader=False)

    _server_thread = threading.Thread(target=run, daemon=True)
    _server_thread.start()
    return actual_port
