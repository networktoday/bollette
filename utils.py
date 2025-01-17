import re
import logging
from PIL import Image
import pytesseract
from pdf2image import convert_from_path

def extract_cost_per_unit(text):
    """Extract cost per unit from OCR text"""
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
    text = text.lower()

    # Define Italian and English terms for each type
    gas_terms = [
        'gas', 'cubic meter', 'm³', 'mc', 'metano', 'consumo gas',
        'lettura gas', 'fornitura gas', 'gas naturale'
    ]
    electricity_terms = [
        'electricity', 'electric', 'kw', 'kwh', 'kilowatt',
        'energia elettrica', 'consumo energia', 'luce', 'elettricità',
        'potenza', 'lettura energia', 'energia', 'corrente elettrica'
    ]

    # Count occurrences of terms
    gas_count = sum(1 for term in gas_terms if term in text)
    electricity_count = sum(1 for term in electricity_terms if term in text)

    logging.debug(f"Bill detection - Gas terms found: {gas_count}, Electricity terms found: {electricity_count}")

    # If we find any combination of gas and electricity terms, it's a MIX bill
    if gas_count > 0 and electricity_count > 0:
        logging.debug("Bill type detected: MIX (contains both gas and electricity terms)")
        return 'MIX'
    elif gas_count > 0:
        logging.debug("Bill type detected: GAS")
        return 'GAS'
    elif electricity_count > 0:
        logging.debug("Bill type detected: LUCE")
        return 'LUCE'

    logging.debug("Bill type detected: UNKNOWN")
    return 'UNKNOWN'

def process_bill_ocr(file_path):
    """Process bill file with OCR and extract information"""
    try:
        if file_path.lower().endswith('.pdf'):
            # Convert all pages of PDF to images
            images = convert_from_path(file_path)
            if not images:
                return None, None

            # Process each page and combine the text
            full_text = ""
            for image in images:
                text = pytesseract.image_to_string(image, lang='ita+eng')
                full_text += text + "\n"
        else:
            # Open image file directly
            image = Image.open(file_path)
            full_text = pytesseract.image_to_string(image, lang='ita+eng')

        logging.debug(f"OCR Text extracted: {full_text[:200]}...")  # Log first 200 chars

        # Extract information
        cost_per_unit = extract_cost_per_unit(full_text)
        bill_type = detect_bill_type(full_text)

        return cost_per_unit, bill_type
    except Exception as e:
        logging.error(f"OCR Processing error: {str(e)}")
        return None, None