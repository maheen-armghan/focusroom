"""
FocusRoom — Eye State CNN Evaluation Script
============================================
Loads the best trained model (checkpoints/best_model.keras) and runs a
full evaluation on the held-out test set. Produces:

  1. Overall accuracy, loss, precision, recall, F1
  2. Per-class precision / recall / F1 (focused | distracted | closed)
  3. Confusion matrix (printed as ASCII + saved as PNG)
  4. Top-N most confident correct and incorrect predictions (for visual QA)
  5. Inference speed benchmark (avg ms per image)
  6. Evaluation report saved to: checkpoints/eval_report.json

Usage:
  python evaluate.py                              # evaluate best model on test set
  python evaluate.py --model checkpoints/best_model.keras
  python evaluate.py --model checkpoints/latest_epoch.keras
  python evaluate.py --data_dir data/processed
  python evaluate.py --show_errors               # print worst misclassifications
"""

import os
import sys
import json
import time
import argparse
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    f1_score,
)

# Optional: matplotlib for confusion matrix PNG — skip gracefully if not installed
try:
    import matplotlib
    matplotlib.use("Agg")           # headless — no display required
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ─────────────────────────────────────────────
# 0. CONFIG — must match train.py
# ─────────────────────────────────────────────

CONFIG = {
    "data_dir":          "data/processed",
    "best_checkpoint":   "checkpoints/best_model.keras",
    "report_path":       "checkpoints/eval_report.json",
    "cm_plot_path":      "checkpoints/confusion_matrix.png",

    "img_size":          (32, 32),
    "batch_size":        32,
    "class_names":       ["focused", "distracted", "closed"],
    "seed":              42,
    "n_benchmark":       200,           # images to use for speed benchmark
}

CLASSES = CONFIG["class_names"]


# ─────────────────────────────────────────────
# 1. ARGUMENT PARSER
# ─────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="FocusRoom CNN Evaluator")
    parser.add_argument("--model",       type=str, default=None, help="Path to .keras model file")
    parser.add_argument("--data_dir",    type=str, default=None, help="Dataset root directory")
    parser.add_argument("--show_errors", action="store_true",    help="Print worst misclassifications")
    return parser.parse_args()


# ─────────────────────────────────────────────
# 2. DATA LOADER (test split only)
# ─────────────────────────────────────────────

def load_test_generator(data_dir, img_size, batch_size):
    datagen = ImageDataGenerator(rescale=1.0 / 255.0)
    test_gen = datagen.flow_from_directory(
        os.path.join(data_dir, "test"),
        target_size=img_size,
        color_mode="grayscale",
        batch_size=batch_size,
        class_mode="categorical",
        classes=CLASSES,
        shuffle=False,              # keep order for confusion matrix alignment
        seed=CONFIG["seed"],
    )
    return test_gen


# ─────────────────────────────────────────────
# 3. CONFUSION MATRIX UTILITIES
# ─────────────────────────────────────────────

def print_confusion_matrix_ascii(cm, class_names):
    """Print a readable ASCII confusion matrix."""
    col_w = 12
    header = " " * col_w + "".join(f"Pred:{c[:6]:>6}" for c in class_names)
    print("\n  Confusion Matrix (rows = actual, cols = predicted)")
    print("  " + "─" * (col_w + col_w * len(class_names)))
    print("  " + header)
    print("  " + "─" * (col_w + col_w * len(class_names)))
    for i, row_name in enumerate(class_names):
        row_str = f"  Act:{row_name[:6]:>6}  "
        for j in range(len(class_names)):
            cell = cm[i][j]
            marker = " ✓" if i == j else "  "   # mark diagonal (correct)
            row_str += f"{cell:>6}{marker}  "
        print(row_str)
    print("  " + "─" * (col_w + col_w * len(class_names)))


def save_confusion_matrix_plot(cm, class_names, save_path):
    """Save a colour-coded confusion matrix PNG."""
    if not HAS_MATPLOTLIB:
        print("  matplotlib not installed — skipping confusion matrix plot.")
        return

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    ax.figure.colorbar(im, ax=ax)

    ax.set(
        xticks=np.arange(len(class_names)),
        yticks=np.arange(len(class_names)),
        xticklabels=class_names,
        yticklabels=class_names,
        title="FocusRoom — Eye State CNN Confusion Matrix (Test Set)",
        ylabel="True Label",
        xlabel="Predicted Label",
    )
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    # Annotate each cell with count + percentage
    row_sums = cm.sum(axis=1, keepdims=True)
    cm_norm = cm.astype(float) / np.where(row_sums == 0, 1, row_sums)
    thresh = cm.max() / 2.0

    for i in range(len(class_names)):
        for j in range(len(class_names)):
            ax.text(
                j, i,
                f"{cm[i, j]}\n({cm_norm[i, j] * 100:.1f}%)",
                ha="center", va="center", fontsize=10,
                color="white" if cm[i, j] > thresh else "black",
            )

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ Confusion matrix saved → {save_path}")


# ─────────────────────────────────────────────
# 4. INFERENCE SPEED BENCHMARK
# ─────────────────────────────────────────────

def benchmark_inference(model, test_gen, n_images):
    """
    Measure average single-image inference time.
    We care about this because the FocusRoom SLA is < 150ms per frame.
    Benchmark uses single-image batches (batch_size=1) to simulate real use.
    """
    print(f"\n  Benchmarking inference speed ({n_images} single images)...")

    # Collect n_images from test generator
    images_collected = 0
    all_images = []
    test_gen.reset()

    for batch_x, _ in test_gen:
        for img in batch_x:
            all_images.append(img)
            images_collected += 1
            if images_collected >= n_images:
                break
        if images_collected >= n_images:
            break

    # Time single-image predictions
    latencies = []
    for img in all_images:
        single_batch = np.expand_dims(img, axis=0)    # (1, 48, 48, 1)
        start = time.perf_counter()
        _ = model.predict(single_batch, verbose=0)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    avg_ms  = np.mean(latencies)
    p95_ms  = np.percentile(latencies, 95)
    max_ms  = np.max(latencies)
    sla_ok  = avg_ms < 150

    print(f"  Average latency : {avg_ms:.2f} ms")
    print(f"  P95 latency     : {p95_ms:.2f} ms")
    print(f"  Max latency     : {max_ms:.2f} ms")
    print(f"  SLA (< 150ms)   : {'✓ PASS' if sla_ok else '✗ FAIL — optimise model or use TFLite'}")

    return {"avg_ms": round(avg_ms, 2), "p95_ms": round(p95_ms, 2), "max_ms": round(max_ms, 2), "sla_pass": bool(sla_ok)}


# ─────────────────────────────────────────────
# 5. MISCLASSIFICATION ANALYSIS
# ─────────────────────────────────────────────

def show_worst_errors(y_true, y_pred, confidences, file_paths, n=10):
    """
    Print the N most confident wrong predictions.
    These are the model's 'hard mistakes' — useful for dataset debugging.
    """
    errors = [
        (confidences[i], y_true[i], y_pred[i], file_paths[i])
        for i in range(len(y_true))
        if y_true[i] != y_pred[i]
    ]
    errors.sort(key=lambda x: x[0], reverse=True)   # sort by confidence descending

    print(f"\n  Top {min(n, len(errors))} Most Confident Wrong Predictions:")
    print("  " + "─" * 60)
    print(f"  {'Confidence':>12}  {'True':>10}  {'Predicted':>12}  File")
    print("  " + "─" * 60)
    for conf, true_cls, pred_cls, fpath in errors[:n]:
        fname = os.path.basename(fpath)[:30]
        print(f"  {conf * 100:>10.2f}%  {CLASSES[true_cls]:>10}  {CLASSES[pred_cls]:>12}  {fname}")


# ─────────────────────────────────────────────
# 6. MAIN EVALUATION
# ─────────────────────────────────────────────

def main():
    args = parse_args()

    model_path = args.model or CONFIG["best_checkpoint"]
    data_dir   = args.data_dir or CONFIG["data_dir"]

    print("\n╔══════════════════════════════════════════╗")
    print("║    FocusRoom — Eye State CNN Evaluator    ║")
    print("╚══════════════════════════════════════════╝\n")

    # ── Validate paths ──
    if not os.path.exists(model_path):
        print(f"  ERROR: Model not found at '{model_path}'")
        print("  Run train.py first to generate a trained model.")
        sys.exit(1)

    if not os.path.exists(os.path.join(data_dir, "test")):
        print(f"  ERROR: Test set not found at '{data_dir}/test'")
        sys.exit(1)

    # ── Load model ──
    print(f"  Loading model: {model_path}")
    model = keras.models.load_model(model_path)
    print("  ✓ Model loaded successfully")

    # ── Load test data ──
    print(f"  Loading test data from: {data_dir}")
    test_gen = load_test_generator(data_dir, CONFIG["img_size"], CONFIG["batch_size"])
    print(f"  ✓ {test_gen.samples:,} test images across {len(CLASSES)} classes\n")

    # ── Keras built-in evaluation (loss + metrics) ──
    print("  Running model.evaluate() on test set...")
    test_gen.reset()
    results = model.evaluate(test_gen, verbose=1)
    metric_names = model.metrics_names
    keras_metrics = dict(zip(metric_names, results))

    print(f"\n  Keras evaluation:")
    for name, val in keras_metrics.items():
        print(f"    {name:12s} : {val:.4f}")

    # ── Get all predictions ──
    print("\n  Collecting predictions for full analysis...")
    test_gen.reset()
    y_pred_probs = model.predict(test_gen, verbose=1)   # shape: (N, 3)
    y_pred = np.argmax(y_pred_probs, axis=1)
    y_pred_confidence = np.max(y_pred_probs, axis=1)

    # True labels — from generator (not shuffled, so order matches)
    y_true = test_gen.classes

    # File paths for error analysis
    file_paths = [test_gen.filepaths[i] for i in range(len(y_true))]

    # ── Per-class classification report ──
    print("\n" + "─" * 55)
    print("  Per-Class Classification Report")
    print("─" * 55)
    report_str = classification_report(
        y_true, y_pred,
        target_names=CLASSES,
        digits=4,
    )
    # Indent for readability
    for line in report_str.split("\n"):
        print("  " + line)

    # Parse report to dict for JSON saving
    report_dict = classification_report(
        y_true, y_pred,
        target_names=CLASSES,
        digits=4,
        output_dict=True,
    )

    # ── Confusion matrix ──
    cm = confusion_matrix(y_true, y_pred)
    print_confusion_matrix_ascii(cm, CLASSES)
    save_confusion_matrix_plot(cm, CLASSES, CONFIG["cm_plot_path"])

    # ── Macro F1 ──
    macro_f1 = f1_score(y_true, y_pred, average="macro")
    test_accuracy = accuracy_score(y_true, y_pred)

    print("\n  Summary:")
    print(f"    Test accuracy  : {test_accuracy * 100:.2f}%")
    print(f"    Macro F1 score : {macro_f1:.4f}")
    print(f"    Target         : ≥ 88% accuracy")
    print(f"    Status         : {'✓ TARGET MET' if test_accuracy >= 0.88 else '✗ BELOW TARGET — consider more data or tuning'}")

    # ── Inference speed benchmark ──
    speed_metrics = benchmark_inference(model, test_gen, CONFIG["n_benchmark"])

    # ── Misclassification analysis ──
    if args.show_errors:
        show_worst_errors(y_true, y_pred, y_pred_confidence, file_paths, n=10)

    # ── Save evaluation report ──
    eval_report = {
        "model_path":    model_path,
        "test_samples":  int(test_gen.samples),
        "class_names":   CLASSES,
        "test_accuracy": round(float(test_accuracy), 4),
        "macro_f1":      round(float(macro_f1), 4),
        "target_met":    bool(float(test_accuracy) >= 0.88),
        "keras_metrics": {k: round(float(v), 4) for k, v in keras_metrics.items()},
        "per_class":     report_dict,
        "confusion_matrix": cm.tolist(),
        "speed_benchmark": speed_metrics,
    }

    os.makedirs(os.path.dirname(CONFIG["report_path"]), exist_ok=True)
    with open(CONFIG["report_path"], "w") as f:
        json.dump(eval_report, f, indent=2)

    print(f"\n  ✓ Evaluation report saved → {CONFIG['report_path']}")
    print("\n  Next step:")
    print("    python export.py     # → exports model to TF.js and TFLite\n")


if __name__ == "__main__":
    main()