import os
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Get the API key
api_key = os.getenv('OPENAI_API_KEY')

print(f"API Key loaded: {api_key is not None}")
if api_key:
    print(f"API Key length: {len(api_key)}")
    print(f"API Key starts with: {api_key[:15]}...")
    
    # Test the API key
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[{'role': 'user', 'content': 'Hello, this is a test.'}],
            max_tokens=10
        )
        print("✅ API key is working correctly!")
        print(f"Test response: {response.choices[0].message.content}")
    except Exception as e:
        print(f"❌ Error with API key: {e}")
else:
    print("❌ API Key not found in environment variables")
