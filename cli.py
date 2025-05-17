
import os, json, base64, argparse
from datetime import datetime, timedelta, UTC
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

def get_thread_messages(service, thread_id):
    """Return messages in the thread sorted chronologically."""
    thread = service.users().threads().get(
        userId='me', id=thread_id, format='full'
    ).execute()
    msgs = thread.get('messages', [])
    msgs.sort(key=lambda m: int(m.get('internalDate', '0')))
    return msgs


def build_thread_context(messages, current_id, max_messages=5):
    """Build a text summary of previous messages in the thread."""
    prior = [m for m in messages if m['id'] != current_id]
    prior = prior[-max_messages:]
    parts = []
    for m in prior:
        sender = get_header(m, 'From')
        subject = get_header(m, 'Subject')
        body = extract_plain_text(m)
        parts.append(f"From: {sender}\nSubject: {subject}\n\n{body}")
    return "\n\n".join(parts)


def is_important(message):
    """Return True if Gmail marked this message as important."""
    return 'IMPORTANT' in message.get('labelIds', [])


def is_mailing_list(message):
    """Detect if the message is from a mailing list or newsletter."""
    labels = set(message.get('labelIds', []))
    if labels.intersection({'CATEGORY_PROMOTIONS', 'CATEGORY_FORUMS', 'CATEGORY_UPDATES', 'CATEGORY_SOCIAL'}):
        return True
    for h in message.get('payload', {}).get('headers', []):
        if h['name'].lower() in {'list-unsubscribe', 'list-id'}:
            return True
    return False

def get_or_create_label(service, name: str) -> str:
    """Return the Gmail label ID for ``name``, creating it if needed."""
    resp = service.users().labels().list(userId='me').execute()
    for lbl in resp.get('labels', []):
        if lbl.get('name') == name:
            return lbl['id']
    body = {
        'name': name,
        'labelListVisibility': 'labelShow',
        'messageListVisibility': 'show',
    }
    created = service.users().labels().create(userId='me', body=body).execute()
    return created['id']

def main(auto_send: bool = False, max_age_days: int = 7):
    creds   = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    label_id = get_or_create_label(service, 'HumanActionNeeded-GPT')
    client = OpenAI(api_key=OPENAI_KEY)
    cutoff  = datetime.now(UTC) - timedelta(days=max_age_days)

    print("Looking for unread messages...")
    gmail_resp = service.users().messages().list(userId='me', q='is:unread').execute()
    messages = gmail_resp.get('messages', [])
    print(f"Found {len(messages)} unread message(s)")
    if not messages:
        return
    for item in messages:
        msg = service.users().messages().get(userId='me', id=item['id'], format='full').execute()
        labels = set(msg.get('labelIds', []))
        if 'SPAM' in labels:
            print("Skipping spam message.")
            continue
        if not is_important(msg):
            service.users().messages().modify(
                userId='me', id=msg['id'], body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print("Skipping not-important message.")
            continue
        if is_mailing_list(msg):
            service.users().messages().modify(
                userId='me', id=msg['id'], body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print("Skipping mailing list or automated message.")
            continue

        received_ts = int(msg.get('internalDate', '0')) / 1000
        received_dt = datetime.fromtimestamp(received_ts, UTC) if received_ts else None
        if received_dt and received_dt < cutoff:
            service.users().messages().modify(
                userId='me',
                id=msg['id'],
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print(
                f"Skipping '{msg.get('snippet', '')[:30]}...' from {received_dt.date()} older than {max_age_days} days."
            )
            continue

        sender = get_header(msg, 'From')
        subject = get_header(msg, 'Subject')
        body = extract_plain_text(msg)

        thread_msgs = get_thread_messages(service, msg.get('threadId'))
        context = build_thread_context(thread_msgs, msg['id'])

        print(f"Processing '{subject}' from {sender}...")

        # Single GPT call: decide + draft
        system = {
            "role": "system",
            "content": (
                "You are an email assistant. "
                "When a reply is required, draft it in the same language as the original email. "
                "Output valid JSON with exactly three keys: "
                "  • should_reply: \"YES\" or \"NO\"  "
                "  • draft_reply: the reply text in the same language if should_reply is YES, otherwise empty string. "
                "  • reason: a short explanation if should_reply is NO, otherwise empty string."
            )
        }
        user_content = ""
        if context:
            user_content += f"Thread context:\n{context}\n\n"
        user_content += f"From: {sender}\nSubject: {subject}\n\n{body}"
        user = {
            "role": "user",
            "content": user_content,
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
            if (
                "should_reply" not in data
                or "draft_reply" not in data
                or "reason" not in data
            ):
                raise ValueError("Missing keys in assistant response")
            result = {
                "should_reply": data.get("should_reply", "").strip(),
                "draft_reply": data.get("draft_reply", ""),
                "reason": data.get("reason", ""),
            }

        except Exception as e:
            print(f"! Error parsing assistant response: {e}")
            result = {"should_reply": "NO", "draft_reply": "", "reason": ""}

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
            reason = result.get("reason", "").strip()
            if reason:
                print(f"No reply needed according to GPT because {reason}.")
            else:
                print("No reply needed according to GPT.")
            service.users().messages().modify(
                userId='me',
                id=msg['id'],
                body={'removeLabelIds': ['UNREAD'], 'addLabelIds': [label_id]}
            ).execute()
            print("Marked as read.\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process unread Gmail messages with GPT.')
    parser.add_argument('--auto-send', action='store_true', help='Send replies without confirmation')
    parser.add_argument('--max-age-days', type=int, default=7,
                        help='Ignore unread messages older than this many days')
    args = parser.parse_args()
    main(auto_send=args.auto_send, max_age_days=args.max_age_days)
