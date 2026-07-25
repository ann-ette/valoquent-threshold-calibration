#!/usr/bin/env python3
"""
CAL-026-C09: Intensity Threshold Stress-Test
=============================================
Runs emotional content from existing test transcripts through the emotion
classifier at three threshold settings to find where retention breaks down.

Thresholds tested:
  - Loose:   permanent ≥ 0.65, mid ≥ 0.35
  - Current: permanent ≥ 0.70, mid ≥ 0.40  (production values)
  - Tight:   permanent ≥ 0.75, mid ≥ 0.45

For each threshold setting, reports:
  - How many moments are classified per emotion category
  - How many reach permanent vs. mid vs. low retention
  - Which specific moments are borderline (±0.05 of the permanent threshold)
  - Which moments tight settings would drop from permanent
  - Which moments loose settings would promote to permanent

Input: a saved full-battery test run (results/test-run-*.json; pass a path
       to use another run)
Output: CAL-026-C09-results.json in results/
"""

import json
import sys
import time
from pathlib import Path
from collections import Counter, defaultdict

# Import from the agent directory
script_dir = Path(__file__).parent
agent_dir = script_dir.parent / "agent"

if not (agent_dir / "character_memory.py").exists():
    print("ERROR: Cannot find agent directory with character_memory.py")
    sys.exit(1)

sys.path.insert(0, str(agent_dir))
from character_memory import _classify_emotion, _EMOTION_VOCABULARY

# ---------------------------------------------------------------------------
# Load test data
# ---------------------------------------------------------------------------

results_dir = script_dir / "results"
test_run_path = (Path(sys.argv[1]) if len(sys.argv) > 1
                 else results_dir / "test-run-1774490444.json")

if not test_run_path.exists():
    print(f"ERROR: Test run not found at {test_run_path}")
    sys.exit(1)

with open(test_run_path) as f:
    test_data = json.load(f)

# Extract all user messages with context
all_messages = []
for result in test_data["results"]:
    character = result["character"]
    archetype = result["archetype"]
    for turn in result["turns"]:
        msg = turn.get("user_message", "")
        if msg:
            all_messages.append({
                "text": msg,
                "character": character,
                "archetype": archetype,
                "score": turn.get("score", 0),
                "zone": turn.get("zone", ""),
                "depth": turn.get("features", {}).get("depth", ""),
                "session": turn.get("session", 0),
                "turn": turn.get("turn", 0),
            })

print(f"Loaded {len(all_messages)} user messages from {test_run_path.stem}")
print()

# ---------------------------------------------------------------------------
# Classify all messages
# ---------------------------------------------------------------------------

print("=" * 70)
print("PHASE 1: Classify all messages with current classifier")
print("=" * 70)

classified = []
for msg_info in all_messages:
    emotion, intensity = _classify_emotion(msg_info["text"])
    classified.append({
        **msg_info,
        "emotion": emotion,
        "intensity": intensity,
    })

# Report classification distribution
emotion_counts = Counter(c["emotion"] for c in classified)
total_classified = sum(v for k, v in emotion_counts.items() if k != "unclassified")
total_unclassified = emotion_counts.get("unclassified", 0)

print(f"\nClassification rate: {total_classified}/{len(classified)} "
      f"({100*total_classified/len(classified):.1f}%)")
print(f"Unclassified: {total_unclassified}")
print()

print("Emotion distribution:")
for emotion, count in sorted(emotion_counts.items(), key=lambda x: -x[1]):
    if emotion == "unclassified":
        continue
    intensities = [c["intensity"] for c in classified if c["emotion"] == emotion]
    avg_i = sum(intensities) / len(intensities) if intensities else 0
    min_i = min(intensities) if intensities else 0
    max_i = max(intensities) if intensities else 0
    print(f"  {emotion:15s}: {count:3d} hits  "
          f"intensity avg={avg_i:.2f} range=[{min_i:.2f}–{max_i:.2f}]")

# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("PHASE 2: Threshold Sweep")
print("=" * 70)

# mid_cap and low_cap record production's per-conversation caps (newest 15 mid,
# newest 5 low). The sweep counts across the whole battery, so they are not applied.
threshold_configs = {
    "loose":   {"permanent": 0.65, "mid_floor": 0.35, "mid_cap": 15, "low_cap": 5},
    "current": {"permanent": 0.70, "mid_floor": 0.40, "mid_cap": 15, "low_cap": 5},
    "tight":   {"permanent": 0.75, "mid_floor": 0.45, "mid_cap": 15, "low_cap": 5},
}
loose_t = threshold_configs["loose"]["permanent"]
current_t = threshold_configs["current"]["permanent"]
tight_t = threshold_configs["tight"]["permanent"]

# Only look at classified (non-unclassified) messages
emotional_messages = [c for c in classified if c["emotion"] != "unclassified"]

sweep_results = {}

for config_name, thresholds in threshold_configs.items():
    perm_thresh = thresholds["permanent"]
    mid_floor = thresholds["mid_floor"]

    permanent = [m for m in emotional_messages if m["intensity"] >= perm_thresh]
    mid = [m for m in emotional_messages if mid_floor <= m["intensity"] < perm_thresh]
    low = [m for m in emotional_messages if m["intensity"] < mid_floor]

    # Per-emotion breakdown
    perm_by_emotion = Counter(m["emotion"] for m in permanent)
    mid_by_emotion = Counter(m["emotion"] for m in mid)
    low_by_emotion = Counter(m["emotion"] for m in low)

    # Borderline moments (within ±0.05 of permanent threshold)
    borderline_high = [m for m in emotional_messages
                       if perm_thresh - 0.05 <= m["intensity"] < perm_thresh]
    borderline_low = [m for m in emotional_messages
                      if perm_thresh <= m["intensity"] < perm_thresh + 0.05]

    sweep_results[config_name] = {
        "thresholds": thresholds,
        "permanent_count": len(permanent),
        "mid_count": len(mid),
        "low_count": len(low),
        "permanent_by_emotion": dict(perm_by_emotion),
        "mid_by_emotion": dict(mid_by_emotion),
        "low_by_emotion": dict(low_by_emotion),
        "borderline_just_below": len(borderline_high),
        "borderline_just_above": len(borderline_low),
        "borderline_below_samples": [
            {"text": m["text"][:100], "emotion": m["emotion"],
             "intensity": m["intensity"], "archetype": m["archetype"]}
            for m in sorted(borderline_high, key=lambda x: -x["intensity"])[:10]
        ],
        "borderline_above_samples": [
            {"text": m["text"][:100], "emotion": m["emotion"],
             "intensity": m["intensity"], "archetype": m["archetype"]}
            for m in sorted(borderline_low, key=lambda x: x["intensity"])[:10]
        ],
    }

    print(f"\n--- {config_name.upper()} (permanent ≥ {perm_thresh}, mid ≥ {mid_floor}) ---")
    print(f"  Permanent: {len(permanent):3d} moments")
    print(f"  Mid-range: {len(mid):3d} moments")
    print(f"  Low:       {len(low):3d} moments")
    print(f"  Borderline (±0.05 of {perm_thresh}): "
          f"{len(borderline_high)} just below, {len(borderline_low)} just above")

    print(f"\n  Permanent by emotion:")
    for emotion in sorted(_EMOTION_VOCABULARY.keys()):
        count = perm_by_emotion.get(emotion, 0)
        base = _EMOTION_VOCABULARY[emotion]["base_intensity"]
        indicator = "●" if count > 0 else "○"
        print(f"    {indicator} {emotion:15s}: {count:3d}  (base={base})")

# ---------------------------------------------------------------------------
# Phase 3: Failure mode analysis
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("PHASE 3: Failure Mode Analysis")
print("=" * 70)

# At LOOSE: what noise gets promoted to permanent?
loose_only_permanent = [m for m in emotional_messages
                        if loose_t <= m["intensity"] < current_t]
print(f"\n--- LOOSE promotes {len(loose_only_permanent)} extra moments to permanent ---")
if loose_only_permanent:
    print(f"  Samples (would be permanent at {loose_t:.2f} but not at {current_t:.2f}):")
    for m in sorted(loose_only_permanent, key=lambda x: x["intensity"])[:8]:
        print(f"    [{m['emotion']:13s} {m['intensity']:.2f}] \"{m['text'][:70]}...\"")

# At TIGHT: what significant moments get dropped from permanent?
tight_dropped = [m for m in emotional_messages
                 if current_t <= m["intensity"] < tight_t]
print(f"\n--- TIGHT drops {len(tight_dropped)} moments from permanent ---")
if tight_dropped:
    print(f"  Samples (permanent at {current_t:.2f} but dropped to mid at {tight_t:.2f}):")
    for m in sorted(tight_dropped, key=lambda x: -x["intensity"])[:8]:
        print(f"    [{m['emotion']:13s} {m['intensity']:.2f}] \"{m['text'][:70]}...\"")

# ---------------------------------------------------------------------------
# Phase 4: Per-archetype analysis
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("PHASE 4: Per-Archetype Emotional Signal Rate")
print("=" * 70)

archetype_stats = defaultdict(lambda: {"total": 0, "emotional": 0, "permanent_current": 0})
for c in classified:
    arch = c["archetype"]
    archetype_stats[arch]["total"] += 1
    if c["emotion"] != "unclassified":
        archetype_stats[arch]["emotional"] += 1
        if c["intensity"] >= current_t:
            archetype_stats[arch]["permanent_current"] += 1

print(f"\n{'Archetype':<25s} {'Total':>6s} {'Emotional':>10s} {'Rate':>6s} {'Permanent':>10s}")
print("-" * 60)
for arch in sorted(archetype_stats.keys()):
    s = archetype_stats[arch]
    rate = 100 * s["emotional"] / s["total"] if s["total"] else 0
    print(f"  {arch:<23s} {s['total']:>6d} {s['emotional']:>10d} {rate:>5.1f}% {s['permanent_current']:>10d}")

# ---------------------------------------------------------------------------
# Phase 5: Recommendation
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("PHASE 5: Summary and Red Flags")
print("=" * 70)

# Calculate key metrics for the summary
current = sweep_results["current"]
loose = sweep_results["loose"]
tight = sweep_results["tight"]

loose_gain_rate = (loose["permanent_count"] - current["permanent_count"]) / max(1, current["permanent_count"]) * 100
tight_drop_rate = (current["permanent_count"] - tight["permanent_count"]) / max(1, current["permanent_count"]) * 100

print(f"\n  Current ({current_t:.2f}): {current['permanent_count']} permanent moments")
print(f"  Loose ({loose_t:.2f}):   {loose['permanent_count'] - current['permanent_count']} more permanent "
      f"({loose_gain_rate:+.1f}% change)")
print(f"  Tight ({tight_t:.2f}):   {current['permanent_count'] - tight['permanent_count']} fewer permanent "
      f"({-tight_drop_rate:.1f}% change)")

# Check if any emotion category gets completely excluded at tight
excluded_at_tight = [e for e in _EMOTION_VOCABULARY
                     if tight["permanent_by_emotion"].get(e, 0) == 0
                     and current["permanent_by_emotion"].get(e, 0) > 0]
if excluded_at_tight:
    print(f"\n  ⚠ TIGHT would completely exclude these from permanent: {', '.join(excluded_at_tight)}")

# Check if any emotion doubles, or enters permanent for the first time, at loose
for emotion in _EMOTION_VOCABULARY:
    loose_perm = loose["permanent_by_emotion"].get(emotion, 0)
    current_perm = current["permanent_by_emotion"].get(emotion, 0)
    if current_perm == 0 and loose_perm > 0:
        print(f"\n  ⚠ LOOSE would admit {emotion} to permanent for the first time "
              f"(0 → {loose_perm})")
    elif current_perm > 0 and loose_perm >= current_perm * 2:
        print(f"\n  ⚠ LOOSE would double {emotion} permanent moments "
              f"({current_perm} → {loose_perm})")

# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------

output = {
    "test_name": "CAL-026-C09",
    "description": "Intensity threshold stress-test",
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "input_test_run": test_run_path.stem,
    "total_messages": len(all_messages),
    "total_emotional": len(emotional_messages),
    "classification_rate": round(100 * total_classified / len(classified), 1),
    "emotion_distribution": {
        emotion: {
            "count": count,
            "avg_intensity": round(
                sum(c["intensity"] for c in classified if c["emotion"] == emotion) / count, 3
            ) if count > 0 else 0,
        }
        for emotion, count in emotion_counts.items()
    },
    "threshold_sweep": sweep_results,
    "archetype_stats": {k: dict(v) for k, v in archetype_stats.items()},
    "recommendation": {
        "current_permanent": current["permanent_count"],
        "loose_delta": loose["permanent_count"] - current["permanent_count"],
        "tight_delta": tight["permanent_count"] - current["permanent_count"],
        "excluded_at_tight": excluded_at_tight,
    },
    "base_intensities": {e: v["base_intensity"] for e, v in _EMOTION_VOCABULARY.items()},
}

output_path = results_dir / "CAL-026-C09-results.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"\n\nResults saved to: {output_path.relative_to(script_dir)}")
print("Done.")
