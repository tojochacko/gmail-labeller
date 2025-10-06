import asyncio
from autogen_core.models import UserMessage
from autogen_ext.models.ollama import OllamaChatCompletionClient


async def main() -> None:
        # Assuming your Ollama server is running locally on port 11434.
        ollama_model_client = OllamaChatCompletionClient(
                                model="deepseek-r1",
                                host="127.0.0.1:11436"
                            )

        response = await ollama_model_client.create([UserMessage(content="What is the capital of Australia?", source="user")])
        print(response)
        await ollama_model_client.close()

asyncio.run(main())
