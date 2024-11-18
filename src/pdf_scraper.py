import os
import subprocess
import sys
import time

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from urllib.parse import urljoin


def download_pdf(filename, url, output_dir):
    """
    Download a PDF file and save it to the specified directory.
    
    :param title: str, title of the paper
    :param url: str, URL of the PDF
    :param output_dir: str, directory to save the PDF
    """
    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    def _download_with_retry():
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Failed to download PDF: HTTP {response.status_code}")
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return filepath

    try:
        return _download_with_retry()
    except Exception as e:
        print(f"Failed to download after retries: {str(e)}")
        return None


def check_firefox_installation():
    """
    Check Firefox ESR installation and print debug information.
    """
    try:
        # Check Firefox ESR version
        firefox_version = subprocess.check_output(['firefox-esr', '--version']).decode().strip()
        print(f"Firefox ESR version: {firefox_version}")
        
        # Check geckodriver
        driver_path = GeckoDriverManager().install()
        print(f"Geckodriver path: {driver_path}")
        
        return True
    except FileNotFoundError:
        print("Firefox ESR is not installed or not in PATH")
        return False
    except Exception as e:
        print(f"Error checking Firefox ESR installation: {e}")
        return False


def setup_firefox_driver():
    """
    Set up Firefox driver with appropriate options for Debian Linux using Firefox ESR.
    """
    if not check_firefox_installation():
        raise Exception("Firefox ESR is not properly installed. Please install Firefox ESR first.")

    options = FirefoxOptions()
    
    # Basic headless setup
    options.add_argument('--headless')
    options.add_argument('--width=1920')
    options.add_argument('--height=1080')
    
    # Additional Firefox preferences for stability
    options.set_preference('browser.download.folderList', 2)
    options.set_preference('browser.download.manager.showWhenStarting', False)
    options.set_preference('browser.helperApps.neverAsk.saveToDisk', 'application/pdf')
    options.set_preference('browser.tabs.remote.autostart', False)
    options.set_preference('browser.tabs.remote.autostart.2', False)
    
    # Reduce memory usage
    options.set_preference('browser.sessionhistory.max_entries', 10)
    
    # Set the binary location to Firefox ESR
    options.binary_location = '/usr/bin/firefox-esr'
    
    try:
        print("Setting up Firefox ESR driver...")
        service = FirefoxService(
            GeckoDriverManager().install(),
            log_output=os.path.devnull  # Suppress Geckodriver logs
        )
        
        driver = webdriver.Firefox(
            service=service,
            options=options
        )
        print("Firefox ESR driver successfully initialized", flush=True)
        return driver
    except Exception as e:
        print(f"Failed to initialize Firefox ESR driver: {str(e)}")
        print(f"System platform: {sys.platform}")
        print(f"Python version: {sys.version}")
        raise


def scrape_openreview(conference, year, track, submission_type=None, max_retries=3, num_cap=None):
    """
    Scrape OpenReview for PDFs based on given parameters using Selenium with Firefox.
    
    :param conference: str, conference name (e.g., 'ICLR', 'NeurIPS')
    :param year: int, year of the conference
    :param track: str, track name (e.g., 'Poster', 'Oral')
    :param submission_type: str, type of submission
    :param max_retries: int, maximum number of retries for failed operations
    :param num_cap: int, maximum number of papers to scrape
    :return: list of tuples (paper_title, pdf_url)
    """
    base_url = f"https://openreview.net/group?id={conference}/{year}/{track}"
    if submission_type is not None:
        base_url += f"#{submission_type}"
    
    driver = None
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"\nAttempt {retry_count + 1} of {max_retries}")
            print(f"Initializing Firefox driver...")
            driver = setup_firefox_driver()
            
            print(f"Navigating to URL: {base_url}")
            driver.get(base_url)
            
            papers = []
            page_number = 1
            
            while True:
                print(f"Processing page {page_number}", flush=True)
                # Wait for the content to load with increased timeout
                print("Waiting for content to load...")
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "note"))
                )
            
                # Scroll to load all papers on the current page
                print("Scrolling through page...")
                last_height = driver.execute_script("return document.body.scrollHeight")
                scroll_attempts = 0
                max_scroll_attempts = 10
            
                while scroll_attempts < max_scroll_attempts:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(3)  # Increased wait time
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                    scroll_attempts += 1
            
                # Extract paper information
                print("Extracting paper information...")
                notes = driver.find_elements(By.CLASS_NAME, "note")
            
                for paper in notes:
                    try:
                        title = paper.find_element(By.TAG_NAME, "h4").text.strip()
                        pdf_links = paper.find_elements(By.XPATH, ".//a[@title='Download PDF']")
                        if pdf_links and len(title.strip()) > 0:
                            pdf_url = pdf_links[0].get_attribute("href")
                            paper_id = f'{title}_{conference}_{year}_{track}_{submission_type}'
                            papers.append((paper_id, title, pdf_url))
                            print(f"Found paper: {title}")
                            
                            # Check if we've reached the num_cap
                            if num_cap is not None and len(papers) >= num_cap:
                                print(f"Reached paper cap of {num_cap}")
                                return papers
                                
                    except Exception as e:
                        print(f"Error extracting paper info: {str(e)}")
                        continue

                # Store current page papers for comparison
                current_page_titles = [note.find_element(By.TAG_NAME, "h4").text.strip() 
                                       for note in notes]
                
                # Check if there's a next page
                try:
                    next_button = driver.find_element(By.XPATH, "//li[contains(@class, 'right-arrow')]/a/span[text()='›']")
                    print("Moving to the next page...", flush=True)
                    # Scroll the button into view using JavaScript
                    driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                    # Wait a moment for the scroll to complete
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)  # Wait for the next page to load

                    # Check if we're still on the same page by comparing paper titles
                    new_notes = driver.find_elements(By.CLASS_NAME, "note")
                    new_page_titles = [note.find_element(By.TAG_NAME, "h4").text.strip() 
                                     for note in new_notes]
                    
                    if current_page_titles == new_page_titles:
                        print("Reached the last page (detected by content comparison)", flush=True)
                        break
                    
                    page_number += 1
                except Exception as e:
                    print(f"Navigation error: {e}", flush=True)
                    print("No more pages or error finding next button.", flush=True)
                    break
            
            return papers
            
        except Exception as e:
            print(f"Error during scraping (attempt {retry_count + 1}): {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                print("Retrying...")
                time.sleep(5)  # Wait before retrying
            else:
                print("Max retries reached. Giving up.")
                raise
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    print(f"Error closing driver: {str(e)}")


def scrape_from_txt(file_path):
    """
    Scrape PDFs from URLs listed in a text file.
    Each line in the text file should contain a PDF URL.
    
    :param file_path: str, path to the text file containing PDF URLs
    :return: list of tuples (paper_id, title, pdf_url)
    """
    papers = []
    
    try:
        with open(file_path, 'r') as file:
            for line_number, line in enumerate(file, 1):
                pdf_url = line.strip()
                if pdf_url:
                    # Generate a unique paper ID using line number since we might not have titles
                    paper_id = f'paper_{line_number}_{pdf_url}'
                    # Use the URL as a placeholder title since we can't extract it without downloading
                    title = f"Paper from {pdf_url}"
                    papers.append((paper_id, title, pdf_url))
                    print(f"Found paper URL: {pdf_url}")
                else:
                    print(f"Skipping invalid URL at line {line_number}: {pdf_url}")
        
        print(f"Successfully loaded {len(papers)} paper URLs from {file_path}")
        return papers
        
    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
        raise


def scrape_ai_conference(conference, year, filter_name=None, filter_value=None, max_papers=None):
    """
    Scrape papers from the three top AI conference websites (ICLR, ICML, NeurIPS).

    :param conference: Conference name ('ICLR', 'ICML', or 'NeurIPS')
    :param year: Conference year (e.g., 2024)
    :param filter_name: Filter category (e.g., 'title', 'topic', 'author', 'session')
    :param filter_value: Value to filter by
    :param max_papers: Maximum number of papers to scrape (optional)
    :return: list of tuples (paper_id, title, pdf_url)
    """
    driver = None
    papers = []
    paper_count = 0
    
    try:
        # Construct the base URL based on conference
        conference = conference.upper()
        if conference not in ['ICLR', 'ICML', 'NEURIPS']:
            raise ValueError(f"Unsupported conference: {conference}")
            
        base_url = f"https://{conference.lower()}.cc/virtual/{year}/papers.html"
        if filter_name and filter_value:
            encoded_filter_value = filter_value.replace(' ', '+')
            base_url += f"?filter={filter_name}&search={encoded_filter_value}"
        
        driver = setup_firefox_driver()
        print(f"Fetching papers from {conference}: {base_url}")
        driver.get(base_url)
        time.sleep(3)  # Wait for dynamic content
        
        # Get all paper links from the filtered page
        paper_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='poster/']")
        paper_links = [elem.get_attribute('href') for elem in paper_elements if elem.get_attribute('href')]
        
        for paper_url in paper_links:
            try:
                # Get paper title
                driver.get(paper_url)
                title_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h2.card-title.main-title.text-center"))
                )
                title = title_element.text.strip() if title_element else "Unknown Title"
                
                # Handle PDF link based on conference
                if conference == 'ICML':
                    try:
                        # First try the direct PDF link
                        pdf_element = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "a[title='PDF']"))
                        )
                        pdf_url = pdf_element.get_attribute('href')
                    except Exception:
                        # If direct PDF link not found, try the proceedings link
                        try:
                            proceedings_element = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Paper PDF')]"))
                            )
                            proceedings_url = proceedings_element.get_attribute('href')
                            
                            # Navigate to the proceedings page
                            driver.get(proceedings_url)
                            
                            # Look for the download PDF link
                            pdf_element = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Download PDF')]"))
                            )
                            pdf_url = pdf_element.get_attribute('href')
                        except Exception as e:
                            print(f"Could not find PDF link for paper: {str(e)}")
                            continue
                else:
                    # For ICLR and NeurIPS, get PDF through OpenReview
                    openreview_element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[title='OpenReview']"))
                    )
                    openreview_url = openreview_element.get_attribute('href')
                    if not openreview_url:
                        continue
                    
                    driver.get(openreview_url)
                    pdf_element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.citation_pdf_url"))
                    )
                    pdf_url = pdf_element.get_attribute('href')
                    if pdf_url.startswith('/'):
                        pdf_url = urljoin("https://openreview.net", pdf_url)
                
                # Generate paper ID and store paper info
                paper_number = paper_url.split('/')[-1]
                paper_id = f"{conference}{year}_{paper_number}"
                
                papers.append((paper_id, title, pdf_url))
                paper_count += 1
                print(f"Found paper {paper_count}: {title}", flush=True)
                
                if max_papers and paper_count >= max_papers:
                    return papers
                    
            except Exception as e:
                print(f"Error processing paper {paper_url}: {str(e)}")
                continue
                
        return papers
        
    except Exception as e:
        print(f"Error during {conference} scraping: {str(e)}")
        raise
        
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                print(f"Error closing driver: {str(e)}")


def scrape_cvpr(year, filter_name=None, filter_value=None, max_papers=None):
    """
    Scrape papers from the CVPR conference website.

    :param year: Conference year (e.g., 2024)
    :param filter_name: Filter category (e.g., 'sessions')
    :param filter_value: Value to filter by (e.g., 'Oral')
    :param max_papers: Maximum number of papers to scrape (optional)
    :return: list of tuples (paper_id, title, pdf_url)
    """
    driver = None
    papers = []
    paper_count = 0
    
    try:
        # Construct the base URL
        base_url = f"https://cvpr.thecvf.com/virtual/{year}/papers.html"
        if filter_name and filter_value:
            encoded_filter_value = filter_value.replace(' ', '+')
            base_url += f"?filter={filter_name}&search={encoded_filter_value}"
        
        driver = setup_firefox_driver()
        print(f"Fetching papers from CVPR: {base_url}")
        driver.get(base_url)
        time.sleep(10)  # Wait for dynamic content
        
        # Get all paper links from the filtered page
        paper_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='poster/']")
        paper_links = [elem.get_attribute('href') for elem in paper_elements if elem.get_attribute('href')]
        print(f"Found {len(paper_links)} papers")
        
        for paper_url in paper_links:
            try:
                # Get paper title and PDF link
                driver.get(paper_url)
                title_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h2.card-title.main-title.text-center"))
                )
                title = title_element.text.strip() if title_element else "Unknown Title"
                
                try:
                    # Try finding by link text
                    pdf_page_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Paper PDF')]"))
                    )
                except Exception as e:
                    print(f"Could not find PDF page link: {str(e)}")
                    continue

                # Navigate to the paper's HTML page
                pdf_page_url = pdf_page_element.get_attribute('href')
                driver.get(pdf_page_url)
                
                # Find the actual PDF download link
                pdf_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//a[text()='pdf']"))
                )
                pdf_relative_url = pdf_element.get_attribute('href')
                
                # Convert relative URL to absolute URL if necessary
                if pdf_relative_url.startswith('/'):
                    pdf_url = f"https://openaccess.thecvf.com{pdf_relative_url}"
                else:
                    pdf_url = pdf_relative_url
                
                # Generate paper ID and store paper info
                paper_number = paper_url.split('/')[-1]
                paper_id = f"CVPR{year}_{paper_number}"
                
                papers.append((paper_id, title, pdf_url))
                paper_count += 1
                print(f"Found paper {paper_count}: {title}", flush=True)
                
                if max_papers and paper_count >= max_papers:
                    return papers
                    
            except Exception as e:
                print(f"Error processing paper {paper_url}: {str(e)}")
                continue
                
        return papers
        
    except Exception as e:
        print(f"Error during CVPR scraping: {str(e)}")
        raise
        
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                print(f"Error closing driver: {str(e)}")