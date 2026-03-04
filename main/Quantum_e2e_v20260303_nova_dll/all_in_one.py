import pandas as pd
import sys
import os
import argparse
from overall_checkv3 import *
from memory_retrieval_judge import *
from KB_retrieval_judge import *
from excel_colored import *
from summary_v12 import *
import datetime
import Auto_Judge
from pathlib import Path
from summary_local import generate_summary


def reorder_dataframe_columns(df, desired_order):
    """
    安全地重新排序 DataFrame 列，处理缺失的列
    
    Args:
        df: 原始 DataFrame
        desired_order: 期望的列顺序列表
    
    Returns:
        重新排序后的 DataFrame
    """
    # 获取实际存在的列
    existing_cols = df.columns.tolist()
    
    # 筛选出实际存在的列，保持期望的顺序
    valid_order = [col for col in desired_order if col in existing_cols]
    
    # 找出不在期望顺序中但存在于 DataFrame 的列
    extra_cols = [col for col in existing_cols if col not in desired_order]
    
    # 合并：期望顺序的列 + 额外的列
    final_order = valid_order + extra_cols
    
    # 打印信息
    missing_cols = [col for col in desired_order if col not in existing_cols]
    if missing_cols:
        print(f"警告: 以下列不存在于 DataFrame 中: {missing_cols}")
    
    if extra_cols:
        print(f"提示: 以下列不在期望顺序中，已添加到末尾: {extra_cols}")
    
    return df[final_order]




def step_accuracy_check(input_path, output_path):
    """
    步骤2: 执行精度检查
    """
    print("" + "="*60)
    print("步骤2: 精度检查")
    print("="*60)
    
    try:
        df = get_check_result(input_path, output_path)
        print("✓ 精度检查完成")
        return True
    except Exception as e:
        print(f"✗ 精度检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_memory_retrieval_judge(input_path, output_path):
    """
    步骤3: 执行Memory Retrieval判决
    """
    print("" + "="*60)      
    print("步骤3: Memory Retrieval判决")
    print("="*60)
    
    try:
        # 配置参数
        AZURE_ENDPOINT = "https://llm-east-us2-test.openai.azure.com/"
        AZURE_KEY = "A5eBgaB3ypK7FLLGApu6RPtUM1iziQ4CDYNDRtdUvn3JMayubDd2JQQJ99BIACHYHv6XJ3w3AAABACOGNvvY"
        DEPLOYMENT_NAME = "gpt-4.1"
        
        # 创建验证器实例
        memory_retrieval_judge = MemoryRetrievalJudge(
            azure_endpoint=AZURE_ENDPOINT,
            azure_key=AZURE_KEY,
            deployment_name=DEPLOYMENT_NAME,
            max_workers=32,
            request_delay=0.1
        )
        
        # 执行验证
        memory_retrieval_stats = memory_retrieval_judge.verify_excel(
            input_path=input_path,
            output_path=output_path,
            question_col="question",
            gt_col="answer",
            pred_col="MemoryRetrievalTop3",
            dimension_col="dimension"
        )
        
        # 打印统计结果
        print(f"✓ Memory Retrieval判决完成！")
        print(f"  总数据量: {memory_retrieval_stats['total']}")
        print(f"  Memory域数据量: {memory_retrieval_stats['memory_total']}")
        print(f"  Memory域通过数: {memory_retrieval_stats['pass_count']}")
        print(f"  Memory域通过率: {memory_retrieval_stats['pass_ratio']:.2%}")
        
        return memory_retrieval_stats
    except Exception as e:
        print(f"✗ Memory Retrieval判决失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def step_kb_retrieval_judge(input_path, output_path):
    """
    步骤4: 执行KB Retrieval判决
    """
    print("" + "="*60)
    print("步骤4: KB Retrieval判决")
    print("="*60)
    
    try:
        evaluator = KBRetrievalEvaluator(max_workers=32)
        
        # 执行评估，scene_filter为'kbqa'或者'Kbqa'
        kb_result_df = evaluator.evaluate_excel(
            input_excel=input_path,
            output_excel=output_path,
            topk=3,
            scene_filter_list=['kbqa', 'Kbqa']
        )
        
        # 获取统计信息
        kb_stats = evaluator.get_statistics(kb_result_df, scene_filter_list=['kbqa', 'Kbqa'])
        
        print("✓ KB Retrieval判决完成！")
        print("  评估统计信息:")
        for key, value in kb_stats.items():
            print(f"  {key}: {value}")
        
        return kb_result_df, kb_stats
    except Exception as e:
        print(f"✗ KB Retrieval判决失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def step_finalize_results(input_path, output_final_path):
    """
    步骤5: 整理最终结果
    """
    print("" + "="*60)
    print("步骤5: 整理最终结果")
    print("="*60)
    
    try:
        df = pd.read_excel(input_path, engine="openpyxl")
        
        # 第一次排序
        cols = df.columns.tolist()
        print(f"原始列数量: {len(cols)}")
        
        desired_order_1 = [
            'question', 'domain', 'scene', 'secondary', 'pathlist', 'answer', 
            'domain_label', 'intent_mapping_label', 'intent_recognition_label', 'slot_label', 
            'result', 'response_time', 'data_json_list',
            'start_time', 'end_time', 'first_word_time', 'first_text_response_time', 
            'ttft', 'token_count', 'generation_speed', 
            'gt', 'diamond', 'Reason', 'pass', 'gt_text', 'gt_file',
            'trace_id', 'trace_start_time', 'trace_end_time', 'source_file', 'span_count',
            'DOMAIN', 'CURRENT_INTENT_MAPPING', 'CURRENT_INTENT_RECOGNITION', 
            'NEED_REWRITE', 'REWRITE_QUERY', 'FINAL_ANSWER', 'LOCAL_TOOL_RETURN', 
            'MemoryRetrievalTop3', 'search_start_time', 'search_end_time', 'search_gap_time', 
            'search_query', 'search_file_list', 'search_text_list',
            'domain_check', 'DomainClassifierNode', 'RewriteJudgeNode', 
            'mapping_check', 'IntentMappingNode', 'intent_check', 
            'slot_Result', 'slot_Correct_Count', 'slot_Error_Reasons', 'IntentUnderstandingNode',
            'tool_check', 'TaskExecutionNode', 'LocalGreetingNode', 
            'memoryRetrieval_check', 'memoryRetrieval_reason', 'SearchMemory', 
            'kbRetrieval_check', 
            'SearchKnowledge', 'GenerateDuration', 'Unknown', 'Result', 'LocalGraph', 'GeneralGenerationNode'
        ]
        
        df = reorder_dataframe_columns(df, desired_order_1)
        df.to_excel(output_final_path, index=False, engine="openpyxl")
        
        # 第二次排序（判决结果在最后）
        df = pd.read_excel(output_final_path, engine="openpyxl")
        
        desired_order_2 = [
            'question', 'domain', 'scene', 'secondary', 'pathlist', 'answer', 
            'domain_label', 'intent_mapping_label', 'intent_recognition_label', 'slot_label', 
            'result', 'response_time', 'data_json_list', 
            'start_time', 'end_time', 'first_word_time', 'first_text_response_time', 
            'ttft', 'token_count', 'generation_speed', 
            'gt', 'diamond', 'Reason', 'pass', 'gt_text', 'gt_file', 
            'trace_id', 'trace_start_time', 'trace_end_time', 'source_file', 'span_count', 
            'DOMAIN', 'CURRENT_INTENT_MAPPING', 'CURRENT_INTENT_RECOGNITION', 
            'NEED_REWRITE', 'REWRITE_QUERY', 'FINAL_ANSWER', 'LOCAL_TOOL_RETURN', 
            'MemoryRetrievalTop3', 'search_start_time', 'search_end_time', 'search_gap_time', 
            'search_query', 'search_file_list', 'search_text_list', 
            'DomainClassifierNode', 'RewriteJudgeNode', 'IntentMappingNode', 
            'IntentUnderstandingNode', 'TaskExecutionNode', 'LocalGreetingNode', 
            'SearchMemory', 'SearchKnowledge', 'GenerateDuration', 'Unknown', 
            'LocalGraph', 'GeneralGenerationNode', 
            'slot_Correct_Count', 'slot_Error_Reasons', 'memoryRetrieval_reason',
            'domain_check', 'mapping_check', 'intent_check', 'slot_Result', 
            'tool_check', 'memoryRetrieval_check', 'kbRetrieval_check', 
            'Result'
        ]
        
        df = reorder_dataframe_columns(df, desired_order_2)
        
        # 重命名列
        column_rename_map = {
            'domain_check': 'Domain Classifier',
            'mapping_check': 'Intent Mapping',
            'intent_check': 'Intent Recognition',
            'slot_Result': 'Slot Extraction',
            'tool_check': 'Tool Execution',
            'memoryRetrieval_check': 'Memory Retrieval',
            'kbRetrieval_check': 'Knowledge Retrieval',
            'Result': 'Final Answer'
        }
        
        df = df.rename(columns=column_rename_map)
        
        # 按domain和secondary排序
        df = df.sort_values(by=['domain', 'secondary'])
        
        # 保存重新排序的结果
        output_reordered_path = output_final_path.replace("_Final.xlsx", "_Final_reordered.xlsx")
        df.to_excel(output_reordered_path, index=False, engine="openpyxl")
        
        print(f"✓ 最终结果整理完成")
        print(f"  输出文件: {output_reordered_path}")
        
        return output_reordered_path
    except Exception as e:
        print(f"✗ 整理最终结果失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def step_generate_summary(input_path, output_path):
    """
    步骤6: 生成汇总表格
    """
    print("" + "="*60)
    print("步骤6: 生成汇总表格")
    print("="*60)
    
    try:
        summarize(input_path, output_path)
        print(f"✓ 汇总表格生成完成")
        print(f"  输出文件: {output_path}")
        return True
    except Exception as e:
        print(f"✗ 生成汇总表格失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_format_excel(input_path, output_path):
    """
    步骤7: Excel着色格式化
    """
    print("" + "="*60)
    print("步骤7: Excel着色格式化")
    print("="*60)
    
    try:
        excel_formatter = ExcelStyleFormatter()
        df_result = excel_formatter.format_excel(
            input_path=input_path,
            output_path=output_path,
            primary_sort_columns=['domain', 'secondary']
        )
        print(f"✓ Excel格式化完成")
        print(f"  输出文件: {output_path}")
        return df_result
    except Exception as e:
        print(f"✗ Excel格式化失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def process_pipeline(input_excel_path, result_dir, modules=['all']):
    """
    主处理流程，根据modules参数执行相应的模块
    
    Args:
        input_excel_path: 输入Excel路径
        result_dir: 结果输出目录
        modules: 要执行的模块列表，可选值: ['KBQA', 'Memory', 'other', 'all']
    """
    # 规范化modules参数
    if isinstance(modules, str):
        modules = [modules]
    
    modules = [m.lower() for m in modules]
    
    if 'all' in modules:
        modules = ['kbqa', 'memory', 'other']
    
    print("" + "="*60)
    print("处理流程配置")
    print("="*60)
    print(f"执行模块: {modules}")
    print(f"输入文件: {input_excel_path}")
    print(f"结果目录: {result_dir}")
    
    # 定义输出文件路径
    
    output_predeal_path = os.path.join(result_dir, os.path.basename(input_excel_path).replace(".xlsx", "_predeal.xlsx"))

    output_check_path = os.path.join(result_dir, os.path.basename(input_excel_path).replace(".xlsx", "_check.xlsx"))
    output_memory_check_path = os.path.join(result_dir, os.path.basename(input_excel_path).replace(".xlsx", "_memory_retrieval_check.xlsx"))
    output_kb_check_path = os.path.join(result_dir, os.path.basename(input_excel_path).replace(".xlsx", "_kb_retrieval_check.xlsx"))
    output_final_path = os.path.join(result_dir, os.path.basename(input_excel_path).replace(".xlsx", "_Final.xlsx"))
    
    # 步骤0：将Result列的1全部替换为pass，0全部替换为fail
    df_initial = pd.read_excel(input_excel_path, engine="openpyxl")
    if 'Result' in df_initial.columns:
        df_initial['Result'] = df_initial['Result'].replace({1: 'pass', 0: 'fail'})
        df_initial.to_excel(output_predeal_path, index=False, engine="openpyxl")
    else:
        print("警告: 输入文件中未找到'Result'列，跳过步骤0的替换操作。")
        df_initial.to_excel(output_predeal_path, index=False, engine="openpyxl")
    
    
    # 步骤2: 精度检查（所有模块都需要）
    if not step_accuracy_check(output_predeal_path, output_check_path):
        print("✗ 精度检查失败，继续流程")
        
    
    # 当前处理的文件路径
    current_input = output_check_path
    
    # 步骤3: Memory Retrieval判决
    if 'memory' in modules:
        memory_stats = step_memory_retrieval_judge(current_input, output_memory_check_path)
        if memory_stats:
            current_input = output_memory_check_path
        else:
            print("⚠ Memory Retrieval判决失败，使用上一步的输出继续")
    else:
        print("⏭ 跳过 Memory Retrieval判决")
        # 如果不执行Memory判决，直接复制文件
        import shutil
        shutil.copy(current_input, output_memory_check_path)
        current_input = output_memory_check_path
    
    # 步骤4: KB Retrieval判决
    if 'kbqa' in modules:
        kb_result_df, kb_stats = step_kb_retrieval_judge(current_input, output_kb_check_path)
        if kb_result_df is not None:
            current_input = output_kb_check_path
        else:
            print("⚠ KB Retrieval判决失败，使用上一步的输出继续")
    else:
        print("⏭ 跳过 KB Retrieval判决")
        # 如果不执行KB判决，直接复制文件
        import shutil
        shutil.copy(current_input, output_kb_check_path)
        current_input = output_kb_check_path
    
    # 步骤5-7: 其他通用处理
    # 步骤5: 整理最终结果
    output_reordered_path = step_finalize_results(current_input, output_final_path)
    if not output_reordered_path:
        print("✗ 整理最终结果失败，继续流程")
        
    
    # 步骤6: 生成汇总
    output_summary_path = output_final_path.replace("_Final.xlsx", "_summary.xlsx")
    step_generate_summary(output_final_path, output_summary_path)
    
    # 步骤7: Excel格式化
    output_styled_path = output_final_path.replace("_Final.xlsx", "_Final_styled.xlsx")
    step_format_excel(output_reordered_path, output_styled_path)
    
    print("" + "="*60)
    print("✓ 处理流程完成！")
    print("="*60)
    print(f"结果保存在: {result_dir}")
    
    # 步骤8: 生成结果分析报告
    # 调用
    result_path = generate_summary(
        input_file=output_summary_path,
        output_file=output_final_path.replace("_Final.xlsx", "_SummaryLocal.xlsx")
    )

    print(f"文件已保存到：{result_path}")
    
    return True


def parse_arguments():
    """
    解析命令行参数
    """
    parser = argparse.ArgumentParser(
        description='日志分析和数据处理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用根文件夹路径（推荐）
  python script.py --root-folder /path/to/folder --modules all
  
  # 手动指定所有路径
  python script.py --log-path logs/ --input test.xlsx --modules all
  
  # 只执行Memory模块
  python script.py --root-folder /path/to/folder --modules memory
  
  # 执行多个模块
  python script.py --root-folder /path/to/folder --modules memory,kbqa
  
  # 指定输出目录
  python script.py --root-folder /path/to/folder --output-dir results/ --modules all
        """
    )
    
    # 根文件夹参数（新增）
    parser.add_argument(
        '--root_folder', '-rf',
        required=True,
        default=None,
        help='根文件夹路径，将自动查找日志、输入文件和注册文件'
    )
        
    parser.add_argument(
        '--modules', '-m',
        default='all',
        help='要执行的模块，可选: all, kbqa, memory, other，多个模块用逗号分隔（默认: all）'
    )
    
    parser.add_argument(
        '--output_dir', '-o',
        default=None,
        help='输出目录路径（默认: 自动生成带时间戳的目录）'
    )
    parser.add_argument(
        '--test_mode', '-t',
        default="local",
        help='测试模式标志（默认: local）,cloud表示云端测试，local表示本地测试'
    )
    return parser.parse_args()


def main():
    """
    主函数
    """
    # 解析命令行参数
    args = parse_arguments()
    

    # 使用root-folder模式
    root_folder = Path(args.root_folder)
    
    if not os.path.exists(root_folder):
        print(f"❌ 错误: 根文件夹不存在: {root_folder}")
        sys.exit(1)
    
    input_excel_path = ''
    
    if args.test_mode == "cloud":
        excel_files = []
        for f in os.listdir(os.path.join(root_folder,"testresult")):
            if f.startswith("test") and f.endswith(".xlsx"):
                print(f"Found file: {f}")
                excel_files.append(os.path.join(root_folder,"testresult",f))
        Auto_Judge.run(doc_dir='.', out_dir=root_folder, excel_files=excel_files, test_mode=args.test_mode)
            
        print("云端测试模式，结束程序")
        sys.exit(0)
        
        
    excel_files = []
        
    for f in os.listdir(os.path.join(root_folder,"Results")):
        if f.startswith("test") and f.endswith(".xlsx"):
            print(f"Found file: {f}")
            excel_files.append(os.path.join(root_folder,"Results",f))
            break
    Auto_Judge.run(doc_dir='.', out_dir=root_folder, excel_files=excel_files, test_mode=args.test_mode)
    
    for f in os.listdir(os.path.join(root_folder,"judge_results")):
        if f.startswith("test") and f.endswith(".xlsx"):
            print(f"Found file: {f}")
            input_excel_path = os.path.join(root_folder,"judge_results",f)
            break

        
    # 解析模块参数
    modules = [m.strip() for m in args.modules.split(',')]
    
    # 创建结果目录
    if args.output_dir:
        result_dir = args.output_dir
    else:
        # 如果使用root-folder，在root-folder下创建Results目录
        if args.root_folder:
            base_dir = args.root_folder
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        result_dir = os.path.join(base_dir, f"Results")
    
    os.makedirs(result_dir, exist_ok=True)
    
    # 执行处理流程
    success = process_pipeline(
        input_excel_path=input_excel_path,
        result_dir=result_dir,
        modules=modules
    )
    
    if success:
        print("🎉 所有任务执行成功！")
    else:
        print("❌ 部分任务执行失败，请检查日志")
        sys.exit(1)


# 主程序
if __name__ == '__main__':
    main()