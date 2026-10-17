"""Generates grafana/dashboards/caption-observability.json.

Every panel goes through the same helpers so the "7 commandments" hold
everywhere:
  1. Colour-blind-safe palette: Okabe-Ito colours only (shades of one hue for
     open-ended series such as client IPs).
  2. Markers that survive print/greyscale: series also differ by line style.
  3. Named axes: every y axis has a label.
  4. Scale and unit stated: axis labels say "linear" or "log10" plus the unit.
  5. Legends whenever a panel has more than one series.
  6. Title + subtitle: "Title · subtitle".
  7. A description (the (i) tooltip) telling the panel's story, plus one
     text strip per row.

PromQL attribution: the queries were generated with Claude Code (Anthropic,
Claude Opus 5.5). Prompt used: "complete the required Assignment4.pdf".
The logic of each query is explained by hand in docs/PROMQL.md.

Run:  python3 grafana/build_dashboard.py
"""

import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
OUT = Path(__file__).parent / "dashboards" / "caption-observability.json"

# Okabe-Ito colour-blind-safe palette
BLUE, ORANGE, GREEN, SKY = "#0072B2", "#E69F00", "#009E73", "#56B4E9"
VERMILLION, PURPLE, YELLOW, GREY = "#D55E00", "#CC79A7", "#F0E442", "#999999"

SOLID = {"fill": "solid"}
DASH = {"fill": "dash", "dash": [10, 6]}
DOT = {"fill": "dot", "dash": [0, 8]}
LONGDASH = {"fill": "dash", "dash": [20, 6]}

panels, _ids, _y = [], iter(range(1, 1000)), [0]
_row_x, _row_h = [0], [0]


def place(w, h):
    """Simple left-to-right, top-to-bottom grid layout (24 columns)."""
    if _row_x[0] + w > 24:
        _y[0] += _row_h[0]
        _row_x[0], _row_h[0] = 0, 0
    pos = {"x": _row_x[0], "y": _y[0], "w": w, "h": h}
    _row_x[0] += w
    _row_h[0] = max(_row_h[0], h)
    return pos


def newline():
    _y[0] += _row_h[0]
    _row_x[0], _row_h[0] = 0, 0


def target(expr, legend="", ref="A", instant=False, fmt="time_series"):
    return {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref,
            "instant": instant, "range": not instant, "format": fmt}


def targets(queries, **kw):
    return [target(q[0], q[1] if len(q) > 1 else "", chr(65 + i), **kw)
            for i, q in enumerate(queries)]


def row(title, story):
    newline()
    panels.append({"type": "row", "id": next(_ids), "title": title, "collapsed": False,
                   "gridPos": {"x": 0, "y": _y[0], "w": 24, "h": 1}, "panels": []})
    _y[0] += 1
    panels.append({"type": "text", "id": next(_ids), "title": "", "transparent": True,
                   "gridPos": place(24, 2),
                   "options": {"mode": "markdown", "content": story}})
    newline()


def style(match, color, line=SOLID, extra=()):
    """Override for series whose display name matches the regex `match`."""
    props = [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}},
             {"id": "custom.lineStyle", "value": line}]
    props += [{"id": k, "value": v} for k, v in extra]
    return {"matcher": {"id": "byRegexp", "options": f"/{match}/"}, "properties": props}


def right_axis(match, label, unit, color, line=DASH, log=False):
    """Put matching series on a second, separately labelled right-hand axis."""
    scale = {"type": "log", "log": 10} if log else {"type": "linear"}
    return style(match, color, line, [("custom.axisPlacement", "right"),
                                      ("custom.axisLabel", label), ("unit", unit),
                                      ("custom.scaleDistribution", scale),
                                      ("custom.fillOpacity", 0)])


def timeseries(title, desc, queries, unit, axis, w=12, h=9, log=False, styles=(),
               stack=False, fill=10, minv=0, shades=None, bars=False):
    scale = {"type": "log", "log": 10} if log else {"type": "linear"}
    color = ({"mode": "shades", "fixedColor": shades} if shades
             else {"mode": "fixed", "fixedColor": BLUE})
    panels.append({
        "type": "timeseries", "id": next(_ids), "title": title,
        "description": desc + "\n\nX axis: wall-clock time (5 s samples).",
        "datasource": DS, "gridPos": place(w, h), "targets": targets(queries),
        "fieldConfig": {
            "defaults": {
                "unit": unit, "min": None if log else minv, "color": color,
                "custom": {
                    "drawStyle": "bars" if bars else "line", "lineWidth": 2,
                    "fillOpacity": 60 if bars else fill, "showPoints": "auto", "pointSize": 5,
                    "lineInterpolation": "linear", "spanNulls": False,
                    "axisLabel": axis, "axisPlacement": "left", "axisBorderShow": True,
                    "scaleDistribution": scale, "lineStyle": SOLID,
                    "stacking": {"mode": "normal" if stack else "none", "group": "A"},
                    "gradientMode": "none", "barAlignment": 0,
                    "thresholdsStyle": {"mode": "off"},
                },
            },
            "overrides": list(styles),
        },
        "options": {
            "legend": {"showLegend": True, "displayMode": "table", "placement": "bottom",
                       "calcs": ["lastNotNull", "mean", "max"]},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    })


def stat(title, desc, expr, unit="none", mappings=(), steps=None, w=4, h=4,
         text_mode="value", legend="", color_mode="background", decimals=None):
    steps = steps or [{"color": BLUE, "value": None}]
    panels.append({
        "type": "stat", "id": next(_ids), "title": title, "description": desc,
        "datasource": DS, "gridPos": place(w, h),
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {"defaults": {
            "unit": unit, "decimals": decimals, "mappings": list(mappings),
            "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "values": False},
                    "colorMode": color_mode, "graphMode": "none", "textMode": text_mode,
                    "justifyMode": "center", "orientation": "auto",
                    "wideLayout": True, "showPercentChange": False},
    })


def updown(ok_text, bad_text):
    return [{"type": "value", "options": {
        "1": {"text": ok_text, "color": BLUE, "index": 0},
        "0": {"text": bad_text, "color": VERMILLION, "index": 1}}},
        {"type": "special", "options": {"match": "null", "result": {
            "text": "NO DATA", "color": VERMILLION, "index": 2}}}]


def bargauge(title, desc, expr, legend, unit, w=6, h=9, color=BLUE, fmt="time_series",
             minv=0, maxv=None, steps=None):
    steps = steps or [{"color": color, "value": None}]
    panels.append({
        "type": "bargauge", "id": next(_ids), "title": title, "description": desc,
        "datasource": DS, "gridPos": place(w, h),
        "targets": [target(expr, legend, instant=True, fmt=fmt)],
        "fieldConfig": {"defaults": {"unit": unit, "min": minv, "max": maxv,
                                     "color": {"mode": "thresholds"},
                                     "thresholds": {"mode": "absolute", "steps": steps}},
                        "overrides": []},
        "options": {"orientation": "horizontal", "displayMode": "basic",
                    "valueMode": "text", "showUnfilled": True, "namePlacement": "left",
                    "sizing": "auto", "minVizHeight": 16, "maxVizHeight": 24,
                    "reduceOptions": {"calcs": ["lastNotNull"], "values": False}},
    })


def table(title, desc, expr, hide, rename, w=12, h=8, no_value="No data", sort=None,
          order=None, widths=None):
    panels.append({
        "type": "table", "id": next(_ids), "title": title, "description": desc,
        "datasource": DS, "gridPos": place(w, h),
        "targets": [target(expr, instant=True, fmt="table")],
        "transformations": [{"id": "organize", "options": {
            "excludeByName": {k: True for k in hide}, "renameByName": rename,
            "indexByName": {k: i for i, k in enumerate(order or [])}}}],
        "fieldConfig": {"defaults": {"noValue": no_value, "custom": {"align": "auto"}},
                        "overrides": [{"matcher": {"id": "byName", "options": k},
                                       "properties": [{"id": "custom.width", "value": v}]}
                                      for k, v in (widths or {}).items()]},
        "options": {"showHeader": True, "cellHeight": "sm",
                    "sortBy": [{"displayName": sort, "desc": True}] if sort else []},
    })


# ===================================================================== Panels
panels.append({
    "type": "text", "id": next(_ids), "title": "How to read this dashboard",
    "gridPos": place(24, 3),
    "options": {"mode": "markdown", "content": (
        "**Read top to bottom: health → throughput → latency → workload → clients → host "
        "hardware.** Orange shaded bands mark the time a **Bulk (ZIP) job** was running, so "
        "you can line spikes in latency or CPU up with uploads. Colours are the colour-blind-"
        "safe Okabe-Ito palette, and series also differ by line style (solid / dashed / "
        "dotted), so the charts still read in greyscale print. "
        "Single mode = **blue**, Bulk mode = **orange**, errors = **vermillion**.")},
})

# ----------------------------------------------------------- 1. Health
row("① Service health: is everything up?",
    "Status at a glance. Blue = healthy, vermillion = needs attention; the text says the "
    "state too, so colour is never the only cue.")
stat("Caption app · up?",
     "`up{job=\"caption-app\"}`: 1 if Prometheus scraped the app's /metrics endpoint "
     "on its last attempt, 0 if it failed.",
     'up{job="caption-app"}', mappings=updown("UP", "DOWN"),
     steps=[{"color": VERMILLION, "value": None}, {"color": BLUE, "value": 1}])
stat("node_exporter · up?",
     "`up{job=\"node\"}`: 1 if host metrics (CPU, RAM, disk, network) are being collected.",
     'up{job="node"}', mappings=updown("UP", "DOWN"),
     steps=[{"color": VERMILLION, "value": None}, {"color": BLUE, "value": 1}])
stat("Model · ready?",
     "`caption_model_loaded`: the app sets it to 1 once the BLIP weights are in memory.",
     "caption_model_loaded", mappings=updown("READY", "LOADING"),
     steps=[{"color": VERMILLION, "value": None}, {"color": BLUE, "value": 1}])
stat("Alerts · firing",
     "Number of Prometheus alert rules in the firing state (rules in "
     "prometheus/alert_rules.yml). 0 means all clear.",
     'count(ALERTS{alertstate="firing"}) or vector(0)',
     steps=[{"color": BLUE, "value": None}, {"color": VERMILLION, "value": 1}])
stat("Images · in range",
     "Successful captions (Single + Bulk) in the dashboard's time range: "
     "`increase()` of the success counter over `$__range`.",
     'sum(increase(caption_images_processed_total{status="success"}[$__range]))',
     unit="short", decimals=0, color_mode="none")
stat("Errors · 5 min ratio",
     "Failed images / all images over the last 5 minutes. "
     "Above 10 % fires the HighCaptionErrorRatio alert.",
     'sum(rate(caption_images_processed_total{status="error"}[5m])) '
     '/ clamp_min(sum(rate(caption_images_processed_total[5m])), 1e-9)',
     unit="percentunit", decimals=1,
     steps=[{"color": BLUE, "value": None}, {"color": ORANGE, "value": 0.05},
            {"color": VERMILLION, "value": 0.10}])
newline()
stat("In-flight", "`sum(caption_active_requests)`: uploads being processed now.",
     "sum(caption_active_requests)", w=3, color_mode="none")
stat("Sessions", "`caption_active_sessions`: browser tabs connected to Streamlit.",
     "caption_active_sessions", w=3, color_mode="none")
stat("Model state",
     "`caption_app_state` (Enum): what the model is doing now: idle, single or bulk.",
     "caption_app_state == 1", legend="{{caption_app_state}}", text_mode="name", w=3,
     color_mode="none")
stat("App uptime", "Time since the app process started: `time() - process_start_time_seconds`.",
     'time() - process_start_time_seconds{job="caption-app"}', unit="dtdurations", w=3,
     color_mode="none")
table("Alerts · pending and firing",
      "Every alert rule that is pending (condition true, waiting for its `for:` time) "
      "or firing. Alertmanager sends firing alerts to the alert-logger webhook.",
      "ALERTS", hide=["Time", "Value", "__name__"],
      rename={"alertname": "Alert", "alertstate": "State", "severity": "Severity"},
      w=12, h=4, no_value="No alerts: all clear")

# ----------------------------------------------------------- 2. Throughput
row("② Throughput: how much work is the app doing?",
    "Images and requests per unit time, split by mode. One Bulk request = one ZIP "
    "= many images, so Bulk shows up far more in images/s than in requests/min.")
timeseries("Images captioned per second · by mode",
           "Rate of successful captions (1-minute window), Single vs. Bulk, with failed images "
           "for comparison. Bulk jobs show up as plateaus that match the orange bands.",
           [('sum by (mode) (rate(caption_images_processed_total{status="success"}[1m]))',
             "{{mode}} · captioned"),
            ('sum(rate(caption_images_processed_total{status="error"}[1m]))',
             "all modes · failed")],
           "short", "Images / second · linear",
           styles=[style("^single", BLUE), style("^bulk", ORANGE, DASH),
                   style("failed", VERMILLION, DOT)])
timeseries("Requests per minute · by mode",
           "Uploads handled per minute: a Single request is one image, a Bulk request is one ZIP.",
           [("sum by (mode) (rate(caption_requests_total[1m])) * 60", "{{mode}}")],
           "short", "Requests / minute · linear", w=6, bars=True,
           styles=[style("^single", BLUE), style("^bulk", ORANGE, DASH)])
timeseries("Upload volume · bytes per second",
           "Bytes received in uploads (images or ZIPs), 1-minute rate.",
           [("sum by (mode) (rate(caption_upload_bytes_total[1m]))", "{{mode}}")],
           "Bps", "Upload (bytes/s) · linear", w=6,
           styles=[style("^single", BLUE), style("^bulk", ORANGE, DASH)])

# ----------------------------------------------------------- 3. Latency
row("③ Latency: how fast is each caption?",
    "Percentiles come from the **Histogram** (`caption_inference_seconds`), means from "
    "**Summary** `_sum / _count`. Log scale, because a contended CPU makes latency jump "
    "by orders of magnitude.")
timeseries("Per-image inference latency · p50 / p95 / p99",
           "Percentiles of model time per image (both modes), computed with "
           "`histogram_quantile` over 1-minute bucket rates. If p99 is far above p50, a few "
           "images (usually during Bulk jobs) are much slower than usual.",
           [(f"histogram_quantile({q}, sum by (le) "
             f"(rate(caption_inference_seconds_bucket[1m])))", f"p{int(q * 100)}")
            for q in (0.5, 0.95, 0.99)],
           "s", "Latency (s) · log10", log=True, fill=0,
           styles=[style("^p50", GREEN), style("^p95", ORANGE, DASH),
                   style("^p99", VERMILLION, DOT)])
timeseries("Mean latency by mode · request vs. model only",
           "Solid = mean end-to-end request time (Summary `caption_request_seconds`: upload to "
           "result, a whole ZIP for Bulk). Dashed = mean model time per image (Histogram "
           "`_sum / _count`). The gap between them is decoding, queueing and UI time.",
           [("sum by (mode) (rate(caption_request_seconds_sum[1m])) / "
             "sum by (mode) (rate(caption_request_seconds_count[1m]))",
             "{{mode}} · request (summary)"),
            ("sum by (mode) (rate(caption_inference_seconds_sum[1m])) / "
             "sum by (mode) (rate(caption_inference_seconds_count[1m]))",
             "{{mode}} · per image (histogram)")],
           "s", "Mean latency (s) · log10", log=True, fill=0,
           styles=[style("^single · request", BLUE), style("^bulk · request", ORANGE),
                   style("^single · per image", BLUE, DASH),
                   style("^bulk · per image", ORANGE, DASH)])
panels.append({
    "type": "heatmap", "id": next(_ids),
    "title": "Inference latency distribution · images per bucket per minute",
    "description": "Each column is one time step; each cell counts the images whose inference "
                   "time fell into that latency bucket (from histogram buckets). Brighter = more "
                   "images. Viridis colours are colour-blind safe and read in greyscale.",
    "datasource": DS, "gridPos": place(12, 9),
    "targets": [target("sum by (le) (increase(caption_inference_seconds_bucket[1m]))",
                       "{{le}}", fmt="heatmap")],
    "options": {
        "calculate": False, "cellGap": 1,
        "color": {"mode": "scheme", "scheme": "Viridis", "steps": 64, "exponent": 0.5,
                  "fill": BLUE, "reverse": False},
        "yAxis": {"axisPlacement": "left", "unit": "s", "decimals": 2,
                  "axisLabel": "Latency bucket (s)"},
        "rowsFrame": {"layout": "le", "value": "Images"},
        "filterValues": {"le": 1e-9},
        "legend": {"show": True},
        "tooltip": {"mode": "single", "yHistogram": True, "showColorScale": True},
        "cellValues": {"unit": "short"},
    },
    "fieldConfig": {"defaults": {}, "overrides": []},
})
timeseries("Waiting vs. preprocessing · p95 per image",
           "Queue wait = time spent waiting for the model lock while another request uses the "
           "CPU. It grows when users overlap, especially behind a Bulk job. Preprocessing = "
           "decode + RGB conversion + resize.",
           [("histogram_quantile(0.95, sum by (le) (rate(caption_queue_wait_seconds_bucket[1m])))",
             "p95 queue wait"),
            ("histogram_quantile(0.95, sum by (le) (rate(caption_preprocess_seconds_bucket[1m])))",
             "p95 preprocessing")],
           "s", "Latency (s) · log10", log=True, fill=0,
           styles=[style("queue", PURPLE), style("preprocessing", SKY, DASH)])

# ----------------------------------------------------------- 4. Workload & errors
row("④ Workload & errors: what is being uploaded and what fails?",
    "Size of Bulk jobs, the images inside them, and every error or skipped ZIP entry by type.")
bargauge("Bulk job size · jobs by ≤ N images",
         "How many Bulk jobs (since app start) had up to N images: from the "
         "`caption_bulk_job_images` histogram, de-accumulated per bucket.",
         "sum by (le) (caption_bulk_job_images_bucket)", "≤ {{le}} images", "short",
         color=ORANGE, fmt="heatmap")
timeseries("Bulk progress · queue and jobs",
           "Solid (left axis) = images still waiting in running Bulk jobs; it falls as batches "
           "finish. Dashed (right axis) = number of Bulk jobs in progress.",
           [("caption_bulk_images_remaining", "images remaining"),
            ("caption_active_bulk_jobs", "active Bulk jobs")],
           "short", "Images remaining · linear", w=6,
           styles=[style("images", ORANGE),
                   right_axis("active", "Active jobs · linear", "short", GREY)])
timeseries("Errors per minute · by type",
           "Errors by `error_type` label: corrupt images, invalid ZIPs, ZIPs with no images, "
           "model failures. A flat line at 0 is the goal.",
           [("sum by (error_type) (rate(caption_errors_total[1m])) * 60", "{{error_type}}")],
           "short", "Errors / minute · linear", w=6,
           styles=[style("corrupt_image", VERMILLION), style("zip_invalid", PURPLE, DASH),
                   style("zip_no_images", YELLOW, DOT), style("inference_error", GREY, LONGDASH),
                   style("decompression_bomb", SKY, DASH), style("zip_entry_error", GREEN, DOT),
                   style("bulk_job_error", BLUE, LONGDASH)])
timeseries("Skipped ZIP entries per minute · by reason",
           "Files inside ZIPs that were not captioned: not an image, hidden/__MACOSX, too "
           "large, over the per-job limit, or corrupt.",
           [("sum by (reason) (rate(caption_zip_entries_skipped_total[1m])) * 60", "{{reason}}")],
           "short", "Entries / minute · linear", w=6, bars=True,
           styles=[style("not_image", GREY), style("hidden", SKY, DASH),
                   style("too_large", PURPLE, DOT), style("over_limit", YELLOW, LONGDASH),
                   style("corrupt", VERMILLION)])
newline()
timeseries("Image resolution · p50 / p95 megapixels",
           "Size of uploaded images before resizing (`caption_image_megapixels` histogram). "
           "Large photos cost more decode time, not more model time (BLIP uses 384 px).",
           [("histogram_quantile(0.5, sum by (le) (rate(caption_image_megapixels_bucket[5m])))",
             "p50"),
            ("histogram_quantile(0.95, sum by (le) (rate(caption_image_megapixels_bucket[5m])))",
             "p95")],
           "short", "Megapixels · linear", w=6, fill=0,
           styles=[style("p50", GREEN), style("p95", ORANGE, DASH)])
timeseries("Captions · length and tokens/s",
           "Solid (left) = mean caption length in characters (Summary `caption_length_chars` "
           "_sum/_count). Dashed (right) = decoder tokens generated per second.",
           [("sum(rate(caption_length_chars_sum[5m])) / sum(rate(caption_length_chars_count[5m]))",
             "mean caption length"),
            ("sum(rate(caption_tokens_generated_total[1m]))", "tokens / s")],
           "short", "Chars / caption · linear", w=6, fill=0,
           styles=[style("length", BLUE),
                   right_axis("tokens", "Tokens / s · linear", "short", ORANGE)])
timeseries("Mean upload size · by mode",
           "Average size of one upload (Summary `caption_upload_size_bytes` _sum/_count): an "
           "image for Single, a whole ZIP for Bulk.",
           [("sum by (mode) (rate(caption_upload_size_bytes_sum[5m])) / "
             "sum by (mode) (rate(caption_upload_size_bytes_count[5m]))", "{{mode}}")],
           "bytes", "Upload size (bytes) · log10", w=6, log=True, fill=0,
           styles=[style("^single", BLUE), style("^bulk", ORANGE, DASH)])
bargauge("Image formats · images since start",
         "Successfully decoded images by file format (`caption_images_by_format_total`).",
         "sum by (image_format) (caption_images_by_format_total)", "{{image_format}}", "short",
         color=SKY)

# ----------------------------------------------------------- 5. Clients
row("⑤ Clients: who is using the app?",
    "Client metadata from custom labels: source IP, Streamlit session id (first 8 chars) "
    "and browser family. Open the app in two browsers to see two sessions.")
table("Requests per client · since app start",
      "Counter `caption_requests_total` broken down by its client labels. One row per "
      "client IP + session + browser + mode.",
      "sum by (client_ip, session_id, browser, mode) (caption_requests_total) > 0",
      hide=["Time"], rename={"client_ip": "Client IP", "session_id": "Session",
                             "browser": "Browser", "mode": "Mode", "Value": "Requests"},
      sort="Requests", order=["client_ip", "session_id", "browser", "mode", "Value"],
      widths={"Client IP": 130, "Session": 110, "Browser": 90, "Mode": 80})
timeseries("Requests per minute · by client IP",
           "Upload requests per minute from each source IP. Shades of blue are used because the "
           "set of clients is open-ended.",
           [("sum by (client_ip) (rate(caption_requests_total[1m])) * 60", "{{client_ip}}")],
           "short", "Requests / minute · linear", w=6, shades=BLUE)
timeseries("Sessions · live and new/min",
           "Solid = browser sessions connected now. Dashed = new sessions started per minute, "
           "by browser family.",
           [("caption_active_sessions", "connected sessions"),
            ("sum by (browser) (rate(caption_sessions_started_total[1m])) * 60",
             "new · {{browser}}")],
           "short", "Sessions · linear", w=6, fill=0,
           styles=[style("connected", BLUE), style("new · chrome", ORANGE, DASH),
                   style("new · firefox", GREEN, DOT), style("new · edge", PURPLE, LONGDASH),
                   style("new · (safari|script|other)", GREY, DASH)])

# ----------------------------------------------------------- 6. Host
row("⑥ Host resources: does app load show up on the hardware? (node_exporter)",
    "System metrics from node_exporter next to the app's own process metrics. During a Bulk "
    "job (orange band) CPU should rise with images/s, and app memory should stay flat.")
timeseries("Host CPU busy % vs. images captioned per second",
           "Solid (left) = % of all CPU cores busy on the host (100 − idle). Dashed (right) = "
           "images captioned per second. If the two rise and fall together, the captioning "
           "app is what loads the CPU.",
           [('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))', "host CPU busy %"),
            ('sum(rate(caption_images_processed_total{status="success"}[1m]))', "images / s")],
           "percent", "CPU busy % · linear",
           styles=[style("CPU", VERMILLION, SOLID, [("max", 100)]),
                   right_axis("images", "Images / s · linear", "short", BLUE)])
timeseries("CPU cores in use · caption app vs. rest of host",
           "Stacked: CPU cores used by the caption-app process (`process_cpu_seconds_total`) "
           "and by everything else on the host. The top of the stack is total busy cores.",
           [('rate(process_cpu_seconds_total{job="caption-app"}[1m])', "caption-app process"),
            ('clamp_min(sum(rate(node_cpu_seconds_total{mode!="idle"}[1m])) - '
             'sum(rate(process_cpu_seconds_total{job="caption-app"}[1m])), 0)',
             "rest of host")],
           "short", "CPU cores busy · linear", stack=True, fill=40,
           styles=[style("caption-app", ORANGE), style("rest", GREY, DASH)])
timeseries("Memory · host used vs. caption-app RSS",
           "Solid = host RAM in use (MemTotal − MemAvailable). Dashed = resident memory of the "
           "caption-app process. Dotted = memory held by the BLIP weights alone.",
           [("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "host used"),
            ('process_resident_memory_bytes{job="caption-app"}', "caption-app RSS"),
            ("caption_model_memory_bytes", "model weights")],
           "bytes", "Memory (bytes) · linear", w=8, fill=0,
           styles=[style("host", VERMILLION), style("RSS", ORANGE, DASH),
                   style("weights", PURPLE, DOT)])
timeseries("Disk I/O · read and write throughput",
           "Bytes per second read from / written to physical disks (partitions and loop "
           "devices are excluded by node_exporter).",
           [("sum(rate(node_disk_read_bytes_total[1m]))", "read"),
            ("sum(rate(node_disk_written_bytes_total[1m]))", "write")],
           "Bps", "Disk (bytes/s) · linear", w=8, fill=0,
           styles=[style("read", BLUE), style("write", ORANGE, DASH)])
timeseries("Network · receive and transmit",
           "Bytes per second on physical interfaces (loopback, Docker bridges and veth "
           "pairs excluded). Uploads to the app show up as receive spikes.",
           [('sum(rate(node_network_receive_bytes_total{device!~"lo|docker.*|br-.*|veth.*"}[1m]))',
             "receive"),
            ('sum(rate(node_network_transmit_bytes_total{device!~"lo|docker.*|br-.*|veth.*"}[1m]))',
             "transmit")],
           "Bps", "Network (bytes/s) · linear", w=8, fill=0,
           styles=[style("receive", BLUE), style("transmit", ORANGE, DASH)])
timeseries("Load average vs. CPU count",
           "1- and 5-minute load averages. The dotted line is the number of CPU cores: load above "
           "it means processes are waiting for CPU.",
           [("node_load1", "load 1m"), ("node_load5", "load 5m"),
            ('count(node_cpu_seconds_total{mode="idle"})', "CPU cores")],
           "short", "Load (procs) · linear", fill=0,
           styles=[style("1m", VERMILLION), style("5m", ORANGE, DASH),
                   style("cores", GREY, DOT)])
bargauge("Filesystem usage · % used per mount",
         "Share of each real filesystem that is used. Orange from 80 %, vermillion from 90 % "
         "(the HostDiskAlmostFull alert fires below 10 % free).",
         '100 * (1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs|ramfs|fuse.*"} '
         '/ node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs|ramfs|fuse.*"})',
         "{{mountpoint}}", "percent", w=12, maxv=100,
         steps=[{"color": BLUE, "value": None}, {"color": ORANGE, "value": 80},
                {"color": VERMILLION, "value": 90}])

dashboard = {
    "uid": "caption-observability",
    "title": "Image Captioning · Observability (DA3408 A4)",
    "description": "BLIP image-captioning app on CPU: health, throughput, latency, workload, "
                   "clients and host resources (Prometheus + node_exporter).",
    "tags": ["da3408", "streamlit", "prometheus", "node_exporter"],
    "timezone": "browser", "editable": True, "graphTooltip": 1,
    "refresh": "5s", "time": {"from": "now-15m", "to": "now"},
    "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m"]},
    "schemaVersion": 41, "version": 1, "liveNow": False,
    "annotations": {"list": [
        {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
         "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
         "name": "Annotations & Alerts", "type": "dashboard"},
        {"datasource": DS, "enable": True, "name": "Bulk job running",
         "iconColor": "rgba(230, 159, 0, 0.35)", "expr": "caption_active_bulk_jobs > 0",
         "step": "5s", "titleFormat": "Bulk job running",
         "textFormat": "{{value}} job(s) in progress", "useValueForTime": False},
        {"datasource": DS, "enable": True, "name": "App restart",
         "iconColor": "rgba(204, 121, 167, 1)",
         "expr": 'changes(process_start_time_seconds{job="caption-app"}[1m]) > 0',
         "step": "60s", "titleFormat": "caption-app restarted", "useValueForTime": False},
    ]},
    "templating": {"list": []},
    "panels": panels,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n")
print(f"wrote {OUT} ({len(panels)} panels)")
