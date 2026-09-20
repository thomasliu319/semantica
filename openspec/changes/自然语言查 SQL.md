自然语言查 SQL
把自然语言问题转成 SQL 执行：基础 prompt → few-shot → 思维链 → RAG 动态检索 schema → 自我改进循环。最优配置准确率 100%。

SQL
数据库
自然语言查 SQL
价值
可访问性：非技术用户无需懂 SQL 也能查数据库
效率：数据分析师快速原型化复杂查询
集成：在内部 BI 工具或聊天机器人里嵌入数据库查询
准确率渐进
配置	准确率	成本
基础 prompt	~70%	最低
Few-shot（5 个示例）	~85%	低
Chain-of-Thought	~92%	中
RAG 动态 schema	~96%	中
RAG + Few-shot + CoT	100%	最高
SDK 调用范例
import asyncio
from cloud_agent_sdk import (
    CloudAgentClient, ManifestBuilder, RuntimeCreateOptions,
)

SCHEMA = """
employees(id INT, name TEXT, department_id INT, salary DECIMAL, hire_date DATE)
departments(id INT, name TEXT, location TEXT)
"""

FEW_SHOT_EXAMPLES = """
<example>
Q: 工程部薪资 Top 5 是谁？
<thought_process>
需要 join employees + departments，按 department.name 过滤工程，按 salary DESC 排序。
</thought_process>
<sql>
SELECT e.name, e.salary FROM employees e
JOIN departments d ON e.department_id = d.id
WHERE d.name = 'Engineering'
ORDER BY e.salary DESC LIMIT 5;
</sql>
</example>
"""

async def text_to_sql(question: str) -> str:
    client = CloudAgentClient(api_key="ck_xxx")

    manifest = (
        ManifestBuilder()
        .id("text-to-sql")
        .name("SQL Helper")
        .version("1.0")
        .system_prompt(open("sql_prompt.md").read())
        .build()
    )

    runtime = await client.runtimes.create(
        RuntimeCreateOptions(runtime_name="sql-job", agent_manifest=manifest)
    )
    session = runtime.sessions.default()

    response = await session.prompt(
        f"Schema:\n{SCHEMA}\n\n{FEW_SHOT_EXAMPLES}\n\nQuestion: {question}"
    )

    await runtime.delete()
    return response.stop_reason

asyncio.run(text_to_sql("过去 30 天入职的员工里平均薪资最高的部门是哪个？"))
自我修正循环
执行 SQL 报错时，把错误信息和原始 SQL 喂回给 Agent，让它分析并改正：

feedback_prompt = f"""
上次 SQL 报错: {error_msg}
分析错误并给出改进版。
原始 SQL: {sql}
在 <thought_process> 解释你的修改，在 <sql> 给出修正版。
"""
通常 1-2 轮就能修复语法或字段名错误。