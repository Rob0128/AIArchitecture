from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()
client = OpenAI()

client.api_key = os.getenv("OPENAI_API_KEY")

def stream_response():
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Tell me a joke. make it 3 paragraphs long"}],
        stream=True
    )
    for chunk in response:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
    
@app.get("/stream")
def stream():
    return StreamingResponse(stream_response(), media_type="text/plain")    
