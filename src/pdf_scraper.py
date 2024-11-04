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
        print("Firefox ESR driver successfully initialized")
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
    base_url = f"https://openreview.net/group?id={conference}.cc/{year}/{track}"
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
                
                # Check if there's a next page
                try:
                    # First check if we're on a disabled last page
                    disabled_button = driver.find_elements(By.XPATH, "//li[contains(@class, 'right-arrow') and contains(@class, 'disabled')]")
                    if disabled_button:
                        print("Reached the last page.", flush=True)
                        break

                    # If not disabled, proceed with finding and clicking the next button
                    next_button = driver.find_element(By.XPATH, "//li[contains(@class, 'right-arrow')]/a/span[text()='›']")
                    print("Moving to the next page...", flush=True)
                    # Scroll the button into view using JavaScript
                    driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                    # Wait a moment for the scroll to complete
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(3)  # Wait for the next page to load
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


def download_pdf(filename, url, output_dir):
    """
    Download a PDF file and save it to the specified directory.
    
    :param title: str, title of the paper
    :param url: str, URL of the PDF
    :param output_dir: str, directory to save the PDF
    """
    response = requests.get(url)
    if response.status_code == 200:
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return filepath
    else:
        return None
