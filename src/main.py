import argparse
import os
import re
import time
import yaml
import hashlib
from tqdm import tqdm

from pdf_parser import parse_and_clean_pdf, clean_text
from pdf_scraper import download_pdf, scrape_openreview, scrape_ai_conference, scrape_cvpr
from sql import Database, Paper
from summarizer import summarize_text


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
        print(f"\nProcessing configuration: {config.get('name', 'Unnamed config')}", flush=True)
        
        # Extract parameters from config
        platform = config['scraping']['platform']
        num_cap = config['scraping'].get('num_cap')
        max_retries = config['scraping'].get('max_retries', 3)
        output_dir = config['paths']['output_dir']
        db_path = config['paths']['db_path']
        
        # Initialize database
        db = Database(db_path)
        db.create_tables()
        
        # Scrape PDF URLs based on platform
        if platform.lower() == 'openreview':
            papers = scrape_openreview(**config['scraping']['filters'], num_cap=num_cap, max_retries=max_retries)
        elif platform.lower() == 'txt':
            papers = scrape_from_txt(**config['scraping']['filters'])
        elif platform.lower() == 'ai_conference':
            papers = scrape_ai_conference(**config['scraping']['filters'], max_papers=num_cap)
        elif platform.lower() == 'cvpr':
            papers = scrape_cvpr(**config['scraping']['filters'], max_papers=num_cap)
        else:
            raise ValueError(f"Unsupported platform: {platform}")
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Process each paper
        for paper_id, title, url in tqdm(papers, desc="Processing papers"):
            # Create a unique ID using MD5 hash
            paper_id = hashlib.md5(paper_id.encode()).hexdigest()
            title = clean_text(title)

            # Check if the paper already exists in the database
            existing_papers = db.get_papers(filters={'id': paper_id})
            if existing_papers and existing_papers[0].summary:
                if config['scraping'].get('enforce_rescrape', False):
                    # Delete existing entry
                    db.delete_paper(existing_papers[0].id)
                else:
                    print(f"Skipping {title}, already processed.")
                    continue
            
            # Download PDF
            pdf_path = download_pdf(f'{paper_id}.pdf', url, output_dir)
            if not pdf_path:
                print(f"Failed to download {title}.")
                continue
            
            # Parse and clean PDF
            content = parse_and_clean_pdf(pdf_path, cap_at=config['scraping']['cap_at'])
            if config['summarization']['content_cap']:
                content = content[:config['summarization']['content_cap']]

            # Summarize the content.
            provider = config['summarization']['provider']
            model_name = config['summarization']['model_name']
            summary = summarize_text(config['summarization']['prefix'], config['summarization']['suffix'], 
                                     content, provider, model_name, **config['summarization']['param'])
            
            # Create a new Paper entry
            paper_entry = Paper(
                id=paper_id,
                title=title,
                platform=platform,
                pdf_url=url,
                pdf_path=pdf_path,
                content=content,
                summary=summary
            )
            
            # Add entry to the database
            db.add_entry(paper_entry)
            
            # Delay to avoid overwhelming the server
            time.sleep(config['scraping']['delay'])

        print(f"Completed processing configuration: {config.get('name', 'Unnamed config')}")

    print("\nAll configurations processed.")


if __name__ == "__main__":
    main()