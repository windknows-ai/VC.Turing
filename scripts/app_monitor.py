"""Watch the running desktop app's whole process tree (Python plus its WebView2 helpers):
CPU, memory, process/thread/handle counts and GPU use, so a slow leak or a busy idle
loop shows up as numbers.

    python scripts/app_monitor.py 10            # watch for 10 minutes
    python scripts/app_monitor.py 10 --launch   # start Turing first (orb mode)

Writes .scratch/monitor/samples.csv and prints a summary. Leaves Turing running.
"""

import csv
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".scratch" / "monitor"


def find_app():
    for p in psutil.process_iter(["name", "cmdline"]):
        cmd = " ".join(p.info["cmdline"] or [])
        if "turing.desktop" in cmd and p.info["name"].lower().startswith("python"):
            # The venv launcher starts the real interpreter as a child: take the leaf.
            kids = [c for c in p.children() if c.name().lower().startswith("python")]
            return kids[0] if kids else p
    return None


def tree(root):
    try:
        return [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        return []


def gpu_percent(pids):
    """Sum of GPU engine utilisation for these processes (Windows performance counters)."""
    pattern = "|".join(f"pid_{p}_" for p in pids)
    script = ("$s=(Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue)"
              f".CounterSamples | Where-Object {{ $_.InstanceName -match '{pattern}' }};"
              "($s | Measure-Object CookedValue -Sum).Sum")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                             text=True, timeout=30).stdout.strip()
        return round(float(out or 0), 2)
    except (ValueError, subprocess.TimeoutExpired):
        return None


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else 10
    if "--launch" in sys.argv and not find_app():
        pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
        subprocess.Popen([str(pythonw), "-m", "turing.desktop"], cwd=str(ROOT),
                         creationflags=subprocess.DETACHED_PROCESS)
        time.sleep(25)  # models load
    app = find_app()
    if not app:
        sys.exit("Turing isn't running.")
    OUT.mkdir(parents=True, exist_ok=True)
    rows, primed = [], set()
    end = time.monotonic() + minutes * 60
    started = time.monotonic()
    while time.monotonic() < end:
        procs = tree(app)
        if not procs:
            sys.exit("Turing exited.")
        for p in procs:
            if p.pid not in primed:
                try:
                    p.cpu_percent()
                except psutil.NoSuchProcess:
                    pass
                primed.add(p.pid)
        time.sleep(10)
        cpu = mem = threads = handles = 0
        webview = 0
        for p in procs:
            try:
                with p.oneshot():
                    cpu += p.cpu_percent()
                    mem += p.memory_info().private
                    threads += p.num_threads()
                    handles += p.num_handles()
                    webview += p.name().lower().startswith("msedgewebview2")
            except psutil.NoSuchProcess:
                pass
        rows.append({
            "seconds": round(time.monotonic() - started),
            "processes": len(procs), "webview_processes": webview,
            "cpu_pct": round(cpu, 1), "private_mb": round(mem / 2**20, 1),
            "threads": threads, "handles": handles,
            "gpu_pct": gpu_percent([p.pid for p in procs]) if len(rows) % 3 == 0 else "",
        })
        print(rows[-1], flush=True)

    with open(OUT / "samples.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    first, last = rows[0], rows[-1]
    gpus = [r["gpu_pct"] for r in rows if isinstance(r["gpu_pct"], float)]
    print(f"\n{len(rows)} samples over {last['seconds']} s")
    print(f"processes {first['processes']} -> {last['processes']}  (WebView2: {last['webview_processes']})")
    print(f"private memory {first['private_mb']} -> {last['private_mb']} MB")
    print(f"threads {first['threads']} -> {last['threads']}   handles {first['handles']} -> {last['handles']}")
    print(f"CPU mean {sum(r['cpu_pct'] for r in rows) / len(rows):.1f}% (of one core), "
          f"max {max(r['cpu_pct'] for r in rows)}%")
    if gpus:
        print(f"GPU mean {sum(gpus) / len(gpus):.2f}%, max {max(gpus)}%")


if __name__ == "__main__":
    main()
