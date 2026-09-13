#!/usr/bin/env python3
"""Bounded, read-only attribution for Windows background UI regressions.

This tool never hides, kills, or restarts processes. It snapshots visible top-level
windows and the foreground window, then attaches PID/executable/parent-chain
context. `watch` is deliberately time-bounded and on-demand; it is not a daemon.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import time
from datetime import datetime, timezone
from typing import Any


TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH = 260
MAX_PARENT_DEPTH = 8
MAX_WATCH_SECONDS = 120.0
MIN_INTERVAL_MS = 50


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parent_chain(processes: dict[int, dict[str, Any]], pid: int, max_depth: int = MAX_PARENT_DEPTH) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[int] = set()
    current = int(pid or 0)
    while current > 0 and current not in seen and len(chain) < max_depth:
        seen.add(current)
        row = processes.get(current)
        if row is None:
            chain.append({"pid": current, "ppid": None, "name": None, "path": None})
            break
        chain.append(
            {
                "pid": current,
                "ppid": row.get("ppid"),
                "name": row.get("name"),
                "path": row.get("path"),
            }
        )
        current = int(row.get("ppid") or 0)
    return chain


def _windows_bindings() -> tuple[Any, Any, Any]:
    if os.name != "nt":
        raise RuntimeError("WINDOWS_UI_PROBE_REQUIRES_WINDOWS")

    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * MAX_PATH),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND

    return kernel32, user32, PROCESSENTRY32W


def _query_process_path(kernel32: Any, pid: int) -> str | None:
    from ctypes import wintypes

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        capacity = 32768
        buffer = ctypes.create_unicode_buffer(capacity)
        size = wintypes.DWORD(capacity)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value[: int(size.value)]
    finally:
        kernel32.CloseHandle(handle)


def _process_table(kernel32: Any, entry_type: Any) -> dict[int, dict[str, Any]]:
    invalid_handle = ctypes.c_void_p(-1).value
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or ctypes.cast(snapshot, ctypes.c_void_p).value == invalid_handle:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    rows: dict[int, dict[str, Any]] = {}
    try:
        entry = entry_type()
        entry.dwSize = ctypes.sizeof(entry_type)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            pid = int(entry.th32ProcessID)
            rows[pid] = {
                "pid": pid,
                "ppid": int(entry.th32ParentProcessID),
                "name": str(entry.szExeFile),
                "path": None,
            }
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    return rows


def _window_text(user32: Any, hwnd: int) -> str:
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_class(user32: Any, hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def _window_pid(user32: Any, hwnd: int) -> int:
    from ctypes import wintypes

    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _decorate_window(
    raw: dict[str, Any], processes: dict[int, dict[str, Any]], kernel32: Any
) -> dict[str, Any]:
    pid = int(raw.get("pid") or 0)
    process = processes.get(pid, {})
    chain = _parent_chain(processes, pid)
    for row in chain:
        chain_pid = int(row.get("pid") or 0)
        cached = processes.get(chain_pid)
        if cached is not None and cached.get("path") is None:
            cached["path"] = _query_process_path(kernel32, chain_pid)
        if cached is not None:
            row["path"] = cached.get("path")
    executable = process.get("path")
    if executable is None and pid:
        executable = _query_process_path(kernel32, pid)
        if process:
            process["path"] = executable
    return {
        **raw,
        "process_name": process.get("name"),
        "executable": executable,
        "parent_chain": chain,
    }


def capture() -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "UNSUPPORTED", "reason": "WINDOWS_UI_PROBE_REQUIRES_WINDOWS", "captured_at": _iso_now()}

    kernel32, user32, entry_type = _windows_bindings()
    processes = _process_table(kernel32, entry_type)
    foreground_hwnd = int(user32.GetForegroundWindow() or 0)
    windows: list[dict[str, Any]] = []

    from ctypes import wintypes

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            windows.append(
                _decorate_window(
                    {
                        "hwnd": int(hwnd),
                        "pid": _window_pid(user32, hwnd),
                        "title": _window_text(user32, hwnd),
                        "class_name": _window_class(user32, hwnd),
                        "foreground": int(hwnd) == foreground_hwnd,
                    },
                    processes,
                    kernel32,
                )
            )
        return True

    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    if not user32.EnumWindows(callback, 0):
        raise OSError(ctypes.get_last_error(), "EnumWindows failed")

    windows.sort(key=lambda row: (not bool(row["foreground"]), int(row["hwnd"])))
    foreground = next((row for row in windows if row["hwnd"] == foreground_hwnd), None)
    if foreground is None and foreground_hwnd:
        foreground = _decorate_window(
            {
                "hwnd": foreground_hwnd,
                "pid": _window_pid(user32, foreground_hwnd),
                "title": _window_text(user32, foreground_hwnd),
                "class_name": _window_class(user32, foreground_hwnd),
                "foreground": True,
            },
            processes,
            kernel32,
        )

    return {
        "status": "OK",
        "captured_at": _iso_now(),
        "foreground": foreground,
        "visible_windows": windows,
    }


def _diff_events(previous: dict[str, Any], current: dict[str, Any], seen_hwnds: set[int]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous_foreground = int((previous.get("foreground") or {}).get("hwnd") or 0)
    current_foreground = int((current.get("foreground") or {}).get("hwnd") or 0)
    if current_foreground and current_foreground != previous_foreground:
        events.append(
            {
                "kind": "foreground_changed",
                "observed_at": current.get("captured_at"),
                "window": current.get("foreground"),
                "previous_hwnd": previous_foreground or None,
            }
        )

    for window in current.get("visible_windows") or []:
        hwnd = int(window.get("hwnd") or 0)
        if hwnd and hwnd not in seen_hwnds:
            seen_hwnds.add(hwnd)
            events.append(
                {
                    "kind": "visible_window_created_or_discovered",
                    "observed_at": current.get("captured_at"),
                    "window": window,
                }
            )
    return events


def watch(seconds: float, interval_ms: int) -> dict[str, Any]:
    seconds = float(seconds)
    interval_ms = int(interval_ms)
    if seconds <= 0 or seconds > MAX_WATCH_SECONDS:
        raise ValueError(f"seconds must be > 0 and <= {MAX_WATCH_SECONDS:g}")
    if interval_ms < MIN_INTERVAL_MS:
        raise ValueError(f"interval-ms must be >= {MIN_INTERVAL_MS}")

    baseline = capture()
    if baseline.get("status") != "OK":
        return {**baseline, "mode": "watch"}

    seen_hwnds = {int(row.get("hwnd") or 0) for row in baseline.get("visible_windows") or []}
    events: list[dict[str, Any]] = []
    previous = baseline
    deadline = time.monotonic() + seconds
    samples = 1
    while time.monotonic() < deadline:
        time.sleep(interval_ms / 1000.0)
        current = capture()
        samples += 1
        events.extend(_diff_events(previous, current, seen_hwnds))
        previous = current

    return {
        "status": "OK",
        "mode": "watch",
        "started_at": baseline.get("captured_at"),
        "finished_at": previous.get("captured_at"),
        "duration_seconds": seconds,
        "interval_ms": interval_ms,
        "samples": samples,
        "baseline_foreground": baseline.get("foreground"),
        "events": events,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded read-only Windows visible-window attribution")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="capture visible top-level windows and foreground owner once")
    watch_parser = sub.add_parser("watch", help="watch briefly for new visible windows or foreground changes")
    watch_parser.add_argument("--seconds", type=float, default=10.0)
    watch_parser.add_argument("--interval-ms", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = capture() if args.command == "snapshot" else watch(args.seconds, args.interval_ms)
    except (OSError, RuntimeError, ValueError) as exc:
        payload = {"status": "ERROR", "error": str(exc), "captured_at": _iso_now()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
