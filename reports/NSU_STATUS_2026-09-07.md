# NSU / CPU status — 2026-09-07

Read-only environment check while S3 Phase A (Kaggle kernel `dmitriigluzdov/duck-qwen3-8-flash-next-nvfp4-mtp` **v6**) is RUNNING. No install, training, dataset copy, kernel push, or submission.

Checked from local Windows `HASEE` as `hasee\dmitry`. SSH client: `C:\WINDOWS\System32\OpenSSH\ssh.exe`. VPN profile `NSU-SSTP` was **Disconnected** at first SSH attempt (~16:25 local); after Match-exec / `rasphone`, it was **Connected**. Do not disconnect it as cleanup.

## SSH identity (actual)

| Alias | First try | Retry after VPN Connected | Identity |
| --- | --- | --- | --- |
| `nsu-quadro` | exit 255, `banner exchange: Connection to UNKNOWN port -1: Connection timed out` | exit 0, `prepost` | user `gluz_d_s`, home `/home/scientists/gluz_d_s` |
| `nsu-a100` | same timeout | exit 0, `ngpu01` | same user/home (shared NFS) |
| `nsu-pc` | same timeout | exit 0, `desktop-7t0uo8i\user` | hostname `DESKTOP-7T0UO8I`, `%USERPROFILE%=C:\Users\User` |

`Test-NetConnection 10.1.0.7 -Port 22` while VPN was coming up: `TcpTestSucceeded=True`, ping failed (expected for these hosts).

## Resources observed (not a reservation)

**prepost (`nsu-quadro`)**, 10:28 server clock: up 46d, load `0.00 0.00 0.00`, 0 users. RAM 251 GiB total, ~247 GiB available. Quadro RTX 6000 24576 MiB, **5 MiB used, 0% util**, UUID `GPU-a4b01714-3774-ca39-a9d9-2f30429e84ba`. Driver 550.54.15, CUDA 12.4 (from `nvidia-smi`). `nvcc` not on PATH. `/usr/bin/python3` = 3.11.2. `timeout 15s sinfo` / `squeue --me`: no output (same as ACCESS snapshot).

**ngpu01 (`nsu-a100`)**: load `0.00`, RAM 251 GiB / ~247 GiB available. A100-0 UUID `GPU-61c0078d-a4a6-37a2-3aba-0378e7794c46` 0 MiB / 81920, 0%. A100-1 UUID `GPU-04efb7bd-1f45-38cd-4a13-c79b6aeaa002` 0 MiB / 81920, 0%. No compute PIDs. Same NFS. `nvcc` missing.

Shared NFS (do not add across hosts): `/home` 7.0T, 55G used, 7.0T avail; `/data` 39T, 104G used, 39T avail. Home and `/data` are writable for this user. Personal quota still unconfirmed.

**nsu-pc**: Python 3.12.3. RTX 3080 10240 MiB, **307 MiB used, 0%**. RAM `TotalVisibleMemorySize=33391960` KB (~31.8 GiB), `FreePhysicalMemory=26129328` KB (~24.9 GiB). Disks: C: ~401 GiB free of ~900 GiB; D: ~11.6 GiB free of ~30.9 GiB; E: ~1.67 TiB free of ~1.86 TiB.

## Registered Kaggle roots

- Linux `~/kaggle` (`/home/scientists/gluz_d_s/kaggle`): **missing**. Home contains only shell/dotfiles (`.bashrc`, `.ssh`, `.config`). No `ROOT_MANIFEST.json`, no `_control`, no git checkout of this repo.
- Windows `%USERPROFILE%\kaggle`: **missing**.
- No clone/pull/mkdir was performed (this prompt forbids transfers and infra changes).
- GPU coordination `_control` is absent → any **direct GPU launch would be `BLOCKED_COORDINATION`**. Idle GPUs are not a lease.

## Current S3 vs NSU

S3 (cross-level transfer on Flash v3 only) is already on Kaggle v6. NSU must **not** run a second Phase A, copy the NVFP4 checkpoint, or occupy a GPU.

NSU **is** usable for CPU-only side work that does not touch kernel v6. This pass used local S2 artifacts instead of remote CPU, because the traces are already on HASEE under `tmp/kernels/s2-output/` (gitignored).

Flash NVFP4 is a ~96 GB VRAM + CPU-offload Kaggle G4 / Blackwell-class stack. It does not fit Quadro 24 GB or RTX 3080 10 GB. One A100 is 80 GB, not 96 GB; two A100s are two devices, not 160 GB. `nvcc` is missing. Treat NSU GPU Phase A as **unproven / likely incompatible** until architecture + kernels are checked in an authorized later task. Do not migrate now.

## Cheap local S2 CPU scan (already-downloaded Phase A)

`score.json` mean **6.3244** / median **2.8991** over 25 public games (matches EXPERIMENT_LOG offline mean 6.32). Six zeros: `cd82`, `cn04`, `g50t`, `sk48`, `tn36`, `wa30`. Telemetry runtime **7922 s** of 32400 budget.

`artifacts/*_events.jsonl`: 5599 frames. Consecutive board pairs: **1808 identical**, **487 changed only in outer 2 rows** (HUD/timer hypothesis), **3279 interior changes**. High consecutive-repeat games include zero-score `cn04` (332/459) and `wa30`. Useful fixture material for **S4** (semantic no-impact guard). Not a leaderboard result.

## Done vs deferred

Done: read NSU + project docs; three SSH identity checks; read-only resource/`~/kaggle` inspect; local S2 score/HUD scan; this note.

Deferred (forbidden this turn): package install, venv, kaggle-root mkdir, git clone/pull, scp of weights/data, training, Slurm submit, GPU lease, kernel push, Phase B submit.

Cleanup: none. No remote files created. No owned unused artifacts to delete. VPN left connected.

## Recommended next CPU-only step (no Kaggle GPU)

After S3 Phase A COMPLETE (other agent owns the one authorized v6 submit): implement **S4 unit tests locally** using S2 event boards as fixtures — identical frames, outer-strip-only diffs, real interior diffs — plus confirmed `(semantic_state, action)` no-impact memory. Run with `C:\Users\Dmitry\.venvs\kg\Scripts\python.exe`. Do not occupy Kaggle. Do not start an NSU GPU job. Create the registered Linux `~/kaggle/projects/arc-prize-2026-arc-agi-3/` tree only when an authorized later task needs remote CPU/env, and only after site storage policy is still as documented.
