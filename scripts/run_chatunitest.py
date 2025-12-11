# This script runs the ChatUniTest context extractor tool for all methods defined in oracle_methods.json for each project.
import os
import json
import subprocess
import sys

import re

# Configuration
JAR_PATH = r"d:\tools\chatunitest-core\chatunitest-core-2.1.2-SNAPSHOT.jar"
BASE_DIR = r"d:\tools\Code slice matching\repositories"

PROJECT_CONFIG = {
    "JHotDraw5.2": {"src": "sources"},
    "MyWebMarket": {"src": "src"},
    "wikidev-filters": {"src": "src", "libs": "files"},
    "junit3.8": {"src": "src"}
}

def simplify_signature(sig):
    """
    Removes generic type parameters from the method signature.
    Example: clustering(ArrayList<IArtifact>) -> clustering(ArrayList)
    """
    # Remove content within angle brackets <...>
    # Using a loop to handle nested brackets if necessary, but simple regex works for most
    # We use a non-greedy match
    sig = re.sub(r'<[^>]+>', '', sig)
    # Remove #RAW suffix if present (found in JHotDraw5.2)
    sig = sig.replace("#RAW", "")
    return sig

def run_tool():
    # Check if JAR exists (using os.path.exists might fail if restricted, but subprocess will definitely fail if not found)
    if not os.path.exists(JAR_PATH):
        print(f"Warning: JAR file not found at {JAR_PATH}")
        # We proceed anyway, maybe it's accessible to the system even if not to python's os.stat
    
    for project_name, config in PROJECT_CONFIG.items():
        project_root = os.path.join(BASE_DIR, project_name)
        json_path = os.path.join(project_root, "oracle_methods.json")
        
        if not os.path.exists(json_path):
            print(f"Skipping {project_name}: {json_path} not found")
            continue
            
        print(f"Loading methods from {json_path}...")
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                methods = json.load(f)
        except Exception as e:
            print(f"Error loading JSON for {project_name}: {e}")
            continue
            
        print(f"Processing {project_name} ({len(methods)} methods)...")
        
        # Build classpath if libs are configured
        classpath_args = []
        if "libs" in config:
            libs_dir = os.path.join(project_root, config["libs"])
            if os.path.exists(libs_dir):
                # Find all .jar files in the libs directory
                jars = [os.path.join(libs_dir, f) for f in os.listdir(libs_dir) if f.endswith(".jar")]
                if jars:
                    # Join with os.pathsep (semicolon on Windows)
                    cp_string = os.pathsep.join(jars)
                    classpath_args = ["-cp", cp_string]
                    print(f"  Using classpath with {len(jars)} jars from {config['libs']}")
        
        success_count = 0
        fail_count = 0
        parsed_successfully = False
        
        for i, method in enumerate(methods):
            class_name = method['class_name']
            original_sig = method['function_name']
            
            # Simplify signature for the tool (remove generics)
            method_sig = simplify_signature(original_sig)
            
            # Construct command
            # java -jar chatunitest-core-2.1.2-SNAPSHOT.jar -p <project_root> -c <class_name> -m <method_sig> -s <src_dir> [-cp <classpath>]
            cmd = [
                "java", "-jar", JAR_PATH,
                "-p", project_root,
                "-c", class_name,
                "-m", method_sig,
                "-s", config['src']
            ]
            
            if classpath_args:
                cmd.extend(classpath_args)
            
            mode_str = "parsing"
            if parsed_successfully:
                cmd.append("--no-parse")
                mode_str = "cached"
            
            print(f"[{i+1}/{len(methods)}] Running ({mode_str}) for {class_name}.{method_sig}...")
            
            try:
                # Run command
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    success_count += 1
                    parsed_successfully = True
                else:
                    fail_count += 1
                    print(f"  Failed: {class_name}.{method_sig}")
                    print(f"  Error: {result.stderr.strip()}")
                    
            except Exception as e:
                fail_count += 1
                print(f"  Exception: {e}")
        
        print(f"Finished {project_name}: {success_count} success, {fail_count} failed.")

if __name__ == "__main__":
    run_tool()
