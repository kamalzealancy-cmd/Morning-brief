import time
from openai import OpenAI

client = OpenAI()

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

start = time.time()
response = client.responses.create(model="gpt-6-luna", input=prompt)

print(response.output_text)
print("\nTime:", round(time.time() - start, 1), "seconds")
