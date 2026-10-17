import io
import os
import threading
import time

import torch
from PIL import Image, UnidentifiedImageError
from transformers import BlipForConditionalGeneration, BlipProcessor

import metrics as m

MODEL_NAME = os.getenv("MODEL_NAME", "Salesforce/blip-image-captioning-base")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "30"))
# BLIP resizes to 384x384 anyway; shrinking first keeps preprocessing cheap.
MAX_SIDE = 1024


class ImageError(Exception):
    """An upload that is not a usable image. `kind` becomes the error_type label."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


class Captioner:
    def __init__(self):
        start = time.perf_counter()
        torch.set_num_threads(int(os.getenv("TORCH_THREADS", os.cpu_count() or 1)))
        self.processor = BlipProcessor.from_pretrained(MODEL_NAME, use_fast=False)
        self.model = BlipForConditionalGeneration.from_pretrained(MODEL_NAME)
        self.model.eval()
        # One inference at a time: parallel generate() calls would fight over
        # the same CPU cores and all get slower. Waiting time is measured.
        self._lock = threading.Lock()

        params = list(self.model.parameters())
        m.MODEL_PARAMETERS.set(sum(p.numel() for p in params))
        m.MODEL_MEMORY_BYTES.set(sum(p.numel() * p.element_size() for p in params))
        m.MODEL_LOAD_SECONDS.set(time.perf_counter() - start)
        m.TORCH_THREADS.set(torch.get_num_threads())
        m.MODEL_INFO.info({
            "model_name": MODEL_NAME,
            "device": "cpu",
            "dtype": str(params[0].dtype).replace("torch.", ""),
            "torch_version": torch.__version__,
            "max_new_tokens": str(MAX_NEW_TOKENS),
        })
        m.MODEL_LOADED.set(1)
        m.APP_STATE.state("idle")

    @staticmethod
    def load_image(data, mode):
        """Decode bytes into an RGB image no larger than MAX_SIDE, recording metrics."""
        start = time.perf_counter()
        try:
            img = Image.open(io.BytesIO(data))
            fmt = (img.format or "unknown").lower()
            img.load()
        except Image.DecompressionBombError as exc:
            raise ImageError("decompression_bomb", "Image is too large to decode safely.") from exc
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            raise ImageError("corrupt_image", "File is not a readable image.") from exc

        m.IMAGE_MEGAPIXELS.labels(mode).observe(img.width * img.height / 1e6)
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        m.IMAGES_BY_FORMAT.labels(mode, fmt).inc()
        m.PREPROCESS_SECONDS.labels(mode).observe(time.perf_counter() - start)
        return img

    def caption(self, images, mode):
        """Caption a list of PIL images in one forward pass. Returns a list of strings."""
        wait_start = time.perf_counter()
        with self._lock:
            m.QUEUE_WAIT_SECONDS.labels(mode).observe(time.perf_counter() - wait_start)
            m.APP_STATE.state(mode)
            try:
                start = time.perf_counter()
                inputs = self.processor(images=images, return_tensors="pt")
                with torch.inference_mode():
                    out = self.model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)
                per_image = (time.perf_counter() - start) / len(images)
            finally:
                m.APP_STATE.state("idle")

        captions = self.processor.batch_decode(out, skip_special_tokens=True)
        pad_id = self.processor.tokenizer.pad_token_id
        for _ in images:
            m.INFERENCE_SECONDS.labels(mode).observe(per_image)
        m.TOKENS_GENERATED.labels(mode).inc(int((out != pad_id).sum()))
        for c in captions:
            m.CAPTION_LENGTH_CHARS.labels(mode).observe(len(c))
        m.IMAGES_PROCESSED.labels(mode, "success").inc(len(images))
        m.LAST_SUCCESS_TIMESTAMP.labels(mode).set_to_current_time()
        return [c.strip() for c in captions]


_instance = None
_instance_lock = threading.Lock()


def get_captioner():
    """Process-wide Captioner, created on first call (blocks until loaded)."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = Captioner()
        return _instance
