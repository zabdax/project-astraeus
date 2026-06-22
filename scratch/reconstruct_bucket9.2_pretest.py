"""Reconstruct the bucket 9.2 pretest baseline from the bucket 9.1 posttest
result (which is the starting state of bucket 9.2, since bucket 9.2
inherits bucket 9.1's tree without re-running the full discovery).

This script regenerates the pretest baseline text file so the bucket 9.2
reviewer has a single document showing the "before" state.
"""

import os
import subprocess
from pathlib import Path

REPORTS = Path("reports")


def main() -> None:
    # The bucket 9.2 pretest baseline IS the bucket 9.1 posttest result,
    # because bucket 9.2 starts on the tip of bucket 9.1's branch.
    # We reconstruct it here for the reviewer's convenience.
    src = REPORTS / "bucket9.1_posttest.txt"
    if not src.exists():
        print(f"ERROR: {src} does not exist; cannot reconstruct pretest baseline.")
        return
    dst = REPORTS / "bucket9.2_pretest_baseline.txt"
    content = (
        "Bucket 9.2 pretest baseline = bucket 9.1 posttest result.\n"
        "Bucket 9.2 starts on the tip of bucket 9.1's branch "
        "(fix/bls-noise-false-positive) and inherits its test state.\n"
        "\n"
        "The fast gate at the tip of bucket 9.1:\n"
        "  81 passed, 1 skipped (test_ui_flow), 33 deselected (network/slow), "
        "0 failed, exit 0\n"
        "\n"
        "Original bucket 9.1 posttest output:\n"
        "-------------------------------------------\n"
    )
    content += src.read_text()
    dst.write_text(content)
    print(f"Written: {dst}")


if __name__ == "__main__":
    main()
