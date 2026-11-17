from collections import deque

from groq import Groq


BASE_PROMPT = (
    "You are a concise, helpful voice assistant. "
    "Reply in plain spoken language in two short sentences or fewer."
)
LANG_RULE = {
    "en": "Reply in English.",
    "hi": "Reply in Hindi, written in Devanagari script only.",
}


class LLM:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = Groq(api_key=api_key)
        self._model = model
        self._history: deque[dict[str, str]] = deque(maxlen=10)

    def respond(self, user_text: str, lang: str = "en") -> str:
        messages = [{"role": "system", "content": BASE_PROMPT + LANG_RULE[lang]}]
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_text})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.4,
            max_tokens=300,
        )
        answer = response.choices[0].message.content
        if not answer:
            raise RuntimeError("Groq returned an empty response")

        self._history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": answer},
            ]
        )
        return answer
