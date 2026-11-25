import json

with open('backend/app/ml/artifacts/phase3_results.json') as f:
    d = json.load(f)

print('=== DATASET & SPLITS ===')
meta = d['metadata']
print(f"Total samples: {meta['total_samples']}, Unique cells: {meta['unique_cells']}")
print(f"Train dates: {meta['train_dates']}")
print(f"Val dates:   {meta['val_dates']}")
print(f"Test dates:  {meta['test_dates']}")

for th, v in d['threshold_evaluations'].items():
    print(f"\n==========================================")
    print(f" CANDIDATE THRESHOLD: {th} ({v['threshold_hours']} hours)")
    print(f"==========================================")
    sc = v['sample_counts']
    print(f"Train: {sc['train_pos']}/{sc['train_total']} ({sc['train_prevalence']*100:.2f}%)")
    print(f"Val:   {sc['val_pos']}/{sc['val_total']} ({sc['val_prevalence']*100:.2f}%)")
    print(f"Test:  {sc['test_pos']}/{sc['test_total']} ({sc['test_prevalence']*100:.2f}%)")
    
    print("\n--- VALIDATION SET ---")
    print(f"{'Model/Baseline':28s} | {'F1':6s} | {'PR-AUC':6s} | {'ROC':6s} | {'Prec':6s} | {'Rec':6s}")
    print("-" * 65)
    for b_name, b_val in v['baselines'].items():
        val = b_val['val']
        print(f"{'[Base] '+b_name:28s} | {val['f1']:.4f} | {val['pr_auc']:.4f} | {val['roc_auc']:.4f} | {val['precision']:.4f} | {val['recall']:.4f}")
    for m_name, m_val in v['ml_models'].items():
        val = m_val['val']
        print(f"{'[ML]   '+m_name:28s} | {val['f1']:.4f} | {val['pr_auc']:.4f} | {val['roc_auc']:.4f} | {val['precision']:.4f} | {val['recall']:.4f}")

    print("\n--- TEST SET (HELD-OUT FUTURE UNSEEN) ---")
    print(f"{'Model/Baseline':28s} | {'F1':6s} | {'PR-AUC':6s} | {'ROC':6s} | {'Prec':6s} | {'Rec':6s} | {'Confusion Matrix':18s}")
    print("-" * 88)
    for b_name, b_val in v['baselines'].items():
        t = b_val['test']
        print(f"{'[Base] '+b_name:28s} | {t['f1']:.4f} | {t['pr_auc']:.4f} | {t['roc_auc']:.4f} | {t['precision']:.4f} | {t['recall']:.4f} | {str(t['confusion_matrix']):18s}")
    for m_name, m_val in v['ml_models'].items():
        t = m_val['test']
        print(f"{'[ML]   '+m_name:28s} | {t['f1']:.4f} | {t['pr_auc']:.4f} | {t['roc_auc']:.4f} | {t['precision']:.4f} | {t['recall']:.4f} | {str(t['confusion_matrix']):18s}")

print("\n==========================================")
print(" CONTINUOUS REGRESSION EVALUATION (T+1)")
print("==========================================")
for k, v in d['regression_evaluation'].items():
    print(f"{k:30s} | MAE: {v['mae']:.4f} | RMSE: {v['rmse']:.4f} | R2: {v['r2']:.4f}")

print("\n==========================================")
print(" SPATIAL GENERALIZATION (> 1.0 hr)")
print("==========================================")
sg = d['spatial_generalization']
print(f"Coastal (<50km)  XGBoost: F1={sg['coastal_xgb']['f1']:.4f}, PR-AUC={sg['coastal_xgb']['pr_auc']:.4f}, P={sg['coastal_xgb']['precision']:.4f}, R={sg['coastal_xgb']['recall']:.4f}")
print(f"Coastal (<50km)  Base-7D: F1={sg['coastal_baseline_7d']['f1']:.4f}, PR-AUC={sg['coastal_baseline_7d']['pr_auc']:.4f}, P={sg['coastal_baseline_7d']['precision']:.4f}, R={sg['coastal_baseline_7d']['recall']:.4f}")
print(f"Offshore (>=50km) XGBoost: F1={sg['offshore_xgb']['f1']:.4f}, PR-AUC={sg['offshore_xgb']['pr_auc']:.4f}, P={sg['offshore_xgb']['precision']:.4f}, R={sg['offshore_xgb']['recall']:.4f}")
print(f"Offshore (>=50km) Base-7D: F1={sg['offshore_baseline_7d']['f1']:.4f}, PR-AUC={sg['offshore_baseline_7d']['pr_auc']:.4f}, P={sg['offshore_baseline_7d']['precision']:.4f}, R={sg['offshore_baseline_7d']['recall']:.4f}")

print("\nTop Active Grid Cells:")
for cid, cmetrics in sg['top_cells'].items():
    print(f"  {cid}: ActiveDays={cmetrics['active_days_test']}/{cmetrics['total_days_test']} | XGB F1={cmetrics['xgb_f1']:.4f}, PR={cmetrics['xgb_pr_auc']:.4f} | Base7D F1={cmetrics['b7d_f1']:.4f}, PR={cmetrics['b7d_pr_auc']:.4f}")

print("\n==========================================")
print(" FEATURE IMPORTANCES (TOP 12)")
print("==========================================")
fi = list(d['feature_importances'].items())[:12]
for feat, score in fi:
    print(f"  {feat:28s}: {score:.4f}")

print("\n==========================================")
print(" ACCEPTANCE VERDICT")
print("==========================================")
print(json.dumps(d['acceptance'], indent=2))
