from aiohttp import web
from aiohttp_cors import setup, ResourceOptions
import os
import asyncio
import json
from src.recursive_search import recursive_profile_search
from src.database import PostgresDatabase
from src.config import config
import openai  # For GPT-4 integration
import logging

# Initialize OpenAI client (add OPENAI_API_KEY to your .env)
openai.api_key = os.getenv("OPENAI_API_KEY")

routes = web.RouteTableDef()

@routes.post('/api/analyze')
async def analyze_profiles(request):
    """Endpoint to start profile analysis"""
    try:
        data = await request.json()
        urls = data.get('urls', [])
        
        if not urls:
            return web.json_response({'error': 'No URLs provided'}, status=400)
        
        # Run analysis in background
        asyncio.create_task(run_analysis(urls))
        
        return web.json_response({'status': 'started', 'urls': len(urls)})
    except Exception as e:
        logging.error(f"Error in analyze_profiles: {e}")
        return web.json_response({'error': str(e)}, status=500)

@routes.get('/api/analyze/status')
async def get_analysis_status(request):
    """Get current analysis progress"""
    try:
        # Get basic stats from database to show progress
        with PostgresDatabase() as db:
            db.cursor.execute("SELECT COUNT(*) as total FROM flagged_comments")
            total_comments = db.cursor.fetchone()['total']
            
            db.cursor.execute("SELECT COUNT(DISTINCT commenter_steamid) as unique FROM flagged_comments")
            unique_commenters = db.cursor.fetchone()['unique']
        
        return web.json_response({
            'status': 'analyzing', 
            'total_comments': total_comments,
            'unique_commenters': unique_commenters
        })
    except Exception as e:
        logging.error(f"Error in get_analysis_status: {e}")
        return web.json_response({'error': str(e)}, status=500)

@routes.post('/api/query')
async def query_database(request):
    """Natural language query endpoint"""
    try:
        data = await request.json()
        query = data.get('query', '')
        
        if not query.strip():
            return web.json_response({'error': 'No query provided'}, status=400)
        
        # Convert natural language to SQL using GPT-4 if available, otherwise use basic search
        if openai.api_key:
            sql = await generate_sql_from_query(query)
        else:
            # Basic fallback search
            sql = f"SELECT * FROM flagged_comments WHERE comment_text ILIKE '%{query}%' LIMIT 10"
        
        # Execute query safely
        with PostgresDatabase() as db:
            db.cursor.execute(sql)
            results = db.cursor.fetchall()
            # Convert RealDictRow to regular dict and handle datetime serialization
            serialized_results = []
            for row in results:
                row_dict = dict(row)
                # Convert datetime objects to strings
                for key, value in row_dict.items():
                    if hasattr(value, 'isoformat'):  # datetime objects
                        row_dict[key] = value.isoformat()
                serialized_results.append(row_dict)
            results = serialized_results
        
        return web.json_response({
            'sql': sql,
            'data': results
        })
    except Exception as e:
        logging.error(f"Error in query_database: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def generate_sql_from_query(natural_query):
    """Use GPT-4 to convert natural language to SQL"""
    try:
        prompt = f"""
        Convert this question to a PostgreSQL query for a database with these tables:
        - flagged_comments (id, commenter_steamid, commenter_alias, profile_steamid, comment_text, comment_date, friend_path, comment_scraped)
        - villains (id, steam_id, aliases)
        
        Question: {natural_query}
        
        Return only the SQL query, nothing else. Limit results to 50 rows maximum.
        """
        
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.choices[0].message.content.strip() if response.choices[0].message.content else ""
    except Exception as e:
        logging.error(f"Error generating SQL from query: {e}")
        # Fallback to basic search
        return f"SELECT * FROM flagged_comments WHERE comment_text ILIKE '%{natural_query}%' LIMIT 10"

async def run_analysis(urls):
    """Run the analysis in the background"""
    try:
        for url in urls:
            logging.info(f"Starting analysis for URL: {url}")
            # The recursive_profile_search is not async, so run it in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, recursive_profile_search, url)
            logging.info(f"Completed analysis for URL: {url}")
    except Exception as e:
        logging.error(f"Error in run_analysis: {e}")

@routes.get('/api/comments')
async def get_comments(request):
    """Get all flagged comments"""
    try:
        with PostgresDatabase() as db:
            comments = db.get_all_flagged_comments_detailed()
            # Convert RealDictRow to regular dict and handle datetime serialization
            serialized_comments = []
            for row in comments:
                row_dict = dict(row)
                # Convert datetime objects to strings
                for key, value in row_dict.items():
                    if hasattr(value, 'isoformat'):  # datetime objects
                        row_dict[key] = value.isoformat()
                serialized_comments.append(row_dict)
        
        return web.json_response({'data': serialized_comments})
    except Exception as e:
        logging.error(f"Error in get_comments: {e}")
        return web.json_response({'error': str(e)}, status=500)

@routes.get('/api/villains')
async def get_villains(request):
    """Get all villains"""
    try:
        with PostgresDatabase() as db:
            villains = db.get_all_villains()
            # Convert RealDictRow to regular dict and handle datetime serialization  
            serialized_villains = []
            for row in villains:
                row_dict = dict(row)
                # Convert datetime objects to strings
                for key, value in row_dict.items():
                    if hasattr(value, 'isoformat'):  # datetime objects
                        row_dict[key] = value.isoformat()
                serialized_villains.append(row_dict)
        
        return web.json_response({'data': serialized_villains})
    except Exception as e:
        logging.error(f"Error in get_villains: {e}")
        return web.json_response({'error': str(e)}, status=500)

@routes.get('/api/stats')
async def get_stats(request):
    """Get database statistics"""
    try:
        with PostgresDatabase() as db:
            report_data = db.get_report_data()
        
        return web.json_response(report_data)
    except Exception as e:
        logging.error(f"Error in get_stats: {e}")
        return web.json_response({'error': str(e)}, status=500)

def create_app():
    # Configure basic logging
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    app = web.Application()
    app.router.add_routes(routes)
    
    # Configure CORS
    setup(app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    logging.info("Batman API server configured successfully")
    return app

if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=8080)