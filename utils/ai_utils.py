import json
from openai import OpenAI

def categorize_email(sender, subject, body, client):
    """Categorize email with GPT and return category with confidence score."""
    system = {
        "role": "system",
        "content": (
            "You are an email categorization assistant. "
            "Categorize the email into ONE of these categories: "
            "  • Urgent: Requires immediate attention (e.g., emergencies, deadlines)"
            "  • Action Required: Requires specific action from the recipient"
            "  • Informational: Provides information, no action needed"
            "  • Meeting Request: Scheduling or meeting related"
            "  • Follow-up: Continuation of previous conversations"
            "  • Newsletter: Periodic updates, marketing content"
            "Return a JSON object with exactly two keys: "
            "  • category: the category name from the list above"
            "  • confidence: a number from 0.0 to 1.0 indicating confidence"
        )
    }
    
    user_content = f"From: {sender}\nSubject: {subject}\n\n{body[:1000]}"
    user = {
        "role": "user",
        "content": user_content,
    }
    
    try:
        chat_resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[system, user],
            max_tokens=100,
        )
        
        assistant_content = chat_resp.choices[0].message.content
        data = json.loads(assistant_content)
        if not isinstance(data, dict):
            raise ValueError("assistant reply must be an object")
        if "category" not in data or "confidence" not in data:
            raise ValueError("Missing keys in assistant response")
        
        return {
            "category": data.get("category", "Informational"),
            "confidence": float(data.get("confidence", 0.5)),
        }
    except Exception as e:
        print(f"! Error categorizing email: {e}")
        return {"category": "Informational", "confidence": 0.5}

def detect_sentiment(sender, subject, body, client):
    """Detect sentiment of the email."""
    system = {
        "role": "system",
        "content": (
            "You are a sentiment analysis assistant. "
            "Analyze the sentiment of the email and return a JSON object with exactly two keys: "
            "  • sentiment: one of 'positive', 'negative', 'neutral', or 'urgent'"
            "  • intensity: a number from 0.0 to 1.0 indicating sentiment intensity"
        )
    }
    
    user_content = f"From: {sender}\nSubject: {subject}\n\n{body[:500]}"
    user = {
        "role": "user",
        "content": user_content,
    }
    
    try:
        chat_resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[system, user],
            max_tokens=100,
        )
        
        assistant_content = chat_resp.choices[0].message.content
        data = json.loads(assistant_content)
        if not isinstance(data, dict):
            raise ValueError("assistant reply must be an object")
        if "sentiment" not in data or "intensity" not in data:
            raise ValueError("Missing keys in assistant response")
        
        return {
            "sentiment": data.get("sentiment", "neutral"),
            "intensity": float(data.get("intensity", 0.5)),
        }
    except Exception as e:
        print(f"! Error detecting sentiment: {e}")
        return {"sentiment": "neutral", "intensity": 0.5}

def extract_entities(body, client):
    """Extract key entities from the email body."""
    system = {
        "role": "system",
        "content": (
            "You are an entity extraction assistant. "
            "Extract key entities from the email and return a JSON object with these keys: "
            "  • people: list of people mentioned"
            "  • organizations: list of organizations mentioned"
            "  • dates: list of dates mentioned"
            "  • action_items: list of actions requested"
            "If any key has no relevant entities, return an empty list for that key."
        )
    }
    
    user_content = f"Email body:\n{body[:1000]}"
    user = {
        "role": "user",
        "content": user_content,
    }
    
    try:
        chat_resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[system, user],
            max_tokens=200,
        )
        
        assistant_content = chat_resp.choices[0].message.content
        data = json.loads(assistant_content)
        if not isinstance(data, dict):
            raise ValueError("assistant reply must be an object")
        
        return {
            "people": data.get("people", [])[:5],
            "organizations": data.get("organizations", [])[:5],
            "dates": data.get("dates", [])[:5],
            "action_items": data.get("action_items", [])[:5],
        }
    except Exception as e:
        print(f"! Error extracting entities: {e}")
        return {"people": [], "organizations": [], "dates": [], "action_items": []}

def summarize_text(client, text):
    """Summarize text using GPT."""
    system = {
        'role': 'system',
        'content': (
            'You summarize emails. Return a short summary of the user provided text.'
        ),
    }
    user = {'role': 'user', 'content': text}
    resp = client.chat.completions.create(model='gpt-3.5-turbo', messages=[system, user])
    return resp.choices[0].message.content.strip()

def generate_insights(client, stats):
    """Generate insights using GPT based on the statistics."""
    system = {
        "role": "system",
        "content": (
            "You are an email productivity consultant. "
            "Analyze the email statistics provided and offer insights on productivity patterns. "
            "Focus on: 1) Time management patterns, 2) Communication efficiency, "
            "3) Areas for improvement. Keep response concise and actionable."
        )
    }
    
    stats_text = json.dumps(stats, indent=2)
    user = {
        "role": "user",
        "content": f"Email statistics:\n{stats_text}"
    }
    
    try:
        chat_resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[system, user],
            max_tokens=300,
        )
        return chat_resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Could not generate insights: {e}"
