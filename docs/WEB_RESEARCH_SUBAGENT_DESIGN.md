# Web Research Sub-Agent — Design Document

Status: **Draft v0.1**
Owner: Research Agent
Last updated: 2026-04-27

---

## 1. Motivation

The `ResearchAgent` currently retrieves context from a single source: a local
vector store seeded with a small corpus of sample contracts
(`data/sample_docs/`, US/UK/India). For every `ClauseBlock` the intake agent
identifies, it returns the top-3 chunks from that store as a flat string in
`state["research_context"][clause_id]`.

Limitations of the status quo:

- **Bounded knowledge.** If a clause references a statute or case the local
  corpus does not contain (e.g., a specific Indian Contract Act section, an
  EU GDPR provision, a US state-specific liability cap rule), retrieval is
  blind.
- **No authority signal.** All retrieved chunks are sample contracts of
  unknown precedential weight. The downstream `AnalysisAgent` cannot tell
  "this is a binding statute" from "this is one drafting example".
- **No citation trail.** The flat string discards source URLs/identifiers,
  so `OutputAgent` cannot produce verifiable citations for the user.

The Web Research Sub-Agent extends the `ResearchAgent` to fetch authoritative
public legal sources (statutes, case law, regulator guidance) on demand and
merge them into the same `research_context` channel — with provenance.

## 2. Goals / Non-goals

**Goals**

1. Extend research coverage beyond the local corpus to public legal sources,
   filtered by jurisdiction detected at intake.
2. Preserve provenance (URL, source name, retrieved-at timestamp) so the
   output agent can cite.
3. Degrade gracefully — if scraping fails, the system still produces a
   report from local retrieval alone.
4. Stay within a per-document latency and per-source rate-limit budget.

**Non-goals (v1)**

- Paid legal databases (Westlaw, LexisNexis) — out of scope.
- JS-heavy SPAs requiring a headless browser — defer to v2 if needed.
- General-purpose web search ("what is a contract?") — only clause-driven
  queries.
- Persistent knowledge-base ingestion — scraped results are per-session
  cache, not added to the FAISS index. (Possible v2.)

## 3. Where it sits in the architecture

The sub-agent is **composed inside `ResearchAgent`**, not a new DAG node.
No new nodes are added to the planner's graph; one new edge is added so the
evaluator can also send work back to `research` (see §3.1).

```
intake → research → analysis → evaluator → (reflect_research → research
                                            |  reflect_analysis → analysis
                                            |  output)
                ↑
                └── ResearchAgent now contains:
                      • LocalRetrievalTool (existing)
                      • WebResearchSubAgent (new) ──► WebSearchTool, WebFetchTool, ContentExtractor
```

Rationale: the web sub-agent is an internal capability of `ResearchAgent`
(directly tied to it), so it lives inside that class rather than as a peer
node. The reflection loop is widened to cover the research stage as well as
analysis — failure modes can be either "thin/wrong context" (re-research) or
"weak reasoning over correct context" (re-analyze).

### 3.1 Research-level reflection

Currently the evaluator only routes back to `analysis`. The new policy:

| Evaluator finding                                         | Routes to          |
|-----------------------------------------------------------|--------------------|
| Confidence high enough on all clauses                     | `output`           |
| Low confidence + analysis cites missing/insufficient context | `reflect_research` → `research` |
| Low confidence + context looks adequate but reasoning is weak / contradictory | `reflect_analysis` → `analysis` |
| Reflection budget exhausted                               | `output`           |

Implementation:

- Add `research_reflection_count` to `AgentState` alongside the existing
  `reflection_count` (renamed `analysis_reflection_count` for clarity).
- `EvaluatorAgent.should_reflect` returns one of `{"reflect_research",
  "reflect_analysis", "output"}` — the conditional edge mapping is extended
  in `PlannerAgent._build_graph()`.
- When re-entering `research`, only clauses flagged by the evaluator are
  re-researched (targeted re-research, not full sweep) — the rest are
  carried over from the prior pass via state.
- Caps: `MAX_RESEARCH_REFLECTIONS = 1`, `MAX_ANALYSIS_REFLECTIONS = 2`
  (keeps total worst-case loops bounded and cost predictable).

This works whether the missing context lives in the local store or on the
web — the sub-agent's triage gate (§4) makes the right call on each
re-research pass, and on a re-research pass the gate is loosened (web tier
escalation is allowed even for clause types that wouldn't trigger on the
first pass).

## 4. Activation policy

The sub-agent does **not** run on every clause unconditionally. It is
triggered by a triage step inside `ResearchAgent`:

| Condition                                                            | Web research? |
|----------------------------------------------------------------------|---------------|
| Clause cites a specific statute / section / regulation               | yes           |
| Clause type is in `{indemnity, liability, ip_assignment, dispute_resolution, governing_law}` (high-stakes) | yes |
| Local retrieval returned < N chars *or* low avg similarity score     | yes           |
| Clause type is `miscellaneous` and contains capitalized proper nouns suggesting a named law/court | yes |
| Otherwise                                                            | no            |

This keeps the common case (boilerplate clauses well-covered locally) cheap,
and spends the latency/network budget only where it adds signal.

## 5. Source strategy — two-tier search

Free, public, citation-grade sources are preferred. Selected per detected
jurisdiction:

| Jurisdiction | Whitelisted sources                                            |
|--------------|----------------------------------------------------------------|
| India        | Indian Kanoon (indiankanoon.org), India Code (indiacode.nic.in)|
| UK           | BAILII (bailii.org), legislation.gov.uk                        |
| US (federal) | Cornell LII (law.cornell.edu), CourtListener (courtlistener.com), eCFR (ecfr.gov) |
| EU           | EUR-Lex (eur-lex.europa.eu)                                    |

**Tier 1 — Whitelisted search.** Search backend query is scoped with `site:`
filters across the jurisdiction's whitelist. Preferred path; provenance is
high-trust by construction.

**Tier 2 — Broadened search (LLM-guided fallback).** If Tier 1 returns fewer
than `MIN_RELEVANT_RESULTS` (default 2) or the top relevance score is below
`MIN_RELEVANCE` (default 0.55), the sub-agent drops the `site:` filter and
runs an unscoped search. The LLM query planner is allowed to propose new
queries with reasoning ("the clause references a specific state regulation
not covered by the whitelist; broaden to .gov domains in that state").

Tier 2 results are still subject to **all** fetch-time constraints:

- `robots.txt` honored
- per-domain rate limit
- 2 MB body cap, 4 KB extracted text cap
- paywall / login-wall heuristic rejection
- content extractor must yield non-trivial main text
- domain blacklist (social media, content farms, AI-generated SEO sites,
  non-legal aggregators) — short and curated

Tier 2 results are tagged `tier=2` in `WebResult` so `OutputAgent` can render
them with a "secondary source" disclaimer.

## 6. Components

### 6.1 `WebResearchSubAgent` (new)

Owns the per-clause web research loop.

```python
class WebResearchSubAgent:
    def research(self, block: ClauseBlock, jurisdiction: str) -> List[WebResult]:
        # 1. plan: LLM generates 1-3 targeted queries from clause text
        # 2. search: WebSearchTool → list of candidate URLs
        # 3. filter: drop non-whitelisted domains, dedupe, cap to top K
        # 4. fetch: WebFetchTool with cache + rate limit
        # 5. extract: ContentExtractor → clean text + metadata
        # 6. score: embedding similarity vs clause text, drop noise
        # 7. return ranked WebResult list (≤ 3)
```

Constraints:
- Max 3 queries per clause, max 5 URLs per clause, max 3 final results.
- Per-clause hard timeout (default 12s); total per-document budget ~60s.
- LLM calls used only for query planning, not for content summarization
  (analysis agent owns that step).

### 6.2 `WebSearchTool` (new)

Thin wrapper over a search backend. Returns `[{url, title, snippet}]`.

Backend selection at construction time:

1. If `TAVILY_API_KEY` is set in env → use **Tavily**
   (`tavily-python`). Native support for `include_domains`, JSON output,
   pre-extracted snippets, AI-tuned ranking.
2. Otherwise → fall back to **DuckDuckGo HTML** scrape via
   `httpx` + `beautifulsoup4`. Best-effort, no key required, brittle by
   nature — log a one-time warning at startup so the operator knows.

The backend is encapsulated behind a single interface
(`SearchBackend.search(query, include_domains, max_results) -> List[SearchHit]`)
so it can be swapped without touching the sub-agent. For Tier 1 (whitelisted)
search the tool passes `include_domains=<jurisdiction whitelist>`; for the
DDG fallback, the tool synthesizes the same scoping with `site:` operators
in the query string. For Tier 2 (broadened) search, no domain restriction is
applied at the search layer — filtering happens at fetch time.

### 6.3 `WebFetchTool` (new)

- HTTP GET via `httpx` with: 10s timeout, `User-Agent: LawAgent-Research/0.1`,
  redirect cap 3, max body 2 MB.
- Disk cache at `data/web_cache/<sha256(url)>.html` keyed on URL; TTL 14d.
- Per-domain rate limit (token bucket: 1 req/sec, burst 3).
- Honor `robots.txt` via `urllib.robotparser`, cached per-domain for the
  session. If disallowed → skip silently.
- No JS execution (v1).

### 6.4 `ContentExtractor` (new)

`trafilatura` (preferred) or `beautifulsoup4` fallback to strip nav/ads and
return main article text. Truncate to 4 KB per page. Detect and drop
"register to view" / paywall stubs by length + keyword heuristics.

### 6.5 State shape change

`research_context` becomes structured:

```python
@dataclass
class WebResult:
    url: str
    source_name: str        # "Indian Kanoon", "BAILII", ...
    title: str
    snippet: str            # extracted, truncated to ~600 chars
    retrieved_at: str       # ISO8601
    relevance: float        # 0-1, embedding similarity to clause
    tier: int               # 1 = whitelisted, 2 = broadened

@dataclass
class ClauseResearch:
    clause_id: str
    local_context: str           # existing flat string from vector store
    web_results: List[WebResult] # may be empty
```

State key updates:

```python
# state.py
research_context: Dict[str, ClauseResearch]   # was Dict[str, str]
jurisdiction: str                              # NEW: "IN" | "UK" | "US" | "EU" | "unknown"
analysis_reflection_count: int                 # renamed from reflection_count
research_reflection_count: int                 # NEW: research-loop counter
```

`jurisdiction` is populated by `IntakeAgent` (it already classifies
`document_type` from the text — extending the same LLM call to also return
an ISO-style country/region tag is essentially free). Default `"unknown"`
disables Tier 1 whitelisting and forces Tier 2 (broadened) for that run.

`AnalysisAgent` and `OutputAgent` are updated to consume the new
`research_context` shape. `OutputAgent` adds a "Sources" section per clause
when `web_results` is non-empty, with separate rendering for tier 1 vs tier
2 results.

## 7. Failure modes

| Failure                          | Behavior                                              |
|----------------------------------|-------------------------------------------------------|
| Search backend returns 0 results | Sub-agent returns `[]`; local context still used      |
| Fetch timeout / 4xx / 5xx        | Skip URL, continue with remaining candidates          |
| `robots.txt` disallows           | Skip URL, log at debug level                          |
| All URLs fail                    | `web_results = []`; report still generated            |
| Per-clause budget exceeded       | Cancel pending fetches, return what's collected       |
| Per-document budget exceeded     | Skip web research for remaining clauses               |
| Search API key missing           | Sub-agent disabled at startup; log once               |

The sub-agent is **never** allowed to raise into `ResearchAgent.run()`. All
exceptions are caught and converted to empty results.

## 8. Configuration

Added to `.env` / `.streamlit/secrets.toml`:

```
TAVILY_API_KEY=...                    # optional; falls back to DDG HTML if absent
WEB_RESEARCH_ENABLED=true             # master switch
WEB_RESEARCH_PER_DOC_BUDGET_SEC=60
WEB_RESEARCH_PER_CLAUSE_TIMEOUT_SEC=12
WEB_RESEARCH_CACHE_TTL_DAYS=14
```

UI: a toggle in the Streamlit sidebar "Enable live legal research (web)" so
users can disable it for offline / air-gapped runs.

## 9. Dependencies (new)

Added to `requirements.txt`:

- `httpx>=0.27`           (HTTP client, async-capable)
- `trafilatura>=1.9`      (content extraction)
- `beautifulsoup4>=4.12`  (extraction fallback, also useful elsewhere)
- `tavily-python>=0.3`    (optional; gated behind API key check)

No new heavy deps (no Playwright, no Selenium, no spaCy).

## 10. Compliance & ethics

- Only public, free, government / courts / well-known legal-info sites.
- Honor `robots.txt`. Identify with a descriptive User-Agent.
- Rate-limit per-domain. No parallel hammering of the same host.
- Cache aggressively to minimize repeat fetches.
- Do **not** scrape paywalled content even if technically reachable.
- Output cites the source URL — users should verify before relying on it.
  A disclaimer line is added to the report when web results are included.

## 11. Phasing

**Phase 1 — skeleton (no LLM planning)**
Hardcoded query template per clause type, single-source fetch, return raw
extracted text. Goal: prove the data path end-to-end through the DAG.

**Phase 2 — LLM query planning + multi-source**
`WebResearchSubAgent.research()` generates queries, fans out across the
jurisdiction whitelist, scores results.

**Phase 3 — citations in output**
`OutputAgent` renders a per-clause sources block; UI shows clickable links.

**Phase 4 (stretch) — feedback to vectorstore**
Promote high-relevance scraped pages into the FAISS index for the session.

## 12. Open questions

1. ~~**Search backend default.**~~ **Resolved (§6.2):** Tavily when
   `TAVILY_API_KEY` is set, DDG HTML fallback otherwise. One swappable
   `SearchBackend` interface so we can add Brave / SearXNG later without
   touching callers.
2. ~~**Jurisdiction detection.**~~ **Resolved (§6.5):** explicit
   `jurisdiction` field on `AgentState`, populated by `IntakeAgent`.
   Default `"unknown"` falls through to Tier 2 broadened search.
3. ~~**Reflection loop interaction.**~~ **Resolved (§3.1):** evaluator can
   route back to `research` (targeted re-research of low-confidence clauses)
   in addition to `analysis`. Capped at 1 research reflection, 2 analysis
   reflections per document.
4. **Caching across sessions.** Disk cache survives restarts — fine for dev,
   but on Streamlit Cloud the FS is ephemeral. Acceptable for v1.

## 13. Out-of-scope risks (acknowledged)

- Source sites change HTML structure → extractor breakage. Mitigation:
  trafilatura is generic; per-source adapters only if needed.
- Search backend ToS changes. Mitigation: backend is one swappable class.
- Hallucinated citations from LLM query planner — *not possible by design*
  here, because the LLM only writes the search query; URLs come from the
  search backend, not from the model.
