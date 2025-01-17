import re
import logging
import os
import cv2
import numpy as np
from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError

# Definizione delle costanti per i termini di ricerca
GAS_TERMS = [
    'gas', 'metano', 'gas naturale', 'distribuzione gas',
    'smc', 'standard m³', 'metri cubi', 'metro cubo',
    'consumo gas', 'lettura gas', 'fornitura gas',
    'materia gas', 'importi gas', 'consumi gas',
    'bolletta gas', 'riepilogo gas', 'spesa gas',
    'pcs', 'potere calorifico', 'coefficiente c',
    'punto di riconsegna', 'pdr', 'codice pdr',
    'remi', 'classe del misuratore', 'gas metano',
    'servizio gas', 'offerta gas', 'costo gas',
    'mc', 'm³', 'consumo mc', 'volume gas',
    'gas naturale', 'gas metano', 'fornitura gas'
]

ELECTRICITY_TERMS = [
    'energia elettrica', 'luce', 'elettricità',
    'kw', 'kwh', 'chilowattora', 'kilowattora',
    'consumo energia', 'potenza', 'energia attiva',
    'f1', 'f2', 'f3', 'fascia oraria', 'fasce',
    'lettura energia', 'potenza impegnata',
    'dispacciamento', 'consumo elettrico',
    'tariffa energia', 'spesa energia',
    'quota energia', 'energia reattiva',
    'servizio elettrico', 'contatore elettrico',
    'pod', 'codice pod', 'punto di prelievo',
    'potenza disponibile', 'tensione di alimentazione',
    'offerta luce', 'costo energia', 'consumo kwh',
    'energia', 'corrente elettrica', 'fornitura energia'
]

class OCRTimeoutError(Exception):
    pass

def process_image_with_timeout(image, timeout_seconds=15):
    """Process a single image with OCR and timeout"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(pytesseract.image_to_string, 
                                 image, 
                                 config=r'--oem 3 --psm 6 -l ita+eng')
        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError:
            logging.error(f"OCR timeout after {timeout_seconds} seconds")
            raise OCRTimeoutError(f"OCR processing timed out after {timeout_seconds} seconds")

def preprocess_image(image):
    """Pre-process the image to improve OCR accuracy with optimized settings"""
    logging.info("Starting optimized image pre-processing")
    try:
        # Convert PIL Image to cv2 format if needed
        if isinstance(image, Image.Image):
            image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply optimized preprocessing
        # 1. Enhanced contrast using CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        contrasted = clahe.apply(gray)

        # 2. Optimized thresholding
        _, binary = cv2.threshold(contrasted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Convert back to PIL Image
        enhanced_pil = Image.fromarray(binary)

        logging.info("Optimized image pre-processing completed")
        return enhanced_pil
    except Exception as e:
        logging.exception("Error during image pre-processing")
        raise RuntimeError(f"Failed to preprocess image: {str(e)}")

def extract_cost_per_unit(text):
    """Extract cost per unit from OCR text with improved pattern matching"""
    logging.debug("Extracting cost per unit from text")
    if not text:
        logging.error("Empty text provided to extract_cost_per_unit")
        return None

    # Enhanced patterns for cost extraction
    patterns = [
        # Standard format with currency
        r'(?:€|EUR)?\s*(\d+[.,]\d*)\s*(?:\/|\s+per\s+)?\s*(?:kw|kwh|m³|mc)',
        # Format without currency
        r'(\d+[.,]\d*)\s*(?:\/|\s+per\s+)?\s*(?:kw|kwh|m³|mc)',
        # Format with text description
        r'(?:costo|prezzo|tariffa)\s+(?:unitario|per)?\s+(?:€|EUR)?\s*(\d+[.,]\d*)',
        # Enel specific formats
        r'(?:prezzo energia|costo energia)\s*[F1-F3]?\s*(?:€|EUR)?\s*(\d+[.,]\d*)',
        r'(?:componente energia|quota energia)\s*(?:€|EUR)?\s*(\d+[.,]\d*)'
    ]

    try:
        # Log the text being analyzed for debugging
        logging.debug("Text to analyze for cost:")
        for line in text.split('\n'):
            if any(term in line.lower() for term in ['€', 'eur', 'costo', 'prezzo', 'tariffa', 'energia']):
                logging.debug(f"Potential cost line: {line}")

        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    cost = float(match.group(1).replace(',', '.').replace('€', ''))
                    if 0 < cost < 1000:  # Sanity check for reasonable cost range
                        logging.debug(f"Found valid cost: {cost} using pattern: {pattern}")
                        return cost
                    else:
                        logging.debug(f"Found cost outside reasonable range: {cost}")
                except ValueError:
                    continue

        logging.warning("No cost per unit found in text")
        return None
    except Exception as e:
        logging.exception(f"Error extracting cost per unit from text: {str(e)}")
        return None

def detect_bill_type(text):
    """Detect bill type from OCR text with improved keyword matching"""
    logging.debug("Starting bill type detection")
    if not text:
        logging.error("Empty text provided to detect_bill_type")
        return 'UNKNOWN'

    text = text.lower()
    logging.info("Full text content for analysis:")
    logging.info(text)

    # Terms that strongly indicate a mixed bill
    mix_patterns = [
        r'doppia\s+fornitura',
        r'dual\s+fuel',
        r'gas\s+[e&]\s+luce',
        r'luce\s+[e&]\s+gas',
        r'(?:bolletta|fattura)\s+(?:unica|combinata)',
        r'(?:enel|eni|a2a|iren|sorgenia)\s+gas\s+e\s+luce',
        r'riepilogo\s+(?:importi)?\s*gas.*riepilogo\s+(?:importi)?\s*(?:energia|luce|elettrica)',
        r'totale\s+gas.*totale\s+(?:energia|luce|elettrica)',
        r'spesa\s+(?:per|della)?\s*materia\s+gas.*spesa\s+(?:per|della)?\s*materia\s+(?:energia|luce|elettrica)',
        r'consumo\s+gas.*consumo\s+(?:energia|luce|elettrica)',
        r'(?:importo|spesa)\s+gas.*(?:importo|spesa)\s+(?:energia|luce|elettrica)',
        r'pdr.*pod',
        r'pod.*pdr'
    ]

    # Check for SMC measurements and PDR (strong indicators of gas)
    smc_patterns = [
        r'\d+(?:[.,]\d+)?\s*(?:smc|Smc|SMC)',  # Standard SMC format
        r'\d+(?:[.,]\d+)?\s*(?:m³|mc|metri cubi)',  # Cubic meters
        r'consumo\s+(?:effettivo|reale|fatturato|stimato)?\s*(?:di)?\s*gas',  # Gas consumption
        r'lettura\s+(?:attuale|precedente|gas)?\s*(?:mc|m³)',  # Gas meter reading
        r'pdr\s*[:\s]\s*\d+',  # PDR number
        r'punto\s+di\s+riconsegna\s*[:\s]\s*\d+',  # PDR full name
        r'codice\s+(?:pdr|cliente\s+gas)\s*[:\s]\s*\d+',  # PDR variations
        r'matricola\s+contatore\s+gas',  # Gas meter ID
        r'remi\s*[:\s]',  # REMI code
        r'(?:consumo|volume)\s+(?:annuo|mensile|effettivo)?\s*(?:gas|mc|m³)',  # Gas consumption variations
        r'spesa\s+(?:per|della)?\s*materia\s+gas'  # Gas cost section
    ]

    # Check for KWH measurements and POD (strong indicators of electricity)
    kwh_patterns = [
        r'\d+(?:[.,]\d+)?\s*(?:kwh|kw/h|chilowattora|kw)',  # Standard KWH format
        r'consumo\s+(?:effettivo|reale|fatturato|stimato)?\s*(?:di)?\s*energia',  # Energy consumption
        r'(?:f1|f2|f3|fascia)\s*[:\s]\s*\d+',  # Time-based consumption
        r'pod\s*[:\s]\s*[a-z0-9]+',  # POD number
        r'punto\s+di\s+prelievo\s*[:\s]\s*[a-z0-9]+',  # POD full name
        r'codice\s+(?:pod|cliente\s+energia)\s*[:\s]\s*[a-z0-9]+',  # POD variations
        r'potenza\s+(?:impegnata|disponibile|contrattuale)',  # Power terms
        r'(?:consumo|lettura)\s+(?:energia|elettrica|attiva)',  # Electricity consumption
        r'tensione\s+di\s+alimentazione',  # Voltage
        r'(?:contatore|matricola)\s+(?:elettrico|elettricità|energia)',  # Electricity meter
        r'spesa\s+(?:per|della)?\s*materia\s+(?:energia|elettrica)'  # Electricity cost section
    ]

    try:
        # Initialize pattern matches and term counts
        mix_matches = []
        gas_pattern_matches = []
        electricity_pattern_matches = []
        gas_terms_found = []
        electricity_terms_found = []

        # Check for mixed bill patterns first
        for pattern in mix_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                mix_matches.append(match.group(0))
                logging.info(f"Found mix pattern match: {match.group(0)}")

        # Check for SMC and gas-related patterns
        for pattern in smc_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                gas_pattern_matches.append(match.group(0))
                logging.info(f"Found gas pattern match: {match.group(0)}")

        # Check for KWH and electricity-related patterns
        for pattern in kwh_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                electricity_pattern_matches.append(match.group(0))
                logging.info(f"Found electricity pattern match: {match.group(0)}")

        # Count gas and electricity terms
        for term in GAS_TERMS:
            if term in text:
                gas_terms_found.append(term)

        for term in ELECTRICITY_TERMS:
            if term in text:
                electricity_terms_found.append(term)

        # Log all findings
        logging.info(f"Mix matches found: {mix_matches}")
        logging.info(f"Gas pattern matches: {gas_pattern_matches}")
        logging.info(f"Electricity pattern matches: {electricity_pattern_matches}")
        logging.info(f"Gas terms found: {gas_terms_found}")
        logging.info(f"Electricity terms found: {electricity_terms_found}")

        # Very relaxed decision logic with priority to mixed bills and sections
        # Check for explicit mix patterns first
        if mix_matches:
            logging.info("Detected type: MIX (explicit mix patterns found)")
            return 'MIX'
        # Check for sections mentioning both gas and electricity
        elif (len(gas_pattern_matches) > 0 and len(electricity_pattern_matches) > 0):
            logging.info("Detected type: MIX (found both gas and electricity patterns)")
            return 'MIX'
        # Check for terms from both categories
        elif (len(gas_terms_found) > 0 and len(electricity_terms_found) > 0):
            logging.info("Detected type: MIX (found both gas and electricity terms)")
            return 'MIX'
        # Check for the presence of both PDR and POD
        elif ('pdr' in text and 'pod' in text):
            logging.info("Detected type: MIX (found both PDR and POD)")
            return 'MIX'
        # If we have any gas patterns/terms but no electricity, it's GAS
        elif gas_pattern_matches or gas_terms_found:
            logging.info("Detected type: GAS (gas patterns or terms found)")
            return 'GAS'
        # If we have any electricity patterns/terms but no gas, it's LUCE
        elif electricity_pattern_matches or electricity_terms_found:
            logging.info("Detected type: LUCE (electricity patterns or terms found)")
            return 'LUCE'

        logging.warning("Could not determine bill type with confidence")
        return 'UNKNOWN'

    except Exception as e:
        logging.exception(f"Error in detect_bill_type: {str(e)}")
        # Instead of raising an error, return UNKNOWN to allow processing to continue
        return 'UNKNOWN'

def process_pages_parallel(images, max_workers=4):
    """Process multiple pages in parallel"""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i, image in enumerate(images, 1):
            # Resize image if too large
            width, height = image.size
            if width > 1000 or height > 1000:  # Reduced from 1200 to 1000
                ratio = min(1000/width, 1000/height)
                new_size = (int(width * ratio), int(height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            processed_image = preprocess_image(image)
            future = executor.submit(process_image_with_timeout, processed_image, 10)  # Reduced timeout
            futures.append(future)

        for i, future in enumerate(futures, 1):
            try:
                result = future.result()
                if result.strip():
                    results.append(result)
                    logging.info(f"Successfully processed page {i}")
                else:
                    logging.warning(f"No text extracted from page {i}")
            except Exception as e:
                logging.error(f"Error processing page {i}: {str(e)}")
                continue

    return results

def process_bill_ocr(file_path):
    """Process bill file with OCR using optimized settings"""
    try:
        logging.info(f"Starting optimized OCR processing for file: {file_path}")

        # Validate file
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        if not os.access(file_path, os.R_OK):
            logging.error(f"File is not readable: {file_path}")
            raise PermissionError(f"File is not readable: {file_path}")

        text = ""

        # Process PDF or image with optimized settings
        if file_path.lower().endswith('.pdf'):
            try:
                logging.info("Converting PDF to images with optimized settings")
                # Reduced DPI from 150 to 100 for faster processing
                images = convert_from_path(file_path, dpi=100)

                if not images:
                    logging.error("Failed to convert PDF to images")
                    raise ValueError("Failed to convert PDF to images")

                logging.info(f"Processing {len(images)} pages in parallel")
                text_parts = process_pages_parallel(images)
                text = "\n".join(text_parts)

            except TimeoutError:
                logging.error("PDF processing timeout")
                raise OCRTimeoutError("PDF processing timed out")
            except Exception as e:
                logging.exception("Error processing PDF")
                raise RuntimeError(f"PDF processing failed: {str(e)}")

        else:
            try:
                logging.info("Processing image file with optimized settings")
                image = Image.open(file_path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')

                # Resize with optimized dimensions
                width, height = image.size
                if width > 1000 or height > 1000:  # Reduced from 1200 to 1000
                    ratio = min(1000/width, 1000/height)
                    new_size = (int(width * ratio), int(height * ratio))
                    image = image.resize(new_size, Image.Resampling.LANCZOS)

                processed_image = preprocess_image(image)
                text = process_image_with_timeout(processed_image, timeout_seconds=10)  # Reduced timeout

            except TimeoutError:
                logging.error("Image processing timeout")
                raise OCRTimeoutError("Image processing timed out")
            except Exception as e:
                logging.exception("Error processing image")
                raise RuntimeError(f"Image processing failed: {str(e)}")

        if not text.strip():
            logging.error("No text extracted from file")
            raise ValueError("No text could be extracted from the file")

        logging.info("Extracted text content:")
        logging.info(text)

        # Extract bill type and cost per unit
        logging.info("Starting bill type detection")
        bill_type = detect_bill_type(text)
        logging.info(f"Detected bill type: {bill_type}")

        if bill_type == 'UNKNOWN':
            logging.warning("Could not determine bill type")
            raise ValueError("Could not determine bill type")

        logging.info("Starting cost extraction")
        cost_per_unit = extract_cost_per_unit(text)
        logging.info(f"Extracted cost per unit: {cost_per_unit}")

        return cost_per_unit, bill_type

    except OCRTimeoutError as e:
        logging.error(f"OCR timeout: {str(e)}")
        raise OCRTimeoutError(f"L'elaborazione OCR è durata troppo tempo: {str(e)}")
    except Exception as e:
        logging.exception(f"Unexpected error during OCR processing: {str(e)}")
        raise