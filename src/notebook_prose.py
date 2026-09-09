"""Our notebook markdown. Credits stay; Tufa/Keith first-person copy does not."""

from __future__ import annotations

FORBIDDEN_FOREIGN_FIRST_PERSON = (
    "milestone-winning 1.21",
    "we haven't had the same lucky result with this one",
    "# Tufa Labs ARC3 submission",
    "See our writeup on the competition forum",
    "My changes are limited to model serving",
)

ABOUT_FORK = """## About this fork

This private notebook continues other people's public work, then adds a policy change we measured on the leaderboard.

**Whose work we continue**

- [Tufa Labs Duck harness — June 30 milestone winner](https://www.kaggle.com/code/jeroencottaar/tufa-labs-duck-harness-june-30-milestone-winner) by Jeroen Cottaar and the Tufa Labs team (Harold Bessis, Isaiah Pressman, Andries Smit, Michal Tesnar, Stefano Viel). The Duck prompts, tool-use loop, game policy, and scorer are theirs. Their public writeup discusses a milestone score of 1.21 on *their* original notebook; that result is not ours and is not claimed here.
- [Keith Tyser's Flash NVFP4 serving fork](https://www.kaggle.com/code/keithtyser/duck-qwen3-8-flash-next-nvfp4-mtp): pinned `keithtyser/qwen3-8-flash-next-nvfp4` (RadixArk / ModelOpt NVFP4, MTP3, offline vLLM, RTX Pro 6000). That fork is serving and runtime, not a new Duck policy.

**What we added**

- **S4** — ignore the top two HUD rows when deciding whether an action changed the interior; after two confirmed no-interior-change repeats of the same `(semantic state, action)`, tell the model. No global action ban. Reset on level change.
- **This notebook (S4b)** — the same guard, but the ignored HUD strip is the **top and bottom two rows**. Local public-25 traces labeled 226 top-only HUD-only pairs vs 487 outer-strip HUD-only pairs; S4 never saw the extra 261 bottom-strip cases.

**Scores (our account, Public LB)**

| Notebook | Public |
|---|---:|
| Tufa Duck original (their public notebooks) | their milestone writeup, not this fork |
| Our Flash NVFP4 serving-only (kernel v3) | 3.39, unlucky repeat 2.95 |
| S1 / S2 / S3 policy tries | 2.71 / 2.72 / 2.77 — rejected, not stacked |
| S4 top-HUD no-impact (kernel v7) | **3.70** |
| This notebook (S4b outer HUD) | not yet submitted |

Public scores on this competition are noisy (same Flash v3 moved 3.39 ↔ 2.95). Treat a single delta as a signal, not a proof. Code from Tufa/Keith remains with credit; the commentary in this notebook is ours.
"""

INTRO = """# ARC-AGI-3 — outer-HUD no-impact on Flash NVFP4

![Tufa Labs](attachment:tufa_labs.png)

Private competition notebook for **ARC Prize 2026 / ARC-AGI-3**. Internet is off. Select GPU **RTX Pro 6000** if you copy the kernel.

The attached solver is Tufa Labs' Duck harness. The serving stack is Keith Tyser's Qwen3.8-Flash-Next NVFP4 port. Tufa's forum writeup is [discussion 717133](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/discussion/717133); the [MLST interview](https://x.com/MLStreetTalk/status/2072326433922297975?s=20) is about *their* harness, not this fork.

This notebook installs the ARC runtime from the competition wheelhouse, imports the bundled Duck snapshot, loads the pickled benchmark, plays the games, and writes `/kaggle/working`. A real competition rerun (`KAGGLE_IS_COMPETITION_RERUN`) uses production budgets and the live Arcade. An interactive Save & Run is a **short smoke** (two public games, capped actions) so we can confirm the checkpoint loads without burning the 9-hour hidden rerun.

**Policy in this version.** After two confirmed repeats that leave the interior identical — including frames that only change the top or bottom HUD strips — the agent is told that action is no-impact in that semantic state. Interior motion is not banned.

Solver code lives in the attached dataset; this notebook is the Kaggle wrapper plus our HUD no-impact hook.
"""

SECTION_HEADERS = {
    "1. Environment and submission mode": """## 1. Environment and submission mode

Detect whether this is a real competition rerun (which minimises diagnostics), set the
framework's environment flags, and put the CUDA libraries on the linker path.
""",
    "2. Install the ARC runtime": """## 2. Install the ARC runtime

Install `arc-agi` from the offline competition wheelhouse (the Kaggle submission environment
has no internet).
""",
    "3. Locate the source bundle": """## 3. Locate the source bundle

Find the uploaded TAAF source dataset by its marker file, and record where Kaggle mounted
every attached input so setup commands and the solver can find them.
""",
    "4. Import the bundled source and run solver setup": """## 4. Import the bundled source and run solver setup

Put the snapshotted repositories on the path (this process and any child processes), then run
the solver's setup commands — installing wheels, fetching model weights, and so on.
""",
    "5. Load the benchmark": """## 5. Load the benchmark

Unpickle the deployment target and the benchmark, stamping the real submission state onto the
target and pointing the benchmark's outputs at the Kaggle working directory.
""",
    "6. Customization hook": """## 6. Customization hook

Solver settings and our S4b outer-HUD no-impact guard are applied here after the bundled Duck
runtime has loaded. Production budgets stay on the competition rerun; Save & Run stays a short smoke.
""",
    "7. Run the benchmark": """## 7. Run the benchmark

In a real competition rerun (`KAGGLE_IS_COMPETITION_RERUN`), wait for the Kaggle gateway and
play the **live competition Arcade**. Otherwise — an interactive Save & Run — play the
competition's **bundled environment files offline**, with no gateway required, so the notebook
runs end-to-end without a submission. Teardown commands run afterward even if the run raises.
""",
    "8. Show the diagnostics": """## 8. Show the diagnostics

A non-submission run writes `diagnostics.html` to `/kaggle/working`; it is rendered inline below
(and downloadable from the working directory). You should be able to click around through the links.
""",
}


def cell_text(cell: dict) -> str:
    source = cell.get("source") or ""
    return "".join(source) if isinstance(source, list) else str(source)


def set_cell_text(cell: dict, text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    cell["source"] = text.splitlines(keepends=True)


def _heading_key(text: str) -> str | None:
    heading = text.lstrip().splitlines()[0].strip() if text.strip() else ""
    for needle in SECTION_HEADERS:
        if heading == f"## {needle}" or heading.startswith(f"## {needle}"):
            return needle
    return None


def rewrite_markdown_cells(nb: dict) -> None:
    for cell in nb.get("cells") or []:
        if cell.get("cell_type") != "markdown":
            continue
        text = cell_text(cell)
        stripped = text.lstrip()
        if stripped.startswith("## About this fork"):
            set_cell_text(cell, ABOUT_FORK)
            continue
        if (
            "# Tufa Labs ARC3 submission" in text
            or stripped.startswith("# ARC-AGI-3")
        ):
            set_cell_text(cell, INTRO)
            continue
        key = _heading_key(text)
        if key is not None:
            set_cell_text(cell, SECTION_HEADERS[key])
            continue
        cleaned = text.replace("â€”", "—").replace("â€“", "–")
        if cleaned != text:
            set_cell_text(cell, cleaned)


def joined_markdown(nb: dict) -> str:
    parts = []
    for cell in nb.get("cells") or []:
        if cell.get("cell_type") == "markdown":
            parts.append(cell_text(cell))
    return "\n".join(parts)


def assert_our_prose(text: str) -> None:
    for blob in FORBIDDEN_FOREIGN_FIRST_PERSON:
        if blob in text:
            raise AssertionError(f"foreign first-person leftover: {blob!r}")
    if "## About this fork" not in text:
        raise AssertionError("missing About this fork")
    if "3.70" not in text:
        raise AssertionError("missing S4 public score 3.70")
    if "Tufa Labs" not in text:
        raise AssertionError("missing Tufa credit")
    if "Keith Tyser" not in text:
        raise AssertionError("missing Keith Tyser credit")
