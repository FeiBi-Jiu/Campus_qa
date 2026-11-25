# 🏫 校园问答小工具 (Campus Q&A)

一个零第三方依赖的命令行校园问答小工具：**本地知识库秒回常见问题，本地答不上来交给 AI 大模型**，兼顾速度、准确性和可扩展性。

## ✨ 功能特性

- **双层问答架构**：本地知识库优先命中，AI 大模型兜底，常见问题不消耗 token
- **关键词加权匹配**：每个命中的关键词计 2 分
- **模糊相似度兜底**：用 `difflib` 计算整句相似度，支持"换个说法"的提问
- **AI 大模型接入**：兼容 OpenAI 风格的 Chat Completions 与 Responses API 两种协议
- **知识库注入提示词**：把内置问答作为参考资料发给模型，显著减少编造
- **多轮对话上下文**：AI 记得前面的问答，可以直接追问"那周末呢？"
- **流式输出**：回答边生成边打印，不用干等
- **三种模式可切换**：混合 / 纯 AI / 纯本地（离线可用）
- **内置指令**：帮助、查看问题列表、清空上下文、退出
- **零第三方依赖**：仅用 Python 3 标准库

## 🚀 快速开始

仅需 Python 3，无需安装任何第三方依赖：

```bash
python3 campus_qa.py
```

### 配置 AI（可选，但强烈推荐）

没有配置 AI 时，程序自动退化为纯本地知识库模式，依然可用。要启用 AI，在项目根目录创建 `.env` 文件：

```ini
CAMPUS_AI_API_KEY=你的密钥
CAMPUS_AI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/responses
CAMPUS_AI_MODEL=doubao-seed-2-1-lite-260915
CAMPUS_AI_TIMEOUT=60
```

> `.env` 已写入 `.gitignore`，不会被提交到仓库。

运行后会出现提示符，直接输入问题即可：

```
你：图书馆几点开门？
小助手：📚 图书馆开放时间：周一至周五 8:00-22:00，周六周日 9:00-21:00，考试周延长至 23:00。
        （参考问题：图书馆的开放时间是什么时候？）
```

知识库没有覆盖的问题会交给 AI，并保留上下文以便追问：

```
你：学校附近有共享单车吗
小助手：本地知识库没找到答案，交给 AI 处理…
小助手：1. 📌 目前校园资料暂未收录学校周边共享单车的相关信息。
        2. 通用建议：多数高校校门周边会有合规投放的共享单车……
        以上为通用建议，具体请以学校官方通知为准。
```

## 🔌 接入其他大模型

程序会**根据 BASE_URL 自动选择协议**，换平台只需改 `.env` 三行：

| 平台 | CAMPUS_AI_BASE_URL | CAMPUS_AI_MODEL | 协议 |
| --- | --- | --- | --- |
| 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3/responses` | `doubao-seed-2-1-lite-260915` | Responses API |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | Chat Completions |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | Chat Completions |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | Chat Completions |
| Ollama 本地 | `http://localhost:11434/v1` | `qwen2.5:7b` | Chat Completions（免 Key） |

判定规则：BASE_URL 以 `/responses` 结尾走 Responses API，否则自动补 `/chat/completions`。指向 `localhost` / `127.0.0.1` 时视为本地模型，可不填 Key。

## 💬 内置指令

| 输入 | 作用 |
| --- | --- |
| `help` / `帮助` / `?` | 显示使用帮助 |
| `list` / `列表` / `问题列表` | 列出知识库覆盖的问题 |
| `auto` / `自动` / `混合` | 混合模式：本地优先、AI 兜底（配置 AI 后默认） |
| `ai` | AI 模式：所有问题都交给大模型 |
| `kb` / `知识库` / `本地` | 本地模式：只查知识库，不联网 |
| `clear` / `清空` / `重置` | 清空 AI 对话上下文 |
| `exit` / `quit` / `退出` / `再见` | 结束程序 |
| `Ctrl+C` / `Ctrl+D` | 强制退出 |

## 📚 已覆盖的问答主题

图书馆开放时间与借阅、食堂开餐、校车班次、选课退课、成绩绩点查询、宿舍门禁与熄灯、校医院与医保报销、社团招新、校园网连接、快递取件、运动场馆开放、奖助学金、转专业、请假销假、挂科补考重修。

## 🧩 扩展知识库

打开 [campus_qa.py](campus_qa.py)，在 `KNOWLEDGE` 列表中追加一条记录：

```python
KNOWLEDGE = [
    # (问题关键词列表, 标准问题, 答案)
    (["关键词1", "关键词2"], "标准问题？", "这里填写答案"),
    # ...
]
```

- **问题关键词列表**：用户提问中可能出现的词，命中越多得分越高
- **标准问题**：展示给用户的参考问题，同时参与整句相似度计算
- **答案**：返回给用户的内容，**同时也会被注入 AI 的提示词作为参考资料**

## ⚙️ 匹配算法说明

在 `find_answer()` 中，对每条知识库记录计算得分：

1. **关键词得分**：`2 分 / 每个命中的关键词`
2. **相似度得分**：`相似度比例 × 3 分`（最高 3 分）
3. 取总分最高的记录；若最高分低于阈值 `2`，则判定为"未匹配"

因此，命中 1 个关键词即可直接命中答案；仅靠句式相近也能被识别出来。未匹配时：
- **混合模式**下自动转交 AI 回答
- **本地模式**下返回兜底提示

## 📁 项目结构

```
SchoolAnswer/
├── campus_qa.py      # 主程序：知识库 + 匹配逻辑 + AI 调用 + 命令行交互
├── .env              # 本地 AI 配置（含密钥，不提交）
├── .gitignore        # 忽略 macOS / Python 缓存 / .env
└── README.md         # 项目说明文档
```

## 🛠 技术栈

- Python 3（标准库 `difflib` / `urllib` / `json` / `ssl`，无第三方依赖）
- 可选 `certifi`：修复部分环境下 Python 根证书缺失导致的 HTTPS 校验失败