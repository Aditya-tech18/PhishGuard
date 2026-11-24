"""Static presentation styling. No user text enters CSS or HTML."""

STYLE = """
<style>
.block-container { max-width: 1260px; padding-top: 2.4rem; padding-bottom: 3rem; }
h1 { letter-spacing: -0.045em; font-weight: 760; }
h2, h3 { letter-spacing: -0.025em; }
[data-testid="stMetric"] { background: rgba(41, 73, 104, .23); border: 1px solid rgba(131, 167, 196, .2); border-radius: 12px; padding: 18px 20px; }
[data-testid="stMetricLabel"] { font-size: .82rem; letter-spacing: .01em; }
[data-testid="stMetricValue"] { font-weight: 700; }
[data-testid="stForm"] { border-radius: 14px; border-color: rgba(131, 167, 196, .28); }
[data-testid="stSidebar"] { border-right: 1px solid rgba(131, 167, 196, .16); }
[data-testid="stSidebar"] h1 { font-size: 1.4rem; }
.stButton button, .stFormSubmitButton button { min-height: 42px; border-radius: 8px; }
[data-testid="stCaptionContainer"] { line-height: 1.55; }
</style>
"""


def apply(st):
    st.markdown(STYLE, unsafe_allow_html=True)
