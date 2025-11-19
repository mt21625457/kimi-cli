Codex SDK
将Codex代理嵌入你的工作流程和应用中。

TypeScript SDK 会封装捆绑的二进制文件。它会生成CLI并通过stdin/stdout交换JSONL事件。codex

安装
npm install @openai/codex-sdk
需要Node.js 18+。

快速入门
import { Codex } from "@openai/codex-sdk";

const codex = new Codex();
const thread = codex.startThread();
const turn = await thread.run("Diagnose the test failure and propose a fix");

console.log(turn.finalResponse);
console.log(turn.items);
在同一个实例上反复拨打电话，继续对话。run()Thread

const nextTurn = await thread.run("Implement the fix");
直播回应
run()缓冲事件直到回合结束。要对中间进展做出反应——工具调用、流式响应和文件变更通知——使用“Instead”，它返回一个结构化事件的异步生成器。runStreamed()

const { events } = await thread.runStreamed("Diagnose the test failure and propose a fix");

for await (const event of events) {
  switch (event.type) {
    case "item.completed":
      console.log("item", event.item);
      break;
    case "turn.completed":
      console.log("usage", event.usage);
      break;
  }
}
结构化输出
Codex 代理可以生成符合指定模式的 JSON 响应。模式可以作为普通的 JSON 对象为每回合提供。

const schema = {
  type: "object",
  properties: {
    summary: { type: "string" },
    status: { type: "string", enum: ["ok", "action_required"] },
  },
  required: ["summary", "status"],
  additionalProperties: false,
} as const;

const turn = await thread.run("Summarize repository status", { outputSchema: schema });
console.log(turn.finalResponse);
你也可以用 zod-to-json-schema 包并设置 to to ，从 Zod 模式创建一个 JSON 模式。target"openAi"

const schema = z.object({
  summary: z.string(),
  status: z.enum(["ok", "action_required"]),
});

const turn = await thread.run("Summarize repository status", {
  outputSchema: zodToJsonSchema(schema, { target: "openAi" }),
});
console.log(turn.finalResponse);
附图
当需要将图片与文本并列时，提供结构化输入条目。文本条目会被串接到最终提示符中，而图片条目则通过 传递到 Codex CLI。--image

const turn = await thread.run([
  { type: "text", text: "Describe these screenshots" },
  { type: "local_image", path: "./ui.png" },
  { type: "local_image", path: "./diagram.jpg" },
]);
恢复现有线程
线程在 中被持久化。如果你丢失了内存中的对象，可以用它重建它并继续使用。~/.codex/sessionsThreadresumeThread()

const savedThreadId = process.env.CODEX_THREAD_ID!;
const thread = codex.resumeThread(savedThreadId);
await thread.run("Implement the fix");
工作目录控制
Codex 默认运行在当前的工作目录中。为避免无法恢复的错误，Codex 要求工作目录必须是 Git 仓库。你可以在创建线程时跳过 Git 仓库检查，通过跳过该选项。skipGitRepoCheck

const thread = codex.startThread({
  workingDirectory: "/path/to/project",
  skipGitRepoCheck: true,
});
控制Codex CLI环境
默认情况下，Codex CLI 继承了 Node.js 进程环境。实例化客户端时提供可选参数，以完全控制CLI接收的变量——这对像Electron应用这样的沙箱主机非常有用。envCodex

const codex = new Codex({
  env: {
    PATH: "/usr/local/bin",
  },
});
SDK 仍然会在环境上注入所需的变量（比如和 ），然后 提供。OPENAI_BASE_URLCODEX_API_KEY