# -*- coding: utf-8 -*-
"""
实验材料配置(正式材料)。
- 受试者只在第一阶段阅读正方材料(participant_article);阶段 2/3 不再阅读,
  其 participant_article 保留作为"该阶段受试者原本要学习的内容"的参照,不在界面展示
- agent 每阶段阅读各自的反方材料(agent_article),其辩论发言只能基于该材料
- 三个阶段共享同一辩论总议题,每阶段聚焦各自的 Learning Goal;
  第 N 阶段讨论中 agent 会自然地把话题引向第 N+1 阶段的 Learning Goal(见 app.py next_learning_goal)
"""

DEBATE_MOTION = "AGI has already been achieved."
DEBATE_MOTION_ZH = "通用人工智能（AGI）已经实现。"

# 中文版材料说明:
# 受试者界面切换到中文时展示 *_zh 字段(界面会标注"由 AI 翻译")。
# 采用静态预译而非运行时调用模型翻译,以保证所有受试者读到完全一致的刺激材料。
# 英文原文为准;修改英文材料后请同步更新对应译文。
# agent_article 无需翻译:它只注入系统提示词,不向受试者展示。

PHASES = [
    {
        "id": 1,
        "learning_goal": "What is AGI, and how do we measure AGI (Turing Test, AI as a tool, etc.)?",
        "topic": DEBATE_MOTION,
        "agent_stance": "Against the motion: AGI has not been achieved; AI should be viewed as a powerful tool, and passing behavioral tests like the Turing Test does not demonstrate genuine understanding.",
        "participant_article": """Learning Goal: What is AGI, and how do we measure AGI (Turing Test, AI as a tool, etc.)?

Artificial General Intelligence (AGI) refers to an artificial intelligence system capable of performing successfully across a broad range of cognitive tasks rather than being limited to a single specialized function. Unlike traditional AI systems that are designed for specific applications, AGI is expected to transfer knowledge between domains, adapt to unfamiliar situations, and solve different kinds of problems. Although the concept of AGI is widely discussed, there is still no universally accepted definition or clear threshold for determining when it has been achieved. Most researchers agree, however, that AGI should demonstrate both breadth and flexibility across many domains rather than excellence in only one task.

Because intelligence cannot be observed directly, it is usually assessed through behavior. Human intelligence is inferred from how people perform on increasingly difficult cognitive tasks rather than from direct observation of the brain itself. Some researchers argue that AI should be evaluated according to the same principle. If humans are considered intelligent because of what they can do, then AI systems should also be judged by their demonstrated capabilities instead of the mechanisms behind them.

One of the best-known behavioral evaluations is the Turing Test, proposed by Alan Turing in 1950. The test asks whether a machine can communicate naturally enough that human judges cannot reliably distinguish it from another person. Recent research found that GPT-4.5 was identified as human in approximately 73% of conversations. Together with strong performance across language, mathematics, reasoning, and creative tasks, this evidence has led some researchers to argue that current large language models already demonstrate the behavioral characteristics expected of general intelligence.""",
        "learning_goal_zh": "什么是通用人工智能（AGI）？我们如何测量 AGI（图灵测试、把 AI 视为工具等）？",
        "topic_zh": DEBATE_MOTION_ZH,
        "participant_article_zh": """学习目标：什么是通用人工智能（AGI）？我们如何测量 AGI（图灵测试、把 AI 视为工具等）？

通用人工智能（AGI）指的是一种能够在广泛的认知任务上成功执行、而不局限于某项专门功能的人工智能系统。与为特定应用而设计的传统 AI 系统不同，人们期待 AGI 能够在不同领域之间迁移知识、适应陌生情境，并解决各种不同类型的问题。尽管 AGI 这一概念被广泛讨论，但至今仍没有一个普遍接受的定义，也没有明确的门槛来判定它何时算是实现了。不过，多数研究者都同意：AGI 应当在众多领域中同时展现出广度与灵活性，而不只是在单一任务上表现卓越。

由于智能无法被直接观察，它通常通过行为来评估。人类的智能是从人们在难度递增的认知任务上的表现推断出来的，而不是通过直接观察大脑本身得出的。一些研究者主张，AI 也应当依据同样的原则来评价。如果我们认为人类之所以有智能是因为他们能做什么，那么 AI 系统也应当依据其展现出的能力、而非其背后的机制来评判。

最著名的行为评估之一是图灵测试，由艾伦·图灵于 1950 年提出。该测试考察机器能否自然地交流，以至于人类评判者无法可靠地将它与另一个人区分开来。近期研究发现，GPT-4.5 在约 73% 的对话中被判定为人类。再加上它在语言、数学、推理和创造性任务上的出色表现，这些证据使一些研究者认为：当前的大语言模型已经展现出人们期待于通用智能的行为特征。""",
        "agent_article": """Learning Goal: What is AGI, and how do we measure AGI (Turing Test, AI as a tool, etc.)?

Artificial General Intelligence (AGI) is commonly described as an AI system that demonstrates broad, human-level intelligence across many different tasks. However, despite its popularity, there is still no universally accepted definition of AGI or a clear standard for determining when it has been achieved. While some people associate AGI with human-level performance on a wide range of tasks, others argue that performing well is not enough. Intelligence involves more than producing correct answers that it also includes understanding, learning independently, adapting to unfamiliar situations, and applying knowledge flexibly across different contexts. Because these characteristics are difficult to define and measure, many researchers believe that claims about AGI should be made cautiously.

One of the most widely discussed evaluations of AI is the Turing Test, which measures whether a machine can imitate human conversation convincingly enough to fool human judges. Although recent language models have performed remarkably well on this test, critics argue that passing the Turing Test demonstrates only that an AI can produce human-like responses, not that it genuinely understands what it is saying. A machine may successfully imitate intelligent behavior without possessing the underlying cognitive processes that give rise to human intelligence. From this perspective, AI should be viewed primarily as a powerful tool designed to perform tasks that humans typically perform, rather than as evidence that machines have already achieved general intelligence.""",
    },
    {
        "id": 2,
        "learning_goal": "How is AI trained (pattern matching, probability, etc.)?",
        "topic": DEBATE_MOTION,
        "agent_stance": "Against the motion: AI's statistical, probability-based learning is fundamentally different from the mechanisms that give rise to general intelligence; impressive performance does not indicate genuine understanding.",
        "participant_article": """Learning Goal: How is AI trained (pattern matching, probability, etc.)?

Large language models are trained using enormous collections of text gathered from books, websites, articles, and other written sources. During training, the model repeatedly predicts the next word in a sentence and adjusts billions of internal parameters to improve its predictions. Because the training process is based on statistical relationships and probability, critics often describe these systems as performing sophisticated pattern matching. However, supporters argue that the way intelligence develops should not be confused with how intelligence is evaluated.

After training, modern AI systems are capable of much more than repeating memorized examples. They can solve unfamiliar mathematical problems, reason across multiple domains, interpret both images and text, and respond appropriately to situations that were never explicitly encountered during training. Researchers suggest that these abilities indicate the emergence of internal representations, sometimes referred to as world models, which enable AI systems to generalize knowledge, make predictions, and reason about hypothetical situations.

Importantly, the expert argue that intelligence does not require human-like learning mechanisms. Human intelligence is produced by biological evolution and neural processes, whereas AI learns through optimization and statistical prediction. Although these mechanisms are fundamentally different, different learning processes do not necessarily imply different levels of intelligence. If a system consistently demonstrates flexible reasoning and broad competence across diverse tasks, its intelligence should be evaluated by its capabilities rather than by the specific method through which those capabilities were acquired.""",
        "learning_goal_zh": "AI 是如何训练出来的（模式匹配、概率等）？",
        "topic_zh": DEBATE_MOTION_ZH,
        "participant_article_zh": """学习目标：AI 是如何训练出来的（模式匹配、概率等）？

大语言模型是用从书籍、网站、文章以及其他书面来源收集来的海量文本训练的。在训练过程中，模型反复预测句子中的下一个词，并调整数十亿个内部参数来改进其预测。由于训练过程建立在统计关系和概率之上，批评者常把这类系统描述为在做复杂的模式匹配。然而支持者认为，智能是如何发展出来的，不应与智能是如何被评估的混为一谈。

训练完成后，现代 AI 系统的能力远不止复述记住的例子。它们能解决陌生的数学问题、在多个领域之间进行推理、同时理解图像与文本，并对训练中从未明确遇到过的情境做出恰当反应。研究者认为，这些能力表明系统内部形成了某种内部表征（有时被称为"世界模型"），使 AI 系统能够泛化知识、做出预测，并对假设情境进行推理。

尤为重要的是，专家们主张智能并不要求具备类人的学习机制。人类智能由生物演化和神经过程产生，而 AI 则通过优化和统计预测来学习。尽管这些机制存在根本差异，但不同的学习过程并不必然意味着不同的智能水平。如果一个系统能在多样的任务上持续展现灵活的推理与广泛的胜任力，那么就应当依据其能力、而非依据这些能力具体是通过何种方法获得的，来评价它的智能。""",
        "agent_article": """Learning Goal: How is AI trained (pattern matching, probability, etc.)?

Modern large language models are trained using enormous collections of human-generated text. During training, they learn statistical relationships among words by repeatedly predicting the most probable next token in a sequence. As a result, AI systems become highly effective at generating fluent language and solving many practical tasks. However, critics argue that this process remains fundamentally different from human learning. Rather than understanding concepts or reasoning independently, AI systems generate responses by identifying complex statistical patterns learned from previous examples. In this sense, they function as sophisticated probability-based systems that transform inputs into outputs.

Supporters of this view emphasize that AI does not create knowledge in the same way humans do. Instead, it recombines patterns extracted from massive amounts of existing human data. When AI produces an answer, it is not necessarily reasoning through a problem or forming new ideas; it is predicting what response is most likely to follow a given prompt based on its training. Although these predictions can appear remarkably intelligent, impressive performance does not necessarily indicate genuine understanding. Furthermore, current AI systems cannot independently identify their own mistakes, acquire new knowledge through lived experience, or continuously improve without additional human-designed training. From this perspective, today's AI models remain highly capable computational tools, but their statistical learning process is fundamentally different from the mechanisms that give rise to general intelligence in humans.""",
    },
    {
        "id": 3,
        "learning_goal": "How has human intelligence emerged? And how do we assess human intelligence?",
        "topic": DEBATE_MOTION,
        "agent_stance": "Against the motion: human intelligence emerges from biological evolution and lived interaction with the world; AI's apparent intelligence is sophisticated statistical computation, so current evidence is insufficient to conclude AGI has been achieved.",
        "participant_article": """Learning Goal: How has human intelligence emerged? And how do we assess human intelligence?

Human intelligence has traditionally been evaluated through observable performance rather than direct examination of mental processes. Psychologists, educators, and researchers assess intelligence by asking individuals to solve problems, communicate effectively, adapt to unfamiliar situations, and apply knowledge across different contexts. No single intelligence test provides definitive proof. Instead, judgments about intelligence are based on the accumulation of evidence collected from many different cognitive tasks.

Supporters of AGI argue that the same standard should be applied consistently to both humans and AI systems. They note that humans themselves vary greatly in intelligence, make mistakes, forget information, and specialize in different domains. No individual possesses perfect knowledge or masters every possible cognitive task. Therefore, perfection should not be considered a requirement for general intelligence. Likewise, intelligence does not require a human brain, a biological body, or identical cognitive processes. These characteristics may influence how intelligence develops, but they are not what define intelligence itself.

Using this behavioral framework, recent large language models have demonstrated increasingly broad competence across language, mathematics, scientific reasoning, creative tasks, and practical problem solving. Rather than relying on a single benchmark, supporters argue that the growing body of evidence across many independent evaluations provides sufficient reason to attribute general intelligence to these systems. From this perspective, if humans are recognized as intelligent based on observable behavior, then current frontier AI systems should be evaluated according to the same standard, leading to the conclusion that AGI has already been achieved.""",
        "learning_goal_zh": "人类智能是如何产生的？我们又如何评估人类智能？",
        "topic_zh": DEBATE_MOTION_ZH,
        "participant_article_zh": """学习目标：人类智能是如何产生的？我们又如何评估人类智能？

人类智能历来是通过可观察的表现来评估的，而不是通过直接考察心理过程。心理学家、教育者和研究者通过要求个体解决问题、有效沟通、适应陌生情境以及在不同情境中运用知识，来评估其智能。没有任何单一的智力测验能提供决定性的证明。相反，关于智能的判断建立在从许多不同认知任务中收集到的证据的累积之上。

AGI 的支持者主张，同一套标准应当一致地适用于人类和 AI 系统。他们指出，人类自身的智能水平就差异很大，会犯错、会遗忘信息，并且各自擅长不同的领域。没有哪个个体拥有完美的知识，或精通一切可能的认知任务。因此，完美不应被视为通用智能的必要条件。同样，智能也并不要求具备人类的大脑、生物性的身体或完全相同的认知过程。这些特征可能影响智能如何发展，但它们并不是智能的定义性要素。

在这一行为主义框架下，近期的大语言模型在语言、数学、科学推理、创造性任务以及实际问题解决方面，展现出日益广泛的胜任力。支持者认为，不必依赖单一的基准测试；来自众多独立评估的、不断累积的证据，已足以将通用智能归属于这些系统。从这一视角看，如果人类是基于可观察的行为而被认定为有智能的，那么当今前沿的 AI 系统就应当依据同样的标准来评价，由此可以得出结论：AGI 已经实现。""",
        "agent_article": """Learning Goal: How has human intelligence emerged? And how do we assess human intelligence?

Human intelligence is the product of billions of years of biological evolution and lifelong interaction with the physical and social world. From birth, humans continuously learn through perception, movement, communication, trial and error, and direct experience. Intelligence develops as people adapt to changing environments, form goals, reflect on mistakes, and modify their behavior over time. This process involves not only acquiring information but also understanding meaning, building mental models, and integrating knowledge from diverse experiences. Because human intelligence emerges through continuous interaction with the world, many researchers argue that it cannot be reduced to successful task performance alone.

Although AI systems can outperform humans on many specialized tasks, critics argue that these achievements should not be confused with general intelligence. Humans can learn independently from everyday experiences, transfer knowledge across unfamiliar situations, and generate entirely new ideas without relying on massive collections of previously generated examples. Current AI systems, by contrast, depend on training data prepared by humans and require extensive computational resources and human intervention to improve. Their apparent intelligence results from sophisticated statistical computation rather than the biological, developmental, and adaptive processes that characterize human cognition. Therefore, while AI has become an extraordinarily useful technology capable of assisting humans in many domains, many researchers argue that it remains a powerful tool rather than a genuinely intelligent agent. From this perspective, current evidence is insufficient to conclude that AGI has already been achieved.""",
    },
]

# 每个阶段需要引发的认知冲突次数,达到后进入总结环节
CONFLICTS_REQUIRED = 3
