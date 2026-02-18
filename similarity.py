import os
import glob
import pickle
import shutil
import numpy as np
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# --- Configuration ---
YEARS = [2023, 2024, 2025, 2026]
CACHE_FILE = "bill_embeddings_cache.pkl"
OUTPUT_DIR = "data_system_similarity"
TOP_K = 50

# The target text to compare against
TARGET_TEXT = """
16 (2) DEVELOP AN ELECTRONIC PROCESS FOR TRACKING THE  17 REAL–TIME INDICATORS; 

21 (3) (I) DEVELOP A MODEL FOR STANDARDIZED DATA COLLECTION  22 WITH MANDATED UNIFORM METRICS, INCLUDING AGE, GENDER IDENTITY, RACE, 23 ETHNICITY, COUNTY OF ORIGIN, PAYER TYPE
"""

def encode_long_text(model, text, chunk_size=256, overlap=20):
    """
    Splits long text into overlapping chunks, encodes them, 
    and averages the embeddings.
    """
    # 1. Tokenize roughly by words to avoid cutting words in half
    # (For stricter tokenization, we'd use the model's tokenizer, but this is faster/simpler)
    words = text.split()
    
    if not words:
        return np.zeros(model.get_sentence_embedding_dimension())

    # 2. Create chunks
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)

    if not chunks:
        return np.zeros(model.get_sentence_embedding_dimension())

    # 3. Encode chunks
    chunk_embeddings = model.encode(chunks, batch_size=1, show_progress_bar=False)

    # 4. Mean pooling (average all chunk embeddings)
    # Result is a single vector of shape (hidden_dim,)
    aggregated_embedding = np.mean(chunk_embeddings, axis=0)
    
    # 5. Normalize the resulting vector (optional but recommended for cosine similarity)
    norm = np.linalg.norm(aggregated_embedding)
    if norm > 0:
        aggregated_embedding = aggregated_embedding / norm
        
    return aggregated_embedding

def get_cached_embeddings(model, texts, cache_file):
    """
    Retrieves embeddings from cache or computes them using chunking.
    """
    cache = {}
    
    # 1. Load existing cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'rb') as f:
                cache = pickle.load(f)
            print(f"Loaded {len(cache)} embeddings from cache.")
        except Exception as e:
            print(f"Could not load cache: {e}. Starting fresh.")

    # 2. Identify missing items
    missing_texts = [t for t in texts if t not in cache]
    
    # 3. Compute missing
    if missing_texts:
        print(f"Computing {len(missing_texts)} new embeddings with chunking...")
        
        # Iterate one by one to handle long texts safely
        for i, text in enumerate(tqdm(missing_texts, desc="Encoding Docs")):
            # Use the helper function to handle long text
            # We treat the input as a single "long text" here
            emb = encode_long_text(model, text, chunk_size=512)
            cache[text] = emb
            
            # periodic save (optional, but good for safety)
            if i % 10 == 0:
                with open(cache_file, 'wb') as f:
                    pickle.dump(cache, f)
        
        # 4. Final Save
        with open(cache_file, 'wb') as f:
            pickle.dump(cache, f)
            
    # 5. Return ordered list
    return np.array([cache[t] for t in texts])

def load_bill_data():
    """
    Scans directories for 2023-2026, finds bills with matching fiscal notes.
    Returns a list of dictionaries containing path info and text content.
    """
    valid_bills = []
    
    print("Scanning for bills and fiscal notes...")
    for year in YEARS:
        # Construct path: data/2023rs/md/*.md
        # Assuming 'rs' stands for Regular Session based on standard MD legislative data formats
        search_path = os.path.join("data", f"{year}rs", "md", "*.md")
        files = glob.glob(search_path)
        
        # Filter for bill files (exclude _fn files)
        bill_files = [f for f in files if "_fn.md" not in f]
        
        for bill_path in bill_files:
            # Construct the expected fiscal note path
            # e.g., data/2023rs/md/HB0001.md -> data/2023rs/md/HB0001_fn.md
            fn_path = bill_path.replace(".md", "_fn.md")
            
            if os.path.exists(fn_path):
                try:
                    with open(bill_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                    # Only add if content is not empty
                    if content.strip():
                        valid_bills.append({
                            "bill_path": bill_path,
                            "fn_path": fn_path,
                            "text": content,
                            "filename": os.path.basename(bill_path)
                        })
                except Exception as e:
                    print(f"Error reading {bill_path}: {e}")
    
    print(f"Found {len(valid_bills)} bills with valid fiscal notes.")
    return valid_bills

def main():
    # 1. Load Data
    bills = load_bill_data()
    if not bills:
        print("No valid bills found. Check your directory structure.")
        return

    # 2. Load Model
    print(f"Loading Model...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    # 3. Get Embeddings (Bill Texts)
    bill_texts = [b['text'] for b in bills]
    print("Retrieving/Computing bill embeddings...")
    bill_embeddings = get_cached_embeddings(model, bill_texts, CACHE_FILE)

    # 4. Get Embedding (Target Text)
    print("Embedding target text...")
    target_embedding = model.encode([TARGET_TEXT])

    # 5. Calculate Similarity
    print("Calculating cosine similarity...")
    # cosine_similarity expects 2D arrays. 
    # Result is shape (1, n_bills), we take [0] to get the 1D array of scores.
    similarity_scores = cosine_similarity(target_embedding, bill_embeddings)[0]

    # 6. Rank Results
    # argsort returns indices that would sort the array, we reverse it for descending order
    ranked_indices = np.argsort(similarity_scores)[::-1]
    
    # 7. Copy Files
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    
    print(f"Copying top {TOP_K} fiscal notes to {OUTPUT_DIR}...")
    
    for rank, idx in enumerate(ranked_indices[:TOP_K]):
        bill_data = bills[idx]
        score = similarity_scores[idx]
        
        # Source and Destination
        src_fn = bill_data['fn_path']
        
        # Rename destinations to include rank and score for easy sorting/viewing
        # e.g. 01_0.8500_HB0001_fn.md and 01_0.8500_HB0001.md
        safe_score = f"{score:.4f}"

        src_bill = bill_data['bill_path']

        dest_filename_fn = f"{rank+1:02d}_{safe_score}_{os.path.basename(src_fn)}"
        dest_path_fn = os.path.join(OUTPUT_DIR, dest_filename_fn)

        dest_filename_bill = f"{rank+1:02d}_{safe_score}_{os.path.basename(src_bill)}"
        dest_path_bill = os.path.join(OUTPUT_DIR, dest_filename_bill)

        try:
            shutil.copy2(src_fn, dest_path_fn)
        except Exception as e:
            print(f"Error copying {src_fn}: {e}")

        try:
            shutil.copy2(src_bill, dest_path_bill)
        except Exception as e:
            print(f"Error copying {src_bill}: {e}")

    print("\nProcessing Complete.")
    print(f"Top {TOP_K} similar fiscal notes are located in: {os.path.abspath(OUTPUT_DIR)}")

if __name__ == "__main__":
    main()