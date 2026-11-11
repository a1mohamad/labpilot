"""Does the timer agree with the independent clocks of measure_clocks.py?

The rules are about INTERVALS that must nest, not about equal numbers, because
the timer and the HTTP clock measure different boundaries:

  V1 outside stopwatch >= the timer's wall, and the gap is small
  V2 every timer step lies inside the outside stopwatch interval
  V3 every HTTP request lies inside some step (nothing hides between steps)
  V4 for every model call: the HTTP requests of the same thread lie inside the
     call's window; the call's END is close to the end of its last request
     (tail), and its START may be earlier by a wait (lead) - a retry delay or a
     pacing sleep is real time that the call includes on purpose
  V5 the timer's own call end (time.time) is close to my wrapper's end (perf_counter)
  V6 for a step that makes ONE call: step >= call, and the difference is the
     step's own work (building a prompt)
  V7 the chain of steps plus the gaps before and after adds up to the wall
"""

import json
import statistics
import sys

TOL = 0.05


def inside(inner, outer, tol=TOL):
    return inner[0] >= outer[0] - tol and inner[1] <= outer[1] + tol


def check(prefix):
    raw = json.load(open(f"{prefix}_raw.json"))
    http, mycalls = raw["http"], raw["calls"]
    bad = []
    print(f"\n######## {prefix}")
    for ask in raw["asks"]:
        steps = [r for r in ask["records"] if r["kind"] == "step"]
        tcalls = [r for r in ask["records"] if r["kind"] == "call"]
        h = http[ask["http"][0] : ask["http"][1]]
        c = mycalls[ask["calls"][0] : ask["calls"][1]]
        out = (ask["outside_start"], ask["outside_end"])
        label = ask["kind"]
        print(
            f"\n== {label}: outside {ask['outside_seconds']:.2f} s, "
            f"timer wall {ask['timer_wall']:.2f} s, {len(steps)} step lines, "
            f"{len(tcalls)} call lines, {len(h)} HTTP requests"
        )

        gap = ask["outside_seconds"] - ask["timer_wall"]
        ok = -0.01 <= gap < 0.2
        print(f"V1 outside - timer wall = {gap:+.3f} s  {'ok' if ok else 'BAD'}")
        if not ok:
            bad.append((label, "V1", gap))

        out_steps = [s for s in steps if not inside((s["start"], s["end"]), out)]
        print(f"V2 steps outside the outside interval: {len(out_steps)}")
        bad += [(label, "V2", s["name"]) for s in out_steps]

        loose = [
            r
            for r in h
            if not any(
                inside((r["start"], r["end"]), (s["start"], s["end"])) for s in steps
            )
        ]
        print(
            f"V3 HTTP requests not inside any step: {len(loose)}"
            + (f"  hosts {sorted({r['host'] for r in loose})}" if loose else "")
        )
        bad += [(label, "V3", r["host"]) for r in loose]

        tails, leads, empties = [], [], []
        for call in c:
            window = (call["end"] - call["seconds"], call["end"])
            mine = [
                r
                for r in h
                if r["thread"] == call["thread"]
                and inside((r["start"], r["end"]), window)
            ]
            if not mine:
                empties.append(call)
                continue
            tails.append(window[1] - max(r["end"] for r in mine))
            leads.append(min(r["start"] for r in mine) - window[0])
        answered = [x for x in c if x["tier"] is not None]
        print(
            f"V4 calls {len(c)} (answered {len(answered)}), with no HTTP request "
            f"inside: {len(empties)}"
        )
        if tails:
            print(
                f"   tail (call end - last request end): median "
                f"{statistics.median(tails):.3f} max {max(tails):.3f} s; "
                f"negative: {sum(t < -TOL for t in tails)}"
            )
            print(
                f"   lead (first request - call start, = waits): median "
                f"{statistics.median(leads):.3f} max {max(leads):.1f} s; "
                f"over 1 s: {sum(x > 1 for x in leads)}"
            )
        bad += [(label, "V4-neg-tail", t) for t in tails if t < -TOL]
        for call in empties:
            if call["tier"] is not None:
                bad.append((label, "V4-answered-no-http", call["seconds"]))

        # V5: the timer's call end vs my wrapper's end, matched by order of end time
        a = sorted(x["end"] for x in tcalls)
        b = sorted(x["end"] for x in c)
        if len(a) == len(b) and a:
            d = max(abs(x - y) for x, y in zip(a, b, strict=True))
            print(
                f"V5 timer call ends vs mine: max difference {d:.3f} s  "
                f"{'ok' if d < 0.1 else 'BAD'}"
            )
            if d >= 0.1:
                bad.append((label, "V5", d))
        else:
            print(f"V5 call counts differ: timer {len(a)} mine {len(b)}  BAD")
            bad.append((label, "V5-count", (len(a), len(b))))

        # V6: steps with exactly one call
        for s in steps:
            inside_calls = [
                x
                for x in tcalls
                if x["step"] == s["name"]
                and s["start"] - TOL <= x["end"] - x["seconds"]
                and x["end"] <= s["end"] + TOL
            ]
            if len(inside_calls) == 1 and s["name"] in {
                "respond",
                "gate",
                "rewrite",
                "plan",
            }:
                x = inside_calls[0]
                diff = s["seconds"] - x["seconds"]
                print(
                    f"V6 {s['name']}: step {s['seconds']:.2f} s, its call "
                    f"{x['seconds']:.2f} s, own work {diff:.2f} s "
                    f"{'ok' if diff >= -TOL else 'BAD'}"
                )
                if diff < -TOL:
                    bad.append((label, "V6", s["name"]))

        # V7
        first = min(s["start"] for s in steps)
        last = max(s["end"] for s in steps)
        print(
            f"V7 before graph {first - ask['outside_start']:.2f} s, graph span "
            f"{last - first:.2f} s, after {ask['outside_end'] - last:.2f} s "
            f"(sum {ask['outside_seconds']:.2f})"
        )
    print("\nPROBLEMS:", bad if bad else "none")
    return bad


if __name__ == "__main__":
    for prefix in sys.argv[1:]:
        check(prefix)
