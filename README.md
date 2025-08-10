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
source venv/bin/activate  # On Windows: venv\Scripts\activate
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

### Process unread emails

```bash
python cli.py [--auto-send] [--max-age-days DAYS] [--disable-enhanced]
```

Use `--auto-send` to send replies automatically without manual confirmation.
`--max-age-days` controls how old unread messages can be before they are ignored (default: 7 days).
`--disable-enhanced` disables the enhanced intelligence features.

The script checks your unread emails labelled as **Important**, skips newsletters and mailing lists when Gmail identifies them, and uses GPT only to decide if a response is needed and draft a reply when appropriate.
Replies are written in the same language as the incoming email. When GPT decides no reply is needed, its reasoning is shown and the message is labeled `HumanActionNeeded-GPT` before being marked as read.

Enhanced intelligence features include:
- Email categorization (Urgent, Action Required, Informational, etc.)
- Sentiment analysis
- Entity extraction (people, organizations, dates, action items)
- Priority ranking
- Processing statistics and analytics

### Summarize an email thread

To generate a Markdown summary of a specific email thread, search by sender or subject with:

```bash
python cli.py --summarize "from:someone@example.com" [--output summary.md] [--no-entities] [--no-timeline]
```

The script finds the first matching thread, orders messages chronologically, and provides:
- Key participants identification
- Timeline of events
- Entity extraction (people, organizations, dates, action items)
- Categorization of each message
- Individual message summaries
- Overall narrative summary

Use `--no-entities` to disable entity extraction.
Use `--no-timeline` to disable timeline generation.
