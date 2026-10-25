#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量多链接抓取 + 全流程分析。
用法：
  python batch_run.py urls.txt                 # 每行一个帖子链接，# 开头为注释
  python batch_run.py urls.txt --force         # 已完成的也重跑
  python batch_run.py urls.txt --no-asr        # 跳过语音转写
  python batch_run.py urls.txt --no-visual     # 跳过视觉分析
流程（每条链接）：
  抓取(xhs_scraper) -> 抽帧(ffmpeg) -> 视觉分析(VLM) -> 语音转写(whisper) -> 汇总(summary.md)
已完成判定：output/<note_id>/summary.md 存在且非 --force 则跳过。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SCRIPTS = BASE / "scripts"
OUTPUT = BASE / "output"
PY = sys.executable

FFMPEG_CANDIDATES = [
    None,  # 稍后 shutil.which
    r"C:\Users\16704\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe",
]


def find_ffmpeg():
    import shutil
    for c in FFMPEG_CANDIDATES:
        if c and Path(c).exists():
            return c
    return shutil.which("ffmpeg")


def note_id_from_url(url):
    m = re.search(r"/(?:explore|discovery/item)/([0-9a-f]{24})", url)
    if m:
        return m.group(1)
    m = re.search(r"/([0-9a-f]{24})", url)
    return m.group(1) if m else None


def run_step(name, cmd, timeout=1800):
    print(f"\n===== [{name}] {' '.join(str(c) for c in cmd[1:])}", flush=True)
    r = subprocess.run([str(c) for c in cmd], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    tail = (r.stdout or "").strip().splitlines()[-6:]
    for line in tail:
        print("  | " + line, flush=True)
    if r.returncode != 0:
        print(f"  !! {name} 失败 exit={r.returncode}", flush=True)
        err = (r.stderr or "").strip().splitlines()[-5:]
        for line in err:
            print("  !! " + line, flush=True)
        return False
    return True


def extract_frames(out_dir, ffmpeg, interval=8, width=640):
    """每 interval 秒一帧，宽缩到 width；已有帧则跳过"""
    frames = out_dir / "frames"
    if any(frames.glob("*.jpg")):
        print("[FRAME] 已有抽帧，跳过", flush=True)
        return True
    frames.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [ffmpeg, "-y", "-i", str(out_dir / "video.mp4"),
         "-vf", f"fps=1/{interval},scale={width}:-1",
         str(frames / "f%03d.jpg")],
        capture_output=True, text=True)
    n = len(list(frames.glob("*.jpg")))
    print(f"[FRAME] 抽出 {n} 帧", flush=True)
    return n > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url_file")
    ap.add_argument("--force", action="store_true", help="已完成也重跑")
    ap.add_argument("--skip-scrape", action="store_true",
                    help="跳过抓取步骤（需要 output/<id>/video.mp4 已存在）")
    ap.add_argument("--no-asr", action="store_true")
    ap.add_argument("--no-visual", action="store_true")
    ap.add_argument("--comments", type=int, default=20)
    args = ap.parse_args()

    urls = []
    for line in Path(args.url_file).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    if not urls:
        print("URL 列表为空")
        sys.exit(1)

    ffmpeg = find_ffmpeg()
    model_ok = (BASE / "bin" / "models" / "ggml-base.bin").exists()
    print(f"共 {len(urls)} 条链接 | ffmpeg={'√' if ffmpeg else '×'} | "
          f"whisper={'√' if model_ok else '×'}")

    results = []
    for i, url in enumerate(urls, 1):
        nid = note_id_from_url(url)
        if not nid:
            results.append((url, "SKIP", "无法解析 note_id"))
            continue
        out_dir = OUTPUT / nid
        done = (out_dir / "summary.md").exists()
        if done and not args.force:
            results.append((url, "SKIP", "已有 summary.md（--force 可重跑）"))
            print(f"\n[{i}/{len(urls)}] {nid} 已完成，跳过")
            continue

        print(f"\n>>> [{i}/{len(urls)}] {nid}", flush=True)
        status, detail = "OK", ""
        try:
            # 1) 抓取
            if args.skip_scrape:
                if not (out_dir / "video.mp4").exists():
                    raise RuntimeError("--skip-scrape 但目录里没有 video.mp4")
                print("[SCRAPER] 按 --skip-scrape 跳过", flush=True)
            elif not run_step("SCRAPER", [
                    PY, SCRIPTS / "xhs_scraper.py", url,
                    "--comments", args.comments]):
                raise RuntimeError("抓取失败")

            # 2) 抽帧 + 视觉
            if not args.no_visual and ffmpeg:
                extract_frames(out_dir, ffmpeg)
                if not run_step("VISUAL", [PY, SCRIPTS / "visual_analyze.py", out_dir]):
                    print("  （视觉分析失败，继续后面步骤）", flush=True)
            elif args.no_visual:
                print("[VISUAL] 按参数跳过", flush=True)

            # 3) 语音转写
            if not args.no_asr and model_ok:
                if not run_step("ASR", [PY, SCRIPTS / "transcribe.py", out_dir]):
                    print("  （转写失败，继续后面步骤）", flush=True)

            # 4) 汇总
            if not run_step("SUMMARY", [PY, SCRIPTS / "make_summary.py", out_dir]):
                raise RuntimeError("汇总失败")
            detail = "summary.md 已生成"
        except Exception as e:
            status, detail = "FAIL", str(e)

        results.append((url, status, detail))

    print("\n========== 批量结果 ==========")
    for url, st, d in results:
        print(f"[{st}] {note_id_from_url(url) or url} — {d}")
    ok = sum(1 for _, s, _ in results if s == "OK")
    skip = sum(1 for _, s, _ in results if s == "SKIP")
    print(f"\n完成 {ok} / 跳过 {skip} / 失败 {len(results)-ok-skip}")


if __name__ == "__main__":
    main()
