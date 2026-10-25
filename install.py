#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本 skill 以目录联接（junction / symlink）装进各 Agent 的 skills 目录。

目标宿主（同一台机器上的不同 Agent 客户端，共用一份代码，避免多份漂移）：
  - WorkBuddy : ~/.workbuddy/skills/
  - Codex     : ~/.codex/skills/
  - Claude    : ~/.claude/skills/

Windows 用 mklink /J（目录联接，无需管理员）；macOS / Linux 用 ln -s。
已存在的链接会跳过；若目标已是一个真实目录则提示手动处理。

用法：  python install.py            # 装全部检测到的宿主
        python install.py --workbuddy # 只装某个
        python install.py --list      # 只打印将链接到的位置
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL_NAME = ROOT.name  # 目录名即 skill 名

HOSTS = {
    "workbuddy": Path.home() / ".workbuddy" / "skills",
    "codex":     Path.home() / ".codex" / "skills",
    "claude":    Path.home() / ".claude" / "skills",
}


def log(msg):
    print("[install] " + msg, flush=True)


def link(src: Path, dst: Path):
    """在 dst 处建立指向 src 的目录联接/符号链接。"""
    if dst.exists() or dst.is_symlink():
        # 已是链接且指向相同 → 跳过
        try:
            if dst.resolve() == src.resolve():
                log(f"已链接，跳过：{dst}")
                return True
        except Exception:
            pass
        log(f"⚠️ 目标已存在且非本 skill 链接，跳过：{dst}（请手动处理）")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        # /J 目录联接，不要求管理员
        subprocess.run(["cmd", "/c", "mklink", "/J",
                        str(dst), str(src)], check=True)
    else:
        os.symlink(str(src), str(dst), target_is_directory=True)
    log(f"已链接：{dst}  ->  {src}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workbuddy", action="store_true")
    ap.add_argument("--codex", action="store_true")
    ap.add_argument("--claude", action="store_true")
    ap.add_argument("--list", action="store_true", help="只打印目标位置")
    args = ap.parse_args()

    selected = {k: v for k, v in HOSTS.items()
                if getattr(args, k)}
    if not selected:
        selected = HOSTS  # 默认全装

    if args.list:
        for k, v in selected.items():
            print(f"{k:10s} -> {v / SKILL_NAME}")
        return

    for k, v in selected.items():
        link(ROOT, v / SKILL_NAME)


if __name__ == "__main__":
    main()
