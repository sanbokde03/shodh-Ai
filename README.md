# Company rule reviewer

Checks company rules against a specification, workflow and Python code. Input: Markdown. Output: JSON.

## Setup

Use Python **3.14.6**. No Python packages need installing. Clone with `git clone https://github.com/sanbokde03/shodh-Ai.git shodh-reviewer`, or extract the ZIP. Run commands from the project folder:

```bash
cd shodh-reviewer
```

Real AI requires Ollama running at `127.0.0.1:11434` with `qwen3.5:9b` installed. Nothing is downloaded automatically. `--offline` uses synthetic AI responses while keeping the rule, workflow and code checks.

## Run supplied cases

```bash
# All cases, offline
python3 -m reviewer inputs --offline --output-dir results_offline

# All cases, real AI
python3 -m reviewer inputs --output-dir results_live

# One case, offline
python3 -m reviewer inputs/defect_boundary.md --offline --output-dir results_offline

# One case, real AI
python3 -m reviewer inputs/defect_boundary.md --output-dir results_live
```

Start with [correct routing](inputs/valid_base.md), a [workflow mistake](inputs/defect_boundary.md), or [example tickets](examples/ticket_demo.md).

## Add your own input

Copy the [starter template](examples/starter_case.md):

```bash
mkdir -p my_inputs
cp examples/starter_case.md my_inputs/my_case.md
```

Edit the copy. Change `# Case: starter_case` to `# Case: my_case`. Enter your company rules, proposed specification, workflow and Python. Keep the section headings and references. Optional **Example tickets** holds actual values to try.

```bash
# Offline
python3 -m reviewer my_inputs/my_case.md --offline --output-dir my_results_offline

# Real AI
python3 -m reviewer my_inputs/my_case.md --output-dir my_results_live
```

## Read results

Each input produces a JSON file with the same name in the chosen result folder.

`outputs/` contains saved real-AI results kept as assessment evidence. The commands above save your new offline runs in `results_offline/` and real-AI runs in `results_live/`. Without `--output-dir`, both modes write to `outputs/` and can overwrite saved results.

```bash
python3 -m json.tool results_offline/defect_boundary.json
python3 -m json.tool results_live/defect_boundary.json
python3 -m json.tool my_results_offline/my_case.json
python3 -m json.tool my_results_live/my_case.json
```

- `status`: `PASS`, `CHANGES_REQUIRED` or `INCOMPLETE` (exit codes 0, 1 or 2).
- `mode`: `offline` or `ai`.
- `findings`: problems, readable locations, exact references, evidence, corrections and counterexamples.
- `ticket_results`: expected and actual routes for supplied tickets.
- `coverage`, `check_results`, `resources`: review scope, checks and runtime/calls/retries.
- `audit`: model responses and technical records, kept at the bottom of the same file. You can skip this when reading the result.

Supplied cases include deliberate defects and missing information. Exit codes 1 and 2 can be expected. AI failures remain `INCOMPLETE`; there is no fake fallback. Use separate input and output folders.

## Tests and evaluation

```bash
python3 scripts/verify.py
```

Expected exit: 0. Runs tests, frozen evaluations, checkpoint comparison, ablation, debugging regressions and saved AI-response replay. No model server or network is needed.

## Details

- [Input format and supported language](docs/contracts.md)
- [Engineering note and AI-assistance disclosure](docs/engineering-note.pdf)
- [Evaluation results (JSON)](reports/summary.json)
