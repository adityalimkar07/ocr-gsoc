import os
import fitz
import docx
import difflib
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

def cer(ref, hyp):
    sm = difflib.SequenceMatcher(None, ref, hyp)
    return 1 - sm.ratio()

def wer(ref, hyp):
    r_words = ref.split()
    h_words = hyp.split()
    sm = difflib.SequenceMatcher(None, r_words, h_words)
    return 1 - sm.ratio()

def read_transcription(file_path):
    doc = docx.Document(file_path)
    pages = {}
    current_page = None
    text = ''
    for para in doc.paragraphs:
        stripped_text = para.text.strip()
        if stripped_text.startswith("PDF p"):
            # Save previous page
            if current_page is not None and text.strip():
                pages[current_page] = text.strip()
            
            # Start new page
            current_page = stripped_text
            text = ''
        elif stripped_text == "END OF EXTRACT":
            if current_page is not None and text.strip():
                pages[current_page] = text.strip()
            current_page = None
            text = ''
        elif current_page is not None and stripped_text != '':
            text += stripped_text + "\n"
    
    # Catch last pending page
    if current_page is not None and text.strip():
        pages[current_page] = text.strip()
        
    return pages

def main():
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)

    pdf_path = r"Test sources\Print\Buendia - Instruccion.pdf"
    docx_path = r"Test transcriptions\Print\Buendia - Instruccion transcription.docx"
    
    print(f"Reading ground truth from: {docx_path}")
    gt_pages = read_transcription(docx_path)
    
    # Evaluate 'PDF p2'
    target_page_key = "PDF p2"
    if target_page_key not in gt_pages:
        print(f"Could not find {target_page_key} in ground truth!")
        return
        
    gt_text = gt_pages[target_page_key]
    
    print(f"Processing PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    
    # "PDF p2" corresponds to index 1
    page_to_extract = 1
    page = doc.load_page(page_to_extract)
    pix = page.get_pixmap(dpi=200)
    img_path = "temp_page.png"
    pix.save(img_path)
    
    print("Uploading image to Gemini...")
    img = Image.open(img_path)
    
    import time
    
    # Step 1: Base OCR
    print("Running Base OCR with Gemini 2.5 Flash...")
    model_flash = genai.GenerativeModel('gemini-2.5-flash')
    response_base = model_flash.generate_content(
        [img, "Transcribe the text in this historical Spanish document exactly as written. Output ONLY the transcription."]
    )
    base_text = response_base.text.strip()
    
    print("Waiting 15 seconds to avoid API rate limits...")
    time.sleep(15)
    
    # Step 2: Post-Processing Pipeline
    print("Running Post-Processing Pipeline with Gemini 2.5 Flash...")
    prompt = f"""Correct the spelling and formatting errors in the following Spanish Renaissance OCR transcription based on these rules:
1. 'u' and 'v' are interchangeable, choose the contextually correct one.
2. 'f' and 's' are interchangeable, choose the contextually correct one.
3. Ignore inconsistent accents, except for 'ñ'.
4. Convert old spelling 'ç' to modern 'z'.
5. Letters with a horizontal 'cap' mean 'n' follows, or 'ue' after a capped 'q' (e.g. q̄ -> que).
6. Leave line-end split hyphens split.

Output ONLY the corrected text without any leading or trailing commentary:

{base_text}"""

    model_pro = genai.GenerativeModel('gemini-2.5-flash')
    response_post = model_pro.generate_content(prompt)
    corrected_text = response_post.text.strip()
    
    # Evaluate
    print(f"\nEvaluating target page: {target_page_key}")
    print("\n--- Evaluation Results ---")
    print(f"Ground Truth length: {len(gt_text)} chars")
    
    base_cer = cer(gt_text, base_text)
    base_wer = wer(gt_text, base_text)
    print(f"Base OCR Accuracy (1 - CER): {1 - base_cer:.2%}")
    print(f"Base OCR Accuracy (1 - WER): {1 - base_wer:.2%}")
    
    post_cer = cer(gt_text, corrected_text)
    post_wer = wer(gt_text, corrected_text)
    print(f"Post-Processed Accuracy (1 - CER): {1 - post_cer:.2%}")
    print(f"Post-Processed Accuracy (1 - WER): {1 - post_wer:.2%}")
    
if __name__ == "__main__":
    main()
