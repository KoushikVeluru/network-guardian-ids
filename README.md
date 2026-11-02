# Network Guardian

**AI-Powered Intrusion Detection System with Plain-English Security Alerts**

A network intrusion detection platform that detects malicious traffic using machine learning, explains each detection with SHAP, computes risk scores, and communicates incidents as plain-English alerts.

---

## Quick Start

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Create venv with Python 3.11
uv python install 3.11
uv venv --python 3.11 .venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Run the full pipeline (requires CIC-IDS2017 CSVs in data/raw/cic-ids2017/MachineLearningCVE/)
python src/ml/data_loader.py      # Step 1: Load, clean, split
python src/ml/train.py            # Step 2: Train RF + XGBoost
python src/explain/shap_explain.py  # Step 3: SHAP explanations
python src/nlp/template_alerts.py   # Step 4: Generate alerts
```

---

## Results (Real, Measured)

**Dataset:** CIC-IDS2017 (8 CSV files, 2,830,743 rows, 79 columns)  
**After cleaning:** 2,233,164 rows (removed 596,780 duplicates, 799 NaN/Inf rows)  
**Binary task:** BENIGN vs ATTACK (15 attack types merged)  
**Stratified sample:** 400,000 rows (all 336,492 attack + 63,508 benign)  
**Split:** 70% train (280K) / 15% validation (60K) / 15% test (60K)  
**Seed:** 42

### Model Comparison (Test Set — reported once)

| Metric | Random Forest | XGBoost (Champion) |
|--------|--------------|-------------------|
| Accuracy | 0.9976 | **0.9990** |
| Precision | 0.9996 | **0.9998** |
| Recall | 0.9976 | **0.9990** |
| F1 | 0.9986 | **0.9994** |
| ROC-AUC | 0.9999 | **1.0000** |
| PR-AUC | 1.0000 | **1.0000** |
| False Positive Rate | 0.0022 | **0.0013** |
| False Negative Rate | 0.0024 | **0.0010** |
| Training Time | 22.9s | **5.5s** |
| Inference (60K flows) | 0.163s | **0.053s** |

**Champion selection:** XGBoost chosen on validation F1 (0.9993 vs 0.9985) and ROC-AUC.

### Top 10 Features (SHAP Global Importance)

| Rank | Feature | Mean |SHAP| |
|------|---------|------|
| 1 | Bwd Packet Length Std | 4.6131 |
| 2 | Init_Win_bytes_backward | 2.1262 |
| 3 | Bwd Packet Length Mean | 0.8139 |
| 4 | Fwd Packet Length Max | 0.7964 |
| 5 | Init_Win_bytes_forward | 0.7943 |
| 6 | Average Packet Size | 0.5777 |
| 7 | Idle Min | 0.4198 |
| 8 | Total Fwd Packets | 0.2928 |
| 9 | Fwd Header Length | 0.2455 |
| 10 | Total Length of Fwd Packets | 0.2367 |

---

## Honest Limitations

1. **Split leakage risk:** The train/test split is random-stratified, not temporal. Flows from the same attack session can appear in both train and test, inflating metrics. A temporal or per-day split would produce lower, more realistic numbers.
2. **Sampling bias:** All attack flows were kept while benign flows were downsampled to 400K total. The original class ratio (85% benign / 15% attack) is not preserved in the sample.
3. **Binary only:** This version uses binary classification (BENIGN vs ATTACK). Multiclass detection is planned.
4. **CIC-IDS2017 dataset issues:** The dataset has known issues including duplicate flows, CICFlowMeter artifacts, and some label inconsistencies documented in published research.
5. **No Zeek integration yet:** Features are CICFlowMeter-generated. A feature compatibility table mapping CIC features to Zeek-reproducible features is planned for Phase 2.
6. **CPU only:** Training was done on CPU. GPU training is planned for deep learning phases.
7. **No live traffic:** This version processes static CSV files. Zeek-based live/PCAP monitoring is planned for Phase 8.

---

## Architecture

```
CIC-IDS2017 CSVs → data_loader.py (clean, sample, split)
                  → train.py (RF, XGBoost, scaler — fit on train only)
                  → shap_explain.py (TreeExplainer, global + per-flow)
                  → template_alerts.py (risk score + plain-English alert)
```

**Pipeline integrity:**
- Scaler fit on training data only, applied to val/test
- Class imbalance handled via `class_weight=balanced` (RF) and `scale_pos_weight` (XGBoost)
- Fixed seed (42) for reproducibility
- All metrics from real runs, no fabricated numbers

---

## Project Structure

```
network-guardian-ids/
├── configs/config.json          # Central configuration
├── data/
│   ├── raw/cic-ids2017/         # Raw CSVs (not committed)
│   └── processed/               # Parquet splits (not committed)
├── models/                      # Trained models, metrics, plots (not committed)
├── src/
│   ├── ml/
│   │   ├── data_loader.py       # Data loading, cleaning, splitting
│   │   └── train.py             # RF + XGBoost training
│   ├── explain/
│   │   └── shap_explain.py      # SHAP global + per-flow
│   ├── nlp/
│   │   └── template_alerts.py   # Template-based alert generation
│   ├── dl/                      # Planned: MLP, Autoencoder
│   ├── mlops/                   # Planned: MLflow, drift monitoring
│   └── network/                 # Planned: Zeek integration
├── api/                         # Planned: FastAPI backend
├── dashboard/                   # Planned: React frontend
├── db/                          # Planned: PostgreSQL schema
├── tests/                       # Planned: pytest suite
├── docker/                      # Planned: Dockerfiles
├── docs/
│   └── MASTER_PROMPT.md         # Full project specification
├── .gitignore
├── .env.example
└── requirements.txt             # Pinned dependencies
```

---

## Done / Planned

| Component | Status | Notes |
|-----------|--------|-------|
| Data loading & cleaning | ✅ Done | Memory-safe, file-by-file, float32, Parquet |
| EDA & data quality report | ✅ Done | Label counts, NaN/Inf, duplicates |
| Binary classification (RF, XGBoost) | ✅ Done | Real metrics, champion selected |
| SHAP explainability | ✅ Done | Global top-10, 3 per-flow explanations |
| Risk scoring & severity | ✅ Done | Documented formula, 0-100 scale |
| Template-based alerts | ✅ Done | Plain-English, no LLM |
| Multiclass classification | 📋 Planned | |
| MLP (deep learning) | 📋 Planned | PyTorch, CUDA |
| Autoencoder (anomaly detection) | 📋 Planned | Benign-only training |
| UNSW-NB15 generalization test | 📋 Planned | Held-out dataset |
| Zeek integration | 📋 Planned | PCAP replay, live capture |
| Feature compatibility table | 📋 Planned | CICFlowMeter ↔ Zeek mapping |
| FastAPI backend | 📋 Planned | JWT, roles, endpoints |
| PostgreSQL database | 📋 Planned | Schema, migrations |
| React dashboard | 📋 Planned | SOC-style UI |
| RAG alert generation | 📋 Planned | Knowledge base + retrieval |
| Security assistant chatbot | 📋 Planned | Intent classification |
| MLflow tracking | 📋 Planned | Experiment tracking, registry |
| Docker Compose | 📋 Planned | Full stack deployment |
| Drift monitoring (PSI/KS) | 📋 Planned | Feature distribution monitoring |
| GitHub Actions CI | 📋 Planned | Automated testing |

---

## Environment

- **Python:** 3.11.18 (via uv)
- **OS:** Ubuntu 26.04 on WSL2
- **CPU:** Intel i7-13650HX (12 threads visible to WSL)
- **RAM:** 9.7 GiB (WSL limit)
- **GPU:** RTX 4060 8GB (available, not used in this phase)
- **Key packages:** scikit-learn 1.9.1, xgboost 3.2.0, shap 0.51.0, pandas 3.1.0, pyarrow 26.0.0

---

## Team

KoushiK Veluru

D Sri Charan Teja

Rahul.U

## License

Academic project.
