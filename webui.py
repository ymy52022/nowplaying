#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webui.py —— nowplaying 的网页界面。

一般由 listen.py --web 调起来；也能单独跑：

    python webui.py
    python webui.py --port 9000 --open

页面是一个本地网页，显示现在在放什么、认没认出来、和最近听过哪些。
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import listen

# ---------------------------------------------------------------- 共享状态

STATE = {
    "status": "starting",   # starting / listening / playing / silent / unknown / error
    "device": "",
    "seconds": 10.0,
    "interval": 3.0,
    "current": None,        # {"title","artist","cover","at"}
    "history": [],          # 最新的在前，最多 50 条
    "message": "",
    "updated": 0,
}

LOCK = threading.Lock()
SUBS: list = []             # 每个 SSE 连接一个 queue.Queue


def snapshot() -> dict:
    with LOCK:
        return json.loads(json.dumps(STATE, ensure_ascii=False))


def publish() -> None:
    data = snapshot()
    for q in list(SUBS):
        try:
            q.put_nowait(data)
        except Exception:
            pass


def update(**kw) -> None:
    with LOCK:
        STATE.update(kw)
        STATE["updated"] = time.time()
    publish()


# ---------------------------------------------------------------- 后台识别

def worker(device, seconds, interval) -> None:
    try:
        asyncio_run(device, seconds, interval)
    except Exception as e:
        update(status="error", message=str(e))


def asyncio_run(device, seconds, interval) -> None:
    import asyncio
    asyncio.run(_loop(device, seconds, interval))


async def _loop(device, seconds, interval) -> None:
    import asyncio
    from shazamio import Shazam

    try:
        mic, name = listen.resolve_device(device)
    except SystemExit as e:
        update(status="error", message=str(e).strip())
        return
    except Exception as e:
        update(status="error", message=str(e))
        return

    update(status="listening", device=name, seconds=seconds, interval=interval, message="")

    shazam = Shazam()
    last_id = None
    try:
        while True:
            try:
                info, level = await listen.recognize(shazam, mic, seconds)
            except Exception as e:
                update(status="error", message=str(e))
                await asyncio.sleep(max(5.0, interval * 3))
                continue

            if info:
                if info["id"] != last_id:
                    last_id = info["id"]
                    entry = {
                        "title": info["title"],
                        "artist": info["artist"],
                        "cover": info.get("cover", ""),
                        "at": time.strftime("%H:%M"),
                    }
                    with LOCK:
                        STATE["current"] = entry
                        STATE["history"].insert(0, entry)
                        del STATE["history"][50:]
                update(status="playing", message="")
            elif level < listen.SILENCE_RMS:
                update(status="silent", message="")
            else:
                update(status="unknown", message="")

            await asyncio.sleep(max(0.5, interval))
    finally:
        close = getattr(shazam, "close", None)
        if close:
            try:
                await close()
            except Exception:
                pass


# ---------------------------------------------------------------- 页面

PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>nowplaying</title>
<style>
:root {
  --bg: #0f1318;
  --panel: #161b22;
  --line: #232a34;
  --text: #e6e3dd;
  --dim: #7d8590;
  --accent: #4fb8c9;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}
.shell { width: 100%; max-width: 680px; }
header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 28px;
}
h1 {
  font-size: 13px;
  font-weight: 500;
  letter-spacing: .2em;
  text-transform: uppercase;
  color: var(--dim);
  margin: 0;
}
#clock { font-size: 12px; color: var(--dim); font-variant-numeric: tabular-nums; }
.current {
  display: flex;
  gap: 24px;
  align-items: center;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 24px;
  min-height: 152px;
}
.cover {
  width: 112px;
  height: 112px;
  border-radius: 10px;
  object-fit: cover;
  background: #0b0e12;
  flex: none;
  opacity: 1;
  transition: opacity .35s ease;
}
.cover.empty { opacity: 0; }
.meta { min-width: 0; }
.title {
  font-size: 25px;
  line-height: 1.3;
  font-weight: 600;
  margin: 0 0 6px;
  letter-spacing: -.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.artist {
  font-size: 15px;
  color: var(--dim);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 18px;
  font-size: 12.5px;
  color: var(--dim);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--dim);
  transition: background .3s, box-shadow .3s;
}
.tag.on .dot { background: var(--accent); box-shadow: 0 0 0 4px rgba(79, 184, 201, .13); }
.tag.on { color: var(--text); }
.list { margin-top: 36px; }
.list h2 {
  font-size: 12px;
  letter-spacing: .16em;
  text-transform: uppercase;
  color: var(--dim);
  font-weight: 500;
  margin: 0 0 12px;
}
ul { list-style: none; margin: 0; padding: 0; }
li {
  display: flex;
  gap: 16px;
  padding: 11px 2px;
  border-bottom: 1px solid var(--line);
  font-size: 14px;
}
li:last-child { border-bottom: 0; }
li time { color: var(--dim); font-variant-numeric: tabular-nums; flex: none; width: 44px; }
li .t { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
li .a { color: var(--dim); margin-left: 8px; }
.hint { font-size: 13px; color: var(--dim); padding: 16px 2px; }

/* 小窗模式：?mini=1 */
body.mini { padding: 0; display: block; min-height: 0; }
body.mini .shell { max-width: none; padding: 14px 16px; }
body.mini header { margin-bottom: 10px; }
body.mini .current { padding: 14px; gap: 14px; min-height: 0; border-radius: 12px; }
body.mini .cover { width: 68px; height: 68px; border-radius: 8px; }
body.mini .title { font-size: 17px; margin-bottom: 3px; }
body.mini .artist { font-size: 12.5px; }
body.mini .tag { margin-top: 8px; font-size: 11.5px; }
body.mini .list { display: none; }
</style>
</head>
<body>
<div class="shell">
  <header>
    <h1>nowplaying</h1>
    <span id="clock"></span>
  </header>

  <div class="current">
    <img id="cover" class="cover empty" alt="">
    <div class="meta">
      <p class="title" id="title">在等一首歌</p>
      <p class="artist" id="artist">把音乐放起来就行</p>
      <div class="tag" id="tag"><span class="dot"></span><span id="status">正在启动</span></div>
    </div>
  </div>

  <div class="list">
    <h2>听过</h2>
    <ul id="history"></ul>
    <div class="hint" id="hint">还没有认出来的歌。</div>
  </div>
</div>

<script>
if (location.search.indexOf("mini") >= 0) document.body.classList.add("mini");
const $ = (id) => document.getElementById(id);
const LABEL = {
  starting: "正在启动",
  listening: "正在听",
  playing: "认出来了",
  silent: "现在很安静",
  unknown: "有声音，但没认出来",
  error: "出错了"
};

function render(s) {
  const cur = s.current;
  if (cur) {
    $("title").textContent = cur.title;
    $("artist").textContent = cur.artist;
    if (cur.cover) {
      $("cover").src = cur.cover;
      $("cover").classList.remove("empty");
    } else {
      $("cover").classList.add("empty");
    }
  }

  const tag = $("tag");
  tag.classList.toggle("on", s.status === "playing");
  let label = LABEL[s.status] || s.status;
  if (s.device && s.status !== "playing") label += " · " + s.device;
  if (s.message) label += "：" + s.message;
  $("status").textContent = label;

  const ul = $("history");
  ul.innerHTML = "";
  const rows = s.history || [];
  rows.forEach((h) => {
    const li = document.createElement("li");
    const t = document.createElement("time");
    t.textContent = h.at;
    const d = document.createElement("div");
    d.className = "t";
    d.textContent = h.title;
    const a = document.createElement("span");
    a.className = "a";
    a.textContent = h.artist;
    d.appendChild(a);
    li.append(t, d);
    ul.appendChild(li);
  });
  $("hint").style.display = rows.length ? "none" : "block";
}

fetch("/api/state").then((r) => r.json()).then(render).catch(() => {});

const es = new EventSource("/events");
es.onmessage = (e) => {
  try { render(JSON.parse(e.data)); } catch (_) {}
};

setInterval(() => {
  const d = new Date();
  $("clock").textContent = d.toTimeString().slice(0, 5);
}, 1000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "nowplaying"

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            body = json.dumps(snapshot(), ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8")
        elif path == "/events":
            self._sse()
        else:
            self.send_error(404)

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        q = queue.Queue()
        SUBS.append(q)
        try:
            first = "data: " + json.dumps(snapshot(), ensure_ascii=False) + "\n\n"
            self.wfile.write(first.encode("utf-8"))
            self.wfile.flush()
            while True:
                try:
                    data = q.get(timeout=15)
                    payload = "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"
                except queue.Empty:
                    payload = ": ping\n\n"
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
        except Exception:
            pass
        finally:
            try:
                SUBS.remove(q)
            except ValueError:
                pass


# ---------------------------------------------------------------- 入口

def serve(args) -> int:
    device = getattr(args, "device", None)
    seconds = getattr(args, "seconds", 10.0)
    interval = getattr(args, "interval", 3.0)
    port = getattr(args, "port", 8765)

    threading.Thread(
        target=worker, args=(device, seconds, interval), daemon=True
    ).start()

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print("端口 %d 起不来：%s" % (port, e), file=sys.stderr)
        print("换一个：python listen.py --web --port 8766", file=sys.stderr)
        return 1

    url = "http://127.0.0.1:%d/" % port
    print("网页界面：%s" % url, file=sys.stderr)
    print("Ctrl+C 退出。", file=sys.stderr)

    if getattr(args, "open", False):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("", file=sys.stderr)
    finally:
        httpd.server_close()
    return 0


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="webui.py", description="nowplaying 的网页界面")
    ap.add_argument("--device", "-d", help="输出设备：名字片段或序号")
    ap.add_argument("--seconds", "-s", type=float, default=10.0)
    ap.add_argument("--interval", "-i", type=float, default=3.0)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="自动打开浏览器")
    return serve(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
