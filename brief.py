import time
from openai import OpenAI

client = OpenAI()

articles = ""
for name in ["article.txt", "article2.txt", "article3.txt"]:
    with open(name, encoding="utf-8") as f:
        articles += f.read() + "\n\n---\n\n"

prompt = "Make a short news brief from these articles:\n\n" + articles

start = time.time()
response = client.responses.create(model="gpt-6-luna", input=prompt)

print(response.output_text)
print("\nTime:", round(time.time() - start, 1), "seconds")
