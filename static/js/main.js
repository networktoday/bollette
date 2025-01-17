document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const preview = document.getElementById('preview');
    const form = document.getElementById('upload-form');
    const phoneInput = document.getElementById('phone');

    // Drag and drop handling
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        dropZone.classList.add('drag-hover');
    }

    function unhighlight(e) {
        dropZone.classList.remove('drag-hover');
    }

    dropZone.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }

    fileInput.addEventListener('change', function() {
        handleFiles(this.files);
    });

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            console.log('File selected:', file.name, file.type);
            if (validateFile(file)) {
                displayPreview(file);
                // Process OCR in background
                setTimeout(() => processBillOCR(file), 100);
            }
        }
    }

    function validateFile(file) {
        const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
        if (!validTypes.includes(file.type)) {
            showAlert('danger', 'Per favore carica un\'immagine (JPG, PNG) o un file PDF');
            return false;
        }
        if (file.size > 16 * 1024 * 1024) { // 16MB
            showAlert('danger', 'Il file è troppo grande. Dimensione massima: 16MB');
            return false;
        }
        return true;
    }

    function displayPreview(file) {
        console.log('Displaying preview for:', file.name);
        const reader = new FileReader();

        reader.onload = function(e) {
            console.log('FileReader loaded successfully');
            preview.innerHTML = `
                <div class="preview-item">
                    <img src="${e.target.result}" alt="Anteprima" class="preview-image">
                    <button type="button" class="btn btn-danger btn-sm delete-preview" onclick="document.getElementById('preview').innerHTML = '';">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
        };

        reader.onerror = function(e) {
            console.error('FileReader error:', e);
            showAlert('danger', 'Errore durante la lettura del file');
        };

        if (file.type.startsWith('image/')) {
            reader.readAsDataURL(file);
        } else if (file.type === 'application/pdf') {
            // For PDFs, show a generic icon
            preview.innerHTML = `
                <div class="preview-item">
                    <i class="fas fa-file-pdf fa-3x text-danger"></i>
                    <p class="mt-2">${file.name}</p>
                    <button type="button" class="btn btn-danger btn-sm delete-preview" onclick="document.getElementById('preview').innerHTML = '';">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
        }
    }

    async function processBillOCR(file) {
        try {
            const worker = await Tesseract.createWorker({
                logger: m => console.log(m)
            });

            await worker.load();
            await worker.loadLanguage('eng');
            await worker.initialize('eng');

            if (file.type.startsWith('image/')) {
                const { data: { text } } = await worker.recognize(file);
                const billType = detectBillType(text);
                document.getElementById('billType').value = billType;
                console.log('OCR completed, bill type:', billType);
            }

            await worker.terminate();
        } catch (error) {
            console.error('OCR Error:', error);
            // Don't show OCR errors to user, just log them
        }
    }

    function detectBillType(text) {
        text = text.toLowerCase();
        if (text.includes('gas') && text.includes('electricity')) return 'MIX';
        if (text.includes('gas')) return 'GAS';
        if (text.includes('electricity') || text.includes('kw')) return 'LIGHT';
        return 'UNKNOWN';
    }

    phoneInput.addEventListener('input', function() {
        this.value = this.value.replace(/[^\d+]/g, '');
    });

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        if (!validateForm()) return;

        const formData = new FormData(form);
        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            if (result.success) {
                showAlert('success', 'File caricato con successo!');
                resetForm();
            } else {
                showAlert('danger', result.error || 'Caricamento fallito');
            }
        } catch (error) {
            console.error('Upload error:', error);
            showAlert('danger', 'Si è verificato un errore durante il caricamento');
        }
    });

    function validateForm() {
        if (!phoneInput.value) {
            showAlert('danger', 'Inserisci un numero di telefono');
            return false;
        }
        if (!fileInput.files.length) {
            showAlert('danger', 'Seleziona un file');
            return false;
        }
        return true;
    }

    function showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.querySelector('.alerts').appendChild(alertDiv);
        setTimeout(() => alertDiv.remove(), 5000);
    }

    function resetForm() {
        form.reset();
        preview.innerHTML = '';
    }
});