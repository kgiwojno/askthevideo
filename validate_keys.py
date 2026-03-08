from dotenv import load_dotenv
load_dotenv()

# Antropic
from anthropic import Anthropic
client = Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=100,
    messages=[{"role": "user", "content": "Say 'API working' and nothing else."}]
)
print(response.content[0].text)
print(f"Tokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out")

#Pinecone
import os
from pinecone import Pinecone

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
print("Indexes:", pc.list_indexes().names())

#YouTube
from youtube_transcript_api import YouTubeTranscriptApi

ytt_api = YouTubeTranscriptApi()
transcript = ytt_api.fetch("dQw4w9WgXcQ")
print(f"Segments: {len(transcript.snippets)}")
print(f"First: {transcript.snippets[0]}")
print(f"Language: {transcript.language}")
print(f"Auto-generated: {transcript.is_generated}")

#Discord
import os, requests

requests.post(os.getenv("DISCORD_WEBHOOK_URL"), json={
    "content": "🔧 AskTheVideo webhook test — if you see this, it works!"
})



