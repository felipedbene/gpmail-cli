import os
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify'
]
TOKEN_PATH = 'token.json'

def get_credentials(scopes=None):
    """Get Gmail API credentials."""
    if scopes is None:
        scopes = SCOPES
        
    creds = None
    # 1) Load cached credentials if they exist
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes)
    # 2) If no creds or expired, refresh or re-run the flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', scopes)
            creds = flow.run_local_server(port=0, open_browser=False)
        # 3) Save the fresh credentials back to token.json
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return creds

def get_header(message, name):
    """Extract a header from a Gmail message."""
    for h in message['payload'].get('headers', []):
        if h['name'].lower() == name.lower():
            return h['value']
    return ""

def extract_plain_text(message):
    """Extract plain text content from a Gmail message."""
    def _extract_text_from_part(part):
        """Recursively extract text from a message part."""
        if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
            return base64.urlsafe_b64decode(part['body']['data']).decode()
        elif 'parts' in part:
            # Handle nested multipart messages
            for sub_part in part['parts']:
                text = _extract_text_from_part(sub_part)
                if text:
                    return text
        return ""
    
    payload = message.get('payload', {})
    return _extract_text_from_part(payload)

def get_thread_messages(service, thread_id):
    """Return messages in the thread sorted chronologically."""
    thread = service.users().threads().get(
        userId='me', id=thread_id, format='full'
    ).execute()
    msgs = thread.get('messages', [])
    msgs.sort(key=lambda m: int(m.get('internalDate', '0')))
    return msgs

def search_messages(service, query):
    """Search for messages matching a query."""
    resp = service.users().messages().list(userId='me', q=query).execute()
    return resp.get('messages', [])

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
