# Web Research Sub-Agent — Implementation Plan

Status: **Draft v0.1**
Source of truth: [WEB_RESEARCH_SUBAGENT_DESIGN.md](WEB_RESEARCH_SUBAGENT_DESIGN.md)
Last updated: 2026-04-27

This plan maps the design into concrete, sequenced work. Each phase has an
exit criterion — do not advance until met.

---

## 0. Sequencing overview

```
Phase 0  Foundation              ── state shape, deps, config        (~½ day)
   │
Phase 1  Skeleton end-to-end     ── prove data path through DAG      (~1 day)
   │
Phase 2  LLM query planning +    ── tier 1 + tier 2 + Tavily/DDG     (~1½ days)
         two-tier search
   │
Phase 3  Citations in output     ── OutputAgent + Streamlit UI       (~½ day)
   │
Phase 4  (stretch) Session FAISS ── promote scraped pages            (deferred)
```

Phase 0 is hard-blocking; phases 1→3 are sequential. Phase 4 is optional.

---

## 1. Phase 0 — Foundation

**Goal.** Make the state shape, dependencies, and configuration ready so the
rest of the work has a stable target.

### 1.1 State shape changes

**Modify** [src/agents/state.py](../src/agents/state.py):

- Add dataclasses:
  - `WebResult(url, source_name, title, snippet, retrieved_at, relevance, tier)`
  - `ClauseResearch(clause_id, local_context, web_results: List[WebResult])`
- Update `AgentState` TypedDict:
  - `research_context: Dict[str, ClauseResearch]`  (was `Dict[str, str]`)
  - `jurisdiction: str`  (new; default `"unknown"`)
  - rename `reflection_count` → `analysis_reflection_count`
  - add `research_reflection_count: int`
  - add `clauses_to_rerun: List[str]`  (clause_ids flagged by evaluator for re-research; empty on first pass)

### 1.2 Migrate existing consumers of `research_context`

`research_context` is referenced in seven source files. The migration
strategy keeps the **downstream tool contracts unchanged** (still accept
`research_context: str`), pushing the dict→string formatting up into the
agent layer. This minimizes Phase 0 surface area.

**Modify**:
- [src/agents/research_agent.py](../src/agents/research_agent.py) — return `ClauseResearch` per clause (with `web_results=[]` for now).
- [src/agents/analysis_agent.py](../src/agents/analysis_agent.py) line 39 — read `clause_research.local_context` instead of the flat string before passing into `clause_analyzer_tool`.
- [src/agents/evaluator_agent.py](../src/agents/evaluator_agent.py) line 42 — same: extract `local_context` from `ClauseResearch` before passing into `evaluator_tool`.
- [src/agents/output_agent.py](../src/agents/output_agent.py) — same access pattern; no rendering of web results yet (deferred to Phase 3).
- [src/agents/planner_agent.py](../src/agents/planner_agent.py) line 70 — initialize the new state fields in `analyze_document()`.

**Unchanged in Phase 0** (string contract preserved):
- [src/tools/clause_analyzer_tool.py](../src/tools/clause_analyzer_tool.py) — keeps `research_context: str` parameter.
- [src/tools/evaluator_tool.py](../src/tools/evaluator_tool.py) — keeps `research_context: str` parameter.

In Phase 3, `ResearchAgent` will format the string passed to these tools to
also include a brief "Web sources:" bullet block when `web_results` is
non-empty, so the analysis LLM sees citations as context. The tool API
itself does not need to change.

### 1.3 Intake — emit jurisdiction

**Modify** [src/agents/intake_agent.py](../src/agents/intake_agent.py):
extend the existing LLM classification call to also return one of
`{"IN", "UK", "US", "EU", "unknown"}`, write to `state["jurisdiction"]`.

### 1.4 Dependencies

**Modify** [requirements.txt](../requirements.txt) — add:
```
httpx>=0.27
trafilatura>=1.9
beautifulsoup4>=4.12
tavily-python>=0.3        # optional at runtime, gated by env var
```

### 1.5 Configuration

**Modify** `.env.example` (create if absent) and document in
[README.md](../README.md):
```
TAVILY_API_KEY=                                     # optional
WEB_RESEARCH_ENABLED=true
WEB_RESEARCH_PER_DOC_BUDGET_SEC=60
WEB_RESEARCH_PER_CLAUSE_TIMEOUT_SEC=12
WEB_RESEARCH_CACHE_TTL_DAYS=14
```

### 1.6 Cache directory

**New** `data/web_cache/` (gitignored). Add `data/web_cache/` to
[.gitignore](../.gitignore).

### Phase 0 exit criteria

- `streamlit run app.py` still works end-to-end on a sample doc.
- Manual smoke test: run each of `Indian_Employment_Agreement.txt`,
  one UK contract, one US contract through the DAG; confirm
  `state["jurisdiction"]` is populated correctly per doc.
- No web research is happening yet — `web_results` is `[]` for every clause.
- `analysis_agent` and `evaluator_agent` produce identical outputs to the
  pre-migration baseline on the same sample doc (the formatted string
  passed into the unchanged tools must match). Capture a baseline run
  *before* this phase to compare against.

### Phase 0 — out of scope

[tests/test_legal_assistant.py](../tests/test_legal_assistant.py) tests the
*legacy* `LegalAssistantAgent` (single-agent), not the multi-agent DAG, and
already mocks a class (`ChatGoogleGenerativeAI`) the codebase no longer
imports. It does **not** reference `research_context`. Updating or
replacing this test file is its own concern, separate from the web research
work — flagged for a future cleanup task. **Phase 0 does not gate on
`test_legal_assistant.py`** beyond not making it worse.

---

## 2. Phase 1 — Skeleton end-to-end

**Goal.** A real (but minimal) web fetch happens for at least one clause on
a sample document, populating `web_results` with a real URL, and the
evaluator's reflection loop can route back to research. No LLM query
planning yet — hardcoded query templates per clause type.

### 2.1 New tool: WebFetchTool

**New** `src/tools/web_fetch_tool.py`:

- `httpx.Client` with `timeout=10`, `follow_redirects=True` (max 3),
  `headers={"User-Agent": "LawAgent-Research/0.1 (+contact)"}`.
- `fetch(url) -> Optional[FetchResult]` where `FetchResult = (status, body, final_url)`.
- Body cap 2 MB; truncate and warn beyond that.
- Disk cache at `data/web_cache/<sha256(url)>.html`, TTL from env
  (`WEB_RESEARCH_CACHE_TTL_DAYS`). Cache key is the *original* URL pre-redirect.
- robots.txt: `urllib.robotparser`, results cached per-domain in-memory for
  the process lifetime. Disallowed → return `None`.
- Per-domain rate limit: simple in-memory token bucket
  (1 req/sec, burst 3). Sleep up to the timeout; if still blocked, return
  `None`.
- Never raises; all exceptions → `None` + debug log.

**Test** `tests/test_web_fetch_tool.py` — mock `httpx` with
`respx`, cover: cache hit, robots disallow, 5xx, timeout, redirect chain,
oversized body. (Add `respx>=0.21` to dev deps if not present.)

### 2.2 New tool: ContentExtractor

**New** `src/tools/content_extractor.py`:

- Primary: `trafilatura.extract(html, include_comments=False, include_tables=True)`.
- Fallback (when trafilatura returns < 200 chars): bs4 with a tag denylist
  (`script, style, nav, footer, aside, form`).
- Truncate to 4 KB.
- Paywall heuristic: reject if length < 200 chars *or* matches keyword list
  (`subscribe to read|sign in to continue|premium content`, case-insensitive).
- Pure function: `extract(html, url) -> Optional[str]`.

**Test** `tests/test_content_extractor.py` — fixtures: a real Indian Kanoon
HTML snapshot, a paywall stub, an empty-body page. Assert correct outcomes.

### 2.3 New tool: WebSearchTool (Phase 1 stub)

**New** `src/tools/web_search_tool.py`:

- Define abstract `SearchBackend` with `.search(query, include_domains, max_results)`.
- Implement `DDGHTMLBackend` only (no Tavily yet — Phase 2). Best-effort
  HTML scrape of `https://html.duckduckgo.com/html/?q=...`.
- `WebSearchTool` selects backend based on env at init; for Phase 1 it just
  uses DDG.
- Always returns at most `max_results` `SearchHit(url, title, snippet)`,
  even on failure (empty list).

**Test** `tests/test_web_search_tool.py` — mock the HTTP layer with `respx`,
assert parsing, query-construction with `site:` operators, and graceful
empty return.

### 2.4 New: WebResearchSubAgent (Phase 1 form)

**New** `src/agents/web_research_subagent.py`:

- Constructor takes `WebSearchTool`, `WebFetchTool`, `ContentExtractor`,
  jurisdiction whitelist mapping, and timing budgets.
- `research(block, jurisdiction, allow_tier2=False) -> List[WebResult]`:
  1. Build query from a hardcoded template per `clause_type` (e.g.
     `termination → "{clause_type} clause case law {jurisdiction}"`).
  2. Search Tier 1 with `include_domains` from the jurisdiction whitelist.
     If no jurisdiction, return `[]` in Phase 1.
  3. Take top 3 hits, fetch each via `WebFetchTool`.
  4. Extract main text via `ContentExtractor`.
  5. Build `WebResult` (no relevance scoring yet — set `relevance=1.0`,
     `tier=1`).
  6. Return list (≤ 3).
- Per-clause hard timeout enforced via wall-clock check between steps.
- Catches all exceptions internally; logs at `INFO` for failures.

### 2.5 Wire into ResearchAgent

**Modify** [src/agents/research_agent.py](../src/agents/research_agent.py):

- Construct `WebResearchSubAgent` in `__init__`.
- In `run()`:
  - If `state["clauses_to_rerun"]` is non-empty (re-research pass), only
    re-process those clauses; preserve others from existing
    `state["research_context"]`. Pass `allow_tier2=True` on rerun.
  - For each (re-)processed clause:
    - Call existing local retrieval → `local_context`.
    - Apply triage gate (§4 of design) → decide if web research runs.
    - If yes, call `WebResearchSubAgent.research(...)` with the per-document
      budget timer.
    - Build `ClauseResearch(clause_id, local_context, web_results)` and put
      it on the state map.
- Honor master switch `WEB_RESEARCH_ENABLED` — when `false`, skip the
  sub-agent entirely.

### 2.6 Triage gate

**New** helper inside `research_agent.py` (private function):

```python
def _should_web_research(block, local_result, jurisdiction, force=False) -> bool:
    if force: return True
    if jurisdiction == "unknown": return False  # Phase 1 only — Phase 2 enables tier 2
    if _looks_like_statute_citation(block.content): return True
    if block.clause_type in HIGH_STAKES_TYPES: return True
    if len(local_result) < 200: return True
    return False
```

`HIGH_STAKES_TYPES = {"indemnity", "liability", "ip_assignment", "dispute_resolution", "governing_law"}`.

`_looks_like_statute_citation` is a regex hit on patterns like
`Section \d+`, `§\s*\d+`, `Act,?\s+\d{4}`, `Article \d+` — kept simple.

### 2.7 Reflection loop in evaluator + planner

**Modify** [src/agents/evaluator_agent.py](../src/agents/evaluator_agent.py):

- Replace `should_reflect` two-way return with three-way:
  `"reflect_research" | "reflect_analysis" | "output"`.
- Decision rules:
  - If `analysis_reflection_count >= MAX_ANALYSIS_REFLECTIONS` and
    `research_reflection_count >= MAX_RESEARCH_REFLECTIONS` → `output`.
  - For each low-confidence clause, the evaluator's existing rationale text
    is prompted to also classify the failure as
    `missing_context | weak_reasoning`. Aggregate:
    - if any `missing_context` and budget remains → `reflect_research` and
      populate `state["clauses_to_rerun"]` with those clause IDs.
    - else if any `weak_reasoning` and budget remains → `reflect_analysis`.
    - else → `output`.

**Modify** [src/agents/planner_agent.py](../src/agents/planner_agent.py):

- Extend the conditional-edge mapping:
  ```python
  workflow.add_conditional_edges("evaluator", EvaluatorAgent.should_reflect, {
      "reflect_research":  "research",
      "reflect_analysis":  "analysis",
      "output":            "output",
  })
  ```
- In `_research_node`: increment `research_reflection_count` (first run = 0 → 1, same pattern as analysis).
- In `_analysis_node`: rename counter (already `reflection_count`; rename).
- After a successful re-research pass, clear `clauses_to_rerun` to avoid
  re-using stale flags on subsequent reflections.

### 2.8 Streamlit toggle

**Modify** [app.py](../app.py):

- Sidebar checkbox: "Enable live legal research (web)" — bound to a session-state
  flag that overrides the env default per-session.

### Phase 1 exit criteria

- Run `streamlit run app.py` against `demo/indian_employment_contract.pdf`.
- At least one clause produces a non-empty `web_results` list.
- The URL shown in `web_results[0].url` resolves and is on the Indian
  Kanoon or India Code domain.
- Disabling the sidebar toggle produces a run with all `web_results = []`
  and no network calls (verifiable via logs).
- Triggering a low-confidence clause (manually adjusting evaluator
  threshold for the test) demonstrably routes back to `research`, and on
  that pass *only* the flagged clause is re-researched.
- `tests/test_legal_assistant.py` and the new tool tests pass.

---

## 3. Phase 2 — LLM query planning + two-tier search

**Goal.** Replace hardcoded queries with LLM-generated ones, add Tavily
backend, and implement Tier 2 broadened search.

### 3.1 Tavily backend

**Modify** `src/tools/web_search_tool.py`:

- Add `TavilyBackend` implementing `SearchBackend`.
- `WebSearchTool.__init__`: pick `TavilyBackend` if `TAVILY_API_KEY` env is
  present and `tavily-python` import succeeds; otherwise `DDGHTMLBackend`.
  Log selection once at startup.
- For Tavily: pass `include_domains` natively. For DDG: synthesize
  `site:a.com OR site:b.com` operators in the query.

### 3.2 LLM query planner

**New** method on `WebResearchSubAgent`:

```python
def _plan_queries(self, block, jurisdiction, prior_results=None) -> List[str]:
    # LLM call: returns 1-3 search queries given clause text and jurisdiction.
    # On a re-research pass, prior_results is passed so the LLM can avoid
    # duplicating queries that already came back empty.
```

- Uses the same `ChatOpenAI` model as the rest of the system, low
  temperature (0.2), 60s timeout.
- Output parsed as JSON array of strings; defensive parsing with fallback
  to one hardcoded query if parsing fails.
- Prompt explicitly instructs: queries must be specific (statute name,
  section number, jurisdiction-appropriate terminology); do NOT include
  `site:` filters (those are added by the tool).

### 3.3 Tier 2 fallback

**Modify** `WebResearchSubAgent.research`:

- Run Tier 1 (whitelisted) first.
- Compute `tier1_quality = (len([r for r in results if r.relevance >= MIN_RELEVANCE]), max(r.relevance for r in results, default=0))`.
- If `tier1_quality < (MIN_RELEVANT_RESULTS, MIN_RELEVANCE)` and
  `allow_tier2`:
  - Re-plan queries with the LLM (one shot), this time hinted that the
    whitelist returned nothing useful.
  - Search without `include_domains`.
  - Apply **fetch-time filters**: short curated domain blacklist (social
    media, content farms, AI-content sites), all the existing rate-limit /
    robots / paywall rejection.
  - Tag survivors with `tier=2`.
- Final `web_results` mixes tier 1 and tier 2; sorted by relevance.

### 3.4 Relevance scoring

**Modify** `WebResearchSubAgent`:

- After extraction, score relevance via cosine similarity between the
  clause text and each extracted snippet, then drop results with
  `relevance < 0.35`.

**Important caveat about the scorer.**
[src/utils/simple_embeddings.py](../src/utils/simple_embeddings.py) is a
**TF-IDF** implementation, not a semantic embedding model. Two implications:

1. It requires `.fit(corpus)` before use — IDF degenerates on tiny
   corpora. Required pattern for ad-hoc scoring:
   ```python
   embedder = SimpleEmbeddings()
   embedder.fit([clause_text, *candidate_snippets])
   q_vec = embedder.embed_query(clause_text)
   for snippet, vec in zip(candidate_snippets, embedder.embed_documents(candidate_snippets)):
       score = cosine(q_vec, vec)
   ```
2. Keyword-overlap, not semantic. *"termination"* vs *"ending the
   contract"* will score near zero. Adequate as a coarse "is this snippet
   on-topic at all" gate, weak for fine-grained ranking.

This is acceptable for v1 — the gate's purpose is to drop obvious
unrelated results, not to nail final ordering (which the LLM analysis step
implicitly does anyway). If quality issues surface in manual inspection,
the upgrade path is sentence-transformers (heavy dep) or OpenAI embeddings
(API call cost). Defer that decision until we see the failure mode in
practice.

### 3.5 Domain blacklist

**New** `src/agents/_web_constants.py`:

```python
JURISDICTION_WHITELIST = { "IN": [...], "UK": [...], ... }
TIER2_BLACKLIST = {
    "facebook.com", "twitter.com", "x.com", "reddit.com",
    "medium.com", "quora.com", "linkedin.com",
    # SEO/AI content farms — short list, expand as needed
    ...
}
```

### Phase 2 exit criteria

- With `TAVILY_API_KEY` set: Tavily is selected at startup, logged once.
- Without it: DDG fallback is selected, with a one-time WARNING.
- A test document with a statute-specific clause produces queries
  generated by the LLM (visible in logs at DEBUG level).
- A clause whose jurisdiction is `"unknown"` triggers Tier 2 and returns
  results from non-whitelisted but legitimate domains, none from the
  blacklist.
- Relevance filtering drops obviously-irrelevant results in a manual
  inspection of one doc run.

---

## 4. Phase 3 — Citations in output

**Goal.** The final report cites web sources alongside its findings.

### 4.1 OutputAgent rendering

**Modify** [src/agents/output_agent.py](../src/agents/output_agent.py):

- For each clause in the report, when `clause_research.web_results` is
  non-empty, append a "Sources" subsection.
- Render Tier 1 and Tier 2 separately:
  - **Tier 1** — bullet list, format: `[<source_name>] <title> — <url>`
  - **Tier 2** — bullet list under a "Secondary sources" header with a
    one-line disclaimer: *"Surfaced via broadened search; verify before
    relying."*
- The clause's plain-summary still drives the analysis text; sources are
  supportive, not primary.

### 4.2 Report-level disclaimer

**Modify** OutputAgent: when *any* `web_results` present in the report,
prepend the report with a one-line note: *"This analysis includes
references to public legal sources retrieved live from the web. Verify all
citations before acting on them."*

### 4.3 Streamlit rendering

**Modify** [app.py](../app.py): the existing markdown rendering should pick
up clickable links automatically. Verify in browser; no code change
expected unless we want collapsible source sections (nice-to-have).

### Phase 3 exit criteria

- Run on `demo/indian_employment_contract.pdf` with web research enabled.
- Report contains a "Sources" block under at least one clause.
- All listed URLs are clickable in the Streamlit UI and resolve in a
  browser.
- Report top contains the disclaimer line when (and only when) sources are
  present.

---

## 5. Phase 4 — Session FAISS feedback (stretch, deferred)

Out of scope for v1. Sketch only:

- After analysis completes, take any web result with `relevance >= 0.7` and
  ingest into a session-scoped FAISS index (separate from the persistent
  one).
- Subsequent queries (e.g., follow-up Q&A in `process_query`) can hit the
  augmented index.
- No persistence beyond the session; no writes to the on-disk vectorstore.

---

## 6. Testing strategy

| Layer                    | Approach                                                  |
|--------------------------|-----------------------------------------------------------|
| Tools (fetch, search, extract) | Unit tests with `respx` for HTTP, fixture HTML files |
| WebResearchSubAgent      | Integration test with a mocked `SearchBackend` + recorded HTML; assert `WebResult` shapes |
| ResearchAgent            | Existing tests extended; add a "web disabled" path test   |
| EvaluatorAgent routing   | Unit test the three-way `should_reflect` with crafted states |
| Full DAG                 | One end-to-end test per jurisdiction (IN/UK/US sample docs) — assert no exceptions, web_results populated for at least one clause when enabled |
| Cassette / VCR           | Optional: record real Tavily/DDG responses with `vcrpy` to avoid live calls in CI |

CI runs all tests with `WEB_RESEARCH_ENABLED=false` to keep CI offline.
A separate `WEB_RESEARCH_ENABLED=true` job is opt-in (manual).

---

## 7. Rollout

- **Feature flag.** `WEB_RESEARCH_ENABLED` env var (default `true`) plus
  the Streamlit sidebar toggle (per-session override).
- **Defaults at first deploy.** Phase 1 only; Tavily key not yet set →
  DDG fallback in production. No user-visible disclaimer needed yet
  because Phase 3 hasn't shipped.
- **Phase 3 deploy gate.** Disclaimer must ship with citations — do not
  deploy citations without the disclaimer.
- **Streamlit Cloud.** Set `TAVILY_API_KEY` in Streamlit Cloud secrets
  before Phase 2 deploy; cache directory is ephemeral on that platform —
  acceptable trade-off.

---

## 8. Risks and mitigations

| Risk                                              | Mitigation                                          |
|---------------------------------------------------|-----------------------------------------------------|
| DDG HTML scrape breaks silently when DDG changes layout | Tool has parser-failure logging; test fixture is recorded HTML; switch to Tavily key when broken |
| Tavily free-tier exhaustion mid-month             | Per-document budget caps total searches; metric counter logged; alert if approaching limit |
| Reflection loop oscillation (research→analysis→research) | Hard caps `MAX_RESEARCH_REFLECTIONS=1`, `MAX_ANALYSIS_REFLECTIONS=2`; total worst case 1+2+1 = 4 LLM rounds per doc |
| robots.txt fetch blocks rendering on first call   | robots.txt fetched with shorter timeout (3s); on failure, default to "disallow" for safety |
| Source HTML structure changes break extractor     | trafilatura is generic and resilient; fallback bs4 path; per-source adapters only if needed |
| Per-clause web research blows up p95 latency      | Per-clause timeout 12s; per-doc budget 60s; once exceeded, remaining clauses get `web_results=[]` |
| Hallucinated citations from LLM                   | Impossible by design — LLM writes queries only; URLs come from search backend |

---

## 9. Definition of done (v1, end of Phase 3)

1. `streamlit run app.py` produces a report with web citations on each of
   the three sample documents (one per supported jurisdiction).
2. Disabling the sidebar toggle produces a fully offline run.
3. Reflection loop demonstrably re-researches at least one clause when
   the evaluator flags it as `missing_context`.
4. CI is green with web research disabled.
5. Manual test: kill the network mid-run — report still completes from
   local context, no traceback.
6. README has a "Web research" section explaining the feature, the
   `TAVILY_API_KEY` env var, the disclaimer policy, and the toggle.
