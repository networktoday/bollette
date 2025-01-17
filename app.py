import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import logging
import uuid
from werkzeug.utils import secure_filename
from utils import process_bill_ocr

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

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
app.config["UPLOAD_FOLDER"] = "uploads"

# Ensure upload directory exists
if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])

db.init_app(app)

def save_file(file):
    """Save uploaded file and return the file path"""
    try:
        if file and file.filename:
            # Generate unique filename to prevent collisions
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
            file.save(file_path)
            logging.debug(f"File saved successfully at: {file_path}")
            return file_path
        logging.error("Invalid file object received")
        return None
    except Exception as e:
        logging.error(f"Error saving file: {str(e)}")
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        logging.info("Upload request received")

        # Validate request data
        if not request.form:
            logging.error("No form data received")
            return jsonify({"error": "No form data received"}), 400

        phone = request.form.get("phone")
        if not phone:
            logging.error("No phone number received")
            return jsonify({"error": "No phone number received"}), 400

        files = request.files.getlist("files[]")
        logging.info(f"Received {len(files)} files")

        if not files:
            logging.error("No files received")
            return jsonify({"error": "No files received"}), 400

        # Process each file
        saved_bills = []
        for i, file in enumerate(files):
            try:
                if not file or not file.filename:
                    logging.error(f"Invalid file at index {i}")
                    continue

                logging.info(f"Processing file {i+1}/{len(files)}: {file.filename}")

                # Save the file
                file_path = save_file(file)
                if not file_path:
                    logging.error(f"Failed to save file: {file.filename}")
                    continue

                logging.info(f"File saved at: {file_path}")

                # Process with OCR
                cost_per_unit, detected_type = process_bill_ocr(file_path)
                logging.info(f"OCR results - Cost per unit: {cost_per_unit}, Detected type: {detected_type}")

                if detected_type == 'UNKNOWN':
                    logging.warning(f"Could not detect bill type for file: {file.filename}")
                    continue

                # Create new bill record
                bill = models.Bill(
                    phone=phone,
                    bill_type=detected_type,
                    file_path=file_path,
                    cost_per_unit=cost_per_unit
                )
                db.session.add(bill)
                saved_bills.append(bill)
                logging.info(f"Bill record created for file: {file.filename}")

            except Exception as e:
                logging.error(f"Error processing file {file.filename if file else 'unknown'}: {str(e)}")
                continue

        if not saved_bills:
            logging.error("No bills were successfully processed")
            return jsonify({"error": "Nessuna bolletta è stata elaborata correttamente"}), 400

        # Commit all bills to database
        logging.info("Committing bills to database")
        try:
            db.session.commit()
            logging.info(f"Successfully saved {len(saved_bills)} bills to database")
        except Exception as e:
            logging.error(f"Database commit error: {str(e)}")
            db.session.rollback()
            return jsonify({"error": "Errore nel salvare le bollette nel database"}), 500

        # Return success response with bill details
        response_data = {
            "success": True,
            "message": "Bollette caricate con successo",
            "bills": [bill.to_dict() for bill in saved_bills]
        }
        logging.info("Upload completed successfully")
        return jsonify(response_data)

    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return jsonify({"error": "Si è verificato un errore durante il caricamento"}), 500

with app.app_context():
    import models
    db.create_all()