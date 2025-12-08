import os
import uuid
import shutil
import subprocess
from flask import Flask, request, send_file, jsonify, abort
from pathlib import Path
import tempfile

app = Flask(__name__)

# Config: tune these default limits
DEFAULT_DEPTH = 4         # recursion depth -l
DEFAULT_WAIT = 0.5        # wait between requests in seconds
MAX_DURATION = 3000        # max seconds to allow wget to run (safety)
MAX_DISK_BYTES = 500_000_000  # 500 MB per job (safety)

def run_wget(target_url, outdir, depth=DEFAULT_DEPTH, wait=DEFAULT_WAIT, obey_robots=False):
    # build wget command
    # -E --adjust-extension
    # -k --convert-links
    # -p --page-requisites
    # -r --recursive -l depth
    # --no-parent
    # -e robots=off or on
    # --wait
    # --restrict-file-names=windows makes safe filenames
    robots_setting = "on" if obey_robots else "off"
    cmd = [
        "wget",
        "--recursive",
        f"--level={depth}",
        "--no-parent",
        "--page-requisites",
        "--convert-links",
        "--adjust-extension",
        "--restrict-file-names=windows",
        f"--wait={wait}",
        f"-e", f"robots={robots_setting}",
        "--no-verbose",
        "--span-hosts", # optionally allow subdomains/resources if needed
        "--directory-prefix", str(outdir),
        target_url
    ]
    # Run with timeout
    subprocess.run(cmd, check=True, timeout=MAX_DURATION, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout.decode())

def dir_size_bytes(path: Path):
    total = 0
    for p in path.rglob('*'):
        if p.is_file():
            total += p.stat().st_size
    return total

@app.route("/download", methods=["POST"])
def download_site():
    data = request.get_json(force=True)
    if not data or "url" not in data:
        return jsonify({"error": "send JSON {\"url\":\"https://example.com\", \"depth\":2, \"wait\":0.5, \"obey_robots\":false}"}), 400

    url = data["url"]
    depth = int(data.get("depth", DEFAULT_DEPTH))
    wait = float(data.get("wait", DEFAULT_WAIT))
    obey_robots = bool(data.get("obey_robots", False))

    # quick validation
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"error": "url must start with http:// or https://"}), 400

    job_id = uuid.uuid4().hex
    tmpdir = Path(tempfile.gettempdir()) / f"site_snap_{job_id}"
    try:
        tmpdir.mkdir(parents=True, exist_ok=False)
    except Exception as e:
        return jsonify({"error": f"failed to create tmpdir: {e}"}), 500

    try:
        # run wget
        run_wget(url, tmpdir, depth=depth, wait=wait, obey_robots=obey_robots)

        # safety check: don't zip huge things
        size = dir_size_bytes(tmpdir)
        if size > MAX_DISK_BYTES:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return jsonify({"error": "download exceeded size limit"}), 413

        # zip it
        zip_path = tmpdir.with_suffix(".zip")
        shutil.make_archive(base_name=str(zip_path.with_suffix('')), format='zip', root_dir=str(tmpdir))

        # return zip file
        return send_file(str(zip_path), as_attachment=True, download_name=f"site_snapshot_{job_id}.zip")

    except subprocess.TimeoutExpired:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return jsonify({"error": "wget timed out"}), 504
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return jsonify({"error": f"wget failed: {e}"}), 500
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return jsonify({"error": f"unexpected error: {e}"}), 500
    finally:
        # optional: keep or remove tmpdir after returning file
        # we remove to avoid filling disk
        try:
            if tmpdir.exists():
                shutil.rmtree(tmpdir, ignore_errors=True)
            zipfile = tmpdir.with_suffix(".zip")
            if zipfile.exists():
                pass  # we already served it; optionally remove
        except Exception:
            pass

if __name__ == "__main__":
import os
port = int(os.environ.get("PORT", 8080))
app.run(host="0.0.0.0", port=port)
