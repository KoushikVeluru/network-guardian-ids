"""Web demo.  Run (from ~/network-guardian-ids):  streamlit run demo_app.py"""
import pandas as pd, streamlit as st, shap, matplotlib.pyplot as plt
from demo_core import Guardian

st.set_page_config(page_title="Network Guardian demo", page_icon="🛡️", layout="wide")
st.title("🛡️ Network Guardian: live detection demo")
st.caption("Runs the real saved XGBoost model and SHAP on the input below. Not live network traffic.")

@st.cache_resource
def load(): return Guardian()
g = load()
s = st.session_state
s.setdefault("idx", g.pick("attack", 1))

c1, c2, c3, c4 = st.columns(4)
if c1.button("🎲 Random benign flow"): s.idx = g.pick("benign")
if c2.button("🎲 Random attack flow"): s.idx = g.pick("attack")
s.idx = int(c3.number_input("Test flow #", 0, len(g.test) - 1, s.idx))
idx = s.idx
st.subheader(f"Input: test flow #{idx} (77 features, editable)")
st.caption("Change any value, then press Detect, to see how the model reacts.")
df = pd.DataFrame({"feature": g.cols, "value": g.raw_row(idx)})
edited = st.data_editor(df, height=280, disabled=["feature"], key=f"ed{idx}")

if st.button("🔍 Detect", type="primary"):
    r = g.detect(edited["value"].values)
    truth = "ATTACK" if g.test["Label_Binary"].iloc[idx] == 1 else "BENIGN"
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Verdict", r["label"]); m2.metric("Attack probability", f"{r['prob']:.4%}")
    m3.metric("Risk score", f"{r['risk']}/100 ({r['severity']})"); m4.metric("Dataset label", truth)
    a, b = st.columns(2)
    a.subheader("Why (SHAP)")
    fig = plt.figure(figsize=(7, 4.5))
    shap.plots.waterfall(shap.Explanation(values=r["shap"], base_values=g.explainer.expected_value,
        data=r["xs"], feature_names=g.cols), max_display=10, show=False)
    a.pyplot(fig, clear_figure=True)
    b.subheader("Alert"); b.code(r["alert"], language=None)
