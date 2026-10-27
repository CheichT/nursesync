"""One tiny request to prove the API key works. Run: cd backend && ../.venv/bin/python -m app.check_connection

Prints only whether it worked, never the key.
"""

import sys

import anthropic

from app.config import MODEL, load_api_key


def main() -> int:
    try:
        client = anthropic.Anthropic(api_key=load_api_key())
        reply = client.messages.create(
            model=MODEL, max_tokens=10, messages=[{"role": "user", "content": "Reply with the single word: ok"}]
        )
    except RuntimeError as err:
        print(f"Not ready: {err}")
        return 1
    except anthropic.AuthenticationError:
        print("The API rejected the key. Check the key in .env (no quotes, no spaces) or create a new one.")
        return 1
    except anthropic.APIError as err:
        print(f"The API call failed: {type(err).__name__}")
        return 1
    print(f"Connected. Model {MODEL} replied: {reply.content[0].text.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
