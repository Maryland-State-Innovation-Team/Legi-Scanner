import os
import hashlib
from google import genai
from glob import glob
from llm_utils import query_llm_with_retries

SYSTEM_PROMPT = (
    "Below you will find bill markdown wrapped in <bill> tags, "
    "followed by amendment markdown wrapped in <amendment> tags. "
    "Apply the instructions in the amendment to the bill. "
    "Respond ONLY with the resulting markdown."
)

USER_TEMPLATE = (
    "<bill>\n{}\n</bill>\n\n"
    "<amendment>\n{}\n</amendment>"
)

def apply_amendments(session_year: int, bill_number: str, state_manager, client, model_name: str, model_family: str):
    md_dir = os.path.abspath(f'data/{session_year}rs/md')
    bill_path = os.path.join(md_dir, f"{bill_number}.md")
    
    if not os.path.exists(bill_path):
        print(f"Skipping amend for {bill_number}: Main MD not found.")
        return

    # Find amendment MD files
    amd_pattern = os.path.join(md_dir, f"{bill_number}_amd*.md")
    amd_files = glob(amd_pattern)
    
    if not amd_files:
        state_manager.update_bill(bill_number, {"needs_amend": False, "amended_status": "original"})
        return

    # Sort amendments (logic might differ, but alphabetical usually works for id)
    amd_files.sort()
    
    # Calculate hash of inputs to determine if we need to re-run LLM
    hasher = hashlib.sha256()
    with open(bill_path, 'r', encoding='utf-8') as f:
        bill_content = f.read()
        hasher.update(bill_content.encode('utf-8'))
    
    for amd_file in amd_files:
        with open(amd_file, 'r', encoding='utf-8') as f:
            hasher.update(f.read().encode('utf-8'))
    
    current_hash = hasher.hexdigest()
    bill_state = state_manager.get_bill(bill_number)
    amended_path = os.path.join(md_dir, f"{bill_number}_amended.md")

    if bill_state.get('amend_input_hash') == current_hash and os.path.exists(amended_path):
        state_manager.update_bill(bill_number, {
            "needs_amend": False,
            "needs_qa": True
        })
        return

    current_bill_md = bill_content

    # Apply sequentially
    for amd_file in amd_files:
        with open(amd_file, 'r', encoding='utf-8') as f:
            amd_md = f.read()
        
        value = USER_TEMPLATE.format(current_bill_md, amd_md)
        
        # Using Gemini via llm_utils
        response_text = query_llm_with_retries(
            client=client,
            prompt=SYSTEM_PROMPT,
            value=value,
            response_format=None,
            model_name=model_name,
            model_family=model_family
        )
        
        if response_text:
            current_bill_md = response_text
        else:
            print(f"Error applying amendment {amd_file}: LLM returned no response")
            state_manager.update_bill(bill_number, {"amended_status": "failed"})
            return

    # Save Amended Version
    amended_path = os.path.join(md_dir, f"{bill_number}_amended.md")
    with open(amended_path, 'w', encoding='utf-8') as f:
        f.write(current_bill_md)

    state_manager.update_bill(bill_number, {
        "needs_amend": False,
        "needs_qa": True,
        "amended_status": "amended",
        "amend_input_hash": current_hash
    })