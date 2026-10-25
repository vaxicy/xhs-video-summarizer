#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用本地 qwen2.5vl 视觉模型分析视频帧：描述内容 + OCR 画面文字 + 总结核心信息。
用法：python visual_analyze.py <output_dir>
依赖：本机 Ollama 已拉取 qwen2.5vl:7b 且 ollama serve 在跑。
Ollama 单请求对帧数有限制，故分批（每批 <=6 帧）分析后综合。
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

MODEL = "qwen2.5vl:7b"
API = "http://localhost:11434/api/chat"
BATCH = 4  # 单请求帧数；Ollama 默认 ctx 4096，4 帧@640px≈4160 token，靠 num_ctx 撑住


def call(prompt, images):
    payload = {"model": MODEL,
               "messages": [{"role": "user", "content": prompt, "images": images}],
               "stream": False,
               "options": {"num_ctx": 16384}}
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["message"]["content"]


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "output"
    frames = sorted((out_dir / "frames").glob("*.jpg"))
    if not frames:
        print("ERROR: 没有 frames/*.jpg，先抽帧")
        sys.exit(1)

    batches = [frames[i:i + BATCH] for i in range(0, len(frames), BATCH)]
    parts = []
    for bi, batch in enumerate(batches):
        print(f"[VLM] 批次 {bi+1}/{len(batches)}，{len(batch)} 帧 ...", flush=True)
        imgs = [base64.b64encode(p.read_bytes()).decode() for p in batch]
        sub = (f"这是视频的第 {bi+1}/{len(batches)} 批帧画面（按时间先后顺序）。"
               "请：①描述这批画面在展示什么；②逐条提取画面上的所有文字（OCR：标题、字幕、"
               "标签、按钮、标注、数据等）；③简要说明这批对应视频的哪一步/哪部分内容。用中文。")
        parts.append(call(sub, imgs))

    print("[VLM] 综合 ...", flush=True)
    joined = "\n\n".join(f"【第{bi+1}批】\n{t}" for bi, t in enumerate(parts))
    final_prompt = (
        "以下是把一段小红书视频分批改写出的各批画面分析，请综合成最终结论：\n"
        "1) 视频整体在讲什么（主题 / 演示步骤 / 核心观点）；\n"
        "2) 画面上的全部文字汇总（OCR，去重整理）；\n"
        "3) 用中文总结该视频传达的核心信息，以及它大概想教观众什么。\n"
        "请尽量具体，保留关键原文。\n\n" + joined
    )
    final = call(final_prompt, [])  # 综合阶段无需图，纯文本
    (out_dir / "visual_analysis.txt").write_text(final, encoding="utf-8")
    print(f"[VLM] 完成，输出 {len(final)} 字", flush=True)
    print(final[:400])


if __name__ == "__main__":
    main()
