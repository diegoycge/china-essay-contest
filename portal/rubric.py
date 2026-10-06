"""The judging rubric, as data.

Source: rubric-for-judges-sep14-2100.docx and the accompanying judging sheet.
The English text is reproduced from those documents. The Chinese text is a
working translation and should be reviewed by the committee before judging
opens. Example sentences are left in English in both languages because they
illustrate what essay text at each level looks like.

To change the rubric, edit this file and redeploy; nothing else needs to
change as long as the four criterion keys stay the same.
"""

from django.utils.translation import get_language

RUBRIC_URL = "https://www.dukechinaessay.com"

GENERAL_INSTRUCTIONS = {
    "en": [
        "Entries in both the high school division and the undergraduate division should be judged using the scoring system as outlined below; candidate scores will be compared against others in their own division.",
        "Essays are judged on the quality of writing, argument, and evidence. Judges may not penalize or reward an essay for being misaligned with their personal beliefs on the issue. If you feel that your personal standpoint on the issue hinders your ability to judge the essay fairly, you should refer the essay to the judge committee chair for reassignment.",
        "All essays are to be judged by at least two human readers and two AI readers. The two AI readers are to be provided the exact same judging criteria as presented to the human readers. All readers are to remain blind to scores that other judges have assigned a particular essay. The human reader score will account for 75% (37.5% each) and AI reader score will account for 25% (12.5% each) of the final score.",
        "Essays with significant divergences in scores assigned (exact criteria TBD) will be re-scored by one different human reader and one different AI reader.",
        "Human readers are discouraged from using AI to score essays.",
        "All final scores must be justified with at least 100 words of comments, addressing all aspects of the grading criteria.",
        "Topics, judging criteria, and more info can be found: https://www.dukechinaessay.com",
    ],
    "zh": [
        "高中组和本科组的参赛作品均应按照下述评分体系进行评审；参赛者的得分仅与同组别的其他参赛者比较。",
        "评审依据的是文章的写作质量、论证和论据。评委不得因文章观点与个人立场相左或一致而扣分或加分。如果您认为自己在相关议题上的个人立场会妨碍您公正评审某篇文章，应将该文章提交评审委员会主席重新分配。",
        "每篇文章至少由两名人工评委和两名 AI 评委评阅。AI 评委所获得的评分标准与人工评委完全相同。所有评委均不得知晓其他评委对同一篇文章给出的分数。人工评委的评分占最终成绩的 75%（每人 37.5%），AI 评委的评分占 25%（每个 12.5%）。",
        "评分差异显著的文章（具体标准待定）将由另一名人工评委和另一名 AI 评委重新评分。",
        "不鼓励人工评委使用 AI 为文章评分。",
        "所有最终评分均须附有至少 100 词的评语说明理由，并涵盖评分标准的各个方面。",
        "题目、评分标准及更多信息见：https://www.dukechinaessay.com",
    ],
}

SCORE_RANGES = {
    "en": "Essay scores in each category will be assigned on a scale of 0 to 10, in increments of 0.5. Judges are encouraged to use the full range of scores from 0 to 10. The default score assigned for an essay should therefore be 5, with points added or deducted as you read the essay against the prescribed criteria. Only essays of extraordinary quality should receive a score above 9, and only essays with issues significant enough to hinder comprehension should receive a score below 1, on any particular criteria.",
    "zh": "每个评分项的分数范围为 0 至 10 分，以 0.5 分为单位。鼓励评委充分使用 0 至 10 分的完整区间。因此，一篇文章的默认分数应为 5 分，再根据您对照评分标准阅读时的判断加分或减分。在任何一项标准上，只有质量非凡的文章才应获得 9 分以上，只有问题严重到妨碍理解的文章才应获得 1 分以下。",
}

AI_NOTE = {
    "en": [
        "Many studies have shown that humans, even trained professionals, cannot reliably distinguish between human-written and AI-generated texts, and that texts produced by ESL speakers are routinely flagged as more likely to be AI-generated even when they are not. AI-detector software on the market today also proves inaccurate in many cases. You should therefore not disqualify an essay, or assign low scores, simply because it reads like an AI-generated essay.",
        "However, AI-generated texts are more likely to be generic, less original in claims and use of evidence, and less varied in language and sentence construction. You may score essays on these criteria accordingly, independently of whether you suspect a particular essay may be AI-generated or AI-assisted.",
        "If an essay is submitted with unambiguous AI markers (e.g. Claude-styled format of title page, “happy to help!” phrases at the end of essay, fabricated citations, etc.), you should refer the essay to the committee chair who will then decide whether to disqualify the essay.",
        "All finalist essays will be run through plagiarism checks. However, if you suspect an essay to contain plagiarized text, please note this in the scoring sheet, in the Originality section.",
    ],
    "zh": [
        "许多研究表明，人类（即使是训练有素的专业人士）无法可靠地区分人类撰写的文本与 AI 生成的文本，而且以英语为第二语言者所写的文本即使并非 AI 生成，也经常被标记为更可能由 AI 生成。目前市面上的 AI 检测软件在许多情况下同样不准确。因此，您不应仅因一篇文章读起来像 AI 生成的，就取消其资格或给予低分。",
        "不过，AI 生成的文本往往更为空泛，论点和论据的使用缺乏原创性，语言和句式也较少变化。您可以据此按相应标准评分，而无需考虑您是否怀疑该文章由 AI 生成或经 AI 辅助完成。",
        "如果提交的文章带有明确无误的 AI 痕迹（例如 Claude 风格的标题页格式、文末出现“happy to help!”之类的语句、捏造的引文等），您应将该文章提交委员会主席，由其决定是否取消该文章的参赛资格。",
        "所有入围决赛的文章都将接受抄袭检测。但如果您怀疑某篇文章含有抄袭内容，请在评分表的“原创性”部分注明。",
    ],
}

CRITERIA_INTRO = {
    "en": "For each category, choose the level of ‘best fit’ and use the descriptions and examples as guides for how to score.",
    "zh": "对于每个评分项，请选择“最符合”的等级，并以描述和示例作为评分参考。",
}

CONFIRMATION = {
    "en": "I confirm that the assessment I provide above are the results of my honest and best effort deliberation, and that I am unaware of the identity of the essay’s author, or the other judge(s) reading the same essay. I acknowledge that my submission may be processed by a Duke-provided AI service.",
    "zh": "我确认，以上评审是我诚实并尽最大努力审慎考虑的结果，且我不知道该文章作者的身份，也不知道评阅同一篇文章的其他评委的身份。我知悉我提交的内容可能会由杜克大学提供的 AI 服务进行处理。",
}

CRITERIA = [
    {
        "key": "originality",
        "name": {"en": "Originality", "zh": "原创性"},
        "address": {
            "en": [
                "Is the argument distinct from what is commonly said on this issue?",
                "Is the stance consistent, and justified through the essay’s own reasoning?",
                "Does the evidence include primary or uncommonly cited sources?",
            ],
            "zh": [
                "论点是否有别于该议题上的常见说法？",
                "立场是否前后一致，并通过文章自身的推理加以论证？",
                "论据是否包含一手资料或不常被引用的资料？",
            ],
        },
        "levels": [
            {
                "range": "0–3",
                "desc": {
                    "en": [
                        "The essay simply repeats facts readily available online through cursory searches.",
                        "There is no stated argument in the essay.",
                        "The essay’s voice is clearly, repeatedly, and unambiguously that of an AI model (refer to the AI note above).",
                        "There is evidence of plagiarism.",
                    ],
                    "zh": [
                        "文章只是重复通过粗略搜索即可在网上轻易获得的事实。",
                        "文章没有明确提出论点。",
                        "文章的行文语气明显、反复且毫不含糊地呈现 AI 模型的特征（参见上文关于 AI 的说明）。",
                        "存在抄袭的证据。",
                    ],
                },
                "examples": [
                    "“China is a very large country and has a larger population than the US.”"
                ],
            },
            {
                "range": "4–6",
                "desc": {
                    "en": [
                        "The essay has a stated argument, but the argument is trite, completely uncontroversial, and commonly accepted by most people on the issue discussed.",
                    ],
                    "zh": [
                        "文章有明确的论点，但该论点陈旧老套、毫无争议，且为大多数人在该议题上所普遍接受。",
                    ],
                },
                "examples": ["“I believe the US should pay attention to China in world affairs.”"],
            },
            {
                "range": "7–8",
                "desc": {
                    "en": [
                        "The essay has an argument that is distinct from most commonly raised arguments on the particular issue, though not necessarily contrarian.",
                        "The essay argues a consistent stance on the topic discussed.",
                        "The argument uses original evidence, including primary sources, sources not commonly cited in media and academic writing on the issue, or sources that provides unique perspectives on the topic.",
                    ],
                    "zh": [
                        "文章的论点有别于该议题上最常见的论点，但不一定是反主流的观点。",
                        "文章在所讨论的题目上立场前后一致。",
                        "论证使用了原创性的论据，包括一手资料、媒体和学术写作中不常引用的资料，或能为该题目提供独特视角的资料。",
                    ],
                },
                "examples": [
                    "“America will lose the AI race for the same reason that it won the Second World War: domestic industrial capacity.”"
                ],
            },
            {
                "range": "9–10",
                "desc": {
                    "en": [
                        "The essay contributes to the discussion with remarkable originality and is able to provoke thought and discussions in readers. Its core idea is original enough to be published as an academic paper, or an opinion-editorial at a top-ranked journal or newspaper.",
                        "The essay argues a consistent stance on the topic discussed, and provides justification for its position through unique arguments.",
                        "The argument uses unusually well-assembled diverse and original evidence consistently throughout the paper.",
                    ],
                    "zh": [
                        "文章以非凡的原创性为相关讨论作出贡献，能够激发读者的思考和讨论。其核心观点的原创程度足以作为学术论文发表，或作为评论文章刊登于顶级期刊或报纸。",
                        "文章在所讨论的题目上立场前后一致，并通过独到的论证为其立场提供依据。",
                        "论证自始至终使用了组织得异常出色、多样且原创的论据。",
                    ],
                },
                "examples": [],
                "examples_note": {
                    "en": "N/A – that’s the nature of ‘originality’",
                    "zh": "无——这正是“原创性”的本质",
                },
            },
        ],
    },
    {
        "key": "clarity",
        "name": {"en": "Argument clarity and writing quality", "zh": "论点清晰度与写作质量"},
        "address": {
            "en": [
                "Is the argument explicitly stated and clear throughout?",
                "Is it narrow enough to argue in depth, and does it answer the question directly?",
                "Frequency of language errors, and whether they impede comprehension.",
            ],
            "zh": [
                "论点是否明确提出，并在全文中始终清晰？",
                "论点是否足够集中以便深入论证，并且直接回答了题目？",
                "语言错误的频率，以及是否妨碍理解。",
            ],
        },
        "levels": [
            {
                "range": "0–3",
                "desc": {
                    "en": [
                        "There is no stated argument in the essay.",
                        "There is a stated argument, but the argument is incomprehensible and confusing, or the argument does not answer the question at all.",
                        "There are a significant number of grammatical or spelling errors, and they impede comprehension.",
                    ],
                    "zh": [
                        "文章没有明确提出论点。",
                        "文章有明确的论点，但论点令人费解、含混不清，或完全没有回答题目。",
                        "存在大量语法或拼写错误，妨碍理解。",
                    ],
                },
                "examples": ["“I should be President because China AI.”"],
            },
            {
                "range": "4–6",
                "desc": {
                    "en": [
                        "The essay has a stated argument, but it could be further narrowed down or clarified easily in a way that would make the argument stronger.",
                        "The essay has an underlying argument, but is never explicitly stated, or is presented in a convoluted way.",
                        "There is a noticeable number of language errors, but they largely do not impede comprehension.",
                    ],
                    "zh": [
                        "文章有明确的论点，但可以很容易地进一步收窄或澄清，从而使论证更有力。",
                        "文章有潜在的论点，但从未明确表述，或表述方式迂回曲折。",
                        "存在较为明显的语言错误，但基本不妨碍理解。",
                    ],
                },
                "examples": [
                    "“I think that middle powers should change more and make sure that they can have both Chinese and American support.”"
                ],
            },
            {
                "range": "7–8",
                "desc": {
                    "en": [
                        "The essay has a stated argument that is consistent with what it argues, and this is clear to the reader throughout the essay.",
                        "The argument is narrow enough to explain in depth, answers the question directly, and written about in a concise and effective manner.",
                        "There are no, or very few language errors.",
                    ],
                    "zh": [
                        "文章明确提出的论点与其实际论证一致，读者在通篇阅读中始终清楚这一点。",
                        "论点足够集中，能够深入阐述；直接回答题目；行文简洁有效。",
                        "没有或极少有语言错误。",
                    ],
                },
                "examples": [
                    "“The EU should accept Canada as an associate member, for instance, in an effort to deepen security cooperation against previously underweighted threats from American hegemony.”"
                ],
            },
            {
                "range": "9–10",
                "desc": {
                    "en": [
                        "The argument is extraordinarily clearly argued, is intuitive to understand, and convinces the reader that the conclusion the essay makes is natural and a matter of course.",
                        "The argument answers the question in a very precise and direct way, written about concisely and effectively beyond the expected level for undergraduate writing.",
                        "There is no language error.",
                    ],
                    "zh": [
                        "论证极其清晰、易于理解，使读者确信文章的结论自然而然、顺理成章。",
                        "论点非常精确、直接地回答了题目，行文之简洁有效超出对本科写作的预期水平。",
                        "没有语言错误。",
                    ],
                },
                "examples": [],
                "examples_note": {"en": "N/A", "zh": "无"},
            },
        ],
    },
    {
        "key": "evidence",
        "name": {"en": "Use of evidence", "zh": "论据的运用"},
        "address": {
            "en": [
                "Is each key claim supported by specific, accurate, relevant evidence?",
                "Is the evidence connected to the claim, or merely dropped in?",
                "Does the essay engage critically with its sources, including those that cut against it?",
            ],
            "zh": [
                "每项关键主张是否都有具体、准确、相关的论据支持？",
                "论据是否与主张相联系，还是只是简单堆砌？",
                "文章是否批判性地对待其资料来源，包括那些不利于其论点的资料？",
            ],
        },
        "levels": [
            {
                "range": "0–3",
                "desc": {
                    "en": [
                        "The essay makes claims with no supporting evidence, or the evidence provided is irrelevant to the claims being made.",
                        "Evidence is factually wrong, misattributed, or fabricated (e.g. invented statistics, quotes, or citations).",
                        "The essay relies entirely on unsupported assertions, personal anecdotes, or generalizations presented as fact.",
                    ],
                    "zh": [
                        "文章提出主张却没有论据支持，或所提供的论据与主张无关。",
                        "论据存在事实错误、张冠李戴或系捏造（例如编造的统计数据、引语或引文）。",
                        "文章完全依赖未经证实的断言、个人轶事，或被当作事实陈述的笼统概括。",
                    ],
                },
                "examples": [
                    "“Everyone knows that China’s economy will collapse within five years.”",
                    "A statistic cited to a report that does not exist, or a quote attributed to the wrong person.",
                ],
            },
            {
                "range": "4–6",
                "desc": {
                    "en": [
                        "The essay uses some evidence, but it is limited to widely-cited headline facts, general news coverage, or a small number of secondary sources.",
                        "Evidence is broadly relevant but is dropped into the essay without being clearly connected to the specific claim it is meant to support.",
                        "Some claims that need support are left unsupported, or the essay leans heavily on a single source.",
                    ],
                    "zh": [
                        "文章使用了一些论据，但仅限于被广泛引用的重大事实、一般新闻报道或少量二手资料。",
                        "论据大体相关，但只是被放进文章，没有与其所要支持的具体主张明确联系起来。",
                        "一些需要支持的主张缺乏论据，或文章严重依赖单一来源。",
                    ],
                },
                "examples": [
                    "“According to the World Bank, China’s GDP grew at 5% last year, which shows that China is a strong economy.”"
                ],
            },
            {
                "range": "7–8",
                "desc": {
                    "en": [
                        "The essay supports its key claims with specific, accurate, and relevant evidence drawn from several credible sources.",
                        "Evidence is clearly tied to the claim it supports, and the essay explains why the evidence matters for the argument rather than simply presenting it.",
                        "The essay draws on at least some less obvious sources, such as primary documents, official statements, data, or specialist scholarship, and cites them accurately.",
                    ],
                    "zh": [
                        "文章以来自多个可靠来源的具体、准确且相关的论据支持其关键主张。",
                        "论据与其所支持的主张紧密相连，文章解释了论据对论证的意义，而非仅仅罗列。",
                        "文章至少引用了一些不那么显而易见的资料，如原始文件、官方声明、数据或专业学术研究，且引用准确。",
                    ],
                },
                "examples": [
                    "“Beijing’s own 2024 Government Work Report dropped the ‘housing is for living, not speculation’ slogan for the first time since 2016 – a signal that the leadership now sees the property downturn, not speculation, as the greater risk.”"
                ],
            },
            {
                "range": "9–10",
                "desc": {
                    "en": [
                        "The essay assembles a wide range of well-chosen evidence – including primary sources, data, and sources in the original language where appropriate – and every major claim is backed convincingly.",
                        "The essay engages critically with its evidence, acknowledging limitations, weighing competing sources, and addressing evidence that cuts against its argument.",
                        "The selection and use of evidence is of a standard one would expect in a published academic paper or an expert-authored op-ed.",
                    ],
                    "zh": [
                        "文章汇集了广泛且精心挑选的论据——包括一手资料、数据，并在适当情况下使用原文资料——每一项主要主张都得到了令人信服的支持。",
                        "文章以批判的态度对待论据：承认其局限性，权衡相互矛盾的资料，并回应不利于自身论点的证据。",
                        "论据的选择和使用达到了已发表的学术论文或专家撰写的评论文章应有的水准。",
                    ],
                },
                "examples": [],
                "examples_note": {"en": "N/A", "zh": "无"},
            },
        ],
    },
    {
        "key": "depth",
        "name": {"en": "Analytical depth", "zh": "分析深度"},
        "address": {
            "en": [
                "Does the essay explain mechanisms — how and why — rather than only describing?",
                "Are second-order effects, trade-offs, or competing interests considered?",
                "Does the essay engage seriously with the strongest counterargument?",
            ],
            "zh": [
                "文章是否解释了机制（如何以及为何），而不仅仅是描述？",
                "是否考虑了次级效应、利弊权衡或相互竞争的利益？",
                "文章是否认真回应了最有力的反方论点？",
            ],
        },
        "levels": [
            {
                "range": "0–3",
                "desc": {
                    "en": [
                        "The essay stays entirely at the level of description or summary; it reports what is happening without explaining why or what follows from it.",
                        "The essay presents a single, one-sided view with no reasoning offered, or the reasoning offered is illogical or contradicts itself.",
                        "The essay does not engage with the actual substance of the question beyond surface-level restatement.",
                    ],
                    "zh": [
                        "文章完全停留在描述或概述的层面；只报告正在发生什么，而不解释原因或由此产生的影响。",
                        "文章只呈现单一、片面的观点而不给出推理，或所给出的推理不合逻辑或自相矛盾。",
                        "文章除表面复述之外，没有触及题目的实质内容。",
                    ],
                },
                "examples": [
                    "“China and the US are competing. This is a big problem. The US should do something about it.”"
                ],
            },
            {
                "range": "4–6",
                "desc": {
                    "en": [
                        "The essay offers some explanation of causes or consequences, but the analysis is shallow, generic, or could apply to almost any issue.",
                        "The essay identifies a mechanism or reason but does not follow it through, or leaves obvious follow-up questions unaddressed.",
                        "Counterarguments are either ignored or mentioned only in passing and dismissed without real engagement.",
                    ],
                    "zh": [
                        "文章对原因或后果作了一些解释，但分析肤浅、空泛，或几乎可以套用于任何议题。",
                        "文章指出了某种机制或原因，但没有深入推演，或留下明显的后续问题未作回应。",
                        "对反方论点要么置之不理，要么只是顺带提及，未经认真回应便予以否定。",
                    ],
                },
                "examples": [
                    "“Tariffs hurt trade, so the US should reduce tariffs on China. Some people disagree, but I think trade is good for everyone.”"
                ],
            },
            {
                "range": "7–8",
                "desc": {
                    "en": [
                        "The essay explains the mechanisms behind its claims – how and why something happens – rather than simply asserting that it does.",
                        "The essay considers second-order effects, trade-offs, or the interests of multiple actors, and shows how they interact.",
                        "The essay engages seriously with at least one strong counterargument and explains why its own position still holds.",
                    ],
                    "zh": [
                        "文章解释了其主张背后的机制——事情如何发生、为何发生——而不仅仅是断言其发生。",
                        "文章考虑了次级效应、利弊权衡或多方行为体的利益，并说明它们如何相互作用。",
                        "文章认真回应了至少一个有力的反方论点，并解释了自身立场为何仍然成立。",
                    ],
                },
                "examples": [
                    "“Export controls on advanced chips slow China’s AI progress in the short term, but they also give Beijing a stronger incentive to subsidize domestic fabs – so the policy’s effect depends on whether the US can widen the gap faster than China can close it.”"
                ],
            },
            {
                "range": "9–10",
                "desc": {
                    "en": [
                        "The essay demonstrates a sophisticated, layered understanding of the issue, tracing causal chains, identifying tensions and unintended consequences, and situating the question in its broader political, economic, or historical context.",
                        "The essay anticipates and answers the strongest objections to its position, and is precise about the conditions under which its argument holds or fails.",
                        "The analysis yields insights that would be new even to a well-informed reader, at a level comparable to professional policy writing.",
                    ],
                    "zh": [
                        "文章展现出对议题成熟而有层次的理解：梳理因果链条，指出其中的张力和意外后果，并将问题置于更广阔的政治、经济或历史背景之中。",
                        "文章预见并回应了对其立场最有力的反驳，并精确说明其论证在何种条件下成立或不成立。",
                        "分析所得出的见解即使对熟悉情况的读者而言也是新颖的，水平可与专业政策写作相媲美。",
                    ],
                },
                "examples": [],
                "examples_note": {"en": "N/A", "zh": "无"},
            },
        ],
    },
]

# Upper bound (inclusive) of each level, used to highlight the band a score falls in.
LEVEL_UPPER_BOUNDS = [3.5, 6.5, 8.5, 10]


def _lang(lang=None):
    lang = lang or get_language() or "en"
    return "zh" if lang.lower().startswith("zh") else "en"


def criterion_name(key, lang=None):
    code = _lang(lang)
    for criterion in CRITERIA:
        if criterion["key"] == key:
            return criterion["name"][code]
    raise KeyError(key)


def get_rubric(lang=None):
    """The rubric flattened into the requested (or active) language."""
    code = _lang(lang)
    criteria = []
    for criterion in CRITERIA:
        levels = []
        for index, level in enumerate(criterion["levels"]):
            note = level.get("examples_note")
            levels.append(
                {
                    "index": index,
                    "range": level["range"],
                    "desc": level["desc"][code],
                    "examples": level["examples"],
                    "examples_note": note[code] if note else "",
                }
            )
        criteria.append(
            {
                "key": criterion["key"],
                "name": criterion["name"][code],
                "address": criterion["address"][code],
                "levels": levels,
            }
        )
    return {
        "general": GENERAL_INSTRUCTIONS[code],
        "score_ranges": SCORE_RANGES[code],
        "ai_note": AI_NOTE[code],
        "criteria_intro": CRITERIA_INTRO[code],
        "confirmation": CONFIRMATION[code],
        "criteria": criteria,
        "url": RUBRIC_URL,
    }
