# 小红书视频帖抓取 + 全内容总结

一个给 AI Agent 用的 skill：把一条（或一批）小红书视频帖，自动变成一份结构化总结 Markdown。

它会帮你把视频帖「拆解干净」——文案、标签、点赞收藏评论数、口播语音转写、画面里写了什么字（OCR）、评论区在聊什么，最后再用本地模型综合成一段《内容总结》。素材全程留在本机，不上传任何第三方云服务。

## 能拿到什么

最终每个帖子生成一份 `output/<note_id>/summary.md`，包含 9 节：

1. 基本信息（标题 / 作者 / 发布时间 / 链接）
2. 文案原文
3. 话题标签
4. 互动数据（点赞 / 收藏 / 评论 / 分享）
5. 视频「时刻」章节（从文案 `#mm:ss[时刻]# 标题` 解析）
6. 🎙️ 语音口播转写（whisper.cpp，本地 CPU）
7. 🎬 画面内容（视觉分析 + OCR，本地 VLM）
8. 评论摘录（置顶优先）
9. 内容总结（本地 LLM 综合，模型挂了会降级拼接）

## 它怎么工作

```
小红书链接
   │
   ▼  xhs_scraper.py   （Playwright 扫码登录，持久 cookie）
   ├─ metadata.json / metadata_raw.json   （文案、标签、互动数、评论）
   └─ video.mp4
         │
         ├─► transcribe.py      whisper.cpp 本地转写  ──► transcript.txt
         └─► 抽帧(ffmpeg)
                 │
                 └─► visual_analyze.py  本地 VLM(qwen2.5vl)  ──► visual_analysis.txt
                                                                   │
                                              make_summary.py  ──► summary.md
```

所有重活（语音、视觉、综合）都跑在**你本机的模型**上：whisper.cpp 做语音转写，Ollama 上的视觉/文本模型做画面分析和总结。没有一步把视频或文案发给外部 API。

## 安装（每个新机器跑一次）

需要 Python 3.10+，以及系统里的 `ffmpeg`（Windows：`winget install ffmpeg`；macOS：`brew install ffmpeg`）。

```bash
cd xhs-video-summarizer
python setup.py      # 建 .venv、装 Playwright、下载 Chromium、下载 whisper 模型
python install.py    # 把 skill 链入 WorkBuddy / Codex / Claude 的 skills 目录
```

- `setup.py`：在本目录建 `.venv`，装好依赖，下载 Chromium 浏览器内核和 whisper 模型（约 141MB，首次较慢）。
- `install.py`：用目录联接（Windows `mklink /J`，macOS/Linux `ln -s`）把**同一份代码**链进三个 Agent 宿主的 `skills/` 目录，三端共用、改一处全生效。只装某个宿主：`python install.py --codex`；预览位置：`python install.py --list`。

> 二进制说明：`bin/` 下的 whisper.cpp 本体（main.exe 等）是 Windows x64 构建，已随仓库提供；macOS / Linux 用户需自行放入对应平台的 whisper.cpp 二进制（保持 `main` / `whisper.so` / `libSDL2` 文件名）。

## 使用

### 批量（推荐）

把链接写进 `urls.txt`（每行一条，`#` 开头是注释）：

```bash
python scripts/batch_run.py urls.txt
```

常用参数：`--force`（重跑已完成）、`--skip-scrape`（只重分析）、`--no-asr` / `--no-visual`（跳过某步）、`--comments N`（评论条数，默认 20）。结束会打印成功 / 跳过 / 失败统计。

### 单步

| 步骤 | 命令 | 产出 |
|---|---|---|
| 抓取 | `python scripts/xhs_scraper.py "<URL>" --comments 20` | `metadata.json` / `video.mp4` |
| 转写 | `python scripts/transcribe.py output/<note_id>` | `transcript.txt` |
| 视觉 | `python scripts/visual_analyze.py output/<note_id>` | `visual_analysis.txt` |
| 汇总 | `python scripts/make_summary.py output/<note_id>` | `summary.md` |

首次抓取会弹出浏览器让你扫码登录小红书，cookie 存到 `data/profile/`，约 30 天内复用。

## 组件与依赖

| 环节 | 方案 | 说明 |
|---|---|---|
| 抓取 | Playwright 持久 profile | 互动数从 `__INITIAL_STATE__` 解析，视频直链正则抓取（注意是 http 非 https） |
| 语音转写 | whisper.cpp（本地 CPU） | `bin/models/ggml-base.bin`；要更准换 `ggml-small.bin` 并传 `--model` |
| 画面分析 | 本地 Ollama `qwen2.5vl:7b` | `num_ctx:16384`，每批 ≤4 帧 |
| 综合总结 | 本地 Ollama 文本模型 | 模型不可用时降级为规则拼接，不报错中断 |
| 抽帧 | ffmpeg | 每 8 秒一帧，宽缩到 640px |

## 常见问题

- **一直停在登录页**：未扫码或 cookie 失效。删掉 `data/profile/` 重跑一次，重新扫码。
- **转写报「找不到 ffmpeg」**：ffmpeg 没进 PATH，先装好再跑。
- **视觉分析整段缺失**：本机 Ollama 没在跑，或没拉 `qwen2.5vl:7b`。转写和元数据不受影响。
- **whisper 转写有同音错别字**：base 模型精度有限，看大意够用；要逐字稿换 small/medium 模型。
- **小红书改版后选择器失效**：读 `output/<note_id>/metadata_raw.json` 排查字段路径，改 `xhs_scraper.py` 的提取逻辑。

## 合规

仅用于**个人备份 / 内容学习**。请勿用于批量商业抓取，遵守小红书平台服务条款。登录态 cookie 属于敏感信息，已在 `.gitignore` 中排除，不会进入任何仓库。

## 文件结构

```
xhs-video-summarizer/
├── SKILL.md            # skill 说明（Agent 读取）
├── README.md           # 本文
├── setup.py            # 环境准备（venv + 依赖 + Chromium + 模型）
├── install.py          # 跨宿主安装（WorkBuddy / Codex / Claude）
├── requirements.txt
├── scripts/            # 抓取 / 转写 / 视觉 / 汇总 / 批量
├── bin/                # whisper.cpp 二进制 + 模型目录
├── data/               # 登录 profile（git 忽略）
├── output/             # 抓取与分析产物（git 忽略）
└── urls.txt            # 批量链接样例
```
