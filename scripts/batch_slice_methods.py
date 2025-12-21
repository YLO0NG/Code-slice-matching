import os
import json
import time
from openai import OpenAI
import re
 
# Retry settings for transient API failures
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1  # seconds
BACKOFF_FACTOR = 2


# Initialize OpenAI client
# Using the key provided in the example attachment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) 

BASE_DIR = r"d:\tools\Code slice matching"
REPOS_DIR = os.path.join(BASE_DIR, "repositories")
CCGS_DIR = os.path.join(BASE_DIR, "ccgs")
PROMPT_FILE = os.path.join(BASE_DIR, "prompt.txt")


def simplify_signature(sig):
    """
    Removes generic type parameters from the method signature.
    Example: clustering(ArrayList<IArtifact>) -> clustering(ArrayList)
    """
    sig = re.sub(r'<[^>]+>', '', sig)
    # Remove #RAW suffix if present
    sig = sig.replace("#RAW", "")
    return sig

def get_context_filename(class_name, function_name):
    """
    Generates the context filename based on class and function name.
    """
    # First, simplify the signature to match what run_chatunitest.py does
    simplified_func_name = simplify_signature(function_name)
    
    # Replace common special characters with underscores to match file naming convention
    # Example: start(String[]) -> start_String___
    safe_func_name = simplified_func_name
    replacements = {
        "(": "_",
        ")": "_",
        "[": "_",
        "]": "_",
        "<": "_",
        ">": "_",
        ", ": "__",
        " ": "" # Remove any remaining spaces
    }
    
    for old, new in replacements.items():
        safe_func_name = safe_func_name.replace(old, new)
        
    return f"context_{class_name}_{safe_func_name}.json"

def load_ccg_data(project_name):
    """
    Loads the CCG data for the given project.
    """
    ccg_path = os.path.join(CCGS_DIR, f"{project_name}_ccg.json")
    if os.path.exists(ccg_path):
        print(f"  Loading CCG data from {ccg_path}...")
        with open(ccg_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    print(f"  Warning: CCG file not found: {ccg_path}")
    return []

def find_matching_ccg(method_data, ccg_list):
    """
    Finds the matching CCG entry for the given method.
    """
    class_name = method_data['class_name']
    function_name = method_data['function_name']
    
    # Extract simple method name (e.g., "init" from "init()")
    simple_method_name = function_name.split('(')[0]
    
    # Convert class name to path suffix (e.g., "a.b.C" -> "a/b/C.java")
    path_suffix = class_name.replace('.', '/') + ".java"
    path_suffix_win = class_name.replace('.', '\\') + ".java"
    
    candidates = []
    for ccg in ccg_list:
        if ccg['method_name'] == simple_method_name:
            # Check file path
            ccg_path = ccg['file_path']
            # Normalize separators for comparison
            norm_ccg_path = ccg_path.replace('\\', '/')
            norm_suffix = path_suffix.replace('\\', '/')
            
            if norm_ccg_path.endswith(norm_suffix):
                candidates.append(ccg)
    
    if not candidates:
        return None
        
    if len(candidates) == 1:
        return candidates[0]
        
    # If multiple candidates, try to match by line numbers
    if 'code_lines' in method_data and method_data['code_lines']:
        method_start = method_data['code_lines'][0]['line']
        method_end = method_data['code_lines'][-1]['line']
        
        for ccg in candidates:
            # Check if CCG nodes overlap with method lines
            ccg_lines = [node['line_num'] for node in ccg.get('nodes', [])]
            if not ccg_lines:
                continue
            ccg_start = min(ccg_lines)
            ccg_end = max(ccg_lines)
            
            # Simple overlap check
            if not (ccg_end < method_start or ccg_start > method_end):
                return ccg
                
    return candidates[0] # Fallback

def load_prompt_template():
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def slice_method(method_data, dependencies, ccg_data, prompt_template, model="gpt-4o"):
    """
    Slices a single method using OpenAI API.
    """
    # Prepare the focal method JSON string
    focal_method_str = json.dumps(method_data, indent=2)
    
    # Prepare the dependencies JSON string
    dependencies_str = json.dumps(dependencies, indent=2)
    
    # Prepare the CCG JSON string
    ccg_str = json.dumps(ccg_data, indent=2) if ccg_data else "No CCG available"
    
    # Replace placeholders in the prompt
    prompt = prompt_template.replace("{{ focal method }}", focal_method_str)
    prompt = prompt.replace("{{ dependencies }}", dependencies_str)
    prompt = prompt.replace("{{ code_context_graph }}", ccg_str)
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert in software engineering and code refactoring, specialized in analyzing and decomposing complex methods."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_completion_tokens=4096
        )

        # Defensive: ensure response has choices
        if not response or not getattr(response, 'choices', None) or len(response.choices) == 0:
            print(f"  Warning: Empty or malformed response for {method_data.get('function_name')}")
            return None

        content = response.choices[0].message.content
        
        # Parse response
        result = {
            "full_response": content,
            "analysis": "",
            "slices": []
        }
        
        # Extract JSON part
        json_start = content.find("```json")
        if json_start != -1:
            result["analysis"] = content[:json_start].strip()
            json_start = content.find("\n", json_start) + 1
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            try:
                result["slices"] = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"  Warning: Failed to parse JSON for {method_data.get('function_name')}: {e}")
                print(f"Response content: {content}")
        else:
            result["analysis"] = content
            
        return result
        
    except Exception as e:
        print(f"  Error calling API: {e}")
        return None

def process_project(project_name):
    print(f"Processing project: {project_name}")
    project_dir = os.path.join(REPOS_DIR, project_name)
    oracle_methods_path = os.path.join(project_dir, "oracle_methods.json")
    context_dir = os.path.join(project_dir, "target", "chatunitest-info")
    output_path = os.path.join(project_dir, "LLM_slices.json")
    
    if not os.path.exists(oracle_methods_path):
        print(f"  oracle_methods.json not found in {project_dir}")
        return

    with open(oracle_methods_path, 'r', encoding='utf-8') as f:
        methods = json.load(f)
    
    # Load CCG data for the project
    ccg_list = load_ccg_data(project_name)
    
    prompt_template = load_prompt_template()
    
    all_results = []
    
    # Check if output already exists to resume or append? 
    # For now, we'll start fresh or maybe just process a few for testing if needed.
    # But the user asked to process "all methods".
    
    # LIMIT for testing purposes (remove or set to None for full run)
    # methods = methods[:1] 
    
    for method in methods:
        class_name = method['class_name']
        function_name = method['function_name']
        
        print(f"  Analyzing: {class_name}::{function_name}")
        
        # Find matching CCG
        ccg_data = find_matching_ccg(method, ccg_list)
        if not ccg_data:
            print(f"    Warning: No matching CCG found for {class_name}::{function_name}")
        
        context_filename = get_context_filename(class_name, function_name)
        context_path = os.path.join(context_dir, context_filename)
        
        dependencies = {}
        if os.path.exists(context_path):
            with open(context_path, 'r', encoding='utf-8') as f:
                dependencies = json.load(f)
        else:
            print(f"    Warning: Context file not found: {context_filename}")
            dependencies = {"message": "Context information not available"}

        result = slice_method(method, dependencies, ccg_data, prompt_template)

        # If initial call failed (None), retry with exponential backoff
        if result is None:
            retries = 0
            delay = INITIAL_RETRY_DELAY
            while retries < MAX_RETRIES and result is None:
                retries += 1
                print(f"    Retry {retries}/{MAX_RETRIES} for {class_name}::{function_name} after {delay}s")
                time.sleep(delay)
                result = slice_method(method, dependencies, ccg_data, prompt_template)
                delay *= BACKOFF_FACTOR

        if result:
            # Combine original method info with result
            method_result = {
                "class_name": class_name,
                "function_name": function_name,
                "analysis": result["analysis"],
                "slices": result["slices"],
                "full_response": result["full_response"]
            }
            all_results.append(method_result)
        else:
            # After retries still failed — record a stub result so we know it failed
            print(f"    Failed after {MAX_RETRIES} retries: {class_name}::{function_name}")
            method_result = {
                "class_name": class_name,
                "function_name": function_name,
                "analysis": "Error: failed after retries",
                "slices": [],
                "full_response": ""
            }
            all_results.append(method_result)
            
        # Sleep briefly to avoid rate limits if necessary
        # time.sleep(0.5) 

    # Save results
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  Saved results to {output_path}")

def main():
    projects = [d for d in os.listdir(REPOS_DIR) if os.path.isdir(os.path.join(REPOS_DIR, d))]
    
    for project in projects:
        process_project(project)

if __name__ == "__main__":
    main()
