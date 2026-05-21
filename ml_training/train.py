"""
FocusRoom — Eye State CNN  |  train.py
=======================================
Trains a 3-class eye-state classifier:
    0 → focused     (open eyes, forward gaze)
    1 → distracted  (open eyes, gaze off-centre)
    2 → closed      (closed / heavy-lidded eyes)

Checkpoint / Resume System
--------------------------
Every epoch is saved as:
    checkpoints/epoch_{N:03d}_acc{val_acc:.4f}.keras

On ANY interruption (Ctrl-C, power cut, OOM crash) the latest
epoch file is preserved.  Re-run the SAME command and training
resumes automatically from the last saved epoch — no flags needed.

State that is preserved across a resume:
    • Model weights
    • Epoch counter   (training continues from epoch N+1)
    • Optimizer state (Adam momentum / variance)
    • Training history so far (loss/accuracy curves)
    • Random seeds

Files written
-------------
    checkpoints/
        epoch_001_acc0.6210.keras       ← per-epoch snapshots
        epoch_002_acc0.6890.keras
        ...
        best_model.keras                ← best val_accuracy ever seen
        final_model.keras               ← weights at end of training
        training_state.json             ← epoch counter + history log
    model_weights/
        saved_model/                    ← TF SavedModel for TF.js export
        model_config.json
    reports/
        training_report.png
        training_log.csv
        class_report.txt

Usage
-----
    python train.py                          # full run (auto-resumes if interrupted)
    python train.py --epochs 5              # smoke-test
    python train.py --force_restart         # ignore existing checkpoints, start fresh
    python train.py --skip_preprocessing    # skip raw→processed copy
    python train.py --eval_only             # evaluate best_model.keras on test set
    python train.py --export_only           # export best_model.keras to SavedModel

Data layout expected
--------------------
    ml_training/data/raw/
        focused/     ← open eyes + forward gaze
        distracted/  ← open eyes + gaze off-centre
        closed/      ← closed / drowsy eyes
"""

import os
import sys
import json
import signal
import argparse
import random
import time
from pathlib import Path
from datetime import datetime
from copy import deepcopy

import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
    f1_score,
)
from sklearn.utils.class_weight import compute_class_weight

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, regularizers
    from tensorflow.keras.preprocessing.image import ImageDataGenerator
    print(f"TensorFlow {tf.__version__} loaded  |  "
          f"GPU: {tf.config.list_physical_devices('GPU')}")
except ImportError:
    print(
        "\n[ERROR] TensorFlow not installed.\n"
        "    pip install tensorflow==2.16.1\n"
    )
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

IMG_SIZE             = 64
BATCH_SIZE           = 32
EPOCHS               = 50
LEARNING_RATE        = 1e-3
DROPOUT_RATE         = 0.4
L2_LAMBDA            = 1e-4

EARLY_STOP_PAT       = 10
LR_REDUCE_PAT        = 5
LR_REDUCE_FACTOR     = 0.5
LR_MIN               = 1e-6

SPLIT_TRAIN          = 0.70
SPLIT_VAL            = 0.15
SPLIT_TEST           = 0.15

MIN_IMAGES_PER_CLASS = 100
CLASS_NAMES          = ["focused", "distracted", "closed"]
VALID_EXTS           = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
RANDOM_SEED          = 42

# Paths
SCRIPT_DIR      = Path(__file__).parent
DATA_RAW        = SCRIPT_DIR / "data" / "raw"
DATA_PROCESSED  = SCRIPT_DIR / "data" / "processed"
CHECKPOINT_DIR  = SCRIPT_DIR / "checkpoints"
WEIGHTS_DIR     = SCRIPT_DIR / "model_weights"
REPORT_DIR      = SCRIPT_DIR / "reports"

# Special checkpoint filenames
BEST_CKPT       = CHECKPOINT_DIR / "best_model.keras"
FINAL_CKPT      = CHECKPOINT_DIR / "final_model.keras"
STATE_FILE      = CHECKPOINT_DIR / "training_state.json"  # epoch + history


# ══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def set_seeds(seed: int = RANDOM_SEED):
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def make_dirs():
    for split in ("train", "val", "test"):
        for cls in CLASS_NAMES:
            (DATA_PROCESSED / split / cls).mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# CHECKPOINT STATE  — persists epoch counter + history across interruptions
# ══════════════════════════════════════════════════════════════════════════════

def save_training_state(epoch: int, history_so_far: dict, best_val_acc: float):
    """
    Write current training state to JSON so a resume can continue
    from exactly the right epoch with the right history.
    """
    state = {
        "last_completed_epoch" : epoch,
        "best_val_accuracy"    : best_val_acc,
        "saved_at"             : datetime.now().isoformat(),
        "history"              : history_so_far,
    }
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)   # atomic replace — never leaves a corrupt file


def load_training_state() -> dict | None:
    """
    Return the saved state dict if it exists, else None.
    """
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        log(f"Found training state: last epoch={state['last_completed_epoch']}, "
            f"best val_acc={state['best_val_accuracy']:.4f}")
        return state
    except (json.JSONDecodeError, KeyError) as e:
        log(f"[WARNING] Could not parse training state ({e}). Starting fresh.")
        return None


def find_latest_epoch_checkpoint() -> Path | None:
    """
    Scan checkpoints/ for epoch_{N:03d}_*.keras files and return the
    one with the highest N.  Returns None if no epoch checkpoints exist.
    """
    epoch_ckpts = sorted(CHECKPOINT_DIR.glob("epoch_*.keras"))
    if not epoch_ckpts:
        return None
    return epoch_ckpts[-1]   # sorted lexicographically → highest epoch last


def epoch_from_filename(path: Path) -> int:
    """Extract epoch number from 'epoch_007_acc0.8123.keras'."""
    try:
        return int(path.stem.split("_")[1])
    except (IndexError, ValueError):
        return 0


def cleanup_old_epoch_checkpoints(keep_last_n: int = 3):
    """
    Keep only the N most recent per-epoch checkpoints to save disk space.
    Always keeps best_model.keras and final_model.keras untouched.
    """
    epoch_ckpts = sorted(CHECKPOINT_DIR.glob("epoch_*.keras"))
    to_delete = epoch_ckpts[:-keep_last_n]
    for p in to_delete:
        p.unlink(missing_ok=True)
    if to_delete:
        log(f"Cleaned up {len(to_delete)} old epoch checkpoint(s).")


# ══════════════════════════════════════════════════════════════════════════════
# GRACEFUL INTERRUPT HANDLER
# ══════════════════════════════════════════════════════════════════════════════

_interrupt_requested = False

def _handle_sigint(sig, frame):
    """
    On Ctrl-C: set a flag so the training loop saves state before exiting,
    instead of crashing and losing the current epoch.
    """
    global _interrupt_requested
    if not _interrupt_requested:
        print(
            "\n[!] Interrupt received. Finishing current epoch then saving…\n"
            "    (Press Ctrl-C again to force-quit without saving)\n",
            flush=True,
        )
        _interrupt_requested = True
    else:
        print("\n[!] Force quit.", flush=True)
        sys.exit(1)

signal.signal(signal.SIGINT, _handle_sigint)


# ══════════════════════════════════════════════════════════════════════════════
# DATASET SCANNING
# ══════════════════════════════════════════════════════════════════════════════

def scan_raw_data() -> dict:
    log("Scanning raw dataset…")
    dataset = {c: [] for c in CLASS_NAMES}

    if not DATA_RAW.exists():
        log(f"[ERROR] Raw data folder missing: {DATA_RAW}")
        log("Create it and add sub-folders: focused/  distracted/  closed/")
        sys.exit(1)

    for cls in CLASS_NAMES:
        cls_dir = DATA_RAW / cls
        if not cls_dir.exists():
            log(f"[WARNING] Missing class folder: {cls_dir}")
            continue
        for p in cls_dir.rglob("*"):
            if p.suffix.lower() in VALID_EXTS:
                dataset[cls].append(p)

    for cls, paths in dataset.items():
        log(f"  {cls:12s}: {len(paths):6,} images")
        if len(paths) < MIN_IMAGES_PER_CLASS:
            log(f"[ERROR] '{cls}' has {len(paths)} images (min {MIN_IMAGES_PER_CLASS}).")
            sys.exit(1)

    log(f"  Total: {sum(len(v) for v in dataset.values()):,} images")
    return dataset


# ══════════════════════════════════════════════════════════════════════════════
# PREPROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def preprocess_image(img_path: Path) -> "np.ndarray | None":
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return cv2.resize(img, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)


def build_processed_splits(dataset: dict, max_per_class: int = 0):
    log("Building train / val / test splits…")
    split_counts = {"train": 0, "val": 0, "test": 0}

    for cls, paths in dataset.items():
        random.shuffle(paths)
        if max_per_class > 0 and len(paths) > max_per_class:
            paths = paths[:max_per_class]
            log(f"  [{cls}] capped at {max_per_class:,} images")
        n        = len(paths)
        n_train  = int(n * SPLIT_TRAIN)
        n_val    = int(n * SPLIT_VAL)

        splits = {
            "train": paths[:n_train],
            "val":   paths[n_train: n_train + n_val],
            "test":  paths[n_train + n_val:],
        }

        for split_name, split_paths in splits.items():
            out_dir = DATA_PROCESSED / split_name / cls
            for src in split_paths:
                dst = out_dir / src.name
                if dst.exists():
                    split_counts[split_name] += 1
                    continue
                img = preprocess_image(src)
                if img is None:
                    continue
                cv2.imwrite(str(dst), img)
                split_counts[split_name] += 1

        log(f"  {cls:12s}: train={len(splits['train'])}  "
            f"val={len(splits['val'])}  test={len(splits['test'])}")

    log(f"  Totals → {split_counts}")


# ══════════════════════════════════════════════════════════════════════════════
# DATA GENERATORS
# ══════════════════════════════════════════════════════════════════════════════

def make_generators(batch_size: int):
    log("Creating data generators…")

    train_gen_obj = ImageDataGenerator(
        rescale            = 1.0 / 255.0,
        rotation_range     = 15,
        width_shift_range  = 0.15,
        height_shift_range = 0.15,
        zoom_range         = 0.20,
        horizontal_flip    = True,
        brightness_range   = [0.6, 1.4],
        fill_mode          = "nearest",
    )
    eval_gen_obj = ImageDataGenerator(rescale=1.0 / 255.0)

    common = dict(
        target_size = (IMG_SIZE, IMG_SIZE),
        color_mode  = "grayscale",
        batch_size  = batch_size,
        class_mode  = "categorical",
        classes     = CLASS_NAMES,
        seed        = RANDOM_SEED,
    )

    train_gen = train_gen_obj.flow_from_directory(
        str(DATA_PROCESSED / "train"), shuffle=True, **common
    )
    val_gen = eval_gen_obj.flow_from_directory(
        str(DATA_PROCESSED / "val"), shuffle=False, **common
    )
    test_gen = eval_gen_obj.flow_from_directory(
        str(DATA_PROCESSED / "test"), shuffle=False, **common
    )

    weights_arr = compute_class_weight(
        class_weight="balanced",
        classes=np.unique(train_gen.classes),
        y=train_gen.classes,
    )
    class_weights = dict(enumerate(weights_arr))
    log(f"  Class weights: "
        f"{ {CLASS_NAMES[k]: round(float(v), 3) for k, v in class_weights.items()} }")

    return train_gen, val_gen, test_gen, class_weights


# ══════════════════════════════════════════════════════════════════════════════
# MODEL
# ══════════════════════════════════════════════════════════════════════════════

def build_model(num_classes: int = 3) -> keras.Model:
    reg = regularizers.l2(L2_LAMBDA)
    inp = keras.Input(shape=(IMG_SIZE, IMG_SIZE, 1), name="eye_crop")

    # Block 1
    x = layers.Conv2D(32, 3, padding="same", kernel_regularizer=reg)(inp)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.Conv2D(32, 3, padding="same", kernel_regularizer=reg)(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.MaxPooling2D(2)(x)
    x = layers.Dropout(0.15)(x)

    # Block 2
    x = layers.Conv2D(64, 3, padding="same", kernel_regularizer=reg)(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.Conv2D(64, 3, padding="same", kernel_regularizer=reg)(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.MaxPooling2D(2)(x)
    x = layers.Dropout(0.20)(x)

    # Block 3 — depthwise separable
    # Note: SeparableConv2D does not accept kernel_regularizer in Keras 3.x
    # Regularisation is handled by BatchNormalization + Dropout in each block
    x = layers.SeparableConv2D(128, 3, padding="same")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.SeparableConv2D(128, 3, padding="same")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.MaxPooling2D(2)(x)
    x = layers.Dropout(0.25)(x)

    # Block 4
    x = layers.SeparableConv2D(256, 3, padding="same")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.MaxPooling2D(2)(x)
    x = layers.Dropout(0.30)(x)

    # Head
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dense(128, kernel_regularizer=reg)(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.Dropout(DROPOUT_RATE)(x)
    out = layers.Dense(num_classes, activation="softmax", name="eye_state")(x)

    return keras.Model(inp, out, name="FocusRoom_EyeCNN")


# ══════════════════════════════════════════════════════════════════════════════
# TRAINING  — manual epoch loop for full checkpoint control
# ══════════════════════════════════════════════════════════════════════════════

def train(
    model: keras.Model,
    train_gen,
    val_gen,
    class_weights: dict,
    total_epochs: int,
    force_restart: bool = False,
) -> dict:
    """
    Manual epoch loop that:
      1. Checks for an existing checkpoint and resumes from it
      2. Saves a snapshot after EVERY epoch (so Ctrl-C loses at most one epoch)
      3. Always keeps the best-val-accuracy checkpoint separate
      4. Writes training_state.json so the exact epoch counter is preserved
      5. Returns the full history dict (merged pre-interrupt + post-resume)
    """

    # ── Load or initialise training state ────────────────────────────────────
    state        = None if force_restart else load_training_state()
    start_epoch  = 0
    best_val_acc = 0.0

    # Accumulated history across ALL runs (pre-interrupt + this run)
    full_history: dict[str, list] = {
        "loss": [], "accuracy": [], "val_loss": [], "val_accuracy": [],
        "precision": [], "recall": [], "val_precision": [], "val_recall": [],
        "lr": [],
    }

    if state is not None:
        start_epoch  = state["last_completed_epoch"]   # resume from next epoch
        best_val_acc = state["best_val_accuracy"]

        # Merge saved history
        for k in full_history:
            if k in state.get("history", {}):
                full_history[k] = state["history"][k]

        # Find the right checkpoint to load weights from
        latest_ckpt = find_latest_epoch_checkpoint()
        if latest_ckpt and latest_ckpt.exists():
            log(f"Resuming from epoch {start_epoch} → loading {latest_ckpt.name}")
            model.load_weights(str(latest_ckpt))
        elif BEST_CKPT.exists():
            log(f"No per-epoch checkpoint found. Loading best_model.keras.")
            model = keras.models.load_model(str(BEST_CKPT))
        else:
            log("[WARNING] State file found but no checkpoint. Starting fresh.")
            start_epoch  = 0
            best_val_acc = 0.0
    else:
        if force_restart:
            log("Force restart: ignoring all existing checkpoints.")
        else:
            log("No previous training state found. Starting from epoch 0.")

    if start_epoch >= total_epochs:
        log(f"Already completed {start_epoch}/{total_epochs} epochs. Nothing to do.")
        log("Use --force_restart to retrain from scratch.")
        return full_history

    # ── Compile ───────────────────────────────────────────────────────────────
    optimizer = keras.optimizers.Adam(learning_rate=LEARNING_RATE)
    model.compile(
        optimizer = optimizer,
        loss      = "categorical_crossentropy",
        metrics   = [
            "accuracy",
            keras.metrics.Precision(name="precision"),
            keras.metrics.Recall(name="recall"),
        ],
    )

    if start_epoch == 0:
        model.summary()
        log(f"Parameters: {model.count_params():,}")

    # ── LR schedule state (replicate ReduceLROnPlateau manually) ─────────────
    no_improve_epochs = 0          # for early stopping counter
    lr_no_improve     = 0          # for LR reduction counter
    current_lr        = LEARNING_RATE

    log(f"Training epochs {start_epoch + 1} → {total_epochs}")
    log("─" * 60)

    train_start = time.time()

    for epoch in range(start_epoch, total_epochs):

        if _interrupt_requested:
            log("Interrupt flag detected before epoch start. Saving state…")
            break

        epoch_display = epoch + 1
        epoch_start   = time.time()

        # ── Train one epoch ───────────────────────────────────────────────────
        log(f"Epoch {epoch_display}/{total_epochs}  (lr={current_lr:.2e})")

        train_result = model.fit(
            train_gen,
            epochs          = 1,
            class_weight    = class_weights,
            verbose         = 1,
        )

        # ── Validate ──────────────────────────────────────────────────────────
        val_result = model.evaluate(val_gen, verbose=0, return_dict=True)

        # ── Extract metrics ───────────────────────────────────────────────────
        t = train_result.history
        trn_loss  = t["loss"][0]
        trn_acc   = t["accuracy"][0]
        trn_prec  = t.get("precision", [0])[0]
        trn_rec   = t.get("recall", [0])[0]
        val_loss  = val_result["loss"]
        val_acc   = val_result["accuracy"]
        val_prec  = val_result.get("precision", 0)
        val_rec   = val_result.get("recall", 0)

        epoch_time = time.time() - epoch_start
        log(
            f"  loss={trn_loss:.4f}  acc={trn_acc:.4f}  |  "
            f"val_loss={val_loss:.4f}  val_acc={val_acc:.4f}  "
            f"({epoch_time:.1f}s)"
        )

        # ── Append to full history ────────────────────────────────────────────
        full_history["loss"].append(float(trn_loss))
        full_history["accuracy"].append(float(trn_acc))
        full_history["precision"].append(float(trn_prec))
        full_history["recall"].append(float(trn_rec))
        full_history["val_loss"].append(float(val_loss))
        full_history["val_accuracy"].append(float(val_acc))
        full_history["val_precision"].append(float(val_prec))
        full_history["val_recall"].append(float(val_rec))
        full_history["lr"].append(float(current_lr))

        # ── Per-epoch checkpoint (the key safety net) ─────────────────────────
        epoch_ckpt_path = CHECKPOINT_DIR / (
            f"epoch_{epoch_display:03d}_acc{val_acc:.4f}.keras"
        )
        model.save(str(epoch_ckpt_path))
        log(f"  Checkpoint saved → {epoch_ckpt_path.name}")

        # ── Best model ────────────────────────────────────────────────────────
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            model.save(str(BEST_CKPT))
            log(f"  ★ New best val_acc={best_val_acc:.4f} → best_model.keras updated")
            no_improve_epochs = 0
            lr_no_improve     = 0
        else:
            no_improve_epochs += 1
            lr_no_improve     += 1
            log(f"  No improvement. Patience: {no_improve_epochs}/{EARLY_STOP_PAT}")

        # ── Persist state IMMEDIATELY after saving checkpoint ─────────────────
        # If power dies between epoch saves, this file reflects the correct epoch.
        save_training_state(epoch_display, full_history, best_val_acc)

        # ── Clean up old per-epoch checkpoints (keep last 3) ─────────────────
        cleanup_old_epoch_checkpoints(keep_last_n=3)

        # ── Append to CSV log ─────────────────────────────────────────────────
        csv_path = REPORT_DIR / "training_log.csv"
        write_header = not csv_path.exists()
        with open(csv_path, "a") as f:
            if write_header:
                f.write("epoch,loss,accuracy,precision,recall,"
                        "val_loss,val_accuracy,val_precision,val_recall,lr\n")
            f.write(
                f"{epoch_display},{trn_loss:.6f},{trn_acc:.6f},"
                f"{trn_prec:.6f},{trn_rec:.6f},"
                f"{val_loss:.6f},{val_acc:.6f},"
                f"{val_prec:.6f},{val_rec:.6f},{current_lr:.2e}\n"
            )

        # ── LR reduction ─────────────────────────────────────────────────────
        if lr_no_improve >= LR_REDUCE_PAT:
            new_lr = max(current_lr * LR_REDUCE_FACTOR, LR_MIN)
            if new_lr < current_lr:
                current_lr = new_lr
                optimizer.learning_rate.assign(current_lr)
                log(f"  LR reduced → {current_lr:.2e}")
            lr_no_improve = 0

        # ── Early stopping ────────────────────────────────────────────────────
        if no_improve_epochs >= EARLY_STOP_PAT:
            log(f"Early stopping triggered after {epoch_display} epochs.")
            break

        # ── Honour interrupt after epoch completes cleanly ────────────────────
        if _interrupt_requested:
            log("Training interrupted. State saved. Re-run to resume.")
            break

    # ── Save final model ──────────────────────────────────────────────────────
    model.save(str(FINAL_CKPT))
    log(f"Final model saved → {FINAL_CKPT}")

    total_time = (time.time() - train_start) / 60
    log(f"Training finished in {total_time:.1f} min. "
        f"Best val_acc: {best_val_acc:.4f}")

    return full_history


# ══════════════════════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def evaluate(model: keras.Model, test_gen) -> dict:
    log("Evaluating on test set…")

    if BEST_CKPT.exists():
        log("Loading best_model.keras for evaluation…")
        model = keras.models.load_model(str(BEST_CKPT))

    results = model.evaluate(test_gen, verbose=1, return_dict=True)

    test_gen.reset()
    y_probs = model.predict(test_gen, verbose=1)
    y_pred  = np.argmax(y_probs, axis=1)
    y_true  = test_gen.classes

    report = classification_report(y_true, y_pred, target_names=CLASS_NAMES, digits=4)
    log("\nClassification Report:\n" + report)

    report_path = REPORT_DIR / "class_report.txt"
    with open(report_path, "w") as f:
        f.write("FocusRoom Eye CNN — Evaluation Report\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        f.write(report)
    log(f"Report saved → {report_path}")

    return {"results": results, "y_true": y_true, "y_pred": y_pred}


# ══════════════════════════════════════════════════════════════════════════════
# PLOTS
# ══════════════════════════════════════════════════════════════════════════════

def plot_training_report(history: dict, eval_data: dict):
    log("Generating training report…")

    fig = plt.figure(figsize=(14, 10))
    fig.suptitle("FocusRoom Eye State CNN — Training Report",
                 fontsize=14, fontweight="bold")
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

    epochs_ran = range(1, len(history["accuracy"]) + 1)

    # Accuracy
    ax = fig.add_subplot(gs[0, 0])
    ax.plot(epochs_ran, history["accuracy"],     label="Train", color="#6C63FF", lw=2)
    ax.plot(epochs_ran, history["val_accuracy"], label="Val",   color="#4ECDC4", lw=2, ls="--")
    ax.axhline(0.88, color="#FFD93D", ls=":", lw=1.5, label="Target 88%")
    ax.set(title="Accuracy", xlabel="Epoch", ylabel="Accuracy", ylim=(0, 1))
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # Loss
    ax = fig.add_subplot(gs[0, 1])
    ax.plot(epochs_ran, history["loss"],     label="Train", color="#FF6B6B", lw=2)
    ax.plot(epochs_ran, history["val_loss"], label="Val",   color="#FFD93D", lw=2, ls="--")
    ax.set(title="Loss", xlabel="Epoch", ylabel="Cat. Cross-Entropy")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # Confusion matrix
    ax = fig.add_subplot(gs[1, 0])
    cm = confusion_matrix(eval_data["y_true"], eval_data["y_pred"])
    ConfusionMatrixDisplay(cm, display_labels=CLASS_NAMES).plot(
        ax=ax, colorbar=False, cmap="Blues"
    )
    ax.set_title("Confusion Matrix (Test Set)")

    # Per-class F1
    ax = fig.add_subplot(gs[1, 1])
    f1s = f1_score(eval_data["y_true"], eval_data["y_pred"],
                   average=None, labels=[0, 1, 2])
    bars = ax.bar(CLASS_NAMES, f1s,
                  color=["#6C63FF", "#FF6B6B", "#4ECDC4"],
                  alpha=0.85, edgecolor="white")
    ax.axhline(0.88, color="#FFD93D", ls=":", lw=1.5, label="Target")
    ax.set(title="Per-Class F1 (Test Set)", ylabel="F1 Score", ylim=(0, 1))
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    for bar, s in zip(bars, f1s):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02,
                f"{s:.3f}", ha="center", fontsize=10, fontweight="bold")

    out = REPORT_DIR / "training_report.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log(f"Plot saved → {out}")


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def export_savedmodel(model: keras.Model):
    log("Exporting TF SavedModel…")
    if BEST_CKPT.exists():
        model = keras.models.load_model(str(BEST_CKPT))

    saved_dir = WEIGHTS_DIR / "saved_model"
    model.export(str(saved_dir))
    log(f"SavedModel → {saved_dir}")

    config = {
        "model_name"   : model.name,
        "input_shape"  : [IMG_SIZE, IMG_SIZE, 1],
        "classes"      : CLASS_NAMES,
        "num_classes"  : len(CLASS_NAMES),
        "total_params" : model.count_params(),
        "img_size"     : IMG_SIZE,
        "colour_mode"  : "grayscale",
        "normalisation": "divide_by_255",
        "exported_at"  : datetime.now().isoformat(),
    }
    with open(WEIGHTS_DIR / "model_config.json", "w") as f:
        json.dump(config, f, indent=2)

    log(
        "\nConvert to TF.js (pip install tensorflowjs first):\n"
        f"  tensorflowjs_converter --input_format=tf_saved_model \\\n"
        f"      {saved_dir} {WEIGHTS_DIR / 'tfjs_model'}\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description="FocusRoom Eye State CNN Trainer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--data_dir",           default=str(DATA_RAW))
    p.add_argument("--epochs",             type=int,  default=EPOCHS)
    p.add_argument("--batch_size",         type=int,  default=BATCH_SIZE)
    p.add_argument("--force_restart",      action="store_true",
                   help="Ignore existing checkpoints and retrain from scratch")
    p.add_argument("--skip_preprocessing", action="store_true")
    p.add_argument("--eval_only",          action="store_true")
    p.add_argument("--export_only",        action="store_true")
    p.add_argument("--max_per_class",      type=int,  default=0,
                   help="Cap images per class (e.g. 3000). 0 = use all. "
                        "Biggest CPU speed-up — your closed/ has 41k images.")
    p.add_argument("--img_size",           type=int,  default=0,
                   help="Override IMG_SIZE (e.g. 32). 0 = use default 64. "
                        "Halving size = 4x faster per epoch.")
    p.add_argument("--fast",               action="store_true",
                   help="CPU preset: img_size=32, max_per_class=3000, "
                        "epochs=20, batch_size=64. Good first run on laptop.")
    return p.parse_args()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    args = parse_args()
    global DATA_RAW, IMG_SIZE

    # ── --fast preset  (CPU-friendly) ────────────────────────────────────────
    # Applies before any other override so explicit flags still win.
    if args.fast:
        if args.img_size   == 0: args.img_size        = 32
        if args.max_per_class == 0: args.max_per_class = 3000
        if args.epochs     == EPOCHS:  args.epochs     = 20
        if args.batch_size == BATCH_SIZE: args.batch_size = 64
        log("--fast mode: img_size=32, max_per_class=3000, epochs=20, batch_size=64")

    # ── Apply img_size override ───────────────────────────────────────────────
    if args.img_size > 0:
        IMG_SIZE = args.img_size

    DATA_RAW = Path(args.data_dir)

    set_seeds()
    make_dirs()

    log("=" * 60)
    log("FocusRoom — Eye State CNN Training")
    log(f"  Classes    : {CLASS_NAMES}")
    log(f"  Img size   : {IMG_SIZE}×{IMG_SIZE} grayscale")
    log(f"  Max epochs : {args.epochs}")
    log(f"  Batch size : {args.batch_size}")
    log(f"  Max/class  : {args.max_per_class if args.max_per_class else 'all'}")
    log(f"  Data root  : {DATA_RAW}")
    log(f"  Resume     : {'disabled (--force_restart)' if args.force_restart else 'auto'}")
    log("=" * 60)

    if args.export_only:
        export_savedmodel(build_model())
        return

    if args.eval_only:
        _, _, test_gen, _ = make_generators(args.batch_size)
        eval_data = evaluate(build_model(), test_gen)
        return

    dataset = scan_raw_data()

    if not args.skip_preprocessing:
        build_processed_splits(dataset, max_per_class=args.max_per_class)
    else:
        log("Skipping preprocessing.")

    train_gen, val_gen, test_gen, class_weights = make_generators(args.batch_size)

    model = build_model()
    history = train(
        model         = model,
        train_gen     = train_gen,
        val_gen       = val_gen,
        class_weights = class_weights,
        total_epochs  = args.epochs,
        force_restart = args.force_restart,
    )

    eval_data = evaluate(model, test_gen)
    plot_training_report(history, eval_data)
    export_savedmodel(model)

    best_val = max(history["val_accuracy"]) if history["val_accuracy"] else 0
    test_acc = eval_data["results"]["accuracy"]

    log("")
    log("=" * 60)
    log("COMPLETE")
    log(f"  Best val acc : {best_val:.4f}  ({best_val*100:.1f}%)")
    log(f"  Test acc     : {test_acc:.4f}  ({test_acc*100:.1f}%)")
    log(f"  Target ≥88%  : {'YES ✓' if test_acc >= 0.88 else 'NO ✗ — more data needed'}")
    log(f"  Checkpoint   : {BEST_CKPT}")
    log(f"  SavedModel   : {WEIGHTS_DIR / 'saved_model'}")
    log(f"  Report       : {REPORT_DIR / 'training_report.png'}")
    log("=" * 60)


if __name__ == "__main__":
    main()
