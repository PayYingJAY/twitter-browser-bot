"""Chrome profiles are private and independent for X and Doubao."""
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

def create_browser(config, name):
    if name == 'twitter':
        mode = config.get('twitter_browser', {}).get('mode', 'isolated')
        if mode == 'existing_chrome':
            from existing_chrome import ExistingChrome
            return ExistingChrome(config)
        if mode != 'isolated':
            raise ValueError('twitter_browser.mode must be isolated or existing_chrome')
    options = Options()
    root = Path(config.get('_root', Path(__file__).parent))
    profile = root / 'browser_data' / name
    profile.mkdir(parents=True, exist_ok=True)
    options.add_argument('--user-data-dir=' + str(profile.resolve()))
    options.add_argument('--window-size=1280,900')
    if config.get('headless', False):
        options.add_argument('--headless=new')
    driver_path = config.get('chromedriver_path')
    service = Service(executable_path=driver_path) if driver_path else Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver
