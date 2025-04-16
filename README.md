# Legi-Scanner
Innovation Team Legislation Scanner

## Installation
```bash
pip install virtualenv
python -m virtualenv venv
cd venv/Scripts
activate
cd ../..
pip install -r requirements.txt
```

## Execution
```bash
cd venv/Scripts
activate
cd ../..
python code/download_legislation.py 2025
python code/leg_to_basic_txt.py 2025 # Total page count: 4,653
python code/count_tokens.py 2025 # This will use at least 2,417,695 tokens and cost at least $0.36 to run using model gpt-4o-mini.
```