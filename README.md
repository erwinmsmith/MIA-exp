# MIA-exp

自动派生 subagent 的公开实验基座。仓库用于组织可复现的实验、适配多个
benchmark，并验证 [Roy](https://github.com/erwinmsmith/Roy) 的派生、工具调用、
执行树和轨迹能力。

当前首个 benchmark 是
[LHTB](https://github.com/zli12321/LHTB)（Long-Horizon Terminal-Bench）。

## 仓库边界

```text
MIA-exp/                 # 实验、适配器、配置、结果处理
├── core/Roy/            # 独立 Git submodule；只放 benchmark 无关的核心能力
├── benchmarks/LHTB/     # 独立 Git submodule；上游 benchmark，默认只读
├── experiments/         # 各 benchmark 的适配与实验配置
├── scripts/             # 初始化、检查、启动与仓库边界工具
├── artifacts/           # 本地产物（内容默认忽略）
└── results/             # 原始/汇总结果（内容默认忽略）
```

完整管理规则见 [`AGENTS.md`](AGENTS.md)。关键原则是：实验适配 Roy，不让 Roy
为某个 benchmark 写 special case；只有通用工程能力进入 Roy，并在 Roy 仓库中
单独 commit + push 后再更新外层 submodule 指针。

## 初始化

要求：Git、Node.js 20+、Python 3.11+、`uv`、Git LFS，以及正在运行的 Docker。

```bash
git clone --recurse-submodules https://github.com/erwinmsmith/MIA-exp.git
cd MIA-exp
make bootstrap
make doctor
make check
```

若普通 clone 已完成但 submodule 尚未拉取，`make bootstrap` 会自动补齐。
LHTB 的大文件默认通过 Git LFS 拉取；只做代码检查时可使用：

```bash
MIA_SKIP_LHTB_LFS=1 make bootstrap
```

## 验证层级

```bash
make smoke-roy       # Roy 构建、测试、one-shot CLI 可用性
make smoke-roy-container # Linux amd64 容器内启动 Roy bundle
make smoke-harbor    # Harbor CLI 和 LHTB 配置可读
make smoke-lhtb      # Docker 中运行 LHTB oracle smoke（不需要模型 API key）
make check           # 运行不消耗模型额度的本地检查
make run-lhtb-roy    # 使用已配置的模型凭据运行一项真实 Roy/LHTB 任务
```

真实 Roy 任务还需要设置模型 provider 的环境变量，例如
`OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 或 `DEEPSEEK_API_KEY`。密钥不得写入配置或
提交到 Git。

## 实验

每个 benchmark 的适配器位于 `experiments/<benchmark>/`。LHTB 的入口和运行
说明见 [`experiments/lhtb/README.md`](experiments/lhtb/README.md)。

LHTB 适配器会在 bootstrap 时构建独立的 Roy bundle，并缓存通过官方 SHA-256
校验的 Linux x64 Node runtime，再上传到隔离的 task container。宿主机和
benchmark 镜像无需预装 Roy。

每次结果都应记录：

- MIA-exp、Roy、benchmark 的 commit SHA；
- 模型/provider 与非敏感配置；
- 原始 Harbor job 输出；
- Roy execution tree、events、messages 和 trajectory；
- verifier reward，而不是 agent 自述的完成状态。
