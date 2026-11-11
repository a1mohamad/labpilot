"""Check the timer against the independent clocks for a one_model_run result.

verify_clocks.py reads the raw file of measure_clocks.py. The raw file of
one_model_run.py has another shape, so this turns it into the first shape and
then runs the same checks. It needs one number that the timer's table prints
but does not save: the wall time. Type it with TWO decimals (367.57), because a
rounded wall time shows up as a gap of a few hundredths of a second.

    python -m scripts.verify_one_model OUT_PREFIX WALL_SECONDS
"""

import json
import sys

from scripts.verify_clocks import check

raw = json.load(open(sys.argv[1] + "_raw.json"))
wall = float(sys.argv[2])  # the wall seconds the timer's table printed
ask = {
    "kind": "first",
    "outside_start": raw["outside_start"],
    "outside_end": raw["outside_end"],
    "outside_seconds": raw["outside_seconds"],
    "timer_wall": wall,
    "http": [0, len(raw["http"])],
    "calls": [0, len(raw["calls"])],
    "records": raw["records"],
}
json.dump(
    {"http": raw["http"], "calls": raw["calls"], "asks": [ask]},
    open(sys.argv[1] + "_v_raw.json", "w"),
)
check(sys.argv[1] + "_v")
