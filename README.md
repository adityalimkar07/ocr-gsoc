# RenAIssance OCR LLM / VLM Evaluation Pipeline

This repository contains the newly integrated Gemini Post-Processing Pipeline for the historical Spanish documents in the RenAIssance project.

## Updates
We have implemented a dual-step evaluation pipeline using Google's Gemini models:
1. **Base OCR**: Extracts raw text from historical document images using a Vision Language Model (VLM).
2. **Post-Processing OCR**: Applies specific Renaissance transcription rules (fixing interchangeable chars like u/v, ignoring inconsistent accents, handling split hyphens) via an LLM to dramatically improve the text accuracy and match it directly to the rigorous ground truth standards.

## Project Structure Setup

To run the pipeline and generate evaluation metrics, you MUST organize your workspace carefully. The test documents (Sources and Transcriptions) must be placed in the root directory of this repository:

1. Copy your `Test sources` folder into the root directory.
2. Copy your `Test transcriptions` folder into the root directory.

The resulting folder structure should look exactly like this:
```
ocr-gsoc/
│
├── evaluate_all.py
├── gemini_pipeline.py
├── requirements.txt
├── .gitignore
│
├── Test sources/
│   └── Print/
│       ├── Buendia - Instruccion.pdf
│       └── ...
│
└── Test transcriptions/
    └── Print/
        ├── Buendia - Instruccion transcription.docx
        └── ...
```

## Environment Configuration

Before running any scripts, you **must set up your Gemini API Key**.
1. Create a file named `.env` in the root of the project directory.
2. Add the following line to the `.env` file (replace with your actual API key):
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

## Installation

Install all required Python dependencies:
```bash
pip install -r requirements.txt
```

## Running the Evaluation

### Single Document Test (`gemini_pipeline.py`)
To test the pipeline on a single document (`Buendia - Instruccion`), run:
```bash
python gemini_pipeline.py
```
This script will extract the first valid transcription page, run both OCR stages, and print the Character Error Rate (CER) and Word Error Rate (WER) directly to the console.

### Full Pipeline Evaluation (`evaluate_all.py`)
To evaluate the **entire dataset** and extract the processed text files for manual review, run:
```bash
python evaluate_all.py
```
**Important Notes on `evaluate_all.py`:**
* The script perfectly maps all complex pages, including dynamically concatenated left/right newspaper columns found in the docx ground truths.
* It explicitly sleeps between API calls to gracefully respect free tier rate limits (15 RPM).
* **Outputs:** For every processed document, it will create a `results/` folder containing three txt files:
  1. `[DocumentName]_base.txt` (Raw OCR)
  2. `[DocumentName]_post.txt` (Corrected Post-Processed OCR)
  3. `[DocumentName]_gt.txt` (Ground truth OCR)
* Finally, it produces a `final_summary.txt` in the `results/` directory containing absolute CER and WER accuracies across all documents combined. Additionally, it is important to note that Character Error Rate (CER) and Word Error Rate (WER) may not be the most appropriate evaluation metrics in this context. Although manual verification indicates that the extracted documents are highly accurate, minor alignment differences can disproportionately inflate CER and WER scores. Therefore, it would be beneficial to explore more suitable metrics that better reflect the true quality of the extracted content.
