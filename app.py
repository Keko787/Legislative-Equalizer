"""
Legal Assistant Agent — Streamlit Application
Multi-agent hierarchical DAG system for legal document analysis.
"""

import streamlit as st
import os
from dotenv import load_dotenv
from typing import List, Optional

load_dotenv()

from src.utils.document_processor import DocumentProcessor, create_sample_contract
from src.utils.vector_store import VectorStoreManager

try:
    from src.agents.planner_agent import PlannerAgent as LegalAssistantAgent
except ImportError:
    try:
        from src.agents.legal_agent import LegalAssistantAgent
    except ImportError:
        from src.agents.simple_agent import SimpleLegalAgent as LegalAssistantAgent


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agentic Lawyer AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design tokens ─────────────────────────────────────────────────────────────
NAVY   = "#0f1e36"
GOLD   = "#c9a84c"
GOLD_L = "#e8c97e"
BG     = "#f4f6f9"
WHITE  = "#ffffff"
SLATE  = "#64748b"
HIGH   = "#dc2626"
MED    = "#d97706"
LOW    = "#16a34a"
BORDER = "#e2e8f0"

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
    background: {NAVY} !important;
    border-right: 1px solid rgba(201,168,76,0.2);
}}
[data-testid="stSidebar"] * {{
    color: #e2e8f0 !important;
}}
[data-testid="stSidebar"] .stButton > button {{
    background: transparent !important;
    border: 1px solid {GOLD} !important;
    color: {GOLD} !important;
    border-radius: 8px !important;
    width: 100%;
    font-weight: 500;
    transition: all 0.2s;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: {GOLD} !important;
    color: {NAVY} !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: rgba(201,168,76,0.2) !important;
}}

/* ── Main area ── */
.main .block-container {{
    padding: 0.75rem 1.5rem 2.5rem;
    max-width: 1280px;
}}

/* ── Top bar ── */
.top-bar {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 0.9rem;
    padding: 0.4rem 0 0.6rem;
    border-bottom: 1px solid {BORDER};
    flex-wrap: wrap;
}}
.top-bar-icon {{
    font-size: 1.7rem;
    line-height: 1;
}}
.top-bar-title {{
    font-size: 1.3rem;
    font-weight: 700;
    color: {NAVY};
    margin: 0;
    letter-spacing: -0.02em;
    line-height: 1.2;
}}
.top-bar-subtitle {{
    font-size: 0.78rem;
    color: {SLATE};
    margin: 0;
    line-height: 1.3;
}}
.top-bar-meta {{
    margin-left: auto;
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
}}

/* Tighter sidebar */
[data-testid="stSidebar"] .block-container {{
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
}}
[data-testid="stSidebar"] hr {{ margin: 0.55rem 0 !important; }}
[data-testid="stSidebar"] .stButton > button {{
    padding: 0.4rem 0.6rem !important;
    font-size: 0.85rem !important;
}}

/* ── Status pill ── */
.pill {{
    display: inline-block;
    padding: 4px 14px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.03em;
}}
/* !important needed — overrides the sidebar's blanket text-color rule */
.pill-ok   {{ background: #bbf7d0 !important; color: #14532d !important;
              border: 1px solid #4ade80 !important; }}
.pill-warn {{ background: #fde68a !important; color: #78350f !important;
              border: 1px solid #f59e0b !important; }}
.pill-err  {{ background: #fecaca !important; color: #7f1d1d !important;
              border: 1px solid #f87171 !important; }}

/* ── Sidebar file uploader ──
   Streamlit 1.56 only tags the widget and dropzone with test-ids; the
   uploaded-file row (filename, size, × button) has NO test-id. Strategy:
   default ALL uploader text to dark navy (for the white file-row pill),
   then override the dropzone back to white via a more-specific selector. */

/* DEFAULT: dark navy text on everything in the uploader */
[data-testid="stSidebar"] [data-testid="stFileUploader"],
[data-testid="stSidebar"] [data-testid="stFileUploader"] * {{
    color: {NAVY} !important;
}}

/* DROPZONE override: navy bg → white text */
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {{
    background: #1b2a47 !important;
    border: 1px dashed {GOLD} !important;
    border-radius: 10px !important;
}}
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"],
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] * {{
    color: #f1f5f9 !important;
}}

/* Browse files button — gold pill with navy text */
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button {{
    background: {GOLD} !important;
    color: {NAVY} !important;
    border: none !important;
    font-weight: 600 !important;
}}
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] button:hover {{
    background: {GOLD_L} !important;
}}

/* Uploaded-file CHIP (Streamlit 1.56 uses stFileChipName, not stFileUploaderFile).
   The chip is rendered INSIDE the dropzone, so these selectors must include the
   dropzone ancestor to out-specify the dropzone-default near-white color rule above. */
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] [data-testid="stFileChipName"],
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] [data-testid="stFileChipName"] *,
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] [data-testid="stFileChipName"] + div,
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] [data-testid="stFileChipName"] ~ div {{
    color: #000 !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}}
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] [data-testid="stFileChipName"] {{
    font-weight: 700 !important;
    word-break: break-all !important;
}}
/* The file-size div sits as a sibling of stFileChipName, also no test-id */
[data-testid="stSidebar"] [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] [data-testid="stFileChipName"] + div {{
    color: #000 !important;
    font-weight: 600 !important;
    font-size: 0.78rem !important;
    opacity: 1 !important;
}}

/* Fallback: file-size <small> tag (older Streamlit path) */
[data-testid="stSidebar"] [data-testid="stFileUploader"] small {{
    color: #475569 !important;
    font-weight: 600 !important;
}}
/* × delete button on the white file-row pill — deep amber for contrast */
[data-testid="stSidebar"] [data-testid="stFileUploader"] button[kind="borderlessIcon"],
[data-testid="stSidebar"] [data-testid="stFileUploader"] button[kind="borderlessIcon"] svg {{
    color: #b45309 !important;
    fill: #b45309 !important;
}}

/* ── Sidebar selectbox (Model picker) ──
   Sidebar's blanket text-color rule lightens label + selected value; force
   them dark for legibility. Dropdown popover renders OUTSIDE the sidebar
   in the DOM, so it gets its own rule. */
[data-testid="stSidebar"] [data-testid="stSelectbox"] label,
[data-testid="stSidebar"] [data-testid="stSelectbox"] label *,
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"],
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] *,
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] div {{
    color: {NAVY} !important;
}}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div {{
    background: #ffffff !important;
    border-color: {BORDER} !important;
}}
/* Dropdown menu items (popover is portaled to body, not the sidebar) */
[data-baseweb="popover"] li,
[data-baseweb="popover"] [role="option"],
[data-baseweb="popover"] [role="option"] * {{
    color: {NAVY} !important;
}}

/* ── Welcome card ── */
.welcome-card {{
    background: {WHITE};
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 1.6rem 2rem;
    text-align: center;
    box-shadow: 0 2px 14px rgba(0,0,0,0.05);
    max-width: 640px;
    margin: 1.25rem auto 1rem;
}}
.welcome-icon {{
    font-size: 2.4rem;
    margin-bottom: 0.4rem;
}}
.welcome-title {{
    font-size: 1.4rem;
    font-weight: 700;
    color: {NAVY};
    margin-bottom: 0.3rem;
    letter-spacing: -0.02em;
}}
.welcome-body {{
    color: {SLATE};
    font-size: 0.9rem;
    line-height: 1.55;
    margin-bottom: 0;
}}

/* ── Step cards (How it works) ── */
.step-card {{
    background: {WHITE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 0.85rem 1rem;
    height: 100%;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}}
.step-num {{
    display: inline-block;
    width: 22px; height: 22px;
    border-radius: 999px;
    background: {NAVY};
    color: {GOLD};
    font-size: 0.74rem;
    font-weight: 700;
    text-align: center;
    line-height: 22px;
    margin-right: 6px;
}}
.step-title {{
    font-size: 0.92rem;
    font-weight: 700;
    color: {NAVY};
    display: inline;
}}
.step-body {{
    font-size: 0.8rem;
    color: {SLATE};
    margin-top: 6px;
    line-height: 1.45;
}}

/* ── Risk metric cards ── */
.metric-row {{
    display: flex;
    gap: 0.6rem;
    margin-bottom: 0.85rem;
}}
.metric-card {{
    flex: 1;
    background: {WHITE};
    border-radius: 10px;
    padding: 0.75rem 0.6rem;
    text-align: center;
    border: 1px solid {BORDER};
    box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}}
.metric-num {{
    font-size: 1.55rem;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 2px;
}}
.metric-label {{
    font-size: 0.7rem;
    color: {SLATE};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
.num-high   {{ color: {HIGH}; }}
.num-med    {{ color: {MED};  }}
.num-low    {{ color: {LOW};  }}
.num-total  {{ color: {NAVY}; }}

/* ── Mini badges (jurisdiction, web indicator, confidence) ── */
.mini-badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.02em;
}}
.badge-jur     {{ background: rgba(15,30,54,0.07); color: {NAVY}; border: 1px solid {BORDER}; }}
.badge-web-on  {{ background: #dcfce7; color: #14532d; border: 1px solid #86efac; }}
.badge-web-off {{ background: #f1f5f9; color: {SLATE}; border: 1px solid {BORDER}; }}
.badge-conf    {{ background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; }}

/* ── Summary table ── */
.summary-tbl {{
    width: 100%;
    border-collapse: collapse;
    background: {WHITE};
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    border: 1px solid {BORDER};
    margin-bottom: 1rem;
}}
.summary-tbl th {{
    background: #f8fafc;
    color: {NAVY};
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.55rem 0.7rem;
    text-align: left;
    border-bottom: 1px solid {BORDER};
}}
.summary-tbl td {{
    padding: 0.55rem 0.7rem;
    font-size: 0.85rem;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: middle;
    color: #334155;
}}
.summary-tbl tr:last-child td {{ border-bottom: none; }}
.summary-tbl tr:hover td {{ background: #f8fafc; }}

.risk-pill {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
}}
.risk-pill.high {{ background: #fee2e2; color: #991b1b; }}
.risk-pill.med  {{ background: #fef3c7; color: #854d0e; }}
.risk-pill.low  {{ background: #dcfce7; color: #166534; }}

/* Confidence bar */
.conf-wrap   {{ display: inline-flex; align-items: center; gap: 6px; }}
.conf-track  {{ width: 56px; height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }}
.conf-fill   {{ height: 100%; border-radius: 3px; }}
.conf-fill.h {{ background: {LOW}; }}
.conf-fill.m {{ background: {MED}; }}
.conf-fill.l {{ background: {HIGH}; }}
.conf-num    {{ font-size: 0.78rem; color: {SLATE}; font-weight: 600; min-width: 30px; }}

/* Source chips */
.src-row {{
    margin-top: 0.55rem;
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    align-items: center;
}}
.src-row-label {{
    font-size: 0.72rem;
    color: {SLATE};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-right: 4px;
}}
.src-chip {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.74rem;
    font-weight: 500;
    text-decoration: none !important;
    border: 1px solid {BORDER};
    max-width: 240px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.src-chip.t1 {{ background: #eff6ff; color: #1e40af !important; border-color: #bfdbfe; }}
.src-chip.t2 {{ background: #fef3c7; color: #854d0e !important; border-color: #fde68a; }}
.src-chip:hover {{ filter: brightness(0.96); }}
.src-tier-tag {{ font-size: 0.62rem; font-weight: 800; opacity: 0.75; }}

/* Progress bar — give it real vertical breathing room during the run */
[data-testid="stProgress"] {{
    margin: 1rem 0 0.85rem;
}}
[data-testid="stProgress"] > div {{
    gap: 0.6rem;
}}
/* The actual filled bar (BaseWeb renders nested divs; target the inner track) */
[data-testid="stProgress"] [role="progressbar"],
[data-testid="stProgress"] > div > div > div > div {{
    height: 14px !important;
    border-radius: 7px !important;
}}
[data-testid="stProgress"] > div > div > div {{
    height: 14px !important;
    border-radius: 7px !important;
}}
[data-testid="stProgress"] p {{
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    color: {NAVY} !important;
    margin-top: 0.35rem !important;
}}

/* Live status during pipeline run */
.live-status {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0.75rem 1rem;
    background: {WHITE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin: 0.85rem 0;
}}
.live-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
    background: {GOLD};
    animation: livepulse 1.4s ease-in-out infinite;
    flex-shrink: 0;
}}
.live-stage {{
    font-weight: 700;
    color: {NAVY};
    font-size: 0.85rem;
    flex-shrink: 0;
}}
.live-msg {{
    color: {SLATE};
    font-size: 0.82rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
@keyframes livepulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.4;  transform: scale(0.85); }}
}}

/* ── Parallel board ── */
.par-board {{
    background: {WHITE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 0.6rem 0.8rem;
    margin: 0.4rem 0;
}}
.par-board-title {{
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: {SLATE};
    margin-bottom: 0.45rem;
}}
.par-chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
}}
.par-chip {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: 6px;
    font-size: 0.74rem;
    font-weight: 500;
    border: 1px solid transparent;
}}
.par-chip.queued  {{ background:#f1f5f9; color:{SLATE};  border-color:{BORDER}; }}
.par-chip.running {{ background:#fef9c3; color:#854d0e; border-color:#fde68a; animation:livepulse 1.4s ease-in-out infinite; }}
.par-chip.done    {{ background:#dcfce7; color:#166534; border-color:#bbf7d0; }}
.par-chip.error   {{ background:#fee2e2; color:#991b1b; border-color:#fecaca; }}

/* ── Mode badge ── */
.mode-badge {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.74rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
}}
.mode-badge.parallel   {{ background:#fef9c3; color:#854d0e; border:1px solid #fde68a; }}
.mode-badge.sequential {{ background:#f1f5f9; color:{SLATE};  border:1px solid {BORDER}; }}

/* ── Clause card ── */
.clause-card {{
    background: {WHITE};
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.55rem;
    border: 1px solid {BORDER};
    border-left: 4px solid {BORDER};
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
.clause-card.high   {{ border-left-color: {HIGH}; }}
.clause-card.medium {{ border-left-color: {MED};  }}
.clause-card.low    {{ border-left-color: {LOW};  }}
.clause-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 0.5rem;
}}
.clause-type {{
    font-size: 0.95rem;
    font-weight: 600;
    color: {NAVY};
    text-transform: capitalize;
}}
.clause-summary {{
    color: #374151;
    font-size: 0.9rem;
    line-height: 1.55;
}}
.flag-list {{
    margin-top: 0.6rem;
    padding-left: 1.1rem;
    font-size: 0.85rem;
    color: #4b5563;
}}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {{
    border-radius: 14px !important;
    padding: 0.75rem 1rem !important;
    margin-bottom: 0.5rem !important;
}}

/* ── Suggestions ── */
.suggestion-chip {{
    display: inline-block;
    padding: 6px 14px;
    margin: 4px;
    background: #f1f5f9;
    border: 1px solid {BORDER};
    border-radius: 999px;
    font-size: 0.83rem;
    color: #334155;
    cursor: pointer;
    transition: all 0.15s;
}}
.suggestion-chip:hover {{
    background: {NAVY};
    color: {WHITE};
    border-color: {NAVY};
}}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab"] {{
    font-weight: 600 !important;
    font-size: 0.9rem !important;
}}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {{
    color: {NAVY} !important;
    border-bottom-color: {GOLD} !important;
}}

/* ── Pipeline badge row ── */
.pipeline-row {{
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 1.2rem;
}}
.pipeline-badge {{
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    background: #f1f5f9;
    color: {SLATE};
    border: 1px solid {BORDER};
}}
.pipeline-arrow {{
    color: {SLATE};
    font-size: 0.75rem;
}}

/* ── Scrollbar ── */
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: #f1f5f9; }}
::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 3px; }}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_resource
def get_vector_store_manager():
    try:
        return VectorStoreManager()
    except Exception as e:
        st.error(f"Vector store init error: {e}")
        return None


def initialize_session_state():
    defaults = {
        "agent":                None,
        "vector_store_manager": None,
        "document_processed":   False,
        "conversation_history": [],
        "current_document":     None,
        "document_report":      None,
        "raw_document_text":    "",
        "pipeline_mode":        "sequential",
        "last_run_timing":      None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state.vector_store_manager is None:
        vm = get_vector_store_manager()
        if vm is None:
            st.error("Failed to initialize vector store. Please refresh.")
            st.stop()
        st.session_state.vector_store_manager = vm


# Models the user can pick from the sidebar. First entry is the default.
MODEL_OPTIONS = [
    ("gpt-4o-mini", "Fast (gpt-4o-mini · default)"),
    ("gpt-5.4",     "High quality (gpt-5.4 · slower)"),
]
DEFAULT_MODEL = MODEL_OPTIONS[0][0]


def setup_agent(model: Optional[str] = None):
    api_key = None
    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return None
    try:
        return LegalAssistantAgent(
            api_key=api_key,
            vector_store_manager=st.session_state.vector_store_manager,
            openai_model=model or DEFAULT_MODEL,
        )
    except Exception as e:
        st.error(f"Agent init error: {e}")
        return None


# Each pipeline stage gets a slice of the overall progress bar. Sums to 1.0.
# Tuned by approximate wall-clock cost on a typical contract.
STAGE_RANGES = {
    "intake":    (0.00, 0.06),
    "research":  (0.06, 0.30),
    "analysis":  (0.30, 0.85),
    "evaluator": (0.85, 0.97),
    "output":    (0.97, 1.00),
}
STAGE_ICONS = {
    "intake":    "📥",
    "research":  "🔍",
    "analysis":  "🧠",
    "evaluator": "✅",
    "output":    "📄",
}
STAGE_LABELS = {
    "intake":    "Intake",
    "research":  "Research",
    "analysis":  "Analysis",
    "evaluator": "Evaluator",
    "output":    "Output",
}


def _board_html(board: dict, stage_label: str, stage_icon: str) -> str:
    """Render a parallel-status board as HTML chip grid."""
    STATUS_ICON = {"queued": "⏳", "running": "🔄", "done": "✅", "error": "❌"}
    chips = []
    for _, payload in board.items():
        status, ctype = payload if isinstance(payload, tuple) else ("queued", str(payload))
        icon = STATUS_ICON.get(status, "•")
        chips.append(
            f'<span class="par-chip {status}">{icon} {ctype.replace("_", " ")}</span>'
        )
    chips_html = "".join(chips)
    return (
        f'<div class="par-board">'
        f'<div class="par-board-title">{stage_icon} {stage_label} · parallel workers</div>'
        f'<div class="par-chips">{chips_html}</div>'
        f'</div>'
    )


def run_analysis_pipeline():
    """Run the multi-agent pipeline on the already-indexed document text."""
    agent = st.session_state.get("agent")
    if agent is None or not hasattr(agent, "analyze_document"):
        st.warning("Analysis requires the PlannerAgent. Check your API key.")
        return

    doc_text = st.session_state.get("raw_document_text", "")
    if not doc_text:
        st.warning("No document text found. Please reload the document.")
        return

    import time as _time

    pipeline_mode = st.session_state.get("pipeline_mode", "sequential")
    is_parallel   = pipeline_mode == "parallel"

    # ── Live progress UI ───────────────────────────────────────────────────
    mode_icon  = "⚡" if is_parallel else "➡"
    mode_label = "Parallel" if is_parallel else "Sequential"
    progress_bar = st.progress(
        0.0, text=f"{mode_icon} {mode_label} pipeline starting…"
    )
    live_box   = st.empty()
    timer_box  = st.empty()          # live elapsed timer
    board_box  = st.empty()          # parallel clause-status grid
    detail_log = st.expander("📜  Activity log", expanded=False)
    log_box    = detail_log.empty()
    log_lines: List[str] = []

    state = {
        "max_frac":    0.0,
        "stage_start": {},   # stage → start time
        "stage_times": {},   # stage → elapsed seconds (finalised)
        "current_stage": None,
    }
    pipeline_start = _time.monotonic()

    def progress_cb(stage: str, message: str, intra_fraction: float, board=None):
        now = _time.monotonic()

        # Track per-stage timing
        if stage != state["current_stage"]:
            if state["current_stage"] is not None:
                prev = state["current_stage"]
                state["stage_times"][prev] = now - state["stage_start"].get(prev, now)
            state["current_stage"] = stage
            state["stage_start"][stage] = now

        lo, hi = STAGE_RANGES.get(stage, (0.0, 1.0))
        overall = lo + (hi - lo) * max(0.0, min(1.0, intra_fraction))
        if overall < state["max_frac"]:
            overall = state["max_frac"]
        state["max_frac"] = overall

        icon  = STAGE_ICONS.get(stage, "•")
        label = STAGE_LABELS.get(stage, stage.title())
        pct   = int(overall * 100)
        elapsed = now - pipeline_start

        progress_bar.progress(
            min(0.99, overall),
            text=f"{mode_icon} {icon} {label} · {pct}%",
        )
        safe_msg = (message or "").replace("<", "&lt;").replace(">", "&gt;")
        live_box.markdown(
            f'<div class="live-status">'
            f'<span class="live-dot"></span>'
            f'<span class="live-stage">{icon} {label}</span>'
            f'<span class="live-msg">{safe_msg}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Live elapsed timer
        timer_box.markdown(
            f'<div style="font-size:0.78rem;color:{SLATE};'
            f'font-variant-numeric:tabular-nums;margin:-4px 0 4px 2px;">'
            f'⏱ {elapsed:.1f}s elapsed</div>',
            unsafe_allow_html=True,
        )

        if board is not None and is_parallel:
            board_box.markdown(
                _board_html(board, label, icon),
                unsafe_allow_html=True,
            )
        elif not is_parallel:
            board_box.empty()

        log_lines.append(f"`{label:9s}` {message}")
        log_box.markdown("\n\n".join(log_lines[-50:]))

    try:
        report = agent.analyze_document(
            doc_text,
            web_research_enabled=st.session_state.get("web_research_enabled"),
            progress=progress_cb,
            pipeline_mode=pipeline_mode,
        )
        st.session_state.document_report = report
    except Exception as e:
        st.session_state.document_report = f"Analysis error: {e}"

    total_elapsed = _time.monotonic() - pipeline_start

    # Finalise last stage time
    if state["current_stage"]:
        last = state["current_stage"]
        state["stage_times"][last] = (
            _time.monotonic() - state["stage_start"].get(last, pipeline_start)
        )

    # Store timing in session state so it shows in the report
    st.session_state.last_run_timing = {
        "total":      total_elapsed,
        "mode":       pipeline_mode,
        "stage_times": dict(state["stage_times"]),
    }

    progress_bar.progress(1.0, text=f"✅ Done · {total_elapsed:.1f}s")
    live_box.empty()
    timer_box.empty()
    board_box.empty()
    st.session_state.analysis_running = False
    st.rerun()


def process_document(uploaded_file):
    if uploaded_file is None:
        return False
    if uploaded_file.size > 10 * 1024 * 1024:
        st.error("File too large (max 10 MB).")
        return False

    name = uploaded_file.name or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    with st.spinner("Extracting and indexing document…"):
        try:
            processor = DocumentProcessor()

            # 1. Pull raw text from the upload.
            if ext == "pdf":
                raw_text = processor.extract_text_from_pdf(uploaded_file)
                if not raw_text.strip():
                    st.error("No text could be extracted from the PDF.")
                    return False
            elif ext == "txt":
                raw = uploaded_file.read()
                try:
                    raw_text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raw_text = raw.decode("latin-1", errors="replace")
                if not raw_text.strip():
                    st.error("The .txt file appears to be empty.")
                    return False
            else:
                st.error(f"Unsupported file type: .{ext or '?'}")
                return False

            # 2. Normalize once. preprocess_text now preserves paragraph
            #    structure, which intake's segmenter relies on.
            normalized = processor.preprocess_text(raw_text)

            # 3. Chunk for the vector store + tag for retrieval metadata.
            documents = processor.split_into_chunks(normalized, name)
            enhanced_docs = processor.identify_clauses(documents)
            st.session_state.vector_store_manager.create_vectorstore(enhanced_docs)

            # 4. Store the FULL normalized text (with newlines intact) for
            #    the planner — never the chunk-joined version, which loses
            #    boundary newlines and breaks intake's regex.
            st.session_state.document_processed    = True
            st.session_state.current_document      = name
            st.session_state.document_report       = None
            st.session_state.raw_document_text     = normalized
            st.session_state.conversation_history  = []
            # Auto-start the pipeline so the user goes from upload → report
            # in a single click instead of two.
            st.session_state.analysis_running      = True
            if st.session_state.agent:
                st.session_state.agent.clear_conversation()

            st.rerun()
            return True
        except Exception as e:
            st.error(f"Processing error: {e}")
            return False


def load_sample_document():
    with st.spinner("Loading sample contract…"):
        try:
            processor   = DocumentProcessor()
            sample_text = create_sample_contract()
            docs        = processor.split_into_chunks(sample_text, "Sample Professional Services Agreement")
            enhanced_docs = processor.identify_clauses(docs)
            st.session_state.vector_store_manager.create_vectorstore(enhanced_docs)

            st.session_state.document_processed   = True
            st.session_state.current_document     = "Sample Professional Services Agreement"
            st.session_state.document_report      = None
            st.session_state.raw_document_text    = sample_text
            st.session_state.conversation_history = []
            st.session_state.analysis_running     = False
            if st.session_state.agent:
                st.session_state.agent.clear_conversation()

            st.rerun()
            return True
        except Exception as e:
            st.error(f"Error loading sample: {e}")
            return False


def handle_user_query(query: str):
    if not query or not query.strip():
        return
    if not st.session_state.agent or not st.session_state.document_processed:
        return

    with st.spinner("Thinking…"):
        try:
            response = st.session_state.agent.process_query(query.strip())
            st.session_state.conversation_history.append(
                {"user": query, "agent": response}
            )
            st.rerun()
        except Exception as e:
            err = str(e)
            if "quota" in err.lower() or "rate" in err.lower():
                st.error("API rate limit reached. Please wait and retry.")
            else:
                st.error(f"Error: {err}")


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        # ── Brand (compact) ───────────────────────────────────────────
        st.markdown(f"""
        <div style="padding:0.25rem 0 0.4rem; display:flex; align-items:center;
            gap:8px;">
            <div style="font-size:1.5rem; line-height:1;">⚖️</div>
            <div>
                <div style="font-size:1rem; font-weight:700;
                    color:{GOLD}; letter-spacing:-0.01em; line-height:1.1;">
                    Agentic Lawyer AI
                </div>
                <div style="font-size:0.7rem; color:#94a3b8;">
                    Multi-Agent Legal Analysis
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── API + Model (combined section) ────────────────────────────
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            st.markdown('<span class="pill pill-ok">● API Connected</span>',
                        unsafe_allow_html=True)

            if "openai_model" not in st.session_state:
                st.session_state.openai_model = DEFAULT_MODEL
            model_ids    = [m[0] for m in MODEL_OPTIONS]
            model_labels = [m[1] for m in MODEL_OPTIONS]
            try:
                current_index = model_ids.index(st.session_state.openai_model)
            except ValueError:
                current_index = 0
            picked_label = st.selectbox(
                "Model",
                options=model_labels,
                index=current_index,
                help="`gpt-4o-mini` is faster and cheaper. Switch to "
                     "`gpt-5.4` for higher-quality analysis on complex docs.",
            )
            picked_id = model_ids[model_labels.index(picked_label)]
            if (picked_id != st.session_state.openai_model
                    or st.session_state.agent is None):
                st.session_state.openai_model = picked_id
                st.session_state.agent = setup_agent(picked_id)
        else:
            st.markdown('<span class="pill pill-err">● API Key Missing</span>',
                        unsafe_allow_html=True)
            st.caption("Add OPENAI_API_KEY to your .env file")

        st.markdown("---")

        # ── Document section (combined upload + sample + research toggle) ──
        st.markdown(
            f'<div style="font-size:0.74rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.08em;'
            f'color:{GOLD};margin-bottom:0.4rem;">Document</div>',
            unsafe_allow_html=True
        )

        uploaded_file = st.file_uploader(
            "Upload document",
            type=["pdf", "txt"],
            label_visibility="collapsed",
            help="Upload a legal contract (PDF or .txt, max 10 MB)",
        )

        if uploaded_file and uploaded_file.name != st.session_state.current_document:
            if st.button("⚡  Analyze", width="stretch", type="primary",
                         key="btn_sb_analyze"):
                process_document(uploaded_file)

        if not st.session_state.document_processed:
            if st.button("📄  Try a Sample Contract", width="stretch",
                         key="btn_sb_sample"):
                load_sample_document()

        # Web-research toggle inline
        if "web_research_enabled" not in st.session_state:
            st.session_state.web_research_enabled = (
                os.getenv("WEB_RESEARCH_ENABLED", "true").strip().lower()
                in ("1", "true", "yes", "on")
            )
        st.checkbox(
            "🌐  Live web research",
            key="web_research_enabled",
            help="Supplements local retrieval with whitelisted public legal "
                 "sources (Indian Kanoon, BAILII, Cornell LII). Disable for "
                 "offline runs.",
        )

        st.markdown("---")
        st.markdown(
            f'<div style="font-size:0.74rem;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.08em;'
            f'color:{GOLD};margin-bottom:0.4rem;">Pipeline Mode</div>',
            unsafe_allow_html=True,
        )
        mode_choice = st.radio(
            "Pipeline mode",
            options=["Sequential", "Parallel"],
            index=0 if st.session_state.get("pipeline_mode", "sequential") == "sequential" else 1,
            label_visibility="collapsed",
            help=(
                "**Sequential** — agents run one after another (original).\n\n"
                "**Parallel** — clauses processed concurrently within each "
                "agent stage; research agent gains an internal reflection loop "
                "to improve RAG quality before handing off to analysis."
            ),
        )
        st.session_state.pipeline_mode = mode_choice.lower()
        if st.session_state.pipeline_mode == "parallel":
            st.markdown(
                '<div style="font-size:0.72rem;color:#fde68a;margin-top:4px;">'
                '⚡ Clauses processed in parallel within each stage. '
                'Live status cards shown during run.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-size:0.72rem;color:#94a3b8;margin-top:4px;">'
                '➡ Clauses processed one-by-one (stable, predictable).</div>',
                unsafe_allow_html=True,
            )

        # ── Active document card (only when loaded) ───────────────────
        if st.session_state.document_processed:
            st.markdown("---")
            doc_name = st.session_state.current_document or "Unknown"
            stats    = st.session_state.vector_store_manager.get_stats()
            chunks   = stats.get("total_documents", 0)

            agent = st.session_state.get("agent")
            last_state = (agent.get_last_state()
                          if agent and hasattr(agent, "get_last_state")
                          else None)
            web_n = 0
            jur   = ""
            if last_state:
                rc = last_state.get("research_context", {}) or {}
                web_n = sum(len(cr.web_results) for cr in rc.values() if cr)
                jur   = last_state.get("jurisdiction", "") or ""

            meta_bits = [f"{chunks} chunks"]
            if jur and jur != "unknown":
                meta_bits.append(f"jur·{jur.upper()}")
            if web_n:
                meta_bits.append(f"🌐 {web_n} sources")

            st.markdown(f"""
            <div style="background:rgba(201,168,76,0.16);border:1px solid
                rgba(201,168,76,0.5);border-radius:10px;padding:0.7rem 0.85rem;
                margin-bottom:0.85rem;">
                <div style="font-size:0.66rem;color:{GOLD_L};
                    text-transform:uppercase;letter-spacing:0.08em;font-weight:700;
                    margin-bottom:5px;">Active Document</div>
                <div style="font-size:0.88rem;font-weight:700;
                    color:#ffffff;word-break:break-word;line-height:1.3;">{doc_name}</div>
                <div style="font-size:0.72rem;color:#e2e8f0;margin-top:6px;font-weight:500;">
                    {' · '.join(meta_bits)}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Action row — Re-analyze + Clear, side by side
            col_re, col_clr = st.columns(2)
            with col_re:
                if st.session_state.document_report:
                    if st.button("🔄  Re-run", width="stretch", key="btn_rerun"):
                        st.session_state.document_report  = None
                        st.session_state.analysis_running = True
                        st.rerun()
            with col_clr:
                if st.button("🗑️  Clear", width="stretch", key="btn_clear"):
                    if st.session_state.agent:
                        st.session_state.agent.clear_conversation()
                    st.session_state.conversation_history = []
                    st.session_state.document_processed   = False
                    st.session_state.document_report      = None
                    st.session_state.current_document     = None
                    st.session_state.raw_document_text    = ""
                    st.session_state.analysis_running     = False
                    st.rerun()


# ── Report renderer ───────────────────────────────────────────────────────────

def _risk_pill(risk: str) -> str:
    cls = {"high": "high", "medium": "med", "low": "low"}.get(risk, "low")
    return f'<span class="risk-pill {cls}">{risk.title()}</span>'


def _conf_bar(conf: float) -> str:
    pct = max(0, min(100, int((conf or 0) * 100)))
    cls = "h" if pct >= 75 else ("m" if pct >= 50 else "l")
    return (f'<span class="conf-wrap">'
            f'<span class="conf-track"><span class="conf-fill {cls}" '
            f'style="width:{pct}%"></span></span>'
            f'<span class="conf-num">{pct}%</span></span>')


def _source_chips_html(web_results) -> str:
    if not web_results:
        return ""
    chips = []
    for w in web_results[:6]:
        tier_cls = "t1" if getattr(w, "tier", 1) == 1 else "t2"
        tier_tag = "T1" if getattr(w, "tier", 1) == 1 else "T2"
        label = (getattr(w, "source_name", "") or
                 getattr(w, "title", "") or "source")
        if len(label) > 30:
            label = label[:28] + "…"
        url = getattr(w, "url", "#")
        chips.append(
            f'<a class="src-chip {tier_cls}" href="{url}" target="_blank" '
            f'rel="noopener" title="{getattr(w, "title", "")}">'
            f'<span class="src-tier-tag">{tier_tag}</span>{label}</a>'
        )
    if len(web_results) > 6:
        chips.append(
            f'<span class="src-chip" style="background:#f8fafc;">'
            f'+{len(web_results)-6} more</span>'
        )
    return ('<div class="src-row">'
            '<span class="src-row-label">🌐 Sources</span>'
            + "".join(chips) + '</div>')


def render_report(report_md: str):
    """Render the analysis report from structured agent state.

    Falls back to splitting the markdown if get_last_state() is unavailable
    (e.g. a non-PlannerAgent backend).
    """
    import re

    agent = st.session_state.get("agent")
    last_state = (agent.get_last_state()
                  if agent and hasattr(agent, "get_last_state")
                  else None)

    analyses     = (last_state or {}).get("analysis_results", []) or []
    research_ctx = (last_state or {}).get("research_context", {}) or {}
    jurisdiction = (last_state or {}).get("jurisdiction", "") or "unknown"
    web_enabled  = bool(st.session_state.get("web_research_enabled"))

    # Risk counts — prefer structured state, fall back to regex on markdown
    if analyses:
        high_n = sum(1 for a in analyses if a.risk_level == "high")
        med_n  = sum(1 for a in analyses if a.risk_level == "medium")
        low_n  = sum(1 for a in analyses if a.risk_level == "low")
    else:
        high_n = int((re.search(r'High \| (\d+)',   report_md) or [None,'0'])[1])
        med_n  = int((re.search(r'Medium \| (\d+)', report_md) or [None,'0'])[1])
        low_n  = int((re.search(r'Low \| (\d+)',    report_md) or [None,'0'])[1])
    total_n = high_n + med_n + low_n

    # Web-source totals
    web_total = sum(len(cr.web_results) for cr in research_ctx.values() if cr)
    web_t1    = sum(sum(1 for w in cr.web_results if w.tier == 1)
                    for cr in research_ctx.values() if cr)
    web_t2    = web_total - web_t1
    avg_conf  = (sum(getattr(a, "confidence", 0) for a in analyses) / len(analyses)
                 if analyses else 0)

    # ── Indicator row: jurisdiction + web research + average confidence ──
    bits = []
    if jurisdiction and jurisdiction != "unknown":
        bits.append(f'<span class="mini-badge badge-jur">⚖️ {jurisdiction.upper()} jurisdiction</span>')
    if web_enabled and web_total:
        bits.append(
            f'<span class="mini-badge badge-web-on">🌐 {web_total} web sources '
            f'<span style="opacity:.7;font-weight:600;">'
            f'(T1·{web_t1}{f" / T2·{web_t2}" if web_t2 else ""})</span></span>'
        )
    elif web_enabled:
        bits.append('<span class="mini-badge badge-web-on">🌐 Web research on</span>')
    else:
        bits.append('<span class="mini-badge badge-web-off">📚 Local-only</span>')
    if avg_conf:
        bits.append(f'<span class="mini-badge badge-conf">✓ {int(avg_conf*100)}% avg confidence</span>')

    if bits:
        st.markdown(
            f'<div style="display:flex;gap:6px;flex-wrap:wrap;'
            f'margin-bottom:0.6rem;">{" ".join(bits)}</div>',
            unsafe_allow_html=True,
        )

    # ── Pipeline badges ───────────────────────────────────────────────────
    _pm     = st.session_state.get("pipeline_mode", "sequential")
    _pm_icon  = "⚡" if _pm == "parallel" else "➡"
    _pm_label = "Parallel" if _pm == "parallel" else "Sequential"
    _pm_cls   = _pm
    st.markdown(f"""
    <div class="pipeline-row">
        <span class="mode-badge {_pm_cls}">{_pm_icon} {_pm_label}</span>
        <span class="pipeline-badge">📥 Intake</span>
        <span class="pipeline-arrow">→</span>
        <span class="pipeline-badge">🔍 Research</span>
        <span class="pipeline-arrow">→</span>
        <span class="pipeline-badge">🧠 Analysis</span>
        <span class="pipeline-arrow">→</span>
        <span class="pipeline-badge">✅ Evaluator</span>
        <span class="pipeline-arrow">→</span>
        <span class="pipeline-badge">📄 Output</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Timing summary ───────────────────────────────────────────────────
    timing = st.session_state.get("last_run_timing")
    if timing:
        total  = timing.get("total", 0)
        mode   = timing.get("mode", "sequential")
        stages = timing.get("stage_times", {})
        t_icon = "⚡" if mode == "parallel" else "➡"
        stage_bits = " &nbsp;|&nbsp; ".join(
            f'{STAGE_ICONS.get(s, "•")} {STAGE_LABELS.get(s, s.title())}: <b>{t:.1f}s</b>'
            for s, t in stages.items() if t > 0.05
        )
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;'
            f'padding:0.5rem 0.8rem;background:#f8fafc;border:1px solid {BORDER};'
            f'border-radius:8px;margin-bottom:0.8rem;flex-wrap:wrap;">'
            f'<span style="font-size:0.82rem;font-weight:700;color:{NAVY};">'
            f'⏱ {t_icon} {mode.title()} · <span style="color:{GOLD};">{total:.1f}s total</span>'
            f'</span>'
            f'<span style="font-size:0.76rem;color:{SLATE};">{stage_bits}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Metric row ────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-num num-total">{total_n}</div>
            <div class="metric-label">Clauses</div>
        </div>
        <div class="metric-card">
            <div class="metric-num num-high">{high_n}</div>
            <div class="metric-label">High Risk</div>
        </div>
        <div class="metric-card">
            <div class="metric-num num-med">{med_n}</div>
            <div class="metric-label">Medium Risk</div>
        </div>
        <div class="metric-card">
            <div class="metric-num num-low">{low_n}</div>
            <div class="metric-label">Standard</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Quick summary table ───────────────────────────────────────────────
    if analyses:
        # Order: high → medium → low for at-a-glance scanning
        risk_rank = {"high": 0, "medium": 1, "low": 2}
        ordered = sorted(analyses, key=lambda a: risk_rank.get(a.risk_level, 3))

        rows_html = []
        for i, a in enumerate(ordered, 1):
            cr = research_ctx.get(a.clause_id)
            n_web = len(cr.web_results) if cr else 0
            n_t1  = sum(1 for w in cr.web_results if w.tier == 1) if cr else 0
            n_t2  = n_web - n_t1
            web_cell = (f'🌐 {n_web} '
                        f'<span style="color:#1e40af;font-size:0.7rem;font-weight:700;">T1·{n_t1}</span>'
                        + (f' <span style="color:#854d0e;font-size:0.7rem;font-weight:700;">T2·{n_t2}</span>'
                           if n_t2 else "")) if n_web else \
                       '<span style="color:#94a3b8;">—</span>'
            flag_cell = (str(len(a.flags))
                         if a.flags
                         else '<span style="color:#94a3b8;">—</span>')
            ctype = (a.clause_type or "").replace("_", " ").title() or "Clause"
            rows_html.append(
                f"<tr>"
                f"<td style='color:#94a3b8;font-weight:600;'>{i}</td>"
                f"<td style='font-weight:600;color:{NAVY};'>{ctype}</td>"
                f"<td>{_risk_pill(a.risk_level)}</td>"
                f"<td>{_conf_bar(getattr(a, 'confidence', 0))}</td>"
                f"<td>{flag_cell}</td>"
                f"<td>{web_cell}</td>"
                f"</tr>"
            )

        st.markdown(
            '<div style="font-size:0.74rem;font-weight:700;color:'
            f'{NAVY};text-transform:uppercase;letter-spacing:0.06em;'
            'margin:0.4rem 0 0.4rem;">Quick Summary</div>'
            '<table class="summary-tbl">'
            '<thead><tr>'
            '<th style="width:32px;">#</th>'
            '<th>Clause</th>'
            '<th style="width:90px;">Risk</th>'
            '<th style="width:130px;">Confidence</th>'
            '<th style="width:70px;">Flags</th>'
            '<th style="width:160px;">Web Sources</th>'
            '</tr></thead>'
            '<tbody>' + "".join(rows_html) + '</tbody></table>',
            unsafe_allow_html=True,
        )

    # ── Per-clause detail (structured rendering when state is available) ──
    if analyses:
        risk_rank = {"high": 0, "medium": 1, "low": 2}
        ordered = sorted(analyses, key=lambda a: risk_rank.get(a.risk_level, 3))

        def _render_clause(a):
            cr = research_ctx.get(a.clause_id)
            ctype = (a.clause_type or "").replace("_", " ").title() or "Clause"
            cls   = {"high": "high", "medium": "medium", "low": "low"}.get(a.risk_level, "low")
            flags_html = ""
            if a.flags:
                flags_html = ('<div style="margin-top:0.4rem;font-size:0.82rem;'
                              'color:#4b5563;"><strong>Flags:</strong><ul style="'
                              'margin:4px 0 0 1.1rem;padding:0;">'
                              + "".join(f"<li>{f}</li>" for f in a.flags)
                              + "</ul></div>")
            obs_html = ""
            if a.obligations:
                obs_html = ('<div style="margin-top:0.35rem;font-size:0.82rem;'
                            'color:#4b5563;"><strong>Obligations:</strong><ul style="'
                            'margin:4px 0 0 1.1rem;padding:0;">'
                            + "".join(f"<li>{o}</li>" for o in a.obligations)
                            + "</ul></div>")
            sources_html = _source_chips_html(cr.web_results) if cr else ""
            st.markdown(
                f'<div class="clause-card {cls}">'
                f'<div class="clause-header">'
                f'<span class="clause-type">{ctype}</span>'
                f'{_risk_pill(a.risk_level)}'
                f'<span style="margin-left:auto;">{_conf_bar(getattr(a, "confidence", 0))}</span>'
                f'</div>'
                f'<div class="clause-summary">{a.plain_summary}</div>'
                f'{flags_html}{obs_html}{sources_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # High-risk: rendered open with a header band
        high_clauses = [a for a in ordered if a.risk_level == "high"]
        med_clauses  = [a for a in ordered if a.risk_level == "medium"]
        low_clauses  = [a for a in ordered if a.risk_level == "low"]

        if high_clauses:
            st.markdown(
                f'<div style="background:#fef2f2;border:1px solid #fecaca;'
                f'border-radius:10px;padding:0.55rem 0.9rem;margin:0.6rem 0 0.5rem;">'
                f'<span style="color:{HIGH};font-weight:700;font-size:0.95rem;">'
                f'🔴 High-Risk Clauses ({len(high_clauses)})</span></div>',
                unsafe_allow_html=True,
            )
            for a in high_clauses:
                _render_clause(a)

        if med_clauses:
            with st.expander(f"🟡  Medium-Risk Clauses ({len(med_clauses)})", expanded=False):
                for a in med_clauses:
                    _render_clause(a)

        if low_clauses:
            with st.expander(f"🟢  Standard / Low-Risk Clauses ({len(low_clauses)})", expanded=False):
                for a in low_clauses:
                    _render_clause(a)

        # ── Recommendations (still pulled from the markdown report) ───────
        rec_match = re.search(r'#{1,3} Recommendations?.*?(?=\n#{1,3} |\Z)',
                              report_md, flags=re.DOTALL)
        if rec_match:
            st.markdown("---")
            st.markdown(
                f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;'
                f'border-radius:10px;padding:0.55rem 0.9rem;margin-bottom:0.6rem;">'
                f'<span style="color:{LOW};font-weight:700;">✅ Recommendations'
                f'</span></div>',
                unsafe_allow_html=True,
            )
            body = re.sub(r'^#{1,3} Recommendation.*?\n', '', rec_match.group(0))
            st.markdown(body)
        return

    # ── Fallback: legacy markdown-only rendering ──────────────────────────
    sections = re.split(r'\n(?=#{1,3} )', report_md)
    for section in sections:
        if not section.strip():
            continue
        if '🔴 High' in section:
            st.markdown(
                f'<div style="background:#fef2f2;border:1px solid #fecaca;'
                f'border-radius:10px;padding:0.55rem 0.9rem;margin-bottom:0.5rem;">'
                f'<span style="color:{HIGH};font-weight:700;font-size:0.95rem;">'
                f'🔴 High-Risk Clauses</span></div>',
                unsafe_allow_html=True,
            )
            st.markdown(re.sub(r'^#{1,3} 🔴.*\n', '', section, flags=re.MULTILINE))
        elif '🟡 Medium' in section:
            with st.expander("🟡  Medium-Risk Clauses", expanded=False):
                st.markdown(re.sub(r'^#{1,3} 🟡.*\n', '', section, flags=re.MULTILINE))
        elif '🟢 Standard' in section or '🟢 Low' in section:
            with st.expander("🟢  Standard / Low-Risk Clauses", expanded=False):
                st.markdown(re.sub(r'^#{1,3} 🟢.*\n', '', section, flags=re.MULTILINE))
        elif 'Recommendation' in section:
            st.markdown("---")
            st.markdown(
                f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;'
                f'border-radius:10px;padding:0.55rem 0.9rem;margin-bottom:0.5rem;">'
                f'<span style="color:{LOW};font-weight:700;">✅ Recommendations'
                f'</span></div>',
                unsafe_allow_html=True,
            )
            st.markdown(re.sub(r'^#{1,3} Recommendation.*\n', '', section, flags=re.MULTILINE))
        elif 'Risk Summary' in section or 'Analysis Report' in section:
            pass
        else:
            st.markdown(section)


# ── Chat renderer ─────────────────────────────────────────────────────────────

def render_chat():
    history = st.session_state.conversation_history

    if not history:
        st.markdown(f"""
        <div style="text-align:center;padding:3rem 1rem;color:{SLATE};">
            <div style="font-size:2.5rem;margin-bottom:0.75rem;">💬</div>
            <div style="font-size:1rem;font-weight:600;color:{NAVY};
                margin-bottom:0.4rem;">Ask anything about this document</div>
            <div style="font-size:0.88rem;">
                Use the suggestions on the right or type your own question below.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    for turn in history:
        with st.chat_message("user"):
            st.markdown(turn["user"])
        with st.chat_message("assistant", avatar="⚖️"):
            st.markdown(turn["agent"])


def render_suggestions():
    st.markdown(
        f'<div style="font-size:0.74rem;font-weight:700;color:{NAVY};'
        f'text-transform:uppercase;letter-spacing:0.06em;'
        f'margin-bottom:0.5rem;">Quick Questions</div>',
        unsafe_allow_html=True
    )

    try:
        suggestions = st.session_state.agent.get_follow_up_suggestions()
    except Exception:
        suggestions = [
            "What is the termination clause?",
            "What are the payment terms?",
            "What are my obligations?",
            "What are the key risks?",
            "Explain the liability clause",
        ]

    for s in suggestions:
        if st.button(s, key=f"sug_{hash(s)}", width="stretch"):
            handle_user_query(s)


# ── Document preview renderer ─────────────────────────────────────────────────

def render_document_preview():
    import html

    doc_text = st.session_state.get("raw_document_text", "") or ""
    doc_name = st.session_state.get("current_document") or "document"

    if not doc_text.strip():
        st.markdown(f"""
        <div style="text-align:center;padding:3rem 1rem;color:{SLATE};">
            <div style="font-size:2.5rem;margin-bottom:0.75rem;">📄</div>
            <div style="font-size:1rem;font-weight:600;color:{NAVY};
                margin-bottom:0.4rem;">No document text available</div>
            <div style="font-size:0.88rem;">
                Upload a document to see its content here.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    char_count = len(doc_text)
    word_count = len(doc_text.split())
    line_count = doc_text.count("\n") + 1

    info_col, dl_col = st.columns([3, 1])
    with info_col:
        st.markdown(
            f'<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:0.6rem;">'
            f'<span class="mini-badge badge-jur">📄 {html.escape(doc_name)}</span>'
            f'<span class="mini-badge badge-conf">{word_count:,} words</span>'
            f'<span class="mini-badge badge-conf">{char_count:,} chars</span>'
            f'<span class="mini-badge badge-conf">{line_count:,} lines</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with dl_col:
        st.download_button(
            "⬇  Download text",
            data=doc_text,
            file_name=f"{doc_name.rsplit('.', 1)[0]}.txt",
            mime="text/plain",
            width="stretch",
            key="btn_download_doc_text",
        )

    safe_text = html.escape(doc_text)
    st.markdown(
        f'<div style="background:{WHITE};border:1px solid {BORDER};border-radius:12px;'
        f'padding:1.25rem 1.5rem;max-height:70vh;overflow-y:auto;'
        f'font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;'
        f'font-size:0.86rem;line-height:1.6;color:{NAVY};white-space:pre-wrap;'
        f'word-wrap:break-word;">{safe_text}</div>',
        unsafe_allow_html=True,
    )


# ── Welcome screen ────────────────────────────────────────────────────────────

def render_welcome():
    # Hero card
    st.markdown(f"""
    <div class="welcome-card">
        <div class="welcome-icon">⚖️</div>
        <div class="welcome-title">Read your contract before signing.</div>
        <div class="welcome-body">
            Upload a contract, and a 5-agent pipeline extracts clauses,
            flags risks, scores confidence, and cites public legal sources —
            in plain English, before you ask a single question.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick CTA row — two compact buttons centered
    _, c1, c2, _ = st.columns([1, 1, 1, 1])
    with c1:
        if st.button("📄  Try a Sample Contract", width="stretch",
                     type="primary", key="btn_welcome_sample"):
            load_sample_document()
    with c2:
        st.markdown(
            f'<div style="text-align:center;padding:0.45rem 0;font-size:0.85rem;'
            f'color:{SLATE};">or upload via the sidebar →</div>',
            unsafe_allow_html=True,
        )

    # ── How it works (3 steps) ────────────────────────────────────────
    st.markdown(
        f'<div style="margin:1.4rem 0 0.6rem;text-align:center;">'
        f'<div style="font-size:0.72rem;font-weight:700;color:{GOLD};'
        f'text-transform:uppercase;letter-spacing:0.12em;">How it works</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    steps = [
        ("Upload",   "PDF or .txt up to 10 MB. We extract, normalize and index it locally."),
        ("Analyze",  "5 agents segment clauses, retrieve precedents, flag risks, score confidence."),
        ("Chat",     "Ask follow-ups grounded in the full analysis with cited sources."),
    ]
    cols = st.columns(3)
    for col, (title, body), n in zip(cols, steps, range(1, 4)):
        with col:
            st.markdown(f"""
            <div class="step-card">
                <div><span class="step-num">{n}</span><span class="step-title">{title}</span></div>
                <div class="step-body">{body}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Supported categories — single compact strip ───────────────────
    cats = "  •  ".join([
        "🤝 Service & SLAs",
        "🔒 NDAs",
        "💼 Employment",
        "🏢 Leases",
        "💻 Software / SaaS",
        "🛒 Purchase",
        "📊 Partnership / LLC",
        "📜 Settlement",
    ])
    st.markdown(f"""
    <div style="margin:1.5rem auto 0;max-width:920px;text-align:center;
        background:{WHITE};border:1px solid {BORDER};border-radius:12px;
        padding:0.7rem 1rem;border-top:3px solid {GOLD};
        font-size:0.82rem;color:#334155;line-height:1.6;">
        <span style="font-size:0.7rem;font-weight:700;color:{GOLD};
            text-transform:uppercase;letter-spacing:0.12em;
            display:block;margin-bottom:0.25rem;">Supported Document Types</span>
        {cats}
    </div>
    <div style="text-align:center;font-size:0.72rem;color:{SLATE};
        margin-top:0.5rem;font-style:italic;">
        Text-based PDFs only. Scanned-image PDFs and non-English documents not supported.
    </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    initialize_session_state()
    render_sidebar()

    # Top bar — shorter subtitle, optional indicators on the right
    agent      = st.session_state.get("agent")
    last_state = (agent.get_last_state()
                  if agent and hasattr(agent, "get_last_state")
                  else None)
    meta_html = ""
    if last_state and st.session_state.get("document_report"):
        rc = last_state.get("research_context", {}) or {}
        web_n = sum(len(cr.web_results) for cr in rc.values() if cr)
        jur   = (last_state.get("jurisdiction", "") or "").upper()
        bits = []
        if jur and jur != "UNKNOWN":
            bits.append(f'<span class="mini-badge badge-jur">⚖️ {jur}</span>')
        if web_n:
            bits.append(f'<span class="mini-badge badge-web-on">🌐 {web_n}</span>')
        elif st.session_state.get("web_research_enabled"):
            bits.append('<span class="mini-badge badge-web-on">🌐 on</span>')
        if bits:
            meta_html = f'<div class="top-bar-meta">{" ".join(bits)}</div>'

    st.markdown(f"""
    <div class="top-bar">
        <span class="top-bar-icon">⚖️</span>
        <div>
            <p class="top-bar-title">Agentic Lawyer AI</p>
            <p class="top-bar-subtitle">Plain-English contract review with cited sources.</p>
        </div>
        {meta_html}
    </div>
    """, unsafe_allow_html=True)

    # ── No document loaded → welcome ──────────────────────────────────────────
    if not st.session_state.document_processed:
        render_welcome()
        return

    # ── Document indexed, analysis not yet run → ready / running ─────────────
    if st.session_state.document_report is None:
        doc_name = st.session_state.current_document or "document"
        running  = bool(st.session_state.get("analysis_running", False))

        if running:
            # Compact running header: doc name + stop button on one line
            head, stop_col = st.columns([5, 1])
            with head:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;'
                    f'padding:0.55rem 0.85rem;background:{WHITE};border:1px solid {BORDER};'
                    f'border-radius:10px;">'
                    f'<span style="font-size:1.35rem;">📄</span>'
                    f'<div style="overflow:hidden;">'
                    f'<div style="font-size:0.92rem;font-weight:700;color:{NAVY};'
                    f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                    f'{doc_name}</div>'
                    f'<div style="font-size:0.74rem;color:{SLATE};">'
                    f'Running 5-agent analysis pipeline…</div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            with stop_col:
                if st.button("⏹  Stop", width="stretch", key="btn_stop"):
                    st.session_state.analysis_running = False
                    st.rerun()
            # Synchronous run. Stop registers on the next rerun.
            run_analysis_pipeline()
        else:
            # Idle (e.g. user clicked Re-run): tighter single-button card
            st.markdown(f"""
            <div style="background:{WHITE};border:1px solid {BORDER};border-radius:14px;
                padding:1.5rem 1.5rem;text-align:center;max-width:560px;margin:1.5rem auto;
                box-shadow:0 2px 12px rgba(0,0,0,0.05);">
                <div style="font-size:2rem;margin-bottom:0.4rem;">📄</div>
                <div style="font-size:1.1rem;font-weight:700;color:{NAVY};
                    margin-bottom:0.3rem;">{doc_name}</div>
                <div style="font-size:0.85rem;color:{SLATE};margin-bottom:1rem;
                    line-height:1.55;">Indexed and ready for analysis.</div>
            </div>
            """, unsafe_allow_html=True)
            _, btn_col, _ = st.columns([2, 1, 2])
            with btn_col:
                if st.button("🚀  Run Analysis", width="stretch", type="primary",
                             key="btn_run_analysis"):
                    st.session_state.analysis_running = True
                    st.rerun()
        return

    # ── Report ready → tabbed view ────────────────────────────────────────────
    tab_report, tab_chat, tab_preview = st.tabs(
        ["📋  Analysis Report", "💬  Chat with Document", "📄  Document Preview"]
    )

    with tab_report:
        render_report(st.session_state.document_report)

    with tab_chat:
        chat_col, sug_col = st.columns([3, 1])
        with chat_col:
            render_chat()
        with sug_col:
            render_suggestions()
        user_query = st.chat_input("Ask about this document…")
        if user_query:
            handle_user_query(user_query)

    with tab_preview:
        render_document_preview()


if __name__ == "__main__":
    main()
