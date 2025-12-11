# This script generates oracle_snippets.json containing code snippets and function signatures from oracle_refined.txt and oracle.txt.
import os
import csv
import json
import re

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

def simplify_type(type_str):
    # Remove package prefix
    # java.lang.String -> String
    # java.lang.String[] -> String[]
    # CH.ifa.draw.framework.Drawing -> Drawing
    
    type_str = type_str.strip()
    
    # Regex to match fully qualified names (containing at least one dot)
    # We replace them with just the class name (last part)
    pattern = r'\b([a-zA-Z_$][a-zA-Z0-9_$]*(\.[a-zA-Z_$][a-zA-Z0-9_$]*)+)\b'
    
    def replace_match(match):
        full_name = match.group(0)
        return full_name.split('.')[-1]
    
    simplified = re.sub(pattern, replace_match, type_str)
    
    return simplified

def format_function_signature(raw_signature):
    # raw_signature: "public void writeStorable(CH.ifa.draw.util.Storable)"
    # or "protected junit.framework.TestResult start(java.lang.String[]) throws ..."
    
    # Find the parameters parenthesis
    match = re.search(r'([a-zA-Z0-9_$]+)\s*\((.*?)\)', raw_signature, re.DOTALL)
    if not match:
        return raw_signature # Fallback
        
    method_name = match.group(1)
    params_str = match.group(2)
    
    return format_params(method_name, params_str)

def format_params(method_name, params_str):
    # Clean up newlines and extra spaces
    params_str = " ".join(params_str.split())
    
    if not params_str.strip():
        return f"{method_name}()"
        
    # Split params by comma, respecting generics < >
    params = []
    current_param = ""
    depth = 0
    for char in params_str:
        if char == '<': depth += 1
        elif char == '>': depth -= 1
        elif char == ',' and depth == 0:
            params.append(current_param.strip())
            current_param = ""
            continue
        current_param += char
    if current_param.strip():
        params.append(current_param.strip())
        
    # Extract type from "Type name"
    simplified_params = []
    for p in params:
        # p is like "ArrayList<IArtifact> artifacts" or "int projectid"
        # We want "ArrayList<IArtifact>" or "int"
        
        # Split by space, but be careful about generics
        # Usually type is the first part(s), name is the last part.
        # "final int x" -> type "int"
        
        parts = p.split()
        if not parts: continue
        
        # Remove 'final'
        if parts[0] == 'final':
            parts = parts[1:]
            
        if not parts: continue
        
        # Last part is usually the name
        # But check if it's just a type (e.g. in oracle.txt sometimes?)
        # In oracle.txt for wikidev-filters: "ArrayList<IArtifact> artifacts"
        
        if len(parts) > 1:
            # Assume last token is name
            type_part = " ".join(parts[:-1])
        else:
            type_part = parts[0]
            
        simplified_params.append(simplify_type(type_part))
    
    return f"{method_name}({', '.join(simplified_params)})"

def extract_signature_from_snippet(snippet, function_name):
    # Look for: function_name \s* \( ([^)]*) \)
    pattern = r'\b' + re.escape(function_name) + r'\s*\(([^)]*)\)'
    match = re.search(pattern, snippet, re.DOTALL)
    if match:
        params_str = match.group(1)
        return format_params(function_name, params_str)
    return f"{function_name}()"

def load_oracle_signatures(oracle_path):
    signatures = []
    if not os.path.exists(oracle_path):
        return []
        
    with open(oracle_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            parts = line.split('\t')
            if len(parts) >= 2:
                signatures.append({
                    'class_name': parts[0],
                    'raw_signature': parts[1]
                })
    return signatures

def process_project(base_dir, project_name):
    repo_root = os.path.join(base_dir, project_name)
    oracle_path = os.path.join(repo_root, 'oracle_refined.txt')
    original_oracle_path = os.path.join(repo_root, 'oracle.txt')
    output_json_path = os.path.join(repo_root, 'oracle_snippets.json')
    
    if not os.path.exists(oracle_path):
        print(f"Skipping {project_name}: oracle_refined.txt not found.")
        return

    print(f"Processing {project_name}...")
    
    # Load original signatures
    original_signatures = load_oracle_signatures(original_oracle_path)
    sig_idx = 0
    
    snippets_data = []
    
    try:
        with open(oracle_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                class_name = row['class_name']
                simple_function_name = row['function_name']
                
                # Try to find signature in oracle.txt first
                formatted_signature = None
                
                # Search forward in original_signatures
                # We use a local index to avoid O(N^2) if the files are sorted similarly
                # But if they are not, we might miss it. 
                # Let's just search from 0 if not found, or better, just search all if list is small.
                # Given the size, linear search from 0 is fine for each row.
                
                for sig_entry in original_signatures:
                    if sig_entry['class_name'] == class_name:
                        # Check if function name is in raw signature
                        if re.search(r'\b' + re.escape(simple_function_name) + r'\s*\(', sig_entry['raw_signature']):
                            formatted_signature = format_function_signature(sig_entry['raw_signature'])
                            break
                        # Special case for constructors
                        short_class = class_name.split('.')[-1]
                        if simple_function_name == short_class:
                             if re.search(r'\b' + re.escape(simple_function_name) + r'\s*\(', sig_entry['raw_signature']):
                                formatted_signature = format_function_signature(sig_entry['raw_signature'])
                                break
                
                try:
                    start_offset = int(row['offset_start'])
                    end_offset = int(row['offset_end'])
                    line_start = int(row['line_start'])
                    line_end = int(row['line_end'])
                except ValueError:
                    print(f"  Invalid data for {class_name}.{simple_function_name}")
                    continue
                
                if line_start == -1:
                    print(f"  Skipping invalid entry {class_name}.{simple_function_name}")
                    continue

                file_path = get_file_path(repo_root, class_name, project_name)
                
                if not os.path.exists(file_path):
                    print(f"  File not found: {file_path}")
                    continue
                
                try:
                    with open(file_path, 'rb') as src_f:
                        content = src_f.read()
                    
                    # Clamp offsets
                    start_offset = max(0, min(start_offset, len(content)))
                    end_offset = max(0, min(end_offset, len(content)))
                    
                    code_snippet_bytes = content[start_offset:end_offset]
                    code_snippet = code_snippet_bytes.decode('utf-8', errors='replace')
                    
                    # If signature not found in oracle.txt, try to extract from snippet
                    if not formatted_signature:
                        formatted_signature = extract_signature_from_snippet(code_snippet, simple_function_name)
                    
                    snippets_data.append({
                        'class_name': class_name,
                        'function_name': formatted_signature,
                        'line_start': line_start,
                        'line_end': line_end,
                        'code_snippet': code_snippet
                    })
                    
                except Exception as e:
                    print(f"  Error reading {file_path}: {e}")
                    continue

        # Write JSON
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(snippets_data, f, indent=4, ensure_ascii=False)
            
        print(f"Generated {output_json_path} with {len(snippets_data)} snippets.")

    except Exception as e:
        print(f"Error processing {project_name}: {e}")

if __name__ == "__main__":
    base_dir = r"d:\tools\Code slice matching\repositories"
    projects = ["JHotDraw5.2", "MyWebMarket", "wikidev-filters", "junit3.8"]
    
    for p in projects:
        process_project(base_dir, p)
