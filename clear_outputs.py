"""Clear saved outputs from previous runs.

Removes:
  - all saved plots under plots/
  - all logs directly under log/ (top level only)
  - all low-score logs under log/low_scores/
  - all high-score logs under log/high_scores/ (and log/max_score/ from older runs)
  - all json logs under json/
  - all evaluation pipeline runs under results/ (from evaluate.py)

Usage:
    python clear_outputs.py           # asks for confirmation
    python clear_outputs.py -y        # skips confirmation
    python clear_outputs.py --dry-run # shows what would be deleted
"""

import argparse
import os
import sys

# Resolve paths relative to this script's location (repo root)
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# (directory, recursive) pairs.
# log/ is non-recursive so we only remove files directly under it,
# then handle log/low_scores explicitly.
TARGETS = [
    (os.path.join(REPO_ROOT, "plots"), True),
    (os.path.join(REPO_ROOT, "log"), False),
    (os.path.join(REPO_ROOT, "log", "low_scores"), True),
    (os.path.join(REPO_ROOT, "log", "high_scores"), True),
    (os.path.join(REPO_ROOT, "log", "max_score"), True),
    (os.path.join(REPO_ROOT, "json"), True),
    (os.path.join(REPO_ROOT, "results"), True)
]


def collect_files(directory, recursive):
    """Return a list of file paths to delete in `directory`."""
    files = []
    if not os.path.isdir(directory):
        return files
    if recursive:
        for root, _, names in os.walk(directory):
            for name in names:
                if name == ".gitkeep":
                    continue
                files.append(os.path.join(root, name))
    else:
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isfile(path) and name != ".gitkeep":
                files.append(path)
    return files


def main():
    parser = argparse.ArgumentParser(description="Clear saved plots, logs, and json outputs.")
    parser.add_argument("-y", "--yes", action="store_true", help="delete without asking for confirmation")
    parser.add_argument("--dry-run", action="store_true", help="list files that would be deleted, but do not delete")
    args = parser.parse_args()

    to_delete = []
    for directory, recursive in TARGETS:
        found = collect_files(directory, recursive)
        to_delete.extend(found)
        rel = os.path.relpath(directory, REPO_ROOT)
        if os.path.isdir(directory):
            print(f"  {rel + '/':<20} {len(found)} file(s)")
        else:
            print(f"  {rel + '/':<20} (directory not found, skipping)")

    if not to_delete:
        print("\nNothing to delete.")
        return

    print(f"\nTotal: {len(to_delete)} file(s)")

    if args.dry_run:
        for path in to_delete:
            print(f"  would delete: {os.path.relpath(path, REPO_ROOT)}")
        return

    if not args.yes:
        answer = input("Delete these files? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return

    deleted = 0
    for path in to_delete:
        try:
            os.remove(path)
            deleted += 1
        except OSError as e:
            print(f"  failed to delete {path}: {e}", file=sys.stderr)

    # Remove the now-empty eval_<timestamp>/ folders under results/
    results_dir = os.path.join(REPO_ROOT, "results")
    if os.path.isdir(results_dir):
        for root, dirs, _ in os.walk(results_dir, topdown=False):
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))  # only succeeds if empty
                except OSError:
                    pass

    print(f"Deleted {deleted} file(s).")


if __name__ == "__main__":
    main()
