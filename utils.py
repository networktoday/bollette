import re
import logging
import os
from PIL import Image
import pytesseract
from pdf2image import convert_from_path

def extract_cost_per_unit(text):
    """Extract cost per unit from OCR text"""
    logging.debug("Extracting cost per unit from text")
    if not text:
        logging.error("Empty text provided to extract_cost_per_unit")
        return None

    # Regular expressions for cost extraction
    kw_pattern = r'(\d+[.,]\d*)\s*(?:\/|\s+per\s+)?\s*(?:kw|kwh)'
    cubic_meter_pattern = r'(\d+[.,]\d*)\s*(?:\/|\s+per\s+)?\s*(?:m³|mc)'

    try:
        # Try to find cost per KW
        kw_match = re.search(kw_pattern, text, re.IGNORECASE)
        if kw_match:
            cost = float(kw_match.group(1).replace(',', '.'))
            logging.debug(f"Found kW cost: {cost}")
            return cost

        # Try to find cost per cubic meter
        cubic_match = re.search(cubic_meter_pattern, text, re.IGNORECASE)
        if cubic_match:
            cost = float(cubic_match.group(1).replace(',', '.'))
            logging.debug(f"Found cubic meter cost: {cost}")
            return cost

        logging.warning("No cost per unit found in text")
        logging.debug(f"Text analyzed: {text[:200]}...")  # Log first 200 chars
        return None
    except Exception as e:
        logging.exception(f"Error extracting cost per unit from text: {str(e)}")
        return None

def detect_bill_type(text):
    """Detect bill type from OCR text"""
    logging.debug("Detecting bill type from text")
    if not text:
        logging.error("Empty text provided to detect_bill_type")
        return 'UNKNOWN'

    text = text.lower()

    # Define Italian and English terms for each type
    gas_terms = [
        'gas', 'consumo gas', 'lettura gas', 'fornitura gas',
        'gas naturale', 'metano', 'm³', 'mc', 'metri cubi'
    ]
    electricity_terms = [
        'energia elettrica', 'consumo energia', 'luce', 'elettricità',
        'potenza', 'lettura energia', 'energia', 'corrente elettrica',
        'kw', 'kwh', 'kilowatt'
    ]

    # Count occurrences of terms
    gas_count = sum(1 for term in gas_terms if term in text)
    electricity_count = sum(1 for term in electricity_terms if term in text)

    logging.debug(f"Gas terms found: {gas_count}, terms: {[t for t in gas_terms if t in text]}")
    logging.debug(f"Electricity terms found: {electricity_count}, terms: {[t for t in electricity_terms if t in text]}")

    if gas_count > 0 and electricity_count > 0:
        logging.info("Detected bill type: MIX (both gas and electricity terms found)")
        return 'MIX'
    elif gas_count > 0:
        logging.info("Detected bill type: GAS")
        return 'GAS'
    elif electricity_count > 0:
        logging.info("Detected bill type: LUCE")
        return 'LUCE'

    logging.warning("Could not determine bill type")
    logging.debug(f"Text analyzed: {text[:200]}...")  # Log first 200 chars
    return 'UNKNOWN'

def process_bill_ocr(file_path):
    """Process bill file with OCR and extract information"""
    try:
        logging.info(f"Starting OCR processing for file: {file_path}")

        # Check if file exists and is readable
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return None, None

        if not os.access(file_path, os.R_OK):
            logging.error(f"File is not readable: {file_path}")
            return None, None

        # Get file size
        file_size = os.path.getsize(file_path)
        logging.debug(f"Processing file of size: {file_size} bytes")

        # Process PDF or image
        if file_path.lower().endswith('.pdf'):
            try:
                logging.info("Converting PDF to image")
                # Use higher DPI for better quality
                images = convert_from_path(file_path, dpi=300, first_page=1, last_page=1)
                if not images:
                    logging.error("Failed to convert PDF to image")
                    return None, None
                image = images[0]
                logging.info("PDF converted to image successfully")
            except Exception as e:
                logging.exception("Error converting PDF to image")
                return None, None
        else:
            try:
                logging.info("Opening image file")
                image = Image.open(file_path)
                # Convert to RGB if needed
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                logging.info(f"Image opened successfully: size={image.size}, mode={image.mode}")
            except Exception as e:
                logging.exception("Error opening image file")
                return None, None

        # Configure pytesseract for better accuracy
        try:
            # Configure tesseract to use Italian language
            custom_config = r'--oem 3 --psm 6'
            logging.info("Starting OCR text extraction")

            # Get tesseract version for debugging
            try:
                version = pytesseract.get_tesseract_version()
                logging.info(f"Tesseract version: {version}")
            except:
                logging.warning("Could not get Tesseract version")

            # Log available languages
            try:
                langs = pytesseract.get_languages()
                logging.info(f"Available languages: {langs}")
            except:
                logging.warning("Could not get available languages")

            # Try with Italian first, if it fails try with just English
            try:
                text = pytesseract.image_to_string(image, lang='ita', config=custom_config)
            except:
                logging.warning("Failed with Italian language, trying English")
                text = pytesseract.image_to_string(image, config=custom_config)

            if not text.strip():
                logging.error("OCR produced no text")
                return None, None

            text_length = len(text)
            logging.info(f"OCR completed, extracted {text_length} characters")
            logging.debug(f"First 200 characters of extracted text: {text[:200]}")

        except Exception as e:
            logging.exception("Error during OCR processing")
            return None, None

        # Extract information
        try:
            cost_per_unit = extract_cost_per_unit(text)
            bill_type = detect_bill_type(text)

            logging.info(f"Information extracted - Cost per unit: {cost_per_unit}, Bill type: {bill_type}")
            return cost_per_unit, bill_type

        except Exception as e:
            logging.exception("Error extracting information from OCR text")
            return None, None

    except Exception as e:
        logging.exception(f"Unexpected error during OCR processing")
        return None, None