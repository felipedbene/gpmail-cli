
import os, json, argparse, re, base64
from datetime import datetime, timedelta, UTC
from email.mime.text import MIMEText
from openai import OpenAI
from dotenv import load_dotenv
from collections import defaultdict
from googleapiclient.discovery import build
from utils.gmail_utils import get_credentials, get_header, extract_plain_text, get_thread_messages, is_important, is_mailing_list, get_or_create_label, search_messages
from utils.ai_utils import categorize_email, detect_sentiment, extract_entities, summarize_text
from utils.analytics_utils import identify_key_participants, generate_timeline
load_dotenv()         # load configuration from .env
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY; check your .env")

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

def build_enhanced_thread_context(messages, current_id, client, max_messages=8):
    """Build an enhanced context with semantic analysis of previous messages."""
    prior = [m for m in messages if m['id'] != current_id]
    prior = prior[-max_messages:]
    parts = []
    
    for m in prior:
        sender = get_header(m, 'From')
        subject = get_header(m, 'Subject')
        body = extract_plain_text(m)
        
        # Get category and sentiment for each message
        category_info = categorize_email(sender, subject, body, client)
        sentiment_info = detect_sentiment(sender, subject, body, client)
        
        context_part = f"From: {sender}\nSubject: {subject}\nCategory: {category_info['category']} (confidence: {category_info['confidence']:.2f})\nSentiment: {sentiment_info['sentiment']} (intensity: {sentiment_info['intensity']:.2f})\n\n{body}"
        parts.append(context_part)
    
    return "\n\n---\n\n".join(parts)

def summarize_threads(query, output_path, client, service, include_entities=True, include_timeline=True, max_threads=5):
    """Summarize multiple email threads based on a search query."""
    print(f"Searching for threads with query: {query}")
    
    try:
        # Get all messages matching the query
        search_results = search_messages(service, query)
        if not search_results:
            print('No messages found for query.')
            return

        # Group messages by thread ID
        threads = {}
        for msg in search_results:
            thread_id = msg['threadId']
            if thread_id not in threads:
                threads[thread_id] = []
            threads[thread_id].append(msg)
        
        print(f"Found {len(threads)} threads with {len(search_results)} total messages")
        
        # Limit to max_threads
        thread_ids = list(threads.keys())[:max_threads]
        print(f"Processing {len(thread_ids)} threads (limited to {max_threads})")
        
        all_thread_summaries = []
        all_participants = []
        
        for i, thread_id in enumerate(thread_ids):
            try:
                print(f"\nProcessing thread {i+1}/{len(thread_ids)}...")
                messages = get_thread_messages(service, thread_id)
                
                # Extract thread metadata
                participants = identify_key_participants(messages, get_header)
                timeline = generate_timeline(messages, get_header) if include_timeline else []
                all_participants.extend(participants)
                
                thread_summaries = []
                thread_entities = {
                    "people": [],
                    "organizations": [],
                    "dates": [],
                    "action_items": []
                }
                
                for msg in messages:
                    try:
                        sender = get_header(msg, 'From')
                        subject = get_header(msg, 'Subject')
                        received_ts = int(msg.get('internalDate', '0')) / 1000
                        received_dt = datetime.fromtimestamp(received_ts, UTC)
                        body = extract_plain_text(msg)
                        
                        # Get summary
                        print(f"Generating summary for message: {subject[:50]}...")
                        summary = summarize_text(client, body)
                        
                        # Get category
                        print(f"Categorizing email: {subject[:50]}...")
                        category = categorize_email(sender, subject, body, client)['category']
                        
                        # Extract entities if requested
                        entities = extract_entities(body, client) if include_entities else {}
                        if include_entities:
                            thread_entities["people"].extend(entities.get("people", []))
                            thread_entities["organizations"].extend(entities.get("organizations", []))
                            thread_entities["dates"].extend(entities.get("dates", []))
                            thread_entities["action_items"].extend(entities.get("action_items", []))
                        
                        thread_summaries.append({
                            'sender': sender,
                            'subject': subject,
                            'received': received_dt.isoformat(),
                            'summary': summary,
                            'category': category,
                            'entities': entities if include_entities else {}
                        })
                    except Exception as e:
                        print(f"Error processing message in thread {thread_id}: {e}")
                        continue

                # Generate thread overall summary
                print("Generating overall thread summary...")
                overall_text = '\n\n'.join([f"From: {s['sender']}\nSubject: {s['subject']}\nCategory: {s['category']}\n{s['summary']}" for s in thread_summaries])
                overall_summary = summarize_text(client, overall_text)
                
                all_thread_summaries.append({
                    'thread_id': thread_id,
                    'messages': len(messages),
                    'participants': participants,
                    'timeline': timeline,
                    'summaries': thread_summaries,
                    'entities': thread_entities,
                    'overall_summary': overall_summary
                })
            except Exception as e:
                print(f"Error processing thread {thread_id}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Write output file
        print("Writing output file...")
        with open(output_path, 'w') as f:
            f.write(f"# Multiple Thread Summary\n\n")
            f.write(f"Query: {query}\n")
            f.write(f"Threads processed: {len(thread_ids)}\n")
            f.write(f"Total messages: {sum(t['messages'] for t in all_thread_summaries)}\n\n")
            
            # Key participants across all threads
            f.write(f"## Key Participants\n")
            participant_counts = {}
            for participant, count in all_participants:
                if participant not in participant_counts:
                    participant_counts[participant] = 0
                participant_counts[participant] += count
            sorted_participants = sorted(participant_counts.items(), key=lambda x: x[1], reverse=True)
            for participant, count in sorted_participants[:10]:  # Top 10 participants
                f.write(f"- {participant} ({count} messages)\n")
            f.write(f"\n")
            
            # Individual thread summaries
            f.write(f"## Thread Summaries\n")
            for i, thread_summary in enumerate(all_thread_summaries):
                f.write(f"### Thread {i+1}\n")
                f.write(f"Messages: {thread_summary['messages']}\n")
                f.write(f"Participants: {len(thread_summary['participants'])}\n\n")
                
                # Message summaries for this thread
                for s in thread_summary['summaries']:
                    f.write(f"#### {s['subject']} ({s['received']})\n")
                    f.write(f"From: {s['sender']}\n")
                    f.write(f"Category: {s['category']}\n\n")
                    f.write(f"{s['summary']}\n\n")
                    
                    # Message-specific entities
                    if include_entities and s['entities']:
                        entities = s['entities']
                        if entities.get("action_items"):
                            f.write(f"Action items:\n")
                            for action in entities["action_items"]:
                                f.write(f"- {action}\n")
                            f.write(f"\n")
                
                # Thread overall narrative
                f.write(f"##### Thread Narrative\n\n{thread_summary['overall_summary']}\n\n")
            
            # Overall summary across all threads
            f.write(f"## Overall Summary\n")
            all_narratives = [t['overall_summary'] for t in all_thread_summaries]
            combined_narrative_text = '\n\n'.join(all_narratives)
            final_overall_summary = summarize_text(client, f"Summarize these thread summaries:\n\n{combined_narrative_text}")
            f.write(f"{final_overall_summary}\n")

        print(f"Summary written to {output_path}")
    except Exception as e:
        print(f"Error in summarize_threads: {e}")
        import traceback
        traceback.print_exc()


def main(auto_send: bool = False, max_age_days: int = 7, enable_enhanced: bool = True, 
         summarize_query: str = None, output_path: str = "thread_summary.md", 
         disable_entities: bool = False, disable_timeline: bool = False, no_age_limit: bool = False):
    
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    client = OpenAI(api_key=OPENAI_KEY)
    
    # Handle thread summarization mode
    if summarize_query:
        summarize_threads(
            query=summarize_query,
            output_path=output_path,
            client=client,
            service=service,
            include_entities=not disable_entities,
            include_timeline=not disable_timeline
        )
        return
    
    # Handle email processing mode (original functionality)
    label_id = get_or_create_label(service, 'HumanActionNeeded-GPT')
    cutoff  = datetime.now(UTC) - timedelta(days=max_age_days) if not no_age_limit else None

    print("Looking for unread messages...")
    gmail_resp = service.users().messages().list(userId='me', q='is:unread').execute()
    messages = gmail_resp.get('messages', [])
    print(f"Found {len(messages)} unread message(s)")
    if not messages:
        return
        
    # Track email statistics
    stats = {
        "total_processed": 0,
        "replied": 0,
        "skipped": 0,
        "categories": defaultdict(int),
        "sentiments": defaultdict(int)
    }
    
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
        if cutoff and received_dt and received_dt < cutoff:
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
        
        # Enhanced intelligence features
        if enable_enhanced:
            # Categorize the email
            category_info = categorize_email(sender, subject, body, client)
            print(f"Category: {category_info['category']} (confidence: {category_info['confidence']:.2f})")
            stats["categories"][category_info['category']] += 1
            
            # Detect sentiment
            sentiment_info = detect_sentiment(sender, subject, body, client)
            print(f"Sentiment: {sentiment_info['sentiment']} (intensity: {sentiment_info['intensity']:.2f})")
            stats["sentiments"][sentiment_info['sentiment']] += 1
            
            # Extract entities
            entities = extract_entities(body, client)
            if entities["action_items"]:
                print(f"Action items detected: {len(entities['action_items'])}")
            
            # Build enhanced context
            context = build_enhanced_thread_context(thread_msgs, msg['id'], client)
        else:
            # Use original context building
            context = build_thread_context(thread_msgs, msg['id'])

        print(f"Processing '{subject}' from {sender}...")

        # Enhanced GPT call with more detailed instructions
        system = {
            "role": "system",
            "content": (
                "You are an intelligent email assistant with advanced capabilities. "
                "When a reply is required, draft it in the same language as the original email. "
                "Consider the email category, sentiment, and any action items when deciding to reply. "
                "Output valid JSON with exactly four keys: "
                "  • should_reply: \"YES\" or \"NO\"  "
                "  • draft_reply: the reply text in the same language if should_reply is YES, otherwise empty string. "
                "  • reason: a short explanation if should_reply is NO, otherwise empty string."
                "  • priority: \"high\", \"medium\", or \"low\" indicating response urgency"
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
                "priority": data.get("priority", "medium"),
            }

        except Exception as e:
            print(f"! Error parsing assistant response: {e}")
            result = {"should_reply": "NO", "draft_reply": "", "reason": "", "priority": "medium"}

        stats["total_processed"] += 1
        
        if result["should_reply"] == "YES":
            draft = result["draft_reply"].strip()
            priority = result.get("priority", "medium")
            print(f"GPT suggests replying (Priority: {priority.upper()}).")
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
                stats["replied"] += 1
            else:
                print("✘ Skipped.\n")
                stats["skipped"] += 1
        else:
            reason = result.get("reason", "").strip()
            priority = result.get("priority", "medium")
            if reason:
                print(f"No reply needed according to GPT (Priority: {priority.upper()}) because {reason}.")
            else:
                print(f"No reply needed according to GPT (Priority: {priority.upper()}).")
            service.users().messages().modify(
                userId='me',
                id=msg['id'],
                body={'removeLabelIds': ['UNREAD'], 'addLabelIds': [label_id]}
            ).execute()
            print("Marked as read.\n")
            stats["skipped"] += 1
    
    # Print statistics
    print("\n--- Processing Summary ---")
    print(f"Total processed: {stats['total_processed']}")
    print(f"Replied: {stats['replied']}")
    print(f"Skipped: {stats['skipped']}")
    print("\nCategories:")
    for category, count in stats["categories"].items():
        print(f"  {category}: {count}")
    print("\nSentiments:")
    for sentiment, count in stats["sentiments"].items():
        print(f"  {sentiment}: {count}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process unread Gmail messages with GPT or summarize email threads.')
    parser.add_argument('--auto-send', action='store_true', help='Send replies without confirmation (email processing mode only)')
    parser.add_argument('--max-age-days', type=int, default=7,
                        help='Ignore unread messages older than this many days (email processing mode only)')
    parser.add_argument('--disable-enhanced', action='store_true', 
                        help='Disable enhanced intelligence features')
    parser.add_argument('--no-age-limit', action='store_true',
                        help='Process all unread messages regardless of age (email processing mode only)')
    
    # Thread summarization arguments
    parser.add_argument('--summarize', type=str, metavar='QUERY',
                        help='Summarize an email thread matching the given Gmail search query')
    parser.add_argument('--output', type=str, default='thread_summary.md',
                        help='Output file path for thread summary (default: thread_summary.md)')
    parser.add_argument('--no-entities', action='store_true',
                        help='Disable entity extraction for thread summarization')
    parser.add_argument('--no-timeline', action='store_true',
                        help='Disable timeline generation for thread summarization')
    
    args = parser.parse_args()
    
    if args.summarize:
        # Run in thread summarization mode
        main(
            summarize_query=args.summarize,
            output_path=args.output,
            disable_entities=args.no_entities,
            disable_timeline=args.no_timeline
        )
    else:
        # Run in email processing mode (original functionality)
        main(
            auto_send=args.auto_send,
            max_age_days=args.max_age_days,
            enable_enhanced=not args.disable_enhanced,
            no_age_limit=args.no_age_limit
        )
