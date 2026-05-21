"""
FocusRoom — Model Export Script
=================================
Takes the best trained model (checkpoints/best_model.keras) and exports it
into two deployment-ready formats:

  1. TensorFlow.js  →  exports/tfjs_model/
     Used by the FocusRoom browser client for LOCAL inference (no frame sent to server).
     The TF.js model runs inside the user's browser tab via WebWorker.

  2. TFLite (float32 + quantised int8)  →  exports/tflite/
     Used as the server-side fallback when client device is too slow for TF.js.
     The int8 quantised version is ~4x smaller and faster on CPU.

  3. Verification test
     Loads both exported formats and runs a dummy inference to confirm they work.

After running this script, copy the output to your frontend and backend:
  cp -r exports/tfjs_model/ ../frontend/assets/models/
  cp exports/tflite/eye_cnn_int8.tflite ../backend/ml/model_weights/

Usage:
  python export.py                       # export best model
  python export.py --model checkpoints/best_model.keras
  python export.py --skip_verify        # skip verification step (faster)
  python export.py --quantize_only      # re-quantise from existing SavedModel
"""

import os
import sys
import json
import argparse
import shutil
import numpy as np
import tensorflow as tf
from tensorflow import keras

# TF.js converter — installed via: pip install tensorflowjs
try:
    import tensorflowjs as tfjs
    HAS_TFJS = True
except ImportError:
    HAS_TFJS = False

# ─────────────────────────────────────────────
# 0. CONFIG
# ─────────────────────────────────────────────

CONFIG = {
    "best_checkpoint":      "checkpoints/best_model.keras",
    "eval_report":          "checkpoints/eval_report.json",

    # Export destinations
    "saved_model_dir":      "exports/saved_model",
    "tfjs_dir":             "exports/tfjs_model",
    "tflite_dir":           "exports/tflite",
    "export_manifest":      "exports/export_manifest.json",

    # TFLite filenames
    "tflite_float32":       "eye_cnn_float32.tflite",
    "tflite_int8":          "eye_cnn_int8.tflite",   # quantised — preferred for server

    # Model metadata
    "img_size":             (48, 48),
    "class_names":          ["focused", "distracted", "closed"],
    "num_classes":          3,

    # Int8 quantisation: representative dataset
    # (used to calibrate scale/zero-point for each layer)
    "data_dir":             "data/processed",
    "n_calibration":        200,    # images sampled from val set for calibration
}

CLASSES = CONFIG["class_names"]
IMG_H, IMG_W = CONFIG["img_size"]


# ─────────────────────────────────────────────
# 1. ARGUMENT PARSER
# ─────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="FocusRoom Model Exporter")
    parser.add_argument("--model",         type=str, default=None, help="Path to .keras model")
    parser.add_argument("--skip_verify",   action="store_true",    help="Skip post-export verification")
    parser.add_argument("--quantize_only", action="store_true",    help="Only re-run TFLite quantisation")
    return parser.parse_args()


# ─────────────────────────────────────────────
# 2. EXPORT: SavedModel (intermediate format)
# ─────────────────────────────────────────────

def export_saved_model(model, output_dir):
    """
    Export to TF SavedModel format.
    This is the intermediate format that both TF.js converter
    and TFLite converter read from.
    """
    print(f"\n  [1/3] Exporting SavedModel → {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    model.export(output_dir)
    print(f"  ✓ SavedModel written to: {output_dir}")

    # Quick sanity check — reload and run dummy inference
    reloaded = tf.saved_model.load(output_dir)
    dummy = tf.zeros([1, IMG_H, IMG_W, 1])
    out = reloaded.serve(dummy)
    assert out.shape == (1, CONFIG["num_classes"]), \
        f"SavedModel output shape mismatch: {out.shape}"
    print("  ✓ SavedModel sanity check passed")
    return output_dir


# ─────────────────────────────────────────────
# 3. EXPORT: TensorFlow.js
# ─────────────────────────────────────────────

def export_tfjs(saved_model_dir, tfjs_dir):
    """
    Convert SavedModel → TF.js graph model.

    The TF.js model is loaded in the browser via:
        const model = await tf.loadGraphModel('/assets/models/tfjs_model/model.json');

    Weight sharding: set shard_size_bytes to 4MB so each shard fits
    a browser cache entry. The model.json file lists the shard files.
    """
    print(f"\n  [2/3] Exporting TF.js model → {tfjs_dir}")

    if not HAS_TFJS:
        print("  ⚠ tensorflowjs not installed.")
        print("  Install with:  pip install tensorflowjs")
        print("  Then re-run:   python export.py")
        print("  Skipping TF.js export.")
        return False

    os.makedirs(tfjs_dir, exist_ok=True)

    tfjs.converters.convert_tf_saved_model(
        saved_model_dir,
        tfjs_dir,
        signature_def="serving_default",
        saved_model_tags=["serve"],
        quantization_dtype_map=None,     # float32 — precision matters for CNN
        weight_shard_size_bytes=4 * 1024 * 1024,   # 4MB shards
    )

    # Count shards produced
    shard_files = [f for f in os.listdir(tfjs_dir) if f.endswith(".bin")]
    model_json  = os.path.join(tfjs_dir, "model.json")

    print(f"  ✓ TF.js export complete")
    print(f"    model.json   : {model_json}")
    print(f"    Weight shards: {len(shard_files)} file(s)")

    # Print total model size
    total_bytes = sum(
        os.path.getsize(os.path.join(tfjs_dir, f))
        for f in os.listdir(tfjs_dir)
    )
    print(f"    Total size   : {total_bytes / 1024:.1f} KB")

    return True


# ─────────────────────────────────────────────
# 4. EXPORT: TFLite
# ─────────────────────────────────────────────

def get_calibration_dataset(data_dir, n_samples):
    """
    For int8 quantisation, TFLite needs a representative dataset
    to determine the activation ranges of each layer.
    We sample n_samples images from the validation set.

    Returns a generator that yields individual image batches (shape: 1, 48, 48, 1).
    """
    from tensorflow.keras.preprocessing.image import ImageDataGenerator

    datagen = ImageDataGenerator(rescale=1.0 / 255.0)
    gen = datagen.flow_from_directory(
        os.path.join(data_dir, "val"),
        target_size=(IMG_H, IMG_W),
        color_mode="grayscale",
        batch_size=1,
        class_mode=None,
        shuffle=True,
        seed=42,
    )

    def representative_dataset():
        count = 0
        for batch in gen:
            yield [batch.astype(np.float32)]
            count += 1
            if count >= n_samples:
                break

    return representative_dataset


def export_tflite(saved_model_dir, tflite_dir, data_dir):
    """
    Export two TFLite variants:

    A) float32 — full precision, larger file, no accuracy loss.
       Use this to verify TFLite works before trusting int8.

    B) int8 quantised — ~4x smaller, ~2x faster on CPU.
       Uses post-training quantisation with a representative dataset
       to calibrate activation ranges.
       Accuracy drop is typically < 0.5% for this model type.
    """
    print(f"\n  [3/3] Exporting TFLite models → {tflite_dir}")
    os.makedirs(tflite_dir, exist_ok=True)

    # ── A: float32 ──
    print("  Converting float32 TFLite...")
    converter_f32 = tf.lite.TFLiteConverter.from_saved_model(saved_model_dir)
    tflite_f32 = converter_f32.convert()
    f32_path = os.path.join(tflite_dir, CONFIG["tflite_float32"])
    with open(f32_path, "wb") as f:
        f.write(tflite_f32)
    print(f"  ✓ float32 TFLite → {f32_path}  ({len(tflite_f32) / 1024:.1f} KB)")

    # ── B: int8 quantised ──
    print("  Converting int8 quantised TFLite (this may take 1–2 minutes)...")

    val_path = os.path.join(data_dir, "val")
    if not os.path.exists(val_path):
        print(f"  ⚠ Val set not found at '{val_path}' — skipping int8 quantisation.")
        print("    float32 TFLite will still work as server fallback.")
        return f32_path, None

    representative_data = get_calibration_dataset(data_dir, CONFIG["n_calibration"])

    converter_int8 = tf.lite.TFLiteConverter.from_saved_model(saved_model_dir)
    converter_int8.optimizations = [tf.lite.Optimize.DEFAULT]
    converter_int8.representative_dataset = representative_data
    converter_int8.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter_int8.inference_input_type  = tf.float32   # keep float input for easy integration
    converter_int8.inference_output_type = tf.float32   # keep float output

    tflite_int8 = converter_int8.convert()
    int8_path = os.path.join(tflite_dir, CONFIG["tflite_int8"])
    with open(int8_path, "wb") as f:
        f.write(tflite_int8)

    compression = (1 - len(tflite_int8) / len(tflite_f32)) * 100
    print(f"  ✓ int8 TFLite    → {int8_path}  ({len(tflite_int8) / 1024:.1f} KB)")
    print(f"    Size reduction  : {compression:.1f}% vs float32")

    return f32_path, int8_path


# ─────────────────────────────────────────────
# 5. VERIFICATION
# ─────────────────────────────────────────────

def verify_tflite(tflite_path, label):
    """
    Load a TFLite model and run a single dummy inference.
    Confirms the model loads correctly and produces valid output.
    """
    print(f"  Verifying {label} ({os.path.basename(tflite_path)})...")

    interpreter = tf.lite.Interpreter(model_path=tflite_path)
    interpreter.allocate_tensors()

    input_details  = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    # Create a random eye crop (simulates a normalised 48x48 image)
    dummy_input = np.random.rand(1, IMG_H, IMG_W, 1).astype(np.float32)

    interpreter.set_tensor(input_details[0]["index"], dummy_input)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]["index"])

    # Probabilities should sum to ~1.0 (softmax output)
    prob_sum = output[0].sum()
    predicted_class = CLASSES[np.argmax(output[0])]
    assert 0.99 < prob_sum < 1.01, f"Softmax sum out of range: {prob_sum}"

    print(f"    Input shape     : {input_details[0]['shape']}")
    print(f"    Output shape    : {output_details[0]['shape']}")
    print(f"    Dummy prediction: {predicted_class} ({output[0].max() * 100:.1f}%)")
    print(f"    ✓ {label} verified")


def verify_tfjs_structure(tfjs_dir):
    """Check that the TF.js export contains the required files."""
    required = ["model.json"]
    for fname in required:
        fpath = os.path.join(tfjs_dir, fname)
        if not os.path.exists(fpath):
            print(f"  ✗ Missing required TF.js file: {fname}")
            return False
    shard_count = len([f for f in os.listdir(tfjs_dir) if f.endswith(".bin")])
    print(f"  ✓ TF.js structure valid — model.json + {shard_count} shard(s)")
    return True


# ─────────────────────────────────────────────
# 6. DEPLOYMENT INSTRUCTIONS
# ─────────────────────────────────────────────

def print_deployment_instructions(tfjs_dir, f32_path, int8_path, tfjs_ok):
    print("\n" + "═" * 55)
    print("  DEPLOYMENT INSTRUCTIONS")
    print("═" * 55)

    print("\n  ── Frontend (TF.js — client-side inference) ──")
    if tfjs_ok:
        print(f"  1. Copy TF.js model to frontend:")
        print(f"       cp -r {tfjs_dir}/ ../frontend/assets/models/tfjs_model/")
        print(f"  2. In eye-capture.js, load with:")
        print(f"       const model = await tf.loadGraphModel('/assets/models/tfjs_model/model.json');")
        print(f"  3. Run inference:")
        print(f"       const eyeCrop = tf.browser.fromPixels(canvas, 1)  // grayscale")
        print(f"               .resizeBilinear([48, 48])")
        print(f"               .toFloat().div(255.0)")
        print(f"               .expandDims(0);")
        print(f"       const probs = model.predict(eyeCrop);")
        print(f"       const classIndex = probs.argMax(1).dataSync()[0];")
        print(f"       const classes = {CLASSES};")
        print(f"       const state = classes[classIndex];")
    else:
        print("  TF.js model was not exported (tensorflowjs not installed).")

    print(f"\n  ── Backend (TFLite — server-side fallback) ──")
    if int8_path:
        preferred = int8_path
    else:
        preferred = f32_path
    print(f"  1. Copy TFLite model to backend:")
    print(f"       cp {preferred} ../backend/ml/model_weights/eye_cnn.tflite")
    print(f"  2. In backend/ml/cnn_model.py, load with:")
    print(f"       import tflite_runtime.interpreter as tflite")
    print(f"       interp = tflite.Interpreter('ml/model_weights/eye_cnn.tflite')")
    print(f"       interp.allocate_tensors()")
    print(f"  3. Inference endpoint: POST /api/predict")
    print(f"       Body: base64-encoded 48x48 grayscale eye crop")
    print(f"       Returns: {{state: 'focused', confidence: 0.94}}")

    print("\n═" * 55 + "\n")


# ─────────────────────────────────────────────
# 7. MAIN
# ─────────────────────────────────────────────

def main():
    args = parse_args()
    model_path = args.model or CONFIG["best_checkpoint"]

    print("\n╔══════════════════════════════════════════╗")
    print("║      FocusRoom — Model Exporter           ║")
    print("╚══════════════════════════════════════════╝\n")

    # ── Validate model exists ──
    if not os.path.exists(model_path):
        print(f"  ERROR: Model not found at '{model_path}'")
        print("  Run train.py first, then come back here.")
        sys.exit(1)

    # ── Create exports directory ──
    os.makedirs("exports", exist_ok=True)

    # ── Load model ──
    print(f"  Loading: {model_path}")
    model = keras.models.load_model(model_path)
    print("  ✓ Model loaded\n")

    # Print eval summary if report exists
    if os.path.exists(CONFIG["eval_report"]):
        with open(CONFIG["eval_report"]) as f:
            report = json.load(f)
        print(f"  Model performance (from evaluate.py):")
        print(f"    Test accuracy  : {report.get('test_accuracy', 'N/A')}")
        print(f"    Macro F1 score : {report.get('macro_f1', 'N/A')}")
        print(f"    Target met     : {'✓ Yes' if report.get('target_met') else '✗ No'}\n")

    if args.quantize_only:
        # Skip SavedModel and TF.js — just re-quantise from existing SavedModel
        print("  --quantize_only mode: skipping SavedModel and TF.js exports")
        f32_path, int8_path = export_tflite(
            CONFIG["saved_model_dir"], CONFIG["tflite_dir"], CONFIG["data_dir"]
        )
    else:
        # ── Full export pipeline ──

        # Step 1: SavedModel
        saved_model_dir = export_saved_model(model, CONFIG["saved_model_dir"])

        # Step 2: TF.js
        tfjs_ok = export_tfjs(saved_model_dir, CONFIG["tfjs_dir"])

        # Step 3: TFLite
        f32_path, int8_path = export_tflite(
            saved_model_dir, CONFIG["tflite_dir"], CONFIG["data_dir"]
        )

    # ── Verification ──
    if not args.skip_verify:
        print("\n  ── Verifying exports ──")
        if HAS_TFJS and os.path.exists(CONFIG["tfjs_dir"]):
            verify_tfjs_structure(CONFIG["tfjs_dir"])
        if f32_path and os.path.exists(f32_path):
            verify_tflite(f32_path, "float32 TFLite")
        if int8_path and os.path.exists(int8_path):
            verify_tflite(int8_path, "int8 TFLite")

    # ── Write export manifest ──
    manifest = {
        "source_model":  model_path,
        "tfjs_dir":      CONFIG["tfjs_dir"] if (HAS_TFJS and not args.quantize_only) else None,
        "tflite_float32": f32_path,
        "tflite_int8":   int8_path,
        "class_names":   CLASSES,
        "input_shape":   [1, IMG_H, IMG_W, 1],
        "notes":         "int8 TFLite preferred for server fallback. TF.js for browser inference.",
    }
    with open(CONFIG["export_manifest"], "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  ✓ Export manifest saved → {CONFIG['export_manifest']}")

    # ── Print deployment instructions ──
    print_deployment_instructions(
        CONFIG["tfjs_dir"],
        f32_path,
        int8_path,
        HAS_TFJS and not args.quantize_only,
    )

    print("  ✓ Export complete. All files in: exports/\n")


if __name__ == "__main__":
    main()