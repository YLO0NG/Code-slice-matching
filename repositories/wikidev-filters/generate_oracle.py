
import os
import csv
import re

def get_file_path(repo_root, class_name):
    parts = class_name.split('.')
    # Handle inner classes
    if '$' in parts[-1]:
        parts[-1] = parts[-1].split('$')[0]
    
    # wikidev-filters structure: src/ca/...
    rel_path = os.path.join('src', *parts) + '.java'
    return os.path.join(repo_root, rel_path)

def find_signature_for_slice(content, start_offset, end_offset):
    # We want to find the method definition that encloses [start_offset, end_offset]
    # Strategy:
    # 1. Find all opening braces '{' before start_offset.
    # 2. For each brace, check if it closes after end_offset.
    # 3. The one that is "closest" to start_offset (largest index) and satisfies 2 is the innermost container.
    # 4. Check if that container is a method.
    
    # Find all { and } positions
    # This is a simple parser, might be fooled by comments/strings, but usually sufficient for this task.
    
    # Better: remove comments and strings for parsing structure? 
    # No, we need exact offsets.
    # Let's assume code is well-formatted and comments don't contain unbalanced braces often.
    
    open_braces = [m.start() for m in re.finditer(r'\{', content)]
    close_braces = [m.start() for m in re.finditer(r'\}', content)]
    
    # Map open brace to close brace
    # Stack based approach
    brace_map = {}
    stack = []
    
    # Merge and sort events
    events = [(pos, '{') for pos in open_braces] + [(pos, '}') for pos in close_braces]
    events.sort()
    
    for pos, type in events:
        if type == '{':
            stack.append(pos)
        elif type == '}':
            if stack:
                open_pos = stack.pop()
                brace_map[open_pos] = pos
    
    # Find enclosing blocks
    candidates = []
    for open_pos, close_pos in brace_map.items():
        if open_pos < start_offset and close_pos > end_offset:
            candidates.append(open_pos)
            
    if not candidates:
        return None
        
    # Sort by start position descending (innermost first)
    candidates.sort(reverse=True)
    
    for block_start in candidates:
        # Check if this block looks like a method
        # Scan backwards from block_start to find the signature
        # Stop at ';' or '}' or '{' or start of file
        
        # Limit lookback to avoid reading too much
        lookback_limit = 500
        search_start = max(0, block_start - lookback_limit)
        pre_text = content[search_start:block_start]
        
        # Find the last separator
        last_sep = -1
        for sep in [';', '}', '{']:
            idx = pre_text.rfind(sep)
            if idx > last_sep:
                last_sep = idx
        
        if last_sep != -1:
            signature_text = pre_text[last_sep+1:].strip()
        else:
            signature_text = pre_text.strip()
            
        # Clean up annotations @Override etc
        # Remove lines starting with @
        lines = signature_text.split('\n')
        clean_lines = [l for l in lines if not l.strip().startswith('@')]
        signature_text = " ".join(clean_lines)
        
        # Check if it looks like a method
        # Should have (...)
        if '(' not in signature_text or ')' not in signature_text:
            continue
            
        # Should not be a control structure
        # if, for, while, switch, catch, synchronized
        is_control = False
        for kw in ['if', 'for', 'while', 'switch', 'catch', 'synchronized', 'try', 'else']:
            # Check if it starts with keyword (ignoring whitespace)
            if re.match(r'^\s*' + kw + r'\b', signature_text):
                is_control = True
                break
        if is_control:
            continue
            
        # Should not be a class/interface
        if re.search(r'\b(class|interface|enum)\b', signature_text):
            continue
            
        # It's likely a method!
        # Normalize spaces
        signature_text = " ".join(signature_text.split())
        return signature_text
        
    return None

def generate_oracle(repo_root):
    refined_path = os.path.join(repo_root, 'oracle_refined.txt')
    output_path = os.path.join(repo_root, 'oracle.txt')
    
    if not os.path.exists(refined_path):
        print("oracle_refined.txt not found")
        return

    new_lines = []
    
    with open(refined_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            class_name = row['class_name']
            try:
                start = int(row['offset_start'])
                end = int(row['offset_end'])
            except:
                continue
                
            file_path = get_file_path(repo_root, class_name)
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                continue
                
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as src:
                content = src.read()
                
            signature = find_signature_for_slice(content, start, end)
            
            if signature:
                # Format: Class \t Signature \t eStart:Length;
                length = end - start
                line = f"{class_name}\t{signature}\te{start}:{length};"
                new_lines.append(line)
            else:
                print(f"Could not find signature for {class_name} around {start}-{end}")
                # Fallback: use function name from refined + ()
                func_name = row['function_name']
                line = f"{class_name}\tpublic void {func_name}()\te{start}:{end-start};"
                new_lines.append(line)

    with open(output_path, 'w') as f:
        for line in new_lines:
            f.write(line + '\n')
            
    print(f"Generated {output_path}")

if __name__ == "__main__":
    repo_root = r"d:\tools\Code slice matching\repositories\wikidev-filters"
    generate_oracle(repo_root)
