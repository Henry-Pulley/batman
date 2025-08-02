# app.py
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import asyncio
from src.database import PostgresDatabase
from src.recursive_search import recursive_profile_search
from src.config import config
from src.config_manager import ConfigManager
from main import process_urls
import threading

app = Flask(__name__)
CORS(app)

# Global queue for background tasks
crawl_status = {"active": False, "progress": 0, "total": 0}
crawl_summary = {
    "new_flagged_comments": 0,
    "unique_villains": 0, 
    "new_villains": 0,
    "exit_reason": "Unknown"
}

def get_pre_crawl_counts():
    """Get counts before crawl starts"""
    with PostgresDatabase() as db:
        # Count existing flagged comments
        db.cursor.execute("SELECT COUNT(*) as count FROM flagged_comments")
        result = db.cursor.fetchone()
        existing_comments = result['count'] if result else 0
        
        # Count existing villains
        db.cursor.execute("SELECT COUNT(*) as count FROM villains")
        result = db.cursor.fetchone()
        existing_villains = result['count'] if result else 0
        
        return {
            "comments": existing_comments,
            "villains": existing_villains
        }

def update_crawl_summary(before_counts, crawl_result=None):
    """Update crawl summary with statistics"""
    global crawl_summary
    
    print(f"[DEBUG] Before counts: {before_counts}")
    
    with PostgresDatabase() as db:
        # Count new flagged comments
        db.cursor.execute("SELECT COUNT(*) as count FROM flagged_comments")
        result = db.cursor.fetchone()
        total_comments = result['count'] if result else 0
        new_comments = total_comments - before_counts["comments"]
        print(f"[DEBUG] Total comments: {total_comments}, Before: {before_counts['comments']}, New: {new_comments}")
        
        # Count total villains
        db.cursor.execute("SELECT COUNT(*) as count FROM villains") 
        result = db.cursor.fetchone()
        total_villains = result['count'] if result else 0
        new_villains = total_villains - before_counts["villains"]
        print(f"[DEBUG] Total villains: {total_villains}, Before: {before_counts['villains']}, New: {new_villains}")
        
        # Count unique villains in new flagged comments (simplified)
        # This gets unique commenter IDs from the most recent comments
        if new_comments > 0:
            db.cursor.execute("""
                SELECT COUNT(DISTINCT commenter_steamid) as count
                FROM (
                    SELECT commenter_steamid, comment_scraped
                    FROM flagged_comments 
                    ORDER BY comment_scraped DESC 
                    LIMIT %s
                ) recent_comments
            """, (new_comments,))
            result = db.cursor.fetchone()
            unique_villains = result['count'] if result else 0
        else:
            unique_villains = 0
        
        # Update summary
        crawl_summary.update({
            "new_flagged_comments": new_comments,
            "unique_villains": unique_villains,
            "new_villains": new_villains,
            "exit_reason": determine_exit_reason(crawl_result)
        })
        
        print(f"[DEBUG] Updated crawl summary: {crawl_summary}")

def determine_exit_reason(crawl_result):
    """Determine why the crawl ended"""
    # Check if we have unprocessed profiles
    with PostgresDatabase() as db:
        db.cursor.execute("SELECT COUNT(*) as count FROM unprocessed_profiles")
        result = db.cursor.fetchone()
        unprocessed_count = result['count'] if result else 0
        
        if unprocessed_count > 0:
            # Check the most recent shutdown reason
            db.cursor.execute("""
                SELECT shutdown_reason 
                FROM unprocessed_profiles 
                ORDER BY added_timestamp DESC 
                LIMIT 1
            """)
            result = db.cursor.fetchone()
            if result:
                reason = result['shutdown_reason']
                if "profile" in reason.lower() and "threshold" in reason.lower():
                    return "User profile threshold reached"
                elif "runtime" in reason.lower() and "threshold" in reason.lower():
                    return "Runtime threshold reached"
        
    return "User profile queue cleared"

@app.route('/')
def index():
    return render_template('index.html')  # Your UI HTML file

# API Endpoints
@app.route('/api/crawl', methods=['POST'])
def start_crawl():
    data = request.json
    urls = data.get('urls', [])
    
    if crawl_status["active"]:
        return jsonify({"error": "Crawl already in progress"}), 400
    
    # Start crawl in background thread
    def run_crawl():
        crawl_status["active"] = True
        try:
            # Store before counts
            before_counts = get_pre_crawl_counts()
            
            # DEBUG: Log which URLs are being processed
            import logging
            print(f"[DEBUG] Starting crawl with {len(urls)} URLs:")
            logging.info(f"Starting crawl with {len(urls)} URLs:")
            for i, url in enumerate(urls):
                print(f"[DEBUG]   URL {i+1}: {url}")
                logging.info(f"  URL {i+1}: {url}")
            
            # Run your existing crawl logic
            result = asyncio.run(process_urls(urls))
            
            # Calculate summary after crawl completes
            update_crawl_summary(before_counts, result)
        finally:
            crawl_status["active"] = False
    
    thread = threading.Thread(target=run_crawl)
    thread.start()
    
    return jsonify({"message": "Crawl started", "status": "active"})

@app.route('/api/crawl/status')
def get_crawl_status():
    return jsonify(crawl_status)

@app.route('/api/crawl/summary')
def get_crawl_summary():
    return jsonify(crawl_summary)

@app.route('/api/flagged-comments', methods=['GET'])
def get_flagged_comments():
    # Get query parameters
    search_term = request.args.get('search', '')
    time_filter = request.args.get('time_filter', 'all')
    
    with PostgresDatabase() as db:
        # Build SQL query based on filters
        query = """
            SELECT * FROM flagged_comments 
            WHERE 1=1
        """
        params = []
        
        if search_term:
            query += " AND (commenter_steamid LIKE %s OR commenter_alias LIKE %s)"
            params.extend([f'%{search_term}%', f'%{search_term}%'])
        
        if time_filter == 'hour':
            query += " AND comment_scraped >= NOW() - INTERVAL '1 hour'"
        elif time_filter == '24hours':
            query += " AND comment_scraped >= NOW() - INTERVAL '24 hours'"
        elif time_filter == '7days':
            query += " AND comment_scraped >= NOW() - INTERVAL '7 days'"
        
        query += " ORDER BY comment_scraped DESC"
        
        db.cursor.execute(query, params)
        results = db.cursor.fetchall()
        
    return jsonify(results)

@app.route('/api/villains', methods=['GET'])
def get_villains():
    search_term = request.args.get('search', '')
    time_filter = request.args.get('time_filter', 'all')
    
    with PostgresDatabase() as db:
        # Join with flagged_comments to get the earliest comment_scraped timestamp
        query = """
            SELECT v.*, MIN(fc.comment_scraped) as first_seen
            FROM villains v
            LEFT JOIN flagged_comments fc ON v.steam_id = fc.commenter_steamid
            WHERE 1=1
        """
        params = []
        
        if search_term:
            query += " AND (v.steam_id LIKE %s OR v.aliases LIKE %s)"
            params.extend([f'%{search_term}%', f'%{search_term}%'])
        
        query += " GROUP BY v.id, v.steam_id, v.aliases ORDER BY first_seen DESC"
        
        db.cursor.execute(query, params)
        results = db.cursor.fetchall()
        
    return jsonify(results)

@app.route('/api/report', methods=['POST'])
def report_profile():
    data = request.json
    steam_id = data.get('steam_id')
    alias = data.get('alias')
    comment_id = data.get('comment_id')
    force = data.get('force', False)
    
    with PostgresDatabase() as db:
        # Check if steam_id already exists in reported_profiles
        if not force:
            db.cursor.execute("""
                SELECT COUNT(*) as count FROM reported_profiles 
                WHERE steam_id = %s
            """, (steam_id,))
            result = db.cursor.fetchone()
            if result and result['count'] > 0:
                return jsonify({
                    "duplicate": True,
                    "message": f"Steam ID {steam_id} already exists in the report center."
                })
        
        # Add to reported_profiles table
        # comment_id can be NULL for entries from villains tab
        db.cursor.execute("""
            INSERT INTO reported_profiles 
            (steam_id, alias, comment_id, status, screenshot_path)
            VALUES (%s, %s, %s, 'pending manual review', %s)
        """, (steam_id, alias, comment_id, ''))
        db.conn.commit()
    
    return jsonify({"message": "Profile reported successfully"})

@app.route('/api/monitor', methods=['POST'])
def add_to_monitoring():
    data = request.json
    
    with PostgresDatabase() as db:
        db.cursor.execute("""
            INSERT INTO further_monitoring (steam_id, alias, added_date)
            VALUES (%s, %s, NOW())
            ON CONFLICT (steam_id) DO NOTHING
        """, (data['steam_id'], data['alias']))
        db.conn.commit()
    
    return jsonify({"message": "Added to monitoring"})

@app.route('/api/remove-monitoring', methods=['POST'])
def remove_from_monitoring():
    data = request.json
    steam_id = data.get('steam_id')
    
    with PostgresDatabase() as db:
        # Remove from further_monitoring table
        db.cursor.execute("""
            DELETE FROM further_monitoring 
            WHERE steam_id = %s
        """, (steam_id,))
        db.conn.commit()
        
        # Check if any rows were deleted
        if db.cursor.rowcount == 0:
            return jsonify({"error": "Profile not found in monitoring list"}), 404
    
    return jsonify({"message": "Removed from monitoring successfully"})

@app.route('/api/update-notes', methods=['POST'])
def update_user_notes():
    data = request.json
    steam_id = data.get('steam_id')
    user_notes = data.get('user_notes', '')
    
    if not steam_id:
        return jsonify({"error": "steam_id is required"}), 400
    
    with PostgresDatabase() as db:
        # Update user_notes in further_monitoring table
        db.cursor.execute("""
            UPDATE further_monitoring 
            SET user_notes = %s
            WHERE steam_id = %s
        """, (user_notes, steam_id))
        db.conn.commit()
        
        # Check if any rows were updated
        if db.cursor.rowcount == 0:
            return jsonify({"error": "Profile not found in monitoring list"}), 404
    
    return jsonify({"message": "User notes updated successfully"})

@app.route('/api/confirm-report', methods=['POST'])
def confirm_report():
    data = request.json
    steam_id = data.get('steam_id')
    submitted_date = data.get('submitted_date')
    
    with PostgresDatabase() as db:
        # Update status from 'pending manual review' to 'report submitted' and set submitted_date
        db.cursor.execute("""
            UPDATE reported_profiles 
            SET status = 'report submitted', submitted_date = %s
            WHERE steam_id = %s AND status = 'pending manual review'
        """, (submitted_date, steam_id))
        db.conn.commit()
        
        # Check if any rows were updated
        if db.cursor.rowcount == 0:
            return jsonify({"error": "No profile found with pending manual review status"}), 404
    
    return jsonify({"message": "Report confirmed successfully"})

@app.route('/api/reported-profiles', methods=['GET'])
def get_reported_profiles():
    search_term = request.args.get('search', '')
    status_filter = request.args.get('status_filter', 'all')
    time_filter = request.args.get('time_filter', 'all')
    
    with PostgresDatabase() as db:
        query = """
            SELECT rp.*, COALESCE(fc.comment_text, 'N/A') as comment_text 
            FROM reported_profiles rp 
            LEFT JOIN flagged_comments fc ON rp.comment_id = fc.id 
            WHERE 1=1
        """
        params = []
        
        if search_term:
            query += " AND (rp.steam_id LIKE %s OR rp.alias LIKE %s)"
            params.extend([f'%{search_term}%', f'%{search_term}%'])
        
        if status_filter != 'all':
            query += " AND rp.status = %s"
            params.append(status_filter)
        
        if time_filter == 'hour':
            query += " AND rp.reported_date >= NOW() - INTERVAL '1 hour'"
        elif time_filter == '24hours':
            query += " AND rp.reported_date >= NOW() - INTERVAL '24 hours'"
        elif time_filter == '7days':
            query += " AND rp.reported_date >= NOW() - INTERVAL '7 days'"
        
        query += " ORDER BY rp.reported_date DESC"
        
        db.cursor.execute(query, params)
        results = db.cursor.fetchall()
        
    return jsonify(results)

@app.route('/api/further-monitoring', methods=['GET'])
def get_further_monitoring():
    search_term = request.args.get('search', '')
    time_filter = request.args.get('time_filter', 'all')
    
    with PostgresDatabase() as db:
        query = "SELECT * FROM further_monitoring WHERE 1=1"
        params = []
        
        if search_term:
            query += " AND (steam_id LIKE %s OR alias LIKE %s)"
            params.extend([f'%{search_term}%', f'%{search_term}%'])
        
        if time_filter == 'hour':
            query += " AND added_date >= NOW() - INTERVAL '1 hour'"
        elif time_filter == '24hours':
            query += " AND added_date >= NOW() - INTERVAL '24 hours'"
        elif time_filter == '7days':
            query += " AND added_date >= NOW() - INTERVAL '7 days'"
        
        query += " ORDER BY added_date DESC"
        
        db.cursor.execute(query, params)
        results = db.cursor.fetchall()
        
    return jsonify(results)

@app.route('/api/unprocessed-profiles', methods=['GET'])
def get_unprocessed_profiles():
    search_term = request.args.get('search', '')
    time_filter = request.args.get('time_filter', 'all')
    
    with PostgresDatabase() as db:
        # Join with flagged_comments to get known aliases, and villains for additional aliases
        query = """
        SELECT DISTINCT 
            up.steam_id,
            COALESCE(v.aliases, fc.commenter_alias, 'Unknown') as known_aliases,
            up.friend_path,
            up.depth,
            up.shutdown_reason,
            up.added_timestamp
        FROM unprocessed_profiles up
        LEFT JOIN flagged_comments fc ON up.steam_id = fc.commenter_steamid
        LEFT JOIN villains v ON up.steam_id = v.steam_id
        WHERE 1=1
        """
        params = []
        
        if search_term:
            query += " AND (up.steam_id LIKE %s OR fc.commenter_alias LIKE %s OR v.aliases LIKE %s)"
            params.extend([f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'])
        
        if time_filter == 'hour':
            query += " AND up.added_timestamp >= NOW() - INTERVAL '1 hour'"
        elif time_filter == '24hours':
            query += " AND up.added_timestamp >= NOW() - INTERVAL '24 hours'"
        elif time_filter == '7days':
            query += " AND up.added_timestamp >= NOW() - INTERVAL '7 days'"
        
        query += " ORDER BY up.added_timestamp DESC"
        
        db.cursor.execute(query, params)
        results = db.cursor.fetchall()
        
    return jsonify(results)

# Hate Terms Management Endpoints
@app.route('/api/hate-terms', methods=['GET'])
def get_hate_terms():
    """Get all hate terms from config"""
    try:
        config_manager = ConfigManager()
        terms = config_manager.get_hate_terms()
        return jsonify({"terms": terms})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/hate-terms', methods=['POST'])
def add_hate_term():
    """Add a new hate term to config"""
    data = request.json
    term = data.get('term', '').strip()
    
    if not term:
        return jsonify({"error": "Term cannot be empty"}), 400
    
    try:
        config_manager = ConfigManager()
        success, message = config_manager.add_hate_term(term)
        
        if success:
            # Reload the config to apply changes
            from importlib import reload
            from src import config as config_module
            reload(config_module)
            # Also reload the global config instance
            from src.config import config, compile_hate_patterns
            compile_hate_patterns()
            return jsonify({"message": message, "term": term})
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/hate-terms/<term>', methods=['DELETE'])
def remove_hate_term(term):
    """Remove a hate term from config"""
    try:
        config_manager = ConfigManager()
        success, message = config_manager.remove_hate_term(term)
        
        if success:
            # Reload the config to apply changes
            from importlib import reload
            from src import config as config_module
            reload(config_module)
            # Also reload the global config instance
            from src.config import config, compile_hate_patterns
            compile_hate_patterns()
            return jsonify({"message": message})
        else:
            return jsonify({"error": message}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)