#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书视频帖抓取器：扫码登录(持久profile) -> 抓元数据/评论 -> 下载视频"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent.parent
PROFILE = BASE / "data" / "profile"
OUTPUT = BASE / "output"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def out(ok, **kw):
    print(json.dumps({"ok": ok, **kw}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


def note_id_from_url(url):
    m = re.search(r"/(?:explore|discovery/item)/([0-9a-f]{24})", url)
    if m:
        return m.group(1)
    m = re.search(r"/([0-9a-f]{24})", url)
    return m.group(1) if m else None


def is_logged_in(ctx):
    for c in ctx.cookies("https://www.xiaohongshu.com"):
        if c["name"] == "web_session" and c["value"]:
            return True
    return False


def wait_login(ctx, page, timeout_s):
    """弹窗已在页面时等扫码；尝试点登录按钮唤起二维码"""
    print("[LOGIN] 未登录：请在弹出的浏览器窗口扫码登录小红书 ...", flush=True)
    for sel in (".login-btn", ".side-bar-component .login-btn", "text=登录"):
        try:
            page.locator(sel).first.click(timeout=2000)
            break
        except Exception:
            continue
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if is_logged_in(ctx):
                print("[LOGIN] 登录成功", flush=True)
                return True
        except Exception:
            pass
        time.sleep(1.5)
    return False


EXTRACT_JS = """
() => {
  const t = (sel) => { const el = document.querySelector(sel); return el ? el.innerText.trim() : null; };
  const tagEls = [...document.querySelectorAll('#detail-desc .tag')];
  const counts = {};
  document.querySelectorAll('[class*="wrapper"]').forEach(w => {
    const c = w.querySelector('.count');
    if (!c) return;
    const cls = (w.className || '').toString();
    let key = null;
    if (cls.includes('like')) key = 'like';
    else if (cls.includes('collect')) key = 'collect';
    else if (cls.includes('chat')) key = 'comment';
    else if (cls.includes('share')) key = 'share';
    if (key) counts[key] = c.innerText.trim();
  });
  const video = document.querySelector('.player-el video, #noteContainer video, video');
  let video_src = null;
  if (video) {
    const srcEl = video.querySelector('source') || video;
    video_src = srcEl.getAttribute('src') || srcEl.src || null;
  }
  return {
    title: t('#detail-title'),
    desc: t('#detail-desc'),
    tags: tagEls.map(a => a.innerText.trim().replace(/^#/, '')),
    author: t('.author-container .username') || t('.info .username'),
    time_text: t('.bottom-container .date') || t('.date'),
    counts,
    video_src,
  };
}
"""


def scroll_comments(page, want):
    """滚动评论容器收集评论 DOM"""
    seen, order = {}, []
    sel = ".comment-item"
    for _ in range(24):
        items = page.eval_on_selector_all(
            sel,
            """els => els.map(e => ({
                 author: e.querySelector('.author .name')?.innerText?.trim() || null,
                 content: e.querySelector('.content, .note-text')?.innerText?.trim() || null,
                 like: e.querySelector('.like .count')?.innerText?.trim() || null,
                 time_loc: e.querySelector('.date, .time')?.innerText?.trim() || null,
                 pinned: !!e.querySelector('.pin') || e.innerText.includes('置顶'),
               }))""")
        for it in items:
            if not it["content"]:
                continue
            key = (it["author"], it["content"])
            if key not in seen:
                seen[key] = it
                order.append(key)
        if len(order) >= want:
            break
        scrolled = page.evaluate(
            """() => { const c = document.querySelector('.comments-el, .comments-container, .interaction-container');
                        if (c) { c.scrollTop = c.scrollHeight; return true; }
                        window.scrollBy(0, 1200); return false; }""")
        page.wait_for_timeout(900)
    return [seen[k] for k in order[:want]]


def parse_stats(state_raw):
    """从 __INITIAL_STATE__ 解析互动数据（万为单位时带中文）"""
    stats = {}
    if not state_raw:
        return stats
    for key, fld in (("like", "likedCount"), ("collect", "collectedCount"),
                     ("comment", "commentCount"), ("share", "shareCount")):
        m = re.search(r'"%s"\s*:\s*"?([0-9A-Za-z.万+]+)"?' % fld, state_raw)
        if m:
            stats[key] = m.group(1)
    return stats


def find_video_url(state_raw, dom_src):
    if dom_src and not dom_src.startswith("blob:"):
        return dom_src
    if state_raw:
        m = re.search(r'(?:https?:)?//[^\"\'\s]+?sns-video[^\"\'\s]*?\.mp4[^\"\'\s]*',
                      state_raw)
        if m:
            u = m.group(0)
            if u.startswith("//"):
                u = "https:" + u
            return u
        m = re.search(r'\"masterUrl\"\s*:\s*\"([^\"]+)\"', state_raw)
        if m:
            return m.group(1)
        m = re.search(r'\"playableUrl\"\s*:\s*\"([^\"]+)\"', state_raw)
        if m:
            return m.group(1)
    return None


def open_post(page, url, timeout=60000):
    """打开帖子，等待详情渲染；处理可能出现的验证页/加载慢，重试 3 次"""
    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"[WARN] goto 异常: {e}", flush=True)
        try:
            page.wait_for_function(
                "() => document.querySelector('#detail-title') || "
                "document.querySelector('.note-content') || "
                "document.querySelector('#detail-desc')",
                timeout=timeout)
            return True
        except Exception:
            txt = ""
            try:
                txt = page.evaluate(
                    "() => document.body ? document.body.innerText.slice(0,200) : ''")
            except Exception:
                pass
            if ("验证" in txt) or ("滑块" in txt):
                print("[WARN] 出现验证页，等待后重试 ...", flush=True)
                page.wait_for_timeout(3500)
                continue
            print(f"[WARN] 第 {attempt+1} 次未渲染，重试 ...", flush=True)
            page.wait_for_timeout(2500)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--comments", type=int, default=20)
    ap.add_argument("--timeout", type=int, default=180, help="等扫码秒数")
    args = ap.parse_args()

    nid = note_id_from_url(args.url)
    if not nid:
        out(False, error="无法从 URL 解析 note_id")
    out_dir = OUTPUT / nid
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, locale="zh-CN",
            viewport={"width": 1440, "height": 900},
            user_agent=UA)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            if not is_logged_in(ctx):
                page.goto("https://www.xiaohongshu.com/explore",
                          wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                if not wait_login(ctx, page, args.timeout):
                    out(False, error="等待扫码超时，未登录")
            page.wait_for_timeout(2000)  # 登录后歇一下，避开验证/重定向态

            print("[FETCH] 打开帖子 ...", flush=True)
            if not open_post(page, args.url):
                out(False, error="帖子未渲染（可能被风控/需验证）")

            data = page.evaluate(EXTRACT_JS)
            state_raw = page.evaluate(
                "() => { try { return JSON.stringify(window.__INITIAL_STATE__); } catch(e) { return null; } }")
            if state_raw:
                (out_dir / "metadata_raw.json").write_text(state_raw, encoding="utf-8")

            # 章节/时刻：从 state 里挖 chapter/segment 类字段
            chapters = []
            if state_raw:
                try:
                    st = json.loads(state_raw)
                    map_ = (st.get("note") or {}).get("noteDetailMap") or {}
                    for v in map_.values():
                        note = v.get("note") if isinstance(v, dict) else None
                        if not note:
                            continue
                        for key in ("video",):
                            vd = note.get(key) or {}
                            for ck in ("chapter", "chapters", "segment", "moments",
                                       "videoChapter", "capa"):
                                if ck in vd:
                                    chapters.append(vd[ck])
                        # capa 里通常在 modules -> chapter
                        capa = (note.get("video") or {}).get("capa") or {}
                        mods = capa.get("modules") or {}
                        for mk, mv in mods.items():
                            if "chapter" in mk.lower() or "moment" in mk.lower():
                                chapters.append(mv)
                except Exception as e:
                    print(f"[WARN] state 解析失败: {e}", flush=True)

            print("[FETCH] 抓评论 ...", flush=True)
            comments = scroll_comments(page, args.comments)

            video_url = find_video_url(state_raw, data.get("video_src"))
            video_file = None
            if video_url:
                print(f"[DL] 下载视频: {video_url[:80]} ...", flush=True)
                try:
                    r = ctx.request.get(
                        video_url,
                        headers={"Referer": "https://www.xiaohongshu.com/",
                                 "User-Agent": UA})
                    if r.ok:
                        vf = out_dir / "video.mp4"
                        vf.write_bytes(r.body())
                        video_file = str(vf)
                        print(f"[DL] 完成 {len(r.body())/1e6:.1f} MB", flush=True)
                    else:
                        print(f"[DL] HTTP {r.status}，跳过", flush=True)
                except Exception as e:
                    print(f"[DL] 失败: {e}", flush=True)

            stats = parse_stats(state_raw)
            stats.update({k: v for k, v in (data.get("counts") or {}).items()
                         if v})  # DOM 兜底
            meta = {
                "note_id": nid,
                "url": args.url,
                "title": data.get("title"),
                "desc": data.get("desc"),
                "tags": data.get("tags") or [],
                "author": data.get("author"),
                "publish_time_text": data.get("time_text"),
                "stats": stats,
                "chapters": re.findall(r"#(\d{1,2}:\d{2})\[时刻\]#\s*(.+)",
                                       data.get("desc") or ""),
                "chapters_raw": chapters,
                "comments": comments,
                "video_url": video_url,
                "video_file": video_file,
            }
            (out_dir / "metadata.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            out(True, out_dir=str(out_dir), video=bool(video_file),
                comments=len(comments))
        finally:
            try:
                ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
