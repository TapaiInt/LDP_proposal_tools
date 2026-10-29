#!/usr/bin/env python3
"""Render proposal diagrams (architecture, user journey, Mermaid) as PNG through a headless browser (Playwright + Chromium).

Usage:
    python render_diagram.py --kind architecture spec.json -o arch.png [--title ".."] [--subtitle ".."]
    python render_diagram.py --kind journey      steps.txt -o journey.png [--title ".."] [--subtitle ".."]
    python render_diagram.py --kind mermaid      source.mmd -o flow.png  [--title ".."] [--subtitle ".."]
Prints one JSON object (kind, width, height; for a journey also nodes, edges, lanes, table, warnings).
Exit codes: 0 ok, 2 invalid diagram input (message on stderr), 3 renderer unavailable (Playwright or Chromium missing / failed).

architecture: JSON, every text field plain text (it is escaped; no HTML):
    {"layers": [{"name": "Users & channels", "items": [{"name": "Employee portal", "detail": "Responsive web", "tag": "INT Recommended"}]}],
     "integrations": [{"name": "SAP SuccessFactors", "detail": "Employee master", "tag": "Existing"}],
     "integration_note": "REST through the API gateway"}
    2-8 layers listed top (users) to bottom (platform); 1-8 items per layer; up to 10 integrations.
    tag: Client-Mandated | Existing | INT Recommended | To Be Confirmed (or TBC) | empty.
journey: the build_diagram.py step list (`id | Role | Action | next`, next = ids with an optional `:label`). Each distinct
    Role becomes a vertical swimlane (at most 6); a step with two or more exits gets a decision gateway; a step that points
    back to an earlier one is drawn as a dashed rework loop on the right. Returns the same markdown step table as build_diagram.
mermaid: Mermaid source (flowchart, sequenceDiagram, gantt, stateDiagram ...), rendered with the bundled Mermaid library
    (tools/vendor/mermaid.min.js) at securityLevel strict.

Set RENDER_DIAGRAM_DISABLE=1 to switch the browser off (exit 3; the tool layer then falls back for journeys).
Security: the page has no network (every request is aborted), JavaScript is off for the two templates, and all text is escaped.
"""
import argparse
import html
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_diagram import FlowError, _layers, parse_steps, steps_table  # noqa: E402

MERMAID_JS = os.path.join(HERE, "vendor", "mermaid.min.js")
SCALE = 2                     # device pixels per CSS pixel: sharp when Word prints the picture at 16 cm
NAVY, INK, MUTED, LINE = "#1F3864", "#262B33", "#596370", "#6B7788"
FONT = '"Segoe UI", "Liberation Sans", "DejaVu Sans", Arial, sans-serif'
TAGS = {"client-mandated": ("Client-Mandated", "cm"), "existing": ("Existing", "ex"), "int recommended": ("INT Recommended", "ir"),
        "to be confirmed": ("To Be Confirmed", "tbc"), "tbc": ("To Be Confirmed", "tbc")}


class RendererUnavailable(RuntimeError):
    pass


def esc(s):
    return html.escape(str(s or ""), quote=True)


BASE_CSS = f"""
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: #fff; }}
body {{ font-family: {FONT}; color: {INK}; }}
#wrap {{ display: inline-block; padding: 22px 26px 24px; background: #fff; }}
h1 {{ font-size: 21px; color: {NAVY}; margin: 0 0 3px; font-weight: 700; }}
p.sub {{ margin: 0 0 14px; color: {MUTED}; font-size: 13px; }}
"""


def page(body, extra_css="", title="", subtitle=""):
    head = (f"<h1>{esc(title)}</h1>" if title else "") + (f'<p class="sub">{esc(subtitle)}</p>' if subtitle else "")
    if title and not subtitle:
        head += '<div style="height:10px"></div>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}{extra_css}</style></head>'
            f'<body><div id="wrap">{head}{body}</div></body></html>')


# ------------------------------------------------------------------ architecture
ARCH_CSS = f"""
.grid {{ display: grid; grid-template-columns: 1fr 230px; gap: 14px; width: 1000px; }}
.grid.solo {{ grid-template-columns: 1fr; width: 860px; }}
.layer {{ display: grid; grid-template-columns: 142px 1fr; border: 1px solid #C9D1DD; border-radius: 10px; overflow: hidden; }}
.layer > .name {{ background: {NAVY}; color: #fff; font-weight: 600; font-size: 14px; padding: 12px; display: flex; align-items: center; }}
.layer > .items {{ display: flex; flex-wrap: wrap; gap: 8px; padding: 10px; background: #F4F6FA; }}
.box {{ background: #fff; border: 1px solid {NAVY}; border-radius: 8px; padding: 7px 10px; font-size: 13px; min-width: 128px; max-width: 250px; }}
.box b {{ display: block; font-size: 14px; }}
.box span.d {{ display: block; color: {MUTED}; font-size: 12px; margin-top: 1px; }}
.tag {{ display: inline-block; font-size: 10.5px; font-weight: 600; border-radius: 4px; padding: 1px 6px; margin-top: 4px; }}
.cm {{ background: #FDECEA; color: #9B2C2C; }} .ex {{ background: #E8F2E9; color: #3C7A4B; }}
.ir {{ background: #E3EBF8; color: {NAVY}; }} .tbc {{ background: #FFF4DB; color: #8A5A00; }}
.flow {{ display: flex; justify-content: center; height: 16px; align-items: center; }}
.flow i {{ width: 0; height: 0; border-left: 7px solid transparent; border-right: 7px solid transparent; border-top: 9px solid {LINE}; margin: 0 3px; }}
.flow i.up {{ border-top: 0; border-bottom: 9px solid {LINE}; }}
.side {{ border: 1px dashed {NAVY}; border-radius: 10px; padding: 10px; background: #FAFBFD; align-self: start; }}
.side h3 {{ margin: 0 0 8px; font-size: 14px; color: {NAVY}; }}
.side .box {{ margin-bottom: 8px; max-width: none; border-color: #3C7A4B; }}
.note {{ font-size: 12px; color: {MUTED}; }}
.legend {{ margin-top: 10px; font-size: 11.5px; color: {MUTED}; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
.legend .tag {{ margin: 0; }}
"""


def _text(v, field, limit, where):
    if v is None:
        return ""
    if not isinstance(v, (str, int, float)):
        raise FlowError(f"{where}: `{field}` must be text")
    s = str(v).strip()
    if len(s) > limit:
        raise FlowError(f"{where}: `{field}` is limited to {limit} characters")
    return s


def _item(it, where):
    if isinstance(it, str):
        it = {"name": it}
    if not isinstance(it, dict):
        raise FlowError(f"{where}: an item must be an object with name, detail, tag")
    name = _text(it.get("name"), "name", 60, where)
    if not name:
        raise FlowError(f"{where}: item without a name")
    tag = _text(it.get("tag"), "tag", 30, where)
    if tag and tag.lower() not in TAGS:
        raise FlowError(f"{where}: tag {tag!r} must be one of Client-Mandated, Existing, INT Recommended, To Be Confirmed")
    return name, _text(it.get("detail"), "detail", 90, where), TAGS.get(tag.lower()) if tag else None


def _box(name, detail, tag):
    t = f'<span class="tag {tag[1]}">{esc(tag[0])}</span>' if tag else ""
    d = f'<span class="d">{esc(detail)}</span>' if detail else ""
    return f'<div class="box"><b>{esc(name)}</b>{d}{t}</div>'


def architecture_html(spec, title="", subtitle=""):
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except ValueError as e:
            raise FlowError(f"architecture spec is not valid JSON: {e}")
    if not isinstance(spec, dict):
        raise FlowError("architecture spec must be a JSON object with `layers` (and optional `integrations`)")
    layers = spec.get("layers")
    if not isinstance(layers, list) or not 2 <= len(layers) <= 8:
        raise FlowError("`layers` must be a list of 2 to 8 layers, top (users) to bottom (platform)")
    used = set()
    rows = []
    for i, lay in enumerate(layers, 1):
        if not isinstance(lay, dict):
            raise FlowError(f"layer {i} must be an object with name and items")
        lname = _text(lay.get("name"), "name", 40, f"layer {i}")
        items = lay.get("items")
        if not lname or not isinstance(items, list) or not 1 <= len(items) <= 8:
            raise FlowError(f"layer {i}: needs a name and 1 to 8 items")
        boxes = []
        for j, it in enumerate(items, 1):
            n, d, t = _item(it, f"layer {i} item {j}")
            if t:
                used.add(t)
            boxes.append(_box(n, d, t))
        if rows:
            rows.append('<div class="flow"><i></i><i class="up"></i></div>')
        rows.append(f'<div class="layer"><div class="name">{esc(lname)}</div><div class="items">{"".join(boxes)}</div></div>')
    integ = spec.get("integrations") or []
    if not isinstance(integ, list) or len(integ) > 10:
        raise FlowError("`integrations` must be a list of at most 10 items")
    side = ""
    if integ:
        boxes = []
        for j, it in enumerate(integ, 1):
            n, d, t = _item(it, f"integration {j}")
            if t:
                used.add(t)
            boxes.append(_box(n, d, t))
        note = _text(spec.get("integration_note"), "integration_note", 200, "integrations")
        side = (f'<div class="side"><h3>{esc(spec.get("integrations_title") or "Integrations")}</h3>{"".join(boxes)}'
                + (f'<div class="note">{esc(note)}</div>' if note else "") + "</div>")
    legend = ""
    if used:
        legend = '<div class="legend">' + "".join(f'<span class="tag {c}">{esc(n)}</span>' for n, c in sorted(used)) + "</div>"
    body = f'<div class="grid{"" if side else " solo"}"><div>{"".join(rows)}{legend}</div>{side}</div>'
    return page(body, ARCH_CSS, title, subtitle)


# ------------------------------------------------------------------ journey (vertical swimlanes)
FS, LH, BPAD = 14, 19, 12      # node font size, line height, inner padding
HEAD_H, GAP, GW = 40, 62, 11   # lane header height, gap between rows, gateway half-size


def _wrap(text, chars):
    lines, cur = [], ""
    for w in text.split():
        while len(w) > chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:chars])
            w = w[chars:]
        t = (cur + " " + w).strip()
        if len(t) <= chars:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def journey_svg(text):
    nodes, order = parse_steps(text)
    preds = {nid: [u for u in order if any(t == nid for t, _ in nodes[u]["out"])] for nid in order}
    titles = [nodes[n]["title"] for n in order]
    # an end step with a title of its own ("Closed", "Approved") is an outcome, not a role: it sits in its predecessor's lane
    outcome = {nid for nid in order if not nodes[nid]["out"] and preds[nid] and titles.count(nodes[nid]["title"]) == 1}
    lanes = []
    for nid in order:
        if nid not in outcome and nodes[nid]["title"] not in lanes:
            lanes.append(nodes[nid]["title"])
    lane_of = {}
    for nid in order:
        lane_of[nid] = lanes.index(nodes[nid]["title"]) if nid not in outcome else None
    for nid in order:
        if lane_of[nid] is None:
            lane_of[nid] = next((lane_of[u] for u in preds[nid] if lane_of[u] is not None), 0)
    if len(lanes) > 6:
        raise FlowError(f"{len(lanes)} roles; a journey swimlane holds at most 6. Merge roles or split the journey")
    layer, back = _layers(nodes, order)
    # row per step: after every non-loop predecessor, and never two steps in the same lane cell
    row, taken = {}, set()
    for nid in sorted(order, key=lambda n: (layer[n], order.index(n))):
        r = max([row[u] + 1 for u in preds[nid] if (u, nid) not in back and u in row], default=0)
        lane = lane_of[nid]
        while (lane, r) in taken:
            r += 1
        row[nid] = r
        taken.add((lane, r))
    nrows = max(row.values()) + 1
    lane_w = 214 if len(lanes) <= 4 else 186
    box_w = lane_w - 30
    chars = max(12, int((box_w - 2 * BPAD - 6) / (0.5 * FS)))
    for n in nodes.values():
        n["lines"] = _wrap(n["desc"] or n["title"], chars)
        n["h"] = max(58, 2 * BPAD + 6 + len(n["lines"]) * LH)
        n["lane"] = lane_of[n["id"]]
        n["dec"] = len(n["out"]) >= 2
        n["start"] = not any(t == n["id"] for m in nodes.values() for t, _ in m["out"])
    row_h = [max([nodes[n]["h"] for n in order if row[n] == r], default=58) for r in range(nrows)]
    ry = [HEAD_H + 18]
    for r in range(1, nrows):
        ry.append(ry[-1] + row_h[r - 1] + GAP)
    lanes_h = ry[-1] + row_h[-1] + 22
    loops = [(u, t, lab) for u in order for t, lab in nodes[u]["out"] if row[t] <= row[u]]
    # a rework loop runs in the side channel nearer to its two lanes
    left = [lp for lp in loops if nodes[lp[0]]["lane"] + nodes[lp[1]]["lane"] < len(lanes) - 1]
    right = [lp for lp in loops if lp not in left]
    OX = (40 + 16 * len(left)) if left else 0          # room on the left for loop channels and their labels
    W = OX + len(lanes) * lane_w + ((40 + 16 * len(right)) if right else 0) + 2
    H = lanes_h + 2

    def box(nid):
        n = nodes[nid]
        x = OX + n["lane"] * lane_w + (lane_w - box_w) / 2
        y = ry[row[nid]] + (row_h[row[nid]] - n["h"]) / 2
        return x, y, box_w, n["h"]

    def out_pt(nid):
        x, y, w, h = box(nid)
        return x + w / 2, y + h + (2 * GW + 2 if nodes[nid]["dec"] else 0)

    def in_pt(nid):
        x, y, w, h = box(nid)
        return x + w / 2, y

    def gap_y(r):                       # middle of the gap below row r
        return ry[r] + row_h[r] + GAP / 2

    slots = {}

    def slot_y(r):
        k = slots.get(r, 0)
        slots[r] = k + 1
        return gap_y(r) + (k % 3 - 1) * 9

    svg, labels = [], []
    for k, ln in enumerate(lanes):
        x = OX + k * lane_w
        svg.append(f'<rect x="{x + 1}" y="1" width="{lane_w - 2}" height="{lanes_h - 2}" rx="8" fill="{"#F7F9FC" if k % 2 == 0 else "#FFFFFF"}" stroke="#C9D1DD"/>')
        svg.append(f'<rect x="{x + 1}" y="1" width="{lane_w - 2}" height="{HEAD_H}" rx="8" fill="{NAVY}"/>'
                   f'<rect x="{x + 1}" y="{HEAD_H - 8}" width="{lane_w - 2}" height="9" fill="{NAVY}"/>')
        svg.append(f'<foreignObject x="{x + 6}" y="1" width="{lane_w - 12}" height="{HEAD_H}"><div xmlns="http://www.w3.org/1999/xhtml" class="lh">{esc(ln)}</div></foreignObject>')

    def path(pts, dashed=False):
        d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        svg.append(f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="1.6" stroke-linejoin="round"'
                   + (' stroke-dasharray="5 4"' if dashed else "") + ' marker-end="url(#ah)"/>')

    def label(x, y, text):
        if text:
            w = len(text) * 6.6 + 14
            labels.append(f'<rect x="{x - w / 2:.1f}" y="{y - 10:.1f}" width="{w:.1f}" height="20" rx="5" fill="#fff" stroke="#C9D1DD"/>'
                          f'<text x="{x:.1f}" y="{y + 4:.1f}" class="el">{esc(text)}</text>')

    for u, t, lab in loops:                              # rework loops: dashed, in a side channel
        sx, sy = out_pt(u)
        tx, ty = in_pt(t)
        if (u, t, lab) in left:
            cx = OX - 14 - 16 * left.index((u, t, lab))
        else:
            cx = OX + len(lanes) * lane_w + 14 + 16 * right.index((u, t, lab))
        y1, y0 = slot_y(row[u]), ty - GAP / 2 + 6
        path([(sx, sy), (sx, y1), (cx, y1), (cx, y0), (tx, y0), (tx, ty - 1)], dashed=True)
        label(cx, (y1 + y0) / 2, lab)
    for u in order:                                      # forward edges
        for t, lab in nodes[u]["out"]:
            if row[t] <= row[u]:
                continue
            sx, sy = out_pt(u)
            tx, ty = in_pt(t)
            y1 = slot_y(row[u])
            if row[t] == row[u] + 1:
                pts = [(sx, sy), (sx, y1), (tx, y1), (tx, ty - 1)] if abs(sx - tx) > 1 else [(sx, sy), (tx, ty - 1)]
            else:                                        # skips rows: run down the target lane's left gutter
                gx = OX + nodes[t]["lane"] * lane_w + 8
                y2 = ty - GAP / 2
                pts = [(sx, sy), (sx, y1), (gx, y1), (gx, y2), (tx, y2), (tx, ty - 1)]
            path(pts)
            label((sx + tx) / 2 if abs(sx - tx) > 1 else sx, y1 if abs(sx - tx) > 1 else (sy + ty) / 2, lab)

    for nid in order:
        n = nodes[nid]
        x, y, w, h = box(nid)
        if n["start"]:
            fill, stroke, cls = NAVY, NAVY, "nt s"
        elif not n["out"]:
            fill, stroke, cls = "#E8F2E9", "#3C7A4B", "nt e"
        else:
            fill, stroke, cls = "#FFFFFF", NAVY, "nt"
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
        txt = "<br/>".join(esc(ln) for ln in n["lines"])
        svg.append(f'<foreignObject x="{x}" y="{y}" width="{w}" height="{h}"><div xmlns="http://www.w3.org/1999/xhtml" class="{cls}">{txt}</div></foreignObject>')
        bf, bt = ("#FFFFFF", NAVY) if n["start"] else (NAVY, "#FFFFFF")
        svg.append(f'<circle cx="{x + 2}" cy="{y + 2}" r="11" fill="{bf}" stroke="{NAVY}" stroke-width="1.2"/>'
                   f'<text x="{x + 2}" y="{y + 6.5}" class="num" fill="{bt}">{n["n"]}</text>')
        if n["dec"]:
            cx, cy = x + w / 2, y + h + GW + 1
            svg.append(f'<path d="M{cx},{cy - GW} L{cx + GW},{cy} L{cx},{cy + GW} L{cx - GW},{cy} Z" fill="#E3EBF8" stroke="{NAVY}" stroke-width="1.4"/>')
    defs = (f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>')
    out = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{defs}{"".join(svg)}{"".join(labels)}</svg>'
    info = {"nodes": len(order), "edges": sum(len(n["out"]) for n in nodes.values()), "lanes": lanes, "rows": nrows,
            "table": steps_table(nodes, order), "warnings": []}
    if nrows > 10:
        info["warnings"].append(f"{nrows} rows deep; consider splitting the journey")
    return out, info


JOURNEY_CSS = f"""
.lh {{ height: 40px; display: flex; align-items: center; justify-content: center; text-align: center; color: #fff; font-weight: 600; font-size: 13.5px; line-height: 16px; }}
.nt {{ width: 100%; height: 100%; display: flex; align-items: center; padding: {BPAD}px {BPAD}px {BPAD}px {BPAD + 6}px; font-size: {FS}px; line-height: {LH}px; color: {INK}; }}
.nt.s {{ color: #fff; font-weight: 600; }} .nt.e {{ font-weight: 600; }}
.num {{ font: 600 12px {FONT}; text-anchor: middle; }}
.el {{ font: 12px {FONT}; fill: {MUTED}; text-anchor: middle; }}
"""


def journey_html(text, title="", subtitle=""):
    svg, info = journey_svg(text)
    return page(svg, JOURNEY_CSS, title, subtitle), info


# ------------------------------------------------------------------ mermaid
MERMAID_CONFIG = {
    "startOnLoad": False, "securityLevel": "strict", "theme": "base", "fontFamily": FONT,
    "flowchart": {"useMaxWidth": False, "htmlLabels": True, "curve": "basis", "nodeSpacing": 42, "rankSpacing": 48},
    "sequence": {"useMaxWidth": False}, "gantt": {"useMaxWidth": False}, "state": {"useMaxWidth": False},
    "themeVariables": {"fontFamily": FONT, "fontSize": "15px", "primaryColor": "#F4F6FA", "primaryBorderColor": NAVY, "primaryTextColor": INK,
                       "lineColor": LINE, "secondaryColor": "#E3EBF8", "tertiaryColor": "#FAFBFD", "clusterBkg": "#FAFBFD", "clusterBorder": "#C9D1DD",
                       "edgeLabelBackground": "#FFFFFF", "actorBkg": "#F4F6FA", "actorBorder": NAVY, "noteBkgColor": "#FFF4DB"},
}


def mermaid_html(title="", subtitle=""):
    return page('<div id="mm"></div>', "#mm svg { max-width: none !important; }", title, subtitle)


# ------------------------------------------------------------------ browser
class _Lock:
    """One render at a time per container: Chromium needs ~150-250 MB, and the API runs several workers."""

    def __enter__(self):
        self.f = open(os.path.join(tempfile.gettempdir(), "render_diagram.lock"), "w")
        try:
            import fcntl
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except ImportError:  # Windows (local development): no lock
            pass
        return self

    def __exit__(self, *exc):
        self.f.close()


def screenshot(html_text, out, mermaid_src=None):
    if os.environ.get("RENDER_DIAGRAM_DISABLE", "").lower() in ("1", "true", "yes"):
        raise RendererUnavailable("disabled by RENDER_DIAGRAM_DISABLE")
    try:
        from playwright.sync_api import Error as PwError
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RendererUnavailable("Playwright is not installed (pip install playwright; python -m playwright install chromium)")
    if mermaid_src is not None and not os.path.exists(MERMAID_JS):
        raise RendererUnavailable(f"bundled Mermaid library missing: {MERMAID_JS}")
    with _Lock():
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(args=["--disable-dev-shm-usage", "--disable-gpu"])
                try:
                    ctx = browser.new_context(device_scale_factor=SCALE, viewport={"width": 1600, "height": 1000},
                                              java_script_enabled=mermaid_src is not None)
                    ctx.route("**/*", lambda route: route.abort())          # no network at all
                    pg = ctx.new_page()
                    pg.set_default_timeout(30000)
                    pg.set_content(html_text, wait_until="load")
                    if mermaid_src is not None:
                        pg.add_script_tag(path=MERMAID_JS)
                        err = pg.evaluate("""async ([src, cfg]) => {
                            try { mermaid.initialize(cfg); const r = await mermaid.render('mmd', src);
                                  document.getElementById('mm').innerHTML = r.svg; return null; }
                            catch (e) { return String((e && (e.str || e.message)) || e); } }""", [mermaid_src, MERMAID_CONFIG])
                        if err:
                            raise FlowError("Mermaid could not parse the diagram: " + err.splitlines()[0][:300]
                                            + ("; " + " ".join(err.splitlines()[1:4])[:300] if len(err.splitlines()) > 1 else ""))
                    pg.locator("#wrap").screenshot(path=out, type="png")
                finally:
                    browser.close()
        except PwError as e:
            raise RendererUnavailable(f"headless browser failed: {str(e).splitlines()[0][:300]}")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def build(kind, text, out, title="", subtitle=""):
    if kind == "architecture":
        info = {}
        screenshot(architecture_html(text, title, subtitle), out)
    elif kind == "journey":
        doc, info = journey_html(text, title, subtitle)
        screenshot(doc, out)
    elif kind == "mermaid":
        src = str(text).strip()
        if not src:
            raise FlowError("the Mermaid source is empty")
        if len(src) > 12000:
            raise FlowError("the Mermaid source is limited to 12,000 characters; split the diagram")
        info = {}
        screenshot(mermaid_html(title, subtitle), out, mermaid_src=src)
    else:
        raise FlowError("kind must be architecture, journey or mermaid")
    w, h = png_size(out)
    return dict(kind=kind, width=w, height=h, **info)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="input file: JSON (architecture), step list (journey) or Mermaid source (mermaid)")
    ap.add_argument("-o", "--out", required=True, help="PNG file to write")
    ap.add_argument("--kind", required=True, choices=["architecture", "journey", "mermaid"])
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitle", default="")
    a = ap.parse_args()
    with open(a.spec, encoding="utf-8") as f:
        text = f.read()
    try:
        info = build(a.kind, text, a.out, a.title, a.subtitle)
    except FlowError as e:
        print(f"invalid diagram: {e}", file=sys.stderr)
        sys.exit(2)
    except RendererUnavailable as e:
        print(f"renderer unavailable: {e}", file=sys.stderr)
        sys.exit(3)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
