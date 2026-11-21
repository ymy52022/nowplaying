#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
window.py —— 把网页界面装进一个桌面小窗。

    python window.py
    python window.py --on-top
    python window.py --borderless       无边框，拖哪都能拖

它自己会把服务起在后台，再开一个 WebView2 小窗连上去；
关掉窗口，进程就退出。
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.request
from types import SimpleNamespace

import webui


def _serve(port, device, seconds, interval) -> None:
    try:
        webui.serve(SimpleNamespace(
            device=device, seconds=seconds, interval=interval, port=port, open=False
        ))
    except Exception as e:
        print("服务起不来：%s" % e, file=sys.stderr)


def _wait(port, timeout: float = 15.0) -> bool:
    url = "http://127.0.0.1:%d/api/state" % port
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(prog="window.py", description="nowplaying 小窗")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--device", "-d", help="输出设备：名字片段或序号")
    ap.add_argument("--seconds", "-s", type=float, default=10.0)
    ap.add_argument("--interval", "-i", type=float, default=3.0)
    ap.add_argument("--on-top", action="store_true", help="窗口置顶")
    ap.add_argument("--borderless", action="store_true", help="无边框（可拖动）")
    ap.add_argument("--width", type=int, default=440)
    ap.add_argument("--height", type=int, default=210)
    args = ap.parse_args()

    threading.Thread(
        target=_serve,
        args=(args.port, args.device, args.seconds, args.interval),
        daemon=True,
    ).start()

    if not _wait(args.port):
        print("服务没起来，窗口就不开了。", file=sys.stderr)
        return 1

    import webview

    webview.create_window(
        "nowplaying",
        "http://127.0.0.1:%d/?mini=1" % args.port,
        width=args.width,
        height=args.height,
        min_size=(320, 150),
        frameless=args.borderless,
        easy_drag=args.borderless,
        on_top=args.on_top,
        background_color="#0f1318",
    )
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
