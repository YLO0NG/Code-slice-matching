import os
import json
from openai import OpenAI

# ================= 配置区 =================
# 确保这些文件名与你本地保存的文件名一致
ORACLE_FILE = "test/JHotDraw5.2_oracle_methods.json"
CONTEXT_FILE = "test/context_CH.ifa.draw.standard.PasteCommand_execute__.json"
PROMPT_TEMPLATE_FILE = "test/prompt.txt"

TARGET_CLASS = "CH.ifa.draw.standard.PasteCommand"
TARGET_FUNCTION = "execute()"
# ==========================================

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_text(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def run_single_analysis():
    print(f"开始分析方法: {TARGET_CLASS}::{TARGET_FUNCTION}...")

    # 1. 加载数据
    oracle_data = load_json(ORACLE_FILE)
    context_data = load_json(CONTEXT_FILE)
    prompt_template = load_text(PROMPT_TEMPLATE_FILE)

    # 2. 从 Oracle 中筛选目标方法
    focal_method = next(
        (m for m in oracle_data if m['class_name'] == TARGET_CLASS and m['function_name'] == TARGET_FUNCTION), 
        None
    )

    if not focal_method:
        print(f"错误: 在 {ORACLE_FILE} 中找不到目标方法。")
        return

    # 3. 构造最终的 Prompt
    # 按照 prompt.txt 的占位符进行替换
    final_prompt = prompt_template.replace("{{ focal method }}", json.dumps(focal_method, indent=2))
    final_prompt = final_prompt.replace("{{ dependencies }}", json.dumps(context_data, indent=2))

    # 4. 调用 OpenAI API
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

        # 5. 输出结果
        print("\n" + "="*50)
        print("LLM 分析结果:")
        print("="*50)
        print(content)

        # 6. 保存到文件
        output_filename = f"analysis_result_{TARGET_CLASS.split('.')[-1]}.md"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n结果已保存至: {output_filename}")

    except Exception as e:
        print(f"调用 API 失败: {e}")

if __name__ == "__main__":
    run_single_analysis()