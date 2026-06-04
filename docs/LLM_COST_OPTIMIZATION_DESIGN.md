# LLM Cost Optimization — Design Document

Status: **Draft v0.1**
Last updated: 2026-04-27
Trigger: OpenAI 429 (quota exceeded) hit during a Phase 2 run on the Indian
employment contract.

---

## 1. Problem

Phase 2 of the web research sub-agent added an **LLM-driven query planner**
that fires once per clause passing the triage gate. Combined with the
existing per-clause analysis and evaluator calls, plus reflection loops,
total LLM calls per document have grown enough to push low-tier OpenAI
accounts past their monthly quota during routine testing.

This document scopes three independent optimizations to reduce LLM call
volume without changing the architecture, plus one larger refactor parked
as out-of-scope.

## 2. Current cost accounting (per document)

For a 15-clause Indian contract, ~5 high-stakes clauses passing triage:

| Stage                              | Phase 1 | Phase 2 |
|------------------------------------|---------|---------|
| Intake — document type             | 1       | 1       |
| Intake — jurisdiction              | 1       | 1       |
| Query planner (one per triaged clause) | 0   | **5**   |
| Analysis (capped at MAX_CLAUSES=20) | 15     | 15      |
| Evaluator                          | 15      | 15      |
| Output recommendations             | 1       | 1       |
| **Total per pass**                 | **33**  | **38**  |
| With one analysis reflection       | 63      | 68      |
| With one analysis + one research reflection | 78 | 88   |

At GPT-4-class pricing (~500–1500 input + ~200–500 output tokens per call),
that's roughly $0.50–$1.50 per worst-case document run.

## 3. Optimization options

### 3.1 Cache query plans by (clause_type, jurisdiction)  [recommended first]

**What.** Within a single document run, memoize the query planner's output
keyed on `(clause_type, jurisdiction)`. Two `termination` clauses in the
same Indian contract share one LLM-planned query list.

**Why it's the right call.** It's a correctness improvement, not a hack.
Re-planning identical queries is pure waste — the planner has no
clause-specific input strong enough to justify a fresh call.

**Cost reduction.** ~30–50% of planner calls eliminated on typical
contracts, which have several clauses of the same type.

**Implementation.**
- Add an instance-level dict `self._query_cache: Dict[Tuple[str, str, bool], List[str]]` on `WebResearchSubAgent`. Key is `(clause_type, jurisdiction, broaden)`.
- In `_plan_queries`, check the cache before invoking the LLM; populate on success.
- Cache lifetime = sub-agent lifetime = document analysis lifetime (the planner is constructed inside `ResearchAgent` per `PlannerAgent`, which is rebuilt per Streamlit session — natural scope).
- *Don't* cache across documents — a new doc may have a different clause emphasis.

**Lines changed.** ~10 in [src/agents/web_research_subagent.py](../src/agents/web_research_subagent.py).
No state-shape changes, no new files.

**Risk.** None meaningful. Cache key is fully deterministic; clause-content
specificity is already absorbed by the clause_type bucket.

### 3.2 Make the LLM planner opt-in, default to templates  [recommended second]

**What.** Add a constructor flag (and env var
`WEB_RESEARCH_LLM_PLANNER=true|false`) that gates whether `_plan_queries`
calls the LLM at all. When off, always use the existing template fallback.

**Why.** The template path is already implemented (Phase 1) and tested. It
just isn't the default any more. Flipping the default for cost-constrained
users is one boolean.

**Cost reduction.** Eliminates **all** planner calls. Phase 2 query
quality regresses to Phase 1 (still functional — Phase 1 produced real
results from Indian Kanoon).

**Implementation.**
- Read env var in `WebResearchSubAgent.__init__`.
- In `_plan_queries`: if disabled, skip directly to `_template_query`.
- Document the trade-off in `.env.example` and the README.

**Lines changed.** ~5 in [src/agents/web_research_subagent.py](../src/agents/web_research_subagent.py)
+ 1 line in [.env.example](../.env.example).

**Risk.** Quality regression for clauses where the template is generic
(e.g., `miscellaneous`) — those see the biggest benefit from LLM planning.
Manageable: keep planner on for the long-tail clause types, off for the
common ones. But that's premature optimization; flat default is fine.

### 3.3 Switch the project's default model to a cheaper variant

**What.** Change the default `openai_model` from `gpt-5.4` (currently used
across all agents) to `gpt-4o-mini` or similar.

**Why.** 5–10× cost reduction at OpenAI's price points; analysis and
evaluator quality typically degrades modestly, often within tolerance for
this use case.

**Implementation.**
- Single change in [src/agents/planner_agent.py](../src/agents/planner_agent.py)
  `__init__` default.
- Each sub-agent already accepts `model` as a parameter, so no other
  surgery needed.
- Optionally split: keep premium model for `OutputAgent` recommendations
  (user-facing prose), use mini for analysis / evaluator / planner.

**Lines changed.** 1 default value, optionally 1 per agent if mixing
models per role.

**Risk.** Quality regression in clause analysis. Needs a side-by-side
comparison run on the sample contracts before committing.

### 3.4 Combine analysis + evaluator into one LLM call  [out of scope]

**What.** A single prompt that produces both the clause analysis *and* a
self-evaluation of confidence + failure mode in one round-trip.

**Why not now.** Saves ~15 calls/doc (the largest single win) but changes
the agent boundary, the reflection loop semantics, and the tool contracts.
This is a Phase 5-class refactor, not a tweak. Park.

## 4. Recommended sequence

1. **Land 3.1 (caching)** — small, no-risk, design-correct. Single PR.
2. **Land 3.3 (cheaper default model)** — single line, but gate on a
   side-by-side quality comparison on `Indian_Employment_Agreement.txt`,
   one UK contract, one US contract.
3. **Optionally add 3.2 (planner opt-in flag)** — only if cost still bites
   after 3.1 + 3.3. Keeps the LLM planner as the default and lets
   constrained users opt out via env var.
4. Defer 3.4 indefinitely.

After step 1 alone, expect cost per document to drop ~10–15% on typical
contracts. After 1 + 3, expect 60–80% reduction.

## 5. Verification plan

- **3.1 caching.** Add a counter to `_plan_queries` that logs cache hits
  vs. misses at INFO. Run on the Indian sample, confirm hit rate > 0 for
  documents with repeated clause types.
- **3.3 model swap.** Manual side-by-side: same document, two runs (one per
  model). Compare risk levels assigned, flags raised, plain-summary
  readability. If material disagreement on >2 of ~15 clauses, defer the swap.
- **3.2 planner opt-in.** Cover both code paths in a smoke test — env var
  off, env var on, no env var.

## 6. Open questions

1. **Cache invalidation across reflection passes.** When the evaluator
   sends us back to research with `clauses_to_rerun`, should the cache
   carry over? Argument for: same clause type, same jurisdiction → same
   query. Argument against: a re-research pass exists *because* the prior
   research was thin — re-planning might help. Lean toward
   carrying-over; on a re-research pass the second LLM call would be
   gated by the cache hit anyway and produce the same query.
2. **Per-role model assignment.** Worth the config complexity, or keep
   one model for the whole pipeline? Probably keep simple — one model
   project-wide — until we have evidence that a split helps.
3. **Telemetry.** Should we log cumulative LLM call counts per document
   run so users can see cost-per-doc directly in the UI? Cheap to add and
   would prevent re-discovering the quota issue. Not in this design's
   scope but flagged for follow-up.
