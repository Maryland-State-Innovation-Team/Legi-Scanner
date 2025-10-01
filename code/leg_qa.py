# Remote server Ollama install
# curl -fsSL https://ollama.com/install.sh | sh
# pip install ollama python-dotenv pydantic pandas google-genai openai

import os
import sys
import json
import argparse
from time import sleep
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from google import genai
import ollama
from ollama import chat
from ollama import ChatResponse
from pydantic import BaseModel
from typing import Literal, Optional
from tqdm import tqdm
import time
from llm_utils import query_llm_with_retries


question_dict = {
    'bill_summary': 'Write a brief, plain-English summary of the bill.',
    'programmatic': 'Does this bill establish a distinct service, initiative, or intervention for the public? Answer False if it mainly changes rules, fees, definitions, or legal processes.',
    'program_start_year': 'What year do the programs described in the bill start?',
    'program_end_year': 'What year do the programs described in the bill end?',
    'funding': 'How much money in total has been allocated for the programs? (if millions, write out full number. E.g. "1 million" should be 1000000)',
    'responsible_party': 'What Maryland State agency, department, office, or role is responsible for implementing the programs?',
    'stakeholders': 'What population will be impacted by the bill?',
    'innovative_summary': 'How innovative (employing new technologies or new approaches to government) is the program?',
    'innovative_score': 'How innovative is the program on a scale from 1 to 10, with 10 being the most innovative?',
    'child_poverty_direct_summary': 'How high is the potential for the program to have a direct impact on child poverty?',
    'child_poverty_direct_score': 'How high is the potential for the program to have a direct impact on child poverty on a scale from 1 to 10, with 10 being highest potential?',
}


SYSTEM_PROMPT = (
    "You are reading markdown generated from the text of a bill passed by the Maryland General Assembly. "
    "Please note that the strikethrough syntax (~~) means a word or section should be ignored. "
    "Your goal is to read the markdown carefully, and then answer the following questions:\n"
    "{}\n"
    "Please respond with only valid JSON in the specified format."
)
SYSTEM_PROMPT = SYSTEM_PROMPT.format(
    "\n".join([f"- {key}: {value}" for key, value in question_dict.items()])
)


class AnswersToQuestions(BaseModel):
    bill_summary: str
    programmatic: bool
    program_start_year: Optional[int] = None
    program_end_year: Optional[int] = None
    funding: Optional[float] = None
    responsible_party: str
    stakeholders: str
    innovative_summary: str
    innovative_score: int
    child_poverty_direct_summary: str
    child_poverty_direct_score: int


def main(args):
    load_dotenv()
    model_family = args.model_family.lower()
    # Set default model names if not provided
    if args.model is None:
        if model_family == 'gemini':
            model_name = 'gemini-2.5-flash'
        elif model_family == 'gpt':
            model_name = 'gpt-4.1-nano'
        else:
            model_name = 'phi4'
    else:
        model_name = args.model

    if model_family == 'gemini':
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if GEMINI_API_KEY is None:
            print("Please provide a GEMINI_API_KEY in a .env file.")
            return
        client = genai.Client(api_key=GEMINI_API_KEY)
    elif model_family == 'gpt':
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        if OPENAI_API_KEY is None:
            print("Please provide an OPENAI_API_KEY in a .env file.")
            return
        client = OpenAI(api_key=OPENAI_API_KEY)
    else:  # Assume all other models are served via ollama
        print(f"Pulling model: {model_name}")
        ollama.pull(model_name)
        client = chat

    csv_dir = os.path.abspath(f'data/{args.session_year}rs/csv')
    md_dir = os.path.abspath(f'data/{args.session_year}rs/md')
    csv_filepath = os.path.join(csv_dir, "legislation.csv")
    data = pd.read_csv(csv_filepath)
    data = data[['YearAndSession', 'BillNumber', 'Title', 'Synopsis']]
    bill_numbers = data['BillNumber'].values.tolist()

    model_responses = []
    for bill_number in tqdm(bill_numbers):
        bill_filepath = os.path.join(md_dir, f"{bill_number}_amended.md")
        if not os.path.exists(bill_filepath):
            bill_filepath = os.path.join(md_dir, f"{bill_number}.md")
        with open(bill_filepath, 'r', encoding='utf-8') as b_f:
            bill_md = b_f.read()
        model_response = query_llm_with_retries(
            client=client,
            prompt=SYSTEM_PROMPT,
            value=bill_md,
            response_format=AnswersToQuestions,
            model_name=model_name,
            max_retries=3,
            model_family=model_family
        )
        model_responses.append(model_response)

    response_df = pd.DataFrame.from_records(model_responses)
    combined_df = pd.concat([data.reset_index(drop=True), response_df.reset_index(drop=True)], axis=1)
    output_filepath = os.path.join(csv_dir, "legislation_model_responses.csv")
    combined_df.to_csv(output_filepath, index=False, encoding='utf-8')
    print(f"Saved model responses to {output_filepath}")
        

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='Legislative scan question answerer',
        description='A program to answer questions about legislation')
    parser.add_argument('--model-family', default='gemini', choices=['gpt', 'gemini', 'ollama'], help='The LLM backend family to use')
    parser.add_argument('--model', default=None, help='The model name to use (e.g., gpt-4.1-nano, gemini-2.5-flash, llama3, etc.)')
    parser.add_argument('session_year', type=int, help='The regular session year')
    args = parser.parse_args()
    main(args)