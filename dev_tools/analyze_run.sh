#!/usr/bin/env bash
# Run every log_analyzer command on a single simulation run (all its games),
# optionally only on the games whose final score is in [a, b].
# Usage (from the repo root):
#   bash dev_tools/analyze_run.sh <timestamp> [a b]
#   e.g.  bash dev_tools/analyze_run.sh 20261007_180731          # all games
#         bash dev_tools/analyze_run.sh 20261007_180731 10 15    # games scoring 10..15
# The timestamp is the suffix of the log names, e.g. 3p0135_20261007_180731.txt
set -e
R=$1
A=${2:-0}
B=${3:-25}
if [ -z "$R" ] || [ $# -eq 2 ]; then
    echo "usage: $0 <timestamp> [a b]"; exit 1
fi
D=/tmp/run_${R}_${A}-${B}

# Copy one game (its .txt log and matching .json log) if its score is in [A, B].
# The .txt log keeps its low_scores/ or high_scores/ subfolder.
copy_if_in_range() {
    local txt=$1 subdir=$2
    local score
    score=$(sed -n 's/^Final Score: //p' "$txt")
    [ -n "$score" ] && [ "$score" -ge "$A" ] && [ "$score" -le "$B" ] || return 0
    cp "$txt" "$D/txt/$subdir"
    cp "json/$(basename "$txt" .txt).json" "$D/json/"
}

rm -rf "$D"; mkdir -p "$D/txt/low_scores" "$D/txt/high_scores" "$D/json"
shopt -s nullglob
for f in log/*_"$R".txt;             do copy_if_in_range "$f" "";            done
for f in log/low_scores/*_"$R".txt;  do copy_if_in_range "$f" low_scores/;  done
for f in log/high_scores/*_"$R".txt; do copy_if_in_range "$f" high_scores/; done

n=$(ls "$D/json" | wc -l)
echo "Run $R, scores in [$A, $B]: $n games (copied to $D)"; echo
[ "$n" -eq 0 ] && { echo "No games in this score range."; exit 0; }

python dev_tools/log_analyzer.py end_reasons        "$D/txt";  echo
python dev_tools/log_analyzer.py lost_lives         "$D/txt";  echo
python dev_tools/log_analyzer.py critical_discards  "$D/txt";  echo
python dev_tools/log_analyzer.py hint_types         "$D/json"; echo
python dev_tools/log_analyzer.py third_player_hints "$D/txt"; echo
python dev_tools/log_analyzer.py critical_misplays  "$D/txt";  echo
python dev_tools/log_analyzer.py critical_hints     "$D/txt"
