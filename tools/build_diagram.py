#!/usr/bin/env python3
"""Render a user-journey / process flow as a PNG in INT's proposal style, from a plain step list (no Graphviz needed).

Usage:
    python build_diagram.py steps.txt -o journey.png [--title "Approval journey"] [--direction down|right]
Prints one JSON object: nodes, edges, width, height and `table` (the same flow as a markdown step table).

Step list: one step per line, fields separated by `|`:

    id | Title | Description | next
    S1 | Reward SPOC | Records vested and unvested grant decisions | S2
    S2 | Compliance SPOC | Reviews the submitted decision | S3:Approved, S4:Returned
    S3 | Approved | Record the decision and update status |
    S4 | Returned | Return to the Reward SPOC with comments | S1

`id` is letters, digits or underscore. `Description` and `next` are optional. `next` is a comma-separated list of ids, each with an
optional `:label` for the arrow. Lines starting with `#` are ignored. A step that points back to an earlier step is drawn as a loop
on the side. At most 24 steps. Every step is numbered in the order listed; the numbers match the step table.
"""
import argparse
import json
import re
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required: pip install pillow")

NAVY = (0x1F, 0x38, 0x64)
INK = (0x26, 0x2B, 0x33)
MUTED = (0x59, 0x63, 0x70)
LINE = (0x6B, 0x77, 0x88)
NODE_FILL = (0xF4, 0xF6, 0xFA)
DECISION_FILL = (0xE3, 0xEB, 0xF8)
END_FILL = (0xE8, 0xF2, 0xE9)
END_LINE = (0x3C, 0x7A, 0x4B)
WHITE = (255, 255, 255)

MAX_NODES = 24
NODE_W = 300
PAD = 16
GAP_ALONG = 70          # space between layers (arrows and labels live here)
GAP_CROSS = 44
MARGIN = 36
SS = 2                  # supersampling factor for smooth lines


class FlowError(ValueError):
    pass


# ------------------------------------------------------------------ parsing
def parse_steps(text):
    nodes, order = {}, []
    for ln, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 2:
            raise FlowError(f"line {ln}: expected `id | Title | Description | next`, found {line[:60]!r}")
        nid, title = parts[0], parts[1]
        desc = parts[2] if len(parts) > 2 else ""
        nxt = parts[3] if len(parts) > 3 else ""
        if len(parts) > 4:
            raise FlowError(f"line {ln}: more than 4 fields; a `|` inside the text is not allowed")
        if not re.fullmatch(r"\w+", nid):
            raise FlowError(f"line {ln}: id {nid!r} must be letters, digits or underscore")
        if nid in nodes:
            raise FlowError(f"line {ln}: duplicate id {nid!r}")
        if not title:
            raise FlowError(f"line {ln}: step {nid} has no title")
        if len(title) > 80 or len(desc) > 160:
            raise FlowError(f"line {ln}: title is limited to 80 characters and description to 160")
        edges = []
        for item in [x for x in nxt.split(",") if x.strip()]:
            tgt, _, label = item.strip().partition(":")
            edges.append((tgt.strip(), label.strip()))
        nodes[nid] = {"id": nid, "title": title, "desc": desc, "out": edges, "n": len(order) + 1}
        order.append(nid)
    if len(order) < 2:
        raise FlowError("a flow needs at least 2 steps")
    if len(order) > MAX_NODES:
        raise FlowError(f"{len(order)} steps; the limit is {MAX_NODES}. Split it into two diagrams")
    for n in nodes.values():
        for tgt, _ in n["out"]:
            if tgt not in nodes:
                raise FlowError(f"step {n['id']} points to unknown step {tgt!r}")
            if tgt == n["id"]:
                raise FlowError(f"step {n['id']} points to itself")
    return nodes, order


def steps_table(nodes, order):
    """Markdown table for the proposal text: the flow as words, next to the picture."""
    rows = ["| Step | Actor / stage | Action | Next |", "|---|---|---|---|"]
    for nid in order:
        n = nodes[nid]
        nxt = ", ".join(f"{nodes[t]['n']}" + (f" ({lab})" if lab else "") for t, lab in n["out"]) or "End"
        esc = lambda s: s.replace("|", "\\|")  # noqa: E731
        rows.append(f"| {n['n']} | {esc(n['title'])} | {esc(n['desc']) or '—'} | {nxt} |")
    return "\n".join(rows)


# ------------------------------------------------------------------ layout
def _layers(nodes, order):
    """Layer per node by longest path, with edges that close a loop (back edges) set aside."""
    state, back = {}, set()

    def dfs(u):
        state[u] = 1
        for t, _ in nodes[u]["out"]:
            if state.get(t) == 1:
                back.add((u, t))
            elif t not in state:
                dfs(t)
        state[u] = 2

    incoming = {t for n in nodes.values() for t, _ in n["out"]}
    sys.setrecursionlimit(5000)
    for nid in [n for n in order if n not in incoming] + order:
        if nid not in state:
            dfs(nid)
    layer = {n: 0 for n in order}
    for _ in range(len(order)):                          # relax until stable (DAG after removing back edges)
        moved = False
        for u in order:
            for t, _ in nodes[u]["out"]:
                if (u, t) not in back and layer[t] < layer[u] + 1:
                    layer[t], moved = layer[u] + 1, True
        if not moved:
            break
    return layer, back


def _wrap(font, text, width):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if font.getlength(trial) <= width or not cur:
            cur = trial
            while font.getlength(cur) > width and len(cur) > 1:          # a single very long word
                k = len(cur)
                while k > 1 and font.getlength(cur[:k]) > width:
                    k -= 1
                lines.append(cur[:k])
                cur = cur[k:]
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def render(nodes, order, title="", direction="down"):
    if direction not in ("down", "right"):
        raise FlowError("direction must be `down` or `right`")
    f_title = ImageFont.load_default(size=22)
    f_desc = ImageFont.load_default(size=18)
    inner = NODE_W - 2 * PAD - 8

    layer, back = _layers(nodes, order)
    # node boxes: size from wrapped text
    for n in nodes.values():
        n["tl"] = _wrap(f_title, n["title"], inner)
        n["dl"] = _wrap(f_desc, n["desc"], inner) if n["desc"] else []
        h = PAD + len(n["tl"]) * 28 + (6 + len(n["dl"]) * 24 if n["dl"] else 0) + PAD
        n["w"], n["h"] = NODE_W, max(h, 70)
        n["in"] = sum(1 for m in nodes.values() for t, _ in m["out"] if t == n["id"])
        n["end"] = not n["out"]
        n["decision"] = len(n["out"]) >= 2

    # order within layers: list order, then two barycenter passes on parents
    nlayers = max(layer.values()) + 1
    rows = [[n for n in order if layer[n] == k] for k in range(nlayers)]
    pos = {n: i for r in rows for i, n in enumerate(r)}
    for _ in range(2):
        for k in range(1, nlayers):
            def bary(nid, k=k):
                ps = [pos[u] for u in order if layer[u] < k and any(t == nid and (u, t) not in back for t, _ in nodes[u]["out"])]
                return sum(ps) / len(ps) if ps else pos[nid]
            rows[k].sort(key=bary)
            for i, nid in enumerate(rows[k]):
                pos[nid] = i

    down = direction == "down"
    along = (lambda n: n["h"]) if down else (lambda n: n["w"])         # size along the flow
    cross = (lambda n: n["w"]) if down else (lambda n: n["h"])         # size across the flow
    ext = [max(along(nodes[n]) for n in r) for r in rows]
    tot = [sum(cross(nodes[n]) for n in r) + GAP_CROSS * (len(r) - 1) for r in rows]
    cross_size = max(tot)
    gap_a = GAP_ALONG if down else GAP_ALONG + 40
    a0 = [0] * nlayers
    for k in range(1, nlayers):
        a0[k] = a0[k - 1] + ext[k - 1] + gap_a
    along_size = a0[-1] + ext[-1]
    for k, r in enumerate(rows):
        c = (cross_size - tot[k]) / 2
        for nid in r:
            n = nodes[nid]
            n["a"] = a0[k] + (ext[k] - along(n)) / 2            # start along the flow
            n["c"] = c                                          # start across the flow
            c += cross(n) + GAP_CROSS

    # edges: neighbours in the next layer are drawn straight/elbow; loops and layer-skipping edges use a side channel
    side = [(u, t, lab) for u in order for t, lab in nodes[u]["out"] if (u, t) in back or layer[t] - layer[u] != 1]
    chan0 = cross_size + 34
    head = 60 if title else 0
    pre = gap_a / 2 if any(layer[t] == 0 for _, t, _ in side) else 0         # room above the first row for a loop back to it
    cs = cross_size + (34 + 26 * len(side) + 20 if side else 0)
    if down:
        ox, oy = MARGIN, MARGIN + head + pre
        W, H = int(cs + 2 * MARGIN), int(along_size + pre + 2 * MARGIN + head)
    else:
        ox, oy = MARGIN + pre, MARGIN + head
        W, H = int(along_size + pre + 2 * MARGIN), int(cs + 2 * MARGIN + head)
    W, H = max(W, 420), max(H, 160)

    img = Image.new("RGB", (W * SS, H * SS), WHITE)
    d = ImageDraw.Draw(img)

    def XY(a, c):                                               # (along, cross) -> pixel point
        return ((ox + c) * SS, (oy + a) * SS) if down else ((ox + a) * SS, (oy + c) * SS)

    def poly(points, width=2):
        d.line([XY(*p) for p in points], fill=LINE, width=width * SS, joint="curve")

    def arrow(p_from, p_to):
        (x0, y0), (x1, y1) = XY(*p_from), XY(*p_to)
        dx, dy = x1 - x0, y1 - y0
        ln = max((dx * dx + dy * dy) ** 0.5, 1)
        ux, uy = dx / ln, dy / ln
        s = 11 * SS
        d.polygon([(x1, y1), (x1 - ux * s - uy * s * 0.55, y1 - uy * s + ux * s * 0.55),
                   (x1 - ux * s + uy * s * 0.55, y1 - uy * s - ux * s * 0.55)], fill=LINE)

    def label(a, c, text):
        if not text:
            return
        x, y = XY(a, c)
        fnt = ImageFont.load_default(size=16 * SS)
        w = fnt.getlength(text)
        d.rounded_rectangle([x - w / 2 - 6 * SS, y - 12 * SS, x + w / 2 + 6 * SS, y + 12 * SS], radius=6 * SS, fill=WHITE, outline=(0xC9, 0xD1, 0xDD), width=SS)
        d.text((x - w / 2, y - 10 * SS), text, font=fnt, fill=MUTED)

    def ends(n):                                                # (along start, along end, cross centre, cross end)
        return n["a"], n["a"] + along(n), n["c"] + cross(n) / 2, n["c"] + cross(n)

    n_out, n_in = {}, {}
    for u in order:                                             # lines first, boxes on top
        nu = nodes[u]
        for t, lab in nu["out"]:
            nt = nodes[t]
            if (u, t) in back or layer[t] - layer[u] != 1:
                idx = side.index((u, t, lab))
                ch = chan0 + 26 * idx
                i_o, i_i = n_out.get(u, 0), n_in.get(t, 0)
                n_out[u], n_in[t] = i_o + 1, i_i + 1
                sc_ = ends(nu)[2] + 26 + 12 * i_o
                tc_ = ends(nt)[2] + 26 + 12 * i_i
                g_s = a0[layer[u]] + ext[layer[u]] + gap_a / 2      # free gap below the source row
                g_t = a0[layer[t]] - gap_a / 2                      # free gap above the target row
                pts = [(ends(nu)[1], sc_), (g_s, sc_), (g_s, ch), (g_t, ch), (g_t, tc_), (nt["a"] - 2, tc_)]
                poly(pts)
                arrow((nt["a"] - 16, tc_), (nt["a"], tc_))
                label((g_s + g_t) / 2, ch, lab)
            else:
                s0, s1, sc, _ = ends(nu)
                t0, _, tc, _ = ends(nt)
                mid = (s1 + t0) / 2
                if abs(sc - tc) < 1:
                    poly([(s1, sc), (t0 - 2, tc)])
                else:
                    poly([(s1, sc), (mid, sc), (mid, tc), (t0 - 2, tc)])
                arrow((t0 - 14, tc), (t0, tc))
                label(mid, (sc + tc) / 2, lab)

    for nid in order:
        n = nodes[nid]
        a0_, a1_, cc, ce = ends(n)
        x0, y0 = XY(a0_, n["c"])
        x1, y1 = XY(a1_, ce)
        if n["in"] == 0:
            fill, outline, ink, sub = NAVY, NAVY, WHITE, (0xDC, 0xE4, 0xF2)
        elif n["end"]:
            fill, outline, ink, sub = END_FILL, END_LINE, INK, MUTED
        elif n["decision"]:
            fill, outline, ink, sub = DECISION_FILL, NAVY, INK, MUTED
        else:
            fill, outline, ink, sub = NODE_FILL, NAVY, INK, MUTED
        d.rounded_rectangle([x0, y0, x1, y1], radius=12 * SS, fill=fill, outline=outline, width=2 * SS)
        ft, fd = ImageFont.load_default(size=22 * SS), ImageFont.load_default(size=18 * SS)
        ty = y0 + PAD * SS
        left = x0 + (PAD + 8) * SS
        for ln in n["tl"]:
            d.text((left, ty), ln, font=ft, fill=ink, stroke_width=1, stroke_fill=ink)
            ty += 28 * SS
        if n["dl"]:
            ty += 6 * SS
            for ln in n["dl"]:
                d.text((left, ty), ln, font=fd, fill=sub)
                ty += 24 * SS
        r = 13 * SS                                              # step number badge on the top-left corner
        bx, by = x0 + 4 * SS, y0 + 4 * SS
        bfill, btxt = (WHITE, NAVY) if n["in"] == 0 else (NAVY, WHITE)
        d.ellipse([bx - r + 8 * SS, by - r + 8 * SS, bx + r + 8 * SS, by + r + 8 * SS], fill=bfill, outline=NAVY, width=SS)
        fnum = ImageFont.load_default(size=15 * SS)
        s = str(n["n"])
        d.text((bx + 8 * SS - fnum.getlength(s) / 2, by + 8 * SS - 9 * SS), s, font=fnum, fill=btxt)

    if title:
        fh = ImageFont.load_default(size=28 * SS)
        w = fh.getlength(title)
        d.text(((W * SS - w) / 2, (MARGIN - 8) * SS), title, font=fh, fill=NAVY, stroke_width=1, stroke_fill=NAVY)

    return img.resize((W, H), Image.LANCZOS)


def build(text, title="", direction="down"):
    nodes, order = parse_steps(text)
    img = render(nodes, order, title, direction)
    edges = sum(len(n["out"]) for n in nodes.values())
    return img, {"nodes": len(order), "edges": edges, "width": img.width, "height": img.height, "table": steps_table(nodes, order)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("steps", help="text file with the step list")
    ap.add_argument("-o", "--out", required=True, help="PNG file to write")
    ap.add_argument("--title", default="")
    ap.add_argument("--direction", default="down", choices=["down", "right"])
    a = ap.parse_args()
    with open(a.steps, encoding="utf-8") as f:
        text = f.read()
    try:
        img, info = build(text, a.title, a.direction)
    except FlowError as e:
        sys.exit(f"invalid flow: {e}")
    img.save(a.out, "PNG", optimize=True)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
