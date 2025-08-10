import os
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Get the API key
api_key = os.getenv('OPENAI_API_KEY')

print("=== API KEY DEBUG INFO ===")
print(f"API Key loaded: {api_key is not None}")
if api_key:
    print(f"API Key length: {len(api_key)}")
    print(f"API Key starts with: {api_key[:20]}...")
    print(f"API Key ends with: ...{api_key[-10:]}")
    
    # Check for any special characters or issues
    print(f"Contains special chars: {any(c in api_key for c in ['\\n', '\\r', ' ', '\\t'])}")
    
    # Try to create a client
    try:
        client = OpenAI(api_key=api_key)
        print("✅ Client created successfully!")
        
        # Try a simple API call
        response = client.models.list()
        print("✅ API call successful!")
        
    except Exception as e:
        print(f"❌ Error creating client or making API call: {e}")
else:
    print("❌ API Key not found in environment variables")
