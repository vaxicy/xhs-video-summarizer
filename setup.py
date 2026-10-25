#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键准备运行环境（跨平台）。

做什么：
  1) 在仓库根建 .venv（若已有则复用）
  2) 装 requirements.txt（Playwright）
  3) 下载 Chromium 浏览器（playwright install chromium）
  4) 下载 whisper 模型 ggml-base.bin 到 bin/models/（若缺失）

whisper.cpp 的二进制本体（main.exe / whisper.dll / SDL2.dll）需自行放入 bin/：
  - Windows：把 whisper.cpp 构建产物（或第三方预编译包）的这三个文件拷到 bin/
  - macOS / Linux：放对应平台的二进制；文件名保持 main / whisper.so / libSDL2
模型较大（约 141MB），仅首次下载；想更准可换 bin/models/ggml-small.bin 并在
transcribe.py 传 --model ggml-small.bin。
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
BIN = ROOT / "bin"
MODELS = BIN / "models"

MODEL_URLS = [
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
    "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
]


def log(msg):
    print("[setup] " + msg, flush=True)


def run(cmd, **kw):
    log(" ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def venv_python():
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def main():
    # 1) venv
    if not venv_python().exists():
        log("创建虚拟环境 .venv ...")
        run([sys.executable, "-m", "venv", str(VENV)])
    py = venv_python()

    # 2) 依赖
    log("安装 Python 依赖 ...")
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])

    # 3) Chromium
    log("下载 Chromium（Playwright）...")
    run([py, "-m", "playwright", "install", "chromium"])
    if sys.platform.startswith("linux"):
        try:
            run([py, "-m", "playwright", "install-deps", "chromium"])
        except Exception as e:
            log(f"install-deps 失败（可忽略，手动装系统库即可）：{e}")

    # 4) whisper 模型
    MODELS.mkdir(parents=True, exist_ok=True)
    model = MODELS / "ggml-base.bin"
    if model.exists():
        log(f"whisper 模型已存在：{model}")
    else:
        ok = False
        for url in MODEL_URLS:
            try:
                log(f"下载 whisper 模型：{url}")
                urllib.request.urlretrieve(url, str(model))
                ok = True
                break
            except Exception as e:
                log(f"  下载失败：{e}")
        if not ok:
            log("模型下载失败，请手动把 ggml-base.bin 放到 bin/models/")

    # whisper 二进制检查
    main_bin = BIN / ("main.exe" if sys.platform == "win32" else "main")
    if not main_bin.exists():
        log("⚠️ 未找到 whisper.cpp 二进制（bin/main" +
            (".exe" if sys.platform == "win32" else "") +
            "），请放入后再运行抓取流程。")
    else:
        log(f"whisper 二进制就绪：{main_bin}")

    log("环境准备完成。运行示例：")
    if sys.platform == "win32":
        log(f'  {VENV / "Scripts" / "python.exe"} scripts/batch_run.py urls.txt')
    else:
        log(f"  {VENV / 'bin' / 'python'} scripts/batch_run.py urls.txt")


if __name__ == "__main__":
    main()
