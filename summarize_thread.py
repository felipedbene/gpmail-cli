#!/usr/bin/env python3

import os
import base64
import argparse
from datetime import datetime, UTC
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from openai import OpenAI

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
]
TOKEN_PATH = 'token.json'

load_dotenv()
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_KEY:
    raise RuntimeError('Missing OPENAI_API_KEY; check your .env')


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return creds


def get_header(message, name):
    for h in message['payload'].get('headers', []):
        if h['name'].lower() == name.lower():
            return h['value']
    return ''


def extract_plain_text(message):
    payload = message.get('payload', {})
    if payload.get('mimeType') == 'text/plain' and payload.get('body', {}).get('data'):
        return base64.urlsafe_b64decode(payload['body']['data']).decode()
    for part in payload.get('parts', []):
        if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
            return base64.urlsafe_b64decode(part['body']['data']).decode()
    return ''


def search_messages(service, query):
    resp = service.users().messages().list(userId='me', q=query).execute()
    return resp.get('messages', [])


def get_thread_messages(service, thread_id):
    thread = service.users().threads().get(userId='me', id=thread_id, format='full').execute()
    msgs = thread.get('messages', [])
    msgs.sort(key=lambda m: int(m.get('internalDate', '0')))
    return msgs


def summarize_text(client, text):
    system = {
        'role': 'system',
        'content': (
            'You summarize emails. Return a short summary of the user provided text.'
        ),
    }
    user = {'role': 'user', 'content': text}
    resp = client.chat.completions.create(model='gpt-3.5-turbo', messages=[system, user])
    return resp.choices[0].message.content.strip()


def summarize_thread(query, output_path):
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    client = OpenAI(api_key=OPENAI_KEY)

    search_results = search_messages(service, query)
    if not search_results:
        print('No messages found for query.')
        return

    thread_id = search_results[0]['threadId']
    messages = get_thread_messages(service, thread_id)

    summaries = []
    for msg in messages:
        sender = get_header(msg, 'From')
        subject = get_header(msg, 'Subject')
        received_ts = int(msg.get('internalDate', '0')) / 1000
        received_dt = datetime.fromtimestamp(received_ts, UTC)
        body = extract_plain_text(msg)
        summary = summarize_text(client, body)
        summaries.append({
            'sender': sender,
            'subject': subject,
            'received': received_dt.isoformat(),
            'summary': summary,
        })

    overall_text = '\n\n'.join([f"From: {s['sender']}\nSubject: {s['subject']}\n{ s['summary']}" for s in summaries])
    overall_summary = summarize_text(client, overall_text)

    with open(output_path, 'w') as f:
        f.write(f"# Thread summary\n\n")
        f.write(f"Query: {query}\n\n")
        for s in summaries:
            f.write(f"## {s['subject']} ({s['received']})\n")
            f.write(f"From: {s['sender']}\n\n{s['summary']}\n\n")
        f.write(f"# Narrative\n\n{overall_summary}\n")

    print(f"Summary written to {output_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Summarize an email thread by sender or subject query.')
    parser.add_argument('query', help='Gmail search query to find the thread')
    parser.add_argument('--output', default='thread_summary.md', help='Path to output markdown file')
    args = parser.parse_args()
    summarize_thread(args.query, args.output)
