import json
import re
import networkx as nx
import os
import glob

# ==========================================
# 核心类：高级语义切片图构建器
# ==========================================
class AdvancedSemanticGraphBuilder:
    def __init__(self, method_info, slice_info):
        self.class_name = method_info['class_name']
        self.method_name = method_info['function_name']
        self.slices = slice_info['slices']
        self.graph = nx.MultiDiGraph()
        
        # 预编译正则，提升性能
        self.patterns = {
            'control_start': re.compile(r'\b(if|for|while|switch|try|else|case|catch)\b'),
            'terminal': re.compile(r'\b(return|throw|break|continue)\b'),
            'defs': re.compile(r'\b(?:[A-Z][a-zA-Z0-9]*|int|boolean|double|float|long|short|byte|char|String)\s+([a-z][a-zA-Z0-9]*)\b'),
            'words': re.compile(r'\b[a-zA-Z_]\w*\b')
        }
        
        # Java 关键字集合，用于过滤变量使用
        self.keywords = {
            'public', 'private', 'protected', 'static', 'final', 'void', 'int', 'boolean', 
            'char', 'byte', 'short', 'long', 'float', 'double', 'new', 'return', 'if', 'else', 
            'for', 'while', 'do', 'switch', 'case', 'default', 'break', 'continue', 'try', 
            'catch', 'finally', 'throw', 'throws', 'class', 'interface', 'extends', 'implements',
            'this', 'super', 'null', 'true', 'false', 'synchronized', 'abstract', 'instanceof'
        }

    def build(self):
        self._create_nodes()
        self._build_advanced_edges()
        return self._export_to_dict()

    def _create_nodes(self):
        for s in self.slices:
            code = s['code']
            
            # 1. 变量 Def/Use 分析
            defs = set(self.patterns['defs'].findall(code))
            all_words = set(self.patterns['words'].findall(code))
            uses = all_words - self.keywords - defs
            
            # 2. 控制流特征分析
            # 计算花括号平衡：正数表示开启了新作用域，负数表示关闭了作用域
            open_braces = code.count('{')
            close_braces = code.count('}')
            balance = open_braces - close_braces
            
            # 检查是否包含控制流关键字
            has_control_keyword = bool(self.patterns['control_start'].search(code))
            
            # 检查是否包含终结符 (Return/Throw)
            # 注意：这里做简单检查，如果切片包含 return，我们标记它可能终止
            is_terminal = bool(re.search(r'\b(return|throw)\b', code))

            self.graph.add_node(s['id'], 
                                label=f"Slice {s['id']}", 
                                code=code, 
                                defs=list(defs), 
                                uses=list(uses),
                                brace_balance=balance,
                                has_control=has_control_keyword,
                                is_terminal=is_terminal,
                                start_line=s.get('start_line'),
                                end_line=s.get('end_line'))

    def _build_advanced_edges(self):
        """构建 CF, DD, 和 高级 CD 边"""
        nodes = sorted(self.graph.nodes(data=True), key=lambda x: x[0]) # 按 ID 排序
        node_ids = [n[0] for n in nodes]
        
        # --- 1. 构建数据依赖 (DD) ---
        # 逻辑不变：Def-Use 关系
        for i in range(len(nodes)):
            u_id, u_data = nodes[i]
            for j in range(len(nodes)):
                if i == j: continue
                v_id, v_data = nodes[j]
                
                common = set(u_data['defs']).intersection(set(v_data['uses']))
                if common:
                    self.graph.add_edge(u_id, v_id, type='DD', vars=list(common))

        # --- 2. 构建高级控制依赖 (CD) ---
        # 使用“作用域栈”来模拟代码嵌套结构
        scope_stack = [] # 存储 (slice_id, brace_debt)
        
        for i in range(len(nodes)):
            curr_id = node_ids[i]
            curr_data = self.graph.nodes[curr_id]
            
            # A. 栈中的每个元素都是当前切片的“父作用域”，建立 CD 边
            for parent_id in scope_stack:
                # 只有当父节点是真正的控制结构（if/while等）时才建立 CD
                # 如果父节点只是一个普通的代码块（比如 static {），通常不算 CD
                if self.graph.nodes[parent_id]['has_control']:
                    self.graph.add_edge(parent_id, curr_id, type='CD', reason='Nesting')

            # B. 维护栈状态
            balance = curr_data['brace_balance']
            
            # 如果当前切片关闭了作用域 (balance < 0)
            # 我们需要从栈顶弹出对应数量的 scope
            # 这是一个简化处理：假设闭合的是最近开启的 scope
            temp_balance = balance
            while temp_balance < 0 and scope_stack:
                scope_stack.pop()
                temp_balance += 1
            
            # 如果当前切片开启了新作用域 (balance > 0)
            # 且它包含控制关键字，或者是显式的 block，则压入栈
            if balance > 0:
                # 压入 balance 次（通常一次 slice 可能开多个口，虽然少见）
                for _ in range(balance):
                    scope_stack.append(curr_id)

        # --- 3. 补充“卫语句”控制依赖 (Guard CD) ---
        # 如果 Slice A 是 terminal (return/throw)，且它处于某个作用域中，
        # 那么后续同作用域的切片其实都依赖于它。
        # 简化逻辑：保留之前的 Guard Check，因为它捕捉了 post-dominance
        for i in range(len(nodes)):
            u_id = node_ids[i]
            if self.graph.nodes[u_id]['is_terminal']:
                for j in range(i + 1, len(nodes)):
                    v_id = node_ids[j]
                    self.graph.add_edge(u_id, v_id, type='CD', reason='GuardCheck')

        # --- 4. 构建精细化控制流 (CF) ---
        for i in range(len(nodes) - 1):
            curr_id = node_ids[i]
            next_id = node_ids[i+1]
            curr_data = self.graph.nodes[curr_id]
            
            # 默认连接：顺序流
            should_connect = True
            
            # 如果当前切片包含无条件终止 (return/throw)，且不在 if/try 块内部（简化判断）
            # 这里的判断比较激进：只要有 return 就断开 CF。
            # 修正：如果 return 是在 if (...) { return; } 里面，那么还是可以流向下一条（如果 if 为假）
            # 因此，只有当切片是“纯粹的”终结者，或者我们在切片层面无法区分时，保留连接更安全。
            # 但我们可以标记一种特殊的 CF 类型
            
            if curr_data['is_terminal']:
                # 如果包含 return，我们标记 CF 边为 "Possible" 而不是 "Definite"
                # 或者，如果它是无条件的 return（比如代码全是 return ...），则断开
                # 这里为了图的连通性，我们保留边，但添加属性
                self.graph.add_edge(curr_id, next_id, type='CF', status='Conditional')
            else:
                self.graph.add_edge(curr_id, next_id, type='CF')

    def _export_to_dict(self):
        output = {
            "class_name": self.class_name,
            "method_name": self.method_name,
            "nodes": [],
            "edges": []
        }
        for n_id, data in self.graph.nodes(data=True):
            output["nodes"].append({
                "id": n_id,
                "label": data['label'],
                "start_line": data.get('start_line'),
                "end_line": data.get('end_line'),
                "defs": data['defs'],
                "uses": data['uses'],
                "is_terminal": data['is_terminal'],
                "has_control": data['has_control']
            })
        for u, v, data in self.graph.edges(data=True):
            edge_info = {"from": u, "to": v, "type": data['type']}
            if 'vars' in data: edge_info['vars'] = data['vars']
            if 'reason' in data: edge_info['reason'] = data['reason']
            output["edges"].append(edge_info)
        return output

# ==========================================
# 主程序逻辑 (保持文件扫描逻辑不变)
# ==========================================

def process_single_project(methods_file, slices_file, output_file):
    print(f"   Processing pair:")
    print(f"     -> Source Input: {os.path.basename(methods_file)}")
    
    try:
        with open(methods_file, 'r', encoding='utf-8') as f:
            methods_data = json.load(f)
        with open(slices_file, 'r', encoding='utf-8') as f:
            slices_data = json.load(f)
    except Exception as e:
        print(f"   [Error] Failed to load JSON files: {e}")
        return

    slices_map = {}
    for item in slices_data:
        key = f"{item['class_name']}:{item['function_name']}"
        slices_map[key] = item

    project_graphs = []
    for method in methods_data:
        key = f"{method['class_name']}:{method['function_name']}"
        if key in slices_map:
            # 使用新的高级构建器
            builder = AdvancedSemanticGraphBuilder(method, slices_map[key])
            graph_json = builder.build()
            project_graphs.append(graph_json)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(project_graphs, f, indent=2, ensure_ascii=False)
    
    print(f"   [Success] Output saved to -> {output_file}")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, 'data')
    if not os.path.exists(data_dir):
        parent_dir = os.path.dirname(script_dir)
        data_dir = os.path.join(parent_dir, 'data')
    
    if not os.path.exists(data_dir):
        print(f"Error: Could not find 'data' directory.")
        return

    print(f"Reading data from: {data_dir}\n")
    pattern = os.path.join(data_dir, "*_oracle_methods.json")
    method_files = glob.glob(pattern)

    count = 0
    for m_file_path in method_files:
        m_filename = os.path.basename(m_file_path)
        project_name = m_filename.replace("_oracle_methods.json", "")
        s_filename = f"{project_name}_LLM_slices.json"
        s_file_path = os.path.join(data_dir, s_filename)
        output_filename = f"{project_name}_graphs.json"
        output_file_path = os.path.join(script_dir, output_filename)

        if os.path.exists(s_file_path):
            count += 1
            print(f"[{count}] Project: {project_name}")
            process_single_project(m_file_path, s_file_path, output_file_path)
            print("-" * 50)

    print(f"\nAll done. Processed {count} projects.")

if __name__ == "__main__":
    main()