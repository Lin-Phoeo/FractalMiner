"""Extract named constant-buffer values and texture bindings for the Tifuluosi
front-frame character draws from an already-exported RenderDoc details JSON.

Names come from the 1.5.3 decompiled HLSL dump (SPIRV-Cross output with
explicit packoffset declarations).  Captured reflection variables are
matched to HLSL members by *byte offset*, never by index, because RenderDoc
collapses arrays into a single variable.

Usage:
    python Tools/extract_front_frame_constants.py [DETAILS_DIR] [DUMP_DIR] [OUT_DIR]
or via env vars FF_DETAILS_DIR / FF_DUMP_DIR / FF_OUT_DIR.
No dependencies beyond the standard library.
"""
import collections
import json
import math
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DETAILS_DIR = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "FF_DETAILS_DIR", os.path.join(REPO, "Validation/Captures/tifuluosi-front-20260917/replay-details-01")))
DUMP_DIR = (sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
    "FF_DUMP_DIR", os.path.join(REPO, "_dump_1.5.3/AllShader_1.5.3/Assets/packages/com.hg.render-pipelines/runtime/shaders/materials/characternpr")))
OUT_DIR = (sys.argv[3] if len(sys.argv) > 3 else os.environ.get(
    "FF_OUT_DIR", os.path.join(os.path.dirname(DETAILS_DIR.rstrip("/\\")), "extracted")))

MAIN_EVENTS = collections.OrderedDict([
    (776, ("iris", "characternpr_eye")),
    # Captured t1=LUT(1024x32), t2=diffRamp(256x1), t3=normal, t4=base.
    # A same-size cloth buffer is not evidence of the same shader family.
    (786, ("body", "characternpr_skin")),
    (835, ("cloth_01", "characternpr")),
    (850, ("cloth_02", "characternpr")),
    (860, ("face", "characternpr_skin")),
    (875, ("hair", "characternpr_hair")),
])
OVERLAY_EVENTS = [892, 897, 912, 923, 982, 987]

# Manually reviewed contracts for this specific front-frame event inventory.
# They constrain semantic names, NOT filenames or keywords. b114/b208 and
# b471/b474/etc. remain alternative variants of each matching signature.
# Evidence: body t1 1024x32 BC7-sRGB LUT, t2 256x1 ramp, t3 BC5, t4 base;
# cloth01 t1 256x256 specRamp, t2 packed P, t3 256x1 ramp, t4 BC5, t5 base.
REVIEWED_SET1_TEXTURES = {
    786: {1: "_ShadowLutTex", 2: "_DiffRampMap", 3: "_BumpMap", 4: "_BaseMap"},
    835: {1: "_SpecRampMap", 2: "_MetallicGlossMap", 3: "_DiffRampMap", 4: "_BumpMap", 5: "_BaseMap"},
}

# Captured blocks are anonymous ("uniformsNN"); identify them by (set, binding).
BLOCK_BY_BINDING = {
    (0, 12): "TransformVariables",
    (0, 14): "LightDataBuffer",
    (0, 15): "ShadowData",
    (0, 16): "ShaderVariablesGlobal",
    (0, 48): "LightBinningConstants",
    (0, 50): "LightCookieCB",
    (1, 0): "UnityPerMaterial",
    (1, 2): "UnityPerMaterial",
    (2, 0): "UnityInstancing_SRP_UnityPerDraw",
}
BIG_ARRAY_LIMIT = 16  # arrays longer than this are summarised

# --------------------------------------------------------------------------- HLSL parsing
RE_CB = re.compile(r"cbuffer\s+(\w+)\s*:\s*register\(b(\d+)(?:,\s*space(\d+))?\)\s*\{(.*?)\n\};", re.S)
RE_MEM = re.compile(r"^\s*(?:(?:column_major|row_major)\s+)?(\w+)\s+(\w+)(?:\[(\d+)\])?\s*:\s*packoffset\(c(\d+)(?:\.([xyzw]))?\)", re.M)
RE_MAJOR = re.compile(r"^\s*(column_major|row_major)\s+", re.M)
RE_RES = re.compile(r"^((?:RW)?Texture\w+|SamplerState|SamplerComparisonState|(?:RW)?ByteAddressBuffer|(?:RW)?StructuredBuffer)(?:<([^>]+)>)?\s+(\w+)\s*:\s*register\(([tsbu])(\d+)(?:,\s*space(\d+))?\)", re.M)


def hlsl_type_size(t):
    m = re.match(r"^(float|int|uint|half|bool)(?:(\d)(?:x(\d))?)?$", t)
    if not m:
        return None
    rows, cols = m.group(2), m.group(3)
    if cols:
        return int(rows) * 16
    if rows:
        return int(rows) * 4
    return 4


def parse_hlsl(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    cbuffers = {}
    for m in RE_CB.finditer(text):
        name, b, sp, body = m.group(1), int(m.group(2)), int(m.group(3) or 0), m.group(4)
        short = name[len("type_"):] if name.startswith("type_") else name
        members = []
        end = 0
        for line in body.split("\n"):
            mm = RE_MEM.match(line)
            if not mm:
                continue
            t, n, cnt, c, comp = mm.groups()
            off = int(c) * 16 + ("xyzw".index(comp) * 4 if comp else 0)
            es = hlsl_type_size(t)
            cnt = int(cnt) if cnt else None
            size = None
            if es is not None:
                size = cnt * ((es + 15) // 16 * 16) if cnt else es
                end = max(end, off + size)
            major = RE_MAJOR.match(line)
            members.append(dict(type=t, name=n, count=cnt, offset=off, size=size,
                                major=major.group(1) if major else None))
        cbuffers[short] = dict(name=short, binding=b, space=sp, size=(end + 15) // 16 * 16, members=members)
    resources = []
    for m in RE_RES.finditer(text):
        kind, fmt, n, rk, rn, sp = m.groups()
        resources.append(dict(kind=kind, fmt=fmt, name=n, reg=rk, binding=int(rn), space=int(sp or 0)))
    return dict(path=path, cbuffers=cbuffers, resources=resources)


def load_dump(dump_dir):
    files = {}
    for folder in sorted(os.listdir(dump_dir)):
        d = os.path.join(dump_dir, folder)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.startswith("Sub0_Pass0_Fragment") and f.endswith(".hlsl"):
                files[(folder, f)] = parse_hlsl(os.path.join(d, f))
    return files


def is_stripped(name):
    return "Stripped" in name


def union_names(files, block, folder=None):
    """offset -> set of non-stripped names (plus types) seen in any variant."""
    out = collections.defaultdict(lambda: collections.defaultdict(set))
    for (fld, _), info in files.items():
        if folder is not None and fld != folder:
            continue
        cb = info["cbuffers"].get(block)
        if not cb:
            continue
        for m in cb["members"]:
            if not is_stripped(m["name"]):
                out[m["offset"]][m["name"]].add(m["type"] + ("[%d]" % m["count"] if m["count"] else ""))
    return out


# --------------------------------------------------------------------------- captured layout
def align(v, a):
    return (v + a - 1) // a * a


def var_size_and_layout(v, off):
    """Return (start, size) for a captured reflection variable placed at cursor
    `off` using HLSL constant-buffer packing rules; also annotate children."""
    members = v.get("members")
    if members:
        start = align(off, 16)
        cur = start
        if v["type"].endswith("Struct") and not v["name"].endswith("]"):
            # struct: lay members out sequentially
            for m in members:
                s, sz = var_size_and_layout(m, cur)
                m["_offset"], m["_size"] = s, sz
                cur = s + sz
            size = align(cur - start, 16)
            return start, size
        # array: every element starts on a 16-byte boundary
        for m in members:
            s, sz = var_size_and_layout(m, align(cur, 16))
            m["_offset"], m["_size"] = s, sz
            cur = s + align(sz, 16)
        return start, cur - start
    rows, cols = v.get("rows", 1), v.get("columns", 1)
    if rows > 1:
        size = rows * 16 if rows >= cols else cols * 16
        return align(off, 16), size
    size = 4 * cols
    start = off
    if start % 16 + size > 16:
        start = align(start, 16)
    return start, size


def flatten_layout(cb):
    """Assign _offset/_size to all top-level captured variables and return the
    sequence [(offset, size, var)]."""
    seq = []
    cur = 0
    for v in cb["variables"]:
        s, sz = var_size_and_layout(v, cur)
        v["_offset"], v["_size"] = s, sz
        seq.append((s, sz, v))
        cur = s + sz
    return seq, align(cur, 16)


def captured_value(v, full=False):
    members = v.get("members")
    if members:
        if len(members) <= BIG_ARRAY_LIMIT or full:
            return [captured_value(m, full) for m in members]
        def has_nonzero(x):
            if isinstance(x, list):
                return any(has_nonzero(y) for y in x)
            return bool(x)
        nonzero = sum(1 for m in members if has_nonzero(captured_value(m, True)))
        return dict(array_len=len(members), first=captured_value(members[0], True),
                    nonzero_elements=nonzero)
    val = v.get("value")
    if isinstance(val, list) and v.get("rows", 1) > 1:
        r, c = v["rows"], v["columns"]
        return [val[i * c:(i + 1) * c] for i in range(r)]
    return val


def type_str(v):
    t = v["type"].split(".")[-1].lower()
    r, c = v.get("rows", 1), v.get("columns", 1)
    if v.get("members"):
        return "array[%d]" % len(v["members"]) if v["name"] and not v["type"].endswith("Struct") else "struct"
    if r > 1:
        return "%s%dx%d" % (t, r, c)
    if c > 1:
        return "%s%d" % (t, c)
    return t


# --------------------------------------------------------------------------- matching
def captured_block_map(stage):
    out = {}
    for cb in stage.get("constants", []):
        key = (cb["set"], cb["binding"])
        out[BLOCK_BY_BINDING.get(key, "unknown_s%d_b%d" % key)] = cb
    return out


def captured_resource_bindings(stage, space):
    return sorted(set(r["binding"] for r in stage.get("resources", []) if r["set"] == space))


def hlsl_member_seq(cb):
    return [(m["offset"], m["size"]) for m in cb["members"]]


def texture_resources(info, space):
    # RenderDoc's captured `resources` list here contains images, not the
    # separate storage buffers or samplers that also occupy HLSL registers.
    return [r for r in info["resources"] if r["space"] == space
            and r["kind"].startswith(("Texture", "RWTexture"))]


def score_variant(info, upm_captured, upm_seq, set1_bind, set0_bind):
    cb = info["cbuffers"].get("UnityPerMaterial")
    if not cb:
        return None
    s = {}
    s["binding_ok"] = (cb["binding"], cb["space"]) == (upm_captured["binding"], upm_captured["set"])
    s["size_ok"] = cb["size"] == upm_captured["size"]
    s["member_seq_ok"] = hlsl_member_seq(cb) == upm_seq
    r1 = sorted(set(r["binding"] for r in texture_resources(info, 1)))
    r0 = sorted(set(r["binding"] for r in texture_resources(info, 0)))
    s["set1_textures_ok"] = r1 == set1_bind
    s["set0_textures_ok"] = r0 == set0_bind
    s["score"] = sum(1 for k in ("binding_ok", "size_ok", "member_seq_ok", "set1_textures_ok", "set0_textures_ok") if s[k])
    return s


def pick_variant(files, folders, upm_captured, upm_seq, set1_bind, set0_bind, expected_texture_names=None):
    """Rank all families. Folder hints break ties, never exclude evidence.

    All equal-scoring candidates remain available to the caller's ambiguity
    report. A layout match is a hypothesis, not proof of texture semantics.
    """
    scored = []
    for (fld, f), info in files.items():
        if expected_texture_names is not None:
            actual = {r["binding"]: r["name"] for r in texture_resources(info, 1)}
            if actual != expected_texture_names:
                continue
        s = score_variant(info, upm_captured, upm_seq, set1_bind, set0_bind)
        if s and s["binding_ok"] and s["size_ok"]:
            scored.append((s["score"], fld, f, s))
    scored.sort(key=lambda x: (-x[0], 0 if folders and x[1] in folders else 1, x[1], x[2]))
    return scored


def signature(info):
    cb = info["cbuffers"].get("UnityPerMaterial")
    return (tuple((m["offset"], m["name"], m["type"]) for m in cb["members"]),
            tuple(sorted((r["binding"], r["name"]) for r in info["resources"] if r["space"] == 1)))


# --------------------------------------------------------------------------- per-event extraction
def name_block(cb_captured, hlsl_cb, union, mismatches, ctx, full_arrays=False, keep=None):
    seq, total = flatten_layout(cb_captured)
    if total != cb_captured["size"]:
        mismatches.append("%s: computed layout total %d != captured block size %d" % (ctx, total, cb_captured["size"]))
    by_off = {}
    if hlsl_cb:
        for m in hlsl_cb["members"]:
            by_off[m["offset"]] = m
    out = []
    for off, sz, v in seq:
        m = by_off.get(off)
        hn = m["name"] if m else None
        ht = (m["type"] + ("[%d]" % m["count"] if m["count"] else "")) if m else None
        alt = None
        if union is not None:
            names = union.get(off)
            if names:
                alt = {n: sorted(t) for n, t in names.items()}
        chosen = hn if (hn and not is_stripped(hn)) else None
        source = "variant"
        if chosen is None and alt:
            if len(alt) == 1:
                chosen = next(iter(alt))
                source = "other_variant"
            else:
                chosen = None
                source = "conflict:" + "|".join(sorted(alt))
        if m is None and hlsl_cb is not None:
            mismatches.append("%s: captured var %s at offset %d (size %d) has no HLSL member at that offset" % (ctx, v["name"], off, sz))
        elif m is not None and m["size"] is not None and m["size"] != sz:
            mismatches.append("%s: %s offset %d size captured %d vs HLSL %s %d" % (ctx, hn, off, sz, ht, m["size"]))
        if keep is not None and not keep(chosen or hn or ""):
            continue
        out.append(dict(offset=off, size=sz, captured=v["name"], captured_type=type_str(v),
                        name=chosen or hn, name_source=source if chosen else ("stripped" if hn else "unmatched"),
                        hlsl_type=ht, alt_names=alt if alt and len(alt) > 1 else None,
                        major=m.get("major") if m else None,
                        value=captured_value(v, full_arrays)))
    return dict(set=cb_captured["set"], binding=cb_captured["binding"], size=cb_captured["size"],
                hlsl_size=hlsl_cb["size"] if hlsl_cb else None, variables=out)


def texture_table(stage, info, textures, space):
    by_bind = {}
    if info:
        for r in info["resources"]:
            if r["space"] == space and r["reg"] in ("t", "u"):
                by_bind[r["binding"]] = r
    rows = []
    for r in sorted(stage.get("resources", []), key=lambda r: (r["set"], r["binding"])):
        if r["set"] != space:
            continue
        h = by_bind.get(r["binding"])
        tex = textures.get(r["resource"], {})
        rows.append(dict(set=r["set"], binding=r["binding"], resource=r["resource"],
                         hlsl_name=h["name"] if h else None, hlsl_kind=(h["kind"] + ("<%s>" % h["fmt"] if h["fmt"] else "")) if h else None,
                         inventory_name=tex.get("name"), width=tex.get("width"), height=tex.get("height"),
                         format=tex.get("format"), mips=tex.get("mips"), array_size=tex.get("array_size")))
    return rows


def main():
    details = json.load(open(os.path.join(DETAILS_DIR, "draw-details.json")))
    inventory = json.load(open(os.path.join(DETAILS_DIR, "inventory.json")))
    textures = {t["id"]: t for t in inventory["textures"]}
    draws = {d["event"]: d for d in details["draws_and_dispatches"]}
    files = load_dump(DUMP_DIR)
    folders = sorted(set(k[0] for k in files))

    global_union = {b: union_names(files, b) for b in ("TransformVariables", "ShaderVariablesGlobal", "LightDataBuffer", "ShadowData", "LightBinningConstants")}
    upm_union = {f: union_names(files, "UnityPerMaterial", f) for f in folders}

    result = dict(source=dict(details_dir=DETAILS_DIR, dump_dir=DUMP_DIR),
                  events=collections.OrderedDict(), layout_mismatches=[], notes=[])
    mism = result["layout_mismatches"]
    main_ps = {}

    def process(ev, part, folder_hint, is_overlay):
        d = draws[ev]
        ps = d["stages"].get("ShaderStage.Pixel")
        vs = d["stages"].get("ShaderStage.Vertex")
        blocks = captured_block_map(ps)
        upm = blocks.get("UnityPerMaterial")
        entry = collections.OrderedDict(event=ev, part=part, index_count=d.get("index_count"), pipeline=d.get("pipeline"),
                                        vs_shader=vs.get("shader") if vs else None, ps_shader=ps.get("shader"),
                                        outputs=d.get("outputs"), depth=d.get("depth"),
                                        output_textures=[dict(id=o, **{k: textures.get(o, {}).get(k) for k in ("name", "width", "height", "format")}) for o in d.get("outputs", []) if o != "ResourceId::0"],
                                        captured_blocks=[dict(name=n, set=c["set"], binding=c["binding"], size=c["size"], var_count=len(c["variables"])) for n, c in blocks.items()])
        set1_bind = captured_resource_bindings(ps, 1)
        set0_bind = captured_resource_bindings(ps, 0)
        match_info = None
        chosen = None
        folder = None
        if upm:
            upm_seq_pairs, _ = flatten_layout(upm)
            upm_seq = [(o, s) for o, s, _ in upm_seq_pairs]
            search = [folder_hint] if folder_hint else None
            reviewed_names = REVIEWED_SET1_TEXTURES.get(ev)
            scored = pick_variant(files, search, upm, upm_seq, set1_bind, set0_bind, reviewed_names)
            best = [s for s in scored if s[0] == scored[0][0]] if scored else []
            sigs = {}
            for sc, fld, f, s in best:
                sigs.setdefault(signature(files[(fld, f)]), []).append(f)
            match_info = dict(captured_upm_size=upm["size"], captured_set1_texture_bindings=set1_bind,
                              folder_hint=folder_hint, search_scope="all_families",
                              reviewed_set1_texture_names=reviewed_names,
                              captured_set0_texture_bindings=set0_bind,
                              candidates_same_size=len(scored),
                              best=[dict(folder=fld, file=f, **s) for sc, fld, f, s in best[:12]],
                              distinct_best_signatures=len(sigs),
                              ambiguous=len(sigs) > 1,
                              size_matches_by_folder=dict(collections.Counter(fld for _, fld, _, _ in scored)))
            if best:
                folder, fname = best[0][1], best[0][2]
                chosen = files[(folder, fname)]
                match_info["chosen"] = dict(folder=folder, file=fname)
                if len(sigs) > 1:
                    alts = []
                    for sig, fl in sigs.items():
                        alts.append(dict(files=fl[:4], set1_textures=[dict(binding=b, name=n) for b, n in sig[1]]))
                    match_info["ambiguous_alternatives"] = alts
                    mism.append("event %d: %d distinct best-scoring HLSL signatures (score %d); chose %s/%s" % (ev, len(sigs), best[0][0], folder, fname))
                if not best[0][3]["member_seq_ok"]:
                    mism.append("event %d: no HLSL variant reproduces the captured UnityPerMaterial member sequence exactly (best %s/%s)" % (ev, folder, fname))
        entry["hlsl_match"] = match_info

        cbs = chosen["cbuffers"] if chosen else {}
        blk = collections.OrderedDict()
        ctx = "event %d" % ev
        if upm:
            blk["UnityPerMaterial"] = name_block(upm, cbs.get("UnityPerMaterial"), upm_union.get(folder), mism, ctx + " UnityPerMaterial", full_arrays=True)
        for bname in ("TransformVariables", "ShaderVariablesGlobal", "LightDataBuffer", "ShadowData", "LightBinningConstants"):
            c = blocks.get(bname)
            if not c:
                continue
            hl = cbs.get(bname)
            if hl is None:
                # any variant declares these identically; borrow from the first file that has it
                for info in files.values():
                    if bname in info["cbuffers"]:
                        hl = info["cbuffers"][bname]
                        break
            full = bname in ("TransformVariables", "LightBinningConstants")
            blk[bname] = name_block(c, hl, global_union[bname], mism, ctx + " " + bname, full_arrays=full)
        entry["blocks"] = blk
        entry["textures_set1"] = texture_table(ps, chosen, textures, 1)
        entry["textures_set0"] = texture_table(ps, chosen, textures, 0)
        if is_overlay:
            entry["ps_matches_main_pass"] = [e for e, sid in main_ps.items() if sid == ps.get("shader")]
        else:
            main_ps[ev] = ps.get("shader")
        result["events"][str(ev)] = entry

    for ev, (part, folder) in MAIN_EVENTS.items():
        process(ev, part, folder, False)
    for ev in OVERLAY_EVENTS:
        process(ev, "overlay", None, True)

    # derived camera data from 875
    result["derived"] = derive_camera(result["events"]["875"])
    result["compare_875_vs_860"] = compare_globals(result["events"]["875"], result["events"]["860"])

    os.makedirs(OUT_DIR, exist_ok=True)
    jpath = os.path.join(OUT_DIR, "constants-by-event.json")
    json.dump(result, open(jpath, "w"), indent=1)
    mpath = os.path.join(OUT_DIR, "summary.md")
    open(mpath, "w", encoding="utf-8").write(write_summary(result))
    print("wrote", jpath)
    print("wrote", mpath)
    for m in mism:
        print("MISMATCH:", m)


# --------------------------------------------------------------------------- derived / summary
def find_var(block, name):
    for v in block["variables"]:
        if v["name"] == name:
            return v
    return None


def derive_camera(ev):
    tv = ev["blocks"]["TransformVariables"]
    out = {}
    view = find_var(tv, "_TransformVariables_ViewMatrix")
    proj = find_var(tv, "_TransformVariables_ProjMatrix")
    pos = find_var(tv, "_TransformVariables_WorldSpaceCameraPos_Internal")
    if pos:
        out["camera_pos_world"] = pos["value"][:3]
    if view:
        M = view["value"]
        out["view_matrix_rows_as_captured"] = M
        last_row = M[3]
        last_col = [M[i][3] for i in range(4)]
        out["view_last_row"] = last_row
        out["view_last_col"] = last_col
        # camera-relative rendering => translation column is ~0; basis vectors are the rows of the 3x3.
        if all(abs(x) < 1e-6 for x in last_row[:3]) and abs(last_row[3] - 1) < 1e-6:
            out["view_layout"] = "value[r][c] is the logical row-major matrix (last row = [0,0,0,1]); translation in column 3 = %s" % last_col[:3]
        elif all(abs(x) < 1e-6 for x in last_col[:3]) and abs(last_col[3] - 1) < 1e-6:
            out["view_layout"] = "value rows are matrix columns (last column = [0,0,0,1]); translation in row 3 = %s" % last_row[:3]
        else:
            out["view_layout"] = "could not classify"
        out["camera_right_ws"] = M[0][:3]
        out["camera_up_ws"] = M[1][:3]
        out["camera_forward_ws(view -z)"] = [-x for x in M[2][:3]]
    if proj:
        P = proj["value"]
        out["proj_matrix_rows_as_captured"] = P
        p00, p11 = P[0][0], P[1][1]
        if p00 and p11:
            out["proj_aspect"] = abs(p11 / p00)
            out["proj_vertical_fov_deg"] = 2 * math.degrees(math.atan(1.0 / abs(p11)))
            out["proj_horizontal_fov_deg"] = 2 * math.degrees(math.atan(1.0 / abs(p00)))
            out["proj_y_flipped"] = p11 < 0
        out["proj_row2"] = P[2]
        out["proj_row3"] = P[3]
    ld = ev["blocks"].get("LightDataBuffer")
    if ld:
        out["directional_light"] = {v["name"] or v["captured"]: v["value"] for v in ld["variables"] if not isinstance(v["value"], dict)}
    sg = ev["blocks"].get("ShaderVariablesGlobal")
    if sg:
        for key in ("_ExposureWithMiscParams", "_ScreenSize", "_ZBufferParams", "_ProjectionParams", "_Time"):
            v = find_var(sg, key)
            if v:
                out[key] = v["value"]
    return out


def compare_globals(a, b):
    out = {}
    for bname in ("ShaderVariablesGlobal", "LightDataBuffer", "TransformVariables"):
        va = {v["offset"]: v for v in a["blocks"][bname]["variables"]}
        vb = {v["offset"]: v for v in b["blocks"][bname]["variables"]}
        diffs = []
        for off in sorted(set(va) | set(vb)):
            x, y = va.get(off), vb.get(off)
            if x is None or y is None or json.dumps(x["value"]) != json.dumps(y["value"]):
                diffs.append(dict(offset=off, name=(x or y)["name"], a=x["value"] if x else None, b=y["value"] if y else None))
        out[bname] = dict(identical=not diffs, differing=diffs)
    return out


INTEREST = re.compile(r"Color|Ramp|Shadow|Rim|Spec|Aniso|Outline|Metallic|Smooth|Gloss|Bump|Line|Tint|Sss|SSS|Emission|Fresnel|Hair|Eye|Iris|Pupil|Face|Skin|Cutoff|Alpha|Layer", re.I)


def fmt(v):
    if isinstance(v, float):
        return ("%.6g" % v)
    if isinstance(v, list):
        return "[" + ", ".join(fmt(x) for x in v) + "]"
    if isinstance(v, dict):
        return "array(%s, first=%s)" % (v.get("array_len"), fmt(v.get("first")))
    return str(v)


def write_summary(res):
    L = []
    L.append("# Front-frame constants (tifuluosi-front-20260917 / replay-details-01)\n")
    L.append("Source: `%s`  \nHLSL names: `%s`\n" % (res["source"]["details_dir"], res["source"]["dump_dir"]))
    d = res["derived"]
    L.append("## Camera / projection (event 875)\n")
    for k in ("camera_pos_world", "view_layout", "camera_right_ws", "camera_up_ws", "camera_forward_ws(view -z)", "proj_aspect", "proj_vertical_fov_deg", "proj_horizontal_fov_deg", "proj_y_flipped", "_ExposureWithMiscParams", "_ScreenSize", "_ZBufferParams", "_ProjectionParams", "_Time"):
        if k in d:
            L.append("- %s: %s" % (k, fmt(d[k])))
    L.append("\nView matrix (as captured, rows):\n")
    for r in d.get("view_matrix_rows_as_captured", []):
        L.append("    " + fmt(r))
    L.append("\nProjection matrix (as captured, rows):\n")
    for r in d.get("proj_matrix_rows_as_captured", []):
        L.append("    " + fmt(r))
    L.append("\n## Directional light (LightDataBuffer header, event 875)\n")
    for k, v in d.get("directional_light", {}).items():
        L.append("- %s: %s" % (k, fmt(v)))

    L.append("\n## Per-event HLSL variant match\n")
    L.append("| event | part | PS shader | UPM size | chosen HLSL | score (bind/size/members/set1/set0) | ambiguous |")
    L.append("|---|---|---|---|---|---|---|")
    for ev, e in res["events"].items():
        m = e.get("hlsl_match") or {}
        ch = m.get("chosen")
        b = (m.get("best") or [None])[0]
        sc = "%s/%s/%s/%s/%s" % tuple("Y" if b and b[k] else "n" for k in ("binding_ok", "size_ok", "member_seq_ok", "set1_textures_ok", "set0_textures_ok")) if b else "-"
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (ev, e["part"], e["ps_shader"], m.get("captured_upm_size"), ("%s/%s" % (ch["folder"], ch["file"])) if ch else "none", sc, m.get("ambiguous")))

    L.append("\n## UnityPerMaterial values per part\n")
    for ev, e in res["events"].items():
        upm = e["blocks"].get("UnityPerMaterial")
        if not upm:
            continue
        L.append("### event %s (%s) - %d bytes, %d vars\n" % (ev, e["part"], upm["size"], len(upm["variables"])))
        L.append("| offset | name | type | value |")
        L.append("|---|---|---|---|")
        for v in upm["variables"]:
            nm = v["name"] or v["captured"]
            if v["name_source"].startswith("conflict"):
                nm += " (%s)" % v["name_source"]
            elif v["name_source"] == "other_variant":
                nm += " *"
            L.append("| %d | %s | %s | %s |" % (v["offset"], nm, v["captured_type"], fmt(v["value"])))
        L.append("")
    L.append("`*` = name taken from another variant of the same shader folder (member stripped in the chosen variant).\n")

    L.append("## Texture bindings (set 1 = material)\n")
    L.append("| event | part | binding | HLSL name | resource | inventory name | size | format |")
    L.append("|---|---|---|---|---|---|---|---|")
    for ev, e in res["events"].items():
        for t in e["textures_set1"]:
            L.append("| %s | %s | %d | %s | %s | %s | %sx%s | %s |" % (ev, e["part"], t["binding"], t["hlsl_name"], t["resource"], t["inventory_name"], t["width"], t["height"], t["format"]))
    L.append("\n## Texture bindings (set 0 = global) for event 875\n")
    L.append("| binding | HLSL name | resource | inventory name | size | format |")
    L.append("|---|---|---|---|---|---|")
    for t in res["events"]["875"]["textures_set0"]:
        L.append("| %d | %s | %s | %s | %sx%s | %s |" % (t["binding"], t["hlsl_name"], t["resource"], t["inventory_name"], t["width"], t["height"], t["format"]))

    L.append("\n## ShaderVariablesGlobal fields of interest (event 875)\n")
    sg = res["events"]["875"]["blocks"]["ShaderVariablesGlobal"]
    L.append("| offset | name | value |")
    L.append("|---|---|---|")
    for v in sg["variables"]:
        nm = v["name"] or ""
        if re.search(r"Character|Exposure|SH|Ambient|Fog|Shadow|Env|IV|Sky|Light", nm):
            L.append("| %d | %s | %s |" % (v["offset"], nm, fmt(v["value"])))
    L.append("\n## 875 vs 860 global blocks\n")
    for bname, c in res["compare_875_vs_860"].items():
        if c["identical"]:
            L.append("- %s: identical" % bname)
        else:
            L.append("- %s: %d differing fields: %s" % (bname, len(c["differing"]), ", ".join("%s@%d" % (x["name"], x["offset"]) for x in c["differing"][:20])))

    L.append("\n## Overlay / late passes\n")
    for ev in [str(e) for e in OVERLAY_EVENTS]:
        e = res["events"][ev]
        m = e.get("hlsl_match") or {}
        L.append("- event %s: PS %s, VS %s, outputs %s, depth %s, index_count %s; PS matches main-pass events %s; UPM size %s; size matches by folder %s; chosen %s" % (
            ev, e["ps_shader"], e["vs_shader"], [o["id"] + "(" + str(o["name"]) + ")" for o in e["output_textures"]], e["depth"], e["index_count"], e.get("ps_matches_main_pass"), m.get("captured_upm_size"), m.get("size_matches_by_folder"), m.get("chosen")))
        for t in e["textures_set1"]:
            L.append("    - set1 b%d %s -> %s %s %sx%s %s" % (t["binding"], t["hlsl_name"], t["resource"], t["inventory_name"], t["width"], t["height"], t["format"]))
        L.append("    - set0 bindings: %s" % ", ".join("b%d %s->%s" % (t["binding"], t["hlsl_name"], t["inventory_name"]) for t in e["textures_set0"]))

    L.append("\n## Layout mismatches / unresolved\n")
    if not res["layout_mismatches"]:
        L.append("- none")
    for m in res["layout_mismatches"]:
        L.append("- " + m)
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
