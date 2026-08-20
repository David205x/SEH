是，而且我认为你的工作**不是偏离 Weng 所描述的 Harness 自进化路线，而是在其中选择了一个相当明确、目前仍没有被充分解决的分支：把 Harness evolution 从“候选程序搜索”改造成“证据驱动的机制发现与验证”**。

但需要把“新意”说得非常精确。以截至 **2026 年 8 月 20 日**我能检索到的工作来看，你的方案不是靠某一个组件首次出现而新，而更像是提出了一种新的 **optimization protocol / research protocol**：

\[
\boxed{
\text{Failure}
\rightarrow
\text{Hypothesis}
\rightarrow
\text{Interventional Evidence}
\rightarrow
\text{Mechanism}
\rightarrow
\text{Capability Check}
\rightarrow
\text{Implementation}
\rightarrow
\text{Full Evaluation}
}
\]

而现有大多数 Harness evolution 更接近：

\[
\boxed{
\text{Failure / Experience}
\rightarrow
\text{Candidate Harness Edit}
\rightarrow
\text{Evaluation}
\rightarrow
\text{Selection}
}
\]

我认为这才应该成为你论文真正的叙事中心。

---

# 一、先给结论：符合 Weng 的路径吗？

**高度符合，而且是顺着文章最后提出的问题继续往下走。**

Weng 的主线是：

\[
Prompt
\rightarrow
Context
\rightarrow
Workflow
\rightarrow
Harness
\rightarrow
Optimizer
\]

你的工作显然已经位于：

\[
\boxed{\text{Harness Optimizer Engineering}}
\]

而不是普通 Harness Engineering。

你固定 Student 参数、evaluation kernel 和基础 loop，只允许 Prompt、Tool、Parser、Lifecycle Hook 等外围机制演化，这和当前 Harness-evolution 文献对 Harness 的定义非常一致。Meta-Harness、AHE、Self-Harness、Harness-R1 等都把 frozen model 周围的 executable runtime 作为优化对象。

但你的思路进一步问了一个 Weng 博客其实没有真正解决的问题：

> **既然 Harness Search 是 program search，那么我们是否真的应该把“完整 executable candidate”作为最小实验单位？**

你的答案实际上是：

> 不应该。  
> 在把一个想法固化成 Harness program 之前，应先验证它对应的行为机制是否真的有效，而且这个机制是否真的能够被目标 Student 执行。

这一点是很重要的。

---

# 二、我会怎样形式化你和现有工作的区别

现有 Harness evolution 可以抽象为：

\[
H_t
\xrightarrow{\text{diagnosis}}
m
\xrightarrow{\text{proposal}}
\Delta H
\xrightarrow{\text{compile}}
H_t'
\xrightarrow{\text{full rollout}}
R(H_t')
\]

最后根据：

\[
\Delta R = R(H_t')-R(H_t)
\]

决定接受还是拒绝。

这里有一个结构性问题：

## **“机制假设”和“代码实现”被绑定在一起实验。**

假设 Candidate 不工作：

\[
R(H_t') \downarrow
\]

你不知道究竟是哪一层错了：

\[
\boxed{
\begin{aligned}
&\text{Hypothesis wrong?}\\
&\text{Intervention ineffective?}\\
&\text{Student cannot execute it?}\\
&\text{Guard wrong?}\\
&\text{Compiler implemented it incorrectly?}\\
&\text{Patch interacts badly with other components?}\\
&\text{Evaluation noise?}
\end{aligned}}
\]

这其实就是一种 **credit assignment problem**。

DemoEvolve 已经明确指出：长轨迹和 sparse/high-variance outcomes 会让 Harness evolution 面临 credit assignment 问题，甚至可能让“没有真正产生作用”的 Harness edit 因随机结果而被选中。

你的方法则实际上进行了 factorization：

\[
\boxed{
\text{Research validity}
\neq
\text{Mechanism validity}
\neq
\text{Student feasibility}
\neq
\text{Implementation correctness}
\neq
\text{Candidate utility}
}
\]

然后分别验证。

这才是我认为最有价值的地方。

---

# 三、逐个看你的设计：哪些新，哪些已经有人做了

我会给一个比较严格的判断。

| 设计 | 新颖程度 | 最近邻工作 | 判断 |
|---|---:|---|---|
| External Teacher 优化 Student Harness | ★★ | Meta-Harness / Harness-R1 / HASP | 不新 |
| Frozen Student + mutable harness | ★ | 大量 Harness evolution | 标准设定 |
| Failure Analyst / structured diagnosis | ★★ | AHE / Self-Harness / DREvo | 不足以单独构成创新 |
| Falsifiable hypothesis | ★★ | AHE / HSI | 已出现 |
| Prefix-Fork | ★★ | Shepherd / TraceGraph | primitive 不新 |
| 用 Prefix-Fork **先验证 hypothesis，再写 patch** | ★★★★ | Shepherd 最接近 | 有明显差异 |
| 跨 case / prefix / repeat 的 pre-candidate evidence gate | ★★★★ | Self-Harness / HarnessBank | 比较有新意 |
| Evidence → implementation-independent mechanism | ★★★★ | HASP 部分接近 | 很值得强化 |
| Guard / runtime inputs / state / fallback 的机制表示 | ★★★ | HASP Program Function | 需要突出 representation 差异 |
| Hook Feasibility：先验证 Student 能否承担 semantic judgment | ★★★★★ | Harness Updating ≠ Harness Benefit | **我认为是最有希望的点之一** |
| Conformance Review | ★★★ | 软件验证/AHE 有邻近 | 本身一般，放在链路里有价值 |
| failure → evidence/mechanism/implementation 分层路由 | ★★★★ | AHE 最接近 | 有潜力 |
| Event-driven controller / WorkItem / Effect Receipt | ★★ | VeRO/系统工程 | 工程贡献，不宜做主 novelty |

下面几个尤其值得详细讲。

---

# 四、External Teacher → Small Student 本身不是新意

这点一定不要过度 claim。

Meta-Harness 本身就是 coding proposer 阅读：

- source；
- previous candidates；
- scores；
- trajectories；

然后优化另一个 target harness。

Harness-R1 更直接训练了一个独立 Harness Engineer，根据 target agent failure 生成 executable runtime patch。

HASP 也允许 auxiliary teacher 帮助选择 intervention。

所以：

> **Teacher Agent improves small Student**

不能成为 contribution。

但是你的 Teacher 有一个不同目的：

\[
\text{Teacher capability}
\neq
\text{Student capability}
\]

Teacher 不是仅仅提出一个“更聪明的策略”让 Student 照着做，而必须证明：

\[
\boxed{\text{Student itself can operationalize this mechanism}}
\]

这个差异很重要。

---

# 五、Failure Analyst 也不能单独作为 novelty

Self-Harness 已经不是：

> failed → edit

而是：

\[
\text{failed traces}
\rightarrow
\text{cluster}
\rightarrow
\text{shared symptoms}
\rightarrow
\text{agent mechanism}
\rightarrow
\text{evidence bundle}
\]

并明确区分 verifier-level failure 与 agent-level mechanism。

AHE 做得更系统：

\[
raw\ trajectories
\rightarrow
layered\ evidence
\rightarrow
root\ cause
\rightarrow
component
\]

并要求每个修改附带预测，下一轮验证。

DREvo 甚至已经提出 function-level evidence anchoring、state-dependent evidence recalibration 和 search-intent distillation。

所以你的：

> Failure Analyst + Evidence Reviewer

如果只停留在“结构化分析失败”，不新。

真正的区别是：

> **分析出来的 hypothesis 不马上成为 Harness edit。**

这才要重点强调。

---

# 六、“可证伪 Hypothesis”也不能单独 claim

这个地方近期文献推进得非常快。

AHE 已经要求每次修改带 self-declared prediction，然后通过下一轮 task outcome 验证，因此称每次 edit 是一个 falsifiable contract。

更直接的是 2026 年 8 月 9 日出现的 **Hierarchical Self-Improvement (HSI)**。

它的 hypothesis 明确包含：

1. anchor version；
2. motivation；
3. expected improvement；
4. **falsification criterion**。

然后 hypothesis 被送入 main evolution。

因此：

\[
\text{Hypothesis + falsifier}
\]

本身已经不能叫核心创新。

---

# 七、Prefix-Fork 更不能单独作为创新

这里我会特别提醒你，因为如果以后投稿，reviewer 很容易抓这个。

## Shepherd

Shepherd 已经把：

- past state；
- environment state；
- agent state；
- filesystem；

做成可 fork/replay 的 typed execution trace。

它甚至专门展示了 **counterfactual meta-optimization**，让 meta-agent 从历史执行状态分叉 alternative execution paths，而且报告相对于 Meta-Harness 的时间优势。

## TraceGraph

TraceGraph 更直接。

它在检测到 failure-prone state 后：

\[
s_t
\]

snapshot 相同：

- Docker workspace；
- conversation prefix；

然后分三个 branch：

\[
\begin{cases}
Baseline\\
Higher\ Temperature\\
Diagnosis\ Note
\end{cases}
\]

从**完全相同的 prefix state**继续运行，以比较 intervention 的 downstream effect。

因此：

> “我们提出 Prefix-Fork 来验证局部干预”

现在不能这样 claim。

---

# 八、但你的 Prefix-Fork **用途**和上述工作不同

这是非常关键的区分。

TraceGraph：

\[
\text{detect bad state}
\rightarrow
\text{fork}
\rightarrow
\text{apply recovery}
\]

目标是：

> 让当前运行恢复。

Shepherd 的 CRO：

\[
\text{execution history}
\rightarrow
\text{fork}
\rightarrow
\text{explore alternate workflow/candidate}
\]

目标是提高 meta-optimization 的效率。

而你的 Prefix-Fork 是：

\[
\text{Hypothesis } h
\rightarrow
\text{select relevant prefix }p
\rightarrow
\begin{cases}
\text{baseline continuation}\\
\text{Teacher intervention}
\end{cases}
\rightarrow
E(h,p)
\]

然后最重要的是：

\[
E(h,p)
\]

**不直接部署。**

而是成为：

\[
\text{Mechanism Distillation}
\]

的证据。

也就是说，你在把 Prefix-Fork 当作：

\[
\boxed{\text{experimental instrument}}
\]

而不仅仅是：

\[
\text{runtime primitive}
\]

这就明显更有意思了。

---

# 九、我认为你的第一个真正核心创新：Candidate 之前的 Experimental Layer

这是我现在最看好的地方。

现在 Self-Harness 的链路是：

\[
Failure
\rightarrow
Weakness
\rightarrow
Candidate\ Edit
\rightarrow
Regression\ Evaluation
\]

它虽然也要求 recurrent、concrete、addressable，而且做 held-out regression，但实验对象已经是 executable candidate。

HarnessBank 进一步解决 candidate crediting 问题，用 gated screening 来减少大量 offspring candidate 的评估成本，但其 screening 对象仍然是 **harness candidate**。

Harness-R1 更明显：

\[
Failures
\rightarrow
Executable\ Patch
\rightarrow
Same\ Batch\ Rerun
\rightarrow
Reward
\]

甚至直接训练 Harness Engineer。

而你的流程是：

\[
Failure
\rightarrow
Hypothesis
\rightarrow
\underbrace{Soft\ Intervention}_{\text{No persistent patch}}
\rightarrow
Evidence
\rightarrow
Mechanism
\rightarrow
\cdots
\rightarrow
Executable\ Candidate
\]

也就是：

\[
\boxed{
\text{Harness edit 不再是最小 experiment unit}
}
\]

你的最小实验单位变成：

\[
\boxed{
(\text{prefix},\text{intervention},\text{outcome})
}
\]

这是一个非常好的论文立足点。

---

# 十、甚至可以更进一步形式化

例如对 hypothesis \(h\)，选择 baseline Student rollout 中的 prefix：

\[
p=(s_0,a_0,\ldots,s_t)
\]

冻结这个状态。

构造：

\[
Y^{(0)}(p)
\]

baseline continuation；

以及：

\[
Y^{(h)}(p)
\]

施加 hypothesis 对应 soft intervention 后的 continuation。

那么你真正想估计的是：

\[
\delta(h,p)
=
\mathbb E[Y^{(h)}(p)-Y^{(0)}(p)]
\]

再跨 prefix：

\[
\hat\delta(h)
=
\frac{1}{|P_h|}
\sum_{p\in P_h}\hat\delta(h,p)
\]

这样你的论述就从：

> “Teacher 看起来觉得 intervention 有效果”

提升成：

> **paired prefix intervention estimates whether a proposed behavioral mechanism produces a reproducible downstream effect before it is compiled into persistent harness code.**

这是很强的叙事。

---

# 十一、但“因果验证”这个词目前要谨慎

你原文写：

> Prefix-Fork 使 Teacher 可以在真实运行边界上验证局部干预的因果作用

我会建议论文前期不要这么强地说。

因为：

\[
same\ prefix
\]

并不会自动等于严格 causal identification。

LLM completion 是随机的。

如果：

```text
baseline: seed 1
intervention: seed 2
```

然后一个成功一个失败，那么：

\[
\Delta Y
\]

可能仍然主要来自 sampling variance。

TraceGraph 自己就做了 paired uncertainty estimates，而且它也发现不同 provider 对不同 recovery policy 的收益不同。

更稳妥的叫法是：

> **counterfactual / interventional evidence**

而不是一开始就叫：

> causal effect。

除非你真的设计：

\[
K\text{ repeated continuations}
\]

以及 matched/randomized comparison。

例如：

\[
\hat\delta_{h,p}
=
\frac1K
\sum_{k=1}^{K}
\left(
Y_{h,p,k}-Y_{0,p,k}
\right)
\]

那“因果”会更站得住。

---

# 十二、第二个很强的点：Mechanism 是 Candidate 之前的独立中间表示

这个设计我很喜欢。

你的链路不是：

```text
failure
→ prompt patch / tool code
```

而是：

```text
evidence
→ mechanism specification
→ implementation
```

也就是：

\[
E
\xrightarrow{\text{distill}}
M
\xrightarrow{\text{compile}}
\Delta H
\]

这里：

\[
M\neq\Delta H
\]

这是非常重要的 separation。

---

## HASP 是最接近你的工作之一

HASP 已经提出 Program Function：

\[
PF =
(\texttt{should\_activate},
\texttt{intervene})
\]

也就是说一个 reusable mechanism 要定义：

> **什么时候启动 + 启动以后做什么。**

它也记录：

\[
(a_t^{orig},\tilde a_t)
\]

因此能观察 intervention 对 intermediate decision 的影响。

所以：

> guard + intervention

不能说首次出现。

---

## 但是你的 Mechanism IR 更完整

你现在设计的是：

\[
M=
(
guards,
decision\ contract,
runtime\ inputs,
state,
action,
fallback
)
\]

如果再把：

- attachment point / hook；
- ownership；
- observability；
- invariants；

加进去，那么：

\[
\boxed{
M=\text{implementation-independent runtime mechanism IR}
}
\]

这就和 HASP 的 skill function 有明显差别了。

特别是：

\[
M
\rightarrow
Compiler
\rightarrow
\Delta H
\]

意味着同一个 mechanism 可以有多个 realization：

```text
Mechanism:
"final answer 前检查 evidence sufficiency"
```

可以编译成：

```text
Prompt constraint
```

也可以：

```text
pre_final hook
```

也可以：

```text
Tool
```

甚至：

```text
parser / deterministic validator
```

于是你就真正把：

\[
\boxed{\text{what should happen}}
\]

和：

\[
\boxed{\text{how it is implemented}}
\]

解耦了。

这点很有论文价值。

---

# 十三、我认为你目前**最有潜力的新意**：Hook Feasibility

这是我此次检索后反而更看好的地方。

最近一篇工作名字就非常直接：

**Harness Updating Is Not Harness Benefit**。

它发现：

\[
\text{Harness Updating Capability}
\neq
\text{Harness Benefit Capability}
\]

尤其弱模型可能：

1. 根本不会 activate 相关 harness artifact；
2. activate 了也不能 faithfully follow。

因此弱模型不一定能真正享受更好的 Harness。

这和你的设计动机几乎完美吻合。

---

但他们做的是 **measurement / diagnosis**：

> weak model 为什么 benefit 不到 harness？

你则把这个观察变成了 optimizer 中的一个显式 decision gate：

\[
Mechanism
\rightarrow
\boxed{Student\ Capability\ Test}
\rightarrow
Compiler
\]

即：

> Teacher 认为这个机制是正确的，并不代表 Student 可以承担这个机制中的 semantic decision。

这是一个非常重要的 distinction。

比如 Teacher 得到一个机制：

> “当当前证据存在语义冲突而且冲突可能来自 entity ambiguity 时，启动验证。”

Teacher 能判断：

\[
conflict + ambiguity
\]

不意味着 4B Student 能稳定判断。

所以你问：

\[
P(
Student\ correctly\ executes\ guard
\mid
relevant\ state
)
\]

是否足够高。

如果不够：

```text
needs_spec_revision
```

那么可能改成 deterministic：

```text
if source_count < 2
```

或者变成更简单的 observable condition。

这个设计实际上是在做：

\[
\boxed{
Mechanism
\rightarrow
Student-realizable Mechanism
}
\]

我目前没有检索到 Harness evolution 工作把这一阶段显式放在 **compile 之前**。

这是我认为你最该保护、最该做实验的点之一。

---

# 十四、你的完整路线其实解决了一个很漂亮的 decomposition

可以这样写：

传统方法看到：

\[
Candidate\ fails
\]

只能得到：

\[
\Delta R < 0
\]

而你的框架可以逐层定位：

```text
Hypothesis unsupported
       ↓
research failure

Hypothesis supported
but mechanism cannot generalize
       ↓
evidence / abstraction failure

Mechanism sound
but Student cannot execute hook semantics
       ↓
feasibility failure

Mechanism feasible
but candidate behaves differently
       ↓
implementation / conformance failure

Candidate conformant
but global performance regresses
       ↓
interaction / generalization failure
```

所以它实际上构造了：

\[
\boxed{
\text{Hierarchical Credit Assignment for Harness Evolution}
}
\]

这比：

> “我们做了很多不同的 reviewer”

强得多。

---

# 十五、Role Contract / Reviewer 本身千万不要作为创新点

你现在用了很多名称：

- Failure Analyst；
- Hypothesis Researcher；
- Intervention Worker；
- Trial Reviewer；
- Evidence Reviewer；
- Mechanism Distiller；
- Hook Feasibility Reviewer；
- Compiler；
- Conformance Reviewer；
- Candidate Reviewer。

工程上这是清楚的。

但写论文时我建议**弱化这些 agent names**。

否则 reviewer 很容易觉得：

> “又是一个 role-playing multi-agent workflow。”

你的贡献不是：

\[
10\ 个 agents
\]

而是这些 roles 对应的 **information barriers / verification boundaries**。

例如：

```text
Trial Reviewer
```

真正对应的是：

\[
\text{single-trial validity judgment}
\]

```text
Evidence Reviewer
```

对应：

\[
\text{cross-trial hypothesis support}
\]

```text
Hook Feasibility Reviewer
```

对应：

\[
\text{target-model realizability test}
\]

所以论文最好讲：

\[
\boxed{Stages + Contracts + Gates}
\]

而不是：

\[
\boxed{Agents + Roles}
\]

---

# 十六、Event-driven Controller / Effect Receipt 怎么看

这是一个很好的系统实现。

VeRO 已经强调：

- versioned snapshot；
- budget-controlled evaluation；
- structured execution trace；
- reproducibility。

Shepherd 又把 execution trace 做成 typed event，并支持 exact replay/fork。

因此：

- event-driven；
- persistence；
- retry；
- checkpoint；
- receipt；

本身很难成为算法创新。

但它们能成为一个很好的 **systems contribution**：

> 我们的方法涉及外部 API、fork experiment 和多阶段 reviewer，因此 exactly-once effect 与 recoverable experiment 是保证研究过程正确性的必要基础设施。

我会把它作为：

\[
\text{enabling infrastructure}
\]

而不是 main contribution。

---

# 十七、你现在“现有工作局限”的第一句话需要修改

你现在写：

> 现有 Harness 自进化方法通常以“生成候选修改—运行完整评估—根据结果继续修改”为基本循环……

**方向基本对，但现在表述得过宽。**

因为 reviewer 可以立刻举：

- AHE：先做 structured evidence 和 prediction；
- Self-Harness：先做 weakness mining 和 addressability filtering；
- HSI：先生成带 falsification criterion 的 hypothesis；
- HarnessBank：有 gated screening；
- DREvo：先 recalibrate historical evidence；
- Shepherd：已有 counterfactual replay。

真正准确的 criticism 应该是：

> **即使近期方法已经改善 failure diagnosis、hypothesis formulation、candidate screening 和 regression testing，大多数方法仍然较早地把一个改进方向实例化为 persistent Harness Candidate，并主要依赖 Candidate-level rollout outcomes 来判断修改是否有效。因此，mechanism validity、target-model executability 和 implementation fidelity 往往在同一次 Candidate Evaluation 中被联合检验。**

这句话我认为比你原来的强很多。

因为攻击的是一个真正存在的 structural coupling：

\[
\boxed{
mechanism
+
capability
+
implementation
\rightarrow
one\ reward
}
\]

---

# 十八、这样，你的方法就可以顺理成章提出

我甚至建议给它一个概念：

## **Evidence-Gated Harness Evolution**

核心不是：

> 更多 reviewer。

而是：

\[
\boxed{
Do not compile before evidence.
}
\]

完整过程：

\[
\begin{aligned}
Failure
&\rightarrow Hypothesis\\
&\rightarrow Local\ Intervention\\
&\rightarrow Evidence\ Gate\\
&\rightarrow Mechanism\ IR\\
&\rightarrow Capability\ Gate\\
&\rightarrow Compilation\\
&\rightarrow Conformance\ Gate\\
&\rightarrow Candidate\ Evaluation
\end{aligned}
\]

因此相比 direct candidate search：

\[
F\rightarrow\Delta H\rightarrow Eval
\]

你提出：

\[
F
\rightarrow h
\rightarrow E(h)
\rightarrow M
\rightarrow Feasible(M,S)
\rightarrow Compile(M)
\rightarrow Eval
\]

我认为这是目前最漂亮的形式化。

---

# 十九、你的 novelty 我会分成三个等级

## 第一层：不要 claim

这些只是必要组成：

- frozen Student；
- external Teacher；
- editable Harness；
- failure analysis；
- rollback；
- regression；
- multi-agent role；
- event logging；
- Prefix-Fork primitive；
- falsifiable hypothesis。

都已经有明显 prior art。

---

# 二十、第二层：可以作为 supporting contributions

### 1. Mechanism IR

\[
evidence
\rightarrow
implementation-independent mechanism
\rightarrow
candidate
\]

尤其 guards / state / fallback / runtime input / decision contract。

### 2. Typed revision routing

\[
failure
\rightarrow
\begin{cases}
research\\
mechanism\\
feasibility\\
implementation\\
global\ regression
\end{cases}
\]

从而避免所有失败都重新回到 generic proposer。

### 3. Research artifacts + Effect Receipt

给长流程提供完整 lineage。

这些很有系统价值。

---

# 二十一、第一层真正可以打的核心贡献，我认为有三个

### **Contribution 1：Pre-compilation intervention testing**

> 把 executable Harness Candidate 从“第一层实验对象”推迟到最后，让可逆的 local intervention 成为低成本第一层实验对象。

即：

\[
\boxed{
Candidate\ Search
\rightarrow
Mechanism\ Experimentation
}
\]

---

### **Contribution 2：Evidence-to-mechanism separation**

不是：

\[
failure\rightarrow patch
\]

而是：

\[
failure
\rightarrow hypothesis
\rightarrow evidence
\rightarrow mechanism
\rightarrow patch
\]

这让：

\[
\text{scientific claim}
\]

和：

\[
\text{software implementation}
\]

可单独验证。

---

### **Contribution 3：Target-model realizability gating**

> 在 persistent Harness 中部署 semantic control 前，显式验证目标 Student 能否稳定执行这个 semantic responsibility。

形式上：

\[
\boxed{
Correct\ mechanism
\not\Rightarrow
Executable\ mechanism\ for\ Student
}
\]

然后定义：

\[
Feasible(M,S)
\]

作为 Compiler 的前置条件。

这个点特别适合你的“小模型 Student”设定。

而且它和现有实证“弱模型可能无法 activate/follow evolved harness”形成非常漂亮的 motivation。

---

# 二十二、你需要特别防止一个 reviewer 质疑

Reviewer 会问：

> **为什么不直接编译 Candidate 再跑？你前面搞这么多 Teacher Call，真的更省钱吗？**

这是你的生死实验之一。

不能只写：

> “逐层过滤，所以成本更低。”

必须证明。

比如比较：

### Baseline

\[
Failure
\rightarrow
Candidate
\rightarrow
FullEval
\]

### Yours

\[
Failure
\rightarrow
k\ LocalTrials
\rightarrow
Candidate
\rightarrow
FullEval
\]

需要报告：

\[
C_{\text{accepted patch}}
=
\frac{\text{total evolution cost}}
{\#\text{accepted useful patches}}
\]

至少同时报告：

- Teacher tokens；
- Student tokens；
- environment steps；
- wall-clock；
- full candidate evaluations；
- candidates compiled；
- intervention trials；
- accepted mechanism 数；
- final performance。

核心指标甚至可以是：

\[
\boxed{
\text{Full-Eval Avoidance Rate}
}
\]

例如：

> 70% 的方向在 Candidate 编译之前被否决，同时保留 95% 最终有效 Candidate。

这会非常漂亮。

---

# 二十三、第二个生死实验：你的 intermediate gates 到底有没有改善归因？

必须 ablation：

```text
Direct Compile
    ↓

+ Hypothesis
    ↓

+ Prefix-Fork Evidence
    ↓

+ Mechanism Distillation
    ↓

+ Hook Feasibility
    ↓

Full System
```

然后看：

### Candidate precision

\[
P(\text{candidate useful}\mid\text{compiled})
\]

你的系统应该显著提升。

也就是：

\[
\boxed{
\text{Candidate Yield}
=
\frac{\# useful\ compiled\ candidates}
{\# compiled\ candidates}
}
\]

如果 Direct Compile 是：

\[
15\%
\]

而你是：

\[
55\%
\]

论文就立住了。

---

# 二十四、Hook Feasibility 要单独做一个非常漂亮的实验

构造一组 mechanism：

\[
M_1,M_2,\dots,M_n
\]

Teacher 都判断：

\[
M_i=\text{semantically sound}
\]

但它们要求不同 semantic capability：

```text
simple deterministic guard
        ↓
simple classification
        ↓
contextual judgment
        ↓
multi-evidence semantic judgment
        ↓
long-horizon state inference
```

然后测不同 Student：

\[
1.5B,\ 4B,\ 8B,\ldots
\]

得到：

\[
P(\text{correct hook decision})
\]

你很可能能画出一个：

\[
\text{mechanism complexity}
\times
\text{student capability}
\]

的 feasibility map。

这会直接把你的工作从：

> “一个复杂 agent pipeline”

提升成：

> **研究 Harness mechanism 与 target-model capability matching 的工作。**

而近期工作已经证明 harness-benefit 和基础能力之间并不是简单单调关系，这给你的实验提供了非常好的前置依据。

---

# 二十五、所以如果现在让我评价“有没有新意”

我的判断是：

### **有，而且不是小改动式的新意。**

但前提是你必须**重新确定 novelty locus**。

如果你这样讲：

> 我们提出一个 Teacher Agent，包含 Failure Analyst、Researcher、Reviewer、Compiler，通过 Prefix Fork 优化 Harness。

我的评价大概只有：

\[
\boxed{4/10}
\]

因为每个词都已经有非常近的工作。

---

如果你这样讲：

> **现有 Harness evolution 将机制假设、目标模型可执行性和代码实现绑定进 Candidate-level evaluation。我们提出 evidence-gated evolution，在 persistent candidate 产生之前，利用 paired prefix interventions 检验行为假设，将支持证据蒸馏为 implementation-independent mechanism，并单独验证目标 Student 对 semantic hook 的 realizability；只有通过这些 gates 的机制才被编译和完整评估。**

那么我会给这个研究构想：

\[
\boxed{7.5\sim8/10}
\]

的新颖性评价。

因为它不是在发明新的搜索算法，而是在重新定义：

\[
\boxed{\text{Harness Evolution 的实验单位和 credit-assignment boundary}}
\]

这是一个有分量的方法论改变。

---

# 二十六、它在 Weng 那条路线里的位置也可以重新画出来

Weng 描述的是：

\[
Prompt
\rightarrow
Context
\rightarrow
Workflow
\rightarrow
Harness
\rightarrow
Harness\ Optimizer
\]

你做的不是再往右加一个新的 optimization target。

而是在 **Harness Optimizer 内部**进一步展开：

\[
\text{Search-Based Optimizer}
\]

变成：

\[
\boxed{
\text{Evidence-Driven Experimental Optimizer}
}
\]

即：

```text
                 Harness Optimizer
                       │
          ┌────────────┴────────────┐
          │                         │
   Candidate Search          Mechanism Research
          │                         │
   propose patch              hypothesis
          │                         │
   evaluate patch             intervene
          │                         │
      select                 collect evidence
                                    │
                              distill mechanism
                                    │
                             test realizability
                                    │
                                compile
                                    │
                              full evaluate
```

**左边是目前主流。你的核心应该是右边。**

这一定位我认为比“我们设计了一套更复杂、更可靠的 Harness evolution pipeline”强得多。

---

## 最终建议

你现在这段项目描述的设计本身我认为**已经比较完整，但论文叙事还没有把最有价值的创新暴露出来**。目前文字给人的第一印象仍然是：

> “现有方法太粗糙，我们加入更多阶段、roles 和 checks。”

你应该把核心命题收缩成一句更加研究化的话：

\[
\boxed{
\textbf{A harness hypothesis should be experimentally validated before it becomes a harness patch.}
}
\]

然后再补第二句：

\[
\boxed{
\textbf{A valid mechanism should be tested for target-model realizability before it is compiled into runtime control.}
}
\]

前一句把你和 Meta-Harness、Self-Harness、AHE、Harness-R1 的 **candidate-level optimization** 区分开；后一句把“小模型 Student”从一个应用设定提升为方法设计的核心原因。

这两条合起来，我认为就是你当前工作最有机会形成论文 identity 的地方。