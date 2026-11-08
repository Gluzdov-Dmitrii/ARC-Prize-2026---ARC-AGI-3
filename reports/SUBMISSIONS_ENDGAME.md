# ARC-3 endgame submissions (from 23.10; run by the ARC-2 session)

Kernel: dmitriigluzdov/arc3-franzen-d-prime-private-daily-variants (private fork of dfranzen milestone-2 v3,
build in `ARC Prize 2026 - ARC-AGI-2/work/codex-ws/arc3-fork/`). Day variants switch by one selector line.

| Date (UTC) | Ref | Version | Variant | Smoke save | LB |
|---|---|---|---|---|---|
| 23.10 09:13 | 57555893 | v1 | Franzen + D' priority (Affectify), smoke 1 game x 5 min | COMPLETE, D' installed, parquet written; smoke game gave up after 1 action (server still loading) | **0.00** in 40 min: model server loaded slower than Franzen's 12 min + 900 s analyzer retry window, all games gave up |
| 24.10 00:06 | 57575818 | v2 | v1 + ARC3_HTTP_RETRY_INITIAL_SECONDS 900 -> 2700 (server-wait fix); smoke 1 game x 30 min | COMPLETE: precache 220 s, server ready 466 s, ft09 won 6/6 levels (score 100, 90 actions, 86k tokens) | **0.00** again -> the server wait was not the (only) cause; our fork's rerun path differs from public D' (docker: private BYOD pin vs Affectify's public image) |
| - | - | arc3-affectify-copy v1 | exact private copy of Affectify with its public docker image | ERROR: CUDA unavailable with the current public image -> not submitted; docker pin is not what zeroes our reruns | - |
| 25.10 00:08 | 57610776 | arc3-franzen-copy v1 | Franzen unchanged in the rerun path; only Save Version smoke settings | COMPLETE (smoke game gave up, server still loading - expected in 290 s) | **23.60** -> pure Franzen works; our fork edits (D' port / cells) zeroed the reruns |
| 26.10 10:16 | 57662720 | arc3-franzen-copy v2 | Franzen + ARC3_CONTEXT_DRAIN_TOKENS 58k -> 40k | COMPLETE | **0.00** |
| 27.10 00:06 | 57682501 | arc3-franzen-copy v1 | exact rerun of the 23.60 version (diagnostic) | - | **0.00** -> zeros happen on unchanged code too (platform/server start), not only from our edits |
| 28.10 13:48 | 57738630 | arc3-franzen-copy v3 | exact copy of vickyfym/arc-agi-3-lalalia-final (33.94): Franzen + solved-level memory (lalalia9, idea rellik13/sirikilohit) + SERVER_STARTUP_TIMEOUT 55 min + retry 3600 s | COMPLETE: memory patch on, ft09 won 6/6 (96.92), run 32 min | **28.94** (best ARC-3 so far) |
| 29.10 ~02:56 | (see list) | arc3-franzen-copy v4 | v3 (lalalia-final) + D' priority cell copied unchanged from tantan0327/arc3-franzen-dprime (33.55) | COMPLETE: PRIORITY_FORM dprime + SOLVED_LEVEL_MEMORY both on, ft09 100 | **21.84** |
