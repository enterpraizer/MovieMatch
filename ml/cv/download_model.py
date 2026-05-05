import shutil
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "models"
MODEL_PATH = MODELS_DIR / "emotion_model.onnx"


def download_from_huggingface() -> bool:
    try:
        from huggingface_hub import hf_hub_download

        print("Downloading emotion model from HuggingFace...")
        local_path = hf_hub_download(
            repo_id="trpakov/vit-face-expression",
            filename="model.onnx",
            local_dir=str(MODELS_DIR),
        )
        shutil.copy(local_path, MODEL_PATH)
        size_kb = MODEL_PATH.stat().st_size // 1024
        print(f"Downloaded: {MODEL_PATH} ({size_kb}KB)")
        return True
    except Exception as e:
        print(f"HuggingFace download failed: {e}")
        return False


def create_placeholder_model() -> bool:
    """Build a minimal valid ONNX classifier: (N,3,224,224) -> (N,7).

    Uses GlobalAveragePool + MatMul + Add so face pixels influence the output
    enough for integration testing.
    """
    print("Creating placeholder ONNX model...")
    try:
        import numpy as np
        import onnx
        from onnx import TensorProto, helper, numpy_helper

        rng = np.random.default_rng(42)
        weight = rng.standard_normal((3, 7), dtype=np.float32) * 0.1
        bias = np.zeros((7,), dtype=np.float32)

        w_init = numpy_helper.from_array(weight, name="W")
        b_init = numpy_helper.from_array(bias, name="B")

        input_tensor = helper.make_tensor_value_info(
            "input", TensorProto.FLOAT, ["N", 3, 224, 224]
        )
        output_tensor = helper.make_tensor_value_info(
            "logits", TensorProto.FLOAT, ["N", 7]
        )

        gap = helper.make_node("GlobalAveragePool", ["input"], ["pooled"])
        flatten = helper.make_node("Flatten", ["pooled"], ["flat"], axis=1)
        matmul = helper.make_node("MatMul", ["flat", "W"], ["matmul_out"])
        add = helper.make_node("Add", ["matmul_out", "B"], ["logits"])

        graph = helper.make_graph(
            [gap, flatten, matmul, add],
            "emotion_placeholder",
            [input_tensor],
            [output_tensor],
            [w_init, b_init],
        )
        model = helper.make_model(
            graph, opset_imports=[helper.make_opsetid("", 17)]
        )
        model.ir_version = 10
        onnx.checker.check_model(model)
        onnx.save(model, str(MODEL_PATH))

        print(f"Created placeholder model: {MODEL_PATH}")
        return True
    except Exception as e:
        print(f"Placeholder creation failed: {e}")
        return False


def verify_model() -> bool:
    import numpy as np
    import onnxruntime as ort

    session = ort.InferenceSession(
        str(MODEL_PATH), providers=["CPUExecutionProvider"]
    )
    test_input = np.random.randn(1, 3, 224, 224).astype(np.float32)
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: test_input})
    print(
        f"Model verified: input={session.get_inputs()[0].shape}, "
        f"output_shape={output[0].shape}"
    )
    return True


if __name__ == "__main__":
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if MODEL_PATH.exists():
        print(f"Model already exists: {MODEL_PATH}")
    else:
        success = download_from_huggingface()
        if not success:
            success = create_placeholder_model()
        if not success:
            print("ERROR: Could not obtain model")
            sys.exit(1)

    verify_model()
    print("Model ready for inference!")
