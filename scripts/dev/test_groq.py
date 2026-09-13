import asyncio

from app.llm.groq import (
    load_groq_provider,
)


async def main():

    provider = load_groq_provider()

    result = await provider.generate(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a test assistant."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Reply with exactly: GROQ_OK"
                ),
            },
        ]
    )

    print("RESPONSE:", result)

    print(
        "USAGE:",
        provider.get_last_usage(),
    )

    print(
        "KEY INDEX:",
        provider.last_key_index,
    )


if __name__ == "__main__":
    asyncio.run(main())