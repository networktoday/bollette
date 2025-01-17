import re
import logging
from PIL import Image
import pytesseract
from pdf2image import convert_from_path

def extract_cost_per_unit(text):
    """Extract cost per unit from OCR text"""
    logging.debug("Extracting cost per unit from text")
    # Regular expressions for cost extraction
    kw_pattern = r'(\$?\d+[.,]?\d*)\s*(?:\/|\s+per\s+)?\s*(?:kw|kwh)'
    cubic_meter_pattern = r'(\$?\d+[.,]?\d*)\s*(?:\/|\s+per\s+)?\s*(?:m³|mc)'

    # Try to find cost per KW
    kw_match = re.search(kw_pattern, text, re.IGNORECASE)
    if kw_match:
        return float(kw_match.group(1).replace(',', '.').replace('$', ''))

    # Try to find cost per cubic meter
    cubic_match = re.search(cubic_meter_pattern, text, re.IGNORECASE)
    if cubic_match:
        return float(cubic_match.group(1).replace(',', '.').replace('$', ''))

    return None

def detect_bill_type(text):
    """Detect bill type from OCR text"""
    logging.debug("Detecting bill type from text")
    text = text.lower()

    # Define Italian and English terms for each type
    gas_terms = ['gas', 'metano', 'consumo gas', 'lettura gas']
    electricity_terms = ['energia elettrica', 'luce', 'elettricità', 'kw', 'kwh']

    # Count occurrences of terms
    gas_count = sum(1 for term in gas_terms if term in text)
    electricity_count = sum(1 for term in electricity_terms if term in text)

    if gas_count > 0 and electricity_count > 0:
        return 'MIX'
    elif gas_count > 0:
        return 'GAS'
    elif electricity_count > 0:
        return 'LUCE'

    return 'UNKNOWN'

def process_bill_ocr(file_path):
    """Process bill file with OCR and extract information"""
    try:
        logging.debug(f"Starting OCR processing for file: {file_path}")

        if file_path.lower().endswith('.pdf'):
            # Convert first page of PDF to image
            logging.debug("Converting PDF to image")
            images = convert_from_path(file_path, first_page=1, last_page=1)
            if not images:
                logging.error("Failed to convert PDF to image")
                return None, None

            image = images[0]
        else:
            # Open image file directly
            logging.debug("Opening image file")
            image = Image.open(file_path)

        # Configure pytesseract for better accuracy with minimal settings
        custom_config = r'--oem 3 --psm 6'
        logging.debug("Performing OCR on image")
        text = pytesseract.image_to_string(image, config=custom_config)

        logging.debug(f"OCR text extracted (first 200 chars): {text[:200]}")

        # Extract information
        cost_per_unit = extract_cost_per_unit(text)
        bill_type = detect_bill_type(text)

        logging.debug(f"Extracted cost per unit: {cost_per_unit}, bill type: {bill_type}")
        return cost_per_unit, bill_type

    except Exception as e:
        logging.error(f"OCR Processing error: {str(e)}")
        return None, None