import os
import json
import logging
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from urllib.parse import urlparse
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv(override=True)

API_KEY = os.getenv('YOUTUBE_DATA_API_KEY')
if not API_KEY:
    raise ValueError("YOUTUBE_DATA_API_KEY not found in environment variables")

YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
CSV_PATH = os.path.join(DATA_DIR, 'YouTube Channels - Committee.csv')
OUTPUT_DIR = os.path.join(DATA_DIR, 'youtube')

def get_channel_id_from_handle(youtube, handle):
    try:
        request = youtube.channels().list(
            part='contentDetails',
            forHandle=handle
        )
        response = request.execute()
        
        if 'items' in response and len(response['items']) > 0:
            return response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        else:
            logging.warning(f"No channel found for handle: {handle}")
            return None
    except HttpError as e:
        if e.resp.status == 403 and 'quotaExceeded' in str(e.content):
            logging.critical("YouTube API quota exceeded. Stopping execution.")
            exit(1)
        logging.error(f"An HTTP error occurred: {e.resp.status} {e.content}")
        return None
def get_uploads_playlist_id(youtube, channel_url):
    # Parse handle from URL
    path = urlparse(channel_url).path
    if path.startswith('/@'):
        handle = path[1:] # remove leading /
        return get_channel_id_from_handle(youtube, handle)
    else:
        # Fallback for custom URLs or channel IDs if needed
        logging.warning(f"Could not parse handle from URL: {channel_url}")
        return None

def save_videos(videos, output_path):
    # Sort videos by date (latest first) before saving
    # Handle cases where video_date might be missing (unlikely from API but good for safety)
    videos.sort(key=lambda x: x.get('video_date', ''), reverse=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    logging.info(f"Saved {len(videos)} videos to {output_path}")

def get_all_videos_from_playlist(youtube, playlist_id, existing_urls, output_path, current_videos):
    next_page_token = None
    new_videos_count = 0
    
    while True:
        try:
            request = youtube.playlistItems().list(
                part='snippet',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            
            page_videos = []
            stop_fetching = False
            
            for item in response.get('items', []):
                snippet = item['snippet']
                video_id = snippet['resourceId']['videoId']
                video_url = f'https://www.youtube.com/watch?v={video_id}'
                
                if video_url in existing_urls:
                    logging.info(f"Found existing video {video_url}, stopping fetch for this channel.")
                    stop_fetching = True
                    break
                
                video_data = {
                    'video_title': snippet['title'],
                    'video_url': video_url,
                    'video_description': snippet.get('description', ''),
                    'video_date': snippet.get('publishedAt', '')
                }
                page_videos.append(video_data)
                existing_urls.add(video_url)
            
            if page_videos:
                current_videos.extend(page_videos)
                new_videos_count += len(page_videos)
                save_videos(current_videos, output_path)

            if stop_fetching:
                break

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
                
        except HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e.content):
                logging.critical("YouTube API quota exceeded. Stopping execution.")
                exit(1)
            logging.error(f"An error occurred while fetching playlist items: {e}")
            break
            
    return current_videos, new_videos_count

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=API_KEY)
    
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        logging.error(f"CSV file not found at {CSV_PATH}")
        return

    for index, row in df.iterrows():
        committee_name = row['Name']
        channel_url = row['YouTube channel']
        
        logging.info(f"Processing {committee_name} ({channel_url})")
        
        output_filename = f"{committee_name}_youtube_videos.json"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        current_videos = []
        existing_urls = set()
        
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    current_videos = json.load(f)
                    existing_urls = {v['video_url'] for v in current_videos}
                logging.info(f"Loaded {len(current_videos)} existing videos.")
            except json.JSONDecodeError:
                logging.warning(f"Could not decode {output_path}, starting fresh.")
        
        uploads_playlist_id = get_uploads_playlist_id(youtube, channel_url)
        
        if uploads_playlist_id:
            updated_videos, new_count = get_all_videos_from_playlist(youtube, uploads_playlist_id, existing_urls, output_path, current_videos)
            logging.info(f"Finished {committee_name}. Added {new_count} new videos.")
        else:
            logging.warning(f"Skipping {committee_name} due to missing playlist ID")

if __name__ == "__main__":
    main()
