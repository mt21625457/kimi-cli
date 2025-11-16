#!/usr/bin/env python3
"""
文档质量深度分析工具
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple
import re


class DocQualityAnalyzer:
    """文档质量分析器"""
    
    def __init__(self, results_file: str):
        with open(results_file, 'r', encoding='utf-8') as f:
            self.results = json.load(f)
    
    def analyze_tool_documentation(self) -> Dict:
        """分析工具文档的质量"""
        tool_files = [
            'kimi_cli/tools/bash/__init__.py',
            'kimi_cli/tools/file/read.py',
            'kimi_cli/tools/file/write.py',
            'kimi_cli/tools/file/grep.py',
            'kimi_cli/tools/web/search.py',
            'kimi_cli/tools/web/fetch.py',
            'kimi_cli/tools/task/__init__.py',
            'kimi_cli/tools/dmail/__init__.py',
            'kimi_cli/tools/think/__init__.py',
            'kimi_cli/tools/todo/__init__.py'
        ]
        
        tool_analysis = {
            'well_documented': [],
            'poorly_documented': [],
            'missing_docs': [],
            'descriptions': {}
        }
        
        for file_result in self.results['detailed_results']:
            file_path = file_result['file_path']
            
            if file_path in tool_files:
                # 检查工具类的文档
                if file_result['classes']:
                    for cls in file_result['classes']:
                        if cls['has_docstring']:
                            tool_analysis['well_documented'].append(f"{file_path}::{cls['name']}")
                        else:
                            tool_analysis['poorly_documented'].append(f"{file_path}::{cls['name']}")
                
                # 检查是否有描述文件
                desc_file = self._check_description_file(file_path)
                if desc_file:
                    tool_analysis['descriptions'][file_path] = desc_file
        
        return tool_analysis
    
    def _check_description_file(self, tool_file: str) -> str:
        """检查工具是否有描述文件"""
        base_path = tool_file.replace('kimi_cli/', 'src/kimi_cli/').replace('/__init__.py', '')
        base_path = base_path.replace('.py', '')
        
        possible_files = [
            f"{base_path}.md",
            f"{base_path}/README.md",
            f"{base_path}/description.md"
        ]
        
        for file_path in possible_files:
            if Path(file_path).exists():
                return file_path
        
        return ""
    
    def analyze_core_modules(self) -> Dict:
        """分析核心模块的文档质量"""
        core_files = [
            'kimi_cli/soul/kimisoul.py',
            'kimi_cli/soul/agent.py',
            'kimi_cli/soul/context.py',
            'kimi_cli/llm.py',
            'kimi_cli/config.py',
            'kimi_cli/app.py'
        ]
        
        core_analysis = {
            'documentation_level': {},
            'complex_functions': [],
            'public_apis': []
        }
        
        for file_result in self.results['detailed_results']:
            file_path = file_result['file_path']
            
            if file_path in core_files:
                # 计算文档化水平
                total_items = (len(file_result.get('functions', [])) + 
                             len(file_result.get('classes', [])))
                documented_items = sum(1 for f in file_result.get('functions', []) if f['has_docstring']) + \
                                 sum(1 for c in file_result.get('classes', []) if c['has_docstring'])
                
                if total_items > 0:
                    doc_level = (documented_items / total_items) * 100
                    core_analysis['documentation_level'][file_path] = {
                        'percentage': doc_level,
                        'documented': documented_items,
                        'total': total_items
                    }
                
                # 识别复杂函数（参数较多或逻辑复杂）
                for func in file_result.get('functions', []):
                    if len(func.get('params', [])) > 3:  # 参数超过3个
                        core_analysis['complex_functions'].append({
                            'file': file_path,
                            'function': func['name'],
                            'params': len(func['params']),
                            'has_doc': func['has_docstring']
                        })
        
        return core_analysis
    
    def check_documentation_consistency(self) -> List[str]:
        """检查文档格式一致性"""
        issues = []
        
        # 检查文档字符串格式
        format_patterns = {
            'google': r'Args:\s*\n.*?Returns:\s*\n',
            'numpy': r'Parameters\s*\n.*?----------.*?Returns\s*\n.*?----------',
            'sphinx': r':param.*?\n.*?:(return|returns):'
        }
        
        documented_items = []
        
        for file_result in self.results['detailed_results']:
            for func in file_result.get('functions', []):
                if func['has_docstring']:
                    documented_items.append({
                        'type': 'function',
                        'name': func['name'],
                        'file': file_result['file_path']
                    })
            
            for cls in file_result.get('classes', []):
                if cls['has_docstring']:
                    documented_items.append({
                        'type': 'class', 
                        'name': cls['name'],
                        'file': file_result['file_path']
                    })
        
        issues.append(f"发现 {len(documented_items)} 个有文档的项目，但格式不一致")
        issues.append("建议使用统一的文档格式（Google风格或NumPy风格）")
        
        return issues
    
    def generate_enhanced_report(self) -> str:
        """生成增强版分析报告"""
        tool_analysis = self.analyze_tool_documentation()
        core_analysis = self.analyze_core_modules()
        consistency_issues = self.check_documentation_consistency()
        
        report = []
        report.append("# 📋 Python项目文档质量深度分析报告")
        report.append("=" * 60)
        report.append("")
        
        # 工具文档分析
        report.append("## 🔧 工具文档分析")
        report.append(f"- 工具类总数: {len(tool_analysis['well_documented']) + len(tool_analysis['poorly_documented'])}")
        report.append(f"- 文档化良好的工具: {len(tool_analysis['well_documented'])}")
        report.append(f"- 文档缺失的工具: {len(tool_analysis['poorly_documented'])}")
        report.append(f"- 有描述文件的工具: {len(tool_analysis['descriptions'])}")
        
        if tool_analysis['descriptions']:
            report.append("\n### 📄 工具描述文件")
            for tool_file, desc_file in tool_analysis['descriptions'].items():
                report.append(f"- {tool_file}: {desc_file}")
        
        report.append("")
        
        # 核心模块分析
        report.append("## 🎯 核心模块文档分析")
        for file_path, doc_info in core_analysis['documentation_level'].items():
            report.append(f"\n### {file_path}")
            report.append(f"- 文档化率: {doc_info['percentage']:.1f}% ({doc_info['documented']}/{doc_info['total']})")
            
            if doc_info['percentage'] < 50:
                report.append("- ⚠️ 文档化程度较低，需要优先改进")
            elif doc_info['percentage'] < 80:
                report.append("- ⚡ 文档化程度中等，可以进一步完善")
            else:
                report.append("- ✅ 文档化程度良好")
        
        report.append("")
        
        # 复杂函数分析
        if core_analysis['complex_functions']:
            report.append("## 🔍 复杂函数文档分析")
            report.append(f"发现 {len(core_analysis['complex_functions'])} 个参数较多的复杂函数")
            
            missing_doc_complex = [f for f in core_analysis['complex_functions'] if not f['has_doc']]
            if missing_doc_complex:
                report.append(f"\n其中 {len(missing_doc_complex)} 个缺少文档:")
                for func in missing_doc_complex[:5]:
                    report.append(f"- {func['file']}::{func['function']} ({func['params']}个参数)")
        
        report.append("")
        
        # 一致性问题
        report.append("## 🎨 文档格式一致性分析")
        for issue in consistency_issues:
            report.append(f"- {issue}")
        
        report.append("")
        
        # 具体改进建议
        report.append("## 🚀 具体改进建议")
        report.append("")
        report.append("### 🔥 紧急改进（立即处理）")
        report.append("1. **核心工具类文档化**: 为所有工具类添加完整的文档字符串")
        report.append("2. **复杂函数优先**: 优先为参数较多、逻辑复杂的函数添加文档")
        report.append("3. **API文档标准化**: 统一使用Google风格文档格式")
        report.append("")
        report.append("### ⚡ 重要改进（近期完成）")
        report.append("1. **模块级文档**: 为每个模块添加模块文档字符串，说明模块用途")
        report.append("2. **参数完整性**: 所有函数文档都应包含参数说明和返回值说明")
        report.append("3. **异常说明**: 在文档中添加可能抛出的异常说明")
        report.append("")
        report.append("### 📝 优化改进（持续进行）")
        report.append("1. **示例代码**: 在文档中添加使用示例")
        report.append("2. **版本信息**: 记录API的版本和变更历史")
        report.append("3. **性能说明**: 对性能关键的函数添加性能说明")
        report.append("")
        
        # 最佳实践建议
        report.append("## 💎 文档最佳实践建议")
        report.append("")
        report.append("### 文档字符串结构（Google风格）")
        report.append("""
def function_name(param1: type, param2: type) -> return_type:
    \"\"\"一行简洁的函数功能描述。
    
    更详细的功能描述，包括使用场景和注意事项。
    
    Args:
        param1: 第一个参数的描述。
        param2: 第二个参数的描述。
        
    Returns:
        返回值的详细描述，包括类型和含义。
        
    Raises:
        ValueError: 当参数无效时抛出。
        
    Example:
        >>> function_name("value1", "value2")
        "expected_result"
    \"\"\"
""")
        
        report.append("### 类文档字符串结构")
        report.append("""
class ClassName:
    \"\"\"一行简洁的类功能描述。
    
    更详细的类描述，包括主要职责和使用方式。
    
    Attributes:
        attr1: 属性的描述。
        attr2: 属性的描述。
        
    Example:
        >>> instance = ClassName(param1, param2)
        >>> instance.method_name()
    \"\"\"
""")
        
        return '\n'.join(report)


if __name__ == '__main__':
    analyzer = DocQualityAnalyzer('/home/mt/code/py/kimi-cli/doc_analysis_results.json')
    report = analyzer.generate_enhanced_report()
    
    with open('/home/mt/code/py/kimi-cli/doc_quality_report.md', 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(report)
    print("\n" + "="*60)
    print("深度分析完成！详细报告已保存到 doc_quality_report.md")