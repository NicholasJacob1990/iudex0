# Billing Spec (Poe-style)

## Anchor
- usd_per_point: 0.00003 (USD 30 per 1,000,000 points)

## Size profiles
- S: ~800 input / 300 output
- M: ~2,500 input / 1,200 output
- L: ~4,000 input / 1,500 output

## LLM rate card (points per call)
- gpt-5.2: S 224 / M 847 / L 1120
- gpt-5-mini: S 40 / M 150 / L 200
- claude-4.5-sonnet: S 300 / M 1120 / L 1500
- claude-4.5-opus: S 520 / M 1950 / L 2600
- gemini-3-pro: S 220 / M 820 / L 1100
- gemini-3-flash: S 60 / M 220 / L 300
- grok-4: S 300 / M 1120 / L 1500
- llama-4: S 19 / M 68 / L 95

## Perplexity grounded LLM (Sonar family)
- pricing rule: points = (token_points * context_multiplier) + request_fee_points; then apply points_multiplier
- defaults: search_context_size=low, sonar_pro_search_type=fast, auto_search_type_estimate=pro
- token_points_per_call:
  - sonar: S 44 / M 148 / L 220
  - sonar-pro: S 276 / M 1020 / L 1380
  - sonar-reasoning-pro: S 160 / M 584 / L 800
- request_fee_points_per_call:
  - sonar: low 200 / medium 320 / high 480
  - sonar-pro fast: low 240 / medium 400 / high 560
  - sonar-pro pro: low 560 / medium 720 / high 880
  - sonar-reasoning-pro: low 240 / medium 400 / high 560
- disable_search: request_fee_points = 0

## Tool rate card (points per event)
- web_search_request: 200
- deep_research_effort:
  - low: 16400
  - medium: 47600
  - high: 52800
- perplexity.search_api.points_per_request: 200

## Plans
- free: 3,000 points/day ($0)
- starter: 300,000 points/month ($9)
- standard: 1,000,000 points/month ($30)
- pro: 2,500,000 points/month ($75)
- advanced: 5,000,000 points/month ($150)
- ultra: 12,500,000 points/month ($375)
- topup_100k: 100,000 points (one_off, $3)
- topup_1m: 1,000,000 points (one_off, $30)

## Caps by plan
- free: web_search_requests=1, deep_research_effort_max=none, deep_research_per_month=0, granular_passes=1, final_review_loops=1, style_loops=1, hil_iterations=0
- starter: web_search_requests=3, deep_research_effort_max=low, deep_research_per_month=1, granular_passes=1, final_review_loops=1, style_loops=1, hil_iterations=1
- standard: web_search_requests=5, deep_research_effort_max=low, deep_research_per_month=5, granular_passes=2, final_review_loops=2, style_loops=2, hil_iterations=1
- pro: web_search_requests=5, deep_research_effort_max=medium, deep_research_per_month=20, granular_passes=3, final_review_loops=3, style_loops=3, hil_iterations=2
- advanced: web_search_requests=5, deep_research_effort_max=high, deep_research_per_month=60, granular_passes=3, final_review_loops=3, style_loops=3, hil_iterations=3
- ultra: web_search_requests=5, deep_research_effort_max=high, deep_research_per_month=200, granular_passes=3, final_review_loops=3, style_loops=3, hil_iterations=5

## Enforcement notes
- deep_research_effort is resolved by plan caps before execution and used in billing events.
- web_search fan-out and search_multi max_queries are capped per plan.
- HIL interrupts are capped per plan; when cap is reached, flow auto-approves.
- final review loops use max_final_review_loops.
- granular debate retries use max_granular_passes minus one.

## Usage events
Each call should emit:
- kind, provider, model
- meta.node, meta.size, meta.effort, meta.points_multiplier
- meta.search_context_size, meta.search_type, meta.disable_search (Perplexity grounded LLM)
- points (resolved by billing_config.json)
