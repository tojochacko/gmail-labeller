# Project Overview

## Purpose
Autogen playground for AI agent development using Microsoft's Autogen framework (v0.7.5+). This is a testing ground for exploring various agentic product ideas before committing to full development. The project demonstrates various multi-agent architectures including simple agents, customer support systems, group chats, and integration with external tools.

## Tech Stack

### Core Framework
- **autogen-agentchat** (v0.7.5+): High-level agent chat interface
- **autogen-core** (v0.7.5+): Core agent runtime and messaging
- **autogen-ext**: Extensions for Ollama and OpenAI integrations

### AI/LLM
- **OpenAI**: Primary LLM provider (gpt-4o, gpt-4o-mini)
- **Ollama**: Alternative local LLM support (configured for host.docker.internal:11436)

### Data & Validation
- **pydantic** (v2.11.10+): Data validation and settings management
- **pandas** (v2.3.3+): Data processing

### Tools & Integrations
- **Composio** (v0.8.0+): External tool integration platform (e.g., Gmail)
- **rich** (v14.2.0+): Console output formatting

### Development Environment
- **Python** 3.12+
- **uv**: Package manager for fast dependency management
- **devcontainer**: Docker-based development environment
  - Base: `mcr.microsoft.com/devcontainers/base:ubuntu`
  - Features: Docker-outside-of-docker, Git, Python
- **ipython** (v9.6.0+): Interactive Python shell

## Language
- Python 3.12+
- UTF-8 file encoding