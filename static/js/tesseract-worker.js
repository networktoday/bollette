// Configure Tesseract.js worker for optimal OCR performance
importScripts('https://unpkg.com/tesseract.js@v2.1.0/dist/worker.min.js');

let recognizeText = async (image) => {
    const worker = new Tesseract.Worker({
        workerPath: 'https://unpkg.com/tesseract.js@v2.1.0/dist/worker.min.js',
        langPath: 'https://tessdata.projectnaptha.com/4.0.0',
        corePath: 'https://unpkg.com/tesseract.js-core@v2.1.0/tesseract-core.wasm.js',
    });

    try {
        // Load English language data
        await worker.load();
        await worker.loadLanguage('eng');
        await worker.initialize('eng');

        // Configure recognition settings for better accuracy with utility bills
        await worker.setParameters({
            tessedit_char_whitelist: '0123456789.,ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz$/kWm³', 
            preserve_interword_spaces: '1',
        });

        // Perform OCR
        const { data: { text, confidence } } = await worker.recognize(image);

        // Extract utility bill specific information
        const result = {
            text: text,
            confidence: confidence,
            costPerUnit: extractCostPerUnit(text),
            billType: detectBillType(text)
        };

        await worker.terminate();
        return result;

    } catch (error) {
        console.error('OCR Processing Error:', error);
        if (worker) {
            await worker.terminate();
        }
        throw error;
    }
};

function extractCostPerUnit(text) {
    // Regular expressions for cost extraction
    const kwPattern = /(\$?\d+\.?\d*)\s*(?:\/|\s+per\s+)?\s*kw/i;
    const cubicMeterPattern = /(\$?\d+\.?\d*)\s*(?:\/|\s+per\s+)?\s*m³/i;

    let cost = null;
    
    // Try to find cost per KW
    const kwMatch = text.match(kwPattern);
    if (kwMatch) {
        cost = parseFloat(kwMatch[1].replace('$', ''));
    }

    // Try to find cost per cubic meter
    const cubicMatch = text.match(cubicMeterPattern);
    if (cubicMatch) {
        cost = parseFloat(cubicMatch[1].replace('$', ''));
    }

    return cost;
}

function detectBillType(text) {
    text = text.toLowerCase();
    
    // Count occurrences of key terms
    const gasTerms = (text.match(/gas|cubic meter|m³/g) || []).length;
    const electricityTerms = (text.match(/electricity|electric|kw|kilowatt/g) || []).length;

    if (gasTerms > 0 && electricityTerms > 0) {
        return 'MIX';
    } else if (gasTerms > 0) {
        return 'GAS';
    } else if (electricityTerms > 0) {
        return 'LIGHT';
    }
    
    return 'UNKNOWN';
}

// Listen for messages from the main thread
self.addEventListener('message', async (e) => {
    try {
        const result = await recognizeText(e.data.image);
        self.postMessage({
            status: 'done',
            result: result
        });
    } catch (error) {
        self.postMessage({
            status: 'error',
            error: error.message
        });
    }
});
