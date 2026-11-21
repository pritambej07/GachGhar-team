# AI Gardener setup

The chat works in **basic mode** (simple search, cart, orders) with no configuration. To enable the full conversational
Gardener (Bengali and English, recommendations, comparisons, cart and wishlist actions) you need an **API key**.

## What you need
- An account on a provider's **developer platform** (for example OpenAI Platform or Anthropic Console) with billing enabled.
- A ChatGPT or Claude *chat subscription does not include API access or credits*. API usage is billed separately, per use.
- The exact **model id** from the provider's dashboard.

## Configure (.env only, never in code)
OpenAI or OpenAI-compatible:
    AI_PROVIDER=openai
    AI_PROVIDER_API_KEY=your-key
    AI_MODEL=model-id-from-dashboard
    AI_BASE_URL=            (blank for OpenAI; set for other compatible providers)
Anthropic:
    AI_PROVIDER=anthropic
    AI_PROVIDER_API_KEY=your-key
    AI_MODEL=model-id-from-dashboard

Cost controls: AI_RATE_LIMIT_PER_10_MIN, AI_DAILY_MESSAGE_LIMIT, AI_MAX_OUTPUT_TOKENS, AI_TIMEOUT_SECONDS.
Product names, prices, stock and the customer's own order summaries are sent to the provider as tool results. Email,
phone and address are never sent.
