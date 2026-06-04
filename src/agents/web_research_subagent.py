"""
Web Research Sub-Agent — extends the ResearchAgent's reach to authoritative
public legal sources.

Phase 2:
- LLM-driven query planning (1-3 queries per clause)
- Tier 1 (jurisdiction whitelist) → Tier 2 (broadened) escalation
- TF-IDF cosine relevance scoring; off-topic results dropped
- Hardcoded query templates retained as a fallback for LLM failure
"""

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from ..tools.web_search_tool import WebSearchTool, SearchHit
from ..tools.web_fetch_tool import WebFetchTool
from ..tools.content_extractor import extract as extract_content
from ..utils.simple_embeddings import SimpleEmbeddings
from .state import ClauseBlock, WebResult
from ._web_constants import (
    JURISDICTION_WHITELIST,
    QUERY_TEMPLATES,
    SOURCE_NAMES,
    JURISDICTION_NAMES,
    TIER2_BLACKLIST,
    MIN_RELEVANT_RESULTS,
    MIN_RELEVANCE,
    DROP_RELEVANCE,
)

log = logging.getLogger(__name__)


class WebResearchSubAgent:
    """Per-clause web research with LLM query planning and two-tier search."""

    def __init__(
        self,
        search_tool: WebSearchTool,
        fetch_tool: WebFetchTool,
        api_key: Optional[str] = None,
        model: str = "gpt-5.4",
        per_clause_timeout: float = 12.0,
        max_results: int = 3,
    ):
        self.search_tool = search_tool
        self.fetch_tool = fetch_tool
        self.per_clause_timeout = per_clause_timeout
        self.max_results = max_results
        # Cache LLM-planned queries by (clause_type, jurisdiction, broaden) so
        # multiple clauses of the same type share one planning call.
        self._query_cache: Dict[Tuple[str, str, bool], List[str]] = {}
        self._llm: Optional[ChatOpenAI] = None
        if api_key:
            try:
                self._llm = ChatOpenAI(
                    model=model,
                    api_key=api_key,
                    temperature=0.2,
                    timeout=60,
                )
            except Exception as e:
                log.warning("query planner LLM init failed (%s); using template fallback", e)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def research(
        self,
        block: ClauseBlock,
        jurisdiction: str,
        allow_tier2: bool = False,
    ) -> List[WebResult]:
        deadline = time.monotonic() + self.per_clause_timeout
        try:
            return self._research(block, jurisdiction, allow_tier2, deadline)
        except Exception as e:
            log.warning("web research failed for %s: %s", block.clause_id, e)
            return []

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _research(
        self,
        block: ClauseBlock,
        jurisdiction: str,
        allow_tier2: bool,
        deadline: float,
    ) -> List[WebResult]:
        whitelist = JURISDICTION_WHITELIST.get(jurisdiction, [])

        all_results: List[WebResult] = []

        # ---- Tier 1: whitelisted search ---------------------------------
        if whitelist:
            queries = self._plan_queries(block, jurisdiction, broaden=False)
            tier1 = self._search_fetch_extract(
                queries=queries,
                include_domains=whitelist,
                tier=1,
                deadline=deadline,
                drop_blacklist=False,
                domain_must_match=whitelist,
            )
            tier1 = self._score_relevance(block.content, tier1)
            all_results.extend(tier1)
        else:
            tier1 = []

        # ---- Tier 2: broadened search (when allowed and Tier 1 is thin) -
        if allow_tier2 and self._tier1_insufficient(tier1) and time.monotonic() < deadline:
            log.info(
                "clause %s: Tier 1 insufficient (%d relevant), escalating to Tier 2",
                block.clause_id,
                sum(1 for r in tier1 if r.relevance >= MIN_RELEVANCE),
            )
            broadened_queries = self._plan_queries(
                block, jurisdiction, broaden=True, prior_queries=queries if whitelist else None
            )
            tier2 = self._search_fetch_extract(
                queries=broadened_queries,
                include_domains=(),     # no whitelist — global
                tier=2,
                deadline=deadline,
                drop_blacklist=True,
                domain_must_match=None,
            )
            tier2 = self._score_relevance(block.content, tier2)
            all_results.extend(tier2)

        # ---- Drop noise, sort by relevance, cap to max_results ----------
        kept = [r for r in all_results if r.relevance >= DROP_RELEVANCE]
        kept.sort(key=lambda r: r.relevance, reverse=True)
        return kept[: self.max_results]

    # ------------------------------------------------------------------
    # Query planning (LLM with template fallback)
    # ------------------------------------------------------------------

    def _plan_queries(
        self,
        block: ClauseBlock,
        jurisdiction: str,
        broaden: bool = False,
        prior_queries: Optional[Sequence[str]] = None,
    ) -> List[str]:
        if self._llm is None:
            return [self._template_query(block, jurisdiction)]

        # Cache by (clause_type, jurisdiction, broaden). Multiple clauses of
        # the same type share one LLM-planned query list — no per-clause
        # specificity is strong enough to justify a fresh call. Saves
        # ~30-50% of planner calls on typical contracts.
        cache_key = (block.clause_type, jurisdiction, broaden)
        cached = self._query_cache.get(cache_key)
        if cached is not None:
            log.info("query plan cache HIT for %s", cache_key)
            return cached

        try:
            queries = (
                self._llm_plan(block, jurisdiction, broaden, prior_queries)
                or [self._template_query(block, jurisdiction)]
            )
        except Exception as e:
            log.warning("query planner failed for %s: %s — falling back to template",
                        block.clause_id, e)
            queries = [self._template_query(block, jurisdiction)]

        self._query_cache[cache_key] = queries
        log.info("query plan cache MISS for %s (now cached)", cache_key)
        return queries

    def _llm_plan(
        self,
        block: ClauseBlock,
        jurisdiction: str,
        broaden: bool,
        prior_queries: Optional[Sequence[str]],
    ) -> List[str]:
        jur_name = JURISDICTION_NAMES.get(jurisdiction, "")
        clause_text = (block.content or "")[:1200]

        broaden_block = ""
        if broaden:
            prior = "\n".join(f"- {q}" for q in (prior_queries or [])) or "(none)"
            broaden_block = f"""
The whitelisted-source search returned no useful results for these queries:
{prior}

Generate ALTERNATIVE queries. Try different phrasings, specific statute or
case names, or government / court / regulator terminology that might appear
on official sites outside the whitelist.
""".strip()

        prompt = f"""You are a legal research query planner.
Your job: given one clause from a contract, write 1-3 web search queries
that would surface authoritative legal context (statutes, case law,
regulator guidance) for that clause.

Clause type: {block.clause_type}
Jurisdiction: {jur_name or "unknown"}
Clause text:
\"\"\"
{clause_text}
\"\"\"

{broaden_block}

Rules:
- Each query must be specific. Cite statute names, sections, or
  jurisdiction-appropriate terminology where the clause text supports it.
- DO NOT include "site:" filters. The tool adds those.
- DO NOT include quotation marks around the queries.
- Output JSON only, no markdown, no commentary:
  {{"queries": ["query 1", "query 2"]}}"""

        resp = self._llm.invoke([HumanMessage(content=prompt)])
        text = (resp.content or "").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        data = json.loads(text)
        queries = data.get("queries") or []
        clean: List[str] = []
        for q in queries:
            if isinstance(q, str) and q.strip():
                clean.append(q.strip())
            if len(clean) >= 3:
                break
        return clean

    @staticmethod
    def _template_query(block: ClauseBlock, jurisdiction: str) -> str:
        template = QUERY_TEMPLATES.get(block.clause_type, QUERY_TEMPLATES["miscellaneous"])
        jur_name = JURISDICTION_NAMES.get(jurisdiction, "")
        topic = block.clause_type if block.clause_type != "miscellaneous" \
            else (block.content[:80].strip() or "general")
        return template.format(jurisdiction=jur_name, clause_topic=topic).strip()

    # ------------------------------------------------------------------
    # Search / fetch / extract
    # ------------------------------------------------------------------

    def _search_fetch_extract(
        self,
        queries: Sequence[str],
        include_domains: Sequence[str],
        tier: int,
        deadline: float,
        drop_blacklist: bool,
        domain_must_match: Optional[Sequence[str]],
    ) -> List[WebResult]:
        if not queries:
            return []

        seen_urls: set = set()
        out: List[WebResult] = []
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Pool hits across all queries before fetching, so per-query budget
        # doesn't starve the "best" hits if they appear in later queries.
        pooled: List[SearchHit] = []
        for q in queries:
            if time.monotonic() >= deadline:
                break
            hits = self.search_tool.search(
                query=q,
                include_domains=include_domains,
                max_results=self.max_results + 2,
            )
            pooled.extend(hits)

        for hit in pooled:
            if time.monotonic() >= deadline:
                log.info("budget exhausted in tier=%d, stopping fetches", tier)
                break

            url = hit.url
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            domain = urlparse(url).netloc.lower()
            if not domain:
                continue
            if drop_blacklist and self._is_blacklisted(domain):
                log.debug("tier 2 blacklist drop: %s", domain)
                continue
            if domain_must_match and not any(d in domain for d in domain_must_match):
                continue

            fetched = self.fetch_tool.fetch(url)
            if not fetched:
                continue
            extracted = extract_content(fetched.body, url=url)
            if not extracted:
                continue

            out.append(WebResult(
                url=url,
                source_name=self._source_name(domain),
                title=hit.title or domain,
                snippet=extracted[:600],
                retrieved_at=now_iso,
                relevance=0.0,    # filled in by _score_relevance
                tier=tier,
            ))
        return out

    # ------------------------------------------------------------------
    # Relevance scoring (TF-IDF cosine)
    # ------------------------------------------------------------------

    @staticmethod
    def _score_relevance(clause_text: str, results: List[WebResult]) -> List[WebResult]:
        if not results:
            return []
        # TF-IDF degenerates with only 2 docs in the fit corpus — all shared
        # words get IDF=0, collapsing cosine to 0. Skip scoring in that case
        # and trust the search backend's ranking (relevance=1.0).
        if len(results) < 2:
            return [_with_relevance(r, 1.0) for r in results]

        snippets = [r.snippet for r in results]
        try:
            embedder = SimpleEmbeddings()
            embedder.fit([clause_text] + snippets)
            q_vec = embedder.embed_query(clause_text)
            snippet_vecs = embedder.embed_documents(snippets)
        except Exception as e:
            log.warning("relevance scoring failed: %s", e)
            # Conservative fallback: score 0.5 so they survive DROP_RELEVANCE
            # but won't be treated as highly relevant for Tier 1 sufficiency.
            return [_with_relevance(r, 0.5) for r in results]

        scored: List[WebResult] = []
        for r, vec in zip(results, snippet_vecs):
            score = _cosine(q_vec, vec)
            scored.append(_with_relevance(r, score))
        return scored

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tier1_insufficient(tier1_results: List[WebResult]) -> bool:
        relevant = [r for r in tier1_results if r.relevance >= MIN_RELEVANCE]
        return len(relevant) < MIN_RELEVANT_RESULTS

    @staticmethod
    def _is_blacklisted(domain: str) -> bool:
        domain = domain.lower()
        for bad in TIER2_BLACKLIST:
            if domain == bad or domain.endswith("." + bad):
                return True
        return False

    @staticmethod
    def _source_name(domain: str) -> str:
        for known, friendly in SOURCE_NAMES.items():
            if known in domain:
                return friendly
        return domain


def _with_relevance(r: WebResult, score: float) -> WebResult:
    return WebResult(
        url=r.url,
        source_name=r.source_name,
        title=r.title,
        snippet=r.snippet,
        retrieved_at=r.retrieved_at,
        relevance=max(0.0, min(1.0, float(score))),
        tier=r.tier,
    )


def _cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
