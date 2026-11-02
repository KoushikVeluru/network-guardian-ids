"""
Network Guardian — Template-based Plain-English Alert (Step 6).
Generates a human-readable security alert from a real prediction + real SHAP features.
No LLM involved.
"""

import json
import numpy as np
import pandas as pd
import joblib


# ──── Risk scoring (simplified version of the documented formula) ────
ATTACK_SEVERITY_WEIGHTS = {
    # Higher weight = higher inherent severity
    "DDoS": 0.9,
    "DoS Hulk": 0.85,
    "DoS GoldenEye": 0.85,
    "DoS slowloris": 0.8,
    "DoS Slowhttptest": 0.8,
    "Heartbleed": 1.0,
    "PortScan": 0.5,
    "FTP-Patator": 0.7,
    "SSH-Patator": 0.7,
    "Bot": 0.8,
    "Web Attack": 0.75,
    "Infiltration": 0.9,
    "UNKNOWN_ATTACK": 0.6,
}

def compute_risk_score(confidence, attack_type="UNKNOWN_ATTACK"):
    """
    Risk score: 0-100.
    Formula: risk = 100 * confidence * attack_severity_weight
    Severity thresholds: LOW <25, MEDIUM 25-50, HIGH 50-75, CRITICAL >=75
    
    This is a project-defined risk score, not statistically calibrated.
    """
    # Find best matching weight
    weight = ATTACK_SEVERITY_WEIGHTS.get(attack_type, 0.6)
    for key in ATTACK_SEVERITY_WEIGHTS:
        if key.lower() in attack_type.lower():
            weight = ATTACK_SEVERITY_WEIGHTS[key]
            break
    
    risk = 100 * confidence * weight
    risk = min(100.0, max(0.0, risk))
    
    if risk >= 75:
        severity = "CRITICAL"
    elif risk >= 50:
        severity = "HIGH"
    elif risk >= 25:
        severity = "MEDIUM"
    else:
        severity = "LOW"
    
    return round(risk, 1), severity


def generate_template_alert(prediction, shap_features, risk_score, severity):
    """
    Generate a plain-English alert from structured data.
    No LLM. Template only.
    """
    pred_label = prediction["predicted_label"]
    confidence = prediction["attack_probability"]
    
    if pred_label == "BENIGN":
        return (
            f"✅ BENIGN TRAFFIC (Confidence: {1 - confidence:.1%})\n"
            f"Risk Score: {risk_score}/100 ({severity})\n\n"
            f"This network flow appears to be normal traffic. "
            f"No malicious indicators detected."
        )
    
    # Build feature explanation lines
    feature_lines = []
    for feat in shap_features[:5]:
        direction = "increased" if feat["direction"] == "attack" else "decreased"
        feature_lines.append(
            f"  • {feat['feature']}: {feat['value']:.4g} "
            f"({direction} attack likelihood, SHAP: {feat['shap_value']:+.4f})"
        )
    
    feature_text = "\n".join(feature_lines)
    
    alert = (
        f"🚨 SECURITY ALERT — {severity} SEVERITY\n"
        f"{'═' * 50}\n"
        f"\n"
        f"Detection: MALICIOUS TRAFFIC DETECTED\n"
        f"Confidence: {confidence:.1%}\n"
        f"Risk Score: {risk_score}/100\n"
        f"Severity: {severity}\n"
        f"\n"
        f"Summary:\n"
        f"  Network Guardian's XGBoost model detected potentially\n"
        f"  malicious activity in this network flow with {confidence:.1%}\n"
        f"  confidence. The risk score of {risk_score}/100 classifies\n"
        f"  this as {severity} severity.\n"
        f"\n"
        f"Key Indicators (from SHAP analysis):\n"
        f"{feature_text}\n"
        f"\n"
        f"Recommended Actions:\n"
        f"  1. Review the source and destination of this flow.\n"
        f"  2. Check for other alerts from the same source IP.\n"
        f"  3. If confirmed malicious, block the source at the firewall.\n"
        f"  4. Document the incident for forensic analysis.\n"
        f"\n"
        f"Note: This alert was generated using template-based\n"
        f"explanation. The detection was made by the ML model;\n"
        f"the explanation is based on real SHAP feature attributions.\n"
        f"No LLM was used in generating this alert.\n"
    )
    return alert


def main():
    print("=" * 60)
    print("STEP 6: TEMPLATE-BASED PLAIN-ENGLISH ALERT")
    print("=" * 60)
    
    # Load the SHAP flow explanations from Step 5
    with open("models/shap_flow_explanations.json") as f:
        flow_explanations = json.load(f)
    
    # Generate alerts for each explained flow
    alerts = []
    for i, flow in enumerate(flow_explanations):
        risk_score, severity = compute_risk_score(
            flow["attack_probability"],
            flow.get("attack_type", "UNKNOWN_ATTACK")
        )
        
        alert_text = generate_template_alert(
            flow, flow["top_features"], risk_score, severity
        )
        
        print(f"\n{'━' * 60}")
        print(f"ALERT FOR FLOW {i + 1} (True: {flow['true_label']})")
        print(f"{'━' * 60}")
        print(alert_text)
        
        alerts.append({
            "flow_index": flow["flow_index"],
            "true_label": flow["true_label"],
            "predicted_label": flow["predicted_label"],
            "confidence": flow["attack_probability"],
            "risk_score": risk_score,
            "severity": severity,
            "alert_text": alert_text,
            "shap_features": flow["top_features"],
        })
    
    # Save alerts
    with open("models/template_alerts.json", "w") as f:
        json.dump(alerts, f, indent=2)
    print(f"\n✅ Saved {len(alerts)} alerts to models/template_alerts.json")
    
    return alerts


if __name__ == "__main__":
    main()
