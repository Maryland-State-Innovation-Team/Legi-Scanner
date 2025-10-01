import os
import argparse
from glob import glob
from tqdm import tqdm
import google
from google import genai
import time
from dotenv import load_dotenv


PROMPT_TEMPLATE = (
    "Below you will find bill markdown wrapped in the tags <bill></bill>, "
    "followed by amendment markdown wrapped in the tags <amendment></amendment>. "
    "Read the bill and amendment markdown carefully, and then apply the instructions found in the amendment markdown to the bill markdown. "
    "Respond only with the markdown that results from applying the amendment to the bill. The markdown contents are as follows:\n"
    "<bill>\n{}\n</bill>\n\n"
    "<amendment>\n{}\n</amendment>"
)


def gemini_query(client, contents):
    response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=contents,
    )
    return response.text


def main(client, session_year):
    input_dir = os.path.abspath(f'data/{session_year}rs/md')
    amendment_wildcard = os.path.join(input_dir, '*_amd*.md')
    amendment_files = glob(amendment_wildcard)
    for amendment_file in tqdm(amendment_files):
        file_basename = os.path.basename(amendment_file)
        file_name, _ = os.path.splitext(file_basename)
        bill_number = file_name.split('_')[0]
        bill_file_name = f'{bill_number}.md'
        bill_file = os.path.join(input_dir, bill_file_name)
        with open(bill_file, 'r', encoding='utf-8') as b_f:
            bill_md = b_f.read()
        with open(amendment_file, 'r', encoding='utf-8') as a_f:
            amendment_md = a_f.read()
        destination_basename = f'{bill_number}_amended.md'
        destination_file_path = os.path.join(input_dir, destination_basename)
        if not os.path.exists(destination_file_path):
            prompt = PROMPT_TEMPLATE.format(bill_md, amendment_md)
            amended_bill_md = gemini_query(client, prompt)
            with open(destination_file_path, 'w', encoding='utf-8') as destination_file:
                destination_file.write(amended_bill_md)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Use Gemini 2.5 Pro to apply amendment markdown text.')
    parser.add_argument('session_year', type=int, help='The regular session year')
    args = parser.parse_args()
    load_dotenv()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY is None:
        print("Please provide a GEMINI_API_KEY in a .env file.")
    else:
        client = genai.Client(api_key=GEMINI_API_KEY)
        main(client, args.session_year)