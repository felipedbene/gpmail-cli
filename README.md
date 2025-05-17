# gpmail-cli

A small command-line tool that processes unread Gmail messages with GPT and optionally sends replies.

## Prerequisites

- **Python 3.10+**
- **Gmail API credentials**: download `credentials.json` for a desktop OAuth client with Gmail scopes (`gmail.readonly`, `gmail.compose`, `gmail.modify`).
- **Environment file**: create a `.env` containing your `OPENAI_API_KEY`.

### Gmail API Setup
1. Create a Google Cloud project and enable the Gmail API.
2. Configure an OAuth client ID for a desktop application and place the downloaded `credentials.json` in this directory.
3. On first run, you will be prompted to authorize access; tokens are cached in `token.json`.

## Installation

It is recommended to use a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required packages:

```bash
pip install google-api-python-client google-auth google-auth-oauthlib openai python-dotenv
```

## Usage

Create a `.env` file containing:

```bash
OPENAI_API_KEY=YOUR_KEY_HERE
```

Then run the CLI:

```bash
python cli.py [--auto-send]
```

Use `--auto-send` to send replies automatically without manual confirmation.

The script checks your unread emails, uses GPT to decide if a response is needed and, when appropriate, drafts a reply for you to send.
Replies are written in the same language as the incoming email. Messages that are detected as spam or marketing are automatically reported to Gmail instead of just being marked read.
