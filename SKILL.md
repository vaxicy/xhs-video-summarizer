---
name: xhs-video-summarizer
description: 抓取小红书视频帖（扫码登录，持久 cookie）→ 下载视频 → 语音转写（本地 whisper.cpp）+ 画面分析（本地 VLM，Ollama）→ 评论 → 自动生成结构化总结。支持单条链接或批量 URL 列表。跨 WorkBuddy / Codex / Claude 通用。
---

# 小红书视频帖抓取 + 全内容总结

把一条（或一批）小红书视频帖，自动变成一份结构化总结 Markdown：含文案、标签、互动数据、语音口播转写、画面视觉分析（OCR）、评论摘录，以及本地模型综合的「内容总结」。

## 何时使用
用户给出小红书帖子链接（`xiaohongshu.com/explore/...` 或 `xhslink` 短链），要求：
- 提取帖子内容（标题、文案、标签、互动数据、评论）
- 分析视频内容（画面 + 口播语音）
- 生成内容总结（单条或批量）

## 安装（首次，每个新机器跑一次）
```bash
cd <skill 目录>
python setup.py          # 建 .venv、装 Playwright、下 Chromium、下 whisper 模型
python install.py        # 把本 skill 链入 WorkBuddy / Codex / Claude 的 skills 目录
```
- `setup.py` 会在 skill 目录内建 `.venv`，并把 whisper 模型下载到 `bin/models/`。
- `install.py` 用目录联接（Windows `mklink /J` / macOS·Linux `ln -s`）把同一份代码链进三个宿主的 `skills/` 目录，**三端共用一份，改一处全生效**。只装某个宿主：`python install.py --codex`。
- 系统需预装 **ffmpeg**（在 `PATH` 里）。`python install.py --list` 可预览将被链接到的位置。

## 登录（首次，必须人工扫码）
1. 直接跑一次抓取命令，脚本检测到未登录会**弹出浏览器窗口**并停留。
2. **让用户在弹出的窗口里扫码登录**（小红书 App 扫）。
3. cookie 存在 `data/profile/`，之后**无需再扫码**（约 30 天有效，失效重跑一次扫码即可）。

## 方式一：批量跑（推荐，一条命令全流程）
把链接写进 `urls.txt`（每行一条，`#` 开头为注释），然后：
```bash
cd <skill 目录>
python scripts/batch_run.py urls.txt
```
每条链接自动走：抓取 → 抽帧 → 视觉分析(VLM) → 语音转写(whisper) → 生成 `output/<note_id>/summary.md`。
参数：
- `--force`：已有 summary.md 的也重跑
- `--skip-scrape`：跳过抓取（目录里已有 video.mp4 时，重跑分析用）
- `--no-asr` / `--no-visual`：跳过对应分析
- `--comments N`：评论条数（默认 20）
- 完成判定 = `output/<note_id>/summary.md` 存在；结束打印成功/跳过/失败统计

> 用哪个 python：按 `setup.py` 建好 `.venv` 后，Windows 用 `.venv\Scripts\python.exe`、macOS·Linux 用 `.venv/bin/python`；若宿主已提供装好依赖的 python，直接 `python` 也行——脚本内部都用 `sys.executable` 调起子步骤。

## 方式二：单步手动跑
| 步骤 | 命令 | 产出 |
|---|---|---|
| 抓取 | `python scripts/xhs_scraper.py "<URL>" --comments 20` | `metadata.json` / `metadata_raw.json` / `video.mp4` |
| 语音转写 | `python scripts/transcribe.py output/<note_id>` | `transcript.txt` + `transcript_plain.txt` |
| 视觉分析 | `python scripts/visual_analyze.py output/<note_id>`（需先抽帧，batch 自动抽） | `visual_analysis.txt` |
| 自动汇总 | `python scripts/make_summary.py output/<note_id>` | `summary.md`（9 节结构） |

## summary.md 结构（make_summary.py 自动生成）
基本信息 / 文案原文 / 话题标签 / 互动数据表 / 时刻章节 / 🎙️语音口播转写 / 🎬画面内容（视觉+OCR）/ 评论摘录（置顶优先）/ 内容总结（本地 LLM 综合，Ollama 挂了会降级拼接）。Agent 可在其上再做人工润色，但自动版已可直接交付。

## 组件与依赖
- **抓取**：Playwright 持久 profile；互动数据从 `__INITIAL_STATE__` 解析；视频直链从 state 正则抓（`http://sns-video-*.xhscdn.com/...mp4?sign=...`，注意 http 非 https）。
- **ASR**：whisper.cpp（`bin/main.exe` 等）+ `bin/models/ggml-base.bin`（约 141MB，由 setup.py 下载）。⚠️ whisper.cpp 窄字符 fopen **读不了中文路径**，transcribe.py 会自动把模型/音频复制到 `%TEMP%/xhs_asr/` 中转。想更准换 `ggml-small.bin`（466MB，同源）。
- **视觉**：本机 Ollama `qwen2.5vl:7b`，`num_ctx:16384`，每批 ≤4 帧（默认 ctx 4096 会 HTTP 400）。
- **ffmpeg**：系统 PATH 里的 ffmpeg（Windows 可用 `winget install ffmpeg`；macOS `brew install ffmpeg`）。
- **LLM 综合**：本机 Ollama（视觉模型同款或任意文本模型皆可）。

## 注意
- 登录墙是硬门槛：未登录只能看到「打开 App」页，必须走一次扫码。
- 仅用于个人备份/内容学习，勿用于批量商业抓取（平台 ToS）。
- 若 XHS 改版导致选择器失效：读 `metadata_raw.json` 排查字段路径，更新脚本提取逻辑。
- whisper base 模型中文转写有小错（同音字），看大意够用；要逐字稿精度需换 small/medium 模型。
- 视觉分析与综合需要本机 Ollama 在跑（`ollama serve`）且已拉取对应模型；否则视觉分析与综合会缺，转写/元数据仍正常。
