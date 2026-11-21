# nowplaying

**认出电脑正在播放的歌 —— 不用麦克风。**

抓的是系统音频输出（Windows 上走 WASAPI 回环），每几秒采一段，
交给 Shazam 做指纹匹配，认出来就在终端打印一行：

```
[19:36:20] Samurai Groove — Mikoto
```

不需要装虚拟声卡，不需要开「立体声混音」，也不用把手机凑到音箱边上。

---

## 它怎么工作的

1. **抓**：`soundcard` 打开输出设备的回环接口。回环 = 声卡数字端的副本，
   和扬声器里响的是同一路信号，但不是录音设备，系统不用给你弹麦克风权限。
2. **算指纹**：把波形转成频谱图，取能量峰值点，相邻点配对算成一个个哈希。
   这些哈希就是这首歌的「指纹」。
3. **查**：指纹发给 Shazam，拿回歌名和歌手。匹配只依赖点对之间的相对关系，
   所以切掉开头、加点噪声、音质差一点，都还能认出来。

每段 10 秒左右最稳。低于 3 秒容易认不出，超过 30 秒只是白等。

---

## 装

### Windows（一把梭）

1. 装 [Python 3.10+](https://www.python.org/downloads/)（安装时勾上 *Add python.exe to PATH*）
2. 双击 **`安装.bat`**
3. 放首歌，双击 **`启动.bat`**

### 手动

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python listen.py
```

### 平台支持

| 平台 | 状态 | 说明 |
|---|---|---|
| Windows | ✅ 开箱能用 | WASAPI loopback |
| Linux | ✅ | 需要 PulseAudio 或 PipeWire |
| macOS | ⚠️ | 需要先装 [BlackHole](https://existential.audio/blackhole/) 之类的虚拟声卡 |

---

## 用

```bash
python listen.py             # 一直听
python listen.py --once      # 只听一次
python listen.py --list      # 看看有哪些输出设备
python listen.py -d 耳机      # 指定设备（名字片段）
python listen.py -d 2        # 按序号选
python listen.py --json      # 每行一条 JSON，方便接别的东西
```

JSON 输出长这样，可以拿去做歌词、桌面挂件、弹幕：

```json
{"time": "2026-11-21 19:36:20", "title": "Samurai Groove", "artist": "Mikoto"}
```

### 换设备

插了耳机还在用扬声器？先 `--list` 看一眼，再用 `-d` 指定。
切了输出设备要重新开一次，回环接口是绑在具体设备上的。

---

## 常见问题

**「没有回环接口」**
Windows 一般都有。Linux 检查 `pactl list sources short | grep monitor`；
macOS 基本都要装虚拟声卡。

**一直打点，认不出**
- 先确认有声音（打点就是静音或曲库里没有）
- 音量别太低
- 试试 `-s 12`，多给两秒

**报网络错**
Shazam 偶尔限速。脚本连续失败三次会自己歇一会儿，不用管。

**会失败吗**
会。Shazam 是第三方服务，接口哪天变了这工具就废了 —— 这是这类工具的命。

---

## 说明

- 这个工具只「听」，不上传音频文件，只发指纹（音频特征的哈希）。
- 用的是非官方的 Shazam 接口（[shazamio](https://github.com/shazamio/ShazamIO)），
  仅供个人学习使用，别拿去做商业服务。
- 不保证长期可用。

## License

MIT
