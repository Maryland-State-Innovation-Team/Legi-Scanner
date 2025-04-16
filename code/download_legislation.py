import os
import json
import argparse
import requests
from bs4 import BeautifulSoup
import tqdm
import pandas as pd

# Enable tqdm for pandas
tqdm.tqdm.pandas()

def main(session_year):
    if session_year == 2025:
        passed_type = 'passedByBoth'
    else:
        passed_type = 'chapters'
    base_url = 'https://mgaleg.maryland.gov/mgawebsite/Legislation/GetReportsTable'
    payload = {
        'ys': f'{session_year}rs',
        'type': passed_type 
    }
    headers = {
        'accept': 'text/html, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'sec-ch-ua': '\'Google Chrome\';v=\'135\', \'Not-A.Brand\';v=\'8\', \'Chromium\';v=\'135\'',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '\'Windows\'',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'x-requested-with': 'XMLHttpRequest',
        'Referer': f'https://mgaleg.maryland.gov/mgawebsite/Legislation/Report?id={passed_type}',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
    }
    response = requests.post(base_url, headers=headers, data=payload)
    response.raise_for_status()  # Raise an exception for bad status codes
    tables = pd.read_html(response.content)
    if not tables:
        print('No tables found in the response.')
        return
    df = tables[0]
    # Remove parenthetical text from 'Bill Number'
    df['Bill Number'] = df['Bill Number'].str.replace(r'\s\(.*\)$', '', regex=True)
    print(f'Successfully downloaded and parsed table for {session_year}.')

    synopses = list()

    print(f'Processing {df.shape[0]} rows for {session_year}...')
    for index, row in tqdm.tqdm(df.iterrows(), total=df.shape[0], desc=f'Processing {session_year} bills'):
        bill_number = row['Bill Number']
        bill_url = f'https://mgaleg.maryland.gov/mgawebsite/Legislation/Details/{bill_number}?ys={payload['ys']}'
        bill_response = requests.get(bill_url, headers=headers)
        bill_response.raise_for_status()
        soup = BeautifulSoup(bill_response.content, 'html.parser')

        synopsis_div = soup.find('div', string='Synopsis')
        synopsis_text = ""
        if synopsis_div:
            next_sibling_div = synopsis_div.find_next_sibling('div')
            if next_sibling_div:
                synopsis_text = next_sibling_div.get_text(strip=True)
            else:
                print(f"Warning: Could not find the synopsis text div for bill {bill_number} at {bill_url}")
        else:
            print(f"Warning: Could not find the 'Synopsis' label div for bill {bill_number} at {bill_url}")
        synopses.append(synopsis_text)

        all_tables = soup.find_all('table')

        last_bill_link = None
        subsequent_amd_links = list()
        if len(all_tables) > 1:
            target_table = all_tables[1]
            anchors = target_table.find_all('a', href=True)

            bill_prefix = f'/{session_year}RS/bills/'
            amd_prefix = f'/{session_year}RS/amds/'

            for anchor in anchors:
                href = anchor['href']
                if href.startswith(bill_prefix):
                    last_bill_link = href
                    subsequent_amd_links = list() # Reset amd links when a new bill link is found
                elif href.startswith(amd_prefix):
                    # Only collect amd links if they appear after a bill link
                    if last_bill_link is not None:
                        subsequent_amd_links.append(href)
        else:
            print(f"Warning: Could not find the second table for bill {bill_number} at {bill_url}")
        if last_bill_link:
            print(f"Found {len(subsequent_amd_links) + 1} PDFs to download for {bill_number}.")
            pdf_output_dir = f'data/{session_year}rs/pdf'
            os.makedirs(pdf_output_dir, exist_ok=True)

            # Download the main bill PDF
            bill_pdf_url = f'https://mgaleg.maryland.gov{last_bill_link}'
            bill_pdf_path = os.path.join(pdf_output_dir, f'{bill_number}.pdf')
            try:
                pdf_response = requests.get(bill_pdf_url, headers=headers)
                pdf_response.raise_for_status()
                with open(bill_pdf_path, 'wb') as f:
                    f.write(pdf_response.content)
            except requests.exceptions.RequestException as e:
                print(f"Error downloading {bill_pdf_url}: {e}")
            except IOError as e:
                print(f"Error saving file {bill_pdf_path}: {e}")

            # Download subsequent amendment PDFs
            for i, amd_link in enumerate(subsequent_amd_links, start=1):
                amd_pdf_url = f'https://mgaleg.maryland.gov{amd_link}'
                amd_pdf_path = os.path.join(pdf_output_dir, f'{bill_number}_amd{i}.pdf')
                try:
                    pdf_response = requests.get(amd_pdf_url, headers=headers)
                    pdf_response.raise_for_status()
                    with open(amd_pdf_path, 'wb') as f:
                        f.write(pdf_response.content)
                    # print(f"Successfully downloaded {amd_pdf_url} to {amd_pdf_path}")
                except requests.exceptions.RequestException as e:
                    print(f"Error downloading {amd_pdf_url}: {e}")
                except IOError as e:
                    print(f"Error saving file {amd_pdf_path}: {e}")

    print(f'Finished processing {session_year}.')
    df['Synopsis'] = synopses

    csv_output_dir = f'data/{session_year}rs/csv'
    os.makedirs(csv_output_dir, exist_ok=True)
    csv_output_file = os.path.join(csv_output_dir, 'legislation.csv')
    df.to_csv(csv_output_file, index=False)
    print(f'Saved DataFrame to {csv_output_file}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Download Maryland legislation.')
    parser.add_argument('session_year', type=int, help='The regular session year')
    args = parser.parse_args()
    main(args.session_year)