# Analisi Bollette - Sistema di Gestione Bollette Italiane

Un'applicazione web specializzata per la gestione delle bollette di utenze italiane, che utilizza tecnologie OCR e di elaborazione delle immagini per automatizzare la classificazione e l'estrazione dei dati dalle bollette.

## Funzionalità Principali

- 📷 Scansione e OCR di bollette (supporto per immagini e PDF)
- 🔍 Classificazione automatica del tipo di bolletta (LUCE/GAS/MIX)
- 💰 Estrazione automatica dei costi per unità
- 📱 Interfaccia responsive per dispositivi mobili
- 📊 Elaborazione parallela per file multipagina
- 📨 Sistema di notifiche SMS tramite Twilio

## Requisiti di Sistema

- Python 3.11+
- PostgreSQL Database
- Tesseract OCR
- Poppler (per la conversione PDF)

## Dipendenze Python

- Flask e Flask-SQLAlchemy per il backend
- Pillow e OpenCV per l'elaborazione delle immagini
- Pytesseract per l'OCR
- PDF2Image per la conversione dei PDF
- Twilio per le notifiche SMS

## Installazione

1. Clona il repository:
```bash
git clone https://github.com/networktoday/bollette.git
cd bollette
```

2. Installa le dipendenze:
```bash
pip install -r requirements.txt
```

3. Configura le variabili d'ambiente:
```bash
DATABASE_URL=postgresql://user:password@host:port/dbname
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=your_twilio_number
```

4. Inizializza il database:
```bash
flask db upgrade
```

5. Avvia l'applicazione:
```bash
python main.py
```

## Utilizzo

1. Accedi all'applicazione tramite browser (default: `http://localhost:5000`)
2. Inserisci il numero di telefono per le notifiche
3. Carica le bollette (formati supportati: JPG, PNG, PDF)
4. L'applicazione processerà automaticamente i documenti:
   - Classificazione del tipo di bolletta
   - Estrazione dei costi
   - Salvataggio nel database
   - Invio notifica di conferma via SMS

## Tipi di Bollette Supportati

- **LUCE**: Bollette per energia elettrica
- **GAS**: Bollette per gas naturale
- **MIX**: Bollette combinate luce e gas

## Elaborazione OCR

Il sistema utilizza tecniche avanzate di OCR per:
- Riconoscimento del testo in italiano
- Identificazione automatica del tipo di bolletta
- Estrazione precisa dei costi per unità
- Gestione di documenti multipagina

## Sicurezza

- Validazione dei file in upload
- Sanitizzazione dei nomi dei file
- Protezione da sovraccarico del server
- Gestione sicura delle credenziali tramite variabili d'ambiente

## Contribuire

Siamo aperti a contributi! Se vuoi contribuire al progetto:
1. Fai un fork del repository
2. Crea un branch per la tua feature
3. Invia una pull request

## Licenza

Questo progetto è rilasciato sotto licenza MIT.