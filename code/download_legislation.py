import os
import json
import re
import argparse
import requests
from bs4 import BeautifulSoup
import tqdm
import pandas as pd

# Enable tqdm for pandas
tqdm.tqdm.pandas()

def main(session_year):
    json_url = f'https://mgaleg.maryland.gov/{session_year}rs/misc/billsmasterlist/legislation.json'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }
    response = requests.get(json_url, headers=headers)
    response.raise_for_status()
    leg_data = response.json()

    if session_year == 2025:
        filtered_leg_data = [leg for leg in leg_data if leg['PassedByMGA']]
    else:
        filtered_leg_data = [leg for leg in leg_data if leg['ChapterNumber'] != '']

    df = pd.DataFrame.from_records(filtered_leg_data)

    seen_crossfiled_bill_numbers = list()
    df_rows_to_remove = list()

    print(f'Processing {df.shape[0]} rows for {session_year}...')
    for index, row in tqdm.tqdm(df.iterrows(), total=df.shape[0], desc=f'Processing {session_year} bills'):
        bill_number = row['BillNumber']
        if bill_number in seen_crossfiled_bill_numbers:
            df_rows_to_remove.append(index)
            continue
        crossfiled_bill_number = row['CrossfileBillNumber']
        seen_crossfiled_bill_numbers.append(crossfiled_bill_number)
        bill_url = f'https://mgaleg.maryland.gov/mgawebsite/Legislation/Details/{bill_number}?ys={session_year}rs'
        bill_response = requests.get(bill_url, headers=headers)
        bill_response.raise_for_status()
        soup = BeautifulSoup(bill_response.content, 'html.parser')

        all_tables = soup.find_all('table')

        last_bill_link = None
        subsequent_amd_links = dict()
        if len(all_tables) > 1:
            target_table = all_tables[1]
            anchors = target_table.find_all('a', href=True)

            bill_prefix = f'/{session_year}RS/bills/'
            chapter_prefix = f'/{session_year}RS/Chapters'
            amd_prefix = f'/{session_year}RS/amds/'

            for anchor in anchors:
                href = anchor['href']
                if href.startswith(bill_prefix) or href.startswith(chapter_prefix):
                    last_bill_link = href
                    subsequent_amd_links = dict() # Reset amd links when a new bill link is found
                elif href.startswith(amd_prefix):
                    # Only collect amd links if they appear after a bill link and were adopted and not subsequently withdrawn
                    if last_bill_link is not None:
                        amendment_id = anchor.text.replace("/","_")
                        if 'Adopted' in anchor.parent.text:
                            subsequent_amd_links[amendment_id] = href
                        elif 'Withdrawn' in anchor.parent.text:
                            try:
                                del subsequent_amd_links[amendment_id]
                            except KeyError:
                                pass
        else:
            print(f"Warning: Could not find the second table for bill {bill_number} at {bill_url}")
        if last_bill_link:
            print(f"Found {len(subsequent_amd_links.keys()) + 1} PDFs to download for {bill_number}.")
            pdf_output_dir = f'data/{session_year}rs/pdf'
            os.makedirs(pdf_output_dir, exist_ok=True)

            # Download the main bill PDF
            bill_pdf_url = f'https://mgaleg.maryland.gov{last_bill_link}'
            bill_pdf_path = os.path.join(pdf_output_dir, f'{bill_number}.pdf')
            if not os.path.exists(bill_pdf_path):
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
            for amd_id, amd_link in subsequent_amd_links.items():
                amd_pdf_url = f'https://mgaleg.maryland.gov{amd_link}'
                amd_pdf_path = os.path.join(pdf_output_dir, f'{bill_number}_amd{amd_id}.pdf')
                if not os.path.exists(amd_pdf_path):
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
    print(f"Removing {len(df_rows_to_remove)} crossfiled bills.")
    df.drop(df_rows_to_remove, inplace=True)
    print(f'Finished processing {session_year}.')

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