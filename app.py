import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import logging
import json

logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024 * 10  # 160MB max-size (10 files * 16MB)

db.init_app(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        phone = request.form.get("phone")
        bill_types = json.loads(request.form.get("billTypes", "[]"))
        files = request.files.getlist("files[]")

        if not phone or not files:
            return jsonify({"error": "Missing required fields"}), 400

        if len(files) != len(bill_types):
            return jsonify({"error": "Mismatch between files and bill types"}), 400

        # Process each file
        for file, bill_type in zip(files, bill_types):
            if file:
                # Here you would save the file and process it
                # In a real implementation, we'd save each file and process it
                logging.debug(f"Processing file: {file.filename}, type: {bill_type}")

        return jsonify({
            "success": True,
            "message": "Bills uploaded successfully"
        })
    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return jsonify({"error": "Upload failed"}), 500

with app.app_context():
    import models
    db.create_all()