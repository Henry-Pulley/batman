# Steam Comment Screenshot Feature

## Overview

This feature automatically captures screenshots of reported Steam comments and saves them to the user's Downloads folder. When a user reports a profile from the "Comments" tab (which has an associated comment), the system will:

1. Fetch the original Steam profile page where the comment was posted
2. Locate the specific comment on the page
3. Highlight the comment and capture a screenshot
4. Save the screenshot to `~/Downloads/steam_screenshots/`
5. Store the screenshot path in the database

## How It Works

### User Workflow

1. User navigates to the "Comments" tab in the web interface
2. User clicks the "Report" button for a comment they want to report
3. The system immediately adds the profile to the Report Center
4. **NEW**: The system initiates screenshot capture in the background
5. Screenshot is saved to the Downloads folder and database is updated with the path

### Technical Implementation

#### Files Modified/Added:

- `src/screenshot_utils.py` - New utility module for screenshot capture
- `app.py` - Modified `/api/report` endpoint to trigger screenshots
- `requirements.txt` - Added Selenium and webdriver-manager dependencies

#### Database Schema:

The existing `reported_profiles` table already had a `screenshot_path` column which is now utilized:

```sql
CREATE TABLE reported_profiles (
    id SERIAL PRIMARY KEY,
    steam_id VARCHAR(17) NOT NULL,
    alias VARCHAR(255) NOT NULL,
    comment_id INTEGER REFERENCES flagged_comments(id),
    status VARCHAR(50) DEFAULT 'pending review',
    screenshot_path TEXT,  -- <-- This stores the screenshot file path
    reported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_date TIMESTAMP
);
```

#### Screenshot Process:

1. When `comment_id` is present in the report request, the system:

   - Queries the `flagged_comments` table to get the comment text and profile where it was posted
   - Starts a background thread to capture the screenshot (non-blocking)
   - Uses Selenium WebDriver with headless Chrome to navigate to the Steam profile
   - **NEW**: Automatically scrolls down to the comments section of the profile
   - **NEW**: Attempts to load more comments by clicking pagination buttons
   - Searches for the specific comment text using multiple strategies (exact match, fuzzy match, keyword search)
   - **NEW**: Finds the best container element for the comment to ensure proper screenshot dimensions
   - Highlights the comment with a red border, yellow background, and shadow effect
   - **NEW**: Takes a focused screenshot of the comment container, with fallback to full page if needed
   - Saves screenshot to `~/Downloads/steam_screenshots/steam_comment_{steam_id}_{comment_id}_{timestamp}.png`
   - Updates the database with the screenshot path

2. If no `comment_id` is present (report from Villains tab), no screenshot is captured

#### Screenshot File Naming:

```
steam_comment_{steam_id}_{comment_id}_{timestamp}.png
```

Example: `steam_comment_76561198123456789_42_20240803_143052.png`

## Dependencies

### New Python Packages:

- `selenium==4.15.2` - Web browser automation
- `webdriver-manager==4.0.1` - Automatic ChromeDriver management
- `psutil==5.9.8` - Process management for proper browser cleanup

### System Requirements:

- Google Chrome browser installed on the system
- ChromeDriver (automatically managed by webdriver-manager)

## Configuration

### Downloads Directory:

Screenshots are saved to: `~/Downloads/steam_screenshots/`
This directory is automatically created if it doesn't exist.

### WebDriver Settings:

- Runs in headless mode (no visible browser window)
- Window size: 1920x1080
- Page load timeout: 30 seconds
- Images disabled for faster loading

## Error Handling

### Screenshot Capture Failures:

- If Chrome/ChromeDriver is not available, the report still succeeds but no screenshot is captured
- If the specific comment cannot be found on the page, a full page screenshot is taken instead
- If screenshot capture completely fails, the report still succeeds with an empty screenshot_path
- All errors are logged but don't prevent the reporting functionality

### Fallback Behavior:

1. Try webdriver-manager ChromeDriver
2. If that fails, try system Chrome installation
3. If all fails, continue without screenshot (graceful degradation)

## Security Considerations

### Safe Operation:

- Screenshots only capture publicly accessible Steam profile pages
- No authentication or login required
- Runs in sandboxed headless browser environment
- Only captures content that would be visible to any Steam user

### Privacy:

- Screenshots are stored locally in user's Downloads folder
- No screenshots are transmitted to external services
- User has full control over screenshot files

## Testing

### Manual Testing:

1. Run the Flask application: `python3 app.py`
2. Navigate to the web interface
3. Go to the "Comments" tab
4. Click "Report" on any comment
5. Check `~/Downloads/steam_screenshots/` for the generated screenshot
6. Verify the screenshot path is stored in the `reported_profiles` table

### Automated Testing:

Run the test script to verify functionality:

```bash
python3 test_screenshot.py
```

## Troubleshooting

### Common Issues:

#### ChromeDriver Problems:

- **Error**: "Exec format error" on macOS
- **Solution**: The system automatically handles this with fallback to system Chrome

#### Permission Errors:

- **Error**: Cannot write to Downloads folder
- **Solution**: Ensure proper file system permissions for the user

#### Missing Chrome:

- **Error**: Chrome browser not found
- **Solution**: Install Google Chrome browser on the system

#### Network Timeouts:

- **Error**: Page load timeout
- **Solution**: Check internet connection and Steam availability

### Logs:

Screenshot capture activities are logged using Python's logging module. Check application logs for detailed information about screenshot operations.

## Future Enhancements

### Potential Improvements:

1. **Comment Highlighting**: Better visual highlighting of the target comment
2. **Multiple Screenshots**: Capture before/after screenshots showing context
3. **Metadata Extraction**: Save additional metadata about the comment (timestamp, reactions, etc.)
4. **Compression**: Optimize screenshot file sizes
5. **Batch Processing**: Queue multiple screenshots for better performance
6. **Cloud Storage**: Option to save screenshots to cloud storage services

### UI Enhancements:

1. **Screenshot Preview**: Show screenshot thumbnails in the Report Center
2. **Download Links**: Add direct download links for screenshots in the web interface
3. **Status Indicators**: Show screenshot capture status in real-time

## Technical Notes

### Thread Safety:

Screenshot capture runs in daemon threads to avoid blocking the web interface. The main application continues to function normally even if screenshot capture is in progress.

### Performance Impact:

- Screenshot capture happens asynchronously
- Typical capture time: 10-30 seconds depending on page load speed
- Memory usage: ~50-100MB per active Chrome instance
- **Browser cleanup**: Chrome instances are automatically closed after each capture
- No impact on normal application performance

### Browser Compatibility:

Currently only supports Chrome/Chromium browsers. Future versions could support Firefox or other browsers if needed.

## Support

For issues related to the screenshot feature:

1. Check the application logs for error messages
2. Verify Chrome browser is installed and up to date
3. Test with the provided test script
4. Ensure proper file system permissions for Downloads folder
