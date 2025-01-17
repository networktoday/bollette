import re
import logging
from PIL import Image
import pytesseract
from pdf2image import convert_from_path

def extract_cost_per_unit(text):
    """Extract cost per unit from OCR text"""
    # Regular expressions for cost extraction
    kw_pattern = r'(\$?\d+\.?\d*)\s*(?:\/|\s+per\s+)?\s*kw'
    cubic_meter_pattern = r'(\$?\d+\.?\d*)\s*(?:\/|\s+per\s+)?\s*m³'

    # Try to find cost per KW
    kw_match = re.search(kw_pattern, text, re.IGNORECASE)
    if kw_match:
        return float(kw_match.group(1).replace('$', ''))

    # Try to find cost per cubic meter
    cubic_match = re.search(cubic_meter_pattern, text, re.IGNORECASE)
    if cubic_match:
        return float(cubic_match.group(1).replace('$', ''))

    return None

def detect_bill_type(text):
    """Detect bill type from OCR text"""
    text = text.lower()
    gas_terms = len(re.findall(r'gas|cubic meter|m³', text))
    electricity_terms = len(re.findall(r'electricity|electric|kw|kilowatt', text))

    if gas_terms > 0 and electricity_terms > 0:
        return 'MIX'
    elif gas_terms > 0:
        return 'GAS'
    elif electricity_terms > 0:
        return 'LUCE'  # Changed from 'LIGHT' to 'LUCE'
    return 'UNKNOWN'

def process_bill_ocr(file_path):
    """Process bill file with OCR and extract information"""
    try:
        if file_path.lower().endswith('.pdf'):
            # Convert first page of PDF to image
            images = convert_from_path(file_path, first_page=1, last_page=1)
            if not images:
                return None, None
            image = images[0]
        else:
            # Open image file directly
            image = Image.open(file_path)

        # Perform OCR
        text = pytesseract.image_to_string(image)
        logging.debug(f"OCR Text extracted: {text[:200]}...")  # Log first 200 chars

        # Extract information
        cost_per_unit = extract_cost_per_unit(text)
        bill_type = detect_bill_type(text)

        return cost_per_unit, bill_type
    except Exception as e:
        logging.error(f"OCR Processing error: {str(e)}")
        return None, None