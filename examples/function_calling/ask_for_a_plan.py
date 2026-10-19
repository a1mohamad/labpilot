import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.5-flash-lite:generateContent"
)

QUESTION = (
    "Why does my model clip gradients at 1.5 when paper says 1.0? "
    "I uploaded the paper as A and my training code as B."
)

STEPS = ["summarize", "find_bugs", "extract_claims", "verify", "respond"]

PLAN_TOOL = {
    "name": "make_plan",
    "description": "Choose the steps LabPilot runs, and what to search for.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "steps": {
                "type": "ARRAY",
                "items": {
                    "type": "STRING",
                    "enum": STEPS,
                },
            },
            "queries": {
                "type": "ARRAY",
                "items": {
                    "type": "STRING",
                },
            },
        },
        "required": ["steps", "queries"],
    },
}

body = {
    "contents": [{"parts": [{"text": QUESTION}]}],
    "tools": [{"functionDeclarations": [PLAN_TOOL]}],
    "toolConfig": {
        "functionCallingConfig": {
            "mode": "ANY",
            "allowedFunctionNames": ["make_plan"],
        }
    },
    "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024},
}

print("WE SEND:")
print(json.dumps(body, indent=2))

response = requests.post(
    URL,
    headers={"x-goog-api-key": os.environ["GOOGLE_API_KEY"]},
    json=body,
    timeout=60,
)

print("\nSTATUS:", response.status_code)
print("THE MODEL ANSWERS:")
print(json.dumps(response.json(), indent=2))

part = response.json()["candidates"][0]["content"]["parts"][0]
call = part["functionCall"]
print("\nname:", call["name"])
print("steps:", call["args"]["steps"])
print("queries:", call["args"]["queries"])
