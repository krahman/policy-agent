"""Hello-world traced chain: verifies API keys and LangSmith tracing (Step 0 exit check)."""

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from policy_agent.llm import get_chat_model


def build_chain():
    prompt = ChatPromptTemplate.from_messages([("human", "Reply with one word: {word}")])
    model = get_chat_model(max_tokens=20)
    return prompt | model | StrOutputParser()


def main() -> None:
    load_dotenv()
    print(build_chain().invoke({"word": "ready"}))


if __name__ == "__main__":
    main()
