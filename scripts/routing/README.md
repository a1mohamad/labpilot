# scripts/routing - keep the routes up to date

The routes of `labpilot/llm/routes.py` are computed from two tables that these
scripts write: `labpilot/llm/ratings.py` (one row per tier: strength, seconds,
calls a day) and `labpilot/llm/accuracy.py` (how well each model did each task).
Free models change every week, so the tables must be measured again.

Run every script from the repository root, with the virtual environment active.
They write only under `artifacts/routing-bench/` (git-ignored), except a script
run with `--apply`, which copies its proposed table into `labpilot/llm/`.

| script | what it does | quota |
|---|---|---|
| `free_lists.py` | each gateway's free list against the chain: GONE, BACK, NEW | none |
| `speed_check.py` | availability, speed and trust of every live tier | about 80 calls (`--quick`), more without |
| `write_ratings.py` | proposes `ratings.py` from the speed logs | none |
| `collect_data.py` | gathers the labelled cases of the bench into one folder (once) | none |
| `bench.py` | accuracy of every model on every task, rounds `r1` and `r2` | about 1,300 calls for round 1 |
| `analyze_bench.py` | the accuracy table, the round 2 plan, proposes `accuracy.py` | none |
| `compare_routes.py` | how the first models of each route would change | none |

## Every week (availability and speed)

```
python -m scripts.routing.free_lists
python -m scripts.routing.speed_check --quick
python -m scripts.routing.write_ratings
python -m scripts.routing.compare_routes
```

Read the GONE and NEW lists and the route changes. If they look right:

```
python -m scripts.routing.write_ratings --apply
python -m pytest tests/unit/llm -q
```

A tier with no valid answer in the speed check is NOT moved to `KNOWN_DEAD`
by any script: probe it again on another day, then move it by hand (a free
model can come back). A NEW model needs a tier in `registry.py` and a family
in `write_ratings.py` before it can have a rating.

To save quota, run the quick check on all tiers every week and the full check
(`speed_check.py` without `--quick`) every two weeks, or on a new tier only:
`speed_check.py --only "Model name"`.

## When a model, a prompt or a task changes (accuracy)

```
python -m scripts.routing.collect_data        # once, or when a study folder changes
python -m scripts.routing.bench r1 all
python -m scripts.routing.analyze_bench plan
python -m scripts.routing.bench r2 all
python -m scripts.routing.analyze_bench table
python -m scripts.routing.analyze_bench write
python -m scripts.routing.compare_routes
python -m scripts.routing.analyze_bench write --apply
```

A new model only: `bench.py r1 all all "Model family"`, after adding it to `F`
in `bench.py`. Results already in the log are not measured again; delete the
lines of a model to measure it again (for example after a prompt change).

Rules that keep the numbers honest:

- every script that calls a model checks the network first (the exit ISP and a
  Google probe) and stops when Google does not answer 200;
- a call refused for quota counts neither as right nor as wrong;
- a score rests on few cases: a result on 1 or 2 cases is pulled toward the
  guess from the model's strength in `routes.accuracy`;
- the answer keys were written before any model was scored. Never change a key
  after reading a result; add new cases instead;
- review the first 3 models of each task (`compare_routes.py`) before `--apply`.

## Later: a scheduled job

Each command above is one step a scheduler (Airflow, or a GitHub workflow) can
run: `free_lists` and `speed_check --quick` weekly, then `write_ratings`, then
`compare_routes`, and a person reviews the change before `--apply` (or the job
opens a pull request with the new `ratings.py`, never a commit on `main`).
