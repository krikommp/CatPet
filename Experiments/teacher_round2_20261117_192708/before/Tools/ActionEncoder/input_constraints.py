"""Conservative execution guards for explicit action counts, times and cycle relations.

This is not a general language parser. It never repairs a model prediction. Explicit
numeric syntax outside the supported subset is reported as unresolved; colloquial
words such as 一边, 一点 and 一起 are not numeric requests. Dialogue bypasses this
instruction-only validator at the caller, but still uses the strict config decoder.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

POLICY_VERSION = "explicit-instruction-guard.v2"
NUMBER = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万点半]+)"
ORDINAL = re.compile(r"第(" + NUMBER + r")(?:次|下|遍)")
# Chinese words touch their number, so duration matching cannot use a word boundary.
DURATION = re.compile(r"(" + NUMBER + r")\s*(毫秒|秒钟|秒|ms|s)(?![a-z])", re.I)
ALIASES = {
    "blink.full": r"眨(?:眨)?眼|眨(?:" + NUMBER + r")[次下遍]眼|眨眼睛",
    "nod.basic": r"点(?:点)?头", "shake_head.basic": r"摇(?:摇)?头|晃脑袋",
    "tilt_head.basic": r"歪(?:歪)?头|歪脑袋",
    "look_around.basic": r"四处张望|东张西望|左右看|环顾四周|张望",
    "smile.basic": r"微笑|笑一笑|笑笑|浅笑|笑",
    "angry.basic": r"生气|鼓嘴", "shy.basic": r"害羞|不好意思",
    "surprise.basic": r"惊讶|吓一跳|吃惊", "wave.basic": r"挥(?:挥)?手|招(?:招)?手|摆手|打招呼",
    "cheer.basic": r"举手欢呼|欢呼|加油", "bow.basic": r"鞠躬|行礼",
}


def number_value(token):
    if token == "半":
        return Decimal("0.5")
    try:
        return Decimal(token)
    except InvalidOperation:
        digits = {c: i for i, c in enumerate("零一二三四五六七八九")}
        digits.update({"〇": 0, "两": 2})
        if "点" in token:
            left, right = token.split("点", 1)
            return number_value(left) + Decimal("0." + "".join(str(digits[x]) for x in right))
        if any(c not in digits and c not in "十百千万" for c in token):
            raise ValueError("unsupported number")
        if len(token) > 1 and all(c in digits for c in token):
            raise ValueError("ambiguous Chinese digit sequence")
        total = current = 0
        for c in token:
            if c in digits:
                current = digits[c]
            elif c in "十百千":
                total += (current or 1) * {"十": 10, "百": 100, "千": 1000}[c]
                current = 0
            else:
                raise ValueError("large number syntax is not supported")
        return Decimal(total + current)


def mentioned_resources(text):
    return [rid for rid, pattern in ALIASES.items() if re.search(pattern, text)]


def validate_instruction_constraints(text, config):
    result = {"policy": POLICY_VERSION, "checks": [], "violations": [], "unresolved": [],
              "coverage_is_partial": True, "no_silent_repair": True}
    if config.get("decision") != "execute":
        result["execution_constraints_applicable"] = False
        return result
    result["execution_constraints_applicable"] = True
    order = list(ALIASES)
    flat = [a for step in config.get("steps", []) for a in
            sorted(step["actions"], key=lambda a: order.index(a["resource_id"]))]
    by_rid = {}
    for i, action in enumerate(flat):
        by_rid.setdefault(action["resource_id"], []).append(i)
    covered = []
    requested_counts = {}

    def unresolved(kind, span):
        item = {"kind": kind, "span": span}
        if item not in result["unresolved"]:
            result["unresolved"].append(item)

    def check(kind, ai, passed, **kw):
        item = {"kind": kind, "action_index": ai, "passed": bool(passed), **kw}
        result["checks"].append(item)
        if not passed:
            result["violations"].append(item)

    def resolve(clause, prior=""):
        named = mentioned_resources(clause)
        if not named:
            named = mentioned_resources(prior)
        if len(named) == 1 and len(by_rid.get(named[0], [])) == 1:
            return by_rid[named[0]][0]
        return None

    def numeric(token, whole):
        try:
            return number_value(token)
        except (ValueError, KeyError, InvalidOperation):
            unresolved("unsupported_number", whole)
            return None

    # Count scope comes from the text, never from how many cycles the model emitted.
    for rid, alias in ALIASES.items():
        count_patterns = [r"(?:" + alias + r")\s*(" + NUMBER + r")[次下遍]"]
        if rid == "blink.full":
            count_patterns.append(r"眨(" + NUMBER + r")[次下遍]眼")
        for pattern in count_patterns:
            for m in re.finditer(pattern, text):
                covered.append(m.span())
                preceding_clause = re.split(r"[，,；;。]", text[:m.start()])[-1]
                following_clause = re.split(r"[，,；;。]", text[m.end():])[0]
                if re.search(r"不要|不许|不能|不得|禁止|别", preceding_clause):
                    unresolved("negated_action_count", m.group(0))
                    continue
                if re.search(r"大约|大概|差不多|约莫|至少|至多|最多|最少|不超过|不少于|不多于|约$", preceding_clause) or re.match(r"\s*(?:左右|上下|以上|以下|以内|以外|半|多|有余|(?:到|至)\s*" + NUMBER + r"|或|或者)", following_clause):
                    unresolved("unsupported_count_range_or_approximation", m.group(0))
                    continue
                expected = numeric(m.group(1), m.group(0))
                if expected is None:
                    continue
                if expected != expected.to_integral_value() or expected < 1:
                    unresolved("non_integer_action_count", m.group(0))
                    continue
                requested_counts.setdefault(rid, set()).add(int(expected))
                ids = by_rid.get(rid, [])
                if len(ids) != 1:
                    unresolved("count_action_scope", m.group(0))
                    continue
                # Repeated named actions may refer to separate steps; do not merge them.
                if len(list(re.finditer(pattern, text))) > 1:
                    unresolved("repeated_action_count_scope", m.group(0))
                    continue
                actual = len(flat[ids[0]]["cycles"])
                # A first event introduced by 先 is not a total count when the text
                # explicitly names later cycles of the SAME sole action. Never use
                # another action's ordinal or the model's cycle count to infer scope.
                later_ordinals = list(ORDINAL.finditer(text[m.end():]))
                if expected == 1 and "先" in preceding_clause and mentioned_resources(text) == [rid] and later_ordinals:
                    later = [numeric(x.group(1), x.group()) for x in later_ordinals]
                    if all(x is not None and x == x.to_integral_value() and x >= 2 for x in later):
                        minimum = int(max(later))
                        requested_counts[rid].discard(1)
                        check("referenced_cycle_exists", ids[0], actual >= minimum,
                              expected_minimum=minimum, actual=actual, span=m.group(0))
                        continue
                check("cycle_count", ids[0], actual == int(expected), expected=int(expected), actual=actual, span=m.group(0))

    clauses = list(re.finditer(r"[^，,；;。]+", text))
    for cm in clauses:
        clause = cm.group(); prior = text[:cm.start()]
        ordinals = list(ORDINAL.finditer(clause))
        duration_matches = list(DURATION.finditer(clause))
        for dm in duration_matches:
            covered.append((cm.start() + dm.start(), cm.start() + dm.end()))
            prefix = clause[:dm.start()]
            suffix = clause[dm.end():]
            if prefix.endswith(("-", "−")):
                unresolved("negative_duration", clause)
                continue
            if re.search(r"保持|停顿|闭眼|定格|间隔|等待|延迟|总共|总计|总时长|至少|至多|不超过|以内|以上|以下|到|至|分之|不要|不许|不能|不得|禁止|别", prefix):
                unresolved("unsupported_duration_field_or_range", clause)
                continue
            if re.search(r"大约|大概|差不多|约莫|最多|最少|不少于|不多于|约$", prefix) or re.match(r"\s*(?:左右|上下|以上|以下|以内|以外|半|多|有余|(?:到|至)\s*" + NUMBER + r"|或|或者)", suffix):
                unresolved("unsupported_duration_range_or_approximation", clause)
                continue
            ai = resolve(clause, prior)
            if ai is None:
                unresolved("duration_action_scope", clause)
                continue
            expected = numeric(dm.group(1), clause)
            if expected is None:
                continue
            expected *= 1 if dm.group(2).lower() in ("毫秒", "ms") else 1000
            if expected <= 0 or expected != expected.to_integral_value():
                unresolved("non_integral_millisecond_duration", clause)
                continue
            preceding = [m for m in ordinals if m.end() <= dm.start()]
            counts = requested_counts.get(flat[ai]["resource_id"], set())
            if preceding:
                ordinal_value = numeric(preceding[-1].group(1), clause)
                if ordinal_value is None or ordinal_value != ordinal_value.to_integral_value():
                    unresolved("duration_cycle_scope", clause); continue
                targets = [int(ordinal_value) - 1]
            elif re.search(r"每[次下遍]", prefix) and len(counts) == 1:
                targets = list(range(next(iter(counts))))
            elif counts == {1}:
                targets = [0]
            else:
                unresolved("duration_cycle_scope", clause); continue
            cycles = flat[ai]["cycles"]
            for ci in targets:
                actual = cycles[ci]["duration_ms"] if 0 <= ci < len(cycles) else None
                check("exact_duration_ms", ai, actual == expected, cycle_index=ci,
                      expected=int(expected), actual=actual, span=clause)

        if ordinals:
            for om in ordinals:
                covered.append((cm.start() + om.start(), cm.start() + om.end()))
            ai = resolve(clause, prior)
            # An ordinal is itself an explicit cycle reference. Marking its text as
            # consumed must not hide a missing cycle merely because the following
            # wording has no supported relation or duration rule.
            for om in ordinals:
                ordinal_value = numeric(om.group(1), clause)
                if ai is None or ordinal_value is None or ordinal_value != ordinal_value.to_integral_value() or ordinal_value < 1:
                    unresolved("ordinal_action_or_cycle_scope", clause)
                else:
                    check("referenced_cycle_exists", ai, int(ordinal_value) <= len(flat[ai]["cycles"]),
                          expected_minimum=int(ordinal_value), actual=len(flat[ai]["cycles"]), span=om.group())
            relations = [("duration_ms", "gt", r"慢|放慢"), ("duration_ms", "lt", r"快|加快"),
                         ("amplitude_scale", "gt", r"更重|重一点|快重|用力一点|更大|更深|更高|加大幅度|幅度大一点"),
                         ("amplitude_scale", "lt", r"更轻|轻一点|慢轻|更小|减小幅度|幅度小一点"),
                         ("hold_time_ms", "gt", r"停得更久|保持更久|闭眼更久|停顿更久")]
            found = [(field, op) for field, op, pattern in relations if re.search(pattern, clause)]
            if "比" in clause and len(ordinals) == 2:
                tail = clause[ordinals[-1].end():]
                for field, op, word in (("amplitude_scale", "gt", "重"), ("amplitude_scale", "lt", "轻"),
                                        ("duration_ms", "gt", "长"), ("duration_ms", "lt", "短")):
                    if word in tail and (field, op) not in found:
                        found.append((field, op))
            if found and re.search(r"不要|不许|不能|不得|别|不比|不更|不再|并非|一样|同样|也要|相同", clause):
                unresolved("negated_or_equal_cycle_relation", clause)
                continue
            if found:
                indices = [numeric(m.group(1), clause) for m in ordinals]
                if ai is None or any(x is None or x != x.to_integral_value() for x in indices):
                    unresolved("relative_action_or_cycle_scope", clause); continue
                ci = int(indices[0]) - 1
                if "比" in clause:
                    if len(indices) != 2 or clause.index("比") < ordinals[0].end():
                        unresolved("relative_reference_scope", clause); continue
                    ref = int(indices[1]) - 1
                elif len(indices) == 1:
                    ref = ci - 1
                else:
                    unresolved("relative_reference_scope", clause); continue
                # 第一次慢 is qualitative; it cannot imply a comparison with cycle zero.
                if ci == 0 and ref == -1:
                    continue
                cycles = flat[ai]["cycles"]
                for field, op in found:
                    def value(index):
                        if not 0 <= index < len(cycles): return None
                        c = cycles[index]
                        if field == "duration_ms": return c["duration_ms"]
                        if field == "hold_time_ms": return c["duration_ms"] * c["controls"]["hold_ratio"]
                        return c["controls"].get(field)
                    a, b = value(ci), value(ref)
                    check("relative", ai, a is not None and b is not None and (a > b if op == "gt" else a < b),
                          cycle_index=ci, reference_cycle_index=ref, field=field, op=op, actual=a, reference=b, span=clause)
            elif not duration_matches and re.search(r"比|幅度|倍|百分|%|％|一半|分之|周期|持续|用时|时长|做|动", clause):
                unresolved("unsupported_cycle_request", clause)

    # Explicit quantities that no supported rule consumed must not silently pass.
    markers = [r"\d+(?:\.\d+)?", NUMBER + r"(?:毫秒|秒钟|秒|分钟|分半|小时|赫兹|Hz|周期|次|遍|度|倍|%|％)",
               r"[二两三四五六七八九十百]+下", r"一半(?:的)?(?:幅度|速度|时长)", r"百分之" + NUMBER]
    for marker in markers:
        for m in re.finditer(marker, text):
            if not any(a <= m.start() and m.end() <= b for a, b in covered):
                unresolved("uncovered_explicit_quantity", m.group(0))
    gradual = [("duration_ms", "gt", r"越来越慢|逐渐放慢"), ("duration_ms", "lt", r"越来越快|逐渐加快"),
               ("amplitude_scale", "gt", r"越来越重|幅度越来越大"),
               ("amplitude_scale", "lt", r"越来越轻|幅度越来越小")]
    for field, op, pattern in gradual:
        if not re.search(pattern, text):
            continue
        ai = resolve(text)
        counts = requested_counts.get(flat[ai]["resource_id"], set()) if ai is not None else set()
        if ai is None or len(counts) != 1 or next(iter(counts)) < 2 or re.search(r"不要|不能|别|不再|并非", text):
            unresolved("unsupported_gradual_relation", text)
            continue
        cycles = flat[ai]["cycles"]
        for ci in range(1, len(cycles)):
            a = cycles[ci].get(field, cycles[ci]["controls"].get(field))
            b = cycles[ci - 1].get(field, cycles[ci - 1]["controls"].get(field))
            check("gradual_relative", ai, a is not None and b is not None and (a > b if op == "gt" else a < b),
                  cycle_index=ci, reference_cycle_index=ci - 1, field=field, op=op, actual=a, reference=b, span=text)
    if re.search(r"先[^，,；;。]{0,8}[快慢轻重][^，,；;。]{0,4}后[^，,；;。]{0,4}[快慢轻重]", text):
        unresolved("unsupported_ordered_quality_scope", text)
    result["passed_checked_constraints"] = not result["violations"] and not result["unresolved"]
    return result
