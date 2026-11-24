import json
import urllib.request

with open("headlines.json", encoding="utf-8") as f:
    headlines = {h["url"]: h for h in json.load(f)}

for name in ["article.txt", "article2.txt", "article3.txt"]:
    with open(name, encoding="utf-8") as f:
        url = f.readline().strip()
        text = f.read().strip()
    info = headlines.get(url, {})
    article = {
        "title": info.get("title", name),
        "url": url,
        "posted": info.get("posted"),
        "text": text,
    }
    request = urllib.request.Request(
        "http://127.0.0.1:8000/articles",
        data=json.dumps(article).encode(),
        headers={"Content-Type": "application/json"},
    )
    print(name, "->", urllib.request.urlopen(request).read().decode())
