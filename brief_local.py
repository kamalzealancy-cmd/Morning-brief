import time
import json
import urllib.request

articles = ""
for name in ["article.txt", "article2.txt", "article3.txt"]:
    with open(name, encoding="utf-8") as f:
        articles += f.read() + "\n\n---\n\n"

prompt = """You are writing a short morning news brief.

Rules:
- Write exactly one bullet point per article.
- Each bullet is one sentence, under 25 words.
- Only use facts from the article. Do not add anything.
- Under each bullet, add the article's link (the first line of each article).
- Plain text only. No bold, no headings.

Example of the output:
- Apple released a new chip that makes its laptops 20% faster.
  Link: https://example.com/apple-chip

Articles:
""" + articles

data = json.dumps({
    "model": "qwen2.5:0.5b",
    "messages": [{"role": "user", "content": prompt}],
    "stream": False,
    "options": {"num_ctx": 16384},
}).encode()

start = time.time()
request = urllib.request.Request("http://localhost:11434/api/chat", data=data,
                                 headers={"Content-Type": "application/json"})
result = json.loads(urllib.request.urlopen(request).read())

print(result["message"]["content"])
print("\nTime:", round(time.time() - start, 1), "seconds")
