import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# from autogen_core.models import UserMessage
# from autogen_ext.models.ollama import OllamaChatCompletionClient


# async def main() -> None:
#         # Assuming your Ollama server is running locally on port 11434.
#         ollama_model_client = OllamaChatCompletionClient(
#                                 model="deepseek-r1",
#                                 host="host.docker.internal:11436"
#                             )

#         response = await ollama_model_client.create([UserMessage(content="What is the capital of Australia?", source="user")])
#         print(response)
#         await ollama_model_client.close()

# asyncio.run(main())

from autogen_core import AgentId, MessageContext, RoutedAgent, message_handler, AgentType
from autogen_core import SingleThreadedAgentRuntime

# For data validation
from dataclasses import dataclass # either this one or Pydantic's BaseModel
from pydantic import BaseModel

# For Chat Agent
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient

async def main() -> None:
        @dataclass
        class MyMessage:
                content: str


        class TextMessage(BaseModel):
                content: str
                source: str


        class ImageMessage(BaseModel):
                url: str
                source: str


        class MyAgent(RoutedAgent):
                def __init__(self) -> None:
                        super().__init__("MyAgent")

                @message_handler
                async def handle_my_message_type(self, message: MyMessage, ctx: MessageContext) -> None:
                        print(f"{self.id.type} received message: {message.content}")


        class MyAssistant(RoutedAgent):
                def __init__(self, name: str) -> None:
                        super().__init__(name)
                        # model_client = OpenAIChatCompletionClient(model="gpt-4o")
                        # self._delegate = AssistantAgent(name, model_client=model_client)

                @message_handler
                async def handle_my_message_type(self, message: MyMessage, ctx: MessageContext) -> None:
                        print(f"{self.id.type} received message: {message.content}")
                        print(f"{self.id.type} received message: {ctx}")
                        # response = await self._delegate.on_messages(
                        #         [TextMessage(content=message.content, source="user")], ctx.cancellation_token
                        # )
                        # print(f"{self.id.type} responded: {response.chat_message.content}")

                @message_handler
                async def on_text_message(self, message: TextMessage, ctx: MessageContext) -> None:
                        print(f"Hello, {message.source}, you said {message.content}!")

                @message_handler
                async def on_image_message(self, message: ImageMessage, ctx: MessageContext) -> None:
                        print(f"Hello, {message.source}, you sent me {message.url}!")


        runtime = SingleThreadedAgentRuntime()
        await MyAgent.register(runtime, "my_agent", lambda: MyAgent())
        await MyAssistant.register(runtime, "my_assistant", lambda: MyAssistant("MyAssistant"))
        # AgentType(type='my_assistant')

        runtime.start()  # Start processing messages in the background.
        await runtime.send_message(MyMessage("Hello, World!"), AgentId("my_agent", "default"))
        await runtime.send_message(MyMessage("Hello, Tojo!"), AgentId("my_assistant", "default"))

        await runtime.send_message(TextMessage(content="Hello, World!", source="User"), AgentId("my_assistant", "default"))
        await runtime.send_message(ImageMessage(url="https://example.com/image.jpg", source="User"), AgentId("my_assistant", "default"))

        await runtime.stop()  # Stop processing messages in the background.
        await runtime.close()

asyncio.run(main())
