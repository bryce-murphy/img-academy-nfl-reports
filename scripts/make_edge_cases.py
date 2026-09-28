"""Write tests/fixtures/pbp_edge_cases.csv: one real 2026 play per diagram edge case (network)."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data import PLAY_COLUMNS, load_sources  # noqa: E402
CASES = {
    "interception": lambda r: r["interception"] == "1",
    "lost_fumble": lambda r: r["fumble_lost"] == "1",
    "lateral": lambda r: "1" in (r["lateral_reception"], r["lateral_rush"]),
    "penalty": lambda r: r["penalty"] == "1" and r["play_type"] != "no_play",
    "goal_line_td": lambda r: r["touchdown"] == "1" and r["rush_attempt"] == "1" and r["yardline_100"] in ("1", "2", "3"),
    "sack": lambda r: r["sack"] == "1",
    "completion": lambda r: r["complete_pass"] == "1" and r["air_yards"] not in ("", "NA") and r["fumble"] == "0",
    "incompletion": lambda r: r["pass_attempt"] == "1" and r["complete_pass"] == "0" and r["interception"] == "0" and r["sack"] == "0",
    "run_loss": lambda r: r["rush_attempt"] == "1" and r["yards_gained"].startswith("-") and r["fumble"] == "0",
    "kneel": lambda r: r["qb_kneel"] == "1",
    "two_point": lambda r: r["two_point_attempt"] == "1",
    "punt": lambda r: r["play_type"] == "punt",
}


def main():
    data, _, _ = load_sources(2026, ROOT / ".cache", historical=True, only={"pbp"})
    rows = []
    for case, test in CASES.items():
        match = next((r for r in data["pbp"] if test(r)), None)
        if match is None:
            raise SystemExit(f"No 2026 play found for {case}")
        rows.append({"case": case, **match})
    columns = ["case", "game_id", "play_id", "week", "desc", "epa", "play_type", "touchdown", "fumble_lost", *PLAY_COLUMNS]
    with (ROOT / "tests" / "fixtures" / "pbp_edge_cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} edge cases")


if __name__ == "__main__":
    main()
