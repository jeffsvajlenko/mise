"""Webpage content extraction for recipe parsing."""

import re
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from typing import TypeAlias


ScrapedContent: TypeAlias = dict[str, str]


def scrape_webpage(url: str, timeout: int = 10) -> ScrapedContent:
    """
    Scrape a webpage and extract content as markdown.

    Strategy:
    1. Fetch the webpage
    2. Remove definitively non-recipe elements (nav, footer, ads, scripts)
    3. Try to find main content container (article, main, or body)
    4. Convert HTML to markdown to preserve structure (headings, lists, etc.)
    5. Clean up excessive whitespace

    This approach is intentionally permissive - we keep most content and let
    Claude filter out irrelevant parts during extraction.

    Args:
        url: URL to scrape
        timeout: Request timeout in seconds (default: 10)

    Returns:
        dict with keys:
            - url: The scraped URL
            - title: Page title
            - content: Extracted content as markdown
            - html_title: HTML title tag content

    Raises:
        requests.RequestException: If request fails
        ValueError: If content cannot be extracted

    Example:
        >>> data = scrape_webpage("https://example.com/recipe")
        >>> print(data['title'])
        >>> print(data['content'][:200])
    """
    # Fetch the webpage
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()

    # Parse HTML
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract title
    html_title: str = soup.title.string if soup.title and soup.title.string else ""

    # Remove elements that are definitely not recipe content
    # Be conservative - only remove obvious noise
    for element in soup.find_all(['script', 'style', 'noscript', 'iframe']):
        element.decompose()

    # Remove nav, header, footer - but only top-level ones
    for tag in ['nav', 'header', 'footer']:
        for element in soup.find_all(tag, recursive=False):
            element.decompose()

    # Remove common ad/tracking/social elements by class/id patterns
    noise_patterns = [
        'advertisement', 'ad-container', 'ad-wrapper', 'ads-',
        'social-share', 'share-buttons', 'social-buttons',
        'newsletter', 'subscribe', 'popup', 'modal', 'overlay',
        'sidebar', 'widget', 'comment', 'related-posts',
        'navigation', 'breadcrumb', 'menu'
    ]

    for pattern in noise_patterns:
        # Remove by class - find all elements with classes containing the pattern
        for element in soup.find_all(class_=True):
            if not hasattr(element, 'attrs') or element.attrs is None:
                continue
            classes = element.get('class')
            if classes and isinstance(classes, list):
                class_str = ' '.join(classes).lower()
                if pattern in class_str:
                    element.decompose()

        # Remove by id - find all elements with id containing the pattern
        for element in soup.find_all(id=True):
            if not hasattr(element, 'attrs') or element.attrs is None:
                continue
            elem_id = element.get('id')
            if elem_id and isinstance(elem_id, str) and pattern in elem_id.lower():
                element.decompose()

    # Try to find main content container
    content_container = None

    # 1. Try to find article or main tag
    for tag in ['article', 'main']:
        content_container = soup.find(tag)
        if content_container:
            break

    # 2. Fallback to body
    if not content_container:
        content_container = soup.find('body')

    if not content_container:
        raise ValueError("Could not extract content from webpage")

    # Convert HTML to markdown
    # This preserves headings, lists, bold/italic, links, etc.
    markdown_content = md(
        str(content_container),
        heading_style="ATX",  # Use # for headings
        bullets="-",  # Use - for lists
        strip=['a'],  # Remove link URLs but keep text
    )

    # Clean up the markdown
    # Remove excessive blank lines
    markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)

    # Remove lines that are just whitespace or special chars
    lines = markdown_content.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Keep the line if it has actual content (not just punctuation/whitespace)
        if stripped and not re.match(r'^[^\w\s]+$', stripped):
            cleaned_lines.append(line)

    markdown_content = '\n'.join(cleaned_lines)

    # Final cleanup
    markdown_content = markdown_content.strip()

    return {
        'url': url,
        'title': html_title,
        'content': markdown_content,
        'html_title': html_title,
    }


def extract_recipe_metadata(soup: BeautifulSoup) -> dict:
    """
    Try to extract structured recipe metadata from schema.org markup.

    Many recipe sites use JSON-LD or microdata with schema.org Recipe schema.
    This can provide structured data that's easier to parse.

    Args:
        soup: BeautifulSoup object

    Returns:
        dict: Extracted metadata (may be empty)
    """
    metadata = {}

    # Try JSON-LD first (most common for recipes)
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    for script in json_ld_scripts:
        try:
            import json
            if not script.string:
                continue
            data = json.loads(script.string)

            # Handle both single objects and arrays
            if isinstance(data, list):
                data = next((item for item in data if item.get('@type') == 'Recipe'), None)

            if data and data.get('@type') == 'Recipe':
                metadata = data
                break
        except (json.JSONDecodeError, AttributeError):
            continue

    return metadata
