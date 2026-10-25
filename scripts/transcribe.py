#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语音口播转写：whisper.cpp (ggml 模型, CPU)。
用法：python transcribe.py <output_dir> [--model ggml-base.bin] [--lang zh]
产出：<output_dir>/transcript.txt（whisper 原始带段落）+ transcript_plain.txt（纯文本）
注意：whisper.cpp v1.6.x 窄字符 fopen 读不了中文路径，
     故把模型/音频复制到 ASCII 临时目录里跑，跑完拷回。
"""
import argparse
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BIN = BASE / "bin"
MODELS = BIN / "models"
FFMPEG_CANDIDATES = [
    shutil.which("ffmpeg"),
    r"C:\Users\16704\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe",
    r"C:\Users\16704\AppData\Local\Microsoft\WinGet\Links\ffmpeg",
]


def find_ffmpeg():
    for c in FFMPEG_CANDIDATES:
        if c and Path(c).exists():
            return c
    return None


def ascii_cache(src: Path, tag: str) -> Path:
    """把文件复制到 ASCII 临时目录（同名同大小则跳过），返回新路径"""
    cache_dir = Path(tempfile.gettempdir()) / "xhs_asr"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dst = cache_dir / f"{tag}_{src.name}"
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return dst
    shutil.copy2(src, dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--model", default="ggml-base.bin")
    ap.add_argument("--lang", default="zh")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    video = out_dir / "video.mp4"
    if not video.exists():
        print("ERROR: 没有 video.mp4")
        sys.exit(1)

    model = MODELS / args.model
    if not model.exists():
        print(f"ERROR: 模型不存在 {model}（放到 bin/models/ 下）")
        sys.exit(1)

    main_exe = BIN / "main.exe"
    if not main_exe.exists():
        print(f"ERROR: 找不到 whisper.cpp 可执行文件 {main_exe}")
        sys.exit(1)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("ERROR: 找不到 ffmpeg")
        sys.exit(1)

    # 1) 16kHz 单声道 wav（whisper 要求）
    wav = out_dir / "audio16k.wav"
    print("[ASR] 提取 16kHz 单声道音频 ...", flush=True)
    r = subprocess.run(
        [ffmpeg, "-y", "-i", str(video), "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", str(wav)],
        capture_output=True, text=True)
    if not wav.exists():
        print("ERROR: 音频提取失败:\n" + (r.stderr or "")[-800:])
        sys.exit(1)

    # 2) 中文路径中转：模型 + 音频复制到 ASCII 临时目录
    print("[ASR] 准备 ASCII 路径中转（whisper.cpp 不认中文路径）...", flush=True)
    m_cached = ascii_cache(model, "m")
    w_cached = ascii_cache(wav, "w")  # 音频每次都可能变，按大小比对
    prefix_cached = Path(tempfile.gettempdir()) / "xhs_asr" / "transcript"

    # 3) whisper.cpp 转写
    print(f"[ASR] whisper.cpp 转写（{args.lang}，CPU，约 1-3 分钟）...", flush=True)
    r = subprocess.run(
        [str(main_exe), "-m", str(m_cached), "-f", str(w_cached),
         "-l", args.lang, "-of", str(prefix_cached), "-otxt"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt_cached = prefix_cached.with_suffix(".txt")
    if not txt_cached.exists():
        print("ERROR: 转写失败:\n" + (r.stderr or r.stdout or "")[-1200:])
        sys.exit(1)

    # 4) 拷回 + 生成纯文本版
    txt = out_dir / "transcript.txt"
    shutil.copy2(txt_cached, txt)
    content = txt.read_text(encoding="utf-8").strip()
    (out_dir / "transcript_plain.txt").write_text(
        " ".join(content.split()), encoding="utf-8")
    print(f"[ASR] 完成，{len(content)} 字")
    print(content[:300])


if __name__ == "__main__":
    main()
