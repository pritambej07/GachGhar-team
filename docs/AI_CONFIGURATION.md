# AI Gardener configuration

The assistant at `/assistant/` has a basic mode that works without a model provider. The provider-backed conversational integration, server-side tools, rate limits, timeout handling, and graceful fallback are implemented.

To enable a provider, set `AI_PROVIDER`, `AI_PROVIDER_API_KEY`, and the exact `AI_MODEL` in the private environment. OpenAI-compatible providers can use `AI_BASE_URL`; Anthropic uses its provider adapter. Keep API keys out of source control and chat.

See [AI Gardener setup](AI_GARDENER_SETUP.md) for provider account, model, cost, and data-handling details. `AI_RATE_LIMIT_PER_10_MIN`, `AI_DAILY_MESSAGE_LIMIT`, `AI_MAX_OUTPUT_TOKENS`, and `AI_TIMEOUT_SECONDS` control usage.
