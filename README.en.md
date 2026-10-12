# CCF BDCI 2026 · Traceable Research Agent

[简体中文](README.md)

This project builds a **semi-automated research agent on openJiuwen / JiuwenSwarm** for the CCF BDCI 2026 research-paper generation challenge. Given prepared research materials, the agent organizes experiments, analyzes results, and produces an English paper using the ICLR template. This repository contains the **SOURCE12** framework snapshot, research configuration, reviewed paper, and experiment records that can be checked offline.

## What the project does

- **Research workflow:** Configures Design, PreparedCode, Execution, Reflection, and Reporting stages to organize inputs, execute experiments, and generate papers. Actual stage execution is established by each run's reports.
- **Artifact Provenance Gate (APG):** Modifies JiuwenSwarm itself to check the PDF, successful terminal Reporting state, declared artifact paths and existence, model-call ledger, and citation keys in a reliable LaTeX AUX file before publishing completion. The gate makes no model or network calls. The citation check is SKIPPED when no reliable AUX is available.
- **Execution and cost controls:** Adds request-level pause, deadline, and budget admission checks, with actual model usage and settlement records. Calls with unknown outcomes are not automatically retried.
- **Traceable evidence:** Preserves paper sources, framework patches, run records, resource accounting, and frozen requests/responses for replay without new model calls.

APG checks artifact integrity; it does not establish scientific truth. The available evidence supports a semi-automated workflow with prepared inputs, rather than independent topic selection, experiment implementation from scratch, or autonomous research across topics.

## Repository layout

| Path | Contents |
| --- | --- |
| code/jiuwenswarm/ | SOURCE12 framework source with 12 applied patch layers, dependency lock, and tests |
| code/research_project/ | Research entry points, pipeline, frozen inputs, and budget templates |
| code/apg_pilot/, code/patches/ | APG pilot artifacts and framework patches |
| paper/ | Seven-page English ICLR PDF and LaTeX source |
| docs/ | Architecture, module calls, innovations, and reproduction instructions |
| evidence/ | Run records, resource accounting, and offline replay scripts |
| EXPORT_MANIFEST.json | File hashes, publication exclusions, and export validation records |

## Usage

### 1. Clone the repository

The documented primary environment is Windows PowerShell 7 with Python 3.12. Installing locked framework dependencies also requires uv.

~~~powershell
git clone https://github.com/SHIChenhao-0801/CCF_BDCI_2026.git
Set-Location CCF_BDCI_2026
~~~

### 2. Replay frozen results without a model API

Run this command from the repository root. It reads frozen records and writes its output outside the repository:

~~~powershell
$replayOutput = Join-Path (Split-Path (Get-Location).Path -Parent) 'ccf-bdci-replay'
New-Item -ItemType Directory -Path $replayOutput -Force | Out-Null
py -3.12 -I -B -X utf8 evidence/tokenmatched-holdout240-completed-20261009/replay.py --output (Join-Path $replayOutput 'study240.json')
~~~

The publication copy was verified to produce **237 complete pairs, 3 missing items, 0 model calls, and 0 network requests**. See the [reproduction guide](docs/REPRODUCE.md), currently in Chinese, for additional replay commands and details.

### 3. Install framework dependencies and run regression tests

~~~powershell
Set-Location code/jiuwenswarm
uv sync --frozen --group test
uv run --frozen --group test python -B -m pytest tests/unit_tests/rsi -o addopts= -p no:cacheprovider --asyncio-mode=auto -q
~~~

The historical local SOURCE12 regression result was **442 PASS, 2 Windows permission SKIP, and 0 FAIL**. This GitHub preparation checked copied-file identities and the offline replay above; it did not rerun the full regression suite.

### 4. Run the agent to generate a new paper

Follow [docs/REPRODUCE.md](docs/REPRODUCE.md) to prepare your own private model environment, an external budget ledger, and a request policy. Start the budget proxy, then run code/research_project/run_agent.py. Required model configuration includes DEEPSEEK_API_KEY, a verified DEEPSEEK_API_BASE, and DEEPSEEK_MODEL. This step consumes model API credits: set a budget first and keep real credentials out of Git.

To rebuild the paper, use a LaTeX toolchain in paper/source/ and run latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex. Rebuilding can change PDF bytes; the included paper.pdf preserves the reviewed version.

## Paper and evidence limits

- The paper is *Artifact Gates and Bounded Verifier Feedback in a Traceable Research Agent*, a seven-page ICLR-format manuscript. Its historical Reviewer score of 6.3 is not a competition score.
- The frozen paper reports a 24-task pilot and an earlier 102/240 checkpoint. The complete 237/240 results and other later analyses are separate supplementary evidence, not retroactively included in that PDF.
- This repository is a source-and-evidence snapshot of the final delivery. It excludes upstream Git history, the Reviewer Access Token, private review receipts, and local working directories. References to those private paths in original submission documents remain as provenance notes.
- The framework contribution commit is dae143d9ac19cb5e05864d459b8cd89de96de908. See [framework_contribution.md](framework_contribution.md) and [resource_report.md](resource_report.md). PR merge, current CI, and competition receipt status must be verified against their respective platforms.

Upstream and third-party license files are retained. Each component remains subject to its existing terms; this repository does not assign a new blanket license to the entire artifact bundle.
