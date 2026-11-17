#!/usr/bin/env python3
"""Force many NPU runtime resumes and watch the kernel log for amdxdna SMU errors.

Each loop waits until the NPU is runtime-suspended (autosuspend delay set to 200 ms),
then sends one tiny request to a service that runs work on the NPU, so that every
request is a resume. It stops at the first SMU timeout, immediately at a fatal line,
or after --minutes. The original power settings are restored at the end.

You need a local service whose requests run on the NPU (we used an embedding server
on the NPU). Run as root, with nothing else using the NPU.

    sudo ./npu_resume_burst.py --pci 0000:c6:00.1 \
         --url http://127.0.0.1:8090/embedding --body '{"content": ["x"]}' --minutes 20

Find the PCI address with:  lspci -D | grep -i 'signal processing'
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request

FATAL = re.compile(r"smu cmd 4|Access power failed|mailbox|aie2_smu_init|Hardware init failed")
HICCUP = re.compile(r"smu cmd 6 timed out|wait for smu intr idle timed out")


def kernel_lines(since):
    """amdxdna lines of the kernel log since `since` (epoch seconds): journalctl, or dmesg as a fallback."""
    try:
        r = subprocess.run(["journalctl", "-k", "--since", "@%d" % int(since), "--no-pager", "-o", "short-iso"],
                           capture_output=True, text=True, timeout=60)
        out = r.stdout
    except FileNotFoundError:
        out = subprocess.run(["dmesg", "-T"], capture_output=True, text=True, timeout=60).stdout
    return [l for l in out.splitlines() if "amdxdna" in l]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pci", required=True, help="PCI address of the NPU, e.g. 0000:c6:00.1")
    ap.add_argument("--url", required=True, help="HTTP endpoint whose requests run on the NPU")
    ap.add_argument("--body", default='{"content": ["x"]}', help="JSON body of one tiny request")
    ap.add_argument("--minutes", type=float, default=20, help="maximum duration (default 20)")
    ap.add_argument("--delay-ms", type=int, default=200, help="autosuspend delay during the test (default 200)")
    a = ap.parse_args()

    power = "/sys/bus/pci/devices/%s/power/" % a.pci
    rd = lambda f: open(power + f).read().strip()

    def wr(f, v):
        with open(power + f, "w") as fh:
            fh.write(str(v))

    before = {"control": rd("control"), "autosuspend_delay_ms": rd("autosuspend_delay_ms")}
    body = a.body.encode()
    t0 = time.time()
    calls = resumes = errors = 0
    result, first_line, ms = "time limit", None, []
    print("start · before: %s" % before, flush=True)
    try:
        wr("autosuspend_delay_ms", a.delay_ms)
        wr("control", "auto")
        last_check = time.time()
        while time.time() - t0 < a.minutes * 60:
            t_wait = time.time()
            while time.time() - t_wait < 3:
                if rd("runtime_status") == "suspended":
                    resumes += 1
                    break
                time.sleep(0.02)
            t1 = time.time()
            try:
                req = urllib.request.Request(a.url, data=body, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=15).read()
                ms.append((time.time() - t1) * 1000)
            except Exception as e:
                errors += 1
                print("call %d: error %s" % (calls + 1, str(e)[:80]), flush=True)
            calls += 1
            if time.time() - last_check > 10 or errors:
                last_check = time.time()
                lines = kernel_lines(t0)
                fatal = [l for l in lines if FATAL.search(l)]
                hiccup = [l for l in lines if HICCUP.search(l)]
                if fatal:
                    result, first_line = "FATAL", fatal[0]
                    break
                if hiccup:
                    result, first_line = "SMU TIMEOUT", hiccup[0]
                    break
                if calls % 200 == 0:
                    print("%d calls, %d resumes, %d errors, %.0f s" % (calls, resumes, errors, time.time() - t0), flush=True)
    finally:
        wr("autosuspend_delay_ms", before["autosuspend_delay_ms"])
        wr("control", before["control"])
    end = {"result": result, "calls": calls, "resumes": resumes, "errors": errors,
           "seconds": round(time.time() - t0), "median_ms": round(sorted(ms)[len(ms) // 2]) if ms else None,
           "first_line": first_line, "after": {"control": rd("control"), "autosuspend_delay_ms": rd("autosuspend_delay_ms")}}
    print(json.dumps(end, indent=1), flush=True)
    return 0 if result == "time limit" else 1


if __name__ == "__main__":
    sys.exit(main())
