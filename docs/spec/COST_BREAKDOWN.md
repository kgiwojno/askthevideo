# AskTheVideo — Cost Breakdown

**Project:** YouTube Video QA Chatbot (RAG + LangChain Agent)
**Author:** Krzysztof Giwojno
**Bootcamp:** IronHack AI Engineering, Final Project
**Date:** February 2026

---

## Summary

Total project cost: **~$5-7 in Anthropic API credits.** Everything else runs on free tiers.

| Component | Provider | Cost |
|---|---|---|
| LLM (answer generation) | Anthropic Claude Sonnet 4.6 | ~$5-7 total |
| Embeddings | Pinecone Inference (llama-text-embed-v2) | Free |
| Vector database | Pinecone Starter | Free |
| Agent tracing + eval | LangSmith | Free |
| App hosting | Koyeb (Docker) | Free |
| Landing page hosting | OVH (static HTML) | Free (existing hosting) |

---

## How the costs work

The only paid component is **Anthropic's Claude Sonnet 4.6** API, used to generate answers from retrieved transcript chunks. Pricing is per token (1 token ≈ 0.75 words):

| | Price per 1M tokens |
|---|---|
| Input (question + context sent to Claude) | $3.00 |
| Output (Claude's answer) | $15.00 |

Everything else — embeddings, vector storage, search, hosting — is covered by free tiers.

---

## Cost per action

### Embedding a video (one-time, at ingestion)

| Video length | Transcript tokens | Embedding cost | Storage cost |
|---|---|---|---|
| 10 min | ~2,400 | Free | Free |
| 20 min | ~5,000 | Free | Free |
| 30 min | ~7,400 | Free | Free |
| 60 min | ~14,700 | Free | Free |

Embeddings are generated via Pinecone Inference API (free tier: 5M tokens/month). A 60-min video uses ~14.7K tokens — that's 0.3% of the monthly allowance. You could embed **~340 sixty-minute videos per month** before hitting the limit.

### Answering a question (per query, Claude API)

**Original estimates vs actual measurements (182-min test video):**

| Query type | Est. input | Est. cost | Actual input | Actual cost | Notes |
|---|---|---|---|---|---|
| **vector_search** | ~2,000-3,000 | ~$0.01-0.02 | ~8,700 | **$0.033** | 10 chunks with timestamped text = more context |
| **summarize_video** (fresh, 60-min) | ~15,000 | ~$0.05 | ~43,500* | **$0.141*** | *182-min video. 60-min would be ~$0.05 |
| **summarize_video** (cached) | 0 | $0.00 | 0 | **$0.00** | Cache hit in ~0.6s |
| **list_topics** (fresh, 60-min) | ~15,000 | ~$0.05 | ~43,500* | **$0.143*** | *182-min video. 60-min would be ~$0.05 |
| **list_topics** (cached) | 0 | $0.00 | 0 | **$0.00** | Cache hit in ~0.6s |
| **compare_videos** (2 videos) | ~4,000-5,000 | ~$0.02 | ~8,900 | **$0.041** | Single video test |
| **get_metadata** (no LLM call) | 0 | $0.00 | 0 | **$0.00** | Pinecone fetch only |

**Why vector_search actuals are higher:** 10 chunks (not 5) with full timestamped text provide richer context for better answers. Summarize/topics scale linearly with video duration — estimates for 60-min videos hold.

**Revised 10-question session estimate (60-min video): ~$0.25-0.30**

**Key optimization:** Summaries and topic lists are cached in Pinecone after first generation. Subsequent requests for the same video's summary cost $0.00 — even across different users.

### Example: vector_search cost calculation

```
User asks: "What does the video say about backpropagation?"

→ System retrieves 5 transcript chunks (~400 tokens each)    = 2,000 tokens
→ System prompt + question                                    = 500 tokens
→ Total input to Claude                                       = 2,500 tokens
→ Claude generates answer                                     = 400 tokens

Input cost:  2,500 × $0.000003 = $0.0075
Output cost:   400 × $0.000015 = $0.0060
Total:                           $0.0135 per question
```

---

## Cost per session

A typical free-tier user session:

| Action | Details | Cost |
|---|---|---|
| Load 3 videos | Embedding (Pinecone Inference) | $0.00 |
| 7 search questions | 7 × $0.015 | $0.105 |
| 1 summary request | First time: $0.05, cached: $0.00 | $0.00-0.05 |
| 1 topics request | First time: $0.05, cached: $0.00 | $0.00-0.05 |
| 1 comparison | 1 × $0.02 | $0.02 |
| **Session total** | | **~$0.13-0.22** |

Free tier limit: **10 questions per session** → max cost per free user: ~$0.15

---

## Total project budget

| Phase | Queries | Estimated cost |
|---|---|---|
| Development + debugging | ~50 | ~$1.00 |
| LangSmith evaluation (15 test pairs × 3 runs) | ~45 | ~$0.70 |
| Live demo (presentation day) | ~20 | ~$0.50 |
| Real users (20 users × 1 session) | ~200 | ~$3.00 |
| **Total** | | **~$5-7** |

---

## Free tier limits vs expected usage

Assuming moderate traffic of ~20 users per day:

| Resource | Monthly limit | Expected usage | Headroom |
|---|---|---|---|
| Pinecone Inference (embeddings) | 5M tokens | ~1.5M tokens | 70% unused |
| Pinecone reads (search queries) | 1M | ~6K | 99% unused |
| Pinecone writes (vector upserts) | 2M | ~3K | 99% unused |
| Pinecone storage | 2 GB | hundreds of videos | Plenty |
| LangSmith traces | 5K | ~600 | 88% unused |
| Koyeb hosting (compute) | 512 MB RAM, 0.1 vCPU | Always on | — |

All free tiers have significant headroom even at 20 users/day.

---

## Cost control mechanisms

| Mechanism | What it controls | Limit |
|---|---|---|
| Questions per session | Total Claude API calls per user | 10 (free), unlimited (contributor) |
| Videos per session | Number of videos loaded | 5 (free), unlimited (contributor) |
| Video duration cap | Max transcript length for summarize/topics | 60 min (free), unlimited (contributor) |
| Summary/topics caching | Prevents duplicate expensive calls | Cached in Pinecone after first generation |
| Cross-user video reuse | Prevents duplicate embedding costs | Check namespace before re-embedding |

---

## Architecture decisions that minimize cost

1. **Pinecone Inference for embeddings** — free tier covers hundreds of videos/month. No need for paid embedding APIs (OpenAI ada-002 would cost ~$0.02 per 60-min video).

2. **Pinecone as vector DB** — free 2GB storage offloads everything from the server. No need for a paid database.

3. **Summary caching in Pinecone** — each video summarized once ever, stored as a special record. All future requests for the same summary cost $0.

4. **Cross-user video reuse** — if User A loads a popular video, User B gets it instantly with zero embedding cost.

5. **Koyeb free tier for hosting** — server is just a thin orchestration layer (Streamlit + LangChain). All heavy work (embeddings, storage, search) is handled by Pinecone.

6. **Claude Sonnet 4.6 (not Opus)** — near-Opus quality at Sonnet pricing ($3/$15 vs $15/$75 per MTok). Same answer quality for 5× lower cost.

7. **Session-based limits** — 10 questions per session prevents any single user from generating excessive API costs.

---

## Comparison: What this would cost at scale

For context, here's what the same system would cost without free tiers:

| Scale | Monthly Claude cost | Monthly Pinecone cost | Monthly hosting | Total |
|---|---|---|---|---|
| Demo (20 users total) | ~$3 | $0 (free tier) | $0 (free tier) | **~$3** |
| Light (100 users/month) | ~$15 | $0 (free tier) | $0 (free tier) | **~$15** |
| Medium (1,000 users/month) | ~$150 | $70 (Standard) | $10 (Koyeb paid) | **~$230** |
| Heavy (10,000 users/month) | ~$1,500 | $70 (Standard) | $25 (Koyeb paid) | **~$1,600** |

The free tier comfortably handles the bootcamp demo and months of light post-launch traffic.

---

## Tech stack with pricing

| Component | Service | Tier | Monthly cost |
|---|---|---|---|
| LLM | Anthropic Claude Sonnet 4.6 | Pay-per-use | ~$3-5 (usage dependent) |
| Embeddings | Pinecone Inference (llama-text-embed-v2) | Free | $0 |
| Vector DB | Pinecone Starter | Free | $0 |
| App hosting | Koyeb | Free | $0 |
| Landing page | OVH / any static host | Free | $0 |
| Tracing + eval | LangSmith | Free | $0 |
| Analytics | Google Analytics | Free | $0 |
| Feedback | Google Forms | Free | $0 |
| Error alerts | Discord webhook | Free | $0 |
| **Total monthly** | | | **~$3-5** |

---

## Monetization Projection

### Revenue sources

| Source | Model | Implementation |
|---|---|---|
| Google AdSense | Per-impression + per-click ads | Landing page + app sidebar |
| Buy Me a Coffee | Voluntary contributions ($3-5 each) | Landing page + app sidebar |
| Access key sales | Unlimited access via BMC contribution | Manual key delivery |

### Google AdSense — realistic metrics for a small tech tool

| Metric | Pessimistic | Realistic | Optimistic |
|---|---|---|---|
| CPM (per 1,000 impressions) | $0.50 | $1.50 | $3.00 |
| CTR (click-through rate) | 0.5% | 1.5% | 3.0% |
| CPC (cost per click) | $0.05 | $0.15 | $0.40 |

### Ad revenue projection by traffic level

| Daily users | Page views/mo* | Monthly ad revenue (realistic) | Monthly ad revenue (optimistic) |
|---|---|---|---|
| 5 | ~300 | $0.45 | $0.90 |
| 20 | ~1,200 | $1.80 | $3.60 |
| 50 | ~3,000 | $4.50 | $9.00 |
| 100 | ~6,000 | $9.00 | $18.00 |
| 500 | ~30,000 | $45.00 | $90.00 |

*Assuming ~2 page views per visit (landing page + app)

### Break-even analysis (ads only)

| Daily users | Monthly Claude cost | Monthly ad revenue | Break-even? |
|---|---|---|---|
| 5 | ~$0.75 | $0.45 | ❌ No |
| 20 | ~$3.00 | $1.80-3.60 | ⚠️ Maybe |
| 50 | ~$7.50 | $4.50-9.00 | ⚠️ Close |
| 100 | ~$15.00 | $9.00-18.00 | ✅ Likely |

Ads alone require ~50-100 daily users to reliably cover costs.

### Combined revenue model (ads + BMC)

The realistic path to sustainability combines both revenue streams:

| Source | Revenue/mo (at 50 users/day) | Revenue/mo (at 100 users/day) |
|---|---|---|
| Google AdSense | ~$4.50 | ~$9.00 |
| Buy Me a Coffee (2-3 contributions/mo) | ~$10-15 | ~$15-25 |
| **Total revenue** | **~$15-20** | **~$24-34** |
| **Total cost** | **~$7.50** | **~$15.00** |
| **Net profit** | **+$7-12** | **+$9-19** |

**Key insight:** At low traffic, BMC contributions are the bigger revenue driver. One $5 coffee covers ~33 free user sessions. Ads become meaningful only at 50+ daily users.

### Path to self-sustaining

```
Phase 1: Launch (0-30 days)
├── Traffic: 5-10 users/day (bootcamp peers, LinkedIn network)
├── Revenue: ~$5-10/mo (mostly BMC from classmates/network)
├── Cost: ~$1-2/mo
├── Status: ✅ Profitable (low traffic = low cost too)
│
Phase 2: Growth (1-3 months)
├── Traffic: 20-50 users/day (SEO kicks in, word of mouth)
├── Revenue: ~$10-20/mo (BMC + early ad revenue)
├── Cost: ~$3-8/mo
├── Status: ✅ Sustainable
│
Phase 3: Scale (3-6 months)
├── Traffic: 100+ users/day (organic search, social sharing)
├── Revenue: ~$25-35/mo (ads become meaningful)
├── Cost: ~$15/mo
├── Status: ✅ Profitable, consider premium features
```

### Revenue per $1 spent on Claude API

| Scenario | Claude cost | Revenue | Return |
|---|---|---|---|
| Free user (10 questions, ads only) | $0.15 | $0.003 (ad impressions) | 2% — loss |
| Free user (10 questions, ads + eventual BMC) | $0.15 | $0.05 (blended avg) | 33% — loss |
| Contributing user ($5 BMC + unlimited) | $0.50 (avg session) | $5.00 | 1000% — profit |

**Conclusion:** The business model works when a small percentage of users contribute via BMC. Even a 2-3% conversion rate from free to contributing users makes the project self-sustaining.

---

*Document prepared for IronHack AI Engineering Bootcamp, February 2026*
