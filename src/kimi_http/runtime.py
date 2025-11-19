from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, cast, get_args

from loguru import logger
from pydantic import SecretStr

from kimi_cli.agentspec import DEFAULT_AGENT_FILE
from kimi_cli.config import Config, LLMModel, LLMProvider, load_config
from kimi_cli.llm import ModelCapability, augment_provider_with_env_vars, create_llm
from kimi_cli.soul import LLMNotSet, LLMNotSupported
from kimi_cli.soul.agent import load_agent
from kimi_cli.soul.context import Context
from kimi_cli.soul.kimisoul import KimiSoul
from kimi_cli.soul.runtime import Runtime
from kimi_cli.session import Session
from kimi_cli.utils.logging import logger as kimi_logger

from .models import RunRequest


@dataclass(slots=True)
class RuntimeArtifacts:
    soul: KimiSoul
    runtime: Runtime
    session: Session
    env_overrides: dict[str, str]
    agent_file: Path


class RuntimeFactory:
    """Create per-request Runtime + KimiSoul instances."""

    async def create(self, request: RunRequest) -> RuntimeArtifacts:
        session = Session.create(request.work_dir)
        config = load_config(request.config_file)
        model, provider = _select_model_and_provider(config, request.model_name)

        env_overrides = augment_provider_with_env_vars(provider, model)
        env_overrides.update(_apply_request_env_overrides(provider, model, request.env))

        if provider.base_url and model.model:
            kimi_logger.info("Using LLM provider: {provider}", provider=provider)
            kimi_logger.info("Using LLM model: {model}", model=model)
            llm = create_llm(provider, model, session_id=session.id)
        else:
            kimi_logger.warning("LLM not configured; incoming run may fail until setup is complete")
            llm = None

        runtime = await Runtime.create(config, llm, session, request.options.yolo)

        agent_path = request.agent_file or DEFAULT_AGENT_FILE
        agent = await load_agent(agent_path, runtime, mcp_configs=[])

        context = Context(session.history_file)
        await context.restore()

        soul = KimiSoul(agent, runtime, context=context)
        try:
            soul.set_thinking(request.options.thinking)
        except (LLMNotSet, LLMNotSupported) as exc:
            logger.warning("Thinking mode unavailable: {error}", error=exc)

        return RuntimeArtifacts(
            soul=soul,
            runtime=runtime,
            session=session,
            env_overrides=env_overrides,
            agent_file=agent_path,
        )


def _select_model_and_provider(
    config: Config,
    model_name: str | None,
) -> tuple[LLMModel, LLMProvider]:
    model: LLMModel | None = None
    provider: LLMProvider | None = None

    if model_name and model_name in config.models:
        model = config.models[model_name]
        provider = config.providers[model.provider]
    elif not model_name and config.default_model:
        model = config.models[config.default_model]
        provider = config.providers[model.provider]

    if model is None or provider is None:
        model = LLMModel(provider="", model="", max_context_size=100_000)
        provider = LLMProvider(type="kimi", base_url="", api_key=SecretStr(""))
    return model, provider


def _apply_request_env_overrides(
    provider: LLMProvider,
    model: LLMModel,
    env: Mapping[str, str] | None,
) -> dict[str, str]:
    if not env:
        return {}

    applied: dict[str, str] = {}
    env = {key.upper(): value for key, value in env.items()}

    match provider.type:
        case "kimi":
            if base_url := env.get("KIMI_BASE_URL"):
                provider.base_url = base_url
                applied["KIMI_BASE_URL"] = base_url
            if api_key := env.get("KIMI_API_KEY"):
                provider.api_key = SecretStr(api_key)
                applied["KIMI_API_KEY"] = "******"
            if model_name := env.get("KIMI_MODEL_NAME"):
                model.model = model_name
                applied["KIMI_MODEL_NAME"] = model_name
            if max_ctx := env.get("KIMI_MODEL_MAX_CONTEXT_SIZE"):
                model.max_context_size = int(max_ctx)
                applied["KIMI_MODEL_MAX_CONTEXT_SIZE"] = max_ctx
            if capabilities := env.get("KIMI_MODEL_CAPABILITIES"):
                valid_caps = set(get_args(ModelCapability))
                caps = {
                    cast(ModelCapability, cap.strip().lower())
                    for cap in capabilities.split(",")
                    if cap.strip().lower() in valid_caps
                }
                if caps:
                    model.capabilities = caps
                applied["KIMI_MODEL_CAPABILITIES"] = capabilities
        case "openai_legacy" | "openai_responses":
            if base_url := env.get("OPENAI_BASE_URL"):
                provider.base_url = base_url
                applied["OPENAI_BASE_URL"] = base_url
            if api_key := env.get("OPENAI_API_KEY"):
                provider.api_key = SecretStr(api_key)
                applied["OPENAI_API_KEY"] = "******"
        case _:
            logger.debug(
                "No request-specific overrides defined for provider type {type}",
                type=provider.type,
            )

    return applied
