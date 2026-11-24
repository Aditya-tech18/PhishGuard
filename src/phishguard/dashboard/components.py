"""Explicit model uncertainty and readable, non-causal signal names."""

LABELS = {
    "url_length": "URL length",
    "host_length": "Hostname length",
    "path_length": "Path length",
    "query_length": "Query length",
    "host_labels": "Hostname structure",
    "digit_ratio": "Digits in URL",
    "host_digit_ratio": "Digits in hostname",
    "hyphens": "Hyphen pattern",
    "dots": "Dot pattern",
    "ats": "At-sign pattern",
    "percent": "Encoded characters",
    "query_params": "Query structure",
    "slashes": "Path separators",
    "entropy": "URL character variation",
    "host_entropy": "Hostname character variation",
    "https": "HTTP/HTTPS scheme",
    "ip_host": "IP address hostname",
    "punycode": "Internationalized hostname",
    "suspicious_tokens": "Account/security words",
    "encoded_slashes": "Encoded path separators",
    "port_nonstandard": "Nonstandard port",
    "path_depth": "Path depth",
    "equals": "Equals-sign pattern",
    "repeated_chars": "Repeated characters",
}


def render_prediction(st, result):
    st.metric("Estimated phishing probability", f"{result['probability']:.1%}")
    if result["verdict"] == "phishing":
        st.warning("The model flags this input as suspicious. Avoid entering credentials.")
    else:
        st.info("The model assigns low risk. This does not establish that the site is safe.")
    st.caption(result["disclaimer"])
    st.caption("Model version: " + result["model_version"])
    signals = [LABELS.get(name, name.replace("_", " ")) for name in result["reasons"]]
    if signals:
        st.write("Model signals:", ", ".join(signals))
        st.caption(
            "Signals describe model inputs or decision paths; they do not establish cause or site intent."
        )


def render_performance(st, report):
    from phishguard.dashboard.reports import performance_table

    metrics = report.get("test", report.get("metrics", {}))
    if not metrics:
        st.info("This report does not contain labeled evaluation metrics.")
        return
    columns = st.columns(3)
    for column, key in zip(columns, ["precision", "recall", "f1"]):
        value = metrics.get(key)
        column.metric(key.title(), f"{value:.2%}" if value is not None else "Unavailable")
    st.caption(
        f"Held-out rows: {metrics.get('rows', 0):,}. These results describe this dataset only."
    )
    st.write("Selected model:", report.get("winner", report.get("algorithm", "Logistic baseline")))
    table = performance_table(report)
    if table:
        st.subheader("Validation-only comparison")
        st.dataframe(table, use_container_width=True, hide_index=True)
    if "confusion" in metrics:
        st.subheader("Held-out confusion counts")
        st.bar_chart(metrics["confusion"])
    calibration = report.get("calibration", {})
    if calibration.get("bins"):
        st.subheader("Calibration by score range")
        st.dataframe(calibration["bins"], use_container_width=True, hide_index=True)
    if report.get("uncertainty"):
        st.subheader("Domain-bootstrap uncertainty")
        st.json(report["uncertainty"]["intervals"])
    st.warning("Evaluation is not a guarantee of future performance or safety.")
