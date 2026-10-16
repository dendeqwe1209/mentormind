"""Compare self-host vs cloud pass-A answers on the LASI video (fps 4), from the saved raw answers.

No API call: every answer is re-read from data/work/vlm/<VID>/sweep-<provider>/fps4/pass_a/.
Lenient parsing (both models, same rules): `objects` given as a string -> split on commas;
missing `confidence` -> empty; a step without `step` text cannot be used and is counted as lost.
Semantics: BAAI/bge-m3 cosine (the embedding model of spec 01). Lexical: rapidfuzz token_set_ratio.
"""

import csv
import glob
import json
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz, utils
from sentence_transformers import SentenceTransformer

# usage: compare.py <repo> <threshold> [<out_dir> <nameA>=<run_dir> <nameB>=<run_dir>]
REPO = Path(sys.argv[1])
VID = "VID-96bd368c7e84"
T = float(sys.argv[2]) if len(sys.argv) > 2 else 0.75
if len(sys.argv) > 5:
    OUT = REPO / sys.argv[3]
    RUNS = dict((kv.split("=", 1)[0], REPO / kv.split("=", 1)[1]) for kv in sys.argv[4:6])
else:
    OUT = REPO / "data/work/compare/lasi_fps4"
    RUNS = {
        "selfhost": REPO / f"data/work/vlm/{VID}/sweep-local_openai/fps4",
        "cloud": REPO / f"data/work/vlm/{VID}/sweep-qwen_api/fps4",
    }
OUT.mkdir(parents=True, exist_ok=True)
A, B = list(RUNS)


def parse(text):
    try:
        data = json.loads(re.sub(r"^```(json)?|```$", "", text.strip()).strip())
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except Exception:
            data = None
    if not isinstance(data, dict):
        return None, [], 0
    steps, lost = [], 0
    for s in data.get("steps") or []:
        if not isinstance(s, dict) or not str(s.get("step") or "").strip():
            lost += 1
            continue
        objs = s.get("objects") or []
        if isinstance(objs, str):
            objs = [o.strip() for o in objs.split(",") if o.strip()]
        steps.append(
            {
                "step": s["step"].strip(),
                "t0": float(s.get("t_start_rel") or 0),
                "t1": float(s.get("t_end_rel") or 0),
                "objects": objs,
                "conf": s.get("confidence"),
                "actor": s.get("actor"),
                "hand": s.get("hand_action"),
            }
        )
    return data.get("scene"), steps, lost


def load(run_dir):
    segs = {}
    for f in sorted(glob.glob(str(run_dir / "pass_a" / "*.json"))):
        if f.endswith(".repair.json"):
            continue
        rec = json.load(open(f))
        sid = rec["segment_id"]
        attempts = [rec] + (
            [json.load(open(f[:-5] + ".repair.json"))] if Path(f[:-5] + ".repair.json").exists() else []
        )
        parsed = [parse(a["response"]["text"]) for a in attempts]
        best = max(range(len(parsed)), key=lambda i: (len(parsed[i][1]), -i))
        scene, steps, lost = parsed[best]
        dur = rec["t_end"] - rec["t_start"]
        for s in steps:
            a = min(s["t0"], dur)
            b = min(max(s["t1"], s["t0"]), dur)
            s["t0"], s["t1"] = rec["t_start"] + a, rec["t_start"] + b
        tok = sum(
            (a["response"].get("usage") or {}).get("prompt_tokens", 0)
            + (a["response"].get("usage") or {}).get("completion_tokens", 0)
            for a in attempts
        )
        segs[sid] = {
            "t_start": rec["t_start"],
            "t_end": rec["t_end"],
            "scene": scene or "",
            "steps": steps,
            "lost": lost,
            "frames": len(rec["frame_timestamps"]),
            "tokens": tok,
            "calls": len(attempts),
        }
    return segs


def show(s):
    """[t0-t1] (actor) step — the actor shown when the prompt version asked for one."""
    who = f"({s['actor']}) " if s.get("actor") else ""
    return f"[{s['t0']:.1f}-{s['t1']:.1f}] {who}{s['step']}"


def overlaps(a0, a1, b0, b1, slack=1.0):
    return min(a1, b1) + slack >= max(a0, b0)


runs = {k: load(v) for k, v in RUNS.items()}
failed = {
    k: {x["segment_id"] for x in json.load(open(v / "failed_segments.json"))}
    if (v / "failed_segments.json").exists()
    else set()
    for k, v in RUNS.items()
}
truth = json.load(open(REPO / "data/video/groundtruth.json"))["steps"]
model = SentenceTransformer("BAAI/bge-m3")
texts = sorted(
    {s["step"] for r in runs.values() for g in r.values() for s in g["steps"]}
    | {g["scene"] for r in runs.values() for g in r.values() if g["scene"]}
    | {t["step"] for t in truth}
)
vec = dict(zip(texts, model.encode(texts, normalize_embeddings=True, batch_size=32)))


def cos(a, b):
    return float(vec[a] @ vec[b])


def lex(a, b):
    return fuzz.token_set_ratio(a, b, processor=utils.default_process)


def pair(a, b):
    """Greedy one-to-one pairing by cosine; returns [(i, j, cos)]."""
    cand = sorted(((cos(x["step"], y["step"]), i, j) for i, x in enumerate(a) for j, y in enumerate(b)), reverse=True)
    ui, uj, out = set(), set(), []
    for c, i, j in cand:
        if i in ui or j in uj:
            continue
        ui.add(i)
        uj.add(j)
        out.append((i, j, c))
    return out


seg_rows, step_rows = [], []
sum_best_l, sum_best_c, n_l, n_c, agree, scene_cos = 0.0, 0.0, 0, 0, 0, []
for sid in sorted(runs[A]):
    L, C = runs[A][sid], runs[B].get(sid)
    if C is None:
        continue
    sc = cos(L["scene"], C["scene"]) if L["scene"] and C["scene"] else None
    if sc is not None:
        scene_cos.append(sc)
    best_l = [max((cos(x["step"], y["step"]) for y in C["steps"]), default=0.0) for x in L["steps"]]
    best_c = [max((cos(y["step"], x["step"]) for x in L["steps"]), default=0.0) for y in C["steps"]]
    sum_best_l += sum(best_l)
    sum_best_c += sum(best_c)
    n_l += len(best_l)
    n_c += len(best_c)
    pairs = pair(L["steps"], C["steps"])
    ok = [
        p
        for p in pairs
        if p[2] >= T
        and overlaps(L["steps"][p[0]]["t0"], L["steps"][p[0]]["t1"], C["steps"][p[1]]["t0"], C["steps"][p[1]]["t1"])
    ]
    agree += len(ok)
    both_empty = not L["steps"] and not C["steps"]
    seg_rows.append(
        {
            "segment_id": sid,
            "t_start": L["t_start"],
            "t_end": L["t_end"],
            f"{A}_scene": L["scene"],
            f"{B}_scene": C["scene"],
            "scene_cosine": None if sc is None else round(sc, 3),
            f"{A}_steps": " | ".join(show(s) for s in L["steps"]),
            f"{B}_steps": " | ".join(show(s) for s in C["steps"]),
            f"n_{A}": len(L["steps"]),
            f"n_{B}": len(C["steps"]),
            f"{B}_steps_lost_no_text": C["lost"],
            f"{B}_failed_in_pipeline": sid in failed[B],
            f"{A}_failed_in_pipeline": sid in failed[A],
            "agreed_pairs": len(ok),
            "step_soft_f1": 1.0
            if both_empty
            else (
                round(
                    2
                    * (sum(best_l) / max(len(best_l), 1))
                    * (sum(best_c) / max(len(best_c), 1))
                    / max((sum(best_l) / max(len(best_l), 1)) + (sum(best_c) / max(len(best_c), 1)), 1e-9),
                    3,
                )
                if best_l and best_c
                else 0.0
            ),
            f"{A}_frames": L["frames"],
            f"{B}_frames": C["frames"],
            f"{A}_tokens": L["tokens"],
            f"{B}_tokens": C["tokens"],
        }
    )
    for i, j, c in pairs:
        step_rows.append(
            {
                "segment_id": sid,
                f"{A}_step": L["steps"][i]["step"],
                f"{B}_step": C["steps"][j]["step"],
                f"{A}_time": f"{L['steps'][i]['t0']:.1f}-{L['steps'][i]['t1']:.1f}",
                f"{B}_time": f"{C['steps'][j]['t0']:.1f}-{C['steps'][j]['t1']:.1f}",
                f"{A}_actor": L["steps"][i]["actor"],
                f"{B}_actor": C["steps"][j]["actor"],
                f"{A}_hand_action": L["steps"][i]["hand"],
                f"{B}_hand_action": C["steps"][j]["hand"],
                "cosine_bge_m3": round(c, 3),
                "lexical_token_set": round(lex(L["steps"][i]["step"], C["steps"][j]["step"]), 1),
                "agree": c >= T
                and overlaps(L["steps"][i]["t0"], L["steps"][i]["t1"], C["steps"][j]["t0"], C["steps"][j]["t1"]),
            }
        )


def vs_truth(run):
    preds = [s for g in run.values() for s in g["steps"]]
    sem = sum(
        any(overlaps(t["t_start"], t["t_end"], p["t0"], p["t1"]) and cos(t["step"], p["step"]) >= T for p in preds)
        for t in truth
    )
    lx = sum(
        any(overlaps(t["t_start"], t["t_end"], p["t0"], p["t1"], 0) and lex(t["step"], p["step"]) >= 70 for p in preds)
        for t in truth
    )
    tm = sum(any(overlaps(t["t_start"], t["t_end"], p["t0"], p["t1"]) for p in preds) for t in truth)
    psem = sum(
        any(overlaps(t["t_start"], t["t_end"], p["t0"], p["t1"]) and cos(t["step"], p["step"]) >= T for t in truth)
        for p in preds
    )
    return {
        "steps": len(preds),
        "semantic_recall": sem / len(truth),
        "semantic_precision": psem / max(len(preds), 1),
        "lexical_recall": lx / len(truth),
        "time_recall": tm / len(truth),
    }


with open(OUT / "compare_segments.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(seg_rows[0]))
    w.writeheader()
    w.writerows(seg_rows)
with open(OUT / "compare_steps.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(step_rows[0]) if step_rows else ["segment_id"])
    w.writeheader()
    w.writerows(step_rows)
P = sum_best_c / max(n_c, 1)
R = sum_best_l / max(n_l, 1)
summary = {
    "threshold_cosine": T,
    "segments": len(seg_rows),
    "scene_cosine_mean": sum(scene_cos) / len(scene_cos),
    f"steps_{A}": n_l,
    f"steps_{B}": n_c,
    f"{B}_steps_lost_no_text": sum(g["lost"] for g in runs[B].values()),
    f"{B}_failed_in_pipeline": len(failed[B]),
    "agreed_step_pairs": agree,
    f"agreement_{A}_pct": agree / max(n_l, 1),
    f"agreement_{B}_pct": agree / max(n_c, 1),
    "soft_semantic_f1": 2 * P * R / max(P + R, 1e-9),
    "segments_both_empty": sum(1 for r in seg_rows if r[f"n_{A}"] == 0 and r[f"n_{B}"] == 0),
    "vs_truth": {k: vs_truth(v) for k, v in runs.items()},
    "tokens": {k: sum(g["tokens"] for g in v.values()) for k, v in runs.items()},
}
json.dump(summary, open(OUT / "summary.json", "w"), ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
