import os
import json

BASE_DIR = r"d:\tools\Code slice matching\repositories"
PROJECTS = ["JHotDraw5.2", "MyWebMarket", "wikidev-filters", "junit3.8"]

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def clean_function_name(name):
    if not name: return name
    return name.replace("#RAW", "")

def get_overlap_type(snippet, slices):
    ds_start = snippet.get('line_start')
    ds_end = snippet.get('line_end')
    
    if ds_start is None or ds_end is None:
        return "Invalid Snippet"

    # Create a set of line numbers for the snippet
    ds_range = set(range(ds_start, ds_end + 1))
    
    overlapping_slices = []
    
    for sl in slices:
        ls_start = sl.get('start_line')
        ls_end = sl.get('end_line')
        
        if ls_start is None or ls_end is None:
            continue
            
        ls_range = set(range(ls_start, ls_end + 1))
        
        if not ds_range.isdisjoint(ls_range):
            overlapping_slices.append({
                "slice_id": sl.get('id'),
                "ls_start": ls_start,
                "ls_end": ls_end,
                "is_container": ls_start <= ds_start and ls_end >= ds_end
            })
            
    count = len(overlapping_slices)
    
    if count == 0:
        return "No Match", []
    elif count >= 2:
        return "Covers Multiple", overlapping_slices
    elif count == 1:
        if overlapping_slices[0]['is_container']:
            return "Inside One LLM Slice", overlapping_slices
        else:
            return "Partial Overlap with One", overlapping_slices
            
    return "Unknown", []

def evaluate_project(project_name):
    print(f"Evaluating {project_name}...")
    repo_dir = os.path.join(BASE_DIR, project_name)
    
    snippets_path = os.path.join(repo_dir, "oracle_snippets.json")
    slices_path = os.path.join(repo_dir, "LLM_slices.json")
    
    snippets = load_json(snippets_path)
    llm_slices_data = load_json(slices_path)
    
    # Index LLM slices by class_name + function_name for fast lookup
    slices_map = {}
    for item in llm_slices_data:
        c_name = item.get('class_name')
        f_name = clean_function_name(item.get('function_name'))
        key = f"{c_name}::{f_name}"
        slices_map[key] = item.get('slices', [])
        
    results = {
        "Covers Multiple": 0,
        "Inside One LLM Slice": 0,
        "Partial Overlap with One": 0,
        "No Match": 0,
        "Method Not Found": 0,
        "Total Snippets": 0
    }
    
    details = []
    
    for snippet in snippets:
        results["Total Snippets"] += 1
        
        c_name = snippet.get('class_name')
        f_name = clean_function_name(snippet.get('function_name'))
        key = f"{c_name}::{f_name}"
        
        if key not in slices_map:
            results["Method Not Found"] += 1
            details.append({
                "snippet": snippet,
                "result": "Method Not Found"
            })
            continue
            
        method_slices = slices_map[key]
        if not method_slices:
             # Method found but no slices parsed?
            results["No Match"] += 1
            details.append({
                "snippet": snippet,
                "result": "No Match (No Slices)"
            })
            continue

        category, matched_slices = get_overlap_type(snippet, method_slices)
        
        if category in results:
            results[category] += 1
        
        details.append({
            "snippet": snippet,
            "result": category,
            "matched_slices_count": len(matched_slices),
            "matched_slices": matched_slices
        })

    print(f"  Results for {project_name}:")
    for k, v in results.items():
        print(f"    {k}: {v}")
        
    # Update oracle_refined.txt with results
    update_oracle_refined(repo_dir, details)
        
    return results, details

def update_oracle_refined(repo_dir, details):
    refined_path = os.path.join(repo_dir, "oracle_refined.txt")
    output_path = os.path.join(repo_dir, "oracle_refined_evaluated.csv")
    
    if not os.path.exists(refined_path):
        print(f"  Warning: {refined_path} not found. Skipping CSV update.")
        return

    # Create a lookup map from details
    # Key: class_name::simple_function_name::line_start::line_end
    lookup = {}
    for d in details:
        s = d['snippet']
        full_func_name = clean_function_name(s.get('function_name'))
        # Extract simple name (remove parameters)
        simple_func_name = full_func_name.split('(')[0]
        
        key = f"{s.get('class_name')}::{simple_func_name}::{s.get('line_start')}::{s.get('line_end')}"
        lookup[key] = d

    try:
        with open(refined_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        header = lines[0].strip()
        # Check if header already has new columns to avoid duplication if run multiple times
        if "match_type" not in header:
            header += ",match_type,matched_slice_count,matched_slice_ids,matched_slice_ranges"
            
        new_lines = [header + "\n"]
        
        for line in lines[1:]:
            line = line.strip()
            if not line: continue
            
            parts = line.split(',')
            # Expected format: class_name,function_name,offset_start,offset_end,line_start,line_end
            if len(parts) < 6:
                new_lines.append(line + ",Unknown,0,,\n")
                continue
                
            c_name = parts[0]
            # oracle_refined.txt usually has simple function name, but let's be safe
            f_name = clean_function_name(parts[1]).split('(')[0]
            l_start = int(parts[4])
            l_end = int(parts[5])
            
            key = f"{c_name}::{f_name}::{l_start}::{l_end}"
            
            match_type = "Unknown"
            count = 0
            slice_ids = ""
            slice_ranges = ""
            
            if key in lookup:
                res = lookup[key]
                match_type = res['result']
                count = res.get('matched_slices_count', 0)
                matched_slices = res.get('matched_slices', [])
                
                # Sort by slice ID
                matched_slices.sort(key=lambda x: x['slice_id'])
                
                slice_ids = ";".join([str(s['slice_id']) for s in matched_slices])
                slice_ranges = ";".join([f"{s['ls_start']}-{s['ls_end']}" for s in matched_slices])
            else:
                # Fallback: try matching without line numbers if unique? 
                # For now, strict matching is safer.
                match_type = "No Match (Key Mismatch)"
                
            new_lines.append(f"{line},{match_type},{count},{slice_ids},{slice_ranges}\n")
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
            
        print(f"  Saved evaluated CSV to {output_path}")
        
    except Exception as e:
        print(f"  Error updating CSV: {e}")

def main():
    all_stats = {
        "Covers Multiple": 0,
        "Inside One LLM Slice": 0,
        "Partial Overlap with One": 0,
        "No Match": 0,
        "Method Not Found": 0,
        "Total Snippets": 0
    }
    
    full_report = {}
    
    for project in PROJECTS:
        stats, details = evaluate_project(project)
        full_report[project] = details
        
        for k, v in stats.items():
            all_stats[k] += v
            
    print("\n=== Overall Summary ===")
    for k, v in all_stats.items():
        print(f"{k}: {v}")
        
    # Save detailed report
    report_path = os.path.join(BASE_DIR, "evaluation_report.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed report saved to {report_path}")

if __name__ == "__main__":
    main()
