"""Extract presentation values from existing evidence without rerunning workloads."""
import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = ROOT / "experiments/hnsw_build/results"
sources = {}


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


memory = []
for budget, label in [(1024, "low"), (1792, "high")]:
    paths = sorted(RESULTS.glob(f"20260909*-glove-formal-{label}-r*/summary.json"))
    assert len(paths) == 3
    runs = [read(p) for p in paths]
    times = [r["build_elapsed_seconds"] for r in runs]
    memory.append({
        "budget_mb": budget,
        "times_s": times,
        "median_s": median(times),
        "min_s": min(times), "max_s": max(times),
        "spill_count": sum(r["internal_timing"]["records"][0]["spill"] for r in runs),
        "peak_mib_median": median(r["peak_container_memory_bytes"] / 2**20 for r in runs),
    })
example = read(RESULTS / "20260909T140726Z-glove-formal-low-r1/summary.json")
record = example["internal_timing"]["records"][0]
recall = read(RESULTS / "20260910T074253Z-bounded-recall/summary.json")
formal = read(RESULTS / "20260912T174623Z-bounded-crossover-formal/summary.json")
cpu = read(ROOT / "dev/cpu_calibration/results/20260913T030031Z-ce171210b519/summary.json")
groups = [{
    "workers": g["workers"], "spill": g["spill"], "condition": g["condition"],
    "median_change": g["median_change_percent"],
    "upper_change": (g["upper"]["ratio"] - 1) * 100,
    "verdict": g["verdict"], "panels": g["panels"],
} for g in formal["analysis"]["groups"]]
assert len(formal["rows"]) == 768 and len(formal["warmups"]) == 384
assert len(groups) == 12 and sum(g["verdict"] == "supported" for g in groups) == 9
data = {
    "as_of": "2026-09-13", "memory": memory,
    "memory_reduction_percent": (1 - memory[1]["median_s"] / memory[0]["median_s"]) * 100,
    "example": {
        "phase_seconds": {k: v / 1e6 for k, v in record["durations_us"].items()},
        "total_s": record["total_us"] / 1e6,
        "command_s": example["build_elapsed_seconds"],
        "disk_fraction": example["internal_timing"]["dominant_fraction"],
    },
    "recall": [r for r in recall["evaluation"]["validation"]["by_ef_search"]
               if r["ef_search"] in (400, 1000)],
    "formal": {"measurements": 768, "warmups": 384, "groups": groups},
    "cpu": cpu["descriptive"]["outer_wall_s"],
    "source_sha256": sources,
}
(HERE / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print("Extracted 6 memory runs, 2 recall rows, 12 performance comparisons and CPU calibration.")
