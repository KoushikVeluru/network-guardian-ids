"""Network Guardian live demo core. Run from the project root (~/network-guardian-ids).
Loads the REAL saved scaler + XGBoost model, scores one flow, computes SHAP live,
and builds the alert with your own template_alerts.py code."""
import glob, importlib.util, json, os
import joblib, numpy as np, pandas as pd, shap

def _load_alerts_module():
    hits = glob.glob("src/**/template_alerts.py", recursive=True)
    if not hits:
        raise FileNotFoundError("template_alerts.py not found under src/")
    spec = importlib.util.spec_from_file_location("template_alerts", hits[0])
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

class Guardian:
    def __init__(self):
        self.model = joblib.load("models/xgboost.joblib")
        self.scaler = joblib.load("models/scaler.joblib")
        with open("models/feature_columns.json") as f:
            fc = json.load(f)
        self.cols = [c for c in fc if c not in ("Label", "Label_Binary")]
        self.test = pd.read_parquet("data/processed/test.parquet")
        self.explainer = shap.TreeExplainer(self.model)
        self.alerts = _load_alerts_module()

    def pick(self, kind="any", seed=None):
        y = self.test["Label_Binary"].values
        ids = np.arange(len(y))
        if kind == "benign": ids = ids[y == 0]
        if kind == "attack": ids = ids[y == 1]
        return int(np.random.default_rng(seed).choice(ids))

    def raw_row(self, idx):
        return self.test[self.cols].iloc[idx].astype(float).values

    def detect(self, raw):
        raw = np.asarray(raw, dtype=float).reshape(1, -1)
        xs = self.scaler.transform(raw)
        prob = float(self.model.predict_proba(xs)[0, 1])
        label = "ATTACK" if prob >= 0.5 else "BENIGN"
        sv = self.explainer.shap_values(xs)[0]
        top = np.argsort(np.abs(sv))[::-1][:5]
        feats = [{"feature": self.cols[i], "value": float(raw[0, i]),
                  "shap_value": float(sv[i]),
                  "direction": "attack" if sv[i] > 0 else "benign"} for i in top]
        risk, sev = self.alerts.compute_risk_score(prob)
        text = self.alerts.generate_template_alert(
            {"predicted_label": label, "attack_probability": prob}, feats, risk, sev)
        return dict(label=label, prob=prob, risk=risk, severity=sev, feats=feats,
                    alert=text, shap=sv, xs=xs[0], base=self.explainer.expected_value)
