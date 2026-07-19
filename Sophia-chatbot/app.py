import os
import json
import requests
from flask import Flask, request, Response, render_template

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"  #fast and free-tier

SYSTEM_PROMPT = (
    "You are Sophia, a helpful, concise AI assistant created by Benson in 2026. "
    "Your name comes from the Greek word 'sophia', meaning wisdom. "
    "If asked who made you or what your name means, share this naturally."
)

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    if not GROQ_API_KEY:
        return {"error": "Server is missing GROQ_API_KEY. Set it as an environment variable."}, 500

    data = request.get_json(force=True)
    messages = data.get("messages", [])

    # Prepend system prompt
    payload_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    def generate():
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": MODEL,
            "messages": payload_messages,
            "stream": True,
            "temperature": 0.7,
        }

        try:
            with requests.post(GROQ_URL, headers=headers, json=body, stream=True, timeout=60) as r:
                if r.status_code != 200:
                    err_text = r.text
                    yield f"data: {json.dumps({'error': err_text})}\n\n"
                    return

                for line in r.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        chunk = decoded[len("data: "):]
                        if chunk.strip() == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        try:
                            parsed = json.loads(chunk)
                            delta = parsed["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield f"data: {json.dumps({'content': delta})}\n\n"
                        except (KeyError, IndexError, json.JSONDecodeError):
                            continue
        except requests.exceptions.RequestException as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
