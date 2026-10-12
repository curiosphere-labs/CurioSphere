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
HOME_URL = "../index.html"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# Utility functions
# --------------------------------------------------

def parse_frontmatter(text):
    """Read the simple YAML-like frontmatter used by CurioSphere."""
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

        match = re.match(r"^([A-Za-z_][\w-]*):(?:\s*(.*))?$", line)
        if not match:
            continue

        key, value = match.groups()
        value = (value or "").strip()

        if value in ("", "[]"):
            metadata[key] = []
            current_list = key
        elif value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            metadata[key] = [
                item.strip().strip("\"'")
                for item in items if item.strip()
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
    return str(value).strip().lower() in {"true", "yes", "1"}


def safe_url(value):
    """Allow HTTP(S) links and safe local relative paths."""
    value = str(value or "").strip()
    if value.startswith(("https://", "http://")):
        return value
    if (
        value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
    ):
        return value
    if (
        value
        and not value.startswith(("#", "//"))
        and "\\" not in value
        and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value)
    ):
        return value
    return ""


def estimate_reading_time(text):
    words = re.findall(r"\b[\w'-]+\b", text)
    minutes = max(1, round(len(words) / 220))
    return f"{minutes} min read"


def escape_attr(value):
    return html.escape(str(value or ""), quote=True)


# --------------------------------------------------
# Markdown rendering
# Supports headings, paragraphs, lists, quotes, images,
# links, bold, italics, inline code, and horizontal rules.
# Raw HTML is escaped for safety.
# --------------------------------------------------

def format_inline(text):
    text = html.escape(text, quote=False)

    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Images: ![alt text](https://...)
    text = re.sub(
        r'!\[([^\]]*)\]\((https?://[^\s)]+)\)',
        lambda m: (
            '<figure class="inline-figure">'
            '<img src="' + escape_attr(m.group(2)) +
            '" alt="' + escape_attr(m.group(1)) +
            '" loading="lazy">'
            + (('<figcaption>' + html.escape(m.group(1)) +
                '</figcaption>') if m.group(1) else '')
            + '</figure>'
        ),
        text
    )

    # Links: [label](https://...)
    text = re.sub(
        r'\[([^\]]+)\]\((https?://[^\s)]+)\)',
        lambda m: (
            '<a href="' + escape_attr(m.group(2)) +
            '" target="_blank" rel="noopener noreferrer">' +
            m.group(1) + '</a>'
        ),
        text
    )

    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def markdown_to_html(markdown_text):
    """Render supported Markdown into safe, styled HTML."""
    rendered = []
    paragraph = []
    list_type = None
    quote_lines = []

    def flush_paragraph():
        if paragraph:
            content = " ".join(paragraph)
            rendered.append(f"<p>{format_inline(content)}</p>")
            paragraph.clear()

    def flush_list():
        nonlocal list_type
        if list_type:
            rendered.append(f"</{list_type}>")
            list_type = None

    def flush_quote():
        if quote_lines:
            quote_text = " ".join(quote_lines)
            rendered.append(
                '<blockquote><p>' + format_inline(quote_text) +
                '</p></blockquote>'
            )
            quote_lines.clear()

    for original_line in markdown_text.splitlines():
        line = original_line.strip()

        if not line:
            flush_paragraph()
            flush_list()
            flush_quote()
            continue

        # Headings. IDs are added later from the visible heading text.
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            rendered.append(
                f'<h{level} data-toc-title="{escape_attr(title)}">'
                f'{format_inline(title)}</h{level}>'
            )
            continue

        # Blockquotes
        if line.startswith(">"):
            flush_paragraph()
            flush_list()
            quote_lines.append(line[1:].strip())
            continue
        else:
            flush_quote()

        # Horizontal rules
        if re.fullmatch(r"([-*_]\s*){3,}", line):
            flush_paragraph()
            flush_list()
            rendered.append("<hr>")
            continue

        # Unordered and ordered lists
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        ordered = re.match(r"^\d+\.\s+(.+)$", line)

        if bullet or ordered:
            flush_paragraph()
            desired = "ul" if bullet else "ol"
            if list_type != desired:
                flush_list()
                rendered.append(f"<{desired}>")
                list_type = desired
            item = (bullet or ordered).group(1)
            rendered.append(f"<li>{format_inline(item)}</li>")
            continue

        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    flush_quote()
    return "\n".join(rendered)


def build_toc_and_ids(content_html):
    """Add stable IDs to headings and return a table of contents."""
    toc_items = []

    def replace_heading(match):
        level = int(match.group(1))
        inner = match.group(2)
        plain_title = re.sub(r"<[^>]+>", "", inner)
        plain_title = html.unescape(plain_title)
        heading_id = slugify(plain_title)
        toc_items.append((level, plain_title, heading_id))
        return f'<h{level} id="{heading_id}">{inner}</h{level}>'

    content_html = re.sub(
        r'<h([1-3]) data-toc-title="[^"]*">(.*?)</h\1>',
        replace_heading,
        content_html
    )

    if not toc_items:
        return content_html, ""

    links = []
    for level, title, heading_id in toc_items:
        css_class = ' class="toc-sub"' if level >= 3 else ""
        links.append(
            f'<li{css_class}><a href="#{heading_id}">'
            f'{html.escape(title)}</a></li>'
        )

    toc_html = (
        '<nav class="toc" aria-label="Table of contents">'
        '<details open><summary>In this article</summary>'
        '<ol>' + "".join(links) + '</ol></details></nav>'
    )
    return content_html, toc_html


# --------------------------------------------------
# Article page generation
# --------------------------------------------------

def make_page(article, body):
    """Create a polished, responsive HTML page for a published article."""
    title_raw = str(article.get("title", "Untitled"))
    description_raw = str(article.get("description", ""))
    category_raw = str(article.get("category", "General"))
    subcategory_raw = str(article.get("subcategory", ""))
    author_raw = str(article.get("author", "CurioSphere Editorial Team"))
    published_raw = str(article.get("date", date.today().isoformat()))
    image = safe_url(article.get("image", ""))
    image_caption = str(article.get("image_caption", ""))
    image_credit = str(article.get("image_credit", ""))
    source_url = safe_url(article.get("source_url", ""))
    reading_time = estimate_reading_time(body)

    title = html.escape(title_raw)
    description = html.escape(description_raw)
    category = html.escape(category_raw)
    subcategory = html.escape(subcategory_raw)
    author = html.escape(author_raw)
    published = html.escape(published_raw)

    image_html = ""
    if image:
        caption_parts = []
        if image_caption:
            caption_parts.append(html.escape(image_caption))
        if image_credit:
            caption_parts.append(
                'Image credit: ' + html.escape(image_credit)
            )
        caption_html = (
            '<figcaption>' + " · ".join(caption_parts) + '</figcaption>'
            if caption_parts else ""
        )
        image_html = (
            '<figure class="hero-figure">'
            '<img class="hero-image" src="' + escape_attr(image) +
            '" alt="' + escape_attr(title_raw) + '" fetchpriority="high">'
            + caption_html + '</figure>'
        )

    content_html = markdown_to_html(body)

# Remove the first heading if it duplicates the article title.
content_html = re.sub(
    r'^\s*<h1(?:\s+id="[^"]*")?>(.*?)</h1>\s*',
    lambda m: "" if html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip().casefold()
    == str(article.get("title", "")).strip().casefold() else m.group(0),
    content_html,
    count=1,
)

content_html, toc_html = build_toc_and_ids(content_html)

tags = article.get("tags", [])
    if isinstance(tags, str):
        tags = [tags] if tags else []
    if not isinstance(tags, list):
        tags = []

    tags_html = ""
    if tags:
        tags_html = (
            '<div class="tag-list" aria-label="Article tags">' +
            "".join(
                '<span class="tag">' + html.escape(str(tag)) + '</span>'
                for tag in tags
            ) + '</div>'
        )

    source_html = ""
    if source_url:
        source_html = (
            '<a class="source-button" href="' + escape_attr(source_url) +
            '" target="_blank" rel="noopener noreferrer">'
            'Read the primary source ↗</a>'
        )

    # Escape metadata values before embedding them into the document.
    canonical_slug = slugify(title_raw)
    share_title = escape_attr(title_raw)
    share_description = escape_attr(description_raw)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{description}">
  <meta name="author" content="{author}">
  <meta name="theme-color" content="#10142b">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{escape_attr(image)}">
  <title>{title} | {SITE_NAME}</title>
  <style>
    :root {{
      --ink: #19213b;
      --muted: #68718a;
      --navy: #10142b;
      --purple: #7565e8;
      --teal: #36c6b3;
      --paper: #ffffff;
      --canvas: #f5f6fb;
      --line: #e6e8f1;
      --soft-purple: #f0eeff;
      --soft-teal: #e9fbf7;
      --shadow: 0 20px 60px rgba(22, 28, 60, .09);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; scroll-padding-top: 24px; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--canvas);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
                   BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.75;
      -webkit-font-smoothing: antialiased;
    }}
    a {{ color: #5748c9; text-underline-offset: 3px; }}
    a:hover {{ color: #34279e; }}
    .site-header {{
      background: rgba(16, 20, 43, .98);
      color: #fff;
      border-bottom: 1px solid rgba(255,255,255,.1);
    }}
    .header-inner {{
      max-width: 1180px;
      margin: auto;
      padding: 17px 26px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }}
    .brand {{
      color: #fff;
      text-decoration: none;
      font-size: 1.22rem;
      font-weight: 850;
      letter-spacing: -.04em;
    }}
    .brand span {{ color: var(--teal); }}
    .header-tagline {{ color: #c5c9dd; font-size: .82rem; }}
    .back-link {{
      color: #fff;
      text-decoration: none;
      font-size: .9rem;
      font-weight: 650;
      border: 1px solid rgba(255,255,255,.24);
      border-radius: 999px;
      padding: 8px 14px;
      white-space: nowrap;
    }}
    .back-link:hover {{ color: #fff; background: rgba(255,255,255,.1); }}
    .page-wrap {{ max-width: 1180px; margin: 0 auto; padding: 30px 24px 64px; }}
    .breadcrumbs {{
      color: var(--muted);
      font-size: .85rem;
      margin: 0 0 22px;
    }}
    .breadcrumbs a {{ color: var(--muted); text-decoration: none; }}
    .breadcrumbs a:hover {{ color: var(--purple); }}
    .article-card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    .article-top {{ max-width: 900px; margin: auto; padding: 48px 58px 30px; }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: #5546c2;
      background: var(--soft-purple);
      border: 1px solid #e4e0ff;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: .75rem;
      font-weight: 800;
      letter-spacing: .09em;
      text-transform: uppercase;
    }}
    .eyebrow::before {{
      content: "";
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--teal);
    }}
    h1 {{
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(2.25rem, 5.2vw, 4.15rem);
      letter-spacing: -.045em;
      line-height: 1.09;
      margin: 22px 0 20px;
      color: var(--navy);
      text-wrap: balance;
    }}
    .dek {{
      color: #59627a;
      font-size: clamp(1.06rem, 2vw, 1.24rem);
      line-height: 1.65;
      margin: 0 0 25px;
    }}
    .byline {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 9px 14px;
      color: var(--muted);
      font-size: .88rem;
      border-top: 1px solid var(--line);
      padding-top: 19px;
    }}
    .byline strong {{ color: var(--ink); }}
    .dot {{ color: #b0b5c5; }}
    .hero-figure {{ margin: 0; background: #eceefa; }}
    .hero-image {{
      display: block;
      width: 100%;
      max-height: 590px;
      object-fit: cover;
    }}
    .hero-figure figcaption {{
      max-width: 900px;
      margin: auto;
      padding: 10px 24px 14px;
      color: var(--muted);
      font-size: .8rem;
    }}
    .article-layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 245px;
      gap: 46px;
      max-width: 1000px;
      margin: auto;
      padding: 42px 34px 56px;
    }}
    .article-body {{ min-width: 0; font-size: 1.075rem; line-height: 1.9; }}
    .article-body > p:first-child {{
      font-size: 1.18rem;
      color: #39425c;
    }}
    .article-body h2 {{
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(1.7rem, 3vw, 2.25rem);
      line-height: 1.2;
      letter-spacing: -.025em;
      margin: 2.15em 0 .65em;
      color: var(--navy);
      scroll-margin-top: 24px;
    }}
    .article-body h3 {{
      font-size: 1.28rem;
      line-height: 1.35;
      margin: 1.8em 0 .5em;
      color: var(--navy);
      scroll-margin-top: 24px;
    }}
    .article-body p {{ margin: 0 0 1.25em; }}
    .article-body ul, .article-body ol {{ padding-left: 1.45em; margin: 0 0 1.4em; }}
    .article-body li {{ padding-left: .25em; margin: .35em 0; }}
    .article-body strong {{ color: #22294a; }}
    .article-body blockquote {{
      margin: 1.8em 0;
      padding: 22px 25px;
      background: var(--soft-teal);
      border-left: 4px solid var(--teal);
      border-radius: 0 14px 14px 0;
      color: #254b50;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 1.2rem;
      line-height: 1.65;
    }}
    .article-body blockquote p {{ margin: 0; }}
    .article-body hr {{ border: 0; border-top: 1px solid var(--line); margin: 2.5em 0; }}
    .article-body code {{
      background: #f0f1f8;
      padding: .15em .4em;
      border-radius: 5px;
      font-size: .88em;
    }}
    .article-body .inline-figure {{
      margin: 1.5em 0;
    }}
    .inline-figure img {{
      display: block; max-width: 100%; height: auto; border-radius: 14px;
    }}
    .inline-figure figcaption {{ color: var(--muted); font-size: .82rem; }}
    .toc {{
      align-self: start;
      position: sticky;
      top: 20px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #fbfbff;
      padding: 18px 18px 12px;
      font-size: .86rem;
    }}
    .toc summary {{
      cursor: pointer;
      color: var(--navy);
      font-weight: 800;
      margin-bottom: 10px;
    }}
    .toc ol {{ padding-left: 1.2em; margin: 8px 0; }}
    .toc li {{ margin: 7px 0; line-height: 1.45; }}
    .toc a {{ color: #626b83; text-decoration: none; }}
    .toc a:hover {{ color: var(--purple); }}
    .toc .toc-sub {{ margin-left: 8px; font-size: .82rem; }}
    .insight {{
      margin: 2.2em 0;
      padding: 23px 25px;
      border-radius: 16px;
      background: linear-gradient(135deg, #f0eeff, #eefbf8);
      border: 1px solid #e3e3f7;
    }}
    .insight-label {{
      color: #5546c2;
      font-size: .74rem;
      font-weight: 850;
      letter-spacing: .12em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }}
    .insight p {{ margin: 0; }}
    .article-end {{
      border-top: 1px solid var(--line);
      margin-top: 38px;
      padding-top: 24px;
    }}
    .source-button {{
      display: inline-flex;
      align-items: center;
      background: var(--navy);
      color: #fff;
      padding: 10px 15px;
      border-radius: 10px;
      text-decoration: none;
      font-size: .9rem;
      font-weight: 700;
      margin: 4px 0 15px;
    }}
    .source-button:hover {{ background: #292e55; color: #fff; }}
    .tag-list {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
    .tag {{
      display: inline-block;
      border: 1px solid var(--line);
      background: #fafaff;
      color: #626b83;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: .78rem;
    }}
    .article-bottom {{
      border-top: 1px solid var(--line);
      background: #fafaff;
      padding: 24px 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }}
    .article-bottom strong {{ color: var(--navy); }}
    .article-bottom p {{ margin: 3px 0 0; color: var(--muted); font-size: .9rem; }}
    .bottom-link {{
      display: inline-block; text-decoration: none; white-space: nowrap;
      border-radius: 999px; padding: 10px 15px; background: var(--soft-purple);
      color: #5142bd; font-size: .88rem; font-weight: 750;
    }}
    .site-footer {{
      text-align: center;
      color: var(--muted);
      font-size: .85rem;
      padding: 25px 20px 10px;
    }}
    .site-footer strong {{ color: var(--navy); }}
    @media (max-width: 850px) {{
      .article-layout {{ grid-template-columns: 1fr; gap: 24px; padding: 30px 28px 42px; }}
      .toc {{ position: static; grid-row: 1; }}
      .article-top {{ padding: 38px 32px 25px; }}
      .article-bottom {{ padding: 22px 32px; }}
    }}
    @media (max-width: 560px) {{
      .header-inner {{ padding: 14px 17px; }}
      .header-tagline {{ display: none; }}
      .page-wrap {{ padding: 18px 12px 38px; }}
      .article-card {{ border-radius: 17px; }}
      .article-top {{ padding: 28px 22px 22px; }}
      h1 {{ font-size: clamp(2.05rem, 10vw, 3rem); }}
      .dek {{ font-size: 1rem; }}
      .article-layout {{ padding: 23px 21px 32px; }}
      .article-body {{ font-size: 1rem; line-height: 1.8; }}
      .article-bottom {{ align-items: flex-start; flex-direction: column; padding: 22px; }}
      .byline {{ gap: 6px 9px; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      .site-header, .breadcrumbs, .toc, .article-bottom, .site-footer {{ display: none; }}
      .page-wrap {{ padding: 0; }}
      .article-card {{ box-shadow: none; border: 0; }}
      .article-layout {{ display: block; padding: 20px 0; }}
    }}
  </style>
</head>
<body>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="{HOME_URL}">Curio<span>Sphere</span></a>
      <span class="header-tagline">{SITE_TAGLINE}</span>
      <a class="back-link" href="{HOME_URL}">← Explore stories</a>
    </div>
  </header>

  <div class="page-wrap">
    <nav class="breadcrumbs" aria-label="Breadcrumb">
      <a href="{HOME_URL}">Home</a> &nbsp;›&nbsp;
      <span>{category}</span>
      {(" &nbsp;›&nbsp; <span>" + subcategory + "</span>") if subcategory else ""}
    </nav>

    <main class="article-card">
      <section class="article-top">
        <div class="eyebrow">{category}</div>
        <h1>{title}</h1>
        <p class="dek">{description}</p>
        <div class="byline">
          <span>By <strong>{author}</strong></span>
          <span class="dot">•</span>
          <time datetime="{published}">{published}</time>
          <span class="dot">•</span>
          <span>{reading_time}</span>
        </div>
      </section>

      {image_html}

      <div class="article-layout">
        <article class="article-body">
          {content_html}
          <section class="insight" aria-label="CurioSphere Insight">
            <div class="insight-label">CurioSphere Insight</div>
            <p>Curiosity is the beginning of discovery. Keep asking questions, examine the evidence, and explore the ideas that shape our world.</p>
          </section>
          <div class="article-end">
            <h3>References &amp; further reading</h3>
            <p>Explore the original sources and reliable references linked within this article to learn more.</p>
            {source_html}
            {tags_html}
          </div>
        </article>
        {toc_html}
      </div>

      <div class="article-bottom">
        <div>
          <strong>Enjoyed exploring this story?</strong>
          <p>Discover more ideas and perspectives with CurioSphere.</p>
        </div>
        <a class="bottom-link" href="{HOME_URL}">Back to CurioSphere →</a>
      </div>
    </main>

    <footer class="site-footer">
      <strong>{SITE_NAME}</strong> · {SITE_TAGLINE}<br>
      Thoughtful stories for curious minds.
    </footer>
  </div>
</body>
</html>
"""


# --------------------------------------------------
# Main publishing process
# --------------------------------------------------

def main():
    if not ARTICLES_DIR.exists():
        raise SystemExit("ERROR: content/articles directory was not found.")

    # Remember pages from the previous index so obsolete generated pages
    # can be removed safely after the next successful generation.
    previous_slugs = set()
    if INDEX_FILE.exists():
        try:
            previous_index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            for item in previous_index:
                url = str(item.get("url", ""))
                match = re.fullmatch(r"articles/([a-z0-9-]+)\.html", url)
                if match:
                    previous_slugs.add(match.group(1))
        except (json.JSONDecodeError, OSError):
            print("WARNING: Could not read the previous index. No old pages will be deleted.")

    published_articles = []
    used_slugs = set()

    for source_file in sorted(ARTICLES_DIR.glob("*.md")):
        raw_text = source_file.read_text(encoding="utf-8")
        article, body = parse_frontmatter(raw_text)

        title = str(article.get("title", "")).strip()
        if not title:
            print(f"WARNING: Skipping {source_file.name}: missing title.")
            continue

        status = str(article.get("status", "Draft")).strip().lower()
        if status != "published":
            print(f"Not publishing draft: {source_file.name}")
            continue

        # Use the source filename to preserve stable article URLs.
        slug = slugify(source_file.stem)
        if slug in used_slugs:
            raise SystemExit(f"ERROR: Duplicate article slug: {slug}")
        used_slugs.add(slug)

        output_file = OUTPUT_DIR / f"{slug}.html"
        output_file.write_text(make_page(article, body), encoding="utf-8")

        article_date = str(article.get("date", date.today().isoformat()))
        tags = article.get("tags", [])
        if isinstance(tags, str):
            tags = [tags] if tags else []
        if not isinstance(tags, list):
            tags = []

        record = {
            "title": title,
            "description": str(article.get("description", "")),
            "category": str(article.get("category", "General")),
            "subcategory": str(article.get("subcategory", "")),
            "author": str(article.get("author", "CurioSphere Editorial Team")),
            "date": article_date,
            "featured": as_bool(article.get("featured", False)),
            "image": safe_url(article.get("image", "")),
            "tags": tags,
            "url": f"articles/{slug}.html"
        }
        published_articles.append(record)
        print(f"Generated: articles/{slug}.html")

    current_slugs = {
        item["url"].removeprefix("articles/").removesuffix(".html")
        for item in published_articles
    }

    for old_slug in previous_slugs - current_slugs:
        old_file = OUTPUT_DIR / f"{old_slug}.html"
        if old_file.is_file():
            old_file.unlink()
            print(f"Removed unpublished page: {old_file.name}")

    published_articles.sort(
        key=lambda item: (item["featured"], item["date"]),
        reverse=True
    )

    INDEX_FILE.write_text(
        json.dumps(published_articles, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print()
    print("Publishing preparation completed successfully.")
    print(f"Published articles: {len(published_articles)}")
    print(f"Article index: {INDEX_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
