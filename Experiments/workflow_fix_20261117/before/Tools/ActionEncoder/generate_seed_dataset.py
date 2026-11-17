"""Generate a rich, grouped Chinese corpus covering all 12 Yukikaze full-body actions."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "Dataset" / "ActionCards" / "seed_corpus.jsonl"

COUNT_WORDS = {1: ["一", "1"], 2: ["两", "二", "2"], 3: ["三", "3"]}
SPEED_PHRASES = {
    "slow": ["慢慢地", "缓慢地", "慢点"],
    "normal": ["", "自然地"],
    "fast": ["快速", "快点", "迅速地"],
}
AMP_PHRASES = {
    "small": ["轻轻", "微微", "小幅度"],
    "normal": ["", "明显地"],
}


def make_plan(decision: str, steps: list[dict] | None = None) -> dict:
    return {"version": "action-plan.v0.1", "decision": decision, "steps": steps or []}


def build_corpus() -> list[dict]:
    rows: list[dict] = []
    gid = 0

    def add_group(plan: dict, texts: list[str], note: str = ""):
        nonlocal gid
        gid += 1
        group_id = f"seed-grp-{gid:04d}"
        seen = set()
        for t in texts:
            s = " ".join(t.split()).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            rows.append({
                "group_id": group_id,
                "raw_text": s,
                "plan": plan,
                "source": "seed_corpus_v2_fullbody",
                "note": note,
            })

    # 1. blink
    for cnt in (1, 2, 3):
        for spd in ("slow", "normal", "fast"):
            plan = make_plan("execute", [{"actions": [{"type": "blink", "count": cnt, "amplitude": "full", "speed": spd}]}])
            texts = []
            for cw in COUNT_WORDS[cnt]:
                for sp in SPEED_PHRASES[spd]:
                    texts.extend([f"{sp}眨{cw}下眼", f"{sp}眨{cw}次眼", f"{sp}眨眼{cw}次"])
                    if cnt == 1 and sp == "":
                        texts.extend(["眨眼", "眨一下眼睛", "闭眼再睁开", "眨眨眼"])
            add_group(plan, texts, f"blink_{cnt}_{spd}")

    # 2. All other 11 actions with count (1..3), amplitude (small/normal), speed (slow/normal/fast)
    action_templates = {
        "nod": [("{ap}{sp}点{cw}下头", "{ap}{sp}点头{cw}次"), ("点头", "点点头", "答应一下", "同意", "嗯嗯")],
        "shake_head": [("{ap}{sp}摇{cw}下头", "{ap}{sp}摇头{cw}次"), ("摇头", "摇摇头", "晃晃头", "表示不要")],
        "tilt_head": [("{ap}{sp}歪{cw}下头", "{ap}{sp}歪头{cw}次"), ("歪头", "歪歪头", "歪着头卖萌", "疑惑地歪头", "偏一下头")],
        "look_around": [("{ap}{sp}四处张望{cw}次", "{ap}{sp}左右看看{cw}次"), ("四处看看", "东张西望", "看左边看右边", "环顾四周", "看这边")],
        "smile": [("{ap}{sp}微笑{cw}次", "{ap}{sp}笑眯眯{cw}次"), ("微笑", "笑一下", "开心一下", "露出笑容", "笑眯眯", "高兴地笑")],
        "angry": [("{ap}{sp}生气{cw}次", "{ap}{sp}傲娇鼓嘴{cw}次"), ("生气", "生个气", "傲娇一下", "嘟嘴不开心", "哼一声")],
        "shy": [("{ap}{sp}害羞{cw}次", "{ap}{sp}不好意思{cw}次"), ("害羞", "害羞一下", "脸红了", "不好意思地低头", "撒个娇")],
        "surprise": [("{ap}{sp}惊讶{cw}次", "{ap}{sp}吃惊{cw}次"), ("惊讶", "吓一跳", "吃一惊", "张大嘴巴", "哇塞")],
        "wave": [("{ap}{sp}挥{cw}下手", "{ap}{sp}招手{cw}次"), ("挥手", "挥挥手", "打个招呼", "招招手", "拜拜", "你好呀")],
        "cheer": [("{ap}{sp}欢呼{cw}次", "{ap}{sp}举手加油{cw}次"), ("欢呼", "举起双手", "加油", "太棒了", "兴奋地跳一下", "耶")],
        "bow": [("{ap}{sp}鞠躬{cw}次", "{ap}{sp}行礼{cw}次"), ("鞠躬", "行个礼", "鞠躬道歉", "谢谢你", "弯腰致意")],
    }

    for atype, (patterns, defaults) in action_templates.items():
        for cnt in (1, 2, 3):
            for amp in ("small", "normal"):
                for spd in ("slow", "normal", "fast"):
                    plan = make_plan("execute", [{"actions": [{"type": atype, "count": cnt, "amplitude": amp, "speed": spd}]}])
                    texts = []
                    for cw in COUNT_WORDS[cnt]:
                        for ap in AMP_PHRASES[amp]:
                            for sp in SPEED_PHRASES[spd]:
                                for pat in patterns:
                                    texts.append(pat.format(ap=ap, sp=sp, cw=cw))
                    if cnt == 1 and amp == "normal" and spd == "normal":
                        texts.extend(defaults)
                    add_group(plan, texts, f"{atype}_{cnt}_{amp}_{spd}")

    # 3. General open-ended movement / reaction phrases -> responsive lively motions
    add_group(
        make_plan("execute", [{"actions": [{"type": "tilt_head", "count": 1, "amplitude": "normal", "speed": "normal"}]}]),
        ["动一动", "动一下", "做个反应", "随便动动", "做个可爱的动作", "卖个萌"],
        "open_cute_reaction",
    )
    add_group(
        make_plan("execute", [{"actions": [{"type": "wave", "count": 1, "amplitude": "normal", "speed": "normal"}]}]),
        ["来个动作", "表演一下", "互动一下", "和我打招呼"],
        "open_greet_reaction",
    )

    # 4. Two-step sequential & parallel combinations across diverse actions (including amplitude modifiers)
    pairs = [
        ("nod", "点头", "blink", "眨眼"),
        ("nod", "点头", "smile", "微笑"),
        ("shake_head", "摇头", "blink", "眨眼"),
        ("shake_head", "摇头", "angry", "生气"),
        ("tilt_head", "歪头", "smile", "微笑"),
        ("tilt_head", "歪头", "blink", "眨眼"),
        ("wave", "挥手", "smile", "微笑"),
        ("wave", "挥手", "blink", "眨眼"),
        ("bow", "鞠躬", "blink", "眨眼"),
        ("bow", "鞠躬", "smile", "微笑"),
        ("cheer", "欢呼", "blink", "眨眼"),
        ("cheer", "欢呼", "smile", "微笑"),
        ("shy", "害羞", "tilt_head", "歪头"),
        ("surprise", "惊讶", "look_around", "四处看看"),
    ]
    for t1, cn1, t2, cn2 in pairs:
        for cnt1 in (1, 2):
            for cnt2 in (1, 2):
                amp1_list = ["full"] if t1 == "blink" else ["small", "normal"]
                for amp1 in amp1_list:
                    amp2 = "full" if t2 == "blink" else "normal"
                    ap1_words = [""] if t1 == "blink" else (["轻轻", "微微"] if amp1 == "small" else [""])
                    # Sequential
                    plan_seq = make_plan("execute", [
                        {"actions": [{"type": t1, "count": cnt1, "amplitude": amp1, "speed": "normal"}]},
                        {"actions": [{"type": t2, "count": cnt2, "amplitude": amp2, "speed": "normal"}]},
                    ])
                    seq_texts = []
                    for cw1 in COUNT_WORDS[cnt1]:
                        for cw2 in COUNT_WORDS[cnt2]:
                            for ap1 in ap1_words:
                                for conn in ("，然后", "，接着", "之后再"):
                                    seq_texts.append(f"{ap1}{cn1}{cw1}次{conn}{cn2}{cw2}次")
                                    seq_texts.append(f"{ap1}{cn1}{cw1}下{conn}{cn2}{cw2}下")
                                    if cnt2 == 1:
                                        seq_texts.append(f"{ap1}{cn1}{cw1}次{conn}{cn2}一下")
                    add_group(plan_seq, seq_texts, f"seq_{t1}_{amp1}_{t2}")

                    # Parallel
                    plan_par = make_plan("execute", [
                        {"actions": [
                            {"type": t1, "count": cnt1, "amplitude": amp1, "speed": "normal"},
                            {"type": t2, "count": cnt2, "amplitude": amp2, "speed": "normal"},
                        ]}
                    ])
                    par_texts = []
                    for cw1 in COUNT_WORDS[cnt1]:
                        for cw2 in COUNT_WORDS[cnt2]:
                            for ap1 in ap1_words:
                                par_texts.append(f"{ap1}{cn1}{cw1}次，同时{cn2}{cw2}次")
                                par_texts.append(f"一边{ap1}{cn1}{cw1}下一边{cn2}{cw2}下")
                    add_group(plan_par, par_texts, f"par_{t1}_{amp1}_{t2}")

    # 5. Negations -> none
    for g in [
        ["不要点头", "别点头", "千万别点头"],
        ["不要摇头", "别摇头", "别晃头"],
        ["不要眨眼", "别眨眼", "别闭眼"],
        ["什么都别做", "不要动", "保持不动", "别做任何动作"],
    ]:
        add_group(make_plan("none"), g, "negation_none")

    add_group(
        make_plan("execute", [{"actions": [{"type": "blink", "count": 1, "amplitude": "full", "speed": "normal"}]}]),
        ["不要点头，眨一下眼", "别点头，眨眼一次", "不要摇头，只眨一下眼"],
        "negation_plus_blink",
    )

    # 6. Physically impossible / out-of-range -> unsupported
    for g in [
        ["眨四次眼", "眨眼5次", "点头四次"],
        ["一直眨眼直到我喊停", "无限循环摇头", "不停地挥手"],
        ["后空翻", "飞起来", "变身成汽车"],
    ]:
        add_group(make_plan("unsupported"), g, "unsupported")

    return rows


def main():
    rows = build_corpus()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(rows)} seed samples across {len({r['group_id'] for r in rows})} groups -> {OUT_PATH}")


if __name__ == "__main__":
    main()
