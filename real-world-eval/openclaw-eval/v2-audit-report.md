# OpenClaw System Prompt v2 审计

## 8 Pattern 评分

| Pattern | v1 原版 | v2 改进 | 变化 |
|:---|:---:|:---:|:---:|
| 1. Identity Anchor | 2/5 | 4/5 | +2 加了能力定位 |
| 2. Red Line Declaration | 3/5 | 4/5 | +1 显式安全规则 |
| 3. Preference Chain | 3/5 | 4/5 | +1 新增 Tool Preferences 段 |
| 4. Anti-pattern Catalog | 3/5 | 4/5 | +1 反模式更系统 |
| 5. Risk Gradient | 4/5 | 4/5 | = 保持 |
| 6. Adversarial Verification | 1/5 | 4/5 | +3 新增 Verification 段 |
| 7. Context Isolation | 4/5 | 5/5 | +1 加了 Don't peek/race |
| 8. Output Contract | 3/5 | 4/5 | +1 加了数字锚定 |
| **平均** | **2.9/5** | **4.1/5** | **+1.2** |

## 主要改进

1. **Identity**: "personal assistant" → "excels at file management, web research, automation, multi-agent orchestration"
2. **Tool Preferences**: 新增独立段落，Read > cat, Edit > sed 等，有原因和回退
3. **Safety**: 从条件注入改为显式段落，列出了具体红线
4. **Risk Levels**: 新增显式分级（Low/Medium/High + 确认规则）
5. **Verification**: 全新段落——验证代码、不伪造成功、不掩饰失败
6. **Sub-Agent Rules**: 加了 Don't peek 和 Don't race
7. **Output Contract**: 加了 "If you can say it in one sentence, don't use three" 和 "Do not restate"
