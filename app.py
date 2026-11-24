import json
import urllib.request

import psycopg
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

client = OpenAI()
app = FastAPI(title="Morning Brief")

MODEL = "gpt-6-luna"
EMBED_MODEL = "text-embedding-3-small"
DATABASE = "host=localhost dbname=morningbrief"


# ---------- Database setup ----------
def db():
    return psycopg.connect(DATABASE, autocommit=True)


with db() as conn:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("""CREATE TABLE IF NOT EXISTS articles (
        id SERIAL PRIMARY KEY,
        title TEXT,
        url TEXT UNIQUE,
        posted TIMESTAMP,
        text TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chunks (
        id SERIAL PRIMARY KEY,
        article_id INT REFERENCES articles(id) ON DELETE CASCADE,
        content TEXT,
        embedding vector(1536))""")


# ---------- Helpers ----------
def split_into_chunks(text, size=200):
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def embed(texts):
    result = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [str(item.embedding) for item in result.data]


def search_articles(query, limit=4):
    vector = embed([query])[0]
    with db() as conn:
        rows = conn.execute("""
            SELECT a.title, a.url, c.content
            FROM chunks c JOIN articles a ON a.id = c.article_id
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s""", (vector, limit)).fetchall()
    return [{"title": t, "link": u, "passage": p} for t, u, p in rows]


def get_headlines(count=5):
    base = "https://hacker-news.firebaseio.com/v0"
    ids = json.loads(urllib.request.urlopen(f"{base}/topstories.json").read())
    headlines = []
    for story_id in ids[:count]:
        item = json.loads(urllib.request.urlopen(f"{base}/item/{story_id}.json").read())
        headlines.append({
            "title": item.get("title"),
            "link": item.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
        })
    return headlines


# ---------- Request shapes ----------
class Article(BaseModel):
    title: str
    url: str
    posted: str | None = None
    text: str


class Question(BaseModel):
    question: str


# ---------- Part A: add an article ----------
@app.post("/articles")
def add_article(article: Article):
    with db() as conn:
        row = conn.execute(
            """INSERT INTO articles (title, url, posted, text) VALUES (%s, %s, %s, %s)
               ON CONFLICT (url) DO NOTHING RETURNING id""",
            (article.title, article.url, article.posted, article.text)).fetchone()
        if row is None:
            return {"message": "Already saved"}
        chunks = split_into_chunks(article.text)
        if chunks:
            for content, vector in zip(chunks, embed(chunks)):
                conn.execute(
                    "INSERT INTO chunks (article_id, content, embedding) VALUES (%s, %s, %s::vector)",
                    (row[0], content, vector))
    return {"message": "Saved", "id": row[0], "chunks": len(chunks)}


@app.get("/articles")
def list_articles():
    with db() as conn:
        rows = conn.execute("SELECT id, title, url, posted FROM articles ORDER BY posted DESC").fetchall()
    return [{"id": i, "title": t, "link": u, "posted": str(p)} for i, t, u, p in rows]


# ---------- Part A: generate a brief (fixed workflow) ----------
BRIEF_PROMPT = """You are writing a short morning news brief.

Rules:
- Write exactly one bullet point per article.
- Each bullet is one sentence, under 25 words.
- Only use facts from the article. Do not add anything.
- Under each bullet, add the article's link.
- Plain text only. No bold, no headings.

Example of the output:
- Apple released a new chip that makes its laptops 20% faster.
  Link: https://example.com/apple-chip

Articles:
"""


@app.post("/brief")
def make_brief():
    with db() as conn:
        rows = conn.execute(
            "SELECT title, url, text FROM articles ORDER BY posted DESC LIMIT 3").fetchall()
    if not rows:
        return {"brief": "No saved articles yet."}
    articles = "".join(f"Title: {t}\nLink: {u}\n{x}\n\n---\n\n" for t, u, x in rows)
    response = client.responses.create(model=MODEL, input=BRIEF_PROMPT + articles)
    return {"brief": response.output_text}


# ---------- Part B: RAG ----------
@app.post("/ask")
def ask(q: Question):
    passages = search_articles(q.question)
    context = "\n\n".join(f"Source: {p['title']} ({p['link']})\n{p['passage']}" for p in passages)
    prompt = f"""Answer the question using ONLY the passages below.
After the answer, list the source links you used.
If the passages do not contain the answer, reply exactly:
"I couldn't find that in the saved articles."

Passages:
{context}

Question: {q.question}"""
    response = client.responses.create(model=MODEL, input=prompt)
    return {"answer": response.output_text}


# ---------- Part C: agent with two tools ----------
TOOLS = [
    {
        "type": "function",
        "name": "get_headlines",
        "description": "Get today's top Hacker News headlines and their links (no article text).",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "search_articles",
        "description": "Search the user's saved articles. Returns relevant passages with source links.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to search for"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


@app.post("/agent")
def agent(q: Question):
    messages = [
        {"role": "system", "content": "You help with tech news. Use get_headlines for what's new on "
         "Hacker News. Use search_articles for questions about saved articles. Always include links. "
         "If the tools don't have the answer, say so."},
        {"role": "user", "content": q.question},
    ]
    tools_used = []
    for _ in range(5):
        response = client.responses.create(model=MODEL, input=messages, tools=TOOLS)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            return {"tools_used": tools_used, "answer": response.output_text}
        messages += response.output
        for call in calls:
            args = json.loads(call.arguments or "{}")
            if call.name == "get_headlines":
                result = get_headlines()
            else:
                result = search_articles(args.get("query", q.question))
            tools_used.append(call.name)
            messages.append({"type": "function_call_output", "call_id": call.call_id,
                             "output": json.dumps(result)})
    return {"tools_used": tools_used, "answer": "Sorry, I couldn't finish that."}
