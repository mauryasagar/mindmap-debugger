"""
MindMap Debugger — web app.
"""

from flask import Flask, request, jsonify, send_from_directory
from extract import extract_consensus
from detect import build_findings
from cedar_gate import apply_gate

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return send_from_directory("static", "landing.html")


@app.route("/landing.html")
def landing():
    return send_from_directory("static", "landing.html")


@app.route("/dashboard.html")
def dashboard():
    return send_from_directory("static", "dashboard.html")


@app.route("/style.css")
def style():
    return send_from_directory("static", "style.css")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    text = (data or {}).get("text", "").strip()

    if not text:
        return jsonify({"error": "Please paste some text to analyze."}), 400

    try:
        extraction = extract_consensus(text)
        findings = build_findings(extraction)
        gated = apply_gate(findings)
        return jsonify({
            "findings": gated,
            "propositions": extraction["propositions"],
            "relations": extraction["relations"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Starting MindMap Debugger...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, use_reloader=False, port=5000)