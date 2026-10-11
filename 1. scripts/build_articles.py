from pathlib import Path
from datetime import date
import html
import json
import re
import shutil


# --------------------------------------------------
# CurioSphere article publishing configuration
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "content" / "articles"
OUTPUT_DIR = ROOT / "articles"
INDEX_FILE = ROOT / "articles-index.json"

SITE_NAME = "CurioSphere"
SITE_TAGLINE = "Explore Beyond the Ordinary"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# Utility functions
# --------------------------------------------------

def parse_frontmatter(text):
    """Read the simple YAML frontmatter used by CurioSphere."""

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
                stripped[2:].strip().strip("\"'")
            )
            continue

        match = re.match(
            r"^([A-Za-z_][\w-]*):(?:\s*(.*))?$",
            line
        )

        if not match:
            continue

        key, value = match.groups()
        value = (value or "").strip()

        if value in ("", "[]"):
            metadata[key] = []
            current_list = key

        elif (
            value.startswith("[")
            and value.endswith("]")
        ):
            items = value[1:-1].split(",")
            metadata[key] = [
                item.strip().strip("\"'")
                for item in items
                if item.strip()
            ]
            current_list = None

        else:
            metadata[key] = value.strip("\"'")
            current_list = None

    return metadata, parts[2].strip()


def slugify(value):
    """Convert text into a URL-friendly slug."""

    value = str(value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)

    return value.strip("-") or "article"


def as_bool(value):
    """Interpret common true/false metadata values."""

    return str(value).strip().lower() in {
        "true", "yes", "1"
    }


def safe_url(value):
    """Allow only HTTP(S) links or local relative paths."""

    value = str(value or "").strip()

    if value.startswith(("https://", "http://")):
        return value

    if (
        value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
    ):
        return value

    return ""


# --------------------------------------------------
# Basic Markdown rendering
# --------------------------------------------------

def markdown_to_html(text):
    """
    Render basic Markdown without external dependencies.
    Raw HTML in article text is escaped for safety.
    """

    rendered = []
    paragraph = []

    def flush_paragraph():
        if paragraph:
            content = "<br>\n".join(paragraph)
            rendered.append(f"<p>{content}</p>")
            paragraph.clear()

    for original_line in text.splitlines():
        line = original_line.strip()

        if not line:
            flush_paragraph()
            continue

        # Headings
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)

        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            content = format_inline(heading.group(2))
            rendered.append(
                f"<h{level}>{content}</h{level}>"
            )
            continue

        # Horizontal rules
        if re.fullmatch(r"([-*_]\s*){3,}", line):
            flush_paragraph()
            rendered.append("<hr>")
            continue

        # Unordered lists
        bullet = re.match(r"^[-*]\s+(.+)$", line)

        if bullet:
            flush_paragraph()

            if not rendered or rendered[-1] != "__UL__":
                rendered.append("__UL__")

            rendered.append(
                "<li>" + format_inline(bullet.group(1)) + "</li>"
            )
            continue

        flush_paragraph()
        rendered.append(format_inline(line))

    flush_paragraph()

    # Wrap consecutive list items in <ul> elements.
    output = []
    inside_list = False

    for item in rendered:
        if item == "__UL__":
            if inside_list:
                output.append("</ul>")

            output.append("<ul>")
            inside_list = True

        elif item.startswith("<li>"):
            if not inside_list:
                output.append("<ul>")
                inside_list = True

            output.append(item)

        else:
            if inside_list:
                output.append("</ul>")
                inside_list = False

            output.append(item)

    if inside_list:
        output.append("</ul>")

    return "\n".join(output)


def format_inline(text):
    """Format common inline Markdown features."""

    text = html.escape(text, quote=False)

    # Inline code
    text = re.sub(
        r"`([^`]+)`",
        r"<code>\1</code>",
        text
    )

    # Images
    text = re.sub(
        r'!\[([^\]]*)\]\((https?://[^\s)]+)\)',
        lambda m: (
            '<img alt="' + html.escape(m.group(1), quote=True)
            + '" src="' + html.escape(m.group(2), quote=True)
            + '" loading="lazy">'
        ),
        text
    )

    # Links
    text = re.sub(
        r'\[([^\]]+)\]\((https?://[^\s)]+)\)',
        lambda m: (
            '<a href="' + html.escape(m.group(2), quote=True)
            + '" target="_blank" rel="noopener noreferrer">'
            + m.group(1) + '</a>'
        ),
        text
    )

    # Bold and italic
    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<strong>\1</strong>",
        text
    )

    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        r"<em>\1</em>",
        text
    )

    return text


# --------------------------------------------------
# Article page generation
# --------------------------------------------------

def make_page(article, body):
    """Create an individual HTML page for a published article."""

    title = html.escape(
        str(article.get("title", "Untitled"))
    )

    description = html.escape(
        str(article.get("description", ""))
    )

    category = html.escape(
        str(article.get("category", "General"))
    )

    author = html.escape(
        str(article.get(
            "author", "CurioSphere Editorial Team"
        ))
    )

    published = html.escape(
        str(article.get("date", date.today().isoformat()))
    )

    image = safe_url(article.get("image", ""))

    image_html = ""

    if image:
        image_html = (
            '<img class="hero-image" '
            f'src="{html.escape(image, quote=True)}" '
            f'alt="{title}" loading="lazy">'
        )

    content_html = markdown_to_html(body)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <meta name="description" content="{description}">
  <meta name="author" content="{author}">

  <title>{title} | {SITE_NAME}</title>

  <style>
    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: #f6f7fb;
      color: #172033;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.75;
    }}

    header {{
      background: #fff;
      border-bottom: 1px solid #e4e7ef;
      padding: 18px 5%;
    }}

    header a {{
      color: #172033;
      text-decoration: none;
      font-weight: bold;
    }}

    main {{
      max-width: 850px;
      margin: 38px auto;
      padding: 32px;
      background: #fff;
      border-radius: 16px;
      box-shadow: 0 8px 30px rgba(23,32,51,.06);
    }}

    .category {{
      color: #5b4bdb;
      font-weight: bold;
    }}

    h1 {{
      font-size: clamp(2rem, 5vw, 3rem);
      line-height: 1.2;
    }}

    .meta {{
      color: #657087;
      font-size: .95rem;
    }}

    .hero-image {{
      width: 100%;
      max-height: 460px;
      object-fit: cover;
      border-radius: 12px;
    }}

    article {{
      overflow-wrap: anywhere;
    }}

    article img {{
      max-width: 100%;
      height: auto;
    }}

    article a {{
      color: #5145cd;
    }}

    footer {{
      text-align: center;
      color: #657087;
      padding: 25px;
    }}

    @media (max-width: 600px) {{
      main {{
        margin: 16px;
        padding: 20px;
      }}
    }}
  </style>
</head>

<body>
  <header>
    <a href="../index.html">← {SITE_NAME}</a>
  </header>

  <main>
    <div class="category">{category}</div>

    <h1>{title}</h1>

    <p class="meta">By {author} · {published}</p>

    {image_html}

    <p>{description}</p>

    <article>{content_html}</article>
  </main>

  <footer>
    © {SITE_NAME} · {SITE_TAGLINE}
  </footer>
</body>
</html>
"""


# --------------------------------------------------
# Main publishing process
# --------------------------------------------------

def main():
    if not ARTICLES_DIR.exists():
        raise SystemExit(
            "ERROR: content/articles directory was not found."
        )

    # Read the previous index so we know which HTML pages
    # were generated by an earlier version of this script.
    previous_slugs = set()

    if INDEX_FILE.exists():
        try:
            previous_index = json.loads(
                INDEX_FILE.read_text(encoding="utf-8")
            )

            for item in previous_index:
                url = str(item.get("url", ""))
                match = re.fullmatch(
                    r"articles/([a-z0-9-]+)\.html",
                    url
                )

                if match:
                    previous_slugs.add(match.group(1))

        except (json.JSONDecodeError, OSError):
            print(
                "WARNING: Could not read the previous index. "
                "No old pages will be deleted."
            )

    published_articles = []
    used_slugs = set()

    for source_file in sorted(ARTICLES_DIR.glob("*.md")):
        raw_text = source_file.read_text(encoding="utf-8")
        article, body = parse_frontmatter(raw_text)

        title = str(article.get("title", "")).strip()

        if not title:
            print(
                f"WARNING: Skipping {source_file.name}: "
                "missing title."
            )
            continue

        status = str(
            article.get("status", "Draft")
        ).strip().lower()

        # Only explicitly published articles are public.
        if status != "published":
            print(f"Not publishing draft: {source_file.name}")
            continue

        # Use the source filename to create a stable URL.
        slug = slugify(source_file.stem)

        if slug in used_slugs:
            raise SystemExit(
                f"ERROR: Duplicate article slug: {slug}"
            )

        used_slugs.add(slug)

        output_file = OUTPUT_DIR / f"{slug}.html"

        output_file.write_text(
            make_page(article, body),
            encoding="utf-8"
        )

        try:
            article_date = str(
                article.get("date", date.today().isoformat())
            )
        except Exception:
            article_date = date.today().isoformat()

        tags = article.get("tags", [])

        if isinstance(tags, str):
            tags = [tags] if tags else []

        if not isinstance(tags, list):
            tags = []

        record = {
            "title": title,
            "description": str(
                article.get("description", "")
            ),
            "category": str(
                article.get("category", "General")
            ),
            "subcategory": str(
                article.get("subcategory", "")
            ),
            "author": str(
                article.get(
                    "author", "CurioSphere Editorial Team"
                )
            ),
            "date": article_date,
            "featured": as_bool(
                article.get("featured", False)
            ),
            "image": safe_url(article.get("image", "")),
            "tags": tags,
            "url": f"articles/{slug}.html"
        }

        published_articles.append(record)

        print(f"Generated: articles/{slug}.html")

    # Remove stale pages only when they were recorded
    # in the previous generated index.
    current_slugs = {
        item["url"].removeprefix("articles/").removesuffix(".html")
        for item in published_articles
    }

    for old_slug in previous_slugs - current_slugs:
        old_file = OUTPUT_DIR / f"{old_slug}.html"

        if old_file.is_file():
            old_file.unlink()
            print(f"Removed unpublished page: {old_file.name}")

    # Featured articles first, then newest dates.
    published_articles.sort(
        key=lambda item: (
            item["featured"],
            item["date"]
        ),
        reverse=True
    )

    INDEX_FILE.write_text(
        json.dumps(
            published_articles,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print()
    print(
        "Publishing preparation completed successfully."
    )
    print(
        f"Published articles: {len(published_articles)}"
    )
    print(
        f"Article index: {INDEX_FILE.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
