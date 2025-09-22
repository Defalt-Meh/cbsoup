#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, statistics, argparse, random, csv, pathlib, hashlib
from typing import Tuple, Optional, List, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# your package structure: pywebcopy/session.py
from pywebcopy.session import Session

# ------------------------------ Config ----------------------------------------

DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Retry/backoff
MAX_RETRIES = 4
BACKOFF_BASE = 0.2   # seconds
BACKOFF_CAP = 2.5    # seconds

# Only store these asset types
ASSET_EXT_ALLOW = {".css", ".js"}

# -------------------------- Small helpers -------------------------------------

def _sleep_backoff(attempt: int):
    t = BACKOFF_BASE * (2 ** attempt) * (1.0 + random.random() * 0.25)
    time.sleep(min(t, BACKOFF_CAP))

def _safe_join(root: str, *parts: str) -> str:
    p = pathlib.Path(root)
    for part in parts:
        # avoid .. traversal and query fragments in filenames
        part = part.replace("..", "").replace(":", "_")
        p = p / part
    return str(p)

def _hash_name(s: str, prefix: str) -> str:
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{h}"

def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def _ext_from_url(u: str) -> str:
    path = urlparse(u).path
    ext = os.path.splitext(path)[1].lower()
    return ext

def _should_download_asset(u: str) -> bool:
    return _ext_from_url(u) in ASSET_EXT_ALLOW

def _normalize_asset_name(asset_url: str) -> str:
    """
    Make a reasonably stable filename from URL path; fall back to hash if needed.
    """
    pr = urlparse(asset_url)
    name = os.path.basename(pr.path) or _hash_name(asset_url, "asset")
    # strip query so foo.css?v=123 -> foo.css
    if "?" in name:
        name = name.split("?", 1)[0]
    if not os.path.splitext(name)[1]:
        # no extension? add .txt to be safe (but we only store .css/.js anyway)
        name += ".txt"
    # avoid super-long names
    if len(name) > 80:
        name = _hash_name(asset_url, "long")
        ext = _ext_from_url(asset_url)
        if ext:
            name += ext
    return name

# ------------------------ Fetchers (requests / opt) ---------------------------

def _fetch_requests(sess: requests.Session, url: str, timeout: float) -> Tuple[int, bytes, str]:
    last: Optional[Exception] = None
    for i in range(MAX_RETRIES):
        try:
            r = sess.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True, stream=False)
            if r.status_code in (429, 503):
                _sleep_backoff(i); continue
            r.raise_for_status()
            return r.status_code, r.content, r.url
        except requests.RequestException as e:
            last = e; _sleep_backoff(i)
    raise last or RuntimeError("fetch failed")

def _fetch_optimized(sess: Session, url: str, timeout: float, obey_robots: bool) -> Tuple[int, bytes, str]:
    # set once per run (no-op if unchanged)
    sess.set_follow_robots_txt(obey_robots)
    last: Optional[Exception] = None
    for i in range(MAX_RETRIES):
        try:
            r = sess.get(url, timeout=timeout, allow_redirects=True, stream=False, headers=DEFAULT_HEADERS)
            if r.status_code in (429, 503):
                _sleep_backoff(i); continue
            r.raise_for_status()
            return r.status_code, r.content, r.url
        except requests.RequestException as e:
            last = e; _sleep_backoff(i)
    raise last or RuntimeError("fetch failed")

# ---------------------------- Parsing & discovery -----------------------------

CSS_IMPORT_RE = re.compile(r"""@import\s+(?:url\()?['"]?([^'")\s]+)""", re.I)

def _parse_title_links(html: bytes):
    s = BeautifulSoup(html, "lxml")
    title = (s.title.string.strip() if s.title and s.title.string else "")
    links = len(s.find_all("a", href=True))
    return s, title, links

def _discover_assets_from_html(soup: BeautifulSoup, base_url: str) -> Tuple[Set[str], Set[str]]:
    css_urls: Set[str] = set()
    js_urls: Set[str] = set()

    # <link rel="stylesheet" href="...">
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel", [])).lower() if isinstance(link.get("rel"), list) else str(link.get("rel") or "").lower()
        if "stylesheet" in rel:
            u = urljoin(base_url, link["href"])
            if _should_download_asset(u):
                css_urls.add(u)

    # <script src="...">
    for sc in soup.find_all("script", src=True):
        u = urljoin(base_url, sc["src"])
        if _should_download_asset(u):
            js_urls.add(u)

    # @import inside inline <style> blocks
    for style in soup.find_all("style"):
        if style.string:
            for m in CSS_IMPORT_RE.finditer(style.string):
                u = urljoin(base_url, m.group(1))
                if _should_download_asset(u):
                    css_urls.add(u)

    return css_urls, js_urls

def _discover_css_imports_in_bytes(css_bytes: bytes, base_url: str) -> Set[str]:
    out: Set[str] = set()
    try:
        text = css_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return out
    for m in CSS_IMPORT_RE.finditer(text):
        out.add(urljoin(base_url, m.group(1)))
    return out

# ------------------------------ Saving ----------------------------------------

def _save_bytes(dst_dir: str, filename: str, content: bytes):
    _ensure_dir(dst_dir)
    path = os.path.join(dst_dir, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path

def _target_dirs(root_res: str, bucket: str, final_url: str) -> Tuple[str, str, str]:
    """
    Returns (root_dir_for_bucket, site_dir, html_dir)
    e.g., ('res/opt', 'res/opt/amazon.com', 'res/opt/amazon.com/html')
    """
    netloc = urlparse(final_url).netloc or "site"
    bucket_root = _safe_join(root_res, bucket)
    site_dir = _safe_join(bucket_root, netloc)
    html_dir = _safe_join(site_dir, "html")
    _ensure_dir(html_dir)
    return bucket_root, site_dir, html_dir

# ------------------------------ Asset download --------------------------------

def _download_assets(sess, urls: Set[str], timeout: float, dest_dir: str, base_url: str,
                     label: str) -> Tuple[int, List[str]]:
    """
    Downloads given asset URLs (CSS/JS). Returns (count, saved_paths).
    Also resolves @import in CSS and fetches those recursively (1-level deep).
    """
    saved = []
    seen: Set[str] = set()
    queue: List[str] = [u for u in urls if u not in seen and _should_download_asset(u)]
    count = 0

    while queue:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)

        # Choose fetcher based on label
        last_exc: Optional[Exception] = None
        for i in range(MAX_RETRIES):
            try:
                r = sess.get(u, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True, stream=False)
                if r.status_code in (429, 503):
                    _sleep_backoff(i); continue
                r.raise_for_status()
                content = r.content
                final_u = r.url
                break
            except requests.RequestException as e:
                last_exc = e; _sleep_backoff(i)
        else:
            # failed after retries; skip
            continue

        fname = _normalize_asset_name(final_u)
        path = _save_bytes(dest_dir, fname, content)
        saved.append(path)
        count += 1

        # If CSS, parse @import and enqueue (1 level)
        if _ext_from_url(final_u) == ".css":
            imports = _discover_css_imports_in_bytes(content, final_u)
            for dep in imports:
                if dep not in seen and _should_download_asset(dep):
                    queue.append(dep)

    return count, saved

# ------------------------------ One iteration ---------------------------------

def run_once(url: str, timeout: float, obey_robots: bool,
             opt: Session, plain: requests.Session, res_root: str):

    # ---------- OPT ----------
    t0 = time.perf_counter()
    code_o, body_o, final_o = _fetch_optimized(opt, url, timeout, obey_robots)
    t1 = time.perf_counter()
    soup_o, title_o, links_o = _parse_title_links(body_o)
    css_o, js_o = _discover_assets_from_html(soup_o, final_o)
    # dirs for saving
    _, site_o, html_o_dir = _target_dirs(res_root, "opt", final_o)
    html_o_path = _save_bytes(html_o_dir, "index.html", body_o)
    assets_o_dir = _safe_join(site_o, "assets")
    a0 = time.perf_counter()
    cnt_css_o, saved_css_o = _download_assets(opt, css_o, timeout, assets_o_dir, final_o, "opt")
    cnt_js_o, saved_js_o = _download_assets(opt, js_o, timeout, assets_o_dir, final_o, "opt")
    a1 = time.perf_counter()

    # ---------- BS4 (requests) ----------
    t2 = time.perf_counter()
    code_b, body_b, final_b = _fetch_requests(plain, url, timeout)
    t3 = time.perf_counter()
    soup_b, title_b, links_b = _parse_title_links(body_b)
    css_b, js_b = _discover_assets_from_html(soup_b, final_b)
    _, site_b, html_b_dir = _target_dirs(res_root, "bs4", final_b)
    html_b_path = _save_bytes(html_b_dir, "index.html", body_b)
    assets_b_dir = _safe_join(site_b, "assets")
    b0 = time.perf_counter()
    cnt_css_b, saved_css_b = _download_assets(plain, css_b, timeout, assets_b_dir, final_b, "bs4")
    cnt_js_b, saved_js_b = _download_assets(plain, js_b, timeout, assets_b_dir, final_b, "bs4")
    b1 = time.perf_counter()

    # Print per-iteration metrics
    print(f"[OPT] {code_o} html={len(body_o)}B  fetch={t1-t0:.3f}s  parse={t3-t2:.3f}s? (see BS4)  "
          f"assets={a1-a0:.3f}s (css={cnt_css_o}, js={cnt_js_o})  total={(a1-t0):.3f}s  "
          f"saved: {html_o_path}")
    print(f"[BS4] {code_b} html={len(body_b)}B  fetch={t3-t2:.3f}s  parse={b0-t3:.3f}s  "
          f"assets={b1-b0:.3f}s (css={cnt_css_b}, js={cnt_js_b})  total={(b1-t2):.3f}s  "
          f"saved: {html_b_path}")

    return {
        "opt_fetch": (t1 - t0),
        "opt_parse": (a0 - t1),  # parse+discover
        "opt_assets": (a1 - a0),
        "opt_total": (a1 - t0),
        "opt_css_count": cnt_css_o,
        "opt_js_count": cnt_js_o,
        "opt_html_bytes": len(body_o),

        "bs_fetch": (t3 - t2),
        "bs_parse": (b0 - t3),
        "bs_assets": (b1 - b0),
        "bs_total": (b1 - t2),
        "bs_css_count": cnt_css_b,
        "bs_js_count": cnt_js_b,
        "bs_html_bytes": len(body_b),
    }

# --------------------------------- Stats --------------------------------------

def stats(xs: List[float]):
    return dict(
        mean=statistics.mean(xs),
        median=statistics.median(xs),
        p95=(statistics.quantiles(xs, n=20)[18] if len(xs) >= 20 else max(xs)),
        min=min(xs),
        max=max(xs),
    )

# ---------------------------------- CLI ---------------------------------------

def main():
    p = argparse.ArgumentParser(description="Benchmark pywebcopy Session vs requests+BeautifulSoup (HTML + CSS/JS).")
    p.add_argument("--url", action="append",
                   help="Target URL. Can be given multiple times. "
                        "Default: https://www.amazon.com/ (if omitted).")
    p.add_argument("--iters", type=int, default=5, help="Measured iterations per URL.")
    p.add_argument("--warmup", type=int, default=1, help="Unmeasured warmup runs per URL.")
    p.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout (s).")
    p.add_argument("--obey-robots", action="store_true", help="Obey robots.txt in optimized Session.")
    p.add_argument("--csv", help="Optional CSV file to write summary results.")
    p.add_argument("--res-root", default="res", help="Root folder to save outputs (default: ./res).")
    args = p.parse_args()

    urls = args.url or ["https://www.amazon.com/"]

    # Prepare root output
    _ensure_dir(args.res_root)

    # Reuse sessions across all iterations and URLs
    opt = Session(); opt.headers.update(DEFAULT_HEADERS)
    plain = requests.Session(); plain.headers.update(DEFAULT_HEADERS)

    rows = []
    for url in urls:
        print(f"\nTarget: {url}")
        print(f"Iters: {args.iters} (warmup={args.warmup}) timeout={args.timeout:.1f}s obey_robots={args.obey_robots}")
        print("-----------------------------------------------------------------")

        # Warmups (not recorded)
        for _ in range(max(0, args.warmup)):
            try:
                run_once(url, args.timeout, args.obey_robots, opt, plain, args.res_root)
            except Exception as e:
                print("Warmup error:", e)

        # Measurements
        m = {
            "opt_fetch": [], "opt_parse": [], "opt_assets": [], "opt_total": [],
            "bs_fetch": [], "bs_parse": [], "bs_assets": [], "bs_total": [],
            "opt_css_count": [], "opt_js_count": [], "bs_css_count": [], "bs_js_count": [],
            "opt_html_bytes": [], "bs_html_bytes": [],
        }

        for i in range(max(1, args.iters)):
            try:
                r = run_once(url, args.timeout, args.obey_robots, opt, plain, args.res_root)
                for k, v in r.items():
                    m[k].append(v)
            except Exception as e:
                print(f"Iter {i+1} error:", e)

        if not m["opt_total"] or not m["bs_total"]:
            print("No successful iterations for this URL.")
            continue

        # Summary
        so_tot, sb_tot = stats(m["opt_total"]), stats(m["bs_total"])
        so_fetch, sb_fetch = stats(m["opt_fetch"]), stats(m["bs_fetch"])
        so_assets, sb_assets = stats(m["opt_assets"]), stats(m["bs_assets"])
        so_parse, sb_parse = stats(m["opt_parse"]), stats(m["bs_parse"])

        print("\n==================== Results ====================")
        print("TOTAL time (HTML+assets):")
        print(f"  Optimized Session:  mean={so_tot['mean']:.3f}s median={so_tot['median']:.3f}s "
              f"p95={so_tot['p95']:.3f}s min={so_tot['min']:.3f}s max={so_tot['max']:.3f}s")
        print(f"  Requests+BS4:      mean={sb_tot['mean']:.3f}s median={sb_tot['median']:.3f}s "
              f"p95={sb_tot['p95']:.3f}s min={sb_tot['min']:.3f}s max={sb_tot['max']:.3f}s")

        print("\nBreakdown:")
        print(f"  Fetch only:   OPT mean={so_fetch['mean']:.3f}s | BS4 mean={sb_fetch['mean']:.3f}s")
        print(f"  Parse only:   OPT mean={so_parse['mean']:.3f}s | BS4 mean={sb_parse['mean']:.3f}s")
        print(f"  Assets only:  OPT mean={so_assets['mean']:.3f}s | BS4 mean={sb_assets['mean']:.3f}s")
        print(f"  Avg counts:   OPT css={statistics.mean(m['opt_css_count']):.1f}, "
              f"js={statistics.mean(m['opt_js_count']):.1f} | "
              f"BS4 css={statistics.mean(m['bs_css_count']):.1f}, "
              f"js={statistics.mean(m['bs_js_count']):.1f}")
        print("=================================================\n")

        # Row for CSV
        rows.append({
            "url": url,
            "opt_total_mean": so_tot["mean"], "opt_total_median": so_tot["median"], "opt_total_p95": so_tot["p95"],
            "bs_total_mean": sb_tot["mean"], "bs_total_median": sb_tot["median"], "bs_total_p95": sb_tot["p95"],
            "opt_fetch_mean": so_fetch["mean"], "bs_fetch_mean": sb_fetch["mean"],
            "opt_parse_mean": so_parse["mean"], "bs_parse_mean": sb_parse["mean"],
            "opt_assets_mean": so_assets["mean"], "bs_assets_mean": sb_assets["mean"],
            "opt_css_avg": statistics.mean(m["opt_css_count"]), "opt_js_avg": statistics.mean(m["opt_js_count"]),
            "bs_css_avg": statistics.mean(m["bs_css_count"]), "bs_js_avg": statistics.mean(m["bs_js_count"]),
            "opt_html_bytes_last": m["opt_html_bytes"][-1], "bs_html_bytes_last": m["bs_html_bytes"][-1],
        })

    if args.csv and rows:
        _ensure_dir(os.path.dirname(args.csv) or ".")
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"Wrote CSV -> {args.csv}")

if __name__ == "__main__":
    main()
