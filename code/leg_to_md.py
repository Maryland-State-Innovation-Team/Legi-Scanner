import os
import argparse
from dotenv import load_dotenv
from glob import glob
from tqdm import tqdm
from mistralai import Mistral, DocumentURLChunk

def mistral_ocr(client, file_name, pdf_binary):
    uploaded_file = client.files.upload(
        file={
            "file_name": file_name,
            "content": pdf_binary,
        },
        purpose="ocr",
    )

    signed_url = client.files.get_signed_url(file_id=uploaded_file.id, expiry=1)

    pdf_response = client.ocr.process(document=DocumentURLChunk(document_url=signed_url.url), model="mistral-ocr-latest", include_image_base64=True)

    markdowns: list[str] = []
    for page in pdf_response.pages:
        markdowns.append(page.markdown)

    return "\n\n".join(markdowns)


def main(client, session_year):
    input_dir = os.path.abspath(f'data/{session_year}rs/pdf')
    output_dir = os.path.abspath(f'data/{session_year}rs/md')
    os.makedirs(output_dir, exist_ok=True)
    pdf_wildcard = os.path.join(input_dir, '*.pdf')
    pdf_files = glob(pdf_wildcard)
    for pdf_file in tqdm(pdf_files):
        file_basename = os.path.basename(pdf_file)
        if file_basename != "HB0548.pdf":
            continue
        import pdb; pdb.set_trace()
        file_name, _ = os.path.splitext(file_basename)
        destination_basename = '{}.md'.format(file_name)
        destination_file_path = os.path.join(output_dir, destination_basename)
        if not os.path.exists(destination_file_path):
            with open(pdf_file, "rb") as f:
                pdf_binary = f.read()
            full_text = mistral_ocr(client, file_basename, pdf_binary)
            with open(destination_file_path, 'w', encoding='utf-8') as destination_file:
                destination_file.write(full_text)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse Maryland legislation into markdown.')
    parser.add_argument('session_year', type=int, help='The regular session year')
    args = parser.parse_args()

    load_dotenv()
    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    if not mistral_api_key:
        raise ValueError("MISTRAL_API_KEY not found in .env file")
    mistral_client = Mistral(api_key=mistral_api_key)

    main(mistral_client, args.session_year)