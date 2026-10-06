"""This year's contest, as published to contestants.

Source: https://www.dukechinaessay.com (read 5 October 2026). The English
text of the prompts is reproduced from that page. The Chinese text is a
working translation and should be reviewed by the committee, like the rubric.

`python manage.py load_contest` copies the prompts and the basic facts into
the database; after that they can be edited under Setup in the portal. The
brief for judges further down is shown on the rubric page as written here.
"""

from django.utils.translation import get_language

WEBSITE = "https://www.dukechinaessay.com"
CONTEST_NAME = "Duke-UNC China Leadership Summit (CLS) Essay Contest 2026"
CONTACT_EMAIL = "contact@dukeunccls.com"
WORD_LIMIT = 1500

# What the organisers published about dates and logistics. Shown to
# administrators only; none of it drives the portal's own judging deadlines.
LOGISTICS = {
    "en": [
        "Submissions close on October 15, 2026 at 11:59 PM EST; late entries are accepted until November 9, 2026.",
        "Contestants email a PDF to contact@dukeunccls.com with the subject line “Last Name, First Name - Duke CLS Essay Competition 2026”.",
        "Every PDF must begin with a cover page giving the author’s full name, school or institution, word count and the prompt selected (I–VI).",
        "Winning essays are recognized at the 2027 Duke-UNC China Leadership Summit in Durham, North Carolina.",
    ],
    "zh": [
        "投稿截止时间为 2026 年 10 月 15 日美国东部时间晚 11:59；逾期投稿可延至 2026 年 11 月 9 日。",
        "参赛者将 PDF 发送至 contact@dukeunccls.com，邮件标题为“Last Name, First Name - Duke CLS Essay Competition 2026”。",
        "每份 PDF 必须以封面页开头，写明作者全名、学校或机构、字数以及所选题目（I–VI）。",
        "获奖文章将在北卡罗来纳州达勒姆举行的 2027 年杜克–北卡中国领导力峰会上获得表彰。",
    ],
}

# (number, category, theme en, theme zh, question en, question zh)
PROMPTS = [
    (
        1,
        "hs",
        "Artificial Intelligence and Governance",
        "人工智能与治理",
        "Compare U.S. and Chinese approaches to AI governance in the last five years. What does the comparison reveal about how each government understands what AI is and what it does?",
        "比较过去五年中美两国在人工智能治理上的做法。这一比较揭示了两国政府各自如何理解人工智能是什么、能做什么？",
    ),
    (
        2,
        "hs",
        "Economic Interdependence",
        "经济相互依存",
        "With reference to either China or the United States, what are the relative harms and benefits of economic interdependence? Looking ahead, what are the implications of such interdependence?",
        "以中国或美国为例，经济相互依存的利弊各有哪些？展望未来，这种相互依存意味着什么？",
    ),
    (
        3,
        "hs",
        "Climate and Cooperation",
        "气候与合作",
        "Many would argue the U.S. and China should cooperate on climate change, yet little progress has been made. What is one realistic step that could move them toward cooperation, and why might it work?",
        "许多人认为中美应在气候变化问题上开展合作，但迄今进展甚微。有哪一项切实可行的举措能推动两国走向合作？它为什么可能奏效？",
    ),
    (
        4,
        "ug",
        "Prospective Policy Analysis",
        "前瞻性政策分析",
        "Imagine writing, in 2032, a prospective analysis of a major U.S.-China-related policy outcome whose origins lie in decisions being made right now. The outcome has not happened yet, but is being set up by current choices. Identify the decisions or pattern of decisions that will produce this outcome. Then, propose what should be done today to secure or avert this outcome.",
        "设想你身处 2032 年，为一项重大的涉中美关系政策结果撰写前瞻性分析，而该结果的根源在于当下正在作出的决策。这一结果尚未发生，但正由当前的选择所促成。请指出将导致这一结果的决策或决策模式，并提出今天应当采取哪些行动来促成或避免这一结果。",
    ),
    (
        5,
        "ug",
        "Middle Powers and Strategic Adaptation",
        "中等强国与战略调适",
        "As China's rise and U.S.-China competition reshape global institutions, how should middle powers and regional blocs adapt their policies over the next decade to maximize their strategic interests? Assess current dynamics, forecast likely shifts, and propose innovative strategic frameworks for your chosen actor(s).",
        "随着中国崛起和中美竞争重塑全球机制，中等强国和区域集团在未来十年应如何调整政策，以实现自身战略利益的最大化？请评估当前态势，预测可能出现的变化，并为你所选择的行为体提出富有新意的战略框架。",
    ),
    (
        6,
        "ug",
        "Digital Sovereignty and Governance",
        "数字主权与治理",
        "Drawing on current models of how China, the U.S., and the EU treat data, digital infrastructure, and advanced technologies as matters of sovereign control, propose governance frameworks that are both innovative and realistic, balancing competing interests across these three actors.",
        "结合中国、美国和欧盟当前将数据、数字基础设施和先进技术视为主权控制事项的不同模式，提出既有新意又切实可行、能够平衡三方相互竞争的利益的治理框架。",
    ),
]

# What judges should know about what contestants were asked to do.
# %(limit)s is filled from Settings so the two cannot disagree.
BRIEF = {
    "en": [
        "This year’s theme is U.S.–China relations. The contest is open to high school and undergraduate students anywhere in the world, and essays must be written in English.",
        "Essays may be up to %(limit)s words, in both categories.",
        "Prompts I–III are the high school category and Prompts IV–VI the undergraduate category. A high school student may answer an undergraduate prompt and is then considered in the undergraduate category, so every essay is compared with the others in the category of the prompt it answers.",
        "Contestants were asked for a PDF, double-spaced in 12-point Arial or Times New Roman, with page numbers at the bottom right and a cover page giving their name, school, word count and prompt. The cover page is removed before you see the essay.",
        "No particular citation style is required: MLA, APA and Chicago are all acceptable, provided the essay is consistent and clear. Sources must be acknowledged whether they are quoted, paraphrased or built upon.",
        "On AI, contestants were told that they may use AI tools to develop their thinking, explore counterarguments or pressure-test their ideas, but that what they submit must be their own writing; AI-generated content and collaborative writing are not permitted.",
        "Submissions found to contain plagiarism are disqualified.",
        "Contestants were told that essays are judged on clarity of argument, quality of evidence, analytical depth, originality and prose quality, and that a well-structured essay which engages honestly with counterarguments will be rewarded.",
    ],
    "zh": [
        "本届主题为中美关系。比赛面向世界各地的高中生和本科生，文章须以英文撰写。",
        "两个组别的文章篇幅均不超过 %(limit)s 词。",
        "题目 I–III 属于高中组，题目 IV–VI 属于本科组。高中生可以选答本科组题目，届时将在本科组参评；因此每篇文章都与回答同一组别题目的其他文章进行比较。",
        "参赛者须提交 PDF：双倍行距，12 号 Arial 或 Times New Roman 字体，页码位于右下角，并附封面页写明姓名、学校、字数和所选题目。封面页在您看到文章之前已被移除。",
        "不要求特定的引用格式：MLA、APA 和 Chicago 均可，只要全文一致、清晰即可。无论是直接引用、转述还是借鉴他人观点，都必须注明出处。",
        "关于 AI，参赛者被告知：可以使用 AI 工具帮助思考、探讨反方观点或检验自己的想法，但提交的内容必须是本人撰写；不允许提交 AI 生成的内容或合作撰写的作品。",
        "发现存在抄袭的作品将被取消资格。",
        "参赛者被告知：评审依据是论点的清晰度、论据的质量、分析深度、原创性和行文质量；结构清晰并能坦诚回应反方观点的文章将获得更高评价。",
    ],
}

_ROMAN = ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}


def roman(number):
    """1 -> "I". The contest numbers its prompts I–VI."""
    if not 0 < number < 40:
        return str(number)
    out = ""
    for value, symbol in _ROMAN:
        while number >= value:
            out += symbol
            number -= value
    return out


def from_roman(text):
    """ "iv" -> 4, or None if the text is not a small Roman numeral."""
    text = text.strip().upper()
    if not text or any(ch not in _ROMAN_VALUES for ch in text) or len(text) > 6:
        return None
    total = 0
    for index, ch in enumerate(text):
        value = _ROMAN_VALUES[ch]
        following = _ROMAN_VALUES[text[index + 1]] if index + 1 < len(text) else 0
        total += -value if value < following else value
    return total if roman(total) == text else None


def _lang():
    return "zh" if (get_language() or "en").lower().startswith("zh") else "en"


def brief(word_limit):
    return [line % {"limit": f"{word_limit:,}"} for line in BRIEF[_lang()]]


def logistics():
    return LOGISTICS[_lang()]
