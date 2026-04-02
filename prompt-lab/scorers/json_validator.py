#!/usr/bin/env python3
"""
JSON 输出格式评分器 — 确定性评分
用法: python3 json_validator.py <output_file> <schema_file>
"""
import json
import sys
import re

def extract_json(text):
    """从文本中提取 JSON（处理 markdown code block）"""
    # 尝试直接解析
    try:
        return json.loads(text), True
    except json.JSONDecodeError:
        pass
    
    # 尝试提取 ```json ... ``` 块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1)), False
        except json.JSONDecodeError:
            pass
    
    # 尝试找到 { ... } 块
    match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1)), False
        except json.JSONDecodeError:
            pass
    
    return None, False

def validate_schema(data, schema):
    """验证数据是否符合 schema"""
    errors = []
    
    # 检查必需字段
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # 检查字段类型
    properties = schema.get("properties", {})
    for field, rules in properties.items():
        if field not in data:
            continue
        
        expected_type = rules.get("type")
        value = data[field]
        
        type_map = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        if expected_type and not isinstance(value, type_map.get(expected_type, object)):
            errors.append(f"Field '{field}': expected {expected_type}, got {type(value).__name__}")
        
        # 数值范围检查
        if expected_type == "number":
            if "minimum" in rules and value < rules["minimum"]:
                errors.append(f"Field '{field}': {value} < minimum {rules['minimum']}")
            if "maximum" in rules and value > rules["maximum"]:
                errors.append(f"Field '{field}': {value} > maximum {rules['maximum']}")
        
        # 枚举检查
        if "enum" in rules and value not in rules["enum"]:
            errors.append(f"Field '{field}': '{value}' not in enum {rules['enum']}")
    
    return errors

def score(output_text, schema):
    """评分主函数"""
    result = {
        "is_valid_json": False,
        "is_pure_json": False,
        "schema_valid": False,
        "errors": [],
        "score": 0,
    }
    
    data, is_pure = extract_json(output_text)
    
    if data is None:
        result["errors"].append("Could not extract JSON from output")
        return result
    
    result["is_valid_json"] = True
    result["is_pure_json"] = is_pure
    result["score"] = 1  # 基础分：有效 JSON
    
    if is_pure:
        result["score"] += 1  # 加分：纯 JSON，无多余内容
    
    schema_errors = validate_schema(data, schema)
    if not schema_errors:
        result["schema_valid"] = True
        result["score"] += 2  # 加分：schema 匹配
    else:
        result["errors"] = schema_errors
    
    # 总分 4 分制
    # 4 = 纯 JSON + schema 匹配
    # 3 = JSON + schema 匹配（有额外文本）
    # 2 = 有效 JSON 但 schema 不匹配
    # 1 = 能提取出 JSON
    # 0 = 无法提取 JSON
    
    return result

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 json_validator.py <output_file> <schema_file>")
        sys.exit(1)
    
    with open(sys.argv[1]) as f:
        output_text = f.read()
    
    with open(sys.argv[2]) as f:
        schema = json.load(f)
    
    result = score(output_text, schema)
    print(json.dumps(result, indent=2, ensure_ascii=False))
