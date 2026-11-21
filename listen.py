#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nowplaying —— 认出电脑正在播放的歌。

不碰麦克风：直接抓系统音频输出（Windows 上走 WASAPI loopback，
macOS 走 BlackHole，Linux 走 PulseAudio monitor），每段几秒，
做一次 Shazam 指纹查询，认出来就打印一行。

用法:
    python listen.py                    一直听，认出来就打印
    python listen.py --once             只听一次，认完退出
    python listen.py --list             列出可用的输出设备
    python listen.py --device 耳机       指定设备（名字片段，或 --list 里的序号）
    python listen.py --device 2         按序号选
    python listen.py --seconds 8        每段抓 8 秒（默认 10）
    python listen.py --interval 4       两次之间停 4 秒（默认 3）
    python listen.py --json             每行输出一条 JSON（给别的程序读）

退出码:
    0 正常退出    1 环境问题（没设备/没依赖）    2 参数错误
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
import warnings
import wave

import numpy as np
import soundcard as sc
from shazamio import Shazam

# soundcard 抓回环时偶尔会刷「data discontinuity」，不影响识别，压掉
warnings.filterwarnings("ignore", message="data discontinuity in recording")

SAMPLE_RATE = 44100
SILENCE_RMS = 0.002  # 低于这个响度当没声，跳过不浪费一次查询

VERSION = "0.1.0"


# ---------------------------------------------------------------- 设备

def list_speakers():
    """列出所有输出设备，返回 [(序号, 名字)]。序号从 1 开始。"""
    return [(i + 1, s.name) for i, s in enumerate(sc.all_speakers())]


def loopback_for(speaker):
    """拿到某个输出设备对应的回环录音接口。"""
    try:
        return sc.get_microphone(id=str(speaker.name), include_loopback=True)
    except Exception:
        return None


def resolve_device(spec: str | None):
    """把 --device 的参数解析成 (回环设备, 输出设备名)。

    spec 可以是：None（用默认输出）、序号（"2"）、名字片段（"耳机"、耳机"）。
    """
    speakers = sc.all_speakers()
    if not speakers:
        raise SystemExit("一个输出设备都没找到。声卡驱动装了吗？")

    if spec is None:
        spk = sc.default_speaker()
        if spk is None:
            raise SystemExit("没有默认输出设备。用 --list 看看有哪些，再用 --device 指定。")
    elif spec.strip().isdigit():
        idx = int(spec) - 1
        if not (0 <= idx < len(speakers)):
            raise SystemExit("没有第 %s 个设备。当前有 %d 个。" % (spec, len(speakers)))
        spk = speakers[idx]
    else:
        needle = spec.casefold().strip()
        hits = [s for s in speakers if needle in s.name.casefold()]
        if not hits:
            names = "\n".join("  %d. %s" % (i + 1, s.name) for i, s in enumerate(speakers))
            raise SystemExit("没有名字里带「%s」的设备。现有：\n%s" % (spec, names))
        spk = hits[0]

    mic = loopback_for(spk)
    if mic is None:
        raise SystemExit(
            "「%s」没有回环接口。\n"
            "Windows 上一般都有；Linux 需要 PulseAudio/PipeWire；\n"
            "macOS 要先装 BlackHole 或 Loopback 之类的虚拟声卡。" % spk.name
        )
    return mic, spk.name


# ---------------------------------------------------------------- 音频

def rms(x) -> float:
    if x is None or len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(np.asarray(x, dtype=np.float64)))))


def to_wav(data, sr: int = SAMPLE_RATE) -> bytes:
    """float32 -> 16-bit 单声道 PCM WAV 字节。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        pcm = np.clip(np.asarray(data, dtype=np.float64), -1.0, 1.0)
        w.writeframes((pcm * 32767.0).astype("<i2").tobytes())
    return buf.getvalue()


def capture(mic, seconds: float):
    """抓一段声音，返回 numpy 数组（单声道 float32）。"""
    with mic.recorder(samplerate=SAMPLE_RATE, channels=1) as rec:
        return rec.record(numframes=int(SAMPLE_RATE * seconds))


# ---------------------------------------------------------------- 识别

async def recognize(shazam: Shazam, mic, seconds: float):
    """抓一段、认一次。返回 (结果 dict 或 None, 响度)。"""
    data = capture(mic, seconds)
    level = rms(data)
    if level < SILENCE_RMS:
        return None, level

    result = await shazam.recognize(to_wav(data))
    track = (result or {}).get("track") or {}
    if not track:
        return None, level

    images = track.get("images") or {}
    cover = ""
    if isinstance(images, dict):
        cover = images.get("coverart") or images.get("background") or ""

    return {
        "id": track.get("key") or track.get("title") or "",
        "title": track.get("title") or "（无标题）",
        "artist": track.get("subtitle") or "（无歌手）",
        "cover": cover,
    }, level


def emit(info: dict, as_json: bool):
    """打印认出来的歌。"""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if as_json:
        print(json.dumps(
            {"time": stamp, "title": info["title"], "artist": info["artist"]},
            ensure_ascii=False,
        ), flush=True)
    else:
        print("[%s] %s — %s" % (time.strftime("%H:%M:%S"), info["title"], info["artist"]), flush=True)


# ---------------------------------------------------------------- 主循环

async def run(args) -> int:
    mic, name = resolve_device(args.device)
    print("听：%s" % name, file=sys.stderr)
    print("每段 %g 秒，间隔 %g 秒。Ctrl+C 退出。" % (args.seconds, args.interval), file=sys.stderr)

    shazam = Shazam()
    last_id = None
    failures = 0

    try:
        while True:
            try:
                info, level = await recognize(shazam, mic, args.seconds)
                failures = 0
            except KeyboardInterrupt:
                raise
            except Exception as e:
                failures += 1
                print("出错（第 %d 次）：%s" % (failures, e), file=sys.stderr)
                # 连续失败太多，大概率是网断了，歇一会儿再试
                if failures >= 3:
                    await asyncio.sleep(max(5.0, args.interval * 3))
                info, level = None, 0.0

            if info and info["id"] != last_id:
                last_id = info["id"]
                emit(info, args.json)
            elif args.once and not info:
                if level < SILENCE_RMS:
                    print("这一段是静音（响度 %.5f），没有可认的东西。" % level, file=sys.stderr)
                else:
                    print("这段有声音（响度 %.4f），但曲库里没对上。" % level, file=sys.stderr)
            elif not info:
                print(".", end="", file=sys.stderr, flush=True)

            if args.once:
                return 0

            await asyncio.sleep(max(0.5, args.interval))
    finally:
        close = getattr(shazam, "close", None)
        if close:
            try:
                await close()
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="listen.py",
        description="认出电脑正在播放的歌（不用麦克风，抓系统音频回环）",
    )
    ap.add_argument("--device", "-d", help="输出设备：名字片段或 --list 里的序号")
    ap.add_argument("--list", "-l", action="store_true", help="列出输出设备后退出")
    ap.add_argument("--seconds", "-s", type=float, default=10.0, help="每段抓几秒，默认 10")
    ap.add_argument("--interval", "-i", type=float, default=3.0, help="两次之间停几秒，默认 3")
    ap.add_argument("--once", action="store_true", help="只认一次就退出")
    ap.add_argument("--json", action="store_true", help="每行输出一条 JSON")
    ap.add_argument("--web", action="store_true", help="开一个本地网页界面")
    ap.add_argument("--port", type=int, default=8765, help="--web 的端口，默认 8765")
    ap.add_argument("--open", action="store_true", help="--web 时自动打开浏览器")
    ap.add_argument("--version", action="version", version="nowplaying " + VERSION)
    args = ap.parse_args()

    if args.seconds < 3 or args.seconds > 30:
        ap.error("--seconds 建议在 3 到 30 之间（太短认不出，太长浪费时间）")

    if args.list:
        rows = list_speakers()
        if not rows:
            print("没有输出设备。", file=sys.stderr)
            return 1
        for i, name in rows:
            mark = "  ← 默认" if sc.default_speaker() and name == sc.default_speaker().name else ""
            print("%d. %s%s" % (i, name, mark))
        return 0

    if args.web:
        import webui
        return webui.serve(args)

    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        return 0
    except SystemExit:
        raise
    except Exception as e:
        print("起不来了：%s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
