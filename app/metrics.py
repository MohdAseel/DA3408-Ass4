import os
import threading

from prometheus_client import (
    Counter,
    Enum,
    Gauge,
    Histogram,
    Info,
    Summary,
    start_http_server,
)

METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))

# Latency buckets (seconds) chosen for CPU inference: ~0.3 s for a small
# image up to tens of seconds when many sessions compete for the CPU.
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 7.5, 10, 15, 30, 60)

# ---------------------------------------------------------------- Counters
REQUESTS = Counter(
    "caption_requests",
    "Caption requests (one per Single upload or per Bulk ZIP), by client.",
    ["mode", "client_ip", "session_id", "browser"],
)
IMAGES_PROCESSED = Counter(
    "caption_images_processed",
    "Images that went through the captioning pipeline.",
    ["mode", "status"],  # status: success | error
)
ERRORS = Counter(
    "caption_errors",
    "Errors raised while handling uploads, by error type.",
    ["mode", "error_type"],
)
UPLOAD_BYTES = Counter(
    "caption_upload_bytes",
    "Bytes received in uploads (image files or ZIP archives).",
    ["mode"],
)
TOKENS_GENERATED = Counter(
    "caption_tokens_generated",
    "Tokens produced by the caption decoder.",
    ["mode"],
)
IMAGES_BY_FORMAT = Counter(
    "caption_images_by_format",
    "Successfully decoded images, by file format.",
    ["mode", "image_format"],
)
ZIP_ENTRIES_SKIPPED = Counter(
    "caption_zip_entries_skipped",
    "ZIP entries ignored in Bulk mode, by reason.",
    ["reason"],  # not_image | hidden | too_large | over_limit | corrupt
)
BULK_JOBS = Counter(
    "caption_bulk_jobs",
    "Bulk (ZIP) jobs, by final status.",
    ["status"],  # completed | failed | rejected
)
SESSIONS_STARTED = Counter(
    "caption_sessions_started",
    "Browser sessions that opened the app.",
    ["browser"],
)

# ------------------------------------------------------------------ Gauges
ACTIVE_REQUESTS = Gauge(
    "caption_active_requests",
    "Requests being processed right now.",
    ["mode"],
)
ACTIVE_BULK_JOBS = Gauge(
    "caption_active_bulk_jobs",
    "Bulk (ZIP) jobs being processed right now.",
)
BULK_IMAGES_REMAINING = Gauge(
    "caption_bulk_images_remaining",
    "Images still waiting to be captioned in running Bulk jobs.",
)
MODEL_LOADED = Gauge(
    "caption_model_loaded",
    "1 when the captioning model is loaded and ready, else 0.",
)
MODEL_PARAMETERS = Gauge(
    "caption_model_parameters",
    "Number of parameters in the loaded model.",
)
MODEL_MEMORY_BYTES = Gauge(
    "caption_model_memory_bytes",
    "Memory held by the model weights (parameters x bytes per parameter).",
)
MODEL_LOAD_SECONDS = Gauge(
    "caption_model_load_seconds",
    "Seconds it took to load the model at startup.",
)
TORCH_THREADS = Gauge(
    "caption_torch_threads",
    "Intra-op CPU threads PyTorch uses for inference.",
)
LAST_SUCCESS_TIMESTAMP = Gauge(
    "caption_last_success_timestamp_seconds",
    "Unix time of the last successful caption.",
    ["mode"],
)
LAST_BULK_IMAGES = Gauge(
    "caption_last_bulk_images",
    "Number of images in the most recent Bulk job.",
)
ACTIVE_SESSIONS = Gauge(
    "caption_active_sessions",
    "Browser sessions connected to the Streamlit server.",
)

# -------------------------------------------------------------- Histograms
INFERENCE_SECONDS = Histogram(
    "caption_inference_seconds",
    "Model inference time per image (batch time / batch size in Bulk mode).",
    ["mode"],
    buckets=LATENCY_BUCKETS,
)
PREPROCESS_SECONDS = Histogram(
    "caption_preprocess_seconds",
    "Time to decode, convert and resize one image before inference.",
    ["mode"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
QUEUE_WAIT_SECONDS = Histogram(
    "caption_queue_wait_seconds",
    "Time a request waited for the model lock (CPU contention).",
    ["mode"],
    buckets=(0.001, 0.01, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
IMAGE_MEGAPIXELS = Histogram(
    "caption_image_megapixels",
    "Resolution of uploaded images in megapixels (before resizing).",
    ["mode"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 12, 16, 24),
)
BULK_JOB_IMAGES = Histogram(
    "caption_bulk_job_images",
    "Number of images per Bulk (ZIP) job.",
    buckets=(1, 2, 5, 10, 20, 50, 100, 200),
)
BULK_JOB_SECONDS = Histogram(
    "caption_bulk_job_seconds",
    "Total time to process one Bulk (ZIP) job.",
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300, 600),
)

# --------------------------------------------------------------- Summaries
# The Python client's Summary exports <name>_count and <name>_sum (no quantiles).
REQUEST_SECONDS = Summary(
    "caption_request_seconds",
    "End-to-end request time as seen by the user (upload to captions shown).",
    ["mode"],
)
CAPTION_LENGTH_CHARS = Summary(
    "caption_length_chars",
    "Length of generated captions in characters.",
    ["mode"],
)
UPLOAD_SIZE_BYTES = Summary(
    "caption_upload_size_bytes",
    "Size of each upload in bytes.",
    ["mode"],
)

# ------------------------------------------------------------ Info / Enum
MODEL_INFO = Info("caption_model", "Static information about the loaded model.")
APP_STATE = Enum(
    "caption_app_state",
    "What the model is doing right now.",
    states=["loading", "idle", "single", "bulk"],
)

# Pre-create every known label combination at 0. A series that first appears
# with value 1 is invisible to rate()/increase(), so the first image, error
# or job would otherwise be missing from the dashboard.
MODES = ("single", "bulk")
BROWSERS = ("chrome", "edge", "firefox", "safari", "script", "other")
ERROR_TYPES = {
    "single": ("corrupt_image", "decompression_bomb", "inference_error"),
    "bulk": ("corrupt_image", "decompression_bomb", "inference_error", "zip_entry_error",
             "zip_invalid", "zip_no_images", "bulk_job_error"),
}
for _mode in MODES:
    for _status in ("success", "error"):
        IMAGES_PROCESSED.labels(_mode, _status)
    for _kind in ERROR_TYPES[_mode]:
        ERRORS.labels(_mode, _kind)
    for _metric in (UPLOAD_BYTES, TOKENS_GENERATED, ACTIVE_REQUESTS, INFERENCE_SECONDS,
                    PREPROCESS_SECONDS, QUEUE_WAIT_SECONDS, IMAGE_MEGAPIXELS,
                    REQUEST_SECONDS, CAPTION_LENGTH_CHARS, UPLOAD_SIZE_BYTES):
        _metric.labels(_mode)
for _reason in ("not_image", "hidden", "too_large", "over_limit", "corrupt"):
    ZIP_ENTRIES_SKIPPED.labels(_reason)
for _status in ("completed", "failed", "rejected"):
    BULK_JOBS.labels(_status)
for _browser in BROWSERS:
    SESSIONS_STARTED.labels(_browser)

_server_lock = threading.Lock()
_server_started = False


def start_metrics_server():
    """Expose /metrics on METRICS_PORT once per process."""
    global _server_started
    with _server_lock:
        if not _server_started:
            start_http_server(METRICS_PORT)
            APP_STATE.state("loading")
            _server_started = True
