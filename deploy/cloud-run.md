# Deploying the Slack bot (design)

How this bot would run in a company. The code already supports it: every setting
is read from environment variables, so moving from a local `.env` to a secret
manager is a deployment change, not a code change.

## Pieces

| Piece | Choice | Why |
|---|---|---|
| Runtime | Cloud Run service, `min-instances=1`, CPU always allocated | Socket Mode holds a websocket open to Slack, so the container must stay up |
| Secrets | Secret Manager: `llm-api-key`, `slack-bot-token`, `slack-app-token` | Never in the repo or the image; rotated without a redeploy of code |
| Identity | A dedicated service account with only `secretmanager.secretAccessor` on those three secrets | Least privilege: the bot can't read any other secret |
| Data | Serving copy of three published tables, baked into the image daily | The bot has no warehouse credentials at all |
| LLM access | Through the company's LLM gateway if there is one | Central key, spend limits, logging, PII redaction |
| Logs | stdout JSON (one line per question: tools, SQL, tokens, latency) | Picked up by Cloud Logging; alert on error rate and token spend |

## Commands

```bash
# 1. Secrets (values typed in, never stored in shell history files)
printf '%s' "$LLM_KEY"   | gcloud secrets create llm-api-key     --data-file=-
printf '%s' "$BOT_TOKEN" | gcloud secrets create slack-bot-token --data-file=-
printf '%s' "$APP_TOKEN" | gcloud secrets create slack-app-token --data-file=-

# 2. A service account that can read only those secrets
gcloud iam service-accounts create pricebot
for s in llm-api-key slack-bot-token slack-app-token; do
  gcloud secrets add-iam-policy-binding $s \
    --member=serviceAccount:pricebot@$PROJECT.iam.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
done

# 3. Build and deploy; secrets are mounted as environment variables at runtime
gcloud run deploy pricebot --source . --region europe-west2 \
  --service-account pricebot@$PROJECT.iam.gserviceaccount.com \
  --min-instances 1 --no-cpu-throttling --no-allow-unauthenticated \
  --set-secrets LLM_API_KEY=llm-api-key:latest,SLACK_BOT_TOKEN=slack-bot-token:latest,SLACK_APP_TOKEN=slack-app-token:latest
```

## Alternatives

- **HTTP mode instead of Socket Mode:** Slack calls a public HTTPS endpoint, so Cloud Run can
  scale to zero. Needs request-signature verification (Bolt does this) and a public URL.
- **Daily data refresh:** a scheduled Cloud Build that rebuilds the image after the pipeline's
  06:30 UTC run, or mount the serving file from a bucket instead of baking it in.

This repo runs the bot locally with Socket Mode. The deployment above is the design,
not something this demo runs in a cloud account.
