from pathlib import Path

from flask import Flask, send_from_directory

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static_dashboard"

app = Flask(__name__, static_folder=None)
server = app


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:filename>")
def assets(filename: str):
    return send_from_directory(STATIC_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=8050)
