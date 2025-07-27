"""Report generation and visualization functions"""

import logging
from graphviz import Digraph

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
    dot.attr(rankdir='LR')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='lightblue')
    dot.attr('edge', color='red')

    edges = set()
    nodes = {}  # steamid -> alias mapping

    # If no flagged comments, create a simple graph showing the analysis was performed
    if not comments:
        dot.node('start', label='Analysis Started', fillcolor='lightgreen')
        dot.node('no_flags', label='No Hate Speech Found', fillcolor='lightgray')
        dot.edge('start', 'no_flags')
    else:
        for row in comments:
            commenter_id = row[0]
            commenter_name = row[1]
            profile_id = row[2]
            path = row[3]

            # Add to nodes dictionary
            nodes[commenter_id] = commenter_name
            if profile_id not in nodes:
                nodes[profile_id] = profile_id  # Use ID if name not available

            # Parse path to create edges
            path_parts = path.split(' -> ')
            for i in range(len(path_parts) - 1):
                source = path_parts[i].strip()
                target = path_parts[i + 1].strip()
                edges.add((source, target))

        # Add nodes to graph
        for node_id, node_label in nodes.items():
            # Truncate long names and sanitize
            label = node_label[:20] + "..." if len(node_label) > 20 else node_label
            dot.node(node_id, label=label)

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