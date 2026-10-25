#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动生成 summary.md：metadata + 转写 + 视觉分析 -> 结构化总结。
用法：python make_summary.py <output_dir>
最终"内容总结"调用本地 Ollama qwen2.5vl 纯文本综合；Ollama 不可用时降级为规则拼接。
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

MODEL = "qwen2.5vl:7b"
API = "http://localhost:11434/api/chat"


def call_text(prompt):
    payload = {"model": MODEL,
               "messages": [{"role": "user", "content": prompt}],
               "stream": False, "options": {"num_ctx": 16384}}
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["message"]["content"]


def fmt_num(s):
    return s or "-"


def main():
    out_dir = Path(sys.argv[1]).resolve()
    meta_f = out_dir / "metadata.json"
    if not meta_f.exists():
        print("ERROR: 没有 metadata.json")
        sys.exit(1)
    meta = json.loads(meta_f.read_text(encoding="utf-8"))

    visual = ""
    vf = out_dir / "visual_analysis.txt"
    if vf.exists():
        visual = vf.read_text(encoding="utf-8").strip()

    transcript = ""
    tf = out_dir / "transcript.txt"
    if tf.exists():
        transcript = tf.read_text(encoding="utf-8").strip()

    # ---------- LLM 综合（失败降级） ----------
    synthesis = ""
    inputs = []
    if transcript:
        inputs.append("【语音口播转写】\n" + transcript[:6000])
    if visual:
        inputs.append("【画面视觉分析/OCR】\n" + visual[:6000])
    if meta.get("desc"):
        inputs.append("【帖子文案】\n" + meta["desc"][:1500])
    if inputs:
        try:
            print("[SUM] 调用本地模型综合 ...", flush=True)
            synthesis = call_text(
                "以下是小红书视频帖的多模态素材（语音转写 + 画面分析 + 文案），"
                "请综合写出 200~350 字的《内容总结》：视频在教什么/卖什么、"
                "核心步骤或卖点、适合谁看、有什么需要注意的（合规/真实性）。"
                "用中文，直接给正文，不要标题。\n\n" + "\n\n".join(inputs))
        except Exception as e:
            print(f"[SUM] LLM 综合失败（{e}），降级为规则拼接", flush=True)
    if not synthesis:
        parts = []
        if transcript:
            parts.append("**口播要点**：" + " ".join(transcript.split())[:400] + "……")
        if visual:
            parts.append("**画面要点**：见下方视觉分析。")
        synthesis = "\n\n".join(parts) or "（素材不足，未生成综合）"

    # ---------- 组装 markdown ----------
    L = ["# 小红书视频帖内容总结（自动生成）", ""]
    L.append("## 1. 基本信息")
    L.append(f"- **标题**：{meta.get('title') or '-'}")
    L.append(f"- **作者**：{meta.get('author') or '-'}")
    L.append(f"- **发布时间**：{meta.get('publish_time_text') or '-'}")
    L.append(f"- **链接**：{meta.get('url') or '-'}")
    video_f = out_dir / "video.mp4"
    if video_f.exists():
        L.append(f"- **视频文件**：`video.mp4`（{video_f.stat().st_size/1e6:.1f} MB）")
    L.append("")

    if meta.get("desc"):
        L += ["## 2. 文案原文", "", "> " + meta["desc"].replace("\n", "\n> "), ""]

    tags = meta.get("tags") or []
    if tags:
        L += ["## 3. 话题标签", "、".join(tags), ""]

    stats = meta.get("stats") or {}
    if stats:
        L += ["## 4. 互动数据", "", "| 指标 | 数值 |", "|---|---|"]
        for k, label in (("like", "点赞"), ("collect", "收藏"),
                         ("comment", "评论"), ("share", "分享")):
            if stats.get(k):
                L.append(f"| {label} | {fmt_num(stats[k])} |")
        L.append("")

    chapters = meta.get("chapters") or []
    if chapters:
        L += ["## 5. 视频「时刻」章节"] + \
             [f"- **{t} — {c}**" for t, c in chapters] + [""]

    if transcript:
        L += ["## 6. 🎙️ 语音口播转写（whisper）", "", transcript, ""]

    if visual:
        L += ["## 7. 🎬 视频画面内容（视觉分析 + OCR）", "", visual, ""]

    comments = meta.get("comments") or []
    if comments:
        L += ["## 8. 评论摘录（前 %d 条，置顶优先）" % len(comments)]
        ordered = sorted(comments, key=lambda c: not c.get("pinned"))
        for c in ordered[:15]:
            pin = "📌 " if c.get("pinned") else ""
            like = f"（赞 {c['like']}）" if c.get("like") else ""
            L.append(f"- {pin}**{c.get('author') or '?'}**{like}：{c.get('content')}")
        L.append("")

    L += ["## 9. 内容总结", "", synthesis, ""]
    if not transcript:
        L.append("> ⚠️ 语音未转写（缺 whisper 模型，把 ggml-base.bin 放 bin/models/ 后重跑）")
        L.append("")

    (out_dir / "summary.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[SUM] 完成 -> {out_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
