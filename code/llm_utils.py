# LLM (OpenAI/Gemini) helpers for plan areas pipeline

import os
import json
import time
import tiktoken
from openai import OpenAI, OpenAIError
import google
from google import genai
from google.genai.types import GenerateContentConfig
import ollama
from ollama import chat
from ollama import ChatResponse

def query_llm_with_retries(client, prompt, value, response_format, model_name, max_retries=5, model_family='gemini'):
    """
    Query Gemini, OpenAI (GPT), or Ollama LLM with retries and error handling. Returns parsed JSON or None.
    model_family: 'gemini', 'gpt', or 'ollama'
    """
    for attempt in range(max_retries):
        try:
            if model_family == 'ollama':
                formattedPromptContents = [
                    {'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': value},
                ]
                response = client(
                    model=model_name,
                    format=response_format.model_json_schema() if hasattr(response_format, 'model_json_schema') else response_format,
                    messages=formattedPromptContents,
                    options={'temperature': 0.2}
                )
                parsed_response_content = json.loads(response.message.content)
                return parsed_response_content
            elif model_family == 'gemini':
                response = client.models.generate_content(
                    model=model_name,
                    contents=value,
                    config=GenerateContentConfig(
                        system_instruction=prompt,
                        response_mime_type='application/json',
                        response_schema=response_format
                    ),
                )
                return json.loads(response.text)
            elif model_family == 'gpt':
                response = client.beta.chat.completions.parse(
                    model=model_name,
                    messages=[
                        {'role': 'system', 'content': prompt},
                        {'role': 'user', 'content': value},
                    ],
                    response_format=response_format
                )
                return response.choices[0].message.parsed.model_dump()
            else:
                raise ValueError(f"Unknown model_family: {model_family}")
        except (google.genai.errors.ServerError, OpenAIError) as e:
            print(f"Connection error: {e}")
            if attempt < max_retries - 1:
                sleep_duration = (2 ** attempt) * 1
                print(f"Retrying in {sleep_duration} seconds...")
                time.sleep(sleep_duration)
            else:
                print("Max retries reached. Returning None.")
                return None
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            if attempt < max_retries - 1:
                sleep_duration = (2 ** attempt) * 1
                print(f"Retrying in {sleep_duration} seconds...")
                time.sleep(sleep_duration)
            else:
                print("Max retries reached. Returning None.")
                return None
        except Exception as e:
            # For Ollama or any other unexpected error
            print(f"Unexpected error: {e}")
            if attempt < max_retries - 1:
                sleep_duration = (2 ** attempt) * 1
                print(f"Retrying in {sleep_duration} seconds...")
                time.sleep(sleep_duration)
            else:
                print("Max retries reached. Returning None.")
                return None
    return None
