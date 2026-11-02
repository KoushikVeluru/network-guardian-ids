"""
Network Guardian — Model Training (Step 4).
Trains Random Forest and XGBoost on binary classification.
Selects champion on validation; reports test set once.
"""

import os
import json
import time
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    classification_report
)
import xgboost as xgb

warnings.filterwarnings("ignore", category=UserWarning)


def load_splits():
    """Load pre-split parquet files."""
    train = pd.read_parquet("data/processed/train.parquet")
    val = pd.read_parquet("data/processed/val.parquet")
    test = pd.read_parquet("data/processed/test.parquet")
    
    with open("data/processed/feature_columns.json") as f:
        feature_cols = json.load(f)
    
    label_col = "Label_Binary"
    
    # Separate features present in the saved columns
    # Some feature cols might include Label which we don't want
    feature_cols = [c for c in feature_cols if c != label_col and c != "Label"]
    
    X_train = train[feature_cols].values
    y_train = train[label_col].values
    X_val = val[feature_cols].values
    y_val = val[label_col].values
    X_test = test[feature_cols].values
    y_test = test[label_col].values
    
    print(f"Loaded splits — Train: {X_train.shape}, Val: {X_val.shape}, Test: {X_test.shape}")
    print(f"Features: {len(feature_cols)}")
    print(f"Train class balance: BENIGN={int((y_train==0).sum()):,} ATTACK={int((y_train==1).sum()):,}")
    
    return X_train, X_val, X_test, y_train, y_val, y_test, feature_cols


def evaluate_model(model, X, y, dataset_name=""):
    """Compute all required metrics."""
    t0 = time.time()
    y_pred = model.predict(X)
    inference_time = time.time() - t0
    
    y_prob = model.predict_proba(X)[:, 1]
    
    tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0
    
    metrics = {
        "dataset": dataset_name,
        "accuracy": float(accuracy_score(y, y_pred)),
        "precision": float(precision_score(y, y_pred, zero_division=0)),
        "recall": float(recall_score(y, y_pred, zero_division=0)),
        "f1": float(f1_score(y, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, y_prob)),
        "pr_auc": float(average_precision_score(y, y_prob)),
        "false_positive_rate": float(fpr),
        "false_negative_rate": float(fnr),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "inference_time_seconds": float(inference_time),
        "samples": int(len(y)),
    }
    return metrics, y_pred, y_prob


def print_metrics(metrics, model_name):
    """Pretty-print metrics."""
    print(f"\n{'─' * 50}")
    print(f"  {model_name} — {metrics['dataset']}")
    print(f"{'─' * 50}")
    print(f"  Accuracy:      {metrics['accuracy']:.4f}")
    print(f"  Precision:     {metrics['precision']:.4f}")
    print(f"  Recall:        {metrics['recall']:.4f}")
    print(f"  F1:            {metrics['f1']:.4f}")
    print(f"  ROC-AUC:       {metrics['roc_auc']:.4f}")
    print(f"  PR-AUC:        {metrics['pr_auc']:.4f}")
    print(f"  FPR:           {metrics['false_positive_rate']:.4f}")
    print(f"  FNR:           {metrics['false_negative_rate']:.4f}")
    cm = metrics["confusion_matrix"]
    print(f"  Confusion Matrix:")
    print(f"    TN={cm['tn']:,}  FP={cm['fp']:,}")
    print(f"    FN={cm['fn']:,}  TP={cm['tp']:,}")
    print(f"  Inference: {metrics['inference_time_seconds']:.3f}s for {metrics['samples']:,} samples")


def plot_confusion_matrix(y_true, y_pred, model_name, save_path):
    """Save a confusion matrix plot."""
    cm = confusion_matrix(y_true, y_pred)
    fig, ax = plt.subplots(1, 1, figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(["BENIGN", "ATTACK"])
    ax.set_yticklabels(["BENIGN", "ATTACK"])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(f"{model_name} — Confusion Matrix (Test Set)")
    
    for i in range(2):
        for j in range(2):
            color = "white" if cm[i, j] > cm.max() / 2 else "black"
            ax.text(j, i, f"{cm[i, j]:,}", ha="center", va="center", color=color, fontsize=14)
    
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {save_path}")


def train_random_forest(X_train, y_train, config, seed):
    """Train RF with class_weight=balanced."""
    rf_cfg = config["models"]["random_forest"]
    print(f"\n🌲 Training Random Forest (n_estimators={rf_cfg['n_estimators']}, "
          f"max_depth={rf_cfg['max_depth']}, class_weight={rf_cfg['class_weight']}, "
          f"n_jobs={rf_cfg['n_jobs']})...")
    
    t0 = time.time()
    rf = RandomForestClassifier(
        n_estimators=rf_cfg["n_estimators"],
        max_depth=rf_cfg["max_depth"],
        class_weight=rf_cfg["class_weight"],
        n_jobs=rf_cfg["n_jobs"],
        random_state=seed,
    )
    rf.fit(X_train, y_train)
    train_time = time.time() - t0
    print(f"  Training time: {train_time:.1f}s")
    return rf, train_time


def train_xgboost(X_train, y_train, config, seed):
    """Train XGBoost with scale_pos_weight."""
    xgb_cfg = config["models"]["xgboost"]
    
    # Auto scale_pos_weight: ratio of negative to positive
    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    spw = n_neg / n_pos if n_pos > 0 else 1.0
    
    print(f"\n🚀 Training XGBoost (n_estimators={xgb_cfg['n_estimators']}, "
          f"max_depth={xgb_cfg['max_depth']}, lr={xgb_cfg['learning_rate']}, "
          f"scale_pos_weight={spw:.2f}, n_jobs={xgb_cfg['n_jobs']})...")
    
    t0 = time.time()
    model = xgb.XGBClassifier(
        n_estimators=xgb_cfg["n_estimators"],
        max_depth=xgb_cfg["max_depth"],
        learning_rate=xgb_cfg["learning_rate"],
        scale_pos_weight=spw,
        tree_method=xgb_cfg["tree_method"],
        n_jobs=xgb_cfg["n_jobs"],
        random_state=seed,
        eval_metric="logloss",
        verbosity=0,
    )
    model.fit(X_train, y_train)
    train_time = time.time() - t0
    print(f"  Training time: {train_time:.1f}s")
    return model, train_time


def main():
    with open("configs/config.json") as f:
        config = json.load(f)
    
    seed = config["random_seed"]
    np.random.seed(seed)
    
    os.makedirs("models", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)
    
    # Load splits
    X_train, X_val, X_test, y_train, y_val, y_test, feature_cols = load_splits()
    
    # Scale features — fit on train ONLY
    print("\nFitting StandardScaler on training data only...")
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)
    
    # Save scaler params for reproducibility
    scaler_params = {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
    }
    with open("models/scaler_params.json", "w") as f:
        json.dump(scaler_params, f)
    print("Saved scaler params to models/scaler_params.json")
    
    # ──── Random Forest ────
    rf_model, rf_train_time = train_random_forest(X_train_s, y_train, config, seed)
    
    rf_val_metrics, _, _ = evaluate_model(rf_model, X_val_s, y_val, "Validation")
    rf_val_metrics["train_time_seconds"] = rf_train_time
    print_metrics(rf_val_metrics, "Random Forest")
    
    # ──── XGBoost ────
    xgb_model, xgb_train_time = train_xgboost(X_train_s, y_train, config, seed)
    
    xgb_val_metrics, _, _ = evaluate_model(xgb_model, X_val_s, y_val, "Validation")
    xgb_val_metrics["train_time_seconds"] = xgb_train_time
    print_metrics(xgb_val_metrics, "XGBoost")
    
    # ──── Champion selection on validation ────
    print("\n" + "=" * 60)
    print("CHAMPION SELECTION (based on validation F1 and ROC-AUC)")
    print("=" * 60)
    print(f"  Random Forest — F1: {rf_val_metrics['f1']:.4f}, ROC-AUC: {rf_val_metrics['roc_auc']:.4f}")
    print(f"  XGBoost       — F1: {xgb_val_metrics['f1']:.4f}, ROC-AUC: {xgb_val_metrics['roc_auc']:.4f}")
    
    if xgb_val_metrics["f1"] >= rf_val_metrics["f1"]:
        champion_name = "XGBoost"
        champion_model = xgb_model
        champion_val = xgb_val_metrics
    else:
        champion_name = "Random Forest"
        champion_model = rf_model
        champion_val = rf_val_metrics
    
    print(f"\n  ✅ Champion: {champion_name}")
    
    # ──── Final test set evaluation (ONE TIME) ────
    print("\n" + "=" * 60)
    print(f"FINAL TEST SET EVALUATION — {champion_name}")
    print("=" * 60)
    
    test_metrics, y_test_pred, y_test_prob = evaluate_model(
        champion_model, X_test_s, y_test, "Test"
    )
    print_metrics(test_metrics, champion_name)
    
    # Also evaluate the runner-up on test for comparison
    if champion_name == "XGBoost":
        runner_name = "Random Forest"
        runner_model = rf_model
    else:
        runner_name = "XGBoost"
        runner_model = xgb_model
    
    runner_test_metrics, runner_y_pred, _ = evaluate_model(
        runner_model, X_test_s, y_test, "Test"
    )
    print_metrics(runner_test_metrics, f"{runner_name} (runner-up)")
    
    # ──── Save confusion matrix plots ────
    plot_confusion_matrix(y_test, y_test_pred, champion_name,
                          "models/confusion_matrix_champion.png")
    plot_confusion_matrix(y_test, runner_y_pred, runner_name,
                          "models/confusion_matrix_runner.png")
    
    # ──── Save all metrics ────
    all_metrics = {
        "seed": seed,
        "feature_count": len(feature_cols),
        "train_size": int(len(y_train)),
        "val_size": int(len(y_val)),
        "test_size": int(len(y_test)),
        "champion": champion_name,
        "models": {
            "random_forest": {
                "validation": rf_val_metrics,
                "test": runner_test_metrics if champion_name == "XGBoost" else test_metrics,
                "train_time_seconds": rf_train_time,
            },
            "xgboost": {
                "validation": xgb_val_metrics,
                "test": test_metrics if champion_name == "XGBoost" else runner_test_metrics,
                "train_time_seconds": xgb_train_time,
            }
        }
    }
    
    with open("models/metrics.json", "w") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"\n✅ Saved metrics to models/metrics.json")
    
    # Save models with joblib
    import joblib
    joblib.dump(rf_model, "models/random_forest.joblib")
    joblib.dump(xgb_model, "models/xgboost.joblib")
    joblib.dump(scaler, "models/scaler.joblib")
    print(f"✅ Saved models to models/")
    
    # Save feature columns for SHAP step
    with open("models/feature_columns.json", "w") as f:
        json.dump(feature_cols, f, indent=2)
    
    return champion_name, champion_model, scaler, feature_cols


if __name__ == "__main__":
    main()
