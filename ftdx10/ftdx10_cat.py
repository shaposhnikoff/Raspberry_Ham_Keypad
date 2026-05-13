#!/usr/bin/env python3
"""
FTDX10 CAT helper for Raspberry_Ham_Keypad.

No pyserial dependency: uses Linux termios directly.
Default CAT port: /dev/ttyUSB0
Default CAT baud: 38400

Examples:
  ./ftdx10_cat.py band 14
  ./ftdx10_cat.py vol up 10
  ./ftdx10_cat.py freq up 5
  ./ftdx10_cat.py power 10
  ./ftdx10_cat.py tuner tune
  ./ftdx10_cat.py nb on
  ./ftdx10_cat.py raw 'FA;'
  ./ftdx10_cat.py status
"""

from __future__ import annotations

import argparse
import os
import re
import select
import sys
import termios
import time
from dataclasses import dataclass


BAUDS = {
    4800: termios.B4800,
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
}

BANDS = {
    "1.8": "00",
    "160": "00",
    "3.5": "01",
    "80": "01",
    "5": "02",
    "60": "02",
    "7": "03",
    "40": "03",
    "10": "04",
    "30": "04",
    "14": "05",
    "20": "05",
    "18": "06",
    "17": "06",
    "21": "07",
    "15": "07",
    "24.5": "08",
    "12": "08",
    "28": "09",
    "10m": "09",
    "50": "10",
    "6": "10",
    "gen": "11",
    "mw": "12",
}


@dataclass
class CatPort:
    path: str
    baud: int
    timeout: float = 0.6

    def __enter__(self) -> "CatPort":
        if self.baud not in BAUDS:
            raise SystemExit(f"Unsupported baud {self.baud}; use one of {sorted(BAUDS)}")

        self.fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0                         # iflag: raw input
        attrs[1] = 0                         # oflag: raw output
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0                         # lflag: raw local
        attrs[4] = BAUDS[self.baud]          # ispeed
        attrs[5] = BAUDS[self.baud]          # ospeed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0

        # Disable RTS/CTS where available.
        if hasattr(termios, "CRTSCTS"):
            attrs[2] &= ~termios.CRTSCTS

        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        os.close(self.fd)

    def write(self, command: str) -> None:
        if not command.endswith(";"):
            command += ";"
        os.write(self.fd, command.encode("ascii"))
        time.sleep(0.05)

    def read_until_semicolon(self) -> str:
        deadline = time.monotonic() + self.timeout
        data = bytearray()

        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            ready, _, _ = select.select([self.fd], [], [], min(remaining, 0.05))
            if not ready:
                continue

            try:
                chunk = os.read(self.fd, 256)
            except BlockingIOError:
                continue

            if not chunk:
                continue

            data.extend(chunk)
            if b";" in data:
                break

        return data.decode("ascii", errors="replace")

    def query(self, command: str) -> str:
        self.write(command)
        return self.read_until_semicolon()


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def parse_first_int(pattern: str, text: str, label: str) -> int:
    match = re.search(pattern, text)
    if not match:
        raise SystemExit(f"Could not parse {label} from CAT answer: {text!r}")
    return int(match.group(1))


def cmd_band(cat: CatPort, value: str) -> None:
    key = value.strip().lower()
    if key not in BANDS:
        raise SystemExit(f"Unknown band {value!r}; valid keys: {', '.join(sorted(BANDS))}")
    code = BANDS[key]
    cat.write(f"BS{code};")
    print(f"band={value} cat=BS{code};")


def cmd_freq(cat: CatPort, direction: str, count: int) -> None:
    command = {"up": "UP;", "down": "DN;"}[direction]
    for _ in range(max(1, count)):
        cat.write(command)
    print(f"freq_{direction} count={max(1, count)} cat={command}")


def cmd_vol(cat: CatPort, direction: str, step: int) -> None:
    answer = cat.query("AG0;")
    current = parse_first_int(r"AG0(\d{3});", answer, "AF gain")
    delta = abs(step) if direction == "up" else -abs(step)
    new_value = clamp(current + delta, 0, 255)
    cat.write(f"AG0{new_value:03d};")
    print(f"af_gain {current} -> {new_value} cat=AG0{new_value:03d};")


def cmd_power(cat: CatPort, watts: int) -> None:
    watts = clamp(watts, 5, 100)
    cat.write(f"PC{watts:03d};")
    print(f"power={watts}W cat=PC{watts:03d};")


def cmd_tuner(cat: CatPort, action: str) -> None:
    commands = {
        "off": "AC000;",
        "on": "AC001;",
        "tune": "AC002;",
    }
    cat.write(commands[action])
    print(f"tuner={action} cat={commands[action]}")


def cmd_nb(cat: CatPort, state: str) -> None:
    command = "NB01;" if state == "on" else "NB00;"
    cat.write(command)
    print(f"noise_blanker={state} cat={command}")


def cmd_clar(cat: CatPort, action: str) -> None:
    commands = {
        "clear": "RC;",
        "up": "RU;",
        "down": "RD;",
    }
    cat.write(commands[action])
    print(f"clar={action} cat={commands[action]}")


def cmd_raw(cat: CatPort, command: str, read: bool) -> None:
    if read:
        print(cat.query(command))
    else:
        cat.write(command)
        print(f"raw cat={command if command.endswith(';') else command + ';'}")


def cmd_status(cat: CatPort) -> None:
    # FA = VFO-A frequency, AG0 = AF gain, PC = power, IF = operating info.
    # Some answers may be empty if the port/radio is not ready; print whatever is returned.
    for command in ("FA;", "AG0;", "PC;", "IF;"):
        answer = cat.query(command)
        print(f"{command} {answer.strip()}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FTDX10 CAT helper")
    parser.add_argument("--port", default=os.environ.get("CAT_PORT", "/dev/ttyUSB0"))
    parser.add_argument("--baud", type=int, default=int(os.environ.get("CAT_BAUD", "38400")))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("CAT_TIMEOUT", "0.6")))

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("band")
    p.add_argument("value", help="1.8, 3.5, 5, 7, 10, 14, 18, 21, 24.5, 28, 50, gen, mw")

    p = sub.add_parser("freq")
    p.add_argument("direction", choices=["up", "down"])
    p.add_argument("count", nargs="?", type=int, default=1)

    p = sub.add_parser("vol")
    p.add_argument("direction", choices=["up", "down"])
    p.add_argument("step", nargs="?", type=int, default=8)

    p = sub.add_parser("power")
    p.add_argument("watts", type=int)

    p = sub.add_parser("tuner")
    p.add_argument("action", choices=["off", "on", "tune"])

    p = sub.add_parser("nb")
    p.add_argument("state", choices=["on", "off"])

    p = sub.add_parser("clar")
    p.add_argument("action", choices=["clear", "up", "down"])

    p = sub.add_parser("raw")
    p.add_argument("cat_command")
    p.add_argument("--read", action="store_true", help="read and print answer until ';'")

    sub.add_parser("status")

    return parser


def main() -> int:
    args = build_parser().parse_args()

    with CatPort(args.port, args.baud, args.timeout) as cat:
        if args.command == "band":
            cmd_band(cat, args.value)
        elif args.command == "freq":
            cmd_freq(cat, args.direction, args.count)
        elif args.command == "vol":
            cmd_vol(cat, args.direction, args.step)
        elif args.command == "power":
            cmd_power(cat, args.watts)
        elif args.command == "tuner":
            cmd_tuner(cat, args.action)
        elif args.command == "nb":
            cmd_nb(cat, args.state)
        elif args.command == "clar":
            cmd_clar(cat, args.action)
        elif args.command == "raw":
            cmd_raw(cat, args.cat_command, args.read)
        elif args.command == "status":
            cmd_status(cat)
        else:
            raise SystemExit(f"Unhandled command {args.command!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
