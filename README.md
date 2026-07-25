# Threshold Stress-Test: Emotional-Memory Retention

A calibration artifact from Valoquent's local test lab. Valoquent characters remember emotionally significant moments across sessions, and a threshold decides which moments persist permanently. This script stress-tests that threshold at three settings against a full simulated-conversation battery and reports what breaks at each one.

## What It Does

1. Classifies every user message from a saved battery run through the emotion classifier.
2. Sweeps three threshold configurations (loose, production, tight) and buckets each emotional moment into permanent, mid, or low retention.
3. Saves the borderline moments within 0.05 of the permanent cutoff, with their text, to the results file so a person can review the decisions at the boundary.
4. Lists the moments each direction would move: those loose would promote to permanent, and those tight would drop to mid. A person reading them judges which are noise and which are genuine.
5. Reports per-archetype emotional signal rates as a behavioral sanity check, then prints the change at each setting with two automatic red flags: any emotion category completely excluded at tight, and any category that doubles, or enters permanent for the first time, at loose.

## What the Sweep Found

The battery holds 48 conversations of four sessions each, pairing six historical figures with eight user archetypes that run from curious student to intellectual troll. Of its 1,711 user messages, 220 carry an emotion the classifier recognizes.

| Setting | Permanent cutoff | Permanent moments |
|---|---|---|
| Loose | 0.65 | 193 |
| Production | 0.70 | 174 |
| Tight | 0.75 | 128 |

Tight removes curiosity, joy and gratitude from permanent memory entirely and keeps connection, vulnerability and wonder. Loose adds 19 moments and doubles joy. The mid floor has no effect at any setting: every recognized emotion scores 0.53 or higher (0.62 or higher on this battery), above all three floors, so the low tier stays empty. Each keyword carries a fixed score, so shifting the cutoff trades whole keywords in or out of permanent memory.

The full console output and results file from the run are in [`sample-output/`](sample-output/).

## Context

The battery simulates multi-session conversations between user archetypes and Valoquent's historical figures, generated with local models: mistral-small plays the figures and llama3.2:3b plays the simulated users. The classifier matches keywords, so the sweep is deterministic and a rerun against the same battery reproduces these counts exactly.

## Known Limits

The script classifies every user message. Production stores a moment only when the message carries one of the app's emotional trigger phrases, and it stores a triggered message the classifier can't label at 0.5, marked unclassified. Production's population is smaller: 54 permanent moments at the production setting against 174 here. The finding holds there too, with tight still removing curiosity and joy entirely and loose adding 4.

Production also keeps only the newest 15 mid and 5 low moments per conversation. The sweep counts across the whole battery and leaves those caps out; no conversation in this battery reaches them (the most is 9).

Shared as a work sample. It is not runnable standalone: it imports the app's private `character_memory` module and reads saved battery transcripts, neither of which is included here.
