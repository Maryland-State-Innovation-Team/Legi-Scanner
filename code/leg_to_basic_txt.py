import os
import argparse
from glob import glob
import PyPDF2
from PyPDF2 import PdfReader
from tqdm import tqdm

def pdf_full_text(pdf_path):
    pdf_reader = PdfReader(pdf_path)
    text_list = list()
    page_count = 0
    for page in pdf_reader.pages:
        text_list.append(page.extract_text())
        page_count += 1
    return page_count, '\n'.join(text_list).replace('\x00','')


def main(session_year):
    full_page_count = 0
    input_dir = os.path.abspath(f'data/{session_year}rs/pdf')
    output_dir = os.path.abspath(f'data/{session_year}rs/basic_txt')
    os.makedirs(output_dir, exist_ok=True)
    pdf_wildcard = os.path.join(input_dir, '*.pdf')
    pdf_files = glob(pdf_wildcard)
    for pdf_file in tqdm(pdf_files):
        file_basename = os.path.basename(pdf_file)
        file_name, _ = os.path.splitext(file_basename)
        destination_basename = '{}.txt'.format(file_name)
        destination_file_path = os.path.join(output_dir, destination_basename)
        try:
            pdf_page_count, full_text = pdf_full_text(pdf_file)
            full_page_count += pdf_page_count
        except PyPDF2.errors.PdfReadError:
            print("Corrupted PDF: {}".format(file_basename))
        if not os.path.exists(destination_file_path):
            with open(destination_file_path, 'w', encoding='utf-8') as destination_file:
                destination_file.write(full_text)
    print(f'Total page count: {full_page_count}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse Maryland legislation into basic text for token count.')
    parser.add_argument('session_year', type=int, help='The regular session year')
    args = parser.parse_args()
    main(args.session_year)