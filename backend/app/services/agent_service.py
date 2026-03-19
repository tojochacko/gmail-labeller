"""Agent runtime integration service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import logging
import json

from ..config import Settings
from ..schemas.agent import AgentRunRequest, AgentRunResponse, AgentRunStatusResponse
from .pattern_learning_service import PatternLearningService
from .pii_redactor import PIIRedactor
from .supabase_service import SupabaseService


logger = logging.getLogger(__name__)


class AgentService:
    """Trigger and monitor agent runs via the existing runtime API."""

    def __init__(
        self,
        settings: Settings,
        supabase: SupabaseService,
        pattern_service: PatternLearningService | None = None,
        pii_redactor: PIIRedactor | None = None,
    ) -> None:
        self._settings = settings
        self._supabase = supabase
        self._pattern_service = pattern_service or PatternLearningService(supabase)
        self._pii_redactor = pii_redactor or PIIRedactor()
        self._mock_runs: dict[UUID, dict] = {}

    def _is_mock_mode(self) -> bool:
        """Check if running in mock mode (no agent runtime, Ollama, or OpenAI configured)."""
        if self._settings.agent_runtime_base_url is not None:
            return False
        if self._settings.ollama_enabled:
            return False
        if self._settings.openai_api_key:
            return False
        return True

    def _is_ollama_mode(self) -> bool:
        """Check if Ollama local LLM is enabled."""
        return self._settings.ollama_enabled and not self._settings.agent_runtime_base_url

    def _is_openai_mode(self) -> bool:
        """Check if OpenAI is the active classification mode."""
        return (
            bool(self._settings.openai_api_key)
            and not self._settings.ollama_enabled
            and self._settings.agent_runtime_base_url is None
        )

    async def _mock_trigger_agent_run(self, request: AgentRunRequest) -> AgentRunResponse:
        """Mock agent run for development/testing without external runtime."""
        run_id = uuid4()
        status = "completed"

        # Alternate between Important and Not Important for demo purposes
        # Use email_id hash to make it deterministic but varied
        is_important = int(str(request.email_id).split("-")[0], 16) % 2 == 0

        result_payload = {
            "suggestion": "Important" if is_important else "Not Important",
            "confidence": 0.9 if is_important else 0.85,
            "reasoning": (
                "Mock: High priority detected"
                if is_important
                else "Mock: Low priority, can be archived"
            ),
        }

        logger.warning(
            "Agent runtime not configured, using mock mode for email %s user %s",
            request.email_id,
            request.user_id,
        )

        # Store mock run
        self._mock_runs[run_id] = {
            "run_id": str(run_id),
            "user_id": str(request.user_id),
            "email_id": str(request.email_id),
            "status": status,
            "result_payload": result_payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save to database
        await self._supabase.record_agent_run(
            run_id=run_id,
            user_id=request.user_id,
            email_id=request.email_id,
            status=status,
            result_payload=result_payload,
            batch_run_id=request.batch_run_id,
        )

        return AgentRunResponse(run_id=run_id, status=status)

    async def _ollama_trigger_agent_run(self, request: AgentRunRequest) -> AgentRunResponse:
        """Trigger agent run using local Ollama LLM."""
        run_id = uuid4()

        # Build prompt for email classification
        prompt = request.prompt or ""
        if not prompt:
            # Default classification prompt
            prompt = (
                "Analyze this email and classify it as either 'Important' or 'Not Important'.\n\n"
                "Respond in JSON format:\n"
                '{"suggestion": "Important|Not Important", "confidence": 0.0-1.0,'
                ' "reasoning": "explanation"}'
            )

        logger.info(
            "Using Ollama (%s) for email %s user %s",
            self._settings.ollama_model,
            request.email_id,
            request.user_id,
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._settings.ollama_host}/api/generate",
                    json={
                        "model": self._settings.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                # Parse the response
                try:
                    result_text = data.get("response", "")
                    result = json.loads(result_text)
                    suggestion = result.get("suggestion", "Important")
                    confidence = float(result.get("confidence", 0.7))
                    reasoning = result.get("reasoning", "Classified by local LLM")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse Ollama response: {e}, raw: {result_text}")
                    # Fallback to simple parsing
                    if "not important" in result_text.lower():
                        suggestion = "Not Important"
                        confidence = 0.6
                    else:
                        suggestion = "Important"
                        confidence = 0.7
                    reasoning = "Parsed from LLM response"

                result_payload = {
                    "suggestion": suggestion,
                    "confidence": confidence,
                    "reasoning": reasoning,
                }

        except Exception as e:
            logger.error(f"Ollama request failed: {e}, falling back to mock")
            # Fallback to mock mode if Ollama fails
            return await self._mock_trigger_agent_run(request)

        status = "completed"

        # Store run
        await self._supabase.record_agent_run(
            run_id=run_id,
            user_id=request.user_id,
            email_id=request.email_id,
            status=status,
            result_payload=result_payload,
            batch_run_id=request.batch_run_id,
        )

        return AgentRunResponse(run_id=run_id, status=status)

    async def _openai_trigger_agent_run(self, request: AgentRunRequest) -> AgentRunResponse:
        """Trigger agent run using OpenAI gpt-4o-mini for email classification."""
        import openai

        run_id = uuid4()

        prompt = request.prompt or ""
        if not prompt:
            prompt = (
                "Analyze this email and classify it as either 'Important' or 'Not Important'.\n\n"
                "Respond in JSON format:\n"
                '{"suggestion": "Important|Not Important", "confidence": 0.0-1.0,'
                ' "reasoning": "..."}'
            )

        logger.info(
            "Using OpenAI (%s) for email %s user %s",
            self._settings.openai_model,
            request.email_id,
            request.user_id,
        )

        try:
            client = openai.AsyncOpenAI(api_key=self._settings.openai_api_key)
            response = await client.chat.completions.create(
                model=self._settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an email classifier. Respond only with valid JSON: "
                            '{"suggestion": "Important|Not Important", '
                            '"confidence": <float 0-1>, "reasoning": "<brief reason>"}'
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=150,
            )
            result_text = response.choices[0].message.content or ""
            result = json.loads(result_text)
            suggestion = result.get("suggestion", "Important")
            confidence = float(result.get("confidence", 0.8))
            reasoning = result.get("reasoning", "Classified by OpenAI")

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse OpenAI response: {e}, falling back to mock")
            return await self._mock_trigger_agent_run(request)
        except Exception as e:
            logger.error(f"OpenAI request failed: {e}, falling back to mock")
            return await self._mock_trigger_agent_run(request)

        result_payload = {
            "suggestion": suggestion,
            "confidence": confidence,
            "reasoning": reasoning,
        }

        status = "completed"
        await self._supabase.record_agent_run(
            run_id=run_id,
            user_id=request.user_id,
            email_id=request.email_id,
            status=status,
            result_payload=result_payload,
            batch_run_id=request.batch_run_id,
        )
        return AgentRunResponse(run_id=run_id, status=status)

    async def _mock_get_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        """Get mock agent run status."""
        # Check in-memory mock storage
        if run_id in self._mock_runs:
            data = self._mock_runs[run_id]
            return AgentRunStatusResponse(
                run_id=run_id,
                status=data["status"],
                result_payload=data.get("result_payload"),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                error_message=data.get("error_message"),
            )

        # Check database for persisted mock runs
        cached = await self._supabase.fetch_agent_run(run_id)
        return cached

    async def trigger_agent_run(self, request: AgentRunRequest) -> AgentRunResponse:
        # Fetch learned patterns for this user and inject into prompt
        learned_context = await self._pattern_service.get_learned_context(user_id=request.user_id)
        context_text = learned_context.format_for_prompt()

        # Enhance prompt with learned context
        enhanced_prompt = request.prompt or ""
        if context_text:
            enhanced_prompt = f"{enhanced_prompt}\n{context_text}"
            logger.info(
                f"Injected learned context for user {request.user_id}: "
                f"{len(learned_context.important_domains)} important domains, "
                f"{len(learned_context.important_keywords)} important keywords"
            )

        # Redact PII from the prompt before it leaves the host machine.
        # Mock mode is local-only, so redaction is skipped there.
        if not self._is_mock_mode() and enhanced_prompt:
            redaction = self._pii_redactor.redact(enhanced_prompt)
            if redaction.entities_found:
                logger.info(
                    "Redacted %d PII entities from prompt for email %s",
                    redaction.entities_found,
                    request.email_id,
                )
            enhanced_prompt = redaction.text

        # Create enhanced request with learned context
        enhanced_request = AgentRunRequest(
            user_id=request.user_id,
            email_id=request.email_id,
            gmail_message_id=request.gmail_message_id,
            prompt=enhanced_prompt,
            batch_run_id=request.batch_run_id,
        )

        # Use OpenAI if configured (and no Ollama/external runtime)
        if self._is_openai_mode():
            return await self._openai_trigger_agent_run(enhanced_request)

        # Use Ollama if enabled
        if self._is_ollama_mode():
            return await self._ollama_trigger_agent_run(enhanced_request)

        # Use mock mode if agent runtime is not configured
        if self._is_mock_mode():
            return await self._mock_trigger_agent_run(enhanced_request)

        payload = enhanced_request.model_dump()
        logger.info(
            "Triggering agent run for email %s user %s",
            request.email_id,
            request.user_id,
        )
        async with httpx.AsyncClient(base_url=str(self._settings.agent_runtime_base_url)) as client:
            response = await client.post("/runs", json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

        run_id = UUID(data["run_id"])
        status = data.get("status", "queued")
        result_payload = data.get("result_payload")

        await self._supabase.record_agent_run(
            run_id=run_id,
            user_id=request.user_id,
            email_id=request.email_id,
            status=status,
            result_payload=result_payload,
        )

        return AgentRunResponse(run_id=run_id, status=status)

    async def get_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        # Use mock/Ollama/OpenAI mode if agent runtime is not configured
        if self._is_mock_mode() or self._is_ollama_mode() or self._is_openai_mode():
            return await self._mock_get_agent_run(run_id)

        logger.debug("Fetching agent run %s", run_id)
        cached = await self._supabase.fetch_agent_run(run_id)
        if cached:
            return cached

        async with httpx.AsyncClient(base_url=str(self._settings.agent_runtime_base_url)) as client:
            response = await client.get(f"/runs/{run_id}", timeout=15)
            response.raise_for_status()
            data = response.json()

        status = data.get("status", "unknown")
        user_id_raw = data.get("user_id")
        email_id_raw = data.get("email_id")
        updated_at_raw = data.get("updated_at")

        if isinstance(user_id_raw, str) and isinstance(email_id_raw, str):
            await self._supabase.record_agent_run(
                run_id=run_id,
                user_id=UUID(user_id_raw),
                email_id=UUID(email_id_raw),
                status=status,
                result_payload=data.get("result_payload"),
                error_message=data.get("error_message"),
            )

        if isinstance(updated_at_raw, str):
            try:
                updated_at = datetime.fromisoformat(updated_at_raw)
            except ValueError:
                updated_at = datetime.now(timezone.utc)
        else:
            updated_at = datetime.now(timezone.utc)

        return AgentRunStatusResponse(
            run_id=run_id,
            status=status,
            result_payload=data.get("result_payload"),
            updated_at=updated_at,
            error_message=data.get("error_message"),
        )
