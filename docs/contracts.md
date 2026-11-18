# Input and review rules

## Files

Use a Markdown file or folder. Results are JSON files with matching names. `--output-dir` chooses a separate result folder; stdout stays empty and progress uses stderr. Writes are atomic. Malformed cases produce `INCOMPLETE`; the batch continues.

See the [starter input](../examples/starter_case.md) and [run commands](../README.md).

## Markdown sections

| Section | Contents |
|---|---|
| Ticket details | Field declarations, such as `waiting: number (minutes)`, `urgent: yes-no`, `category: choice (billing,technical)`. |
| Company rules | Named `###` records containing rule paragraphs, in priority order. |
| Specification | Named rules with `When`, `Route` and optional `Company rule`. |
| Workflow | `Start`, named steps, conditions, `Yes`/`No` destinations and explicit `Code` links. Terminal steps use `Route`. |
| Python | Named snippets containing literal fenced Python. |
| Approvals | `None.` or named change records with authority/version metadata and replacement wording. |
| Example tickets | Optional actual field values; use `###` headings for multiple tickets. |

Keep metadata bullets together and separate them from paragraphs/code with a blank line. Unknown/duplicate properties, missing sections and malformed fences are rejected. CRLF is accepted. IDs are arbitrary identifiers, not proof of correct behavior. Every snippet must be linked; full code coverage requires an entry-linked snippet.

For a new case without approvals, revision/version defaults to 1. Company/specification order defaults to zero-based document position. Generated source references use `policy/paragraph/<order+1>`; these are labels, not external files. Explicit values override defaults. Later revisions require explicit versions. Cases with approvals require an explicit revision and artifact/rule versions. Conditions, links and approval authority are never inferred.

Specification/workflow `When` accepts `always` and `never` as boolean constants. JSON schemas describe the parsed internal data and output; internal operators are `missing`, `eq/ne/lt/lte/gt/gte`, `and/or/not` and boolean constants. Original JSON under `evaluation/inputs/` is frozen comparison data; the application does not use it as its default input.

## Rule language

Supported examples:

```text
If category is missing, send it for manual review.
If urgent is yes and category is "technical", send it to the priority queue.
Escalate tickets waiting 30 minutes or more.
Send all remaining tickets to the normal queue.
```

Legacy `IF/WHEN ... THEN ...` and `OTHERWISE THEN ...` also work. Comparisons support equality, inequality, inclusive/exclusive boundaries, `at least`, `at most`, `more than`, `less than`, `exactly` and `not equal to`. Numeric suffixes `or more`, `or less` and `or fewer` are supported. `NOT`, `AND`, `OR` use that precedence; parentheses override it. The first matching rule wins. Exactly one unconditional default must be last.

Fields are whole-number quantities, booleans or declared string choices. Units are seconds, minutes, hours or count; counts cannot mix with time. Source decimal cutoffs use exact fractions. Markdown conditions reject conversions that would round; Python floats retain their actual binary value. No field arithmetic or field-to-field comparisons are supported.

Missing keys and null are missing. Comparisons with missing values are false except inequality, which is true; `NOT` negates the result. Quote multiword categories and exact custom route names. Keywords/English aliases ignore case; enum values and custom route names retain it. Field underscores can become spaces; `waiting` also accepts `waiting time`. Ambiguous aliases are refused. Singular time units work. Known destinations map manual review/priority queue/normal queue/escalate to manual/priority/normal/escalation; custom destinations require exact names.

Unsupported wording remains unreviewed. Neither code nor AI may invent a missing requirement. Original wording and source/approval references remain evidence.

## Approvals

A record supplies rule reference, status, inclusive revision range, sequence, base/new versions and replacement text. Only applicable top-level `approved` records change policy. Apply them by sequence; each base version must match the preceding effective version and increase it. Replacement preserves rule order. Structural changes need a new source bundle.

Duplicate IDs, repeated sequence/version claims, broken chains, unknown references, inverted scopes or applicable approved/rejected claims for the same rule version are unresolved. No convenient version is selected. Proposals and out-of-scope decisions do not override policy. Prose/comments cannot grant approval. Revocation is not defined.

## Python and workflow

Each snippet contains one undecorated, unannotated `def route(ticket):`, without defaults or extra arguments. Supported statements are `if/elif/else` and literal string returns. Conditions support booleans, field-to-literal comparisons and `is None`/`is not None`. Read fields using `ticket.get("field")` or `ticket["field"]`; numeric constants use native units.

Imports, assignments, loops, arithmetic, general calls, global code, chained comparisons and other Python constructs are unsupported. Syntax errors are blockers; unsupported valid code remains incomplete. The reviewer interprets a restricted syntax tree and never executes submitted Python. Absent-key access, invalid null comparisons and missing returns can produce behavioral findings.

Compare reachable workflow paths, including missing destinations and cycles. Report unreachable linked code as unreviewed. Entry code implements the complete route. Downstream snippets are compared with policy only on policy-consistent workflow paths; otherwise disclose `nested_code_context` and require a rerun after the workflow is fixed. Syntax inspection and entry/valid-path checks continue.

## Example tickets

Use declared `field: value` lines. Yes/no and true/false are booleans. Categories must be declared; double-quoted strings are accepted. Omitted/blank values or `missing` omit a key; `null` keeps an explicit null. Quote literal categories named missing/null. Integers may include time units; exact conversion must yield a whole native-unit quantity. Unknown fields, repeated fields and invalid values are rejected.

The Python API accepts `review(bundle, provided_tickets=[...])`; explicit arguments override embedded examples. Values use native units. `ticket_results` contains each distinct ticket's expected route and specification/workflow/code routes. Full-domain review still runs. Example values are excluded from the model's policy request.

## Checks, AI and results

The checker combines numeric boundary/interval representatives, every declared boolean/choice value, and absent/null states. Their Cartesian product covers every predicate truth region in the supported domain. This is exhaustive within that domain, not arbitrary prose/Python or sampling.

CLI results contain `status`, `summary`, `mode`, `findings`, `coverage`, `check_results`, `resources` and optional nonempty `ticket_results`. Findings keep the problem, severity, rule reference, artifact/version, source and relevant Python evidence, correction and counterexample. Repeated trace quotes and serialized workflow/specification records are omitted. `coverage.rules` maps rule IDs to their review status; `coverage.unreviewed` retains every incomplete scope and reason. Check results list check names and statuses.

Each finding uses a readable `location`, such as `Workflow step 'check_wait': condition` or `Python snippet 'main', line 4`, and keeps its exact machine location in `reference`. An unknown location says `Specific location could not be identified`. Locations identify candidate repair regions, not a uniquely proven root cause. Exact references use `/rules/index`, `/nodes/index`, `snippet_id:line` or `/approvals/index`.

The same JSON ends with `audit`, containing unchanged model attempts, configuration, request/response hashes and provenance. No second file or folder is created. Supplied results use this presentation of their recorded reviews; formatting is not new inference. The Python `review()` API and frozen historical reports retain the detailed format, including technical `location` and readable `location_description` fields.

The model sees current effective source/approval evidence, declared field meanings and computed interpretations. Unresolved rules are explicitly scoped. Implementation and superseded text cannot define policy. Validate exact requested coverage, rule-bound citations, quotes and conflicting claims. Output schema constraints do not prove correct judgments. Ambiguity contradicting a complete declared-language interpretation is rejected; retries receive recorded feedback. Genuine unresolved wording, repeated invalid claims and transport failures stay incomplete. Model corrections never edit inputs.

- `PASS` / exit 0: all required checks complete, no blocker or unreviewed scope.
- `CHANGES_REQUIRED` / exit 1: an evidenced blocker exists; disclose incomplete checks too.
- `INCOMPLETE` / exit 2: no confirmed blocker, but review cannot finish.

Real AI defaults to local `qwen3.5:9b`; `--offline` explicitly uses synthetic responses. No downloads, client fallback or cache. Edits are re-reviewed. Each attempt records request/response fingerprints, raw response, configuration, validation result and timing; retries retain feedback and rejected responses.

## Limits

- Input: 1,000,000 bytes; 8 fields; 64 source rules; 128 nodes; 32 snippets; 128 approvals/tickets.
- Snippet: 20,000 characters and 1,500 syntax-tree nodes; schema/expression nesting is bounded.
- Comparison: at most 100,000 representative combinations; exceeding it stays incomplete.
- Model: 32,768-token context, 2,048 output tokens, 200 KB request ceiling and a stricter byte-based context allowance reserving output/framing; 64 KB response; two attempts; 90-second socket timeout.

Oversized data is rejected, never silently truncated. Retry inputs are rechecked. Socket timeouts bound inactivity, not absolute elapsed time. Fake failures do not measure real latency. Offline checks need no model or network; live inference uses the installed server's hardware defaults.
