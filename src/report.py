"""Report generation and visualization functions"""

import logging
from graphviz import Digraph
from .config import config

def generate_report(db):
    """
    Generates final report and visualization
    """
    # Get all data in a single call
    report_data = db.get_report_data()
    stats = report_data['statistics']
    villains = report_data['villains']

    # Print console report
    print("\n" + "="*50)
    print("STEAM COMMENT ANALYSIS REPORT")
    print("="*50)
    print(f"Total flagged comments: {stats['total_comments']}")
    print(f"Unique flagged commenters: {stats['unique_commenters']}")
    print(f"Total villains tracked: {len(villains)}")
    print("="*50)

    # Generate visualization with the fetched data
    generate_graph_visualization_with_data(report_data['flagged_comments'])

def generate_graph_visualization_with_data(comments):
    """
    Creates a directed graph visualization of the friend paths using provided data
    """
    # Create graph
    dot = Digraph(comment='Steam Comment Network')
    dot.attr(rankdir='TB')  # Changed to top-bottom for better layout
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='lightblue')
    dot.attr('edge', color='red')

    # Add hate words display at the top
    hate_words_text = "Hate Terms Monitored:\\n" + "\\n".join(config.hate_terms)
    if config.hate_regex_patterns:
        hate_words_text += "\\n\\nRegex Patterns:\\n" + "\\n".join(config.hate_regex_patterns)
    
    dot.node('hate_words_header', label=hate_words_text, 
             shape='plaintext', fillcolor='lightyellow', 
             fontsize='12', fontname='monospace')

    edges = set()
    nodes = {}  # steamid -> alias mapping
    user_comments = {}  # steamid -> list of comments

    # If no flagged comments, create a simple graph showing the analysis was performed
    if not comments:
        dot.node('start', label='Analysis Started', fillcolor='lightgreen')
        dot.node('no_flags', label='No Hate Speech Found', fillcolor='lightgray')
        dot.edge('hate_words_header', 'start', style='invis')  # Invisible edge for layout
        dot.edge('start', 'no_flags')
    else:
        # Process comments to collect user data
        for row in comments:
            commenter_id = row[0]
            commenter_name = row[1]
            profile_id = row[2]
            path = row[3]
            comment_text = row[4] if len(row) > 4 else "No comment text"

            # Add to nodes dictionary
            nodes[commenter_id] = commenter_name
            if profile_id not in nodes:
                nodes[profile_id] = profile_id  # Use ID if name not available

            # Collect comments for each user
            if commenter_id not in user_comments:
                user_comments[commenter_id] = []
            # Truncate comment to reasonable length for display
            truncated_comment = comment_text[:100] + "..." if len(comment_text) > 100 else comment_text
            user_comments[commenter_id].append(truncated_comment)

            # Parse path to create edges
            path_parts = path.split(' -> ')
            for i in range(len(path_parts) - 1):
                source = path_parts[i].strip()
                target = path_parts[i + 1].strip()
                edges.add((source, target))

        # Add nodes to graph with comments
        for node_id, node_label in nodes.items():
            # Truncate long names and sanitize
            display_name = node_label[:20] + "..." if len(node_label) > 20 else node_label
            
            # Add comments if this user has flagged comments
            if node_id in user_comments:
                comments_text = "\\n\\nFlagged Comments:\\n" + "\\n".join([f"• {comment}" for comment in user_comments[node_id][:3]])  # Show max 3 comments
                if len(user_comments[node_id]) > 3:
                    comments_text += f"\\n... and {len(user_comments[node_id]) - 3} more"
                label = display_name + comments_text
                dot.node(node_id, label=label, fillcolor='lightcoral')  # Different color for flagged users
            else:
                dot.node(node_id, label=display_name)

        # Add invisible edge from header to first node for layout
        if nodes:
            first_node = next(iter(nodes.keys()))
            dot.edge('hate_words_header', first_node, style='invis')

        # Add edges to graph
        for source, target in edges:
            dot.edge(source, target)

    # Save visualization
    output_file = 'output/steam_comment_network'
    try:
        dot.render(output_file, format='png', cleanup=True)
        print(f"\nVisualization saved as {output_file}.png")
    except Exception as e:
        logging.error(f"Could not generate visualization: {e}")
        print("\nCould not generate visualization. Make sure graphviz is installed.")