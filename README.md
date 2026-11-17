# xdna-hawkpoint-notes

A patch and a test tool for the AMD NPU (XDNA, `amdxdna` driver) on a Ryzen 9 PRO 8945HS
(Hawk Point, npu1) mini-PC that runs Linux 24/7.

## The problem

With the in-tree `amdxdna` 0.7.0 driver (Linux 7.0.6, Proxmox VE kernel `7.0.6-2-pve`), the NPU
now and then fails a runtime resume, and the kernel log says `smu cmd 6 timed out` (the SMU
command that changes the DPM H-clock). It is rare in normal use and easy to trigger with a short
autosuspend delay and many small jobs.

Reported upstream in [amd/xdna-driver#1805](https://github.com/amd/xdna-driver/issues/1805).
The driver's `main` branch already waits for the SMU to finish the previous command before
sending a new one; AMD said they will make an upstream patch for this.

## Results

Forced runtime resumes, autosuspend delay 200 ms, one tiny NPU job per resume
(`tools/npu_resume_burst.py`). Same machine, same firmware.

| driver | runtime resumes | `smu cmd 6 timed out` |
|---|---|---|
| in-tree 0.7.0, run 1 | 40 | 1 |
| in-tree 0.7.0, run 2 | 643 | 1 |
| in-tree 0.7.0 + the patch here | **4,253** (2 hours) | **0** |

Since 17 November 2026 the patched module is in daily use; a 48-hour count is running and
will be added here. These are the numbers of one machine: they say the wait helps here, not
that it is the whole story.

## What is here

| path | what | license |
|---|---|---|
| `patches/0001-accel-amdxdna-aie2-wait-for-SMU-idle-before-command.patch` | the backport: wait for SMU idle (bit 1 of `SMU_INTR_REG`) before a command, as `main` does | GPL-2.0, like the driver |
| `tools/npu_resume_burst.py` | the test: many forced runtime resumes, stops at the first SMU timeout, restores the power settings | MIT |

Apply the patch to your kernel source (`patch -p1 < patches/0001-…`), rebuild the `amdxdna`
module, and load it in place of the in-tree one. It is a test backport, not an official AMD
patch: use it at your own risk, and only if you see the same error.

---

Written in Italian, published in English. Code written with AI assistants on the command line.
More on the machine and its failures: [wastedtimeonpc.com](https://wastedtimeonpc.com).

*Ale — wastedtimeonpc.com*
