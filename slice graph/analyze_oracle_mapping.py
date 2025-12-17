import json
import os
import glob

# ==========================================
# 工具函数
# ==========================================
def calculate_overlap_metrics(graph_start, graph_end, oracle_start, oracle_end):
    if graph_start is None or graph_end is None: return 0, 0.0
    intersect_start = max(graph_start, oracle_start)
    intersect_end = min(graph_end, oracle_end)
    overlap_len = max(0, intersect_end - intersect_start + 1)
    if overlap_len == 0: return 0, 0.0
    oracle_len = oracle_end - oracle_start + 1
    if oracle_len == 0: return 0, 0.0
    ratio = overlap_len / oracle_len
    return overlap_len, ratio

def normalize_method_name(name):
    if '(' in name:
        return name.split('(')[0]
    return name

# ==========================================
# 核心分析逻辑
# ==========================================
def analyze_simple(graph_file, oracle_file, output_file_handle):
    project_name = os.path.basename(graph_file).replace('_graphs.json', '').replace('_advanced', '')
    
    print(f"\n{'='*60}", file=output_file_handle)
    print(f"Project: {project_name}", file=output_file_handle)
    print(f"{'='*60}", file=output_file_handle)

    try:
        with open(graph_file, 'r', encoding='utf-8') as f:
            graphs = json.load(f)
        
        # 加载 Oracle
        oracles = []
        with open(oracle_file, 'r', encoding='utf-8') as f:
            next(f) # skip header
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 6:
                    oracles.append({
                        'class': parts[0].strip(),
                        'method': parts[1].strip(),
                        'start': int(parts[4]),
                        'end': int(parts[5])
                    })
    except Exception as e:
        print(f"Error loading files: {e}", file=output_file_handle)
        return

    # 建立索引
    graph_index = {}
    for g in graphs:
        simple_name = normalize_method_name(g['method_name'])
        key = f"{g['class_name']}:{simple_name}"
        if key not in graph_index: graph_index[key] = []
        
        # 预计算范围
        starts = [n.get('start_line', 999999) for n in g['nodes']]
        ends = [n.get('end_line', -1) for n in g['nodes']]
        if starts:
            g['_min'] = min(starts)
            g['_max'] = max(ends)
            graph_index[key].append(g)

    # 匹配分析
    for o in oracles:
        key = f"{o['class']}:{o['method']}"
        if key not in graph_index: continue
        
        # 找最佳匹配图 (解决重载)
        candidates = graph_index[key]
        best_g = None
        best_overlap = 0
        
        for g in candidates:
            ov, _ = calculate_overlap_metrics(g.get('_min'), g.get('_max'), o['start'], o['end'])
            if ov > best_overlap:
                best_overlap = ov
                best_g = g
        
        if not best_g or best_overlap == 0: continue
        
        # 找到切片
        matched_ids = []
        for n in best_g['nodes']:
            s_start, s_end = n.get('start_line'), n.get('end_line')
            if not s_start: continue
            
            # 简单的包含/重叠判定
            intersect = max(0, min(s_end, o['end']) - max(s_start, o['start']) + 1)
            slice_len = s_end - s_start + 1
            if intersect > 0 and (intersect/slice_len > 0.3 or intersect/(o['end']-o['start']+1) > 0.5):
                matched_ids.append(n['id'])
        
        matched_ids.sort()
        if not matched_ids: continue

        # 输出结果
        print(f"\n>>> Method: {o['method']} (Oracle Lines: {o['start']}-{o['end']})", file=output_file_handle)
        print(f"    Mapped Slices: {matched_ids}", file=output_file_handle)
        
        # --- [新增功能] 打印切片行号 ---
        for nid in matched_ids:
            # 在 best_g['nodes'] 中找到对应的 node 对象
            node_obj = next((n for n in best_g['nodes'] if n['id'] == nid), None)
            if node_obj:
                print(f"      - Slice {nid}: L{node_obj.get('start_line')}-{node_obj.get('end_line')}", file=output_file_handle)
        # -----------------------------
        
        # 分析节点间关系
        internal_edges = []
        for e in best_g['edges']:
            if e['from'] in matched_ids and e['to'] in matched_ids:
                internal_edges.append(e)
        
        if internal_edges:
            print("    Relationships (Edges between slices):", file=output_file_handle)
            for e in internal_edges:
                details = ""
                if e['type'] == 'DD':
                    details = f", Vars: {e.get('vars', [])}"
                elif e['type'] == 'CD':
                    details = f", Reason: {e.get('reason', 'Guard')}"
                print(f"      {e['from']} -> {e['to']} [{e['type']}{details}]", file=output_file_handle)
        else:
            print("    Relationships: None (Independent slices or single slice)", file=output_file_handle)

# ==========================================
# 主程序
# ==========================================
def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 结果输出文件路径
    result_file_path = os.path.join(script_dir, "oracle_mapping_analysis_result.txt")
    
    # 尝试找到 data 目录
    data_dir = os.path.join(script_dir, 'data')
    if not os.path.exists(data_dir):
        data_dir = os.path.join(os.path.dirname(script_dir), 'data')
    
    if not os.path.exists(data_dir):
        print(f"[Fatal Error] 无法找到 'data' 文件夹。")
        return

    # 在脚本目录查找 graph 文件
    graph_files = glob.glob(os.path.join(script_dir, "*_graphs.json"))
    
    if not graph_files:
        print("[Error] 没有找到图文件 (*_graphs.json)")
        return

    print(f"正在分析 {len(graph_files)} 个项目，结果将保存至: {result_file_path}")

    # 打开文件准备写入
    with open(result_file_path, 'w', encoding='utf-8') as f:
        count = 0
        for g_file in graph_files:
            filename = os.path.basename(g_file)
            if 'semantic' in filename: continue 
            
            project_prefix = filename.replace('_graphs.json', '').replace('_advanced', '')
            oracle_file = os.path.join(data_dir, f"{project_prefix}_oracle_refined.txt")
            
            if os.path.exists(oracle_file):
                count += 1
                print(f"正在处理: {project_prefix} ...")
                analyze_simple(g_file, oracle_file, f)
            else:
                print(f"跳过: {project_prefix} (未找到 Oracle 文件)")

        if count == 0:
            print("未找到匹配的项目文件对。", file=f)
            print("未找到匹配的项目文件对。")
        else:
            print(f"\n全部完成！共分析了 {count} 个项目。")

if __name__ == "__main__":
    main()