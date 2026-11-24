import os

import boto3
from langfuse import get_client, observe

from app import BRIEF_PROMPT, ask_model, db

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")


@observe(name="daily-email")
def main():
    with db() as conn:
        conn.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS emailed_at TIMESTAMPTZ")
        conn.execute("CREATE TABLE IF NOT EXISTS email_runs (run_date DATE PRIMARY KEY)")

        # Up to 3 new articles that were never emailed
        rows = conn.execute("""SELECT id, title, url, text FROM articles
                               WHERE emailed_at IS NULL
                               ORDER BY posted DESC NULLS LAST LIMIT 3""").fetchall()
        if not rows:
            print("No new articles today. Skipping the email.")
            return

        # Only one email per day, even if the task runs twice
        claimed = conn.execute("""INSERT INTO email_runs (run_date) VALUES (CURRENT_DATE)
                                  ON CONFLICT DO NOTHING RETURNING run_date""").fetchone()
        if not claimed:
            print("Today's email was already sent. Skipping.")
            return

        try:
            articles = "".join(f"Title: {t}\nLink: {u}\n{x}\n\n---\n\n" for _, t, u, x in rows)
            brief = ask_model(input=BRIEF_PROMPT + articles).output_text

            if EMAIL_TO:
                boto3.client("sesv2").send_email(
                    FromEmailAddress=EMAIL_FROM,
                    Destination={"ToAddresses": [EMAIL_TO]},
                    Content={"Simple": {
                        "Subject": {"Data": "Your Morning Brief"},
                        "Body": {"Text": {"Data": brief}},
                    }},
                )
                print(f"Sent the Morning Brief with {len(rows)} articles.")
            else:
                print("No EMAIL_TO set, so here is the brief instead:\n\n" + brief)

            conn.execute("UPDATE articles SET emailed_at = now() WHERE id = ANY(%s)", ([r[0] for r in rows],))
        except Exception:
            conn.execute("DELETE FROM email_runs WHERE run_date = CURRENT_DATE")
            raise


if __name__ == "__main__":
    main()
    get_client().flush()
