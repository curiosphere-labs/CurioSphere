from pathlib import Path
import re
import json
import html
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "content" / "articles"
OUTPUT_DIR = ROOT / "articles"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_frontmatter(text):
    """Read simple YAML frontmatter without requiring external packages."""
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    metadata = {}
    current_list = None

    for line in parts[1].strip().splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_list:
            metadata[current_list].append(
                stripped[2:].strip().strip('"\'')
            )
            continue

        match = re.match(r"^([A-Za-z_][\w-]*):(?:\s*(.*))?$", line)
        if not match:
            continue

        key, value = match.groups()
        value = (value or "").strip()

        if value in ("", "[]"):
            metadata[key] = []
            current_list = key
        else:
            metadata[key] = value.strip('"\'')
            current_list = None

    return metadata, parts[2].strip()


def slugify(value):
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "article"


def markdown_to_html(text):
    """Convert basic Markdown into safe, readable HTML."""
    text = html.escape(text)

    text = re.sub(
        r"!\[([^\]]*)\]\((https?://[^\s)]+)\)",
        r'<img alt="\1" src="\2" loading="lazy">',
        text
    )
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        text
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"^### (.+)$", r"<h3>\1</h3>", text, flags=re.M)
    text = re.sub(r"^## (.+)$", r"<h2>\1</h2>", text, flags=re.M)
    text = re.sub(r"^# (.+)$", r"<h1>\1</h1>", text, flags=re.M)

    blocks = re.split(r"\n\s*\n", text)
    rendered = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if re.match(r"^<(h[1-6]|img|ul|ol|li|blockquote|pre)\b", block):
            rendered.append(block)
        else:
            rendered.append("<p>" + block.replace("\n", "<br>\n") + "</p>")

    return "\n".join(rendered)


def make_page(article, body, slug):
    title = html.escape(str(article.get("title", "Untitled")))
    description = html.escape(str(article.get("description", "")))
    category = html.escape(str(article.get("category", "General")))
    author = html.escape(str(article.get("author", "CurioSphere Editorial Team")))
    published = html.escape(str(article.get("date", date.today().isoformat())))
    image = str(article.get("image", "")).strip()

    image_html = ""
    if image.startswith(("https://", "http://", "/")):
        safe_image = html.escape(image, quote=True)
        image_html = (
            f'<img class="hero-image" src="{safe_image}" '
            f'alt="{title}" loading="lazy">'
        )

    content_html = markdown_to_html(body)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{description}">
  <title>{title} | CurioSphere</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: #f6f7fb; color: #172033;
      font-family: Arial, Helvetica, sans-serif; line-height: 1.75;
    }}
    header {{
      background: #fff; border-bottom: 1px solid #e4e7ef;
      padding: 18px 5%; position: sticky; top: 0;
    }}
    header a {{ color: #172033; text-decoration: none; font-weight: bold; }}
    main {{
      max-width: 850px; margin: 38px auto; padding: 32px;
      background: #fff; border-radius: 16px;
      box-shadow: 0 8px 30px rgba(23,32,51,.06);
    }}
    .category {{ color: #5b4bdb; font-weight: bold; }}
    h1 {{ font-size: clamp(2rem, 5vw, 3rem); line-height: 1.2; }}
    .meta {{ color: #657087; font-size: .95rem; }}
    .hero-image {{ width: 100%; max-height: 460px; object-fit: cover; border-radius: 12px; }}
    article {{ overflow-wrap: anywhere; }}
    article img {{ max-width: 100%; height: auto; }}
    article a {{ color: #5145cd; }}
    footer {{ text-align: center; color: #657087; padding: 25px; }}
    @media (max-width: 600px) {{
      main {{ margin: 16px; padding: 20px; }}
    }}
  </style>
</head>
<body>
  <header><a href="../index.html">← CurioSphere</a></header>
  <main>
    <div class="category">{category}</div>
    <h1>{title}</h1>
    <p class="meta">By {author} · {published}</p>
    {image_html}
    <p>{description}</p>
    <article>{content_html}</article>
  </main>
  <footer>© CurioSphere · Explore Beyond the Ordinary</footer>
</body>
</html>
"""


def main():
    if not ARTICLES_DIR.exists():
        print("No content/articles folder found.")
        return

    count = 0

    for file in sorted(ARTICLES_DIR.glob("*.md")):
        raw_text = file.read_text(encoding="utf-8")
        article, body = parse_frontmatter(raw_text)

        title = str(article.get("title", "")).strip()
        if not title:
            print(f"Skipping {file.name}: missing title.")
            continue

        status = str(article.get("status", "Draft")).strip().lower()

        # Only explicitly published articles are placed on the public website.
        if status != "published":
            continue

        slug = slugify(file.stem)
        output_file = OUTPUT_DIR / f"{slug}.html"
        output_file.write_text(
            make_page(article, body, slug),
            encoding="utf-8"
        )

        count += 1
        print(f"Generated: {output_file.relative_to(ROOT)}")

    # Public index for later connection to the CurioSphere homepage.
    published_articles = []

    for file in sorted(OUTPUT_DIR.glob("*.html")):
        if file.name == "index.html":
            continue

        published_articles.append({
            "title": file.stem.replace("-", " ").title(),
            "url": f"articles/{file.name}"
        })

    (ROOT / "articles-index.json").write_text(
        json.dumps(published_articles, indent=2),
        encoding="utf-8"
    )

    print(f"Finished. Generated {count} published article page(s).")


if __name__ == "__main__":
    main()
