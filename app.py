import os
import uuid
import threading
import subprocess
import shutil
from flask import Flask, request, send_file, jsonify

app = Flask(__name__)

JOBS = {}  # job_id -> status dict like {status, path}


def run_wget(job_id, url, depth):
    try:
        JOBS[job_id]["status"] = "running"

        folder = f"jobs/{job_id}"
        os.makedirs(folder, exist_ok=True)

        cmd = [
            "wget",
            "--recursive",
            "--no-parent",
            f"--level={depth}",
            "--convert-links",
            "--adjust-extension",
            "--page-requisites",
            "--reject-regex=logout",
            "--restrict-file-names=windows",
            "--directory-prefix", folder,
            url
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        zip_path = f"{folder}.zip"
        shutil.make_archive(folder, "zip", folder)

        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["zip_path"] = zip_path

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = str(e)


@app.route("/start-job", methods=["POST"])
def start_job():
    data = request.json
    url = data.get("url")
    depth = int(data.get("depth", 2))

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued"}

    thread = threading.Thread(target=run_wget, args=(job_id, url, depth))
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/status")
def status():
    job_id = request.args.get("id")
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    return jsonify(JOBS[job_id])


@app.route("/download")
def download():
    job_id = request.args.get("id")
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404

    info = JOBS[job_id]
    if info["status"] != "done":
        return jsonify({"error": "not ready"}), 400

    return send_file(info["zip_path"], as_attachment=True)


@app.route("/")
def home():
    return "The backend is running."
