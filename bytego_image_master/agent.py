import json
from typing import Callable, Optional

from .agent_tools import TOOLS, ToolRunner
from .api import ApiClient, ApiError
from .platforms import shell_tool_label

SYSTEM_PROMPT = """你是一个运行在用户本机（Windows/macOS）的助手 Agent，宿主程序是 Bytego中转站GPT-Image/Grok Image Master（图像生成工具）。

你可以调用本地工具来替用户完成真实操作，而不是只给建议：
- run_command：执行命令行（默认 """ + shell_tool_label() + """）
- read_file / write_file：读写本地文本文件
- list_directory：查看目录
- open_path：用系统文件管理器打开路径
- generate_image：用配置的图像模型生成图片
- list_history：查看最近的生成记录

工作准则：
1. 需要动手就直接调用工具，不要只描述步骤。
2. 工具会真实作用于用户机器，参数要精确、可回滚；破坏性操作（删除、覆盖、格式化）除非用户明确要求，否则先说明再执行。
3. 调用工具失败时，读懂报错并修正参数重试，不要原样重试同一个错误调用。
4. 最终用中文简洁回答，交代做了什么、结果在哪。生成图片时给出文件路径。
5. 每次回复控制在几句话内，不要长篇大论。"""


class Agent:
    MAX_STEPS = 8

    def __init__(self, client: ApiClient, runner: ToolRunner, model: str = "",
                 system_prompt: str = SYSTEM_PROMPT):
        self.client = client
        self.runner = runner
        self.model = model
        self.system_prompt = system_prompt

    def run(self, user_input: str, history: list,
            on_event: Callable[[dict], None],
            on_retry: Optional[Callable[[int, ApiError], None]] = None) -> str:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history[-20:])
        messages.append({"role": "user", "content": user_input})

        seen_calls: dict[str, int] = {}
        for _ in range(self.MAX_STEPS):
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            try:
                for evt in self.client.chat_stream(messages, tools=TOOLS, model=self.model,
                                                  on_retry=on_retry):
                    if evt["type"] == "text":
                        text_parts.append(evt["text"])
                        on_event({"type": "text", "text": evt["text"]})
                    elif evt["type"] == "tool_calls":
                        tool_calls = evt["calls"]
            except ApiError as exc:
                on_event({"type": "error", "message": exc.display()})
                return "".join(text_parts)

            answer = "".join(text_parts).strip()
            if not tool_calls:
                return answer

            messages.append({
                "role": "assistant",
                "content": answer,
                "tool_calls": [
                    {"id": c.get("id") or f"call_{i}", "type": "function",
                     "function": {"name": c.get("name", ""), "arguments": c.get("arguments") or "{}"}}
                    for i, c in enumerate(tool_calls)
                ],
            })

            for call in tool_calls:
                name = call.get("name", "")
                raw_args = call.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except ValueError:
                    args = {}
                signature = f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
                seen_calls[signature] = seen_calls.get(signature, 0) + 1
                if seen_calls[signature] > 2:
                    on_event({"type": "error",
                              "message": f"工具 {name} 被重复调用，已中止以避免死循环。"})
                    return "".join(text_parts).strip()
                on_event({"type": "tool_start", "name": name, "args": args})
                ok, result = self.runner.execute(name, args)
                on_event({"type": "tool_end", "name": name, "args": args, "ok": ok, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.get("id") or f"call_{name}",
                                 "content": result[:8000]})

        on_event({"type": "error", "message": f"达到最大执行步数（{self.MAX_STEPS}）仍未得出结果，请把要求拆小一点。"})
        return ""
