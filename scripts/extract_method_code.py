# This script generates oracle_methods.json directly from oracle_snippets.json.
# It attempts to extract the full method body from the source code.
# If extraction fails, it falls back to using the code snippet from oracle_snippets.json.

import os
import json
import re

def get_file_path(repo_root, class_name, project_name):
    parts = class_name.split('.')
    if '$' in parts[-1]:
        parts[-1] = parts[-1].split('$')[0]
        
    if project_name == 'JHotDraw5.2':
        rel_path = os.path.join('sources', *parts) + '.java'
    elif project_name == 'MyWebMarket':
        rel_path = os.path.join('src', *parts) + '.java'
    elif project_name == 'wikidev-filters':
        rel_path = os.path.join('src', *parts) + '.java'
    elif project_name == 'junit3.8':
        rel_path = os.path.join('src', *parts) + '.java'
    else:
        rel_path = os.path.join('src', *parts) + '.java'
        
    return os.path.join(repo_root, rel_path)

def simplify_type_str(t):
    t = t.strip()
    # Handle Vector#RAW -> Vector
    if '#' in t:
        t = t.split('#')[0]
        
    # Handle array
    array_suffix = ""
    while t.endswith("[]"):
        array_suffix += "[]"
        t = t[:-2]
        
    # Remove generics <...> for comparison
    if '<' in t:
        t = t[:t.find('<')]
        
    if '.' in t:
        t = t.split('.')[-1]
        
    return t + array_suffix

def parse_signature(sig):
    match = re.match(r'([^(]+)\((.*)\)', sig)
    if not match:
        return sig, []
    name = match.group(1)
    params_str = match.group(2)
    
    params = []
    depth = 0
    current = ""
    for char in params_str:
        if char == '<': depth += 1
        elif char == '>': depth -= 1
        elif char == ',' and depth == 0:
            params.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        params.append(current.strip())
    return name, params

def match_params(source_params_str, target_types):
    src_params = []
    depth = 0
    current = ""
    for char in source_params_str:
        if char == '<': depth += 1
        elif char == '>': depth -= 1
        elif char == ',' and depth == 0:
            src_params.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        src_params.append(current.strip())
        
    if len(src_params) != len(target_types):
        return False
        
    for src, tgt in zip(src_params, target_types):
        parts = src.split()
        modifiers = {'final', 'synchronized'}
        while parts and parts[0] in modifiers:
            parts.pop(0)
            
        if not parts: return False
        
        is_c_array = False
        if parts[-1].endswith(']'):
             if '[' in parts[-1]:
                 is_c_array = True
        
        if len(parts) > 1:
            type_part = " ".join(parts[:-1])
            if is_c_array:
                type_part += "[]"
        else:
            type_part = parts[0]
            
        simple_src = simplify_type_str(type_part)
        simple_tgt = simplify_type_str(tgt)
        
        if simple_src != simple_tgt:
            return False
            
    return True

def extract_method_body(lines, start_line_idx):
    current_idx = start_line_idx
    brace_count = 0
    found_open = False
    
    body_lines = []
    
    while current_idx < len(lines):
        line = lines[current_idx]
        
        clean_line = line
        if '//' in clean_line:
            clean_line = clean_line.split('//')[0]
        
        for char in clean_line:
            if char == '{':
                brace_count += 1
                found_open = True
            elif char == '}':
                brace_count -= 1
        
        body_lines.append({
            "line": current_idx + 1,
            "code": line.rstrip('\n')
        })
        
        if found_open and brace_count == 0:
            return body_lines
            
        current_idx += 1
        
    return []

def find_method_in_file(file_path, method_name, target_param_types):
    if not os.path.exists(file_path):
        return None
        
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if method_name not in line:
            continue
            
        pattern = r'\b' + re.escape(method_name) + r'\s*\((.*)'
        match = re.search(pattern, line)
        if match:
            params_str = match.group(1)
            current_line_idx = i
            
            while ')' not in params_str and current_line_idx + 1 < len(lines):
                current_line_idx += 1
                params_str += " " + lines[current_line_idx].strip()
                
            paren_end = params_str.find(')')
            if paren_end != -1:
                params_content = params_str[:paren_end]
                
                # Check if it looks like a method call or abstract method (ends with ;)
                after_paren = params_str[paren_end+1:].strip()
                if after_paren.startswith(';'):
                    continue
                
                if match_params(params_content, target_param_types):
                    return extract_method_body(lines, i)
                    
    return None

def format_snippet_fallback(snippet, start_line):
    if start_line is None or start_line == -1:
        return []
    
    lines = snippet.splitlines()
    code_lines = []
    current_line = start_line
    
    for line_content in lines:
        code_lines.append({
            "line": current_line,
            "code": line_content
        })
        current_line += 1
    return code_lines

def process_project(base_dir, project_name):
    repo_root = os.path.join(base_dir, project_name)
    input_json_path = os.path.join(repo_root, 'oracle_snippets.json')
    output_json_path = os.path.join(repo_root, 'oracle_methods.json')
    
    if not os.path.exists(input_json_path):
        print(f"Skipping {project_name}: oracle_snippets.json not found.")
        return

    print(f"Processing {project_name}...")
    
    try:
        with open(input_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        annotated_data = []
        seen_signatures = set()
        
        for item in data:
            class_name = item.get('class_name')
            function_name = item.get('function_name')
            
            # Clean up function name (remove #RAW suffix if present)
            if function_name and "#RAW" in function_name:
                function_name = function_name.replace("#RAW", "")

            # Deduplication check
            sig_key = f"{class_name}::{function_name}"
            if sig_key in seen_signatures:
                continue
            seen_signatures.add(sig_key)

            start_line = item.get('line_start')
            code_snippet = item.get('code_snippet', '')
            
            # Parse function name to get simple name and params
            simple_name, param_types = parse_signature(function_name)
            
            if '.' in simple_name:
                simple_name = simple_name.split('.')[-1]
            
            file_path = get_file_path(repo_root, class_name, project_name)
            
            # Try to extract full method body
            code_lines = find_method_in_file(file_path, simple_name, param_types)
            
            if not code_lines:
                print(f"  Method not found: {class_name}.{function_name}. Skipping.")
                # Skip if not found, do not use fallback
                continue
                
            annotated_data.append({
                "class_name": class_name,
                "function_name": function_name,
                "code_lines": code_lines
            })
            
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(annotated_data, f, indent=4, ensure_ascii=False)
            
        print(f"Generated {output_json_path} with {len(annotated_data)} items.")
        
    except Exception as e:
        print(f"Error processing {project_name}: {e}")

if __name__ == "__main__":
    base_dir = r"d:\tools\Code slice matching\repositories"
    projects = ["JHotDraw5.2", "MyWebMarket", "wikidev-filters", "junit3.8"]
    
    for p in projects:
        process_project(base_dir, p)
