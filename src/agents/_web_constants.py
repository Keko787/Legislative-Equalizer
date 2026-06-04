"""
Constants for the web research sub-agent.

Whitelisted sources per jurisdiction, hardcoded query templates per clause
type (Phase 1 — replaced by LLM planning in Phase 2), and the high-stakes
clause type set used by the triage gate.
"""

# Per-jurisdiction whitelist of authoritative public legal sources.
JURISDICTION_WHITELIST = {
    "IN": ["indiankanoon.org", "indiacode.nic.in"],
    "UK": ["bailii.org", "legislation.gov.uk"],
    "US": ["law.cornell.edu", "courtlistener.com", "ecfr.gov"],
    "EU": ["eur-lex.europa.eu"],
}

# Clause types that always trigger web research regardless of local context
# quality. Match the values produced by IntakeAgent's keyword classifier.
HIGH_STAKES_TYPES = {
    "indemnification",
    "liability",
    "intellectual property",
    "dispute resolution",
    "governing law",
}

# Phase 1: hardcoded query templates per clause type.
# `{jurisdiction}` is replaced with a country/region name; `{clause_topic}`
# is the clause type or, for miscellaneous, the first ~80 chars of content.
QUERY_TEMPLATES = {
    "termination":          "termination clause case law {jurisdiction}",
    "payment":              "payment terms enforceability {jurisdiction}",
    "liability":            "limitation of liability clause case law {jurisdiction}",
    "confidentiality":      "confidentiality clause enforceability {jurisdiction}",
    "indemnification":      "indemnification clause scope case law {jurisdiction}",
    "intellectual property":"intellectual property assignment clause {jurisdiction}",
    "force majeure":        "force majeure clause interpretation {jurisdiction}",
    "governing law":        "governing law jurisdiction clause {jurisdiction}",
    "notice":               "contractual notice requirement {jurisdiction}",
    "warranties":           "contractual warranties enforceability {jurisdiction}",
    "dispute resolution":   "arbitration clause enforceability {jurisdiction}",
    "non-compete":          "non-compete clause enforceability {jurisdiction}",
    "assignment":           "assignment of contract clause {jurisdiction}",
    "amendment":            "contract amendment clause {jurisdiction}",
    "miscellaneous":        "{clause_topic} clause {jurisdiction}",
}

# Friendly display names for whitelisted source domains.
SOURCE_NAMES = {
    "indiankanoon.org":    "Indian Kanoon",
    "indiacode.nic.in":    "India Code",
    "bailii.org":          "BAILII",
    "legislation.gov.uk":  "legislation.gov.uk",
    "law.cornell.edu":     "Cornell LII",
    "courtlistener.com":   "CourtListener",
    "ecfr.gov":            "eCFR",
    "eur-lex.europa.eu":   "EUR-Lex",
}

JURISDICTION_NAMES = {
    "IN": "India",
    "UK": "United Kingdom",
    "US": "United States",
    "EU": "European Union",
    "unknown": "",
}

# Tier 2 (broadened) domain blacklist — short and curated. We drop hits
# from these even if a search backend returns them. Expand as needed.
TIER2_BLACKLIST = frozenset({
    # social media
    "facebook.com", "twitter.com", "x.com", "reddit.com",
    "linkedin.com", "instagram.com", "tiktok.com", "youtube.com",
    # general blogging / Q&A / aggregators (not legal authority)
    "medium.com", "quora.com", "stackoverflow.com", "stackexchange.com",
    "wikipedia.org", "wikihow.com",
    # known low-quality SEO / AI content farms
    "answers.com", "ehow.com", "wikihow.com",
})

# Tier 1 sufficiency thresholds. Tier 1 is "sufficient" when at least
# MIN_RELEVANT_RESULTS results score >= MIN_RELEVANCE. Otherwise Tier 2
# may be invoked (when allowed).
#
# These thresholds are calibrated for the TF-IDF cosine similarity produced
# by SimpleEmbeddings — on small corpora (clause + 3-5 snippets) it returns
# values in the 0.0-0.15 range even for clearly relevant content. The
# original design doc proposed 0.35/0.55, which assumed semantic embeddings;
# those values are unreachable with TF-IDF and would force every run into
# Tier 2. If/when we upgrade the scorer to sentence-transformers or OpenAI
# embeddings, raise these back toward the design values.
MIN_RELEVANT_RESULTS = 2
MIN_RELEVANCE = 0.05

# Below this score, drop results entirely as off-topic noise.
DROP_RELEVANCE = 0.02
