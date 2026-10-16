"""``knowhow vlm sweep`` — describe a video at several fps and score it against a truth file.

Spec 04 §6 (T04-6). Matching is the pass-B rule: ``rapidfuzz.token_set_ratio(step) >= 70`` AND a
time overlap > 0, one truth step per predicted step (greedy, best score first). Metrics:

* ``recall``          matched truth / all truth           (1 − missed rate)
* ``precision``       matched predictions / all predictions (1 − hallucination rate)
* ``order_accuracy``  normalised Kendall tau of the matched pairs, (tau + 1) / 2
* ``key_point_recall`` truth steps with a key_point whose match's ``key_point_observed`` matches
  (``token_set_ratio >= 70``); empty when no truth step has a key_point
* ``tokens_used``, ``latency_s`` of the whole run at that fps
"""

from mentormind.processing.vlm.sweep.matching import (
    MATCH_THRESHOLD,
    Match,
    match_steps,
    overlaps,
    similarity,
)
from mentormind.processing.vlm.sweep.metrics import (
    SweepRow,
    actor_accuracy,
    evaluate,
    key_point_recall,
    order_accuracy,
)
from mentormind.processing.vlm.sweep.report import CSV_COLUMNS, markdown_table, write_csv
from mentormind.processing.vlm.sweep.runner import run_sweep
from mentormind.processing.vlm.sweep.truth import TruthStep, load_truth

__all__ = [
    "CSV_COLUMNS",
    "MATCH_THRESHOLD",
    "Match",
    "SweepRow",
    "TruthStep",
    "actor_accuracy",
    "evaluate",
    "key_point_recall",
    "load_truth",
    "markdown_table",
    "match_steps",
    "order_accuracy",
    "overlaps",
    "run_sweep",
    "similarity",
    "write_csv",
]
