# 0009 — Web search runs through the LLM's built-in search tool for now

> Date: 2026-10-10 · Status: accepted

## Context

The tech-stack doc planned a dedicated search API (Tavily or Brave) for web research. That needs
another API key and another service. The Market & Trend Agent prototype already called OpenAI's
search tool, but it asked the model to write the source list (URL, title, snippet) as JSON, so a
source URL was model output and could be invented.

## Decision

1. **Web search goes through the LLM for now**: the OpenAI Responses API `web_search` tool, with
   the key the project already uses. No Tavily/Brave key.
2. **Sources are built from the search tool's `url_citation` annotations**, not from the text the
   model wrote. The URL and title come from the annotation; the snippet is the line of the answer
   that carries the citation. A statement without a citation produces no source. The tracking
   parameter OpenAI appends to URLs is removed so one page maps to one `source.uri`.
3. Everything after that is unchanged: trust tier by domain, `retrieved_at`, evidence level from
   the trust tier, findings extracted against the numbered source list.

## Consequences

- One provider and one key for search, extraction and embeddings.
- The page is not fetched. The snapshot stored on a finding is the model's cited summary, not a
  verbatim passage, so FR-IN-15 (snapshot of the cited passage) is only partly met and a web
  finding cannot be checked against the page text by the Critic without opening the URL.
- No control over ranking, recency or domain filters beyond what the prompt asks for, and results
  are not reproducible between runs. `--seed-sources` remains the deterministic path.
- Revisit with a dedicated search API or a page fetch if verbatim snapshots or domain filtering
  are needed. Only `collect_with_web_search` in `agents/market_trend_agent.py` would change.
