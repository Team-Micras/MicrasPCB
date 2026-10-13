"""Static design portal: build/site/, one page per board, published by CI to GitHub Pages.

Each page shows the check results, schematic, layers, 3D model, BOM with JLCPCB data, the
mechanical spec with its sources, and every download, for one commit. Interactive schematic/PCB
viewing uses KiCanvas; the SVG/PNG views work without it.

    micras-pcb site     # after `micras-pcb outputs` and `micras-pcb fab`
"""

from __future__ import annotations

import csv
import html
import json
import os
import shutil
import subprocess
import tomllib
from datetime import UTC, datetime

from . import spec, status
from .jlc import parts_db
from .paths import BUILD, ROOT, board_pcb, board_sch, boards, build_dir

SITE = BUILD / "site"
KICANVAS = "https://kicanvas.org/kicanvas/kicanvas.js"
MODEL_VIEWER = "https://cdn.jsdelivr.net/npm/@google/model-viewer@4/dist/model-viewer.min.js"

CSS = """
:root{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e3e3de;--ok:#1f7a3a;--bad:#b42318;--acc:#2456a6}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#9a9993;--card:#201f1d;--line:#34332f;--ok:#4cc477;--bad:#ff7b6b;--acc:#7aa7ff}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:20px 32px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
header h1{margin:0;font-size:20px}header .meta{color:var(--muted);font-size:13px}
main{max-width:1200px;margin:0 auto;padding:24px 32px}a{color:var(--acc)}
nav.tabs{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:16px}nav.tabs a{padding:6px 12px;border:1px solid var(--line);border-radius:6px;text-decoration:none;color:var(--fg);background:var(--card)}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px;margin-bottom:20px}
section h2{margin:0 0 12px;font-size:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.grid img{width:100%;border-radius:6px;border:1px solid var(--line);background:#fff}
.badges{display:flex;gap:8px;flex-wrap:wrap}.badge{padding:4px 10px;border-radius:999px;font-size:13px;border:1px solid var(--line)}
.badge.ok{color:var(--ok);border-color:var(--ok)}.badge.bad{color:var(--bad);border-color:var(--bad)}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:500}.muted{color:var(--muted)}
.svgview{background:#fff;border-radius:6px;border:1px solid var(--line);overflow:auto}.svgview img{width:100%}
model-viewer{width:100%;height:520px;background:#e9e9e4;border-radius:6px}kicanvas-embed{display:block;height:600px}
.card{display:block;text-decoration:none;color:inherit}.card img{aspect-ratio:4/3;object-fit:cover}
"""


def _page(title: str, meta: str, body: str, scripts: str = "") -> str:
    return (
        f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport "
        f"content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
        f"<style>{CSS}</style>{scripts}</head><body><header><h1>{html.escape(title)}</h1>"
        f"<span class=meta>{meta}</span></header><main>{body}</main></body></html>"
    )


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _meta() -> str:
    sha = os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD")
    ref = os.environ.get("GITHUB_REF_NAME") or _git("rev-parse", "--abbrev-ref", "HEAD")
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    repo = os.environ.get("GITHUB_REPOSITORY", "Team-Micras/MicrasPCB")
    commit = f"<a href='https://github.com/{repo}/commit/{sha}'>{sha[:8]}</a>" if sha else "uncommitted"
    return f"{html.escape(ref or 'local')} · {commit} · built {when}"


def _badges(checks: dict) -> str:
    if not checks:
        return "<span class=muted>no check results in this build</span>"
    return (
        "<div class=badges>"
        + "".join(
            f"<span class='badge {'ok' if c['ok'] else 'bad'}' title='{html.escape(c['summary'])}'>"
            f"{'✓' if c['ok'] else '✗'} {html.escape(name)}: {html.escape(c['summary'])}</span>"
            for name, c in checks.items()
        )
        + "</div>"
    )


def _bom_table(board: str) -> str:
    path = build_dir(board) / "fab" / f"{board}-bom-jlcpcb.csv"
    if not path.exists():
        return "<p class=muted>run <code>micras-pcb fab</code> to include the BOM</p>"
    db = {e["lcsc"]: (m, e) for m, e in parts_db().items()}
    rows = []
    with path.open() as f:
        for r in csv.DictReader(f):
            lcsc = r["LCSC Part #"]
            _, e = db.get(lcsc, (None, {}))
            rows.append(
                f"<tr><td>{html.escape(r['Designator'])}</td><td>{html.escape(r['Comment'])}</td>"
                f"<td>{html.escape(r['MPN'])}</td><td>{html.escape(r['Footprint'])}</td>"
                f"<td><a href='https://jlcpcb.com/partdetail/{lcsc}'>{lcsc}</a></td>"
                f"<td>{html.escape(e.get('type', '?'))}</td>"
                f"<td>{'✓' if e.get('rotation_verified') else '<span class=muted>not yet</span>'}</td></tr>"
            )
    return (
        "<table><tr><th>Ref</th><th>Value</th><th>MPN</th><th>Footprint</th><th>LCSC</th><th>JLC library</th>"
        "<th>Rotation checked</th></tr>" + "".join(rows) + "</table>"
    )


def _spec_table(board: str) -> str:
    path = ROOT / "spec" / f"{board}.toml"
    if not path.exists():
        return "<p class=muted>no mechanical spec</p>"
    raw = tomllib.loads(path.read_text())
    rows = "".join(
        f"<tr><td>{html.escape(sec)}.{html.escape(k)}</td><td>{html.escape(str(v['value']))}</td>"
        f"<td class=muted>{html.escape(v['source'])}</td></tr>"
        for sec, vals in raw.items()
        for k, v in vals.items()
    )
    return f"<table><tr><th>Value</th><th></th><th>Source</th></tr>{rows}</table>"


def _board_page(board: str) -> str:
    out = SITE / board
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for src in [
        *(build_dir(board) / "review").glob("*"),
        *(build_dir(board) / "fab").glob("*.csv"),
        *(build_dir(board) / "fab").glob("*.zip"),
        build_dir(board) / f"{board}_mech.json",
        board_sch(board),
        board_pcb(board),
    ]:
        if src.is_file():
            shutil.copy2(src, out / src.name)
            files.append(src.name)

    def has(name):
        return name in files

    renders = "".join(
        f"<figure><img src='{board}-{v}.png' alt='{v}'><figcaption class=muted>{v}</figcaption></figure>"
        for v in ("top", "bottom", "iso")
        if has(f"{board}-{v}.png")
    )
    layers = "".join(
        f"<figure><div class=svgview><img src='{board}-{v}.svg' alt='{v} layers'></div>"
        f"<figcaption class=muted>{v} copper, mask, silk</figcaption></figure>"
        for v in ("top", "bottom")
        if has(f"{board}-{v}.svg")
    )
    downloads = "".join(f"<li><a href='{html.escape(f)}' download>{html.escape(f)}</a></li>" for f in sorted(files))
    s = spec.load(board) if (ROOT / "spec" / f"{board}.toml").exists() else {}
    size = (
        (
            f"{s['outline']['width']} x {s['outline']['top'] + s['tab']['depth']:.2f} mm, "
            f"{s['pcb']['copper_layers']} layers, {s['pcb']['thickness']} mm"
        )
        if s
        else ""
    )
    body = f"""
<nav class=tabs><a href='../index.html'>← all boards</a><a href='#checks'>Checks</a><a href='#schematic'>Schematic</a>
<a href='#layout'>Layout</a><a href='#3d'>3D</a><a href='#bom'>BOM</a><a href='#mech'>Mechanical</a><a href='#files'>Files</a></nav>
<section id=checks><h2>Checks</h2>{_badges(status.load(board))}<p class=muted>{html.escape(size)}</p></section>
<section id=renders><h2>Renders</h2><div class=grid>{renders}</div></section>
<section id=schematic><h2>Schematic</h2>
{f"<div class=svgview><img src='{board}-schematic.svg' alt=schematic></div>" if has(f"{board}-schematic.svg") else ""}
<details><summary>Interactive (KiCanvas)</summary><kicanvas-embed src='{board}.kicad_sch' controls=full></kicanvas-embed></details></section>
<section id=layout><h2>Layout</h2><div class=grid>{layers}</div>
<details><summary>Interactive (KiCanvas)</summary><kicanvas-embed src='{board}.kicad_pcb' controls=full></kicanvas-embed></details></section>
<section id=3d><h2>3D</h2>{f"<model-viewer src='{board}.glb' camera-controls auto-rotate shadow-intensity=1 alt='{board} 3D'></model-viewer>" if has(f"{board}.glb") else "<p class=muted>no GLB in this build</p>"}</section>
<section id=bom><h2>BOM (JLCPCB)</h2>{_bom_table(board)}</section>
<section id=mech><h2>Mechanical spec</h2>{_spec_table(board)}</section>
<section id=files><h2>Files</h2><ul>{downloads}</ul></section>"""
    scripts = f"<script type=module src='{KICANVAS}'></script><script type=module src='{MODEL_VIEWER}'></script>"
    (out / "index.html").write_text(_page(f"MicrasPCB · {board}", _meta(), body, scripts))
    return board


def run() -> int:
    shutil.rmtree(SITE, ignore_errors=True)
    SITE.mkdir(parents=True)
    cards = []
    for b in boards():
        _board_page(b)
        img = f"{b}/{b}-iso.png" if (SITE / b / f"{b}-iso.png").exists() else ""
        cards.append(
            f"<a class=card href='{b}/index.html'><section><h2>{html.escape(b)}</h2>"
            f"{f'<img src={img!r} alt={b!r}>' if img else ''}{_badges(status.load(b))}</section></a>"
        )
    body = f"<div class=grid>{''.join(cards)}</div>"
    (SITE / "index.html").write_text(_page("MicrasPCB", _meta(), body))
    (SITE / "manifest.json").write_text(json.dumps({"boards": boards()}, indent=1))
    print(f"  {SITE.relative_to(ROOT)}/index.html")
    return 0
