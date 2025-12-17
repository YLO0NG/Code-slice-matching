import re
import os
from collections import defaultdict, Counter

def analyze_slice_mapping_report(file_path):
    """
    读取 oracle_mapping_analysis_result.txt 文件，统计每个重构案例
    映射到的切片（Slice）数量，并按项目进行分类汇总。
    """
    if not os.path.exists(file_path):
        print(f"错误：文件未找到在 {file_path}")
        return

    # 正则表达式用于提取关键信息
    PROJECT_PATTERN = re.compile(r"^Project: (.*)$")
    SLICES_PATTERN = re.compile(r"^\s*Mapped Slices: \[(.*)\]$")

    # 存储结果: {ProjectName: [slice_count, slice_count, ...]}
    project_slice_counts = defaultdict(list)
    
    current_project = None
    total_cases = 0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # 1. 提取项目名称
                match_project = PROJECT_PATTERN.match(line)
                if match_project:
                    current_project = match_project.group(1)
                    continue

                # 2. 提取切片列表
                if current_project:
                    match_slices = SLICES_PATTERN.match(line)
                    if match_slices:
                        # 提取 [1, 2, 3] 内部的数字，计算切片数量
                        slices_str = match_slices.group(1).replace(' ', '')
                        if slices_str:
                            slice_count = len(slices_str.split(','))
                            project_slice_counts[current_project].append(slice_count)
                            total_cases += 1
                        else:
                            # 理论上不会出现 Mapped Slices: []，但以防万一
                            project_slice_counts[current_project].append(0)
                            total_cases += 1

    except Exception as e:
        print(f"处理文件时发生错误: {e}")
        return

    # --- 统计和报告生成 ---
    if total_cases == 0:
        print("未发现有效数据案例。")
        return

    print("\n" + "="*50)
    print("重构意图切片数量统计报告")
    print("="*50)

    # A. 全局统计
    global_counts = Counter()
    for counts in project_slice_counts.values():
        for count in counts:
            if count >= 4:
                global_counts['4+'] += 1
            else:
                global_counts[count] += 1
    
    print("\n--- 1. 总体映射结果统计 ---")
    print("| 切片数量 | 案例总数 | 占比 |")
    print("| :---: | :---: | :---: |")
    
    for i in range(1, 4):
        count = global_counts[i]
        percent = (count / total_cases) * 100 if total_cases > 0 else 0
        print(f"| {i} 个切片 | {count} | {percent:.1f}% |")

    count_4plus = global_counts['4+']
    percent_4plus = (count_4plus / total_cases) * 100 if total_cases > 0 else 0
    print(f"| 4+ 个切片 | {count_4plus} | {percent_4plus:.1f}% |")
    print(f"| **总计** | **{total_cases}** | **100.0%** |")


    # B. 按项目统计
    print("\n--- 2. 按项目切片数量分布 ---")
    header = "| 项目 | 1 切片 | 2 切片 | 3 切片 | 4+ 切片 | 总计 |"
    print(header)
    print("| :---: | :---: | :---: | :---: | :---: | :---: |")
    
    for project, counts in project_slice_counts.items():
        project_counter = Counter()
        for count in counts:
            if count >= 4:
                project_counter['4+'] += 1
            else:
                project_counter[count] += 1

        total_project_cases = len(counts)
        row = [
            project,
            project_counter[1],
            project_counter[2],
            project_counter[3],
            project_counter['4+'],
            total_project_cases
        ]
        print(f"| {' | '.join(map(str, row))} |")


# --- 主程序执行 ---
# 假设您将 analyze_slice_counts.py 放在与 oracle_mapping_analysis_result.txt 同一个目录下
if __name__ == "__main__":
    # 查找文件名
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_name = "oracle_mapping_analysis_result.txt"
    file_path = os.path.join(script_dir, file_name)

    # 如果当前脚本目录下找不到，尝试在当前工作目录下查找
    if not os.path.exists(file_path):
        file_path = os.path.join(os.getcwd(), file_name)

    analyze_slice_mapping_report(file_path)