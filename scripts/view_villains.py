import logging
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import PostgresDatabase


def setup_logging():
    """Configure logging for the viewer"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def display_villain_summary(villains):
    """Display a summary of all villains"""
    if not villains:
        print("No villains found in the database.")
        return
    
    print(f"\n{'='*60}")
    print(f"VILLAIN SUMMARY ({len(villains)} total)")
    print(f"{'='*60}")
    
    for i, villain in enumerate(villains, 1):
        aliases_list = villain['aliases'].split(',') if villain['aliases'] else ['No aliases']
        primary_alias = aliases_list[0].strip()
        
        print(f"{i:3d}. Steam ID: {villain['steam_id']}")
        print(f"     Commenter Alias: {primary_alias}")
        if len(aliases_list) > 1:
            other_aliases = ', '.join([alias.strip() for alias in aliases_list[1:]])
            print(f"     Other Aliases: {other_aliases}")
        print()

def display_villain_details(villains):
    """Display detailed information for each villain"""
    if not villains:
        return
    
    print(f"\n{'='*60}")
    print("DETAILED VILLAIN INFORMATION")
    print(f"{'='*60}")
    
    for villain in villains:
        print(f"\nVillain ID: {villain['id']}")
        print(f"Steam ID: {villain['steam_id']}")
        print(f"Steam Profile URL: https://steamcommunity.com/profiles/{villain['steam_id']}")
        
        if villain['aliases']:
            aliases_list = [alias.strip() for alias in villain['aliases'].split(',')]
            print(f"Known Aliases:")
            for alias in aliases_list:
                print(f"  - {alias}")
        else:
            print("No known aliases")
        print("-" * 40)

def main():
    """Main function to view villains"""
    setup_logging()
    
    try:
        with PostgresDatabase() as db:
            villains = db.get_all_villains()
            
            if not villains:
                print("No villains found in the database.")
                print("Run the main analyzer to identify and store villains.")
                return
            
            # Display summary
            display_villain_summary(villains)
            
            # Ask user if they want detailed view
            while True:
                choice = input("Show detailed information? (y/n): ").lower().strip()
                if choice in ['y', 'yes']:
                    display_villain_details(villains)
                    break
                elif choice in ['n', 'no']:
                    break
                else:
                    print("Please enter 'y' or 'n'")
    
    except Exception as e:
        logging.error(f"Error viewing villains: {e}")
        print(f"Failed to retrieve villains: {e}")

if __name__ == "__main__":
    main()