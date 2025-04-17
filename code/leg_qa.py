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
import google
from google import genai
from openai import OpenAI, OpenAIError
import ollama
from ollama import chat
from ollama import ChatResponse
from pydantic import BaseModel
from typing import Literal
from tqdm import tqdm
import time


question_dict = {
    'bill_summary': 'Write a brief, plain-English summary of the bill.',
    'programmatic': 'Does this bill establish a distinct service, initiative, or intervention for the public? Answer False if it mainly changes rules, fees, definitions, or legal processes.',
    'program_start_year': 'What year do the programs described in the bill start?',
    'program_end_year': 'What year do the programs described in the bill end?',
    'funding': 'How much money in total has been allocated for the programs? (if millions, write out full number. E.g. "1 million" should be 1000000)',
    'responsible_party': 'What Maryland State agency, department, office, or role is responsible for implementing the programs?',
    'stakeholders': 'What population will be impacted by the bill?',
    'innovative_summary': 'How innovative (employing new technologies or new approaches to government) is the program?',
    'innovative_score': 'How innovative is the program on a scale from 1 to 5, with 5 being the most innovative?',
    'child_poverty_direct_summary': 'How high is the potential for the program to have a direct impact on child poverty?',
    'child_poverty_direct_score': 'How high is the potential for the program to have a direct impact on child poverty on a scale from 1 to 5, with 5 being highest potential?',
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

GEMINI_SYSTEM_PROMPT = SYSTEM_PROMPT + "\nThe markdown follows below:\n\n{}"


class AnswersToQuestions(BaseModel):
    bill_summary: str
    programmatic: bool
    program_start_year: int
    program_end_year: int
    funding: float
    responsible_party: str
    stakeholders: str
    innovative_summary: str
    innovative_score: int
    child_poverty_direct_summary: str
    child_poverty_direct_score: int


def createFormattedPromptContents(model, value):
    if model == 'gemini':
        formattedPromptContents = GEMINI_SYSTEM_PROMPT.format(
            value
        )
    else:
        formattedPromptContents = [
            {
                'role': 'system',
                'content': SYSTEM_PROMPT,
            },
            {
                'role': 'user',
                'content': value,
            },
        ]
    return formattedPromptContents


def geminiClassify(client, model, value):
    sleep(4) # Free tier rate limit of 15 per minute
    formattedPromptContents = createFormattedPromptContents(model, value)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=formattedPromptContents,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': AnswersToQuestions,
                },
            )
            json_response = json.loads(response.text)
            return json_response
        except google.genai.errors.ServerError as e:
            print(f"Connection error: {e}")
            if attempt < max_retries - 1:
                sleep_duration = (2 ** attempt) * 1
                print(f"Retrying in {sleep_duration} seconds...")
                time.sleep(sleep_duration)
            else:
                print("Max retries reached.  Returning None.")
                return None
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Response text: {response.text}")
            if attempt < max_retries - 1:
                sleep_duration = (2 ** attempt) * 1
                print(f"Retrying in {sleep_duration} seconds...")
                time.sleep(sleep_duration)
            else:
                print("Max retries reached.  Returning None.")
                return None
    return None


def gptClassify(client, model, value):
    formattedPromptContents = createFormattedPromptContents(model, value)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            completion = client.beta.chat.completions.parse(
                model='gpt-4.1-nano-2025-04-14',
                messages=formattedPromptContents,
                response_format=AnswersToQuestions
            )
            json_response = completion.choices[0].message.parsed
            return json_response.model_dump()
        except OpenAIError as e:
            print(f"Connection error: {e}")
            if attempt < max_retries - 1:
                sleep_duration = (2 ** attempt) * 1
                print(f"Retrying in {sleep_duration} seconds...")
                time.sleep(sleep_duration)
            else:
                print("Max retries reached.  Returning None.")
                return None
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Response text: {response.text}")
            if attempt < max_retries - 1:
                sleep_duration = (2 ** attempt) * 1
                print(f"Retrying in {sleep_duration} seconds...")
                time.sleep(sleep_duration)
            else:
                print("Max retries reached.  Returning None.")
                return None
    return None


def ollamaClassify(client, model, value):
    formattedPromptContents = createFormattedPromptContents(model, value)
    response: ChatResponse = client(
        model=model,
        format=AnswersToQuestions.model_json_schema(),
        messages=formattedPromptContents
    )
    parsed_response_content = json.loads(response.message.content)
    return parsed_response_content


def main(args):

    load_dotenv()
    if args.model == 'gemini':
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if GEMINI_API_KEY is None:
            print("Please provide a GEMINI_API_KEY in a .env file.")
            return
        client = genai.Client(api_key=GEMINI_API_KEY)
        classifyFunction = geminiClassify
    elif args.model == 'gpt':
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        if OPENAI_API_KEY is None:
            print("Please provide an OPENAI_API_KEY in a .env file.")
            return
        client = OpenAI(api_key = OPENAI_API_KEY)
        classifyFunction = gptClassify
    else: # Assume all other models are served via ollama
        print(f"Pulling model: {args.model}")
        ollama.pull(args.model)
        client = chat
        classifyFunction = ollamaClassify

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
        model_response = classifyFunction(client, args.model, bill_md)
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
    parser.add_argument('-m', '--model', default='gpt')
    parser.add_argument('session_year', type=int, help='The regular session year')
    args = parser.parse_args()
    main(args)