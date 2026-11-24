from openai import OpenAI

client = OpenAI()

with open("article.txt", encoding="utf-8") as f:
    article = f.read()

response = client.responses.create(
    model="gpt-6-luna",
    input="Summarize this news article in 3 short bullet points:\n\n" + article,
)

print(response.output_text)
