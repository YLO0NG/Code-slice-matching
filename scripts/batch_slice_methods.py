import os
import json
import time
from openai import OpenAI

# Initialize OpenAI client
# Using the key provided in the example attachment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) 

BASE_DIR = r"d:\tools\Code slice matching"
REPOS_DIR = os.path.join(BASE_DIR, "repositories")
PROMPT_FILE = os.path.join(BASE_DIR, "prompt.txt")

import re

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

def load_prompt_template():
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def slice_method(method_data, dependencies, prompt_template, model="gpt-4o"):
    """
    Slices a single method using OpenAI API.
    """
    # Prepare the focal method JSON string
    focal_method_str = json.dumps(method_data, indent=2)
    
    # Prepare the dependencies JSON string
    dependencies_str = json.dumps(dependencies, indent=2)
    
    # Replace placeholders in the prompt
    prompt = prompt_template.replace("{{ focal method }}", focal_method_str)
    prompt = prompt.replace("{{ dependencies }}", dependencies_str)
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert in software engineering and code refactoring, specialized in analyzing and decomposing complex methods."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4096
        )
        
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
            except json.JSONDecodeError:
                print(f"  Warning: Failed to parse JSON for {method_data.get('function_name')}")
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
        
        context_filename = get_context_filename(class_name, function_name)
        context_path = os.path.join(context_dir, context_filename)
        
        dependencies = {}
        if os.path.exists(context_path):
            with open(context_path, 'r', encoding='utf-8') as f:
                dependencies = json.load(f)
        else:
            print(f"    Warning: Context file not found: {context_filename}")
            dependencies = {"message": "Context information not available"}

        result = slice_method(method, dependencies, prompt_template)
        
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
