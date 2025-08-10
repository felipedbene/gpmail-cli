from datetime import datetime, UTC
from collections import defaultdict, Counter

def identify_key_participants(messages, get_header_func):
    """Identify key participants in the thread."""
    participants = {}
    for msg in messages:
        sender = get_header_func(msg, 'From')
        if sender not in participants:
            participants[sender] = 0
        participants[sender] += 1
    # Sort by message count
    sorted_participants = sorted(participants.items(), key=lambda x: x[1], reverse=True)
    return sorted_participants[:5]  # Top 5 participants

def generate_timeline(messages, get_header_func):
    """Generate a timeline of key events in the thread."""
    events = []
    for msg in messages:
        sender = get_header_func(msg, 'From')
        subject = get_header_func(msg, 'Subject')
        received_ts = int(msg.get('internalDate', '0')) / 1000
        received_dt = datetime.fromtimestamp(received_ts, UTC)
        events.append({
            'timestamp': received_dt,
            'sender': sender,
            'subject': subject,
        })
    return events

def analyze_email_patterns(messages, get_header_func):
    """Analyze email patterns and extract statistics."""
    stats = {
        "total_messages": len(messages),
        "received": 0,
        "sent": 0,
        "by_hour": defaultdict(int),
        "by_day_of_week": defaultdict(int),
        "top_senders": Counter(),
        "top_recipients": Counter(),
        "top_subject_keywords": Counter(),
        "message_sizes": [],
    }
    
    # Process messages
    for item in messages:
        try:
            msg = item
            labels = set(msg.get('labelIds', []))
            
            # Determine if message was sent or received
            is_sent = 'SENT' in labels
            if is_sent:
                stats["sent"] += 1
                recipient = get_header_func(msg, 'To')
                if recipient:
                    stats["top_recipients"][recipient] += 1
            else:
                stats["received"] += 1
                sender = get_header_func(msg, 'From')
                stats["top_senders"][sender] += 1
            
            # Extract metadata
            received_ts = int(msg.get('internalDate', '0')) / 1000
            received_dt = datetime.fromtimestamp(received_ts, UTC)
            
            # Time-based statistics
            stats["by_hour"][received_dt.hour] += 1
            stats["by_day_of_week"][received_dt.strftime('%A')] += 1
            
            # Subject analysis
            subject = get_header_func(msg, 'Subject')
            if subject:
                # Simple keyword extraction (in a real implementation, you might use NLP)
                words = subject.replace(':', ' ').replace('-', ' ').replace('(', ' ').replace(')', ' ').split()
                for word in words:
                    if len(word) > 3:  # Only count words longer than 3 characters
                        stats["top_subject_keywords"][word.lower()] += 1
            
            # Message size
            size_estimate = msg.get('sizeEstimate', 0)
            stats["message_sizes"].append(size_estimate)
            
        except Exception as e:
            print(f"Error processing message {item.get('id', 'unknown')}: {e}")
            continue
    
    # Convert counters to regular dicts for JSON serialization
    stats["top_senders"] = dict(stats["top_senders"].most_common(10))
    stats["top_recipients"] = dict(stats["top_recipients"].most_common(10))
    stats["top_subject_keywords"] = dict(stats["top_subject_keywords"].most_common(20))
    
    # Calculate averages
    if stats["message_sizes"]:
        stats["avg_message_size"] = sum(stats["message_sizes"]) / len(stats["message_sizes"])
        stats["max_message_size"] = max(stats["message_sizes"])
        stats["min_message_size"] = min(stats["message_sizes"])
    
    return stats
