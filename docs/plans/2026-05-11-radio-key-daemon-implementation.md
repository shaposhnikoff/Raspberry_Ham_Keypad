# Radio Key Daemon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Raspberry Pi friendly userspace keyboard daemon that maps evdev key events to configured shell commands.

**Architecture:** The package is split into config, device discovery, key handling, daemon loop, action execution, logging, and CLI modules. Tests focus on pure logic first, with hardware access isolated behind small functions.

**Tech Stack:** Python 3.11+, evdev, PyYAML, pytest, ruff-compatible formatting, argparse, subprocess, logging, systemd.

---

## Tasks

1. Create packaging files: `pyproject.toml`, `requirements.txt`, package directory, and test directory.
2. Write failing tests for config loading, validation, debounce, and command building.
3. Implement dataclass config loading and validation.
4. Implement action command building and subprocess execution.
5. Implement key helpers and debounce tracker.
6. Implement device listing/selection with clear errors.
7. Implement daemon event loop, exclusive grab lifecycle, dry-run, and signal shutdown.
8. Implement CLI modes: run daemon, list devices, scan keys.
9. Add scripts, example config, systemd unit, and README.
10. Run targeted tests and static checks where available.
