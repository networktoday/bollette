import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import logging
import uuid
from werkzeug.utils import secure_filename
from utils import process_bill_ocr

# Configure logging with more details
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)

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
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max-size per file
app.config["UPLOAD_FOLDER"] = "uploads"

# Ensure upload directory exists with correct permissions
uploads_dir = os.path.join(os.getcwd(), app.config["UPLOAD_FOLDER"])
if not os.path.exists(uploads_dir):
    try:
        os.makedirs(uploads_dir, mode=0o755)
        logging.info(f"Created uploads directory at: {uploads_dir}")
    except Exception as e:
        logging.error(f"Failed to create uploads directory: {str(e)}")

db.init_app(app)

def save_file(file):
    """Save uploaded file and return the file path"""
    try:
        if not file or not file.filename:
            logging.error("Invalid file object received")
            return None

        # Generate unique filename to prevent collisions
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        logging.debug(f"Attempting to save file to: {file_path}")

        # Check if the directory is writable
        if not os.access(os.path.dirname(file_path), os.W_OK):
            logging.error(f"Upload directory is not writable: {os.path.dirname(file_path)}")
            return None

        # Save the file
        try:
            file.save(file_path)
            logging.debug(f"File saved successfully")
        except Exception as e:
            logging.error(f"Error saving file: {str(e)}")
            return None

        # Verify file was saved and is readable
        if not os.path.exists(file_path):
            logging.error(f"File not found after save attempt: {file_path}")
            return None

        if not os.access(file_path, os.R_OK):
            logging.error(f"Saved file is not readable: {file_path}")
            return None

        file_size = os.path.getsize(file_path)
        logging.info(f"File saved successfully at: {file_path}, size: {file_size} bytes")
        return file_path
    except Exception as e:
        logging.exception(f"Error saving file {file.filename if file else 'unknown'}: {str(e)}")
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        logging.info("Upload request received")

        # Log request details
        logging.debug(f"Request form data: {request.form}")
        logging.debug(f"Files received: {[f.filename for f in request.files.getlist('files[]')]}")

        # Validate phone number
        phone = request.form.get("phone")
        if not phone:
            logging.error("No phone number received")
            return jsonify({"error": "Inserisci un numero di telefono"}), 400

        # Validate files
        files = request.files.getlist("files[]")
        if not files:
            logging.error("No files received")
            return jsonify({"error": "Seleziona almeno un file"}), 400

        logging.info(f"Processing {len(files)} files")

        # Process each file
        saved_bills = []
        for i, file in enumerate(files):
            logging.info(f"Processing file {i+1}/{len(files)}: {file.filename}")

            try:
                if not file or not file.filename:
                    logging.error(f"Invalid file at index {i}")
                    continue

                # Save the file
                file_path = save_file(file)
                if not file_path:
                    logging.error(f"Failed to save file: {file.filename}")
                    continue

                # Process with OCR
                logging.info(f"Starting OCR processing for: {file_path}")
                try:
                    cost_per_unit, detected_type = process_bill_ocr(file_path)
                    logging.info(f"OCR results - Cost per unit: {cost_per_unit}, Type: {detected_type}")
                except Exception as ocr_error:
                    logging.exception("OCR processing failed")
                    continue

                if detected_type == 'UNKNOWN':
                    logging.warning(f"Could not detect bill type for file: {file.filename}")
                    continue

                # Create new bill record
                try:
                    bill = models.Bill(
                        phone=phone,
                        bill_type=detected_type,
                        file_path=file_path,
                        cost_per_unit=cost_per_unit
                    )
                    db.session.add(bill)
                    saved_bills.append(bill)
                    logging.info(f"Bill record created for file: {file.filename}")
                except Exception as db_error:
                    logging.exception("Failed to create bill record")
                    continue

            except Exception as e:
                logging.exception(f"Error processing file {file.filename if file else 'unknown'}")
                continue

        if not saved_bills:
            logging.error("No bills were successfully processed")
            return jsonify({"error": "Non è stato possibile elaborare nessuna bolletta"}), 400

        # Commit all bills to database
        logging.info("Committing bills to database")
        try:
            db.session.commit()
            logging.info(f"Successfully saved {len(saved_bills)} bills to database")
        except Exception as e:
            logging.exception("Database commit error")
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
        logging.exception("Unexpected error during upload")
        return jsonify({"error": f"Errore durante il caricamento: {str(e)}"}), 500

with app.app_context():
    import models
    db.create_all()