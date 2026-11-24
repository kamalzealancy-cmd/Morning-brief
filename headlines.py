import json
import urllib.request
from datetime import datetime

url = "https://hacker-news.firebaseio.com/v0/topstories.json"
ids = json.loads(urllib.request.urlopen(url).read())

headlines = []
for story_id in ids[:5]:
    item_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
    item = json.loads(urllib.request.urlopen(item_url).read())
    headlines.append({
        "title": item.get("title"),
        "posted": datetime.fromtimestamp(item["time"]).strftime("%Y-%m-%d %H:%M"),
        "url": item.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
    })

with open("headlines.json", "w", encoding="utf-8") as f:
    json.dump(headlines, f, indent=2)

for h in headlines:
    print(h["title"])
    print("  ", h["posted"], "-", h["url"])
