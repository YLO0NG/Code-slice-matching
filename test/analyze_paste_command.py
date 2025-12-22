import os
import json
from openai import OpenAI

# ================= 配置区 =================
# 确保这些文件名与你本地保存的文件名一致
ORACLE_FILE = "test/JHotDraw5.2_oracle_methods.json"
CONTEXT_FILE = "test/context_CH.ifa.draw.standard.ConnectionTool_mouseDrag_MouseEvent__int__int_.json"
CCG_FILE = "ccgs/JHotDraw5.2_ccg.json"
PROMPT_TEMPLATE_FILE = "test/prompt.txt"

TARGET_CLASS = "CH.ifa.draw.standard.ConnectionTool"
TARGET_FUNCTION = "mouseDrag(MouseEvent, int, int)"
# ==========================================

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_text(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

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

def run_single_analysis():
    print(f"开始分析方法: {TARGET_CLASS}::{TARGET_FUNCTION}...")

    # 1. 加载数据
    print(f"加载 Oracle 数据: {ORACLE_FILE}")
    oracle_data = load_json(ORACLE_FILE)
    
    print(f"加载 Context 数据: {CONTEXT_FILE}")
    context_data = load_json(CONTEXT_FILE)
    
    print(f"加载 CCG 数据: {CCG_FILE}")
    if os.path.exists(CCG_FILE):
        ccg_list = load_json(CCG_FILE)
    else:
        print(f"警告: CCG 文件不存在: {CCG_FILE}")
        ccg_list = []
        
    prompt_template = load_text(PROMPT_TEMPLATE_FILE)

    # 2. 从 Oracle 中筛选目标方法
    focal_method = next(
        (m for m in oracle_data if m['class_name'] == TARGET_CLASS and m['function_name'] == TARGET_FUNCTION), 
        None
    )

    if not focal_method:
        print(f"错误: 在 {ORACLE_FILE} 中找不到目标方法。")
        return

    # 3. 查找匹配的 CCG
    ccg_data = find_matching_ccg(focal_method, ccg_list)
    if not ccg_data:
        print("警告: 未找到匹配的 CCG 数据")
        ccg_str = "No CCG available"
    else:
        print("已找到匹配的 CCG 数据")
        ccg_str = json.dumps(ccg_data, indent=2)

    # 4. 构造最终的 Prompt
    # 按照 prompt.txt 的占位符进行替换
    
    # 准备用于 Prompt 的方法数据，优先使用 cleaned_code
    focal_method_for_prompt = focal_method.copy()
    if 'cleaned_code' in focal_method_for_prompt:
        focal_method_for_prompt['code'] = focal_method_for_prompt['cleaned_code']
        # 移除冗余字段
        if 'code_lines' in focal_method_for_prompt:
            del focal_method_for_prompt['code_lines']
        del focal_method_for_prompt['cleaned_code']

    final_prompt = prompt_template.replace("{{ focal method }}", json.dumps(focal_method_for_prompt, indent=2))
    final_prompt = final_prompt.replace("{{ dependencies }}", json.dumps(context_data, indent=2))
    final_prompt = final_prompt.replace("{{ code_context_graph }}", ccg_str)

    # 5. 调用 OpenAI API
    print("正在发送请求到 OpenAI (gpt-4o)...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert in software engineering and code refactoring, specialized in analyzing and decomposing complex methods."},
                {"role": "user", "content": final_prompt}
            ],
            temperature=0.3
        )

        content = response.choices[0].message.content

        # 6. 输出结果
        print("\n" + "="*50)
        print("LLM 分析结果:")
        print("="*50)
        print(content)

        # 7. 保存到文件
        output_filename = os.path.join('test', f"analysis_result_{TARGET_CLASS.split('.')[-1]}.md")
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n结果已保存至: {output_filename}")

    except Exception as e:
        print(f"调用 API 失败: {e}")

if __name__ == "__main__":
    run_single_analysis()