"""Screenshot utility for capturing Steam comment screenshots"""
import os
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager


class SteamCommentScreenshot:
    """Utility class for capturing screenshots of Steam comments"""
    
    def __init__(self):
        self.driver = None
        self.downloads_path = self._get_downloads_path()
        
    def _get_downloads_path(self) -> str:
        """Get the user's Downloads folder path"""
        home = Path.home()
        downloads = home / "Downloads" / "steam_screenshots"
        downloads.mkdir(exist_ok=True)
        return str(downloads)
    
    def _setup_driver(self) -> bool:
        """Setup Chrome WebDriver with appropriate options"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in background
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-images")  # Faster loading
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            # Use webdriver-manager to automatically manage ChromeDriver
            try:
                # Try to get ChromeDriver path
                driver_path = ChromeDriverManager().install()
                
                # On macOS, fix executable permissions if needed
                import platform
                import stat
                if platform.system() == "Darwin":  # macOS
                    # Find the actual chromedriver executable
                    import glob
                    possible_paths = [
                        driver_path,
                        os.path.join(os.path.dirname(driver_path), "chromedriver"),
                        glob.glob(os.path.join(os.path.dirname(driver_path), "**/chromedriver"), recursive=True)
                    ]
                    
                    for path in possible_paths:
                        if isinstance(path, list):
                            for p in path:
                                if os.path.isfile(p):
                                    driver_path = p
                                    break
                        elif isinstance(path, str) and os.path.isfile(path):
                            driver_path = path
                            break
                    
                    # Make executable
                    if os.path.isfile(driver_path):
                        os.chmod(driver_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
                        logging.info(f"Set executable permissions for ChromeDriver: {driver_path}")
                
                service = Service(driver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                self.driver.set_page_load_timeout(30)
                
                logging.info("Chrome WebDriver initialized successfully")
                return True
                
            except Exception as driver_error:
                logging.error(f"ChromeDriver setup failed: {driver_error}")
                # Fallback: try system Chrome if available
                try:
                    logging.info("Attempting fallback to system Chrome...")
                    self.driver = webdriver.Chrome(options=chrome_options)
                    self.driver.set_page_load_timeout(30)
                    logging.info("Chrome WebDriver initialized using system Chrome")
                    return True
                except Exception as fallback_error:
                    logging.error(f"System Chrome fallback failed: {fallback_error}")
                    return False
            
        except Exception as e:
            logging.error(f"Failed to setup Chrome WebDriver: {e}")
            return False
    
    def _cleanup_driver(self):
        """Clean up WebDriver resources and ensure browser is properly closed"""
        if self.driver:
            try:
                # Get the process ID before quitting (for cleanup verification)
                try:
                    chrome_pid = self.driver.service.process.pid if hasattr(self.driver, 'service') and hasattr(self.driver.service, 'process') else None
                except:
                    chrome_pid = None
                
                # Close all windows first
                try:
                    self.driver.close()
                    logging.debug("All browser windows closed")
                except:
                    pass  # Ignore errors if windows already closed
                
                # Quit the driver completely
                self.driver.quit()
                logging.info("WebDriver browser instance closed successfully")
                
                # Give the process a moment to terminate
                time.sleep(1)
                
                # Verify the Chrome process has terminated
                if chrome_pid:
                    try:
                        import psutil
                        if psutil.pid_exists(chrome_pid):
                            logging.warning(f"Chrome process {chrome_pid} still running, attempting to terminate")
                            process = psutil.Process(chrome_pid)
                            process.terminate()
                            time.sleep(0.5)
                            if process.is_running():
                                process.kill()
                                logging.warning(f"Force killed Chrome process {chrome_pid}")
                    except ImportError:
                        # psutil not available, skip process verification
                        pass
                    except Exception as e:
                        logging.debug(f"Process cleanup verification failed: {e}")
                        
            except Exception as e:
                logging.warning(f"Error during driver cleanup: {e}")
                
                # Emergency cleanup: try to close and quit again
                try:
                    if self.driver:
                        self.driver.close()
                        self.driver.quit()
                        logging.info("Emergency cleanup successful")
                except Exception as emergency_error:
                    logging.warning(f"Emergency cleanup failed: {emergency_error}")
            finally:
                # Always set driver to None to prevent memory leaks
                self.driver = None
                logging.debug("WebDriver reference cleared")
    
    def _construct_steam_profile_url(self, steam_id: str) -> str:
        """Construct Steam profile URL from Steam ID"""
        if steam_id.isdigit() and len(steam_id) == 17:
            # SteamID64 format
            return f"https://steamcommunity.com/profiles/{steam_id}"
        else:
            # Custom URL format
            return f"https://steamcommunity.com/id/{steam_id}"
    
    def _wait_for_comments_section(self, timeout: int = 20) -> bool:
        """Wait for the comments section to load"""
        try:
            # Wait for the comments area to be present
            wait = WebDriverWait(self.driver, timeout)
            
            # Look for various possible comment section selectors (more comprehensive)
            comment_selectors = [
                ".commentthread_comments",
                ".profile_comment_area", 
                ".commentthread_area",
                "#commentthread",
                ".commentthread",
                ".profile_comments",
                ".commentthread_comment",
                "[class*='comment']",
                ".comment_area",
                ".comment_thread"
            ]
            
            for selector in comment_selectors:
                try:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    logging.info(f"Found comments section using selector: {selector}")
                    return True
                except TimeoutException:
                    continue
            
            # Additional wait for dynamic content
            time.sleep(5)
            
            # Try one more time with a simpler approach
            try:
                # Look for any element containing "comment" in its class
                elements = self.driver.find_elements(By.XPATH, "//*[contains(@class, 'comment')]")
                if elements:
                    logging.info(f"Found {len(elements)} comment-related elements")
                    return True
            except:
                pass
            
            logging.warning("No comments section found with any selectors")
            return False
            
        except Exception as e:
            logging.error(f"Error waiting for comments section: {e}")
            return False
    
    def _find_comment_by_text(self, comment_text: str) -> Optional[any]:
        """Find a specific comment element by its text content"""
        try:
            # Clean up the comment text for better matching
            search_text = comment_text.strip().lower()
            
            # Look for comment text in various possible containers (more comprehensive)
            comment_selectors = [
                ".commentthread_comment_text",
                ".comment_content", 
                ".commentthread_comment .commentthread_comment_text",
                ".profile_comment .commentthread_comment_text",
                ".comment_text",
                ".commentthread_comment",
                "[class*='comment_text']",
                "[class*='comment_content']"
            ]
            
            logging.info(f"Searching for comment text: '{search_text[:100]}...'")
            
            for selector in comment_selectors:
                try:
                    comment_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    logging.debug(f"Found {len(comment_elements)} elements with selector: {selector}")
                    
                    for element in comment_elements:
                        element_text = element.text.strip().lower()
                        # Try multiple matching strategies
                        if (search_text in element_text or 
                            element_text in search_text or
                            any(word in element_text for word in search_text.split() if len(word) > 3)):
                            logging.info(f"Found matching comment element using selector: {selector}")
                            logging.debug(f"Element text: '{element_text[:100]}...'")
                            return element
                except Exception as e:
                    logging.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # Fallback: try XPath search for any text containing parts of the comment
            try:
                # Split comment into significant words (>3 chars) and search for any
                words = [word for word in search_text.split() if len(word) > 3]
                if words:
                    for word in words[:3]:  # Try first 3 significant words
                        xpath = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{word}')]"
                        elements = self.driver.find_elements(By.XPATH, xpath)
                        if elements:
                            logging.info(f"Found comment using XPath search for word: '{word}'")
                            return elements[0]
            except Exception as e:
                logging.debug(f"XPath search failed: {e}")
            
            logging.warning(f"Could not find comment with text: {comment_text[:50]}...")
            return None
            
        except Exception as e:
            logging.error(f"Error finding comment by text: {e}")
            return None
    
    def _generate_filename(self, steam_id: str, comment_id: str) -> str:
        """Generate a unique filename for the screenshot"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"steam_comment_{steam_id}_{comment_id}_{timestamp}.png"
    
    def _scroll_to_comments_section(self) -> bool:
        """Scroll down to the comments section of the Steam profile"""
        try:
            logging.info("Scrolling to comments section...")
            
            # First, scroll down to load more content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Look for comments section and scroll to it
            comment_section_selectors = [
                ".commentthread_area", 
                ".profile_comment_area",
                ".commentthread",
                "#commentthread",
                ".commentthread_comments"
            ]
            
            for selector in comment_section_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        logging.info(f"Found comments section with selector: {selector}")
                        # Scroll to the comments section
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", element)
                        time.sleep(2)
                        return True
                except:
                    continue
            
            # If no specific section found, scroll to bottom where comments usually are
            logging.info("No specific comments section found, scrolling to bottom")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            return False
            
        except Exception as e:
            logging.error(f"Error scrolling to comments section: {e}")
            return False

    def _load_more_comments(self, max_attempts: int = 3) -> None:
        """Try to load more comments by clicking 'Show more comments' buttons"""
        try:
            for attempt in range(max_attempts):
                # Look for "Show more comments" or similar buttons
                show_more_selectors = [
                    "a[onclick*='ShowMoreComments']",
                    ".commentthread_show_more",
                    "a[href*='ShowMoreComments']",
                    ".commentthread_show_more_btn",
                    "*[onclick*='comment']",
                    "a[contains(text(), 'more')]"
                ]
                
                found_button = False
                for selector in show_more_selectors:
                    try:
                        buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for button in buttons:
                            if button.is_displayed() and button.is_enabled():
                                button_text = button.text.lower()
                                if 'more' in button_text or 'comment' in button_text:
                                    logging.info(f"Clicking 'Show more comments' button (attempt {attempt + 1})")
                                    self.driver.execute_script("arguments[0].click();", button)
                                    time.sleep(3)  # Wait for more comments to load
                                    found_button = True
                                    break
                        if found_button:
                            break
                    except Exception as e:
                        logging.debug(f"Error with selector {selector}: {e}")
                        continue
                
                if not found_button:
                    logging.debug(f"No more 'Show more comments' buttons found (attempt {attempt + 1})")
                    break
                    
        except Exception as e:
            logging.error(f"Error loading more comments: {e}")

    def capture_comment_screenshot(self, steam_id: str, comment_text: str, comment_id: str) -> Optional[str]:
        """
        Capture a screenshot of a specific comment on a Steam profile
        
        Args:
            steam_id: The Steam ID of the profile where the comment is located
            comment_text: The text content of the comment to find
            comment_id: The database ID of the comment for filename generation
            
        Returns:
            Path to the screenshot file if successful, None otherwise
        """
        if not self._setup_driver():
            return None
        
        try:
            # Construct profile URL
            profile_url = self._construct_steam_profile_url(steam_id)
            logging.info(f"Capturing screenshot for comment on profile: {profile_url}")
            
            # Navigate to the Steam profile
            self.driver.get(profile_url)
            
            # Wait for the page to load
            time.sleep(5)
            logging.info("Page loaded, now scrolling to comments section...")
            
            # Scroll to comments section
            self._scroll_to_comments_section()
            
            # Wait for comments section to load after scrolling
            time.sleep(3)
            
            # Try to load more comments to find the target comment
            logging.info("Loading more comments...")
            self._load_more_comments()
            
            # Wait for additional comments to load
            time.sleep(2)
            
            # Now try to find the specific comment
            logging.info(f"Searching for comment: '{comment_text[:50]}...'")
            comment_element = self._find_comment_by_text(comment_text)
            
            # Generate filename
            filename = self._generate_filename(steam_id, comment_id)
            filepath = os.path.join(self.downloads_path, filename)
            
            if comment_element:
                logging.info("Found target comment! Highlighting and capturing...")
                
                # Scroll the comment into view with some padding
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", comment_element)
                time.sleep(2)
                
                # Find the best container for the comment
                target_element = None
                container_selectors = [
                    "./ancestor::*[contains(@class, 'commentthread_comment')][1]",
                    "./ancestor::*[contains(@class, 'comment_content')][1]", 
                    "./ancestor::*[contains(@class, 'comment')][1]",
                    "./parent::*",
                    "."
                ]
                
                for selector in container_selectors:
                    try:
                        if selector == ".":
                            candidate = comment_element
                        else:
                            candidate = comment_element.find_element(By.XPATH, selector)
                        
                        # Check if element is visible and has dimensions
                        if (candidate.is_displayed() and 
                            candidate.size['width'] > 0 and 
                            candidate.size['height'] > 0):
                            target_element = candidate
                            logging.info(f"Selected target element using selector: {selector}")
                            logging.info(f"Element dimensions: {candidate.size['width']}x{candidate.size['height']}")
                            break
                    except Exception as e:
                        logging.debug(f"Selector {selector} failed: {e}")
                        continue
                
                if not target_element:
                    logging.warning("No suitable target element found, using comment element directly")
                    target_element = comment_element
                
                # Verify target element has proper dimensions
                size = target_element.size
                if size['width'] == 0 or size['height'] == 0:
                    logging.warning(f"Target element has zero dimensions: {size}, trying full page screenshot")
                    self.driver.save_screenshot(filepath)
                    logging.info(f"Full page screenshot saved to: {filepath}")
                else:
                    # Highlight the target element
                    self.driver.execute_script(
                        "arguments[0].style.border = '4px solid #ff0000'; arguments[0].style.backgroundColor = 'rgba(255, 255, 0, 0.2)'; arguments[0].style.boxShadow = '0 0 10px rgba(255, 0, 0, 0.8)';",
                        target_element
                    )
                    time.sleep(1)
                    
                    # Try to take screenshot of the target element
                    try:
                        target_element.screenshot(filepath)
                        logging.info(f"Comment screenshot saved to: {filepath}")
                    except Exception as screenshot_error:
                        logging.warning(f"Element screenshot failed ({screenshot_error}), taking full page screenshot")
                        self.driver.save_screenshot(filepath)
                        logging.info(f"Full page screenshot saved to: {filepath}")
                
            else:
                # Comment not found - take a screenshot of the comments section area
                logging.warning("Specific comment not found, capturing comments section...")
                
                # Try to capture just the comments area
                try:
                    comments_area = self.driver.find_element(By.CSS_SELECTOR, ".commentthread_area, .profile_comment_area, .commentthread")
                    if comments_area:
                        comments_area.screenshot(filepath)
                        logging.info(f"Comments section screenshot saved to: {filepath}")
                    else:
                        raise Exception("No comments area found")
                except:
                    # Final fallback - full page screenshot
                    self.driver.save_screenshot(filepath)
                    logging.info(f"Full page screenshot saved to: {filepath}")
            
            return filepath
            
        except TimeoutException:
            logging.error(f"Timeout while loading Steam profile: {profile_url}")
            return None
        except WebDriverException as e:
            logging.error(f"WebDriver error while capturing screenshot: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error while capturing screenshot: {e}")
            return None
        finally:
            self._cleanup_driver()
    
    def capture_profile_screenshot(self, steam_id: str) -> Optional[str]:
        """
        Capture a general screenshot of a Steam profile (fallback method)
        
        Args:
            steam_id: The Steam ID of the profile
            
        Returns:
            Path to the screenshot file if successful, None otherwise
        """
        if not self._setup_driver():
            return None
        
        try:
            profile_url = self._construct_steam_profile_url(steam_id)
            logging.info(f"Capturing profile screenshot: {profile_url}")
            
            # Navigate to the Steam profile
            self.driver.get(profile_url)
            time.sleep(3)
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"steam_profile_{steam_id}_{timestamp}.png"
            filepath = os.path.join(self.downloads_path, filename)
            
            # Take screenshot
            self.driver.save_screenshot(filepath)
            logging.info(f"Profile screenshot saved to: {filepath}")
            
            return filepath
            
        except Exception as e:
            logging.error(f"Error capturing profile screenshot: {e}")
            return None
        finally:
            self._cleanup_driver()


def capture_steam_comment_screenshot(steam_id: str, comment_text: str, comment_id: str) -> Optional[str]:
    """
    Convenience function to capture a Steam comment screenshot
    
    Args:
        steam_id: The Steam ID of the profile where the comment is located
        comment_text: The text content of the comment to find
        comment_id: The database ID of the comment for filename generation
        
    Returns:
        Path to the screenshot file if successful, None otherwise
    """
    screenshotter = SteamCommentScreenshot()
    return screenshotter.capture_comment_screenshot(steam_id, comment_text, comment_id)


def test_screenshot_capture():
    """Test function for screenshot capture"""
    # This is a test function - would need real Steam IDs and comment text for testing
    test_steam_id = "76561198000000000"  # Example Steam ID
    test_comment = "This is a test comment"
    test_comment_id = "test_123"
    
    result = capture_steam_comment_screenshot(test_steam_id, test_comment, test_comment_id)
    if result:
        print(f"Screenshot captured successfully: {result}")
    else:
        print("Screenshot capture failed")


if __name__ == "__main__":
    test_screenshot_capture()