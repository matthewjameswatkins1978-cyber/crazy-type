"""Mechanical dogfooding under a real Windows pseudo-terminal (ConPTY).

Runs the actual installed CLI with a true console: real keypress bytes,
real Ctrl+C, real ANSI stream. Asserts what a headless run CAN prove —
exit codes, cursor restoration, saved-file contents. Visual aesthetics
still need human eyes.

NOT part of pytest (timing-sensitive, Windows-only). Run by hand:

    uv run python tools/conpty_dogfood.py

Requires: Windows 10 1809+, the project venv (uses .venv Scripts).
Takes ~2 minutes. Known harness limits, not product bugs:
- ConPTY re-emits an optimized stream, so byte counts vary run to run;
  assert on exit codes, marker bytes (b"?25h") and files, not sizes.
- A fresh ConPTY console may default to a non-UTF-8 code page; the harness
  pins PYTHONUTF8=1 so animation paths (not fallbacks) are exercised.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import sys
import threading
import time

REPO = r"D:\Projects\crazy-type"
CT = r"D:\Projects\crazy-type\.venv\Scripts\crazytype.exe"

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class COORD_S(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("lpReserved", ctypes.c_wchar_p), ("lpDesktop", ctypes.c_wchar_p),
        ("lpTitle", ctypes.c_wchar_p), ("dwX", ctypes.c_ulong), ("dwY", ctypes.c_ulong),
        ("dwXSize", ctypes.c_ulong), ("dwYSize", ctypes.c_ulong), ("dwXCountChars", ctypes.c_ulong),
        ("dwYCountChars", ctypes.c_ulong), ("dwFillAttribute", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
        ("wShowWindow", ctypes.c_ushort), ("cbReserved2", ctypes.c_ushort), ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", ctypes.c_void_p), ("hStdOutput", ctypes.c_void_p), ("hStdError", ctypes.c_void_p),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", ctypes.c_void_p), ("hThread", ctypes.c_void_p),
                ("dwProcessId", ctypes.c_ulong), ("dwThreadId", ctypes.c_ulong)]


class STARTUPINFOEX(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFO), ("lpAttributeList", ctypes.c_void_p)]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", ctypes.c_ulong), ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", ctypes.c_bool)]


kernel32.CreatePseudoConsole.argtypes = [COORD_S, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
kernel32.CreatePseudoConsole.restype = ctypes.c_long
kernel32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(ctypes.c_size_t)]
kernel32.InitializeProcThreadAttributeList.restype = ctypes.c_bool
kernel32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
kernel32.UpdateProcThreadAttribute.restype = ctypes.c_bool
kernel32.CreateProcessW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(STARTUPINFOEX), ctypes.POINTER(PROCESS_INFORMATION)]
kernel32.CreateProcessW.restype = ctypes.c_bool
kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
kernel32.ClosePseudoConsole.argtypes = [ctypes.c_void_p]
kernel32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
kernel32.WriteFile.restype = ctypes.c_bool
kernel32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
kernel32.ReadFile.restype = ctypes.c_bool
kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
kernel32.GetExitCodeProcess.restype = ctypes.c_bool
kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
kernel32.TerminateProcess.restype = ctypes.c_bool
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.c_bool
kernel32.CreatePipe.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_ulong]
kernel32.CreatePipe.restype = ctypes.c_bool
kernel32.SetHandleInformation.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
kernel32.SetHandleInformation.restype = ctypes.c_bool

EXTENDED_STARTUPINFO_PRESENT = 0x00080000
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
STILL_ACTIVE = 259
HANDLE_FLAG_INHERIT = 1
ERROR_BROKEN_PIPE = 109


def run_under_conpty(cmdline, cwd=REPO, inputs=(), total_timeout=60, cols=120, rows=30):
    """Spawn cmdline under ConPTY. inputs = [(delay_seconds | 'wait:MARK', bytes)].

    Returns (exit_code, captured_bytes). IMPORTANT: bInheritHandles must be
    False, otherwise the child inherits our redirected pipes instead of using
    the pseudo-terminal for stdio.
    """
    def make_pipe():
        r, w = ctypes.c_void_p(), ctypes.c_void_p()
        sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, True)
        if not kernel32.CreatePipe(ctypes.byref(r), ctypes.byref(w), ctypes.byref(sa), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return r.value, w.value

    in_r, in_w = make_pipe()
    out_r, out_w = make_pipe()
    kernel32.SetHandleInformation(in_w, HANDLE_FLAG_INHERIT, 0)
    kernel32.SetHandleInformation(out_r, HANDLE_FLAG_INHERIT, 0)

    hpc = ctypes.c_void_p()
    hr = kernel32.CreatePseudoConsole(COORD_S(cols, rows), in_r, out_w, 0, ctypes.byref(hpc))
    if hr != 0:
        raise OSError(f"CreatePseudoConsole failed: {hr:#x}")

    size = ctypes.c_size_t(0)
    kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attr_mem = ctypes.create_string_buffer(size.value)
    if not kernel32.InitializeProcThreadAttributeList(attr_mem, 1, 0, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel32.UpdateProcThreadAttribute(attr_mem, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                                              hpc, ctypes.sizeof(ctypes.c_void_p), None, None):
        raise ctypes.WinError(ctypes.get_last_error())

    si = STARTUPINFOEX()
    si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEX)
    si.lpAttributeList = ctypes.cast(attr_mem, ctypes.c_void_p).value
    pi = PROCESS_INFORMATION()
    ok = kernel32.CreateProcessW(None, ctypes.create_unicode_buffer(cmdline), None, None, False,
                                 EXTENDED_STARTUPINFO_PRESENT, None, cwd,
                                 ctypes.byref(si), ctypes.byref(pi))
    kernel32.DeleteProcThreadAttributeList(attr_mem)
    kernel32.CloseHandle(pi.hThread)
    kernel32.CloseHandle(in_r)
    kernel32.CloseHandle(out_w)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())

    chunks: list[bytes] = []
    stop_read = threading.Event()

    def reader():
        while not stop_read.is_set():
            buf = ctypes.create_string_buffer(65536)
            n = ctypes.c_ulong(0)
            ok = kernel32.ReadFile(out_r, buf, 65536, ctypes.byref(n), None)
            if not ok:
                if ctypes.get_last_error() == ERROR_BROKEN_PIPE:
                    break
                time.sleep(0.01)
                continue
            if n.value == 0:
                time.sleep(0.01)
                continue
            chunks.append(buf.raw[: n.value])

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    sent = [False] * len(inputs)
    start = time.monotonic()
    exit_code = None
    try:
        while time.monotonic() - start < total_timeout:
            elapsed = time.monotonic() - start
            captured = b"".join(chunks)
            for i, (delay, data) in enumerate(inputs):
                if sent[i]:
                    continue
                if isinstance(delay, str) and delay.startswith("wait:"):
                    if delay[5:].encode() not in captured:
                        continue
                elif elapsed < delay:
                    continue
                written = ctypes.c_ulong(0)
                kernel32.WriteFile(in_w, data, len(data), ctypes.byref(written), None)
                sent[i] = True
            code = ctypes.c_ulong(0)
            kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
            if code.value != STILL_ACTIVE:
                exit_code = code.value
                break
            time.sleep(0.05)
        if exit_code is None:
            kernel32.TerminateProcess(pi.hProcess, 99)
            exit_code = 99
    finally:
        kernel32.CloseHandle(pi.hProcess)

    stop_read.set()
    # Grace period: ConPTY emits asynchronously; wait for quiet before closing,
    # then close the console first so the blocked reader sees EOF.
    last_len, quiet = -1, 0
    for _ in range(40):
        time.sleep(0.1)
        total = sum(len(c) for c in chunks)
        quiet = quiet + 1 if total == last_len else 0
        if quiet >= 5:
            break
        last_len = total
    kernel32.ClosePseudoConsole(hpc)
    kernel32.CloseHandle(in_w)
    t.join(timeout=10)
    kernel32.CloseHandle(out_r)
    return exit_code, b"".join(chunks)


def check(name, cmdline, inputs, timeout, predicate):
    code, out = run_under_conpty(cmdline, inputs=inputs, total_timeout=timeout)
    ok, detail = predicate(code, out)
    print(f"{'PASS' if ok else 'FAIL'} {name}: exit={code} bytes={len(out)} {detail}", flush=True)
    return ok


def main() -> int:
    if os.name != "nt":
        print("conpty_dogfood needs Windows.", file=sys.stderr)
        return 2
    results = []
    play = f'cmd /c "set PYTHONUTF8=1&& {CT} play particle-reconstruction BAM > CON"'

    def _strip(data: bytes) -> bytes:
        return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][AB0]|\x1b[78]|\x1b\].*?\x07", b"", data)

    results.append(check(
        "play under true console", play, [], 90,
        lambda c, o: (c == 0 and b"BAM" in _strip(o) and b"\x1b[?25h" in o, ""),
    ))
    intr = f'cmd /c "set PYTHONUTF8=1&& {CT} play living-neon InterruptMe > CON"'
    results.append(check(
        "ctrl+c exit 130 + cursor", intr, [(5.0, b"\x03")], 90,
        lambda c, o: (c == 130 and b"\x1b[?25h" in o, ""),
    ))
    nav = f'cmd /c "set PYTHONUTF8=1&& {CT} studio living-neon > CON"'
    results.append(check(
        "dirty-quit arms then quits", nav, [(6.0, b"d"), (8.0, b"q"), (10.0, b"q")], 60,
        lambda c, o: (c == 0, ""),
    ))
    target = os.path.join(REPO, "conpty_save_test.json")
    if os.path.exists(target):
        os.remove(target)
    keys = [(12.0, b"s")]
    for i, ch in enumerate("conpty_save_test.json"):
        keys.append((15.0 + i * 0.1, ch.encode()))
    keys += [(18.0, b"\r"), (20.0, b"q")]
    code, _ = run_under_conpty(nav, REPO, inputs=keys, total_timeout=45)
    saved_ok = code == 0 and os.path.exists(target)
    if saved_ok:
        data = json.load(open(target, encoding="utf-8"))
        saved_ok = data.get("name") == "living-neon"
        os.remove(target)
    print(f"{'PASS' if saved_ok else 'FAIL'} save round trip: exit={code}", flush=True)
    results.append(saved_ok)
    ok = all(results)
    print("DOGFOOD " + ("OK" if ok else "FAILED"), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
