# Agentic Lawyer AI ⚖️

A multi-agent hierarchical DAG system for automated legal document analysis. Upload any text-based legal PDF and get a structured risk report — plain-language summaries, flagged clauses, extracted obligations, and actionable recommendations — before you ask a single question.

> 📄 **Full write-up:** the IEEE-style project report — system architecture, two-level reflection design, parallel-execution model, and experimental results across six figures — is available as a typeset PDF at [`ProjectReport/report.pdf`](ProjectReport/report.pdf) and as org-mode source at [`ProjectReport/PROJECT_REPORT.org`](ProjectReport/PROJECT_REPORT.org). See the [Project Report](#project-report) section below for viewing and rebuild instructions.

---

## Architecture

```
User Upload
    │
    ▼
┌─────────────────────────────────────────────────────┐
│              Planner / Orchestrator (LangGraph DAG) │
│                                                     │
│  📥 Intake Agent   → identifies document type,     │
│                       segments clauses              │
│        │                                            │
│  🔍 Research Agent → RAG retrieval per clause       │
│        │                                            │
│  🧠 Analysis Agent → risk flags, obligations,       │
│                       plain summaries               │
│        │                                            │
│  ✅ Evaluator Agent → confidence scoring;           │
│        │               reflection loop if < 0.70   │
│        │◄──────────────────────────────────────────┤
│  📄 Output Agent   → final markdown report          │
└─────────────────────────────────────────────────────┘
    │
    ▼
💬 Chat Interface  (contextual follow-up Q&A)
```

**Key properties**
- DAG structure — no circular dependencies, fully traceable execution
- Reflection loop — low-confidence clauses are automatically re-analyzed (capped at 2 passes)
- Conversational memory — follow-up questions are answered in context of the full analysis
- Fallback agents — if the Planner fails to import, the system falls back to `LegalAssistantAgent` → `SimpleLegalAgent`

---

## Parallel Pipeline Architecture

The system supports two pipeline modes selectable from the sidebar at runtime.

### Sequential mode (default)
Clauses are processed one at a time inside each agent stage. Predictable and easy to debug.

```
Research:  [clause 1] → [clause 2] → [clause 3] → [clause 4] → [clause 5]
Analysis:  [clause 1] → [clause 2] → [clause 3] → [clause 4] → [clause 5]
```

### Parallel mode
Clauses are processed concurrently inside the Research and Analysis stages using a thread pool (up to 6 workers). Each clause is independent, so all can be dispatched simultaneously. On a 5-clause document this cuts per-stage wall-clock time from `N × T` to `~T`.

```
Research:  [clause 1 ‖ clause 2 ‖ clause 3 ‖ clause 4 ‖ clause 5]
Analysis:  [clause 1 ‖ clause 2 ‖ clause 3 ‖ clause 4 ‖ clause 5]
```

The stage order (Intake → Research → Analysis → Evaluator → Output) remains sequential because each stage depends on the previous stage's output.

### Research Agent — internal reflection loop
In both modes, the Research Agent now scores the quality of each clause's retrieved context (length + keyword overlap). If the score is below the threshold it retries with a progressively broader query — up to 2 internal attempts — before handing off to the Analysis Agent. This makes the RAG system more reliable on short or ambiguous clauses.

```
retrieve context
  → score quality
  → if thin: retry with broader query  (up to 2×)
  → proceed to web research (if enabled)
```

The Evaluator's existing outer reflection loop (routes back to Research when confidence < 0.70) still operates on top of this inner loop.

### Live agent status display
In parallel mode the UI renders a real-time clause status board during the pipeline run, with colour-coded chips for each clause:

| Chip | Meaning |
|---|---|
| ⏳ grey | queued |
| 🔄 yellow (animated) | in progress |
| ✅ green | done |
| ❌ red | error |

The chips update as futures complete, visually proving that clauses finish out of order (i.e. in parallel).

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys)

### 2. Clone and set up a virtual environment

```bash
git clone https://github.com/Keko787/Legislative-Equalizer
cd Legislative-Equalizer

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your API key

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your_openai_api_key_here
```

### 5. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Usage

### Analyzing a document

1. **Upload a PDF** using the sidebar uploader, or click **Load Sample Contract** to try the built-in demo.
2. Once indexed, click **🚀 Run Analysis** in the main area.
3. The 5-agent pipeline runs and produces a structured report with:
   - Risk summary (High / Medium / Low clause counts)
   - Per-clause plain-English explanation, risk flags, and obligations
   - Actionable recommendations
4. Switch to the **💬 Chat** tab to ask follow-up questions.

### Supported documents

Any text-based PDF (not scanned images) up to **10 MB**, including:

| Document type | Examples |
|---|---|
| Service & consulting agreements | Freelance contracts, SLAs |
| NDAs | Mutual and one-way confidentiality agreements |
| Employment contracts | Offer letters, restrictive covenants |
| Lease agreements | Commercial and residential leases |
| Software / SaaS agreements | License agreements, terms of service |
| Purchase agreements | Asset purchase, vendor contracts |
| Partnership / LLC agreements | Operating agreements |
| Settlement agreements | Release and settlement |

> **Note:** Scanned PDFs (image-only), non-English documents, and files over 10 MB are not supported.

---

## Project Structure

```
Law-agent/
├── app.py                              # Streamlit application (entry point)
├── app_simple.py                       # Lightweight, no-LLM fallback UI
├── setup_check.py                      # Environment / config validator
├── test_e2e.py                         # End-to-end smoke test
├── requirements.txt                    # Python dependencies
├── requirements-cloud.txt              # Streamlit Cloud-optimized deps
├── DEPLOYMENT.md                       # Cloud deployment guide
├── DEPLOYMENT_CHECKLIST.md             # Pre-deployment checklist
├── .env                                # API key (not committed)
├── ProjectReport/
│   ├── PROJECT_REPORT.org              # IEEE-style write-up of the system (source)
│   ├── report.pdf                      # Typeset two-column PDF render of the report
│   ├── preamble.tex                    # LaTeX preamble used by the PDF build
│   ├── table-fix.lua                   # Pandoc filter (longtable → table*)
│   └── figures/                        # Architecture diagram + 6 result figures
│       ├── generate_figures.py         # Regenerates the 6 result figures
│       ├── Agentic Layer Flow Diagram.png
│       └── fig{1..6}_*.png
├── src/
│   ├── agents/
│   │   ├── state.py                    # Shared AgentState TypedDict
│   │   ├── planner_agent.py            # Orchestrator — builds and runs the DAG
│   │   ├── intake_agent.py             # Document type detection & clause segmentation
│   │   ├── research_agent.py           # RAG retrieval per clause (inner reflection loop)
│   │   ├── analysis_agent.py           # Risk flagging & obligation extraction
│   │   ├── evaluator_agent.py          # Confidence scoring & outer reflection loop
│   │   ├── output_agent.py             # Final report generation
│   │   ├── legal_agent.py              # Fallback: single LangGraph agent
│   │   └── simple_agent.py             # Fallback: no-dependency agent
│   ├── tools/
│   │   ├── retrieval_tool.py           # Vector search tool
│   │   ├── summarizer_tool.py          # Plain-language summarization
│   │   ├── clause_analyzer_tool.py     # Structured clause analysis (GPT)
│   │   └── evaluator_tool.py           # Confidence scoring tool (GPT)
│   ├── memory/
│   │   └── conversation_memory.py      # Session + document-level context
│   └── utils/
│       ├── document_processor.py       # PDF extraction & chunking
│       ├── vector_store.py             # FAISS / simple vector store
│       └── simple_embeddings.py        # TF-IDF fallback embeddings
├── scraper/
│   └── Scrape_legal_pdfs.py            # Web-scraping subagent for corpus expansion
├── data/
│   ├── sample_docs/                    # Indian + US sample contracts & cases
│   └── vectorstore/                    # Persisted FAISS index (auto-created)
├── demo/                               # Demo guides & sample PDFs
└── tests/
    └── test_legal_assistant.py
```

---

## Configuration

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key |

The model is set to **`gpt-4o-mini`** by default across all agents. To change it, update the `openai_model` default in [`src/agents/planner_agent.py`](src/agents/planner_agent.py).

---

## Troubleshooting

**`API Key Missing` shown in sidebar**
→ Make sure `.env` exists in the project root with `OPENAI_API_KEY=sk-...` and that you activated the virtual environment before running.

**`ModuleNotFoundError` on startup**
→ Run `pip install -r requirements.txt` inside the activated virtual environment.

**"No text extracted from PDF"**
→ The PDF is likely a scanned image. Use a text-based PDF instead.

**Model returns 404 / model not found**
→ Verify the exact model ID available on your OpenAI account at [platform.openai.com](https://platform.openai.com/docs/models). Update `openai_model` in `planner_agent.py` accordingly.

**Analysis produces all "Could not analyze" errors**
→ Almost always a wrong model name or exhausted API quota. Check the model ID and your usage limits.

---

## Tech Stack

| Component | Library |
|---|---|
| UI | [Streamlit](https://streamlit.io) |
| Agent orchestration | [LangGraph](https://langchain-ai.github.io/langgraph/) |
| LLM | [OpenAI GPT](https://platform.openai.com) via `langchain-openai` |
| Vector search | FAISS (with TF-IDF fallback) |
| PDF parsing | pypdf |
| Memory | Custom `ConversationMemory` |

---

## Documentation

### Project Report

The full IEEE-style project report covers the system architecture, the two-level reflection design, the parallel-execution model, and six experiments characterizing scaling, retrieval quality, latency breakdown, and reflection saturation. It is available in two formats — a typeset 7-page two-column PDF and the org-mode source it was rendered from:

| Resource | Path |
|---|---|
| 📄 **Typeset PDF report** (two-column, ~7 pages) | [`ProjectReport/report.pdf`](ProjectReport/report.pdf) |
| Org-mode source | [`ProjectReport/PROJECT_REPORT.org`](ProjectReport/PROJECT_REPORT.org) |
| Architecture diagram (Fig. 1) | [`ProjectReport/figures/Agentic Layer Flow Diagram.png`](ProjectReport/figures/Agentic%20Layer%20Flow%20Diagram.png) |
| Result figures (Fig. 2–7) | [`ProjectReport/figures/`](ProjectReport/figures/) |
| Figure regeneration script | [`ProjectReport/figures/generate_figures.py`](ProjectReport/figures/generate_figures.py) |
| LaTeX preamble (for PDF rebuild) | [`ProjectReport/preamble.tex`](ProjectReport/preamble.tex) |
| Pandoc Lua filter (longtable → table\*) | [`ProjectReport/table-fix.lua`](ProjectReport/table-fix.lua) |

#### Viewing the report

- **PDF** — open [`ProjectReport/report.pdf`](ProjectReport/report.pdf) directly.
- **Org-mode** — GitHub renders `.org` files natively; click the source link above.
- **Slides** — export to a reveal.js deck via [pandoc](https://pandoc.org/):

  ```powershell
  pandoc ProjectReport/PROJECT_REPORT.org -t revealjs -s -o report-slides.html `
         -V revealjs-url=https://unpkg.com/reveal.js@4
  start report-slides.html
  ```

#### Rebuilding the report

To regenerate the PDF after editing the org source (requires pandoc + a TeX engine such as MiKTeX):

```powershell
cd ProjectReport
pandoc PROJECT_REPORT.org --pdf-engine=xelatex `
       -V documentclass=article -V classoption=twocolumn -V classoption=10pt `
       -V mainfont="Cambria" -V monofont="Consolas" `
       --lua-filter=table-fix.lua --include-in-header=preamble.tex `
       -o report.pdf
```

To regenerate the six result figures (e.g. after tuning latency or threshold parameters):

```bash
python ProjectReport/figures/generate_figures.py
```

### Deployment and Testing

| Resource | Path |
|---|---|
| Cloud deployment guide | [`DEPLOYMENT.md`](DEPLOYMENT.md) |
| Pre-deployment checklist | [`DEPLOYMENT_CHECKLIST.md`](DEPLOYMENT_CHECKLIST.md) |
| End-to-end smoke test | [`test_e2e.py`](test_e2e.py) |
| Environment validator | [`setup_check.py`](setup_check.py) |

---

## Team

| Name | Role and Contributions |
|---|---|
| Kevin Kostage | Project lead, agent orchestration, web-scraping subagent |
| Ping Liu | DAG parallel architecture, RAG pipeline |
| Adib Bazgir | Analysis agent, Streamlit UI |
| Mohsen Rezaei | Evaluator agent, reflection loop, parallel workers |
| Saiteja Labba | Deployment, demo content, Research agent |
