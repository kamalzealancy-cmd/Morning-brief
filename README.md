# Morning Brief

An AI news assistant that summarizes tech articles and emails you a short brief every morning.

Built step by step alongside the "6-step roadmap to become an AI engineer" video.

## Demo

<!-- Drag your demo video or GIF here when editing this file on GitHub -->

## What it does

- Gets top headlines from the Hacker News API
- Saves articles in PostgreSQL and makes them searchable with pgvector
- Writes a 3-bullet brief with a link per article (OpenAI)
- Answers questions about saved articles with source links (RAG), and says so when it can't
- An agent that picks between two tools: get headlines, or search saved articles
- Tests and evals on every push (GitHub Actions), monitoring with Langfuse
- Runs on AWS (ECR, ECS Fargate, RDS for PostgreSQL), set up with CDK
- Emails a daily brief at 7:00 AM with EventBridge Scheduler and Amazon SES

## Project steps

| Step | What was added | Files |
|---|---|---|
| 1 | Headlines + one-article summary | `headlines.py`, `summarize.py` |
| 2 | 3-article brief, better prompt, local model comparison | `brief.py`, `brief_better.py`, `brief_local.py` |
| 3 | FastAPI backend, PostgreSQL, RAG with pgvector, agent | `app.py`, `import_articles.py` |
| 4 | Tests, evals, fixes, Langfuse tracing | `tests.py`, `test_set.json` |
| 5 | Docker, AWS with CDK, GitHub Actions, daily email | `Dockerfile`, `infra/`, `.github/workflows/`, `daily_brief.py` |

## Run it on your computer

You need Python 3, PostgreSQL with pgvector (for example Postgres.app on Mac), and an OpenAI API key.

```
pip install -r requirements.txt
createdb morningbrief
export OPENAI_API_KEY=your-key
uvicorn app:app --reload
```

Open http://127.0.0.1:8000/docs to try every endpoint.

Optional: add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` to see traces in Langfuse.

Run the tests (with the app running):

```
python tests.py
```

## Deploy to AWS

You need an AWS account, Docker Desktop, Node.js and the AWS CLI.

1. Sign in: `aws login`
2. Verify your email for sending: `aws sesv2 create-email-identity --email-identity you@example.com`
3. Store your keys in AWS (they never go into the code):

```
aws ssm put-parameter --name /morning-brief/openai-api-key --type SecureString --value "$OPENAI_API_KEY"
aws ssm put-parameter --name /morning-brief/langfuse-public-key --type SecureString --value "$LANGFUSE_PUBLIC_KEY"
aws ssm put-parameter --name /morning-brief/langfuse-secret-key --type SecureString --value "$LANGFUSE_SECRET_KEY"
```

4. Deploy:

```
cd infra
pip install aws-cdk-lib constructs
echo "{\"my_ip\": \"$(curl -s https://checkip.amazonaws.com)/32\", \"email\": \"you@example.com\"}" > cdk.context.json
npx aws-cdk bootstrap
npx aws-cdk deploy
```

5. Import articles into the cloud app (use the `ApiUrl` from the deploy output, without `/docs`):

```
API_URL=http://your-load-balancer-address python import_articles.py
```

The daily email runs every day at 7:00 AM (Asia/Karachi). It summarizes up to 3 new articles, skips days with nothing new, and never sends the same article twice.

## Clean up

To stop all AWS charges:

```
cd infra
npx aws-cdk destroy
```

## GitHub Actions

Add your OpenAI key as a repository secret named `OPENAI_API_KEY`. Every push then runs `tests.py` against a fresh PostgreSQL database.
