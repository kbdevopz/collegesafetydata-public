"""
The pipeline lock: only one pipeline step runs at a time.

Each step's entry point runs under run_locked(), which holds an operating
system lock on data/curated/.pipeline.lock for the whole run. The operating
system releases that lock however the process ends (normal exit, error,
crash, taskkill /F, a closed window, power loss or reboot), so a lock is
never left behind and there is nothing to clear by hand. The file itself is
never deleted.

While a step holds the lock, the file says which step it is (step, process
id, start time in UTC). That text is only used in messages: whether a step is
running is decided by the operating system lock alone, so an old, empty or
unreadable file never blocks a step.

This module is not part of any step's code fingerprint (provenance.STAGE_CODE),
because it cannot change what a step writes. provenance re-exports its names.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from datetime import datetime, timezone

from config import CURATED_DIR

LOCK_PATH = CURATED_DIR / ".pipeline.lock"

# The byte that is locked lies far past the holder text, so other processes
# can still read the text (a Windows lock also blocks reading the bytes it
# covers). Windows allows locking past the end of a file.
_LOCK_OFFSET = 1 << 20

# How long a starting step waits for the lock (a step may be just finishing,
# or the checker may be looking at the lock for an instant), and how long the
# checker waits for a holder that has not written its text yet.
WAIT_SECONDS = 5.0
PROBE_SECONDS = 2.0

_HOLDER_MAX = 4096
_BINARY = getattr(os, "O_BINARY", 0)


class LockError(RuntimeError):
    """The pipeline lock cannot be taken."""


class LockHeld(LockError):
    """Another pipeline step holds the pipeline lock."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _try_lock(fd: int) -> bool:
    """Take the lock on open file `fd` without waiting. False if another
    process (or another open of the file) holds it; other errors raise OSError."""
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except PermissionError:  # the byte is locked by another holder
            return False
        return True
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


def _is_lock_file(fd: int) -> bool:
    """False if the file open as `fd` is no longer the one at LOCK_PATH (POSIX
    allows deleting or replacing an open file; Windows does not)."""
    if os.name == "nt":
        return True
    try:
        return os.path.samestat(os.fstat(fd), os.stat(LOCK_PATH))
    except OSError:
        return False


def _close(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def _holder() -> dict | None:
    """The holder text in the lock file, or None if it is missing or unreadable."""
    try:
        with open(LOCK_PATH, "rb", buffering=0) as f:
            data = f.read(_HOLDER_MAX)
        info = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return info if isinstance(info, dict) and info.get("step") else None


def _describe(info: dict | None) -> str:
    if info is None:
        return "an unnamed step (the lock file does not say which)"
    host = info.get("host")
    where = "" if host in (None, socket.gethostname()) else f" on {host}"
    return f"step {info.get('step')} (process {info.get('pid')}{where}, started {info.get('started')})"


def _write_holder(fd: int, step: str) -> None:
    text = json.dumps({"step": step, "pid": os.getpid(), "host": socket.gethostname(),
                       "started": _now()}, sort_keys=True)
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, text.encode("utf-8"))


def _remove_leftovers() -> None:
    """Remove the guard file an older version of the lock code could leave."""
    try:
        LOCK_PATH.with_name(LOCK_PATH.name + ".clearing").unlink(missing_ok=True)
    except OSError:
        pass


def acquire_lock(step: str) -> int:
    """
    Take the pipeline lock for `step` and write the holder text; returns the
    open lock file for release_lock(). If another step holds the lock, waits
    up to WAIT_SECONDS for it, then raises LockHeld. A lock file that cannot
    be opened or locked raises LockError.
    """
    deadline = time.monotonic() + WAIT_SECONDS
    holder = None
    while True:
        problem = None
        try:
            LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT | _BINARY, 0o666)
        except OSError as e:
            problem = f"Could not open the pipeline lock file {LOCK_PATH}: {e.strerror or e}"
        else:
            try:
                got = _try_lock(fd)
            except OSError as e:
                got = False
                problem = f"Could not lock the pipeline lock file {LOCK_PATH}: {e.strerror or e}"
            if got and _is_lock_file(fd):
                break
            if got:
                try:
                    _unlock(fd)
                except OSError:
                    pass
            _close(fd)
            if problem is None:
                holder = _holder() or holder
        if time.monotonic() >= deadline:
            if problem is None:
                raise LockHeld(f"Another pipeline step is running: {_describe(holder)}. Wait for it "
                               f"to finish, then run step {step} again.")
            raise LockError(f"{problem}. If another program (sync, backup or antivirus) has it open, "
                            f"close it. If this repeats and no pipeline step is running, delete "
                            f"{LOCK_PATH} (the next step creates it again). Then run step {step} again.")
        time.sleep(0.05)
    try:
        _write_holder(fd, step)
    except OSError:
        pass  # the text is only for messages; the lock is held either way
    _remove_leftovers()
    return fd


def release_lock(fd: int) -> None:
    """Clear the holder text and release the lock taken by acquire_lock()."""
    try:
        os.ftruncate(fd, 0)
    except OSError:
        pass
    try:
        _unlock(fd)
    except OSError:
        pass  # closing the file releases it too
    _close(fd)


def lock_report() -> str | None:
    """
    For the checker: None if no pipeline step is running, else what is
    running. It takes the lock for an instant to find out (a step starting at
    that moment waits for it) and never changes or deletes any file.
    """
    where = LOCK_PATH.relative_to(LOCK_PATH.parents[2]).as_posix()
    deadline = time.monotonic() + PROBE_SECONDS
    busy_since = None
    problem = None
    while True:
        try:
            fd = os.open(LOCK_PATH, os.O_RDONLY | _BINARY)
        except FileNotFoundError:
            return None  # no step has run here yet
        except OSError as e:
            problem = e
        else:
            try:
                free = _try_lock(fd)
                if free:
                    _unlock(fd)
                problem = None
            except OSError as e:
                free, problem = False, e
            finally:
                _close(fd)
            if free:
                return None
            if problem is None:
                now = time.monotonic()
                busy_since = now if busy_since is None else busy_since
                info = _holder()
                # Held for 0.2 s or more: a step, not another check looking for an instant
                if info is not None and now - busy_since >= 0.2:
                    return (f"A pipeline step is running: {_describe(info)} holds {where}. Run this "
                            f"check again when it has finished")
        if time.monotonic() >= deadline:
            break
        time.sleep(0.05)
    if problem is not None:
        return (f"Could not check whether a pipeline step is running: {where} cannot be opened or "
                f"locked ({problem.strerror or problem}). If another program (sync, backup or "
                f"antivirus) has it open, close it, then run this check again")
    return (f"A pipeline step is running: {_describe(None)} holds {where}. Run this check again "
            f"when it has finished")


def run_locked(step: str, main) -> int:
    """Run a step's main() while holding the pipeline lock; returns its exit code."""
    from provenance import RecordError  # provenance imports this module
    try:
        lock = acquire_lock(step)
    except LockError as e:
        sys.stdout.flush()
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    try:
        code = main()
    except RecordError as e:
        sys.stdout.flush()
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1
    finally:
        release_lock(lock)
    return code if isinstance(code, int) else 0
