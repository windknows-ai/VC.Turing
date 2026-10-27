"""Turing — a voice assistant for the Windows desktop. Say "嗨，图灵" / "Hey Turing"."""

import os

# numpy's OpenBLAS reserves a buffer per CPU thread when it's imported: ~750 MB on a
# 32-thread PC, for maths Turing never does (the speech models run on onnxruntime).
# One thread keeps it at ~10 MB. Must be set before numpy is first imported.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

__version__ = "0.1.0"
