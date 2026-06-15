from google import genai  # Updated import for 2026 SDK
from chatbot.prompts import SYSTEM_PROMPT

class TravelBot:
    def __init__(self, api_key):
        # In the new SDK, we create a 'Client' instead of using '.configure()'
        self.client = genai.Client(api_key=api_key)
        
        # Use a 2026-supported model name
        self.model_id = 'gemini-2.5-flash' 

    def get_response(self, user_input):
        try:
            # Combine system prompt and user input
            full_query = f"{SYSTEM_PROMPT}\n\nUser Request: {user_input}"
            
            # Use the new client.models.generate_content syntax
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=full_query
            )
            return response.text
            
        except Exception as e:
            return f"AI Error: {str(e)}"