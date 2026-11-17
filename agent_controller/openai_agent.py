
from openai import OpenAI

# Support both direct execution and package imports.
if __package__:
    from .config import OPENAI_API_KEY, OPENAI_MODEL
else:
    from config import OPENAI_API_KEY, OPENAI_MODEL


client = OpenAI(api_key=OPENAI_API_KEY)


def ask_gpt(prompt: str) -> str:
    """Send a prompt to GPT and return its response."""

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )

    return response.output_text
