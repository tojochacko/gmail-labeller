# Codebase Structure

## Root Directory Layout

```
autogen-test/
├── .devcontainer/         # Development container configuration
│   ├── devcontainer.json  # Container settings and features
│   └── startup.sh         # Post-create setup script
├── .claude/               # Claude Code configuration
├── .serena/               # Serena MCP server data
├── .venv/                 # Python virtual environment
├── PRPs/                  # Project requirements/planning docs
├── .env                   # Environment variables (API keys, secrets)
├── .gitignore            # Git ignore patterns
├── pyproject.toml        # Project metadata and dependencies
├── uv.lock               # UV dependency lockfile
├── requirements.txt      # Legacy requirements (use pyproject.toml)
├── CLAUDE.md             # Development guidelines for Claude Code
├── README.md             # Project readme (minimal)
├── main.py               # Simple agent demonstration
├── customer-support.py   # Multi-agent customer service system
├── group-chat-example.py # Collaborative multi-agent group chat
└── gmail-organizer.py    # Composio Gmail integration (WIP)
```

## Architecture Patterns

### 1. RoutedAgent Pattern
All agents inherit from `RoutedAgent` and use `@message_handler` decorators to handle specific message types. Messages are routed through a `SingleThreadedAgentRuntime`.

### 2. Message-Based Communication
Agents communicate via typed Pydantic models:
- `UserTask`: Contains LLM message context
- `AgentResponse`: Contains reply context and routing info
- `GroupChatMessage`: Wraps user messages for group chats
- `RequestToSpeak`: Signals an agent to respond

### 3. Topic-Based Routing
Agents subscribe to topics using `TypeSubscription`. Messages are published to `TopicId` instances with a topic type and source (typically a session ID).

### 4. Tool Integration
- **Direct tools**: Executed by the agent itself (e.g., `execute_order_tool`)
- **Delegate tools**: Transfer control to another agent (e.g., `transfer_to_sales_agent_tool`)
- Tools are defined using `FunctionTool` wrapper around Python functions

## Key Files

### main.py
Simple agent demonstration showing:
- Message routing with multiple message types
- `MyAgent` and `MyAssistant` examples
- Handling `MyMessage`, `TextMessage`, and `ImageMessage`

### customer-support.py
Complex multi-agent customer service system with:
- **Triage agent**: Routes to appropriate specialist
- **Sales agent**: Handles purchases
- **Issues/Repairs agent**: Handles refunds
- **Human agent**: Escalation path
- Demonstrates tool execution, delegation, and conversation flow

### group-chat-example.py
Collaborative multi-agent system with:
- **Group chat manager**: Selects next speaker using LLM
- **Specialized agents**: Writer, Editor, Illustrator
- **Image generation**: DALL-E integration
- **Rich console output**: Better UX

### gmail-organizer.py
Work-in-progress Composio integration for Gmail automation

## Agent Lifecycle

1. Register agent types with runtime: `await MyAgent.register(runtime, "agent_type", factory_function)`
2. Add subscriptions: `await runtime.add_subscription(TypeSubscription(...))`
3. Start runtime: `runtime.start()`
4. Publish initial message: `await runtime.publish_message(...)`
5. Wait for completion: `await runtime.stop_when_idle()`
6. Clean up: `await runtime.close()` and `await model_client.close()`

## Important Notes

- All agents run in a single-threaded runtime (no true concurrency)
- Session isolation is achieved via unique source IDs in TopicId
- LLM calls are async and support cancellation tokens
- Tool schemas are automatically generated from function signatures
- The framework supports both direct execution and agent delegation patterns