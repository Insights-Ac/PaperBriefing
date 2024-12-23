import argparse
import os
import re
import time
import yaml
import hashlib
from tqdm import tqdm

from pdf_parser import parse_pdf, clean_text, download_pdf
from pdf_scraper import scrape_openreview, scrape_ai_conference, scrape_cvpr
from sql import Database, Paper
from summarizer import summarize_text


def get_db_url():
    """Get database URL from environment variables or config file."""
    # Priority: Environment variables > Config file
    db_type = os.getenv('DB_TYPE', 'sqlite')
    
    if db_type.lower() == 'postgresql':
        # PostgreSQL connection parameters
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '5432')
        database = os.getenv('DB_NAME', 'papers')
        user = os.getenv('DB_USER', 'postgres')
        password = os.getenv('DB_PASSWORD', '')
        
        return f'postgresql://{user}:{password}@{host}:{port}/{database}'
    else:
        # Default SQLite connection
        return os.getenv('DB_URL', 'sqlite:///data/papers.db')


def scrape_papers(config):
    """Scrape papers and store their content in the database without summarization."""
    name = config.get('name', 'Unnamed config')
    print(f"\nScraping papers for configuration: {name}", flush=True)
    
    # Extract parameters from config
    output_dir = config['paths']['output_dir']
    db_path = config['paths'].get('db_path', get_db_url())
    platform = config['scraping']['platform']
    
    # Initialize database
    db = Database(db_path)
    db.create_tables()
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Scrape PDF URLs based on platform
    if platform.lower() == 'openreview':
        papers = scrape_openreview(**config['scraping']['scraper_params'])
    elif platform.lower() == 'ai_conference':
        papers = scrape_ai_conference(**config['scraping']['scraper_params'])
    elif platform.lower() == 'cvpr':
        papers = scrape_cvpr(**config['scraping']['scraper_params'])
    else:
        raise ValueError(f"Unsupported platform: {platform}")
    
    # Process each paper
    for paper_id, title, url in tqdm(papers, desc="Scraping papers"):
        # Create a unique ID using SHA-256 hash
        paper_id = hashlib.sha256(paper_id.encode()).hexdigest()
        title = clean_text(title)

        # Check if the paper already exists in the database
        existing_papers = db.get_papers(filters={'id': paper_id})
        if existing_papers:
            if config['scraping'].get('enforce_rescrape', False) or not existing_papers[0].content:
                db.delete_paper(paper_id)
            else:
                print(f"Skipping {title}, already scraped.")
                continue
        
        # Download PDF
        pdf_path = download_pdf(f'{paper_id}.pdf', url, output_dir)
        if not pdf_path:
            print(f"Failed to download {title}.")
            continue
        
        # Parse and clean PDF
        raw_content = parse_pdf(pdf_path, use_pypdf2=config['scraping'].get('use_pypdf2', True))
        content = clean_text(raw_content)

        # Create or update Paper entry
        paper_entry = Paper(
            id=paper_id,
            collection=name,
            title=title,
            platform=platform,
            pdf_url=url,
            pdf_path=pdf_path,
            content=content,
            summary=None  # Summary will be added later
        )
        
        # Add entry to the database
        try:
            db.add_entry(paper_entry)
        except Exception as e:
            print(f"Error adding entry to the database: {e}")
        
        # Delay to avoid overwhelming the server
        time.sleep(config['scraping']['delay'])


def summarize_papers(config):
    """Summarize papers that have content but no summary in the database."""
    name = config.get('name', 'Unnamed config')
    print(f"\nSummarizing papers for configuration: {name}", flush=True)
    
    # Initialize database
    db = Database(config['paths'].get('db_path', get_db_url()))
    
    # Get papers based on enforce_resummary setting
    if config['summarization'].get('enforce_resummary', False):
        # Get all papers with content, regardless of summary status
        papers = db.get_papers(filters={'collection': name})
    else:
        # Get only papers with content but no summary
        papers = db.get_papers(filters={'collection': name, 'summary': None})
    
    for paper in tqdm(papers, desc="Summarizing papers"):
        content = paper.content

        if config['summarization']['cap_at'] and config['summarization']['cap_at'] in content:
            content = content[:content.index(config['summarization']['cap_at'])]

        if config['summarization']['content_cap']:
            content = content[:config['summarization']['content_cap']]

        # Summarize the content
        summary = summarize_text(
            prefix=config['summarization']['prefix'],
            suffix=config['summarization']['suffix'],
            text=content,
            provider=config['summarization']['provider'],
            model_name=config['summarization']['model_name'],
            **config['summarization']['param']
        )
        
        # Update the paper with the summary
        db.update_paper(paper.id, {'summary': summary})
        
        # Delay between API calls if specified
        if 'delay' in config['summarization']:
            time.sleep(config['summarization']['delay'])


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Process academic papers from conferences.')
    parser.add_argument('-c', '--config', type=str, default='config.yaml', help='Path to the configuration file')
    args = parser.parse_args()

    # Load configuration
    with open(args.config, 'r') as config_file:
        configs = yaml.safe_load(config_file)

    # Handle both single config and list of configs
    if not isinstance(configs, list):
        configs = [configs]

    # Process each configuration
    for config in configs:
        if 'scraping' in config:
            scrape_papers(config)
        if 'summarization' in config:
            summarize_papers(config)

    print("\nAll configurations processed.")


if __name__ == "__main__":
    main()