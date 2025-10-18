from openai import OpenAI
from .config import OPENAI_API_KEY, OPENAI_MODEL


def get_ai_response(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return "⚠️ L'AI non è configurata."
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "Sei Gio.ia-bot, un assistente AI specializzato nella gestione inventario. Sei gentile, professionale e parli in italiano. Aiuti gli utenti con domande su inventario, movimenti di magazzino e report."},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()



