import io
import os
import time
import zipfile
from contextlib import contextmanager
from pathlib import PurePosixPath

import pandas as pd
import streamlit as st
from streamlit.runtime import Runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx

import metrics as m
from captioner import MODEL_NAME, ImageError, get_captioner

IMAGE_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff"]
BATCH_SIZE = int(os.getenv("BULK_BATCH_SIZE", "4"))
MAX_BULK_IMAGES = int(os.getenv("MAX_BULK_IMAGES", "200"))
MAX_ENTRY_BYTES = 25 * 1024 * 1024        # one image inside the ZIP
MAX_ZIP_UNCOMPRESSED = 1024 * 1024 * 1024  # guards against ZIP bombs
THUMBNAILS_SHOWN = 24

st.set_page_config(page_title="CPU Image Captioning", page_icon="🖼️", layout="wide")
m.start_metrics_server()  # no-op when started by run.py

def _active_sessions():
    try:
        return Runtime.instance()._session_mgr.num_active_sessions()
    except Exception:
        return float("nan")


m.ACTIVE_SESSIONS.set_function(_active_sessions)


def _browser(user_agent):
    ua = (user_agent or "").lower()
    for token, name in (("edg/", "edge"), ("firefox/", "firefox"), ("chrome/", "chrome"),
                        ("safari/", "safari"), ("curl", "script"), ("python", "script")):
        if token in ua:
            return name
    return "other"


def client_labels():
    """Client metadata used as Prometheus labels: source IP, short session id, browser."""
    ctx = get_script_run_ctx()
    headers = st.context.headers
    forwarded = headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() or st.context.ip_address or "localhost"
    return {
        "client_ip": ip,
        "session_id": ctx.session_id[:8] if ctx else "unknown",
        "browser": _browser(headers.get("User-Agent")),
    }


@contextmanager
def track_request(mode, client, upload_bytes):
    m.REQUESTS.labels(mode=mode, **client).inc()
    m.UPLOAD_BYTES.labels(mode).inc(upload_bytes)
    m.UPLOAD_SIZE_BYTES.labels(mode).observe(upload_bytes)
    m.ACTIVE_REQUESTS.labels(mode).inc()
    start = time.perf_counter()
    try:
        yield
    finally:
        m.ACTIVE_REQUESTS.labels(mode).dec()
        m.REQUEST_SECONDS.labels(mode).observe(time.perf_counter() - start)


def record_error(mode, kind, images=1):
    m.ERRORS.labels(mode, kind).inc()
    if images:
        m.IMAGES_PROCESSED.labels(mode, "error").inc(images)


# ------------------------------------------------------------------ Single
def single_mode(captioner, client):
    st.subheader("Single image")
    upload = st.file_uploader("Upload an image", type=IMAGE_TYPES, key="single_upload")
    if upload is None:
        return

    data = upload.getvalue()
    result = st.session_state.get("single_result")
    if result is None or result["file_id"] != upload.file_id:
        with track_request("single", client, len(data)):
            try:
                img = captioner.load_image(data, "single")
                start = time.perf_counter()
                with st.spinner("Generating caption…"):
                    caption = captioner.caption([img], "single")[0]
                result = {"file_id": upload.file_id, "caption": caption,
                          "seconds": time.perf_counter() - start, "error": None}
            except ImageError as exc:
                record_error("single", exc.kind)
                result = {"file_id": upload.file_id, "error": str(exc)}
            except Exception as exc:  # keep the app alive on unexpected model errors
                record_error("single", "inference_error")
                result = {"file_id": upload.file_id, "error": f"Captioning failed: {exc}"}
        st.session_state["single_result"] = result

    if result["error"]:
        st.error(f"{upload.name}: {result['error']}")
        return
    left, right = st.columns([2, 3])
    left.image(data, caption=upload.name, width="stretch")
    right.markdown(f"### “{result['caption']}”")
    right.caption(f"Generated in {result['seconds']:.2f} s on CPU")


# -------------------------------------------------------------------- Bulk
def _zip_entries(zf):
    """Yield (name, info) for image entries, counting the ones skipped."""
    total, kept = 0, 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        path = PurePosixPath(info.filename)
        if any(part.startswith(".") or part == "__MACOSX" for part in path.parts):
            m.ZIP_ENTRIES_SKIPPED.labels("hidden").inc()
            continue
        if path.suffix.lower().lstrip(".") not in IMAGE_TYPES:
            m.ZIP_ENTRIES_SKIPPED.labels("not_image").inc()
            continue
        if info.file_size > MAX_ENTRY_BYTES:
            m.ZIP_ENTRIES_SKIPPED.labels("too_large").inc()
            continue
        if kept >= MAX_BULK_IMAGES or total + info.file_size > MAX_ZIP_UNCOMPRESSED:
            m.ZIP_ENTRIES_SKIPPED.labels("over_limit").inc()
            continue
        total += info.file_size
        kept += 1
        yield path.name, info


def run_bulk(captioner, zf, entries):
    rows, thumbs = [], []
    progress = st.progress(0.0, text="Starting…")
    remaining = len(entries)
    m.BULK_IMAGES_REMAINING.inc(remaining)
    try:
        for i in range(0, len(entries), BATCH_SIZE):
            batch = []
            for name, info in entries[i:i + BATCH_SIZE]:
                try:
                    img = captioner.load_image(zf.read(info), "bulk")
                    batch.append((name, img))
                except (ImageError, zipfile.BadZipFile, OSError) as exc:
                    kind = exc.kind if isinstance(exc, ImageError) else "zip_entry_error"
                    m.ZIP_ENTRIES_SKIPPED.labels("corrupt").inc()
                    record_error("bulk", kind)
                    rows.append({"file": name, "caption": "", "status": f"skipped: {exc}"})
            if batch:
                try:
                    captions = captioner.caption([img for _, img in batch], "bulk")
                except Exception as exc:
                    record_error("bulk", "inference_error", len(batch))
                    captions = [None] * len(batch)
                    st.warning(f"Batch starting at {batch[0][0]} failed: {exc}")
                for (name, img), caption in zip(batch, captions):
                    rows.append({"file": name, "caption": caption or "",
                                 "status": "ok" if caption is not None else "failed"})
                    if caption is not None and len(thumbs) < THUMBNAILS_SHOWN:
                        img.thumbnail((256, 256))
                        thumbs.append((img, name, caption))
            done = min(i + BATCH_SIZE, len(entries))
            m.BULK_IMAGES_REMAINING.dec(done - i)
            remaining -= done - i
            progress.progress(done / len(entries), text=f"Captioned {done}/{len(entries)} images")
    finally:
        # If the user leaves mid-job, drop the images we never reached.
        m.BULK_IMAGES_REMAINING.dec(remaining)
    progress.empty()
    return rows, thumbs


def bulk_mode(captioner, client):
    st.subheader("Bulk (ZIP of images)")
    st.caption(f"Up to {MAX_BULK_IMAGES} images per ZIP, captioned in batches of {BATCH_SIZE}. "
               "Non-image files, hidden files and __MACOSX entries are skipped.")
    upload = st.file_uploader("Upload a ZIP file", type=["zip"], key="bulk_upload")
    if upload is None:
        return

    result = st.session_state.get("bulk_result")
    if result is None or result["file_id"] != upload.file_id:
        if not st.button("Caption all images", type="primary"):
            return
        data = upload.getvalue()
        result = {"file_id": upload.file_id, "rows": [], "thumbs": [], "error": None}
        with track_request("bulk", client, len(data)):
            m.ACTIVE_BULK_JOBS.inc()
            start = time.perf_counter()
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    entries = list(_zip_entries(zf))
                    if not entries:
                        record_error("bulk", "zip_no_images", images=0)
                        m.BULK_JOBS.labels("rejected").inc()
                        result["error"] = "The ZIP contains no supported images."
                    else:
                        m.BULK_JOB_IMAGES.observe(len(entries))
                        m.LAST_BULK_IMAGES.set(len(entries))
                        result["rows"], result["thumbs"] = run_bulk(captioner, zf, entries)
                        m.BULK_JOBS.labels("completed").inc()
            except zipfile.BadZipFile:
                record_error("bulk", "zip_invalid", images=0)
                m.BULK_JOBS.labels("rejected").inc()
                result["error"] = "This file is not a valid ZIP archive."
            except Exception as exc:
                record_error("bulk", "bulk_job_error", images=0)
                m.BULK_JOBS.labels("failed").inc()
                result["error"] = f"Bulk job failed: {exc}"
            finally:
                m.ACTIVE_BULK_JOBS.dec()
                m.BULK_JOB_SECONDS.observe(time.perf_counter() - start)
            result["seconds"] = time.perf_counter() - start
        st.session_state["bulk_result"] = result

    if result["error"]:
        st.error(result["error"])
        return
    df = pd.DataFrame(result["rows"])
    ok = int((df["status"] == "ok").sum())
    st.success(f"Captioned {ok} of {len(df)} images in {result['seconds']:.1f} s "
               f"({result['seconds'] / max(ok, 1):.2f} s per image).")
    st.download_button("Download captions (CSV)", df.to_csv(index=False).encode(),
                       file_name="captions.csv", mime="text/csv")
    st.dataframe(df, width="stretch", hide_index=True)
    if result["thumbs"]:
        st.markdown(f"**Preview** (first {len(result['thumbs'])} images)")
        cols = st.columns(4)
        for i, (img, name, caption) in enumerate(result["thumbs"]):
            cols[i % 4].image(img, caption=f"{name}: {caption}", width="stretch")


# -------------------------------------------------------------------- Page
client = client_labels()
if not st.session_state.get("session_counted"):
    m.SESSIONS_STARTED.labels(client["browser"]).inc()
    for _mode in m.MODES:  # start this client's request series at 0 (see metrics.py)
        m.REQUESTS.labels(mode=_mode, **client)
    st.session_state["session_counted"] = True

st.title("🖼️ CPU Image Captioning")
st.caption(f"Model: `{MODEL_NAME}` · CPU only · metrics on port {m.METRICS_PORT}/metrics")

with st.sidebar:
    mode = st.radio("Mode", ["Single", "Bulk (ZIP)"])
    st.divider()
    st.markdown("**Client metadata** (sent as metric labels)")
    st.json(client)

with st.spinner("Loading BLIP captioning model on CPU…"):
    captioner = get_captioner()
if mode == "Single":
    single_mode(captioner, client)
else:
    bulk_mode(captioner, client)
