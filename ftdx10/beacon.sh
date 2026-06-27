#!/usr/bin/env bash
set -euo pipefail

# FTDX10 CW beacon through a local or remote rigctld endpoint.

RIGCTL_MODEL="${RIGCTL_MODEL:-2}"
RIGCTL_ENDPOINT="${RIGCTL_ENDPOINT:-127.0.0.1:4532}"
CALLSIGN="${CALLSIGN:-UT3UDX}"
FREQ="${FREQ:-14025000}"
REPEAT="${REPEAT:-1}"
PAUSE="${PAUSE:-5}"
RFPOWER="${RFPOWER:-0.05}"
CW_FILTER="${CW_FILTER:-500}"
MESSAGE="${MESSAGE:-CQ CQ CQ DE $CALLSIGN $CALLSIGN $CALLSIGN K}"

if ! [[ "$FREQ" =~ ^[0-9]+$ ]]; then
  echo "FREQ must be an integer frequency in Hz" >&2
  exit 2
fi

if ! [[ "$REPEAT" =~ ^[0-9]+$ ]]; then
  echo "REPEAT must be an integer" >&2
  exit 2
fi

if ! [[ "$PAUSE" =~ ^[0-9]+$ ]]; then
  echo "PAUSE must be an integer number of seconds" >&2
  exit 2
fi

RIGCTL=(rigctl -m "$RIGCTL_MODEL" -r "$RIGCTL_ENDPOINT")

run_rigctl() {
  "${RIGCTL[@]}" "$@"
}

run_rigctl F "$FREQ"
sleep 1
run_rigctl M CW "$CW_FILTER"
sleep 1
run_rigctl L RFPOWER "$RFPOWER"

echo "Starting CW beacon on $((FREQ / 1000)) kHz"

for ((i = 1; i <= REPEAT; i++)); do
  echo "Round $i/$REPEAT"
  sleep 3
  run_rigctl b "$MESSAGE"
  sleep "$PAUSE"
done

echo "Done"
