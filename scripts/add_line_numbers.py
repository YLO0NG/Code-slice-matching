# This script adds line_start and line_end columns to oracle_refined.txt based on byte offsets.
import os
import csv

def get_file_path(repo_root, class_name, project_name):
    parts = class_name.split('.')
    # Handle inner classes
    if '$' in parts[-1]:
        parts[-1] = parts[-1].split('$')[0]
        
    if project_name == 'JHotDraw5.2':
        # CH.ifa.draw... -> sources/CH/ifa/draw...
        rel_path = os.path.join('sources', *parts) + '.java'
    elif project_name == 'MyWebMarket':
        # classes.CustomerAction -> src/classes/CustomerAction.java
        rel_path = os.path.join('src', *parts) + '.java'
    elif project_name == 'wikidev-filters':
        # ca... -> src/ca...
        rel_path = os.path.join('src', *parts) + '.java'
    elif project_name == 'junit3.8':
        # junit... -> src/junit...
        rel_path = os.path.join('src', *parts) + '.java'
    else:
        # Default fallback
        rel_path = os.path.join('src', *parts) + '.java'
        
    return os.path.join(repo_root, rel_path)

def get_line_number(content, offset):
    # Count newlines up to offset
    # 1-based line number
    return content.count(b'\n', 0, offset) + 1

def process_project(base_dir, project_name):
    repo_root = os.path.join(base_dir, project_name)
    oracle_path = os.path.join(repo_root, 'oracle_refined.txt')
    
    if not os.path.exists(oracle_path):
        print(f"Skipping {project_name}: oracle_refined.txt not found.")
        return

    print(f"Processing {project_name}...")
    
    updated_rows = []
    headers = []
    
    try:
        with open(oracle_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            if 'line_start' not in headers:
                headers.extend(['line_start', 'line_end'])
            
            for row in reader:
                class_name = row['class_name']
                try:
                    start_offset = int(row['offset_start'])
                    end_offset = int(row['offset_end'])
                except ValueError:
                    print(f"  Invalid offsets for {class_name}")
                    row['line_start'] = -1
                    row['line_end'] = -1
                    updated_rows.append(row)
                    continue
                
                file_path = get_file_path(repo_root, class_name, project_name)
                
                if not os.path.exists(file_path):
                    print(f"  File not found: {file_path}")
                    row['line_start'] = -1
                    row['line_end'] = -1
                else:
                    try:
                        with open(file_path, 'rb') as src_f:
                            content = src_f.read()
                        
                        # Clamp offsets
                        start_offset = max(0, min(start_offset, len(content)))
                        end_offset = max(0, min(end_offset, len(content)))
                        
                        line_start = get_line_number(content, start_offset)
                        line_end = get_line_number(content, end_offset)
                        
                        row['line_start'] = line_start
                        row['line_end'] = line_end
                    except Exception as e:
                        print(f"  Error reading {file_path}: {e}")
                        row['line_start'] = -1
                        row['line_end'] = -1
                
                updated_rows.append(row)
                
        # Write back
        with open(oracle_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(updated_rows)
            
        print(f"Updated {oracle_path}")

    except Exception as e:
        print(f"Error processing {project_name}: {e}")

if __name__ == "__main__":
    base_dir = r"d:\tools\Code slice matching\repositories"
    projects = ["JHotDraw5.2", "MyWebMarket", "wikidev-filters", "junit3.8"]
    
    for p in projects:
        process_project(base_dir, p)
