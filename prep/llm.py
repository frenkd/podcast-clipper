"""Structured-output calls to the OpenAI Responses API (stdlib only), with retries on transient failures."""
import json
import time
import urllib.error
import urllib.request

from .config import MODELS, api_error, require_key


def llm_json(system, user, schema, name="out", model="smart", effort="low", images=()):
    """-> the parsed JSON object the model returned for `schema` (a JSON schema dict)"""
    content = [{"type": "input_text", "text": user}] + [{"type": "input_image", "image_url": i} for i in images]
    body = {"model": MODELS[model], "reasoning": {"effort": effort},
            "input": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}}}
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {require_key('OPENAI_API_KEY')}",
                                                  "Content-Type": "application/json"})
            data = json.load(urllib.request.urlopen(req, timeout=600))
            text = next((c["text"] for o in data.get("output", []) if o.get("type") == "message"
                         for c in o.get("content", []) if c.get("type") == "output_text"), None)
            if not text:
                raise RuntimeError(f"OpenAI returned no text (status {data.get('status')})")
            return json.loads(text)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if (e.code < 500 and e.code != 429) or "insufficient_quota" in msg:
                raise api_error("OpenAI", "OPENAI_API_KEY", e.code, msg) from None
            last = api_error("OpenAI", "OPENAI_API_KEY", e.code, msg)
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise last


# small schema helpers so prompts stay readable
def obj(**props):
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


def arr(items):
    return {"type": "array", "items": items}


def string(description=None, **kw):
    return {"type": "string", **({"description": description} if description else {}), **kw}


def integer():
    return {"type": "integer"}
