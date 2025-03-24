import json
import logging
import asyncio
import httpx
from typing import Optional, List
from bs4 import BeautifulSoup
from util.publication_utils.cpv_codes import nl_sectors
import html2text
from urllib.parse import urljoin, urlparse
from openai import OpenAI

from app.ai.openai import get_openai_client


async def extract_text_from_html(html_content: str) -> str:
    """Extract clean text from HTML using html2text."""
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.ignore_tables = False
    converter.ignore_emphasis = True
    converter.body_width = 0  # No wrapping
    
    return converter.handle(html_content)


async def get_important_links(base_url: str, html_content: str) -> List[str]:
    """Extract important links from the website that might contain company information."""
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    base_path = parsed_base.path.rstrip('/')
    
    soup = BeautifulSoup(html_content, 'html.parser')
    important_pages = []
    
    # Keywords that likely indicate pages with company information - multilingual (EN, NL, FR)
    important_keywords = [
        # English
        'about', 'team', 'contact', 'company', 'mission', 'vision', 'who-we-are',
        'clients', 'services', 'projects', 'about-us', 'careers', 'staff', 'our-team',
        'leadership', 'management', 'values', 'history', 'expertise',
        
        # Dutch
        'over', 'bedrijf', 'missie', 'visie', 'wie-zijn-wij', 'klanten', 'diensten', 
        'projecten', 'over-ons', 'werknemers', 'personeel', 'ons-team', 'leiding', 
        'bestuur', 'waarden', 'geschiedenis', 'expertise', 'vacatures', 'loopbaan',
        
        # French
        'propos', 'entreprise', 'mission', 'vision', 'qui-sommes-nous', 'clients', 
        'services', 'projets', 'a-propos', 'carrieres', 'equipe', 'personnel', 
        'direction', 'valeurs', 'histoire', 'expertise', 'emplois'
    ]
    
    # Find all links in the document
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()
        
        # Skip empty hrefs, fragment-only links, javascript links and mailto links
        if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue
        
        # Sanitize URL - remove fragments and query parameters
        href = href.split('#')[0].split('?')[0]
        
        # Construct absolute URL
        if not href.startswith(('http://', 'https://')):
            href = urljoin(base_url, href)
            
        # Skip external links
        parsed_href = urlparse(href)
        if parsed_href.netloc != base_domain:
            continue
            
        # Skip PDF links and other non-HTML content
        if href.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar')):
            continue
        
        # Skip sub-sub links (only scrape top-level important pages)
        href_path = parsed_href.path.rstrip('/')
        
        # Normalize path by removing the .html, .php, etc.
        if '.' in href_path.split('/')[-1]:
            href_path = href_path.rsplit('.', 1)[0]
            
        path_segments = [s for s in href_path.split('/') if s]
        
        # Skip if it's a deep link (more than one level from the base path)
        base_segments = [s for s in base_path.split('/') if s]
        if len(path_segments) > len(base_segments) + 1:
            continue
            
        # Check if link contains important keywords
        href_lower = href.lower()
        if any(keyword in href_lower for keyword in important_keywords):
            important_pages.append(href)
            
    # Also check page titles and text content for language detection
    page_language_signals = {
        'en': ['about', 'contact', 'services', 'team', 'who we are'],
        'nl': ['over', 'contact', 'diensten', 'team', 'wie wij zijn'],
        'fr': ['à propos', 'contact', 'services', 'équipe', 'qui nous sommes']
    }
    
    # Detect potential language from page content
    page_text = soup.get_text().lower()
    language_scores = {}
    for lang, signals in page_language_signals.items():
        score = sum(1 for signal in signals if signal in page_text)
        language_scores[lang] = score
    
    detected_languages = [lang for lang, score in language_scores.items() if score > 0]
    logging.info(f"Detected potential languages: {detected_languages}")
    
    # Limit to 5 additional pages to avoid too many requests
    return list(set(important_pages))[:5]


async def scrape_single_page(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Scrape a single page and extract its text content."""
    try:
        # Sanitize URL first
        url = await sanitize_url(url)
        
        response = await client.get(url, timeout=10.0)
        if response.status_code != 200:
            logging.warning(f"Failed to fetch page {url}: {response.status_code}")
            return None
            
        # Try to detect encoding
        if not response.encoding:
            response.encoding = response.apparent_encoding or 'utf-8'
            
        html_content = response.text
        text_content = await extract_text_from_html(html_content)
        
        # Return a formatted string with the URL and content
        return f"Content from {url}:\n\n{text_content}\n\n"
        
    except Exception as e:
        logging.warning(f"Error scraping page {url}: {e}")
        return None


async def sanitize_url(url: str) -> str:
    """Sanitize a URL by ensuring proper scheme and format."""
    # Strip whitespace
    url = url.strip()
    
    # Add scheme if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Parse and reconstruct to normalize
    parsed = urlparse(url)
    
    # Remove trailing slashes from netloc
    netloc = parsed.netloc.rstrip('/')
    
    # Remove fragments and queries
    path = parsed.path.split('#')[0].split('?')[0]
    
    # Reconstruct
    return f"{parsed.scheme}://{netloc}{path}"


async def scrape_company_website(
    website_url: str, client: OpenAI = None
) -> Optional[str]:
    """
    Scrape a company website using OpenAI to extract relevant company information.
    Returns a JSON string with the extracted information.
    """
    if client is None:
        client = get_openai_client()

    try:
        # Sanitize the URL
        website_url = await sanitize_url(website_url)
        logging.info(f"Scraping website: {website_url}")

        # Create an HTTP client for scraping with retry mechanism
        transport = httpx.AsyncHTTPTransport(retries=2)
        async with httpx.AsyncClient(timeout=15.0, transport=transport, follow_redirects=True) as http_client:
            # Existing code for fetching the website...
            try:
                # Fetch the main page
                response = await http_client.get(website_url)
                if response.status_code != 200:
                    logging.error(f"Failed to fetch website: {response.status_code}")
                    return None
            except httpx.RequestError as e:
                # Try with http:// if https:// fails
                if website_url.startswith('https://'):
                    logging.warning(f"HTTPS request failed, trying HTTP: {e}")
                    website_url = website_url.replace('https://', 'http://')
                    try:
                        response = await http_client.get(website_url)
                        if response.status_code != 200:
                            logging.error(f"Failed to fetch website with HTTP: {response.status_code}")
                            return None
                    except httpx.RequestError as e2:
                        logging.error(f"HTTP request also failed: {e2}")
                        return None
                else:
                    logging.error(f"Request failed: {e}")
                    return None

            # Try to detect the encoding if not specified
            if not response.encoding:
                response.encoding = response.apparent_encoding or 'utf-8'

            # Extract text from the main page
            main_page_html = response.text
            main_page_text = await extract_text_from_html(main_page_html)
            
            # Get additional important pages
            additional_pages = await get_important_links(website_url, main_page_html)
            logging.info(f"Found {len(additional_pages)} additional pages to scrape")
            
            # Scrape additional pages concurrently
            additional_content = ""
            if additional_pages:
                tasks = [scrape_single_page(http_client, page) for page in additional_pages]
                results = await asyncio.gather(*tasks)
                
                for result in results:
                    if result:
                        additional_content += result
                        
            logging.info(f"Successfully scraped main page and {len([r for r in results if r])}/{len(additional_pages)} additional pages")
            
            # Combine the content from all pages
            combined_content = f"Main page content from {website_url}:\n\n{main_page_text}\n\n{additional_content}"
            
            # Limit the combined content to a reasonable size (approximately 16k tokens)
            max_chars = 64000  # Rough estimate: ~4 chars per token
            if len(combined_content) > max_chars:
                combined_content = combined_content[:max_chars] + "...[content truncated]"

            # Create a list of available sectors to provide to OpenAI
            available_sectors = [{"cpv": code, "name": name} for code, name in nl_sectors.items()]

            # Use OpenAI to analyze the website content with multilingual support
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a specialized company information extractor for Belgian companies. 
                        Analyze the provided text content extracted from a company website to extract the following information.
                        The text may be in Dutch, French, or English - analyze the content in whichever language it's presented.
                        
                        Extract the following information:
                        - Company name
                        - Summary of activities (Generate a concise and comprehensive summary of the company's activities based on the scraped website data. Ensure the summary accurately reflects all aspects of what the company does, without adding unrelated information. This summary will be used to generate relevant public tender recommendations, so it must be precise and directly aligned with the company's actual services and expertise.)
                        - Main sectors/industries they operate in
                        - Approximate number of employees (if mentioned)
                        - Operating regions/locations in Belgium (use provinces instead of city names)
                        - Keywords related to their activities
                        
                        For sectors, you MUST choose ONLY from this standardized list of valid CPV sectors:
                        {json.dumps(available_sectors, indent=2)}
                        
                        Return the information in JSON format with the following structure:
                        {{
                            "company_name": string,
                            "vat_number": string,
                            "summary_activities": string,
                            "sectors": [
                                {{
                                    "sector": string,
                                    "cpv_codes": [string],
                                    "confidence": float
                                }}
                            ],
                            "employee_count": int or null,
                            "operating_regions": [string],
                            "activity_keywords": [string]
                        }}
                        
                        When selecting sectors, each entry in the sectors array must have:
                        - "sector" exactly matching a name from the provided standardized list
                        - "cpv_codes" containing an array with the corresponding CPV code (e.g., ["03000000"])
                        - "confidence" with a value from 0.0 to 1.0
                        
                        If you cannot determine a field, use null for that field.
                        Your response should be in Dutch.
                        """,
                    },
                    {
                        "role": "user",
                        "content": f"Here is the text content extracted from {website_url} and related pages:\n\n{combined_content}\n\nExtract the company information.",
                    },
                ],
                temperature=0.3,
            )

            # Return the raw JSON string
            return completion.choices[0].message.content

    except Exception as e:
        logging.error(f"Error scraping website: {e}")
        return None
