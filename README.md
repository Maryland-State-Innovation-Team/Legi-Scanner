# Legi-Scanner

Legi-Scanner is a toolkit developed by the Maryland State Innovation Team to automate the collection, processing, analysis, and summarization of Maryland General Assembly legislation. It downloads legislative data, converts it into machine-readable formats, applies amendments, and leverages large language models (LLMs) to answer policy-relevant questions about bills. The toolkit is designed to support policy analysis, research, and innovation in government.

## Installation

```bash
pip install virtualenv
python -m virtualenv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

## Python Scripts Overview

Below are descriptions of each script in the `code` directory, including their purpose, arguments, defaults, and usage examples.

---

### `download_legislation.py`

**Purpose:**  
Downloads Maryland legislative data and associated PDFs for a given session year, processes cross-filed bills, and saves metadata as CSV.

**Arguments:**  
- `session_year` (int, required): The regular session year.

**Usage:**  
```bash
python code/download_legislation.py 2025
```
- Downloads bill metadata from the Maryland General Assembly website.
- Downloads main bill PDFs and adopted amendment PDFs to `data/{session_year}rs/pdf/`.
- Outputs a CSV file with bill metadata to `data/{session_year}rs/csv/legislation.csv`.

**Note:** For future sessions (currently set as 2026), this script filters for bills that have passed (rather than those with a chapter number) and applies special logic to capture incremental amendments as they are adopted.

---

### `leg_to_basic_txt.py`

**Purpose:**  
Converts all bill PDFs for a session year into plain text files, one per bill.

**Arguments:**  
- `session_year` (int, required): The regular session year.

**Usage:**  
```bash
python code/leg_to_basic_txt.py 2025
```
- Reads PDFs from `data/{session_year}rs/pdf/`.
- Outputs `.txt` files to `data/{session_year}rs/basic_txt/`.
- Prints the total page count processed.

---

### `leg_to_md.py`

**Purpose:**  
Converts all bill PDFs for a session year into markdown files, preserving formatting and marking struck-through text using markdown strikethrough syntax.

**Arguments:**  
- `session_year` (int, required): The regular session year.

**Usage:**  
```bash
python code/leg_to_md.py 2025
```
- Reads PDFs from `data/{session_year}rs/pdf/`.
- Outputs `.md` files to `data/{session_year}rs/md/`.

---

### `amend_leg_md.py`

**Purpose:**  
Uses Google Gemini 2.5 Pro to apply amendment markdown files to bill markdown files, producing amended bill markdowns.

**Arguments:**  
- `session_year` (int, required): The regular session year (e.g., 2025).

**Usage:**  
```bash
python code/amend_leg_md.py 2025
```
- Requires a `.env` file with `GEMINI_API_KEY` set.
- Looks for bill and amendment markdown files in `data/{session_year}rs/md/`.
- Outputs amended markdown files as `{bill_number}_amended.md` in the same directory.

---

### `count_tokens.py`

**Purpose:**  
Counts the number of tokens in all basic text files for a given session year using the `tiktoken` library, and estimates the cost for LLM processing.

**Arguments:**  
- `session_year` (int, required): The regular session year.

**Usage:**  
```bash
python code/count_tokens.py 2025
```
- Scans `data/{session_year}rs/basic_txt/` for `.txt` files.
- Prints the total token count and estimated cost for the default model (`o3`).

---

### `leg_qa.py`

**Purpose:**  
Uses LLMs (Gemini, OpenAI GPT, or Ollama) to answer a set of policy-relevant questions about each bill, based on the bill's markdown text.

**Arguments:**  
- `session_year` (int, required): The regular session year.
- `--model-family` (optional, default: `gemini`): The LLM backend family to use (`gpt`, `gemini`, or `ollama`).
- `--model` (optional): The specific model name to use (e.g., `gpt-4.1-nano`, `gemini-2.5-flash`, `llama3`).

**Usage:**  
```bash
python code/leg_qa.py 2025 --model-family gemini
```
- Requires API keys in `.env` for Gemini (`GEMINI_API_KEY`) or OpenAI (`OPENAI_API_KEY`).
- Reads bill markdowns from `data/{session_year}rs/md/`.
- Outputs a CSV with model responses to `data/{session_year}rs/csv/legislation_model_responses.csv`.

---

## Requirements

All dependencies are listed in `requirements.txt`.  
You will need API keys for Gemini and/or OpenAI if using those LLMs.  
Some scripts require a `.env` file with the appropriate API keys.

---

Let me know if you want to add usage examples, diagrams, or further details!