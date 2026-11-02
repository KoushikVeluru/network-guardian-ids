"""
Unseen benign holdout test — false positive rate on benign flows
never seen during training, validation, or testing.
"""
import os
import json
import time
import gc
import numpy as np
import pandas as pd
import joblib

def main():
    print("=" * 60)
    print("UNSEEN BENIGN HOLDOUT TEST")
    print("=" * 60)

    with open("configs/config.json") as f:
        config = json.load(f)
    seed = config["random_seed"]

    # ── Reload and clean exactly as data_loader.py does ──
    raw_dir = config["data"]["raw_dir"]
    csv_files = sorted(f for f in os.listdir(raw_dir) if f.endswith(".csv"))
    frames = []
    print(f"Loading {len(csv_files)} raw CSVs...")
    for fname in csv_files:
        df = pd.read_csv(os.path.join(raw_dir, fname), low_memory=False)
        df.columns = df.columns.str.strip()
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    del frames
    gc.collect()

    # Same cleaning steps as data_loader.py
    drop_cols = [c for c in config["features"]["drop_columns"] if c in combined.columns]
    combined = combined.drop(columns=drop_cols)
    combined = combined.drop_duplicates()
    numeric_cols = combined.select_dtypes(include=[np.number]).columns
    combined[numeric_cols] = combined[numeric_cols].replace([np.inf, -np.inf], np.nan)
    combined = combined.dropna()
    for col in combined.select_dtypes(include=["float64"]).columns:
        combined[col] = combined[col].astype(np.float32)
    for col in combined.select_dtypes(include=["int64"]).columns:
        combined[col] = combined[col].astype(np.int32)

    # Binary label
    combined["Label_Binary"] = (combined["Label"].str.strip().str.upper() != "BENIGN").astype(np.int32)

    # ── Reproduce the exact sampling ──
    all_benign = combined[combined["Label_Binary"] == 0]
    all_attack = combined[combined["Label_Binary"] == 1]
    n_attack = len(all_attack)
    target_size = config["data"]["sample_size"]
    n_benign_needed = target_size - n_attack

    # Same random state → same 63,508 benign rows selected
    sampled_benign = all_benign.sample(n=n_benign_needed, random_state=seed)
    unseen_benign = all_benign.drop(sampled_benign.index)

    print(f"\nTotal cleaned benign: {len(all_benign):,}")
    print(f"Sampled benign (in train/val/test): {len(sampled_benign):,}")
    print(f"Unseen benign (never in any split): {len(unseen_benign):,}")

    # ── Prepare features ──
    with open("models/feature_columns.json") as f:
        feature_cols = json.load(f)
    feature_cols = [c for c in feature_cols if c not in ("Label_Binary", "Label")]

    X_unseen = unseen_benign[feature_cols].values
    del combined, all_benign, all_attack, sampled_benign, unseen_benign
    gc.collect()

    # ── Scale and predict in memory-safe batches ──
    scaler = joblib.load("models/scaler.joblib")
    model = joblib.load("models/xgboost.joblib")

    batch_size = 250000
    n_total = len(X_unseen)
    n_batches = int(np.ceil(n_total / batch_size))

    print(f"\nRunning inference on {n_total:,} flows in {n_batches} batches...")
    t0 = time.time()
    y_preds = []
    y_probs = []

    for i in range(n_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, n_total)
        batch_X = X_unseen[start_idx:end_idx]
        batch_X_s = scaler.transform(batch_X)
        pred = model.predict(batch_X_s)
        prob = model.predict_proba(batch_X_s)[:, 1]
        y_preds.append(pred)
        y_probs.append(prob)
        print(f"  Batch {i+1}/{n_batches} ({end_idx - start_idx:,} flows) complete")

    inference_time = time.time() - t0
    y_pred = np.concatenate(y_preds)
    y_prob = np.concatenate(y_probs)

    # ── Results ──
    n_fp = int(y_pred.sum())  # all are truly benign, so any 1 is a false positive
    fpr = n_fp / n_total if n_total > 0 else 0

    print(f"\n{'─' * 50}")
    print(f"  RESULTS — Unseen Benign Holdout")
    print(f"{'─' * 50}")
    print(f"  Total unseen benign flows: {n_total:,}")
    print(f"  False positives: {n_fp:,}")
    print(f"  False positive rate: {fpr:.6f} ({fpr*100:.4f}%)")
    print(f"  Mean attack probability: {float(y_prob.mean()):.6f}")
    print(f"  Max attack probability: {float(y_prob.max()):.6f}")
    print(f"  Total inference time: {inference_time:.3f}s ({n_total/inference_time:,.0f} flows/sec)")

    # ── Save to metrics.json ──
    with open("models/metrics.json") as f:
        metrics = json.load(f)

    metrics["unseen_benign_holdout"] = {
        "champion_model": "XGBoost",
        "total_unseen_benign": n_total,
        "false_positives": n_fp,
        "false_positive_rate": float(fpr),
        "mean_attack_probability": float(y_prob.mean()),
        "max_attack_probability": float(y_prob.max()),
        "inference_time_seconds": float(inference_time),
        "throughput_flows_per_sec": float(n_total / inference_time),
        "note": "These flows were never seen during training, validation, or test sampling. Evaluated using the saved StandardScaler fit on training data only."
    }

    with open("models/metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n✅ Updated models/metrics.json")

    return n_total, n_fp, fpr

if __name__ == "__main__":
    main()
