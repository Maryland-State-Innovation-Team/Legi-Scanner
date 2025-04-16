import os
import argparse
from dotenv import load_dotenv
from glob import glob
from tqdm import tqdm
import base64
from mistralai import Mistral, DocumentURLChunk


def encode_image(image_path):
    """Encode the image to base64."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"Error: The file {image_path} was not found.")
        return None
    except Exception as e:  # Added general exception handling
        print(f"Error: {e}")
        return None


def mistral_ocr(client, file_name, base64_image):
    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "image_url",
            "image_url": f"data:image/jpeg;base64,{base64_image}" 
        }
    )
    markdowns: list[str] = []
    for page in ocr_response.pages:
        markdowns.append(page.markdown)

    return "\n\n".join(markdowns)


def main(client, session_year):
    input_dir = os.path.abspath(f'data/{session_year}rs/png')
    output_dir = os.path.abspath(f'data/{session_year}rs/md')
    os.makedirs(output_dir, exist_ok=True)
    pdf_wildcard = os.path.join(input_dir, '*.png')
    pdf_files = glob(pdf_wildcard)
    for pdf_file in tqdm(pdf_files):
        file_basename = os.path.basename(pdf_file)
        if file_basename != "HB0548.png":
            continue
        file_name, _ = os.path.splitext(file_basename)
        destination_basename = '{}_png.md'.format(file_name)
        destination_file_path = os.path.join(output_dir, destination_basename)
        if not os.path.exists(destination_file_path):
            # Getting the base64 string
            base64_image = encode_image(pdf_file)
            full_text = mistral_ocr(client, file_basename, base64_image)
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