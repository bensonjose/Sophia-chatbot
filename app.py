import os                                  # lets us read environment variables (like the API key)
import json                                # for encoding/decoding JSON data sent between server and browser
import requests                            # library used to make HTTP calls to Groq's API
from flask import Flask, request, Response, render_template   # Flask tools: app object, incoming request data, streaming response, HTML rendering

app = Flask(__name__)                      # creates the Flask application instance

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")   # reads your API key from the environment; empty string if not set
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"   # the address we send chat requests to
MODEL = "llama-3.3-70b-versatile"  #fast and free-tier         # which AI model Groq should use to generate replies

SYSTEM_PROMPT = (
    "You are Sophia, a helpful, concise AI assistant created by Benson in 2026. "
    "Your name comes from the Greek word 'sophia', meaning wisdom. "
    "If asked who made you or what your name means, share this naturally."
)                                           # instructions sent to the AI before every conversation, defining its identity/behavior


@app.route("/")                            # runs when the browser visits the homepage ("/")
def index():
    return render_template("index.html")   # sends index.html (the chat UI) to the browser


@app.route("/api/chat", methods=["POST"])  # runs when the browser sends a POST request to /api/chat (i.e. when you hit send)
def chat():
    if not GROQ_API_KEY:                   # safety check: if no API key was set, stop and return an error
        return {"error": "Server is missing GROQ_API_KEY. Set it as an environment variable."}, 500

    data = request.get_json(force=True)    # parses the JSON data sent from the browser (the conversation so far)
    messages = data.get("messages", [])    # extracts the list of chat messages from that data

    # Prepend system prompt
    payload_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages   # adds Sophia's identity instructions to the front of the conversation

    def generate():                        # inner function that streams the AI's reply piece by piece
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",   # proves to Groq who you are (your API key)
            "Content-Type": "application/json",          # tells Groq we're sending JSON data
        }
        body = {
            "model": MODEL,                # which model to use for this request
            "messages": payload_messages,  # the full conversation history + system prompt
            "stream": True,                # tells Groq to send the reply in small chunks instead of all at once, basically it means to send response as the model generates even if it's token by token.
            "temperature": 0.7,            # controls randomness/creativity of the response (0 = very predictable, 1 = more varied)
        }

        try:
            with requests.post(GROQ_URL, headers=headers, json=body, stream=True, timeout=60) as r:   # sends the actual request to Groq, keeping the connection open to stream the response
                if r.status_code != 200:                # if Groq responds with an error status (not 200 OK)
                    err_text = r.text                   # grab the error message text
                    yield f"data: {json.dumps({'error': err_text})}\n\n"   # send that error back to the browser
                    return                               # stop here, nothing more to process

                for line in r.iter_lines():             # loop through each streamed line/chunk Groq sends back
                    if not line:                        # skip empty lines (keep-alive blank lines in the stream)
                        continue
                    decoded = line.decode("utf-8")      # convert the raw bytes into a readable string
                    if decoded.startswith("data: "):    # Groq prefixes each real data chunk with "data: "
                        chunk = decoded[len("data: "):] # strip off that "data: " prefix, leaving just the JSON content
                        if chunk.strip() == "[DONE]":   # Groq sends a "[DONE]" marker when the reply is fully finished
                            yield "data: [DONE]\n\n"    # forward that end signal to the browser
                            break                        # stop the loop, streaming is complete
                        try:
                            parsed = json.loads(chunk)  # convert the chunk's JSON text into a Python dictionary
                            delta = parsed["choices"][0]["delta"].get("content", "")   # extract just the new bit of text in this chunk
                            if delta:                   # if there's actually new text in this chunk
                                yield f"data: {json.dumps({'content': delta})}\n\n"    # send that small piece of text to the browser immediately
                        except (KeyError, IndexError, json.JSONDecodeError):   # if the chunk is malformed or missing expected fields
                            continue                    # skip it and move to the next chunk instead of crashing
        except requests.exceptions.RequestException as e:   # catches network errors (timeout, connection failure, etc.)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"   # send the error message back to the browser

    return Response(generate(), mimetype="text/event-stream", headers={   # wraps generate() as a live streaming HTTP response
        "Cache-Control": "no-cache",       # tells the browser not to cache this streamed response
        "X-Accel-Buffering": "no",         # disables proxy buffering so chunks arrive immediately instead of being held back
    })


if __name__ == "__main__":                 # only runs the server if this file is executed directly (not imported elsewhere)
    app.run(debug=True, port=5000)         # starts the Flask development server on port 5000, with debug mode on (auto-reloads, shows detailed errors)