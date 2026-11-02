"""
Network Guardian — SHAP Explainability (Step 5).
Global top-10 features + explanations for 3 real flows.
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shap


def main():
    print("=" * 60)
    print("STEP 5: SHAP EXPLAINABILITY")
    print("=" * 60)
    
    with open("configs/config.json") as f:
        config = json.load(f)
    
    seed = config["random_seed"]
    shap_cfg = config["shap"]
    
    # Load model, scaler, features, test data
    xgb_model = joblib.load("models/xgboost.joblib")
    scaler = joblib.load("models/scaler.joblib")
    
    with open("models/feature_columns.json") as f:
        feature_cols = json.load(f)
    
    test_df = pd.read_parquet("data/processed/test.parquet")
    label_col = "Label_Binary"
    feature_cols_clean = [c for c in feature_cols if c != label_col and c != "Label"]
    
    X_test = test_df[feature_cols_clean].values
    y_test = test_df[label_col].values
    X_test_s = scaler.transform(X_test)
    
    # ──── Global SHAP importance on a subsample ────
    subsample_size = shap_cfg["subsample_size"]
    np.random.seed(seed)
    idx = np.random.choice(len(X_test_s), size=min(subsample_size, len(X_test_s)), replace=False)
    X_shap = X_test_s[idx]
    
    print(f"\nComputing SHAP values on {len(X_shap)} samples (TreeExplainer)...")
    explainer = shap.TreeExplainer(xgb_model)
    shap_values = explainer.shap_values(X_shap)
    
    # Global importance: mean absolute SHAP value per feature
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    top_k = shap_cfg["top_features"]
    top_idx = np.argsort(mean_abs_shap)[::-1][:top_k]
    
    print(f"\n🔝 Top {top_k} Features by Mean |SHAP|:")
    top_features = []
    for rank, i in enumerate(top_idx, 1):
        print(f"  {rank:2d}. {feature_cols_clean[i]:<35s} — mean|SHAP|={mean_abs_shap[i]:.4f}")
        top_features.append({
            "rank": rank,
            "feature": feature_cols_clean[i],
            "mean_abs_shap": float(mean_abs_shap[i])
        })
    
    # Save global importance
    os.makedirs("models", exist_ok=True)
    with open("models/shap_global_importance.json", "w") as f:
        json.dump(top_features, f, indent=2)
    print(f"\nSaved: models/shap_global_importance.json")
    
    # ──── Global SHAP bar plot ────
    fig, ax = plt.subplots(figsize=(10, 6))
    feature_names_top = [feature_cols_clean[i] for i in top_idx]
    shap_vals_top = [mean_abs_shap[i] for i in top_idx]
    
    bars = ax.barh(range(top_k), shap_vals_top[::-1], color="#2196F3")
    ax.set_yticks(range(top_k))
    ax.set_yticklabels(feature_names_top[::-1], fontsize=10)
    ax.set_xlabel("Mean |SHAP Value|", fontsize=12)
    ax.set_title("Network Guardian — Top 10 Features (XGBoost, Binary Classification)", fontsize=13)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig("models/shap_global_top10.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: models/shap_global_top10.png")
    
    # ──── SHAP summary (beeswarm) plot ────
    fig2 = plt.figure(figsize=(10, 7))
    shap.summary_plot(
        shap_values, X_shap,
        feature_names=feature_cols_clean,
        max_display=top_k,
        show=False
    )
    plt.title("SHAP Summary — Top 10 Features", fontsize=13)
    plt.tight_layout()
    plt.savefig("models/shap_summary_beeswarm.png", dpi=150, bbox_inches="tight")
    plt.close("all")
    print(f"Saved: models/shap_summary_beeswarm.png")
    
    # ──── Per-flow explanations: 1 benign, 2 attack ────
    print(f"\n{'=' * 60}")
    print("PER-FLOW SHAP EXPLANATIONS (3 real flows)")
    print(f"{'=' * 60}")
    
    y_pred = xgb_model.predict(X_test_s)
    y_prob = xgb_model.predict_proba(X_test_s)[:, 1]
    
    # Find: 1 correctly classified benign, 2 correctly classified attacks
    correct_benign = np.where((y_test == 0) & (y_pred == 0))[0]
    correct_attack = np.where((y_test == 1) & (y_pred == 1))[0]
    
    np.random.seed(seed)
    sample_indices = []
    sample_labels = []
    
    if len(correct_benign) > 0:
        sample_indices.append(correct_benign[np.random.randint(len(correct_benign))])
        sample_labels.append("BENIGN")
    if len(correct_attack) >= 2:
        chosen = np.random.choice(correct_attack, size=2, replace=False)
        sample_indices.extend(chosen)
        sample_labels.extend(["ATTACK", "ATTACK"])
    
    flow_explanations = []
    for idx_i, (flow_idx, label) in enumerate(zip(sample_indices, sample_labels)):
        flow_features = X_test_s[flow_idx:flow_idx+1]
        flow_shap = explainer.shap_values(flow_features)[0]
        flow_prob = float(y_prob[flow_idx])
        
        # Top 5 contributing features for this flow
        abs_shap = np.abs(flow_shap)
        top5_idx = np.argsort(abs_shap)[::-1][:5]
        
        print(f"\n  Flow {idx_i + 1} — True: {label}, Predicted: {'ATTACK' if y_pred[flow_idx] else 'BENIGN'}, "
              f"Confidence: {flow_prob:.4f}")
        print(f"  Top 5 contributing features:")
        
        flow_top_features = []
        for rank, fi in enumerate(top5_idx, 1):
            raw_val = float(X_test[flow_idx, fi])
            shap_val = float(flow_shap[fi])
            direction = "↑ ATTACK" if shap_val > 0 else "↓ BENIGN"
            print(f"    {rank}. {feature_cols_clean[fi]:<30s} value={raw_val:.4f}  SHAP={shap_val:+.4f} ({direction})")
            flow_top_features.append({
                "feature": feature_cols_clean[fi],
                "value": raw_val,
                "shap_value": shap_val,
                "direction": "attack" if shap_val > 0 else "benign"
            })
        
        flow_explanations.append({
            "flow_index": int(flow_idx),
            "true_label": label,
            "predicted_label": "ATTACK" if y_pred[flow_idx] else "BENIGN",
            "attack_probability": flow_prob,
            "top_features": flow_top_features
        })
        
        # Individual waterfall plot
        fig3 = plt.figure(figsize=(10, 5))
        shap.plots.waterfall(
            shap.Explanation(
                values=flow_shap,
                base_values=explainer.expected_value,
                data=X_test_s[flow_idx],
                feature_names=feature_cols_clean
            ),
            max_display=10,
            show=False
        )
        plt.title(f"Flow {idx_i+1} — {label} (conf={flow_prob:.3f})", fontsize=12)
        plt.tight_layout()
        plt.savefig(f"models/shap_flow_{idx_i+1}_{label.lower()}.png", dpi=150, bbox_inches="tight")
        plt.close("all")
        print(f"  Saved: models/shap_flow_{idx_i+1}_{label.lower()}.png")
    
    # Save flow explanations
    with open("models/shap_flow_explanations.json", "w") as f:
        json.dump(flow_explanations, f, indent=2)
    print(f"\nSaved: models/shap_flow_explanations.json")
    
    print(f"\n✅ SHAP analysis complete.")
    
    return top_features, flow_explanations


if __name__ == "__main__":
    main()
