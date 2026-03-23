import os
import glob
import re
import time
import docx
import fitz
import difflib
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

# Initialize APIs
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# Configure Models
# We use gemini-2.5-flash for both steps to optimize for the Free Tier 15 RPM
model_flash = genai.GenerativeModel('gemini-2.5-flash')

# Paths (Relative to repository root)
source_dir = r"Test sources\Print"
trans_dir = r"Test transcriptions\Print"
results_dir = r"results"
os.makedirs(results_dir, exist_ok=True)

# Metrics tools
def cer(ref, hyp):
    sm = difflib.SequenceMatcher(None, ref, hyp)
    return 1 - sm.ratio()

def wer(ref, hyp):
    r_words = ref.split()
    h_words = hyp.split()
    sm = difflib.SequenceMatcher(None, r_words, h_words)
    return 1 - sm.ratio()

def get_page_number(title):
    # e.g. "PDF p2 - left" -> 2
    match = re.search(r'PDF p(\d+)', title)
    if match:
        return int(match.group(1))
    return None

def read_transcription(file_path):
    doc = docx.Document(file_path)
    pages = {} # dict mapping page_number to concatenated string
    current_page_title = None
    text = ''
    
    for para in doc.paragraphs:
        stripped_text = para.text.strip()
        if stripped_text.startswith("PDF p"):
            # Save previous
            if current_page_title is not None and text.strip():
                pn = get_page_number(current_page_title)
                if pn is not None:
                    pages[pn] = pages.get(pn, "") + "\n" + text.strip()
            
            current_page_title = stripped_text
            text = ''
        elif stripped_text == "END OF EXTRACT":
            if current_page_title is not None and text.strip():
                pn = get_page_number(current_page_title)
                if pn is not None:
                    pages[pn] = pages.get(pn, "") + "\n" + text.strip()
            current_page_title = None
            text = ''
        elif current_page_title is not None and stripped_text != '':
            text += stripped_text + "\n"
    
    # Catch last pending page
    if current_page_title is not None and text.strip():
        pn = get_page_number(current_page_title)
        if pn is not None:
            pages[pn] = pages.get(pn, "") + "\n" + text.strip()
            
    # Clean up excess newlines
    for pn in pages:
        pages[pn] = pages[pn].strip()

    return pages

# Post processing prompt
prompt_template = """Correct the spelling and formatting errors in the following Spanish Renaissance OCR transcription based on these rules:
1. 'u' and 'v' are interchangeable, choose the contextually correct one.
2. 'f' and 's' are interchangeable, choose the contextually correct one.
3. Ignore inconsistent accents, except for 'ñ'.
4. Convert old spelling 'ç' to modern 'z'.
5. Letters with a horizontal 'cap' mean 'n' follows, or 'ue' after a capped 'q' (e.g. q̄ -> que).
6. Leave line-end split hyphens split.

Output ONLY the corrected text without any leading or trailing commentary:

{}"""

def evaluate():
    pdf_files = glob.glob(os.path.join(source_dir, "*.pdf"))
    
    global_gt_text = ""
    global_base_text = ""
    global_post_text = ""

    summary_log = open(os.path.join(results_dir, "final_summary.txt"), "w", encoding="utf-8")
    
    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        base_name = os.path.splitext(filename)[0]
        
        # Determine the docx name heuristically
        docx_matches = glob.glob(os.path.join(trans_dir, f"{base_name[:12]}*.docx"))
        if not docx_matches:
            print(f"Skipping {filename}, no docx found.")
            continue
            
        docx_path = docx_matches[0]
        print(f"\n--- Processing Document: {base_name} ---")
        
        gt_pages = read_transcription(docx_path)
        
        # Files for this document
        doc_base_file = open(os.path.join(results_dir, f"{base_name}_base.txt"), "w", encoding="utf-8")
        doc_post_file = open(os.path.join(results_dir, f"{base_name}_post.txt"), "w", encoding="utf-8")
        doc_gt_file = open(os.path.join(results_dir, f"{base_name}_gt.txt"), "w", encoding="utf-8")
        
        doc_gt_text = ""
        doc_base_text = ""
        doc_post_text = ""

        # Open PDF
        doc = fitz.open(pdf_path)
        
        for pn, gt_text in sorted(gt_pages.items()):
            page_index = pn - 1  # 1-indexed to 0-indexed
            if page_index < 0 or page_index >= len(doc):
                print(f"Page index {page_index} out of bounds for {filename}")
                continue
                
            print(f"  -> Processing PDF p{pn}")
            
            # Extract Image
            page = doc.load_page(page_index)
            pix = page.get_pixmap(dpi=200)
            img_path = os.path.join(results_dir, f"temp_{base_name[:6]}_p{pn}.png")
            pix.save(img_path)
            img = Image.open(img_path)
            
            try:
                # API Limit wait explicitly to not get 429'd
                time.sleep(5)
                # 1. Base OCR
                resp_base = model_flash.generate_content([img, "Transcribe the text in this historical Spanish document exactly as written. Output ONLY the transcription."])
                raw_text = resp_base.text.strip()
                
                time.sleep(5)
                # 2. Post OCR
                resp_post = model_flash.generate_content(prompt_template.format(raw_text))
                corrected_text = resp_post.text.strip()
                
            except Exception as e:
                print(f"Exception on {filename} p{pn}: {e}")
                continue
                
            # Log results
            doc_base_file.write(f"--- Page {pn} ---\n{raw_text}\n\n")
            doc_post_file.write(f"--- Page {pn} ---\n{corrected_text}\n\n")
            doc_gt_file.write(f"--- Page {pn} ---\n{gt_text}\n\n")
            
            doc_gt_text += gt_text + "\n"
            doc_base_text += raw_text + "\n"
            doc_post_text += corrected_text + "\n"
            
        doc_base_file.close()
        doc_post_file.close()
        doc_gt_file.close()

        # Document Metrics
        if doc_gt_text:
            b_cer, b_wer = cer(doc_gt_text, doc_base_text), wer(doc_gt_text, doc_base_text)
            p_cer, p_wer = cer(doc_gt_text, doc_post_text), wer(doc_gt_text, doc_post_text)
            
            doc_summary = f"""Results for {base_name}:
  Base OCR | CER: {b_cer:.2%} | WER: {b_wer:.2%} | Acc (1-CER): {1-b_cer:.2%}
  Post OCR | CER: {p_cer:.2%} | WER: {p_wer:.2%} | Acc (1-CER): {1-p_cer:.2%}
"""
            print(doc_summary)
            summary_log.write(doc_summary + "\n")
            
            global_gt_text += doc_gt_text + "\n"
            global_base_text += doc_base_text + "\n"
            global_post_text += doc_post_text + "\n"

    # Global Metrics
    if global_gt_text:
        gb_cer, gb_wer = cer(global_gt_text, global_base_text), wer(global_gt_text, global_base_text)
        gp_cer, gp_wer = cer(global_gt_text, global_post_text), wer(global_gt_text, global_post_text)
        
        final_summary = f"""COMBINED ACCURACY FOR ALL DOCUMENTS:
  Base OCR | CER: {gb_cer:.2%} | WER: {gb_wer:.2%} | Acc (1-CER): {1-gb_cer:.2%}
  Post OCR | CER: {gp_cer:.2%} | WER: {gp_wer:.2%} | Acc (1-CER): {1-gp_cer:.2%}
"""
        print(final_summary)
        summary_log.write(final_summary + "\n")
        
    summary_log.close()
    
if __name__ == "__main__":
    evaluate()
