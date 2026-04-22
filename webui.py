import os
import time
from pathlib import Path
from urllib.parse import urlencode

from quart import Quart, jsonify, request, send_file

import grok
from api_solver import TurnstileAPIServer

WEBUI_TITLE = "GrokRegister WebUI"
DOWNLOAD_TOKEN = os.getenv("GROKREGISTER_WEBUI_TOKEN", "change-me")


def _render_html(state: dict) -> str:
    accounts = grok.read_accounts_file()
    sso = grok.read_sso_file()
    running_text = "运行中" if state.get("running") else "已停止"
    last_error = state.get("last_error") or "无"
    return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{WEBUI_TITLE}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background:#f6f7fb; color:#222; }}
    .wrap {{ max-width: 980px; margin: 0 auto; }}
    .card {{ background:#fff; border-radius:16px; padding:20px; box-shadow:0 8px 24px rgba(0,0,0,.08); margin-bottom:18px; }}
    h1,h2 {{ margin-top:0; }}
    .grid {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
    .stat {{ background:#f3f5ff; border-radius:12px; padding:14px; }}
    .stat b {{ display:block; font-size:12px; color:#666; margin-bottom:6px; }}
    input, button {{ padding:10px 12px; border-radius:10px; border:1px solid #ccc; font-size:14px; }}
    button {{ cursor:pointer; background:#111827; color:white; border:none; }}
    button.secondary {{ background:#e5e7eb; color:#111827; }}
    .actions {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; }}
    pre {{ white-space:pre-wrap; background:#111827; color:#f9fafb; padding:12px; border-radius:12px; overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ padding:10px; border-bottom:1px solid #e5e7eb; text-align:left; font-size:14px; }}
    a.download {{ display:inline-block; margin-right:10px; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <h1>{WEBUI_TITLE}</h1>
      <div class=\"grid\">
        <div class=\"stat\"><b>状态</b>{running_text}</div>
        <div class=\"stat\"><b>线程数</b>{state.get('thread_count') or 0}</div>
        <div class=\"stat\"><b>成功数</b>{state.get('success_count') or 0}</div>
        <div class=\"stat\"><b>已保存账号</b>{len(accounts)}</div>
        <div class=\"stat\"><b>已保存 SSO</b>{len(sso)}</div>
        <div class=\"stat\"><b>Action ID</b>{state.get('action_id') or '未初始化'}</div>
      </div>
    </div>

    <div class=\"card\">
      <h2>控制</h2>
      <form class=\"actions\" method=\"post\" action=\"/ui/start\">
        <input type=\"number\" min=\"1\" name=\"thread_count\" value=\"{state.get('thread_count') or 4}\" />
        <button type=\"submit\">启动注册</button>
      </form>
      <form class=\"actions\" method=\"post\" action=\"/ui/stop\" style=\"margin-top:10px;\">
        <button class=\"secondary\" type=\"submit\">停止注册</button>
      </form>
      <p>最后错误：{last_error}</p>
    </div>

    <div class=\"card\">
      <h2>下载结果</h2>
      <a class=\"download\" href=\"/download/accounts.txt?token={DOWNLOAD_TOKEN}\">下载 accounts.txt</a>
      <a class=\"download\" href=\"/download/grok.txt?token={DOWNLOAD_TOKEN}\">下载 grok.txt</a>
    </div>

    <div class=\"card\">
      <h2>最近账号（最多 20 条）</h2>
      <table>
        <thead><tr><th>#</th><th>内容</th></tr></thead>
        <tbody>
          {''.join(f'<tr><td>{i+1}</td><td>{line}</td></tr>' for i, line in enumerate(accounts[-20:][::-1])) or '<tr><td colspan="2">暂无结果</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>"""


def create_webui_app(headless: bool, useragent: str, debug: bool, browser_type: str, thread: int, proxy_support: bool):
    server = TurnstileAPIServer(
        headless=headless,
        useragent=useragent,
        debug=debug,
        browser_type=browser_type,
        thread=thread,
        proxy_support=proxy_support,
    )
    app: Quart = server.app

    @app.get("/ui")
    async def ui_index():
        return _render_html(grok.get_runtime_state())

    @app.post("/ui/start")
    async def ui_start():
        form = await request.form
        thread_count = grok.parse_thread_count(form.get("thread_count", "4"), default=4)
        grok.start_registration(thread_count)
        return _render_html(grok.get_runtime_state())

    @app.post("/ui/stop")
    async def ui_stop():
        grok.stop_registration()
        return _render_html(grok.get_runtime_state())

    @app.get("/api/ui/status")
    async def ui_status():
        state = grok.get_runtime_state()
        state["accounts_count"] = len(grok.read_accounts_file())
        state["sso_count"] = len(grok.read_sso_file())
        return jsonify(state)

    @app.get("/download/<path:name>")
    async def download_result(name: str):
        token = request.args.get("token", "")
        if token != DOWNLOAD_TOKEN:
            return jsonify({"error": "forbidden"}), 403
        allowed = {
            "accounts.txt": Path("keys/accounts.txt"),
            "grok.txt": Path("keys/grok.txt"),
        }
        target = allowed.get(name)
        if not target or not target.exists():
            return jsonify({"error": "not_found"}), 404
        return await send_file(target, as_attachment=True, attachment_filename=name)

    return app


if __name__ == "__main__":
    app = create_webui_app(
        headless=True,
        useragent=None,
        debug=False,
        browser_type="chromium",
        thread=2,
        proxy_support=True,
    )
    app.run(host="0.0.0.0", port=5080)
