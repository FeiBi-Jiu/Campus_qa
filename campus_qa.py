# -*- coding: utf-8 -*-
"""
校园问答小工具
功能：
  1. 本地知识库：关键词匹配 + 模糊相似度打分，常见问题秒回，离线也能用。
  2. AI 问答：接入大模型，本地知识库答不上来的问题交给 AI，
     并把知识库内容作为参考资料一并发送，减少模型编造。
支持：多轮对话上下文、流式输出、模式切换、帮助/列表/清空/退出指令。
配置：项目根目录的 .env 文件中填写 CAMPUS_AI_API_KEY / CAMPUS_AI_BASE_URL / CAMPUS_AI_MODEL。
接口：自动适配 OpenAI 兼容的两种协议
  · Chat Completions：BASE_URL 以 /chat/completions 结尾或只填到 /v1
  · Responses API   ：BASE_URL 以 /responses 结尾（如火山方舟 /api/v3/responses）
"""

import difflib
import json
import os
import ssl
import urllib.error
import urllib.request

# ---------------- 知识库 ----------------
# 每条记录: (问题关键词列表, 标准问题, 答案)
# 想新增问答，只需在 KNOWLEDGE 中追加一条记录即可。
KNOWLEDGE = [
    (["图书馆", "开放时间", "几点"], "图书馆的开放时间是什么时候？",
     "📚 图书馆开放时间：周一至周五 8:00-22:00，周六周日 9:00-21:00，考试周延长至 23:00。"),
    (["图书馆", "借书", "借阅", "能借"], "在图书馆能借多少本书？",
     "📖 本科生最多可借 10 本，研究生 15 本，借期 30 天，可续借 1 次。"),
    (["食堂", "吃饭", "饭点", "开餐"], "食堂几点开饭？",
     "🍚 食堂开餐时间：早餐 6:30-9:00，午餐 11:00-13:30，晚餐 17:00-19:30。"),
    (["校车", "班车", "时间表"], "校车的时间表是怎样的？",
     "🚌 校车工作日每 30 分钟一班，首班 7:00，末班 21:30；周末每小时一班。"),
    (["选课", "退课", "教务系统"], "什么时候可以选课和退课？",
     "🖥️ 选课在教务系统进行：每学期开学第 1-2 周选课，第 3-4 周可退课补选。"),
    (["成绩", "查成绩", "绩点", "GPA"], "在哪里查成绩和绩点？",
     "📊 登录教务系统（jwxt.campus.edu.cn）→ 成绩查询，可查看成绩与绩点；绩点每学期结束后 5 个工作日内更新。"),
    (["宿舍", "熄灯", "断电", "门禁"], "宿舍几点熄灯、有门禁吗？",
     "🛏️ 宿舍门禁 23:00，周日至周四 23:30 熄灯，周五周六 24:00 熄灯，断电时间与熄灯一致。"),
    (["校医院", "看病", "医保", "报销"], "校医院怎么看病、能报销吗？",
     "🏥 校医院工作时间 8:00-17:00，急诊 24 小时。凭校园卡就诊，医保报销比例约 80%，保留发票到一楼服务台办理。"),
    (["社团", "加入社团", "招新"], "怎么加入学生社团？",
     "🎭 每年 9 月开学季和 3 月春季学期有社团招新（百团大战），关注“校学生会”公众号获取招新信息，也可直接到学生活动中心 203 室咨询。"),
    (["wifi", "无线网", "上网", "校园网"], "校园网怎么连？",
     "📶 连接 CampusNet-WiFi，用学号和统一认证密码登录认证页面（10.0.0.55）即可上网；每月免费流量 50G。"),
    (["快递", "取快递", "快递点", "菜鸟"], "快递在哪里取？",
     "📦 快递统一放在菜鸟驿站（生活服务中心一楼），凭取件码取件，营业时间 9:00-21:00。"),
    (["操场", "体育馆", "运动", "健身"], "运动场地什么时候开放？",
     "⚽ 操场全天开放；体育馆 8:00-22:00，需提前在“场馆预约”小程序预约；健身房 14:00-21:00 免费开放。"),
    (["奖学金", "助学金", "评奖"], "奖学金怎么申请？",
     "🏆 奖学金每学年 9 月评选，需满足成绩排名前 30% 且无违纪记录；助学金随时可向辅导员提交申请材料。"),
    (["转专业", "换专业"], "可以转专业吗？",
     "🔄 可以。大一下学期末申请，要求原专业成绩排名前 20%，无挂科记录，通过目标学院面试后转入。"),
    (["请假", "销假"], "请假流程是什么？",
     "📝 3 天以内向辅导员请假，3 天以上需学院审批；销假时到辅导员处登记销假即可。"),
    (["考试", "期末", "挂科", "补考"], "挂科了怎么办？",
     "😨 挂科后可在下学期初参加补考，补考不过需重修；重修请关注教务系统的重修报名通知。"),
]


# ---------------- AI 服务配置 ----------------
def load_dotenv(path):
    """读取 .env 文件写入环境变量（已存在的环境变量优先，不覆盖）"""
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except OSError:
        pass


ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_FILE)

AI_API_KEY = os.environ.get("CAMPUS_AI_API_KEY", "").strip()
AI_BASE_URL = os.environ.get("CAMPUS_AI_BASE_URL", "").strip().rstrip("/")
AI_MODEL = os.environ.get("CAMPUS_AI_MODEL", "").strip()
try:
    AI_TIMEOUT = float(os.environ.get("CAMPUS_AI_TIMEOUT", "60"))
except ValueError:
    AI_TIMEOUT = 60.0

HISTORY_LIMIT = 8  # 保留最近 8 条消息（约 4 轮问答）作为上下文

# 模式：hybrid = 本地优先 + AI 兜底；kb = 仅本地知识库；ai = 始终交给 AI
MODE_HYBRID, MODE_KB, MODE_AI = "hybrid", "kb", "ai"

HELP_TEXT = """
================ 使用帮助 ================
直接输入问题，例如：
  · 图书馆几点开门？
  · 食堂几点开饭？
  · 怎么加入社团？
AI 会记住上下文，可以接着追问，例如：
  · 那周末呢？
其他指令：
  · help / 帮助        → 显示本帮助
  · list / 列表        → 查看知识库覆盖的问题
  · auto / 自动        → 混合模式：本地优先，答不上来交给 AI（默认）
  · ai                 → AI 模式：所有问题都交给大模型
  · kb / 知识库        → 本地模式：只查本地知识库，不联网
  · clear / 清空       → 清空 AI 对话上下文
  · 退出 / exit        → 结束程序
==========================================
"""

SYSTEM_PROMPT_TEMPLATE = """你是校园生活助手「小助手」，面向在校学生回答校园事务问题。

请遵守以下规则：
1. 优先依据下面的【校园资料】回答；资料没有写到的内容不要编造。
2. 资料未覆盖时，可以给出一般性建议，但要补充说明“以上为通用建议，具体请以学校官方通知为准”。
3. 用中文回答，简洁分点，控制在 120 字以内，可适当使用 emoji。
4. 若问题与校园生活无关，礼貌说明你只负责校园事务咨询。

【校园资料】
{knowledge}
"""


def config_problems():
    """返回 AI 配置缺失项列表，为空表示配置完整"""
    problems = []
    if not AI_BASE_URL:
        problems.append("缺少服务地址 CAMPUS_AI_BASE_URL")
    if not AI_MODEL:
        problems.append("缺少模型名 CAMPUS_AI_MODEL")
    if not AI_API_KEY and "localhost" not in AI_BASE_URL and "127.0.0.1" not in AI_BASE_URL:
        problems.append("缺少 API Key CAMPUS_AI_API_KEY")
    return problems


def ai_configured() -> bool:
    """AI 服务是否已完整配置"""
    return not config_problems()


def resolve_endpoint(base_url: str) -> str:
    """根据配置推断具体接口地址，同时兼容两种协议"""
    if base_url.endswith("/responses") or base_url.endswith("/chat/completions"):
        return base_url
    return base_url + "/chat/completions"


def build_system_prompt() -> str:
    """把本地知识库拼进系统提示词，让 AI 的回答有据可依"""
    lines = [f"- {std_q} {answer}" for _, std_q, answer in KNOWLEDGE]
    return SYSTEM_PROMPT_TEMPLATE.format(knowledge="\n".join(lines))


class AIError(Exception):
    """AI 调用失败时抛出，携带可直接展示给用户的提示信息"""


def build_ssl_context():
    """优先用 certifi 的根证书；系统自带证书可用时也能正常工作"""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


SSL_CONTEXT = build_ssl_context()


def open_url(req):
    """发起 HTTPS 请求；本机缺根证书时降级为不校验并给出提示"""
    try:
        return urllib.request.urlopen(req, timeout=AI_TIMEOUT, context=SSL_CONTEXT)
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
            raise
        print("⚠️  本地根证书校验失败，本次请求已跳过证书校验（安装 certifi 可彻底修复）")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return urllib.request.urlopen(req, timeout=AI_TIMEOUT, context=ctx)


def build_payload(endpoint: str, messages: list, stream: bool) -> dict:
    """按接口类型组装请求体：Responses API 用 input/instructions，Chat Completions 用 messages"""
    if endpoint.endswith("/responses"):
        system = messages[0]["content"]
        items = []
        for m in messages[1:]:
            item_type = "output_text" if m["role"] == "assistant" else "input_text"
            items.append({"role": m["role"], "content": [{"type": item_type, "text": m["content"]}]})
        return {
            "model": AI_MODEL,
            "instructions": system,
            "input": items,
            "stream": stream,
            "temperature": 0.3,
        }
    return {
        "model": AI_MODEL,
        "messages": messages,
        "stream": stream,
        "temperature": 0.3,
    }


def extract_text(data: dict) -> str:
    """从 Responses API 的响应对象中提取文本，兼容 Chat Completions 结构"""
    choices = data.get("choices")
    if choices:
        return (choices[0].get("message") or {}).get("content") or ""
    texts = []
    for item in data.get("output") or []:
        for part in item.get("content") or []:
            if part.get("type") in ("output_text", "text") and part.get("text"):
                texts.append(part["text"])
    return "".join(texts)


def ask_ai(question: str, history: list):
    """向 AI 提问，流式逐段 yield 文本；失败抛 AIError"""
    problems = config_problems()
    if problems:
        raise AIError(f"AI 服务未配置完整：{'；'.join(problems)}（请编辑 {ENV_FILE}）")

    messages = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(history[-HISTORY_LIMIT:])
    messages.append({"role": "user", "content": question})

    endpoint = resolve_endpoint(AI_BASE_URL)
    payload = build_payload(endpoint, messages, stream=True)
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if AI_API_KEY:
        headers["Authorization"] = f"Bearer {AI_API_KEY}"

    req = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )

    try:
        resp = open_url(req)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            body = e.read().decode("utf-8", "ignore")
            detail = json.loads(body).get("error", {}).get("message") or body[:200]
        except Exception:
            pass
        raise AIError(f"AI 服务返回错误（HTTP {e.code}）：{detail or e.reason}")
    except urllib.error.URLError as e:
        raise AIError(f"无法连接 AI 服务：{e.reason}（请检查 CAMPUS_AI_BASE_URL 与网络）")
    except TimeoutError:
        raise AIError("AI 服务响应超时，请稍后重试或调大 CAMPUS_AI_TIMEOUT")

    with resp:
        content_type = resp.headers.get("Content-Type", "")
        # 服务不支持流式时，一次性解析完整 JSON
        if "event-stream" not in content_type:
            data = json.loads(resp.read().decode("utf-8"))
            text = extract_text(data)
            if not text:
                raise AIError(f"AI 返回格式异常：{str(data)[:200]}")
            yield text
            return

        # 逐行解析 SSE：兼容 Responses API 的具名事件与 Chat Completions 的 delta
        yielded = False
        for raw_line in resp:
            line = raw_line.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            chunk_type = chunk.get("type") or ""
            if chunk_type == "response.output_text.delta":
                delta = chunk.get("delta") or ""
                if delta:
                    yielded = True
                    yield delta
                continue
            if chunk_type in ("response.completed", "response.incomplete"):
                # 有些实现只在结束事件里给完整结果
                if not yielded:
                    text = extract_text(chunk.get("response") or {})
                    if text:
                        yielded = True
                        yield text
                continue
            if chunk_type and chunk_type.startswith("response."):
                continue

            choices = chunk.get("choices") or []
            if choices:
                delta = (choices[0].get("delta") or {}).get("content")
                if delta:
                    yielded = True
                    yield delta
            elif chunk.get("error"):
                raise AIError(f"AI 服务返回错误：{chunk['error'].get('message', '未知错误')}")


def remember(history: list, question: str, answer: str):
    """把一轮问答写入上下文，并裁剪到 HISTORY_LIMIT"""
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    del history[:-HISTORY_LIMIT]


def answer_with_ai(question: str, history: list) -> str:
    """调用 AI 并边生成边打印，成功返回完整回答（失败返回空串）"""
    print("小助手：", end="", flush=True)
    pieces = []
    try:
        for text in ask_ai(question, history):
            print(text, end="", flush=True)
            pieces.append(text)
    except AIError as e:
        print(f"\n⚠️  {e}\n")
        return ""
    except KeyboardInterrupt:
        print("\n（已中断本次回答）\n")
        return ""

    print("\n")
    answer = "".join(pieces).strip()
    if answer:
        remember(history, question, answer)
    return answer


def find_answer(question: str):
    """根据关键词命中数量和相似度打分，返回 (标准问题, 答案) 或 None"""
    question = question.strip().lower()
    best_score, best_item = 0.0, None

    for keywords, std_q, answer in KNOWLEDGE:
        # 1) 关键词命中：每个命中的关键词记 2 分
        score = sum(2 for kw in keywords if kw in question)
        # 2) 整句相似度（处理换个说法的情况），最高贡献 3 分
        similarity = difflib.SequenceMatcher(None, std_q.lower(), question).ratio()
        score += similarity * 3
        if score > best_score:
            best_score, best_item = score, (std_q, answer)

    # 阈值：至少命中 1 个关键词或有一定相似度
    if best_score >= 2:
        return best_item
    return None


def show_all_questions():
    print("\n--------- 我能回答这些问题 ---------")
    for i, (_, std_q, _) in enumerate(KNOWLEDGE, 1):
        print(f" {i:>2}. {std_q}")
    print("------------------------------------\n")


def print_status(mode: str):
    problems = config_problems()
    if not problems:
        key_state = "已配置" if AI_API_KEY else "免 Key（本地模型）"
        api_kind = "Responses API" if AI_BASE_URL.endswith("/responses") else "Chat Completions"
        print(f"🤖 AI 服务：{AI_MODEL}（{api_kind}）")
        print(f"   接口地址：{resolve_endpoint(AI_BASE_URL)}（{key_state}）")
    else:
        print(f"🤖 AI 服务：未配置完整 —— {'；'.join(problems)}")
        print(f"   请编辑 {ENV_FILE} 后重新运行；未配置时仅使用本地知识库。")
    print(f"⚙️  当前模式：{mode}\n")


def main():
    print("=" * 42)
    print("        🏫 欢迎使用校园问答小工具 🏫")
    print("=" * 42)

    mode = MODE_HYBRID if ai_configured() else MODE_KB
    history = []
    print_status(mode)
    print(HELP_TEXT)

    while True:
        try:
            question = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见，祝你校园生活愉快！👋")
            break

        if not question:
            continue

        cmd = question.lower()
        if cmd in ("exit", "quit", "退出", "再见"):
            print("小助手：再见，祝你校园生活愉快！👋")
            break
        if cmd in ("help", "帮助", "?"):
            print(HELP_TEXT)
            continue
        if cmd in ("list", "列表", "问题列表"):
            show_all_questions()
            continue
        if cmd in ("ai", "ai模式"):
            mode = MODE_AI
            print("小助手：已切换到 AI 模式，所有问题交给大模型回答。\n")
            continue
        if cmd in ("kb", "知识库", "本地"):
            mode = MODE_KB
            print("小助手：已切换到本地知识库模式，不再联网。\n")
            continue
        if cmd in ("auto", "自动", "混合"):
            mode = MODE_HYBRID
            print("小助手：已切换到混合模式，本地优先、AI 兜底。\n")
            continue
        if cmd in ("clear", "清空", "重置"):
            history.clear()
            print("小助手：AI 对话上下文已清空。\n")
            continue

        if mode == MODE_AI:
            answer_with_ai(question, history)
            continue

        result = find_answer(question)
        if result:
            std_q, answer = result
            print(f"小助手：{answer}")
            print(f"        （参考问题：{std_q}）\n")
            remember(history, question, answer)
            continue

        if mode == MODE_HYBRID:
            print("小助手：本地知识库没找到答案，交给 AI 处理…")
            answer_with_ai(question, history)
        else:
            print("小助手：抱歉，我还没学会这个问题 😥 输入 list 可以查看我能回答的问题。")
            if ai_configured():
                print("        输入 ai 可切换到 AI 模式，让大模型来回答。\n")
            else:
                print("        提示：配置 .env 中的 AI 参数后即可用 AI 回答未知问题（见 README）。\n")


if __name__ == "__main__":
    main()