# Prompt Queue Execution Plan

## 目标
再次输入 prompt 时排队等待，当前 turn 结束后自动执行。

## 修改文件
`tui/widgets/conversation.py`

## 修改 1 — 添加队列 (line ~449)
```python
# Before:
        self._post_lock = asyncio.Lock()
        self._auto_named_session = False

# After:
        self._post_lock = asyncio.Lock()
        self._auto_named_session = False
        self._pending_prompts: list[str] = []
```

## 修改 2 — on_user_input_submitted 增加忙碌检测 (line ~951)
```python
# Before:
        elif text := event.body.strip():
            await self.prompt_history.append(event.body)
            self.prompt_history_index = 0
            if text.startswith("/") and await self.slash_command(text):
                return
            await self.post(UserInput(text))
            self.window.scroll_end(animate=False)
            self._loading = await self.post(Loading("Please wait..."), loading=True)
            await asyncio.sleep(0)
            if self._msg_log is not None:
                self._msg_log.user_input(text, self._turn_count)
            self.send_prompt_to_agent(text)

# After:
        elif text := event.body.strip():
            await self.prompt_history.append(event.body)
            self.prompt_history_index = 0
            if text.startswith("/") and await self.slash_command(text):
                return
            await self.post(UserInput(text))
            self.window.scroll_end(animate=False)

            if self.turn == "agent":
                self._pending_prompts.append(text)
                self.flash("Prompt queued — will run when the agent finishes", style="info")
                return

            self._loading = await self.post(Loading("Please wait..."), loading=True)
            await asyncio.sleep(0)
            if self._msg_log is not None:
                self._msg_log.user_input(text, self._turn_count)
            self.send_prompt_to_agent(text)
```

## 修改 3 — agent_turn_over 末尾消费队列 (line ~1069)
```python
# Before:
        if self.app.settings.get("notifications.turn_over", bool):
            self.app.system_notify(
                f"{self.agent_title} has finished working",
                title="Waiting for input",
                sound="turn-over",
            )

# After:
        if self.app.settings.get("notifications.turn_over", bool):
            self.app.system_notify(
                f"{self.agent_title} has finished working",
                title="Waiting for input",
                sound="turn-over",
            )

        if self._pending_prompts:
            next_prompt = self._pending_prompts.pop(0)
            self._loading = await self.post(Loading("Please wait..."), loading=True)
            await asyncio.sleep(0)
            if self._msg_log is not None:
                self._msg_log.user_input(next_prompt, self._turn_count)
            self.send_prompt_to_agent(next_prompt)
```

## 验证
```bash
ruff check tui/widgets/conversation.py
mypy tui/widgets/conversation.py
```

## 回滚方式
```bash
git checkout tui/widgets/conversation.py
```
