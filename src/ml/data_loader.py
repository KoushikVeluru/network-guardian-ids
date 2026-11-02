"""
Network Guardian — Data loading and inspection (Step 2).
Loads CIC-IDS2017 CSVs file by file with memory-safe practices.
"""

import os
import json
import time
import pandas as pd
import numpy as np

def load_config():
    with open("configs/config.json") as f:
        return json.load(f)

def load_and_inspect(config):
    """Load all CSVs, strip whitespace from column names, report stats per file."""
    raw_dir = config["data"]["raw_dir"]
    csv_files = sorted([f for f in os.listdir(raw_dir) if f.endswith(".csv")])
    
    print(f"Found {len(csv_files)} CSV files in {raw_dir}/\n")
    print("=" * 80)
    
    frames = []
    for fname in csv_files:
        path = os.path.join(raw_dir, fname)
        df = pd.read_csv(path, low_memory=False)
        
        # Strip whitespace from column names
        df.columns = df.columns.str.strip()
        
        # Label distribution for this file
        label_counts = df["Label"].value_counts()
        
        print(f"\n📄 {fname}")
        print(f"   Shape: {df.shape}")
        print(f"   Memory: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
        print(f"   Labels:")
        for label, count in label_counts.items():
            print(f"     {label}: {count:,}")
        
        frames.append(df)
    
    # Combine
    print("\n" + "=" * 80)
    print("Combining all files...")
    combined = pd.concat(frames, ignore_index=True)
    del frames  # free memory
    
    print(f"\n📊 COMBINED DATASET")
    print(f"   Shape: {combined.shape}")
    print(f"   Memory: {combined.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    print(f"\n   Columns ({len(combined.columns)}):")
    for i, col in enumerate(combined.columns):
        print(f"     {i:2d}. '{col}' — {combined[col].dtype}")
    
    print(f"\n   Label distribution (all files):")
    label_counts = combined["Label"].value_counts()
    for label, count in label_counts.items():
        pct = 100 * count / len(combined)
        print(f"     {label}: {count:,} ({pct:.2f}%)")
    
    # NaN and Inf
    nan_counts = combined.isnull().sum()
    nan_cols = nan_counts[nan_counts > 0]
    print(f"\n   Columns with NaN values: {len(nan_cols)}")
    for col, count in nan_cols.items():
        print(f"     {col}: {count:,} NaN")
    
    # Check for inf in numeric columns
    numeric_cols = combined.select_dtypes(include=[np.number]).columns
    inf_mask = np.isinf(combined[numeric_cols].values)
    inf_count = inf_mask.sum()
    print(f"\n   Total Inf values in numeric columns: {inf_count:,}")
    if inf_count > 0:
        for col in numeric_cols:
            col_inf = np.isinf(combined[col].values).sum()
            if col_inf > 0:
                print(f"     {col}: {col_inf:,} Inf")
    
    # Duplicates
    print(f"\n   Checking duplicates...")
    dup_count = combined.duplicated().sum()
    print(f"   Duplicate rows: {dup_count:,}")
    
    return combined


def clean_data(df, config):
    """Clean: handle NaN/Inf, remove duplicates, drop identifiers, downcast."""
    print("\n" + "=" * 80)
    print("CLEANING DATA")
    print("=" * 80)
    
    label_col = config["features"]["label_column"]
    drop_cols = config["features"]["drop_columns"]
    
    rows_before = len(df)
    
    # 1. Drop identifier columns (only those that exist)
    existing_drop = [c for c in drop_cols if c in df.columns]
    missing_drop = [c for c in drop_cols if c not in df.columns]
    df = df.drop(columns=existing_drop)
    print(f"\n1. Dropped identifier columns: {existing_drop}")
    if missing_drop:
        print(f"   (Not found, skipped: {missing_drop})")
    
    # 2. Handle duplicates
    df = df.drop_duplicates()
    rows_after_dedup = len(df)
    print(f"\n2. Removed {rows_before - rows_after_dedup:,} duplicate rows ({rows_before:,} → {rows_after_dedup:,})")
    
    # 3. Replace Inf with NaN, then drop rows with NaN
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    inf_before = np.isinf(df[numeric_cols].values).sum()
    df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)
    
    nan_rows = df.isnull().any(axis=1).sum()
    df = df.dropna()
    rows_after_clean = len(df)
    print(f"\n3. Replaced {inf_before:,} Inf values with NaN")
    print(f"   Dropped {nan_rows:,} rows with NaN ({rows_after_dedup:,} → {rows_after_clean:,})")
    
    # 4. Downcast numeric to float32/int32
    for col in df.select_dtypes(include=["float64"]).columns:
        df[col] = df[col].astype(np.float32)
    for col in df.select_dtypes(include=["int64"]).columns:
        df[col] = df[col].astype(np.int32)
    
    mem_after = df.memory_usage(deep=True).sum() / 1024**2
    print(f"\n4. Downcast to float32/int32. Memory: {mem_after:.1f} MB")
    
    # 5. Binary label
    print(f"\n5. Creating binary label (BENIGN=0, ATTACK=1)")
    attack_label_map = {}
    for label in df[label_col].unique():
        is_benign = label.strip().upper() == "BENIGN"
        attack_label_map[label] = 0 if is_benign else 1
        print(f"     '{label}' → {'BENIGN (0)' if is_benign else 'ATTACK (1)'}")
    
    df["Label_Binary"] = df[label_col].map(attack_label_map).astype(np.int32)
    
    print(f"\n   Binary distribution:")
    for val, name in [(0, "BENIGN"), (1, "ATTACK")]:
        count = (df["Label_Binary"] == val).sum()
        pct = 100 * count / len(df)
        print(f"     {name} ({val}): {count:,} ({pct:.2f}%)")
    
    print(f"\n   Final shape: {df.shape}")
    print(f"   Final memory: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    
    return df


def stratified_sample(df, config):
    """Take a stratified sample keeping all rare attack rows."""
    from sklearn.model_selection import train_test_split
    
    print("\n" + "=" * 80)
    print("STRATIFIED SAMPLING & SPLITTING")
    print("=" * 80)
    
    seed = config["random_seed"]
    target_size = config["data"]["sample_size"]
    label_col = "Label_Binary"
    
    n_total = len(df)
    print(f"\nTotal rows after cleaning: {n_total:,}")
    print(f"Target sample size: ~{target_size:,}")
    
    if n_total <= target_size:
        print("Dataset fits within target size, using all rows.")
        sample = df
    else:
        # Keep all attack rows, sample benign
        attacks = df[df[label_col] == 1]
        benign = df[df[label_col] == 0]
        n_attack = len(attacks)
        n_benign_needed = target_size - n_attack
        
        if n_benign_needed > 0 and n_benign_needed < len(benign):
            benign_sample = benign.sample(n=n_benign_needed, random_state=seed)
            sample = pd.concat([benign_sample, attacks], ignore_index=True)
            print(f"Kept all {n_attack:,} attack rows")
            print(f"Sampled {n_benign_needed:,} of {len(benign):,} benign rows")
        else:
            sample = df
            print("Using all rows (attacks exceed target or target >= total)")
    
    print(f"Sample size: {len(sample):,}")
    
    # Split: train/val/test — stratified, BEFORE fitting anything
    test_size = config["data"]["test_size"]
    val_size = config["data"]["val_size"]
    
    # Features and labels
    original_label = "Label"
    feature_cols = [c for c in sample.columns if c not in [original_label, label_col]]
    X = sample[feature_cols]
    y = sample[label_col]
    
    # First split: train+val vs test
    X_trainval, X_test, y_trainval, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )
    
    # Second split: train vs val
    val_fraction = val_size / (1 - test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_trainval, y_trainval, test_size=val_fraction, random_state=seed, stratify=y_trainval
    )
    
    print(f"\nSplit (seed={seed}):")
    print(f"  Train: {len(X_train):,} rows ({100*len(X_train)/len(sample):.1f}%)")
    print(f"    BENIGN: {(y_train==0).sum():,}  ATTACK: {(y_train==1).sum():,}")
    print(f"  Val:   {len(X_val):,} rows ({100*len(X_val)/len(sample):.1f}%)")
    print(f"    BENIGN: {(y_val==0).sum():,}  ATTACK: {(y_val==1).sum():,}")
    print(f"  Test:  {len(X_test):,} rows ({100*len(X_test)/len(sample):.1f}%)")
    print(f"    BENIGN: {(y_test==0).sum():,}  ATTACK: {(y_test==1).sum():,}")
    
    # Limitation note
    print(f"\n⚠️  SPLIT LIMITATIONS (honest disclosure):")
    print(f"  - This is a random stratified split, not a temporal split.")
    print(f"  - CIC-IDS2017 was collected over 5 days; flows from the same")
    print(f"    attack session can land in both train and test, inflating metrics.")
    print(f"  - A stricter split (hold out entire days or attack types) is planned")
    print(f"    for Phase 6 but not done here due to time constraints.")
    print(f"  - Benign class was downsampled; original class ratio not preserved.")
    
    return X_train, X_val, X_test, y_train, y_val, y_test, feature_cols


if __name__ == "__main__":
    config = load_config()
    
    print("STEP 2: Load and Inspect CIC-IDS2017")
    print("=" * 80)
    combined = load_and_inspect(config)
    
    print("\n\nSTEP 3a: Clean Data")
    cleaned = clean_data(combined, config)
    del combined  # free memory
    
    print("\n\nSTEP 3b: Sample and Split")
    X_train, X_val, X_test, y_train, y_val, y_test, feature_cols = stratified_sample(cleaned, config)
    
    # Save processed splits as parquet
    os.makedirs("data/processed", exist_ok=True)
    
    train_df = X_train.copy()
    train_df["Label_Binary"] = y_train.values
    train_df.to_parquet("data/processed/train.parquet", index=False)
    
    val_df = X_val.copy()
    val_df["Label_Binary"] = y_val.values
    val_df.to_parquet("data/processed/val.parquet", index=False)
    
    test_df = X_test.copy()
    test_df["Label_Binary"] = y_test.values
    test_df.to_parquet("data/processed/test.parquet", index=False)
    
    # Save feature list
    with open("data/processed/feature_columns.json", "w") as f:
        json.dump(feature_cols, f, indent=2)
    
    print(f"\n✅ Saved splits to data/processed/ (train.parquet, val.parquet, test.parquet)")
    print(f"✅ Saved feature list to data/processed/feature_columns.json")
    print(f"   Features: {len(feature_cols)}")
