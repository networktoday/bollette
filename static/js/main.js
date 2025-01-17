document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const preview = document.getElementById('preview');
    const form = document.getElementById('upload-form');
    const phoneInput = document.getElementById('phone');

    // Initialize Tesseract.js
    const worker = Tesseract.createWorker({
        logger: m => console.log(m)
    });

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
            if (validateFile(file)) {
                displayPreview(file);
                processBillOCR(file);
            }
        }
    }

    function validateFile(file) {
        const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
        if (!validTypes.includes(file.type)) {
            alert('Please upload an image (JPG, PNG) or PDF file');
            return false;
        }
        return true;
    }

    function displayPreview(file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            preview.innerHTML = `
                <div class="preview-item">
                    <img src="${e.target.result}" alt="Preview">
                    <button type="button" class="btn btn-danger btn-sm delete-preview">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
        }
        reader.readAsDataURL(file);
    }

    async function processBillOCR(file) {
        try {
            await worker.load();
            await worker.loadLanguage('eng');
            await worker.initialize('eng');
            const { data: { text } } = await worker.recognize(file);
            
            // Simple bill type detection based on keywords
            const billType = detectBillType(text);
            document.getElementById('billType').value = billType;
            
        } catch (error) {
            console.error('OCR Error:', error);
        }
    }

    function detectBillType(text) {
        text = text.toLowerCase();
        if (text.includes('gas') && text.includes('electricity')) return 'MIX';
        if (text.includes('gas')) return 'GAS';
        if (text.includes('electricity') || text.includes('kw')) return 'LIGHT';
        return 'UNKNOWN';
    }

    // Phone number validation
    phoneInput.addEventListener('input', function() {
        this.value = this.value.replace(/[^\d+]/g, '');
    });

    // Form submission
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
                showAlert('success', 'Bill uploaded successfully!');
                resetForm();
            } else {
                showAlert('danger', result.error || 'Upload failed');
            }
        } catch (error) {
            showAlert('danger', 'An error occurred during upload');
        }
    });

    function validateForm() {
        if (!phoneInput.value) {
            showAlert('danger', 'Please enter a phone number');
            return false;
        }
        if (!fileInput.files.length) {
            showAlert('danger', 'Please select a file');
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
