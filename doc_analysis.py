#!/usr/bin/env python3
"""
文档分析工具 - 分析Python项目的文档完整性和质量
"""

import ast
import os
from pathlib import Path
from typing import Dict, List, Tuple, Set
import json
from collections import defaultdict


class DocAnalyzer:
    """Python文档分析器"""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.results = {
            'total_files': 0,
            'total_functions': 0,
            'total_classes': 0,
            'doc_coverage': {
                'modules': 0,
                'functions': 0,
                'classes': 0,
                'methods': 0
            },
            'detailed_results': [],
            'missing_docs': [],
            'quality_issues': []
        }
    
    def analyze_file(self, file_path: Path) -> Dict:
        """分析单个Python文件的文档情况"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            file_result = {
                'file_path': str(file_path.relative_to(self.project_path)),
                'module_doc': bool(ast.get_docstring(tree)),
                'functions': [],
                'classes': [],
                'missing_docs': [],
                'quality_issues': []
            }
            
            # 分析模块级文档
            if not file_result['module_doc']:
                file_result['missing_docs'].append(('module', file_path.name))
            
            # 分析函数和类
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._analyze_function(node, file_result, file_path)
                elif isinstance(node, ast.ClassDef):
                    self._analyze_class(node, file_result, file_path)
            
            return file_result
            
        except Exception as e:
            return {
                'file_path': str(file_path.relative_to(self.project_path)),
                'error': str(e)
            }
    
    def _analyze_function(self, node: ast.FunctionDef, file_result: Dict, file_path: Path):
        """分析函数的文档情况"""
        func_info = {
            'name': node.name,
            'has_docstring': bool(ast.get_docstring(node)),
            'is_method': False,
            'line_number': node.lineno,
            'params': [arg.arg for arg in node.args.args],
            'returns': bool(node.returns)
        }
        
        file_result['functions'].append(func_info)
        
        if not func_info['has_docstring']:
            file_result['missing_docs'].append(
                ('function', f"{node.name} (line {node.lineno})")
            )
        else:
            # 检查文档质量
            docstring = ast.get_docstring(node)
            quality_issues = self._check_docstring_quality(docstring, node.name, 'function')
            file_result['quality_issues'].extend(quality_issues)
    
    def _analyze_class(self, node: ast.ClassDef, file_result: Dict, file_path: Path):
        """分析类的文档情况"""
        class_info = {
            'name': node.name,
            'has_docstring': bool(ast.get_docstring(node)),
            'line_number': node.lineno,
            'methods': [],
            'bases': [base.id if hasattr(base, 'id') else str(ast.dump(base)) 
                     for base in node.bases]
        }
        
        # 分析类的方法
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_info = {
                    'name': item.name,
                    'has_docstring': bool(ast.get_docstring(item)),
                    'line_number': item.lineno,
                    'params': [arg.arg for arg in item.args.args]
                }
                class_info['methods'].append(method_info)
                
                if not method_info['has_docstring']:
                    file_result['missing_docs'].append(
                        ('method', f"{node.name}.{item.name} (line {item.lineno})")
                    )
        
        file_result['classes'].append(class_info)
        
        if not class_info['has_docstring']:
            file_result['missing_docs'].append(
                ('class', f"{node.name} (line {node.lineno})")
            )
        else:
            # 检查类文档质量
            docstring = ast.get_docstring(node)
            quality_issues = self._check_docstring_quality(docstring, node.name, 'class')
            file_result['quality_issues'].extend(quality_issues)
    
    def _check_docstring_quality(self, docstring: str, name: str, doc_type: str) -> List[str]:
        """检查文档字符串的质量"""
        issues = []
        
        if not docstring:
            return issues
        
        # 检查长度
        if len(docstring.strip()) < 10:
            issues.append(f"{doc_type.title()} '{name}' 的文档字符串太短 (少于10个字符)")
        
        # 检查是否包含参数说明（对于函数和方法）
        if doc_type in ['function', 'method']:
            if 'Args:' not in docstring and '参数' not in docstring:
                issues.append(f"{doc_type.title()} '{name}' 的文档缺少参数说明")
            
            if 'Returns:' not in docstring and '返回' not in docstring:
                issues.append(f"{doc_type.title()} '{name}' 的文档缺少返回值说明")
        
        # 检查格式一致性
        lines = docstring.strip().split('\n')
        if len(lines) > 1:
            # 检查是否使用三重引号
            if not docstring.startswith('"""') or not docstring.endswith('"""'):
                issues.append(f"{doc_type.title()} '{name}' 的文档字符串格式不规范")
        
        return issues
    
    def run_analysis(self):
        """运行完整的文档分析"""
        python_files = list(self.project_path.rglob('*.py'))
        self.results['total_files'] = len(python_files)
        
        for file_path in python_files:
            if 'venv' in str(file_path) or '__pycache__' in str(file_path):
                continue
                
            file_result = self.analyze_file(file_path)
            self.results['detailed_results'].append(file_result)
            
            # 统计总数
            if 'error' not in file_result:
                self.results['total_functions'] += len(file_result['functions'])
                self.results['total_classes'] += len(file_result['classes'])
                
                # 统计文档覆盖率
                if file_result['module_doc']:
                    self.results['doc_coverage']['modules'] += 1
                
                for func in file_result['functions']:
                    if func['has_docstring']:
                        self.results['doc_coverage']['functions'] += 1
                
                for cls in file_result['classes']:
                    if cls['has_docstring']:
                        self.results['doc_coverage']['classes'] += 1
                    
                    for method in cls['methods']:
                        if method['has_docstring']:
                            self.results['doc_coverage']['methods'] += 1
                
                # 收集缺失文档和质量问题的详细信息
                for missing in file_result['missing_docs']:
                    self.results['missing_docs'].append({
                        'file': file_result['file_path'],
                        'type': missing[0],
                        'name': missing[1]
                    })
                
                for issue in file_result['quality_issues']:
                    self.results['quality_issues'].append({
                        'file': file_result['file_path'],
                        'issue': issue
                    })
    
    def generate_report(self) -> str:
        """生成分析报告"""
        report = []
        report.append("# Python项目文档完整性分析报告")
        report.append("=" * 50)
        report.append("")
        
        # 总体统计
        report.append("## 📊 总体统计")
        report.append(f"- 总文件数: {self.results['total_files']}")
        report.append(f"- 总函数数: {self.results['total_functions']}")
        report.append(f"- 总类数: {self.results['total_classes']}")
        report.append("")
        
        # 文档覆盖率
        report.append("## 📈 文档覆盖率")
        
        if self.results['total_files'] > 0:
            module_coverage = (self.results['doc_coverage']['modules'] / self.results['total_files']) * 100
            report.append(f"- 模块文档覆盖率: {module_coverage:.1f}% ({self.results['doc_coverage']['modules']}/{self.results['total_files']})")
        
        if self.results['total_functions'] > 0:
            func_coverage = (self.results['doc_coverage']['functions'] / self.results['total_functions']) * 100
            report.append(f"- 函数文档覆盖率: {func_coverage:.1f}% ({self.results['doc_coverage']['functions']}/{self.results['total_functions']})")
        
        if self.results['total_classes'] > 0:
            class_coverage = (self.results['doc_coverage']['classes'] / self.results['total_classes']) * 100
            report.append(f"- 类文档覆盖率: {class_coverage:.1f}% ({self.results['doc_coverage']['classes']}/{self.results['total_classes']})")
        
        # 方法覆盖率需要单独计算
        total_methods = sum(len(cls.get('methods', [])) 
                           for file_result in self.results['detailed_results'] 
                           for cls in file_result.get('classes', []))
        
        if total_methods > 0:
            method_coverage = (self.results['doc_coverage']['methods'] / total_methods) * 100
            report.append(f"- 方法文档覆盖率: {method_coverage:.1f}% ({self.results['doc_coverage']['methods']}/{total_methods})")
        
        report.append("")
        
        # 关键缺失文档
        report.append("## 🚨 关键缺失文档")
        
        # 按文件分组显示缺失文档
        missing_by_file = defaultdict(list)
        for missing in self.results['missing_docs']:
            missing_by_file[missing['file']].append(missing)
        
        for file_path, missing_items in missing_by_file.items():
            if len(missing_items) > 3:  # 只显示缺失较多的文件
                report.append(f"\n### {file_path}")
                for item in missing_items[:5]:  # 限制显示数量
                    report.append(f"- {item['type']}: {item['name']}")
                if len(missing_items) > 5:
                    report.append(f"- ... 还有 {len(missing_items) - 5} 个缺失项")
        
        report.append("")
        
        # 文档质量问题
        if self.results['quality_issues']:
            report.append("## ⚠️ 文档质量问题")
            
            # 按问题类型分组
            issues_by_type = defaultdict(list)
            for issue in self.results['quality_issues']:
                issue_type = issue['issue'].split(':')[0].split(' ')[-1]
                issues_by_type[issue_type].append(issue)
            
            for issue_type, issues in issues_by_type.items():
                report.append(f"\n### {issue_type} 相关问题 ({len(issues)}个)")
                for issue in issues[:3]:  # 限制显示数量
                    report.append(f"- {issue['file']}: {issue['issue']}")
                if len(issues) > 3:
                    report.append(f"- ... 还有 {len(issues) - 3} 个类似问题")
        
        report.append("")
        
        # 改进建议
        report.append("## 💡 改进建议")
        report.append("")
        report.append("### 高优先级")
        report.append("1. **核心模块文档化**: 为主要的工具类和核心算法添加文档字符串")
        report.append("2. **API文档完善**: 所有公共函数和类都应该有清晰的文档说明")
        report.append("3. **参数和返回值说明**: 函数文档应包含参数说明和返回值说明")
        report.append("")
        report.append("### 中优先级")
        report.append("1. **模块级文档**: 为每个Python模块添加模块文档字符串")
        report.append("2. **复杂逻辑注释**: 为算法实现添加详细的行内注释")
        report.append("3. **示例代码**: 在文档中添加使用示例")
        report.append("")
        report.append("### 低优先级")
        report.append("1. **文档格式统一**: 统一使用Google风格或NumPy风格的文档格式")
        report.append("2. **类型提示文档**: 结合类型提示提供更完整的文档")
        report.append("3. **版本信息**: 在文档中添加版本和变更信息")
        
        return '\n'.join(report)


if __name__ == '__main__':
    # 运行分析
    analyzer = DocAnalyzer('/home/mt/code/py/kimi-cli/src')
    analyzer.run_analysis()
    
    # 生成报告
    report = analyzer.generate_report()
    print(report)
    
    # 保存详细结果到JSON文件
    with open('/home/mt/code/py/kimi-cli/doc_analysis_results.json', 'w', encoding='utf-8') as f:
        json.dump(analyzer.results, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*50)
    print("分析完成！详细结果已保存到 doc_analysis_results.json")