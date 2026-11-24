"""Local consent-first Streamlit app; no target navigation or automatic submissions."""

import base64
import streamlit as st
from phishguard.dashboard.data_loader import api
from phishguard.dashboard.components import render_prediction, render_performance
from phishguard.dashboard.reports import local_report
from phishguard.dashboard.theme import apply

st.set_page_config(page_title="PhishGuard 2.0", page_icon="🛡️", layout="wide")
apply(st)
st.title("PhishGuard 2.0")
st.caption("PHISHING DETECTION  /  USER CONTROL  /  MEASURED RESULTS")
page = st.radio(
    "View",
    ["Check URL", "Screenshot", "Overview", "Model report", "Data quality", "Retained metadata"],
    horizontal=True,
)
try:
    if page == "Check URL":
        st.subheader("Check a public website URL")
        st.write("The API analyzes the URL text. It does not open the target website.")
        with st.form("scan", clear_on_submit=True):
            url = st.text_input("Public HTTP(S) URL", placeholder="https://example.com/")
            consent = st.checkbox("Send this URL to my configured PhishGuard server")
            submit = st.form_submit_button("Check URL")
        if submit:
            if not consent:
                st.warning("Consent is required for each submission.")
            else:
                render_prediction(st, api("POST", "/api/v1/predict/url", {"url": url}))
    elif page == "Screenshot":
        st.subheader("Optional screenshot check")
        st.warning(
            "Screenshots may contain personal messages or account details. Redact them first."
        )
        st.caption(
            "Selecting a file uploads it to this local dashboard session. Sending it to the API requires the checkbox and button below."
        )
        health = api("GET", "/health")
        if not health.get("vision_enabled"):
            st.info("The local screenshot model is disabled. No image submission is available.")
        else:
            upload = st.file_uploader("PNG or JPEG, up to 5 MB", type=["png", "jpg", "jpeg"])
            consent = st.checkbox("Send this image to my configured API for this one check")
            if st.button("Check screenshot", disabled=upload is None or not consent):
                if upload.size > 5_000_000:
                    st.error("The image exceeds the 5 MB limit.")
                else:
                    encoded = base64.b64encode(upload.getvalue()).decode("ascii")
                    result = api(
                        "POST", "/api/v1/predict/image", {"consent": True, "image_base64": encoded}
                    )
                    render_prediction(st, result)
                    st.caption(
                        "The API and extension do not persist screenshot bytes. Close this dashboard session to release the upload."
                    )
    elif page == "Overview":
        health = api("GET", "/health")
        metrics = api("GET", "/api/v1/metrics")
        runtime = metrics.get("runtime", {})
        first, second, third = st.columns(3)
        first.metric("Service", health.get("status", "unknown").upper())
        second.metric("Requests in this process", runtime.get("requests", 0))
        latency = runtime.get("latency_p95_ms")
        third.metric(
            "Recent p95 response time", f"{latency:.1f} ms" if latency is not None else "No samples"
        )
        st.write("Event storage:", "Enabled" if metrics["storage_enabled"] else "OFF")
        st.write("Loaded model:", health["model_version"])
        if runtime.get("status_classes"):
            st.bar_chart(runtime["status_classes"])
        pipeline = local_report("pipeline")
        if pipeline:
            st.subheader("Last recorded batch run")
            st.json(pipeline)
            st.caption("A saved run report is not a live progress monitor.")
    elif page == "Model report":
        report = local_report("model")
        if report is None:
            st.info("No local evaluation report has been configured.")
        else:
            render_performance(st, report)
    elif page == "Data quality":
        report = local_report("quality")
        if report is None:
            st.info("No aggregate data-quality report has been configured.")
        else:
            st.subheader("Read-only dataset quality summary")
            counts = report.get("input", report.get("counts", {}))
            if counts:
                st.bar_chart(counts)
            first, second = st.columns(2)
            first.metric("Conflicting unique URLs", report.get("conflicting_unique_urls", 0))
            second.metric(
                "Curated rows", report.get("written", report.get("unique_normalized_urls", 0))
            )
            st.caption("Raw URL rows, screenshots and paths are not browsed in this view.")
    else:
        data = api("GET", "/api/v1/predictions")
        st.write("Storage enabled:", data["storage_enabled"])
        st.dataframe(data["items"], use_container_width=True)
        confirmed = st.checkbox("Delete retained prediction metadata")
        if st.button("Delete metadata", disabled=not confirmed):
            st.write(api("DELETE", "/api/v1/predictions"))
except Exception:
    st.error(
        "The request or report could not be read. Check service availability, credentials, input and report configuration."
    )
st.caption("No telemetry. User-initiated submissions only. Models can make mistakes.")
