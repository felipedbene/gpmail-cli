
import os, json, base64, argparse
from email.mime.text import MIMEText
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from openai import OpenAI
from google.auth.transport.requests import Request
from dotenv import load_dotenv
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify'
]
TOKEN_PATH = 'token.json'   

load_dotenv()         # load configuration from .env
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY; check your .env")

def get_credentials():
    creds = None
    # 1) Load cached credentials if they exist
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    # 2) If no creds or expired, refresh or re-run the flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
        # 3) Save the fresh credentials back to token.json
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return creds

def extract_plain_text(message):
    payload = message.get('payload', {})
    if payload.get('mimeType') == 'text/plain' and payload.get('body', {}).get('data'):
        return base64.urlsafe_b64decode(payload['body']['data']).decode()
    for part in payload.get('parts', []):
        if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
            return base64.urlsafe_b64decode(part['body']['data']).decode()
    return ""

def get_header(message, name):
    for h in message['payload'].get('headers', []):
        if h['name'].lower() == name.lower():
            return h['value']
    return ""

def main(auto_send: bool = False):
    creds   = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    client = OpenAI(api_key=OPENAI_KEY)

    print("Looking for unread messages...")
    gmail_resp = service.users().messages().list(userId='me', q='is:unread').execute()
    messages = gmail_resp.get('messages', [])
    print(f"Found {len(messages)} unread message(s)")
    if not messages:
        return
    for item in messages:
        msg     = service.users().messages().get(userId='me', id=item['id'], format='full').execute()
        sender  = get_header(msg, 'From')
        subject = get_header(msg, 'Subject')
        body    = extract_plain_text(msg)

        print(f"Processing '{subject}' from {sender}...")

        # Single GPT call: decide + draft
        system = {
            "role": "system",
            "content": (
                "You’re an email-assistant that both decides whether an email needs a reply "
                "and, if so, drafts it.  "
                "Output valid JSON with exactly two keys: "
                "  • should_reply: \"YES\" or \"NO\"  "
                "  • draft_reply: the reply text if should_reply is YES, otherwise empty string."
            )
        }
        user = {
            "role": "user",
            "content": f"From: {sender}\nSubject: {subject}\n\n{body}"
        }

        try:
            chat_resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[system, user],
            )

            assistant_content = chat_resp.choices[0].message.content
            data = json.loads(assistant_content)
            if not isinstance(data, dict):
                raise ValueError("assistant reply must be an object")
            if "should_reply" not in data or "draft_reply" not in data:
                raise ValueError("Missing keys in assistant response")
            result = {
                "should_reply": data.get("should_reply", "").strip(),
                "draft_reply": data.get("draft_reply", ""),
            }

        except Exception as e:
            print(f"! Error parsing assistant response: {e}")
            result = {"should_reply": "NO", "draft_reply": ""}

        if result["should_reply"] == "YES":
            draft = result["draft_reply"].strip()
            print("GPT suggests replying.")
            print(f"\nFrom: {sender}\nSubject: {subject}\n\nDraft:\n{draft}\n")
            send_it = auto_send
            if not auto_send:
                send_it = input("Send? (y/N) ").lower().startswith('y')
            if send_it:
                mime = MIMEText(draft)
                mime['To'] = sender
                mime['Subject'] = "Re: " + subject
                raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
                print("Sending reply...")
                service.users().messages().send(userId='me', body={'raw': raw}).execute()
                print("✔ Sent!\n")
            else:
                print("✘ Skipped.\n")
        else:
            print("No reply needed according to GPT.")
            # mark as read to skip
            service.users().messages().modify(
                userId='me',
                id=msg['id'],
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print("Marked as read.\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process unread Gmail messages with GPT.')
    parser.add_argument('--auto-send', action='store_true', help='Send replies without confirmation')
    args = parser.parse_args()
    main(auto_send=args.auto_send)
